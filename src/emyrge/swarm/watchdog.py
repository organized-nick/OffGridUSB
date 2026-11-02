"""Cluster health watchdog: probes swarm peers and recovers from drops.

The web app forms a live cluster via CoordinatorRuntime.form_cluster(); this
watchdog keeps it honest afterwards:

- periodically re-handshakes every known peer (verified at cluster formation
  plus any peers that dropped or returned since),
- when membership changes (peer dropped or returned), re-runs the planner
  against the surviving nodes via a caller-provided re-form callback,
- emits timestamped events for the UI (peer_dropped, peer_returned,
  cluster_reformed, cluster_lost, probe_error),
- runs until stopped, or until every known peer is gone (cluster_lost).

Single-client reality check: ggml-rpc-server and the swarm node responder are
single-client services, so probes are cheap TCP handshakes with a short
timeout, run sequentially, and are throttled by ``interval``.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from emyrge.swarm.runtime import SwarmHandshakeError, handshake_node

DEFAULT_PROBE_INTERVAL_SEC = 5.0
DEFAULT_PROBE_TIMEOUT_SEC = 0.8


class SwarmWatchdog:
    """Background health monitor for a formed swarm cluster."""

    def __init__(
        self,
        peers: List[Dict[str, Any]],
        interval: float = DEFAULT_PROBE_INTERVAL_SEC,
        probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SEC,
        reform: Optional[Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = None,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        # peers: [{"id","ip","port", ...}] — we track everything we've ever
        # verified for this cluster so returning peers get re-adopted.
        self._peers: Dict[str, Dict[str, Any]] = {}
        for p in peers or []:
            if isinstance(p, dict) and p.get("ip"):
                self._peers[str(p.get("id") or f"{p['ip']}:{p.get('port', 50052)}")] = dict(p)
        self.interval = max(0.05, float(interval))
        self.probe_timeout = float(probe_timeout)
        self._reform = reform
        self._on_event = on_event
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.health: Dict[str, Any] = {"checked_at": 0.0, "nodes": [], "all_ok": True}

    # -- events ------------------------------------------------------------
    def _event(self, kind: str, msg: str) -> None:
        if self._on_event:
            try:
                self._on_event(kind, msg)
            except Exception:
                pass

    # -- probing -----------------------------------------------------------
    def probe_once(self) -> tuple[List[str], List[Dict[str, Any]]]:
        """Handshake every known peer once. Returns (alive_ids, dead_nodes).

        Also refreshes the public ``health`` snapshot so status polls can read
        the last probe result without probing themselves.
        """
        alive: List[str] = []
        dead: List[Dict[str, Any]] = []
        for pid, peer in list(self._peers.items()):
            try:
                node = handshake_node(peer["ip"], int(peer.get("port", 50052)), timeout=self.probe_timeout)
                alive.append(node.get("id") or pid)
            except SwarmHandshakeError as exc:
                dead.append({**peer, "id": pid, "error": str(exc)})
            except Exception as exc:  # defensive: never let the watchdog die
                dead.append({**peer, "id": pid, "error": f"probe error: {exc}"})
        self._update_health(alive, dead)
        return alive, dead

    def _update_health(self, alive: List[str], dead: List[Dict[str, Any]]) -> None:
        self.health = {
            "checked_at": time.time(),
            "nodes": [
                {"id": pid, **self._peers[pid], "ok": pid in alive}
                for pid in self._peers
            ],
            "all_ok": len(dead) == 0,
        }

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, name="swarm-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_evt.is_set()

    def _loop(self) -> None:
        # Re-adoption bookkeeping: peers that went down stay tracked so we
        # notice when they come back.
        missing: set = set()
        while not self._stop_evt.is_set():
            alive, dead = self.probe_once()
            new_missing = {d["id"] for d in dead}
            returned = missing - new_missing
            if new_missing and new_missing != missing:
                for d in dead:
                    if d["id"] in new_missing - missing:
                        self._event("peer_dropped", f"{d['id']} ({d['ip']}:{d.get('port')}) dropped: {d.get('error', 'unreachable')}")
            if returned:
                for pid in sorted(returned):
                    p = self._peers.get(pid, {})
                    self._event("peer_returned", f"{pid} ({p.get('ip')}:{p.get('port')}) reachable again")

            membership_changed = bool(new_missing != missing or returned)
            missing = new_missing

            if membership_changed and self._reform is not None:
                alive_peers = [p for pid, p in self._peers.items() if pid not in new_missing]
                if not alive_peers:
                    self._event("cluster_lost", "all peers unreachable — cluster dissolved")
                    break
                try:
                    plan = self._reform(alive_peers)
                    live = (plan or {}).get("live") or {}
                    if live.get("cluster_formed"):
                        reverified = live.get("verified_nodes") or []
                        dropped_now = [pid for pid in self._peers if pid not in reverified]
                        # prune only peers the planner actively rejected;
                        # keep unreachable-but-plausible peers tracked so a
                        # later probe can re-adopt them.
                        if dropped_now:
                            self._event(
                                "cluster_reformed",
                                f"re-formed cluster on {len(reverified)} node(s): {', '.join(reverified)}",
                            )
                        else:
                            self._event(
                                "cluster_reformed",
                                f"re-formed cluster on {len(reverified)} node(s): {', '.join(reverified)}",
                            )
                    else:
                        self._event("cluster_lost", "re-form attempt failed — no verified nodes")
                        break
                except Exception as exc:
                    self._event("cluster_lost", f"re-form attempt errored: {exc}")
                    break

            self._stop_evt.wait(self.interval)


def peers_from_verified(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract watchdog peer specs from handshake results or verified nodes.

    Accepts both live.handshakes entries ({ip,port,ok,id}) and full node
    inventory dicts; handshake failures (ok=False) are skipped.
    """
    peers: List[Dict[str, Any]] = []
    for n in entries or []:
        if not isinstance(n, dict) or not n.get("ip"):
            continue
        if n.get("ok") is False:
            continue
        peers.append({"id": n.get("id"), "ip": n["ip"], "port": int(n.get("port", 50052)), "ram_mb": n.get("ram_mb"), "vram_mb": n.get("vram_mb"), "web_port": n.get("web_port")})
    return peers
