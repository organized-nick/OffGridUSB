"""Live swarm runtime for the exo P2P ring (F-33..F-36).

Bridges the pure-planner world of ``cluster_sim.py`` to real machines:
UDP LAN discovery, a versioned TCP swarm handshake, worker process
orchestration for llama.cpp ``--rpc`` backends, and cluster verification
that feeds live node inventory into ``ClusterCoordinator.plan_cluster()``.

100% Python Standard Library — runs on scavenged laptops, Raspberry Pis,
and macOS with zero pip dependencies.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .cluster_sim import ClusterCoordinator

SWARM_PROTO = "swarm/1"
DEFAULT_DISCOVERY_PORT = 50051
DEFAULT_RPC_PORT = 50052
DEFAULT_HANDSHAKE_TIMEOUT = 5.0
DEFAULT_DISCOVERY_WINDOW = 3.0
ANNOUNCE_INTERVAL_SEC = 1.0


class SwarmError(Exception):
    """Base class for swarm runtime failures."""


class SwarmHandshakeError(SwarmError):
    """A node failed the TCP swarm handshake (offline, wrong proto, timeout)."""


class SwarmWorkerError(SwarmError):
    """A llama.cpp RPC worker failed to start or open its port."""


def _json_line_send(sock: socket.socket, payload: Dict[str, Any]) -> None:
    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def _json_line_recv(sock: socket.socket, timeout: float) -> Dict[str, Any]:
    sock.settimeout(timeout)
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            raise SwarmHandshakeError("handshake reply exceeded 64KB")
    if not buf.strip():
        raise SwarmHandshakeError("connection closed before handshake reply")
    try:
        return json.loads(buf.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SwarmHandshakeError(f"malformed handshake reply: {exc}") from exc


_SUBNET_CACHE: List[str] = []
_SUBNET_CACHE_TS = 0.0
_SUBNET_CACHE_TTL = 30.0
_SUBNET_LOCK = threading.Lock()


def _linux_subnet_broadcasts() -> List[str]:
    out = subprocess.run(
        ["ip", "-o", "-4", "addr", "show"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    results: List[str] = []
    for line in out.splitlines():
        fields = line.split()
        # inet <ip>/<prefix> ...
        for i, f in enumerate(fields):
            if f == "inet" and i + 1 < len(fields):
                try:
                    iface = ipaddress.ip_interface(fields[i + 1])
                    bcast = iface.network.broadcast_address
                    if isinstance(bcast, ipaddress.IPv4Address) and str(bcast) != str(iface.ip):
                        results.append(str(bcast))
                except ValueError:
                    continue
    return results


def _windows_subnet_broadcasts() -> List[str]:
    out = subprocess.run(
        ["netsh", "interface", "ipv4", "show", "addresses"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    results: List[str] = []
    ip = prefix_len = None
    for line in out.splitlines():
        text = line.strip()
        if text.startswith("IP Address:"):
            ip = text.split(":", 1)[1].strip()
        elif text.startswith("Subnet Prefix:") and ip:
            raw = text.split(":", 1)[1].strip()  # e.g. 192.168.8.0/24 (masked 255.255.255.0)
            prefix_len = raw.rsplit("/", 1)[-1].split()[0]  # drop "(masked ...)" suffix
            try:
                iface = ipaddress.ip_interface(f"{ip}/{prefix_len}")
                bcast = iface.network.broadcast_address
                if isinstance(bcast, ipaddress.IPv4Address) and str(bcast) != str(iface.ip):
                    results.append(str(bcast))
            except ValueError:
                pass
            ip = prefix_len = None
    return results


def _local_subnet_broadcasts() -> List[str]:
    """Directed broadcast address of every connected IPv4 subnet (stdlib only).

    Loopback, link-local (169.254.x autoconfig) and /32-point-to-point
    networks are skipped. Returns [] when enumeration is impossible (exotic
    OS, parse failure) so callers fall back to the global broadcast target.
    """
    global _SUBNET_CACHE, _SUBNET_CACHE_TS
    with _SUBNET_LOCK:
        if time.time() - _SUBNET_CACHE_TS < _SUBNET_CACHE_TTL:
            return list(_SUBNET_CACHE)
    try:
        if os.name == "nt":
            found = _windows_subnet_broadcasts()
        else:
            found = _linux_subnet_broadcasts()
    except Exception:  # noqa: BLE001 — enumeration is best-effort only
        found = []
    # skip loopback and link-local (APIPA) networks — announcing there is
    # noise at best; the loopback announce copy is already handled separately
    found = [b for b in found if not b.startswith(("127.", "169.254."))]
    with _SUBNET_LOCK:
        _SUBNET_CACHE = found
        _SUBNET_CACHE_TS = time.time()
    return list(_SUBNET_CACHE)


def _linux_fib_trie_ips() -> set:
    """All local IPv4 addrs from /proc/net/fib_trie (linux only, stdlib).

    The UDP-connect trick returns ONE source per subnet, which misses the
    second interface on a multi-homed host with two NICs on the same subnet
    (e.g. wifi + usb-ethernet both on 192.168.8.0/24) — that un-listed
    address then announced back at us and survived the self-announce filter.
    """
    out: set = set()
    if os.name != "nt":
        try:
            with open("/proc/net/fib_trie") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if "/32 host LOCAL" in line:
                    # the address is the indented line right above
                    m = re.search(r"([0-9.]+)\s*$", lines[i - 1])
                    if m:
                        ip = m.group(1)
                        if not ip.startswith(("0.", "127.", "169.254.")):
                            out.add(ip)
        except (OSError, IndexError):
            pass
    return out


_LOCAL_IPS_CACHE: Optional[frozenset] = None
_LOCAL_IPS_LOCK = threading.Lock()


def local_ips() -> frozenset:
    """IPv4 addresses of this host (loopback + one per connected subnet).

    Stdlib only. Uses the UDP-connect trick per local subnet broadcast to find
    the source address each interface would use, plus gethostbyname(hostname).
    Used to recognize self-announces: a discovered node whose ip is one of ours
    is THIS machine — either the coordinator itself or a stale zombie instance
    from an earlier launch (pid-derived ids differ, so id-based dedupe can't
    catch them). Cached for the process lifetime.
    """
    global _LOCAL_IPS_CACHE
    with _LOCAL_IPS_LOCK:
        if _LOCAL_IPS_CACHE is not None:
            return _LOCAL_IPS_CACHE
    ips = {"127.0.0.1"}
    for bcast in _local_subnet_broadcasts():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # SO_BROADCAST is required before connect()ing to a directed
                # broadcast address on linux (EACCES otherwise — which used
                # to silently empty local_ips() on every linux host, making
                # is_self_announce never filter self-entries there)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(0.0)
                s.connect((bcast, 9))
                src = s.getsockname()[0]
                if src and not src.startswith(("0.", "127.", "169.254.")):
                    ips.add(src)
        except OSError:
            continue
    for extra in _linux_fib_trie_ips():
        ips.add(extra)
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip and not host_ip.startswith(("0.", "127.", "169.254.")):
            ips.add(host_ip)
    except OSError:
        pass
    result = frozenset(ips)
    with _LOCAL_IPS_LOCK:
        _LOCAL_IPS_CACHE = result
    return result


def is_self_announce(node: Dict[str, Any], local: frozenset, web_port: Optional[int] = None) -> bool:
    """True when a discovered announce originates from this machine.

    Loopback copies are always self. An entry whose observed ip is one of our
    local addresses is self too (same-host stale instances announce under a
    different pid-derived id, so id-based dedupe can't catch them).

    IMPORTANT: the observed ip alone decides. web_port is deliberately NOT a
    self-proof — every machine in the swarm runs the same app on the same
    default web port, so 'announce carries our web_port' is true for every
    genuine remote peer. Filtering on web_port made the discovered list
    empty everywhere (the 2026-11-03 discovery regression). web_port is kept
    in the signature for call-site compatibility only.
    """
    ip = str(node.get("ip") or "")
    if ip == "127.0.0.1" or ip == "::1":
        return True
    if ip in local:
        return True
    return False


class SwarmNode:
    """A single swarm node: UDP announcer + TCP handshake responder.

    Run one per machine (or several on loopback for testing):
        python -m emyrge.swarm node --port 50052 --rpc-port 50053 ...
    """

    def __init__(
        self,
        node_id: str,
        port: int,
        rpc_port: int = DEFAULT_RPC_PORT,
        ram_mb: int = 4096,
        vram_mb: int = 0,
        arch: str = "x86_64",
        web_port: Optional[int] = None,
        discovery_target: Tuple[str, int] = ("255.255.255.255", DEFAULT_DISCOVERY_PORT),
        announce_interval: float = ANNOUNCE_INTERVAL_SEC,
    ) -> None:
        self.node_id = node_id
        self.port = port
        self.rpc_port = rpc_port
        self.ram_mb = ram_mb
        self.vram_mb = vram_mb
        self.arch = arch
        self.web_port = web_port
        self.discovery_target = discovery_target
        self.announce_interval = announce_interval
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._udp_sock: Optional[socket.socket] = None
        self._tcp_sock: Optional[socket.socket] = None

    # -- info --------------------------------------------------------------

    def info(self) -> Dict[str, Any]:
        info = {
            "id": self.node_id,
            "name": self.node_id,
            "ip": "127.0.0.1",  # replaced by observed source IP on the coordinator side
            "port": self.port,
            "rpc_port": self.rpc_port,
            "ram_mb": self.ram_mb,
            "vram_mb": self.vram_mb,
            "arch": self.arch,
            "proto": SWARM_PROTO,
        }
        if self.web_port is not None:
            info["web_port"] = self.web_port
        return info

    # -- announce thread -----------------------------------------------------

    def _announce_targets(self) -> List[Tuple[str, int]]:
        targets = [self.discovery_target]
        # Directed subnet broadcasts: on multi-homed machines (VPN adapters
        # like tailscale next to the LAN NIC) the OS route choice for the
        # global 255.255.255.255 broadcast is unreliable and can egress the
        # wrong interface — killing LAN discovery asymmetrically (peers see
        # us, we don't see them). Sending to each local subnet's directed
        # broadcast (e.g. 192.168.8.255) ties the egress to the NIC owning
        # that connected route. Harmless extra traffic on other subnets.
        for bcast in _local_subnet_broadcasts():
            target = (bcast, self.discovery_target[1])
            if target not in targets:
                targets.append(target)
        # Broadcast packets are not looped back to local listeners on every OS,
        # so same-host nodes (and the web UI on this device) also get a direct
        # copy on loopback. Harmless duplication for real LAN peers.
        loopback = ("127.0.0.1", self.discovery_target[1])
        if loopback not in targets:
            targets.append(loopback)
        return targets

    def _announce_loop(self, stop_evt: threading.Event) -> None:
        payload = json.dumps({"type": "announce", **self.info()}).encode("utf-8")
        while not stop_evt.is_set():
            try:
                if self._udp_sock is None:
                    self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                for target in self._announce_targets():
                    try:
                        self._udp_sock.sendto(payload, target)
                    except OSError:
                        pass  # one bad target must not skip the rest
            except OSError:
                pass  # discovery target unreachable — node keeps serving TCP regardless
            stop_evt.wait(self.announce_interval)

    # -- tcp responder -------------------------------------------------------

    def _handle_connection(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        with conn:
            try:
                hello = _json_line_recv(conn, DEFAULT_HANDSHAKE_TIMEOUT)
                if hello.get("proto") != SWARM_PROTO:
                    _json_line_send(conn, {"error": f"unsupported proto: {hello.get('proto')}"})
                    return
                _json_line_send(conn, {"proto": SWARM_PROTO, "node": self.info()})
            except (SwarmHandshakeError, OSError):
                pass

    def _tcp_loop(self, stop_evt: threading.Event) -> None:
        assert self._tcp_sock is not None
        self._tcp_sock.listen(8)
        self._tcp_sock.settimeout(0.5)
        while not stop_evt.is_set():
            try:
                conn, addr = self._tcp_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True)
            t.start()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        # restart support: a previously stopped node has a set stop-event;
        # clear it or the threads below exit immediately (dead-but-bound node)
        self._stop.clear()
        stop_evt = self._stop
        threads = [
            threading.Thread(target=self._announce_loop, args=(stop_evt,), daemon=True),
            threading.Thread(target=self._tcp_loop, args=(stop_evt,), daemon=True),
        ]
        # bind on the calling thread so callers can connect immediately after start()
        self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_sock.bind(("0.0.0.0", self.port))
        self._threads = threads
        for t in threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        for sock in (self._tcp_sock, self._udp_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        # joining guarantees the listening fd is fully released before we return,
        # so an immediate re-bind of the same port can't hit EADDRINUSE
        for t in self._threads:
            t.join(timeout=2.0)

    def __enter__(self) -> "SwarmNode":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()


# Announced nodes that have not re-announced within this window are dropped
# from the discovery snapshot (nodes re-announce every ANNOUNCE_INTERVAL_SEC,
# so this is generous: a node that stopped broadcasting disappears quickly).
DEFAULT_DISCOVERY_MAX_AGE_SEC = 30.0
# If NO announce at all arrives within this window (nodes on the LAN usually
# re-announce every second), the listener socket is assumed to have lost its
# delivery slot (Windows quirk: a second SO_REUSEADDR binder on the port
# permanently steals delivery and the earlier socket never recovers) and is
# re-bound from scratch.
DEFAULT_DISCOVERY_REBIND_IDLE_SEC = 45.0


class CoordinatorDiscovery:
    """Listens for UDP swarm announces and tracks live nodes."""

    def __init__(
        self,
        discovery_port: int = DEFAULT_DISCOVERY_PORT,
        max_age_sec: float = DEFAULT_DISCOVERY_MAX_AGE_SEC,
        rebind_idle_sec: float = DEFAULT_DISCOVERY_REBIND_IDLE_SEC,
    ) -> None:
        self.max_age_sec = float(max_age_sec)
        self.rebind_idle_sec = float(rebind_idle_sec)
        self.discovery_port = discovery_port
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._disable_windows_connreset(self._sock)
        self._sock.bind(("0.0.0.0", discovery_port))
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)

    @staticmethod
    def _disable_windows_connreset(sock: socket.socket) -> None:
        """Windows quirk: any ICMP port-unreachable aimed at our UDP port
        (e.g. from announce broadcasts on networks with no listener, or
        another socket bound to the same port) poisons recvfrom on ALL
        sockets bound to that port with WSAECONNRESET — which used to kill
        this listener thread silently, leaving a bound-but-deaf socket.
        SIO_UDP_CONNRESET=0 stops Windows from raising on ICMP errors."""
        if sys.platform != "win32":
            return
        try:
            # python >=3.13 exposes socket.SIO_UDP_CONNRESET; older windows
            # pythons don't, so go through WSAIoctl directly. Either way a
            # failure must not break discovery setup — this is an enhancement.
            sock.ioctl(socket.SIO_UDP_CONNRESET, 0)
        except (AttributeError, OSError, ValueError):
            try:
                import ctypes
                dw = ctypes.c_uint(0)
                cb = ctypes.c_uint(0)
                ctypes.windll.ws2_32.WSAIoctl(
                    sock.fileno(), 0x9800000C,
                    ctypes.byref(dw), 4, None, 0, ctypes.byref(cb), None, None,
                )
            except Exception:
                pass  # listener hardening below still covers us

    def _listen_loop(self) -> None:
        reset_count = 0
        last_packet = time.time()
        while not self._stop.is_set():
            if time.time() - last_packet > self.rebind_idle_sec:
                # self-heal: no announces for a while despite nodes usually
                # re-announcing every second — either the network is truly
                # empty or our socket lost its delivery slot (Windows binds
                # a second SO_REUSEADDR binder and never hands the port
                # back). Re-bind from scratch to get a fresh slot.
                try:
                    self._sock.close()
                except OSError:
                    pass
                try:
                    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self._disable_windows_connreset(self._sock)
                    self._sock.bind(("0.0.0.0", self.discovery_port))
                    self._sock.settimeout(0.5)
                    last_packet = time.time()
                    reset_count = 0
                    print(
                        f"[swarm-discovery] listener re-bound on port {self.discovery_port} after {self.rebind_idle_sec:.0f}s silence",
                        file=sys.stderr,
                        flush=True,
                    )
                except OSError as exc:
                    print(
                        f"[swarm-discovery] re-bind failed (will retry): {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(1.0)
                    continue
            try:
                data, addr = self._sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError as exc:
                # never die on a socket error: WSAECONNRESET (Windows ICMP
                # poisoning) and friends are transient — keep listening
                reset_count += 1
                if reset_count <= 3 or reset_count % 100 == 0:
                    print(
                        f"[swarm-discovery] recv error (continuing): {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue
            last_packet = time.time()
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if msg.get("type") != "announce" or msg.get("proto") != SWARM_PROTO:
                continue
            node = dict(msg)
            node["ip"] = addr[0]  # announce origin is authoritative
            node["last_seen"] = time.time()
            with self._lock:
                existing = self.nodes.get(node["id"])
                if existing:
                    # loopback announces (same-host copies) arrive last; never
                    # let them overwrite a real LAN ip captured earlier
                    if not (node["ip"] in ("127.0.0.1", "::1") and existing["ip"] not in ("127.0.0.1", "::1")):
                        existing.update({k: v for k, v in node.items() if k != "last_seen"})
                    existing["last_seen"] = node["last_seen"]
                else:
                    self.nodes[node["id"]] = node

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.time()
            stale = [
                nid
                for nid, n in self.nodes.items()
                if not isinstance(n.get("last_seen"), (int, float))
                or now - n["last_seen"] > self.max_age_sec
            ]
            for nid in stale:
                del self.nodes[nid]
            return [dict(n) for n in self.nodes.values()]


def handshake_node(ip: str, port: int, timeout: float = DEFAULT_HANDSHAKE_TIMEOUT) -> Dict[str, Any]:
    """Perform the TCP swarm handshake with a node; return its inventory dict.

    Raises SwarmHandshakeError on any failure (refused, timeout, bad proto).
    """
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
    except OSError as exc:
        raise SwarmHandshakeError(f"{ip}:{port} connect failed: {exc}") from exc
    with sock:
        try:
            _json_line_send(sock, {"proto": SWARM_PROTO, "role": "coordinator"})
            reply = _json_line_recv(sock, timeout)
        except OSError as exc:
            raise SwarmHandshakeError(f"{ip}:{port} io error: {exc}") from exc
    if reply.get("proto") != SWARM_PROTO or "node" not in reply:
        raise SwarmHandshakeError(f"{ip}:{port} bad handshake reply: {reply.get('error', reply)}")
    node = dict(reply["node"])
    node["ip"] = ip
    return node


class RpcWorkerLauncher:
    """Launches llama.cpp ``llama-rpc-server`` workers for cluster backends.

    Accepts a custom ``worker_cmd`` (defaults to ``llama-rpc-server`` on PATH)
    so the harness can substitute a stub binary for loopback testing.
    """

    def __init__(
        self,
        worker_cmd: Optional[str] = None,
        readiness_probe: Optional[Callable[[int, float], bool]] = None,
        startup_timeout: float = 10.0,
    ) -> None:
        self.worker_cmd = worker_cmd or shutil.which("llama-rpc-server") or "llama-rpc-server"
        self.readiness_probe = readiness_probe or self._port_open_probe
        self.startup_timeout = startup_timeout
        self.procs: List[subprocess.Popen] = []

    @staticmethod
    def _port_open_probe(port: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.1)
        return False

    def launch(self, port: int, extra_args: Optional[List[str]] = None) -> subprocess.Popen:
        args = [self.worker_cmd, "--host", "127.0.0.1", "--port", str(port)]
        if extra_args:
            args += extra_args
        try:
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise SwarmWorkerError(f"failed to spawn worker on port {port}: {exc}") from exc
        self.procs.append(proc)
        if not self.readiness_probe(port, self.startup_timeout):
            self.terminate()
            raise SwarmWorkerError(f"worker on port {port} never opened its port")
        return proc

    def terminate(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        proc.kill()
                    except OSError:
                        pass
        self.procs = []


class CoordinatorRuntime:
    """Forms a live cluster: discover (or seed) → handshake → plan → verify."""

    def __init__(
        self,
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT,
        worker_launcher: Optional[RpcWorkerLauncher] = None,
        launch_workers: bool = False,
    ) -> None:
        self.handshake_timeout = handshake_timeout
        self.launch_workers = launch_workers
        self.worker_launcher = worker_launcher or RpcWorkerLauncher()
        self.launcher_owned = worker_launcher is None

    def form_cluster(
        self,
        seeds: Optional[List[Dict[str, Any]]] = None,
        discovered: Optional[List[Dict[str, Any]]] = None,
        simulate_drop: bool = False,
    ) -> Dict[str, Any]:
        """Handshake each seed/discovered node, keep survivors, plan the cluster.

        ``seeds`` are ip/port specs; ``discovered`` are announce dicts from
        CoordinatorDiscovery. Returns the planner plan plus live verification
        fields (handshakes, workers, verified_at).
        """
        candidates: List[Dict[str, Any]] = []
        for s in seeds or []:
            candidates.append({"ip": s["ip"], "port": int(s.get("port", DEFAULT_RPC_PORT))})
        for d in discovered or []:
            candidates.append({"ip": d["ip"], "port": int(d.get("port", DEFAULT_RPC_PORT))})

        verified: List[Dict[str, Any]] = []
        handshake_results: List[Dict[str, Any]] = []
        for c in candidates:
            try:
                node = handshake_node(c["ip"], c["port"], timeout=self.handshake_timeout)
                verified.append(node)
                handshake_results.append({
                    "ip": c["ip"], "port": c["port"], "ok": True, "id": node.get("id"),
                    "ram_mb": node.get("ram_mb"), "vram_mb": node.get("vram_mb"),
                    "web_port": node.get("web_port"),
                })
            except SwarmHandshakeError as exc:
                handshake_results.append({"ip": c["ip"], "port": c["port"], "ok": False, "error": str(exc)})

        workers: List[Dict[str, Any]] = []
        if self.launch_workers and verified:
            for node in verified:
                try:
                    self.worker_launcher.launch(node.get("rpc_port", DEFAULT_RPC_PORT))
                    workers.append({"node_id": node["id"], "rpc_port": node.get("rpc_port"), "ok": True})
                except SwarmWorkerError as exc:
                    workers.append({"node_id": node.get("id"), "ok": False, "error": str(exc)})

        plan = ClusterCoordinator.plan_cluster(verified, simulate_drop=simulate_drop)
        plan["live"] = {
            "handshakes": handshake_results,
            "verified_nodes": [n["id"] for n in verified],
            "workers": workers,
            "verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cluster_formed": len(verified) >= 1,
        }
        return plan

    def shutdown(self) -> None:
        if self.launcher_owned:
            self.worker_launcher.terminate()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m emyrge.swarm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_node = sub.add_parser("node", help="run a swarm node (announcer + handshake responder)")
    p_node.add_argument("--id", default=f"node-{os.getpid()}")
    p_node.add_argument("--port", type=int, default=DEFAULT_RPC_PORT)
    p_node.add_argument("--rpc-port", type=int, default=DEFAULT_RPC_PORT + 1)
    p_node.add_argument("--ram-mb", type=int, default=4096)
    p_node.add_argument("--vram-mb", type=int, default=0)
    p_node.add_argument("--arch", default="x86_64")
    p_node.add_argument("--web-port", type=int, default=None, help="web app port to advertise")
    p_node.add_argument("--discovery-target", default="255.255.255.255:50051")

    p_coord = sub.add_parser("coordinate", help="discover nodes and form a cluster")
    p_coord.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    p_coord.add_argument("--window", type=float, default=DEFAULT_DISCOVERY_WINDOW)
    p_coord.add_argument("--seed", action="append", default=[], help="ip:port of a node to handshake directly")
    p_coord.add_argument("--simulate-drop", action="store_true")
    p_coord.add_argument("--json", action="store_true", help="machine-readable output only")

    args = parser.parse_args(argv)

    if args.cmd == "node":
        target = args.discovery_target.split(":")
        node = SwarmNode(
            node_id=args.id,
            port=args.port,
            rpc_port=args.rpc_port,
            ram_mb=args.ram_mb,
            vram_mb=args.vram_mb,
            arch=args.arch,
            web_port=args.web_port,
            discovery_target=(target[0], int(target[1]) if len(target) > 1 else DEFAULT_DISCOVERY_PORT),
        )
        node.start()
        print(f"swarm node {args.id} listening on 0.0.0.0:{args.port}", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            node.stop()
        return 0

    # coordinate
    seeds = []
    for s in args.seed:
        ip, _, port = s.partition(":")
        seeds.append({"ip": ip, "port": int(port) if port else DEFAULT_RPC_PORT})
    discovery = None
    if not seeds:
        discovery = CoordinatorDiscovery(discovery_port=args.discovery_port)
        discovery.start()
        time.sleep(args.window)
        discovered = discovery.snapshot()
        discovery.stop()
    else:
        discovered = []

    runtime = CoordinatorRuntime()
    plan = runtime.form_cluster(seeds=seeds, discovered=discovered, simulate_drop=args.simulate_drop)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        live = plan["live"]
        print(f"cluster formed: {len(live['verified_nodes'])} node(s) verified")
        print(f"unlocked: tier {plan['unlocked_tier']} — {plan['unlocked_model']}")
        print(f"rpc command: {plan['rpc_command']}")
        for h in live["handshakes"]:
            status = "OK" if h["ok"] else f"FAIL ({h['error']})"
            print(f"  {h['ip']}:{h['port']} -> {status}")
    return 0 if plan["live"]["cluster_formed"] else 1




def detect_local_hardware() -> Dict[str, Any]:
    """Best-effort detection of this machine's real RAM/VRAM/arch (no deps).

    Used by the web app so "Start Node" can advertise truthful inventory
    instead of the 4096 MB placeholder. Cross-platform, stdlib only.
    """
    ram_mb = 0
    vram_mb = 0
    arch = "unknown"
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[int](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            ram_mb = int(float(out)) if out else 0
        else:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        ram_mb = int(line.split()[1]) // 1024
                        break
    except Exception:
        ram_mb = ram_mb or 0
    try:
        nvidia = shutil.which("nvidia-smi")
        if nvidia:
            out = subprocess.run(
                [nvidia, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if out:
                vram_mb = sum(int(x) for x in out.splitlines() if x.strip().isdigit())
    except Exception:
        vram_mb = 0
    try:
        import platform
        arch = platform.machine() or "unknown"
    except Exception:
        pass
    return {"ram_mb": ram_mb, "vram_mb": vram_mb, "arch": arch}


if __name__ == "__main__":
    raise SystemExit(main())

