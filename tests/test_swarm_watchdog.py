"""Tests for the swarm watchdog + discovery liveness + hardware detection."""

import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, "src")

from emyrge.swarm import runtime as rt
from emyrge.swarm import watchdog as wdmod
from emyrge.swarm.watchdog import SwarmWatchdog, peers_from_verified


class _FakeCoordinator:
    """Stands in for CoordinatorRuntime.form_cluster in watchdog re-forms."""

    def __init__(self):
        self.calls = []

    def form_cluster(self, seeds=None, discovered=None, **_):
        self.calls.append([s["ip"] for s in (seeds or [])])
        # pretend all seeds verify and the cluster reforms
        verified = [{"id": f"n-{s['ip']}", "ip": s["ip"], "port": s["port"]} for s in (seeds or [])]
        return {
            "live": {"cluster_formed": bool(verified), "verified_nodes": [v["id"] for v in verified]},
            "unlocked_tier": 2,
        }


class TestSwarmWatchdog(unittest.TestCase):
    def _mk(self, peers, coordinator, events, interval=0.2):
        wd = SwarmWatchdog(
            peers=peers,
            interval=interval,
            probe_timeout=0.3,
            reform=lambda alive: coordinator.form_cluster(seeds=alive),
            on_event=lambda kind, msg: events.append((kind, msg)),
        )
        return wd

    def test_reforms_on_drop_and_keeps_returning_peer_tracked(self):
        events = []
        coord = _FakeCoordinator()
        peers = [
            {"id": "a", "ip": "10.0.0.1", "port": 50052},
            {"id": "b", "ip": "10.0.0.2", "port": 50052},
        ]
        wd = self._mk(peers, coord, events, interval=0.1)

        # deterministic phases keyed on per-node call counts:
        # round 1: both alive; rounds 2-4: a dead; rounds 5+: a returns
        counts = {"a": 0, "b": 0}

        def fake_handshake(ip, port, timeout=None):
            nid = "a" if ip == "10.0.0.1" else "b"
            counts[nid] += 1
            if nid == "a" and 2 <= counts["a"] <= 4:
                raise rt.SwarmHandshakeError(f"{ip}:{port} connect failed: refused")
            return {"id": nid, "ip": ip, "port": port}

        with patch.object(wdmod, "handshake_node", side_effect=fake_handshake):
            wd.start()
            deadline = time.time() + 6
            kinds = [k for k, _ in events]
            while time.time() < deadline and not ("peer_returned" in kinds and "peer_dropped" in kinds):
                time.sleep(0.1)
                kinds = [k for k, _ in events]
            wd.stop()
            wd._thread.join(timeout=3)

        kinds = [k for k, _ in events]
        self.assertIn("peer_dropped", kinds)
        self.assertIn("peer_returned", kinds)
        self.assertIn("cluster_reformed", kinds)
        self.assertTrue(any(c == ["10.0.0.2"] for c in coord.calls))

    def test_stops_when_all_peers_lost(self):
        events = []
        coord = _FakeCoordinator()
        wd = self._mk([{"id": "a", "ip": "10.0.0.1", "port": 50052}], coord, events)

        with patch.object(wdmod, "handshake_node", side_effect=rt.SwarmHandshakeError("dead")):
            wd.start()
            deadline = time.time() + 3
            while time.time() < deadline and not (events and events[-1][0] == "cluster_lost"):
                time.sleep(0.1)
            wd.stop()

        kinds = [k for k, _ in events]
        self.assertIn("cluster_lost", kinds)
        self.assertFalse(coord.calls, "must not re-form when everything is gone")

    def test_health_cache_updates(self):
        wd = SwarmWatchdog(peers=[{"id": "a", "ip": "10.0.0.1", "port": 50052}])
        with patch.object(wdmod, "handshake_node", return_value={"id": "a", "ip": "10.0.0.1", "port": 50052}):
            wd.probe_once()
        self.assertTrue(wd.health["all_ok"])
        self.assertEqual(wd.health["nodes"][0]["ok"], True)

    def test_peers_from_verified(self):
        peers = peers_from_verified([{"id": "x", "ip": "1.2.3.4", "port": 50052, "ram_mb": 8000, "vram_mb": 100}])
        self.assertEqual(peers, [{"id": "x", "ip": "1.2.3.4", "port": 50052, "ram_mb": 8000, "vram_mb": 100, "web_port": None}])


class TestDiscoveryLastSeen(unittest.TestCase):
    def test_announce_sets_and_refreshes_last_seen(self):
        import json as _json
        import socket as _socket
        d = rt.CoordinatorDiscovery(discovery_port=0)
        d.start()
        try:
            port = d._sock.getsockname()[1]
            send = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            msg = {"type": "announce", "proto": rt.SWARM_PROTO, "id": "n1", "port": 50052}

            def announce():
                send.sendto(_json.dumps(msg).encode("utf-8"), ("127.0.0.1", port))

            announce()
            deadline = time.time() + 2
            while time.time() < deadline and not d.snapshot():
                time.sleep(0.05)
            first = d.snapshot()
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["ip"], "127.0.0.1")
            self.assertIn("last_seen", first[0])
            ts1 = first[0]["last_seen"]

            time.sleep(0.3)
            announce()
            deadline = time.time() + 2
            ts2 = ts1
            while time.time() < deadline:
                snap = d.snapshot()
                if snap and snap[0]["last_seen"] > ts1:
                    ts2 = snap[0]["last_seen"]
                    break
                time.sleep(0.05)
            self.assertGreater(ts2, ts1)
            self.assertEqual(len(d.snapshot()), 1, "repeat announce must not duplicate the node")
        finally:
            d.stop()


class TestDetectLocalHardware(unittest.TestCase):
    def test_detect_returns_sane_shape(self):
        hw = rt.detect_local_hardware()
        self.assertIn("ram_mb", hw)
        self.assertIn("vram_mb", hw)
        self.assertIn("arch", hw)
        self.assertIsInstance(hw["ram_mb"], int)


if __name__ == "__main__":
    unittest.main()
