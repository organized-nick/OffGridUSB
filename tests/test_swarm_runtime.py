"""Live swarm runtime tests: discovery, TCP handshake, cluster formation.

Everything runs on loopback with in-process SwarmNode servers (plus one
subprocess e2e for the CLI entrypoints) — no real llama.cpp binaries needed.
"""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


def _free_port():
    """Reserve an ephemeral port so repeated/aborted runs never collide."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from emyrge.swarm import runtime as rt
from emyrge.swarm.cluster_sim import DEFAULT_SWARM_NODES
from emyrge.swarm.runtime import (
    CoordinatorDiscovery,
    CoordinatorRuntime,
    SwarmHandshakeError,
    SwarmNode,
    handshake_node,
)


def start_node(node_id, port, **kwargs):
    node = SwarmNode(node_id=node_id, port=port, **kwargs)
    node.start()
    # wait until the TCP listener accepts
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return node
        except OSError:
            time.sleep(0.05)
    node.stop()
    raise RuntimeError(f"node {node_id} never bound port {port}")


class TestHandshake(unittest.TestCase):
    def setUp(self):
        self.nodes = [start_node("n1", 50060, ram_mb=8192, rpc_port=50061)]

    def tearDown(self):
        for n in self.nodes:
            n.stop()

    def test_handshake_returns_node_inventory(self):
        node = handshake_node("127.0.0.1", 50060)
        self.assertEqual(node["id"], "n1")
        self.assertEqual(node["ram_mb"], 8192)
        self.assertEqual(node["rpc_port"], 50061)
        self.assertEqual(node["proto"], "swarm/1")

    def test_handshake_wrong_port_raises(self):
        with self.assertRaises(SwarmHandshakeError):
            handshake_node("127.0.0.1", 59999, timeout=1.0)

    def test_handshake_non_json_service_raises(self):
        garbage = socket.socket()
        garbage.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        garbage.bind(("127.0.0.1", 50062))
        garbage.listen(1)
        try:
            def junk():
                conn, _ = garbage.accept()
                conn.sendall(b"HELLO THERE\n")
                conn.close()
            import threading
            t = threading.Thread(target=junk, daemon=True)
            t.start()
            with self.assertRaises(SwarmHandshakeError):
                handshake_node("127.0.0.1", 50062, timeout=2.0)
        finally:
            garbage.close()


class TestDiscovery(unittest.TestCase):
    def test_udp_announce_is_discovered(self):
        node = SwarmNode(
            node_id="disc-1", port=50070, rpc_port=50071,
            discovery_target=("127.0.0.1", 50080), announce_interval=0.1,
        )
        node.start()
        disc = CoordinatorDiscovery(discovery_port=50080)
        disc.start()
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not disc.snapshot():
                time.sleep(0.05)
            snap = disc.snapshot()
            self.assertEqual(len(snap), 1)
            self.assertEqual(snap[0]["id"], "disc-1")
            self.assertEqual(snap[0]["ram_mb"], 4096)
        finally:
            disc.stop()
            node.stop()

    def test_non_swarm_datagram_ignored(self):
        disc = CoordinatorDiscovery(discovery_port=50081)
        disc.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(b"not json", ("127.0.0.1", 50081))
            time.sleep(0.3)
            self.assertEqual(disc.snapshot(), [])
        finally:
            disc.stop()

    def test_stale_announce_is_pruned(self):
        # a node that stops re-announcing disappears from the snapshot after
        # max_age_sec — the UI "discovered" list must not keep dead entries
        disc = CoordinatorDiscovery(discovery_port=50082, max_age_sec=0.5)
        disc.start()
        try:
            with disc._lock:
                disc.nodes["ghost"] = {"id": "ghost", "ip": "127.0.0.1", "port": 50099, "last_seen": time.time()}
                disc.nodes["fresh"] = {"id": "fresh", "ip": "127.0.0.1", "port": 50098, "last_seen": time.time()}
            self.assertEqual({d["id"] for d in disc.snapshot()}, {"fresh", "ghost"})
            # age past the window, no re-announce → gone
            with disc._lock:
                disc.nodes["fresh"]["last_seen"] = time.time() - 10.0
                disc.nodes["ghost"]["last_seen"] = time.time() - 10.0
            self.assertEqual(disc.snapshot(), [])
        finally:
            disc.stop()

    def test_listener_survives_poisoned_recv(self):
        # Windows WSAECONNRESET: an ICMP error aimed at the discovery port
        # makes recvfrom raise OSError — the listener thread must keep
        # running and recover, not break out and leave a deaf-but-bound socket
        disc = CoordinatorDiscovery(discovery_port=50083)
        disc.start()
        target_sock = disc._sock
        real_recvfrom = socket.socket.recvfrom
        calls = {"n": 0}

        def poisoned_recvfrom(self, *a, **kw):
            if self is target_sock:
                calls["n"] += 1
                if calls["n"] <= 2:
                    raise OSError(10054, "Connection reset")
            return real_recvfrom(self, *a, **kw)

        node = SwarmNode(
            node_id="poison-test", port=50084, rpc_port=50085,
            discovery_target=("127.0.0.1", 50083), announce_interval=0.05,
        )
        node.start()
        try:
            with patch.object(socket.socket, "recvfrom", poisoned_recvfrom):
                # drive a few loop iterations past the poison window
                deadline = time.time() + 6
                while time.time() < deadline:
                    snap = disc.snapshot()
                    if any(d["id"] == "poison-test" for d in snap):
                        break
                    time.sleep(0.05)
            self.assertTrue(
                any(d["id"] == "poison-test" for d in disc.snapshot()),
                "listener thread died on poisoned recvfrom — announce never recovered",
            )
        finally:
            disc.stop()
            node.stop()


class TestClusterFormation(unittest.TestCase):
    def setUp(self):
        self.nodes = [
            start_node("coord-a", 50090, ram_mb=16384, vram_mb=0, rpc_port=50091),
            start_node("coord-b", 50092, ram_mb=32768, vram_mb=0, rpc_port=50093),
        ]

    def tearDown(self):
        for n in self.nodes:
            n.stop()

    def test_form_cluster_via_seeds(self):
        runtime = CoordinatorRuntime()
        plan = runtime.form_cluster(
            seeds=[{"ip": "127.0.0.1", "port": 50090}, {"ip": "127.0.0.1", "port": 50092}]
        )
        self.assertTrue(plan["live"]["cluster_formed"])
        self.assertEqual(plan["live"]["verified_nodes"], ["coord-a", "coord-b"])
        self.assertEqual(len(plan["layer_split"]), 2)
        # live plan reflects actual discovered memory, not the fixture
        self.assertEqual(plan["pooled_ram_mb"], 16384 + 32768)

    def test_form_cluster_tier_from_live_memory(self):
        runtime = CoordinatorRuntime()
        plan = runtime.form_cluster(seeds=[{"ip": "127.0.0.1", "port": 50090}])
        self.assertEqual(plan["unlocked_tier"], 3)  # 16gb pooled
        self.assertEqual(len(plan["layer_split"]), 1)

    def test_dead_node_is_reported_but_does_not_crash(self):
        runtime = CoordinatorRuntime()
        plan = runtime.form_cluster(
            seeds=[{"ip": "127.0.0.1", "port": 50090}, {"ip": "127.0.0.1", "port": 59999}]
        )
        self.assertEqual(plan["live"]["verified_nodes"], ["coord-a"])
        failed = [h for h in plan["live"]["handshakes"] if not h["ok"]]
        self.assertEqual(len(failed), 1)
        self.assertIn("connect failed", failed[0]["error"])

    def test_all_dead_nodes_mean_cluster_not_formed(self):
        runtime = CoordinatorRuntime()
        plan = runtime.form_cluster(seeds=[{"ip": "127.0.0.1", "port": 59999}])
        self.assertFalse(plan["live"]["cluster_formed"])
        self.assertEqual(plan["unlocked_tier"], 0)

    def test_form_cluster_from_discovered(self):
        """Full discovery path: node announces via UDP, coordinator forms from snapshot."""
        disc = CoordinatorDiscovery(discovery_port=50097)
        disc.start()
        announcer = SwarmNode(
            node_id="disc-coord", port=50094, rpc_port=50096,
            discovery_target=("127.0.0.1", 50097), announce_interval=0.1,
        )
        announcer.start()
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not disc.snapshot():
                time.sleep(0.05)
            runtime = CoordinatorRuntime()
            plan = runtime.form_cluster(discovered=disc.snapshot())
            self.assertTrue(plan["live"]["cluster_formed"])
            self.assertIn("disc-coord", plan["live"]["verified_nodes"])
        finally:
            disc.stop()
            announcer.stop()

    def test_plan_matches_static_fixture_shapes(self):
        runtime = CoordinatorRuntime()
        plan = runtime.form_cluster(
            seeds=[{"ip": "127.0.0.1", "port": 50090}, {"ip": "127.0.0.1", "port": 50092}]
        )
        # same invariants as the pure planner: contiguous layers, split sums to total
        total = plan["exo_config"]["total_layers"]
        self.assertEqual(sum(s["layers"] for s in plan["layer_split"]), total)
        self.assertIn("--rpc", plan["rpc_command"])
        self.assertIn("tensor-split", plan["rpc_command"])


class TestCliEndToEnd(unittest.TestCase):
    """Real subprocess e2e: swarm-node CLI + coordinator CLI on loopback."""

    def test_node_and_coordinate_cli(self):
        node_port, rpc_port, disc_port = _free_port(), _free_port(), _free_port()
        env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "src"))
        node_proc = subprocess.Popen(
            [sys.executable, "-m", "emyrge.swarm", "node", "--id", "cli-node", "--port", str(node_port),
             "--rpc-port", str(rpc_port), "--discovery-target", f"127.0.0.1:{disc_port}", "--ram-mb", "8192"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", node_port), timeout=0.5):
                        break
                except OSError:
                    if node_proc.poll() is not None:
                        out = node_proc.stdout.read().decode()
                        self.fail(f"node CLI died early: {out}")
                    time.sleep(0.1)
            coord = subprocess.run(
                [sys.executable, "-m", "emyrge.swarm", "coordinate", "--seed", f"127.0.0.1:{node_port}", "--json"],
                env=env, capture_output=True, timeout=30,
            )
            self.assertEqual(coord.returncode, 0, coord.stderr.decode())
            plan = json.loads(coord.stdout)
            self.assertEqual(plan["live"]["verified_nodes"], ["cli-node"])
            self.assertEqual(plan["unlocked_tier"], 2)  # 8192 pooled
        finally:
            node_proc.terminate()
            node_proc.wait(timeout=5)

    def test_coordinate_with_no_nodes_exits_nonzero(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "src"))
        coord = subprocess.run(
            [sys.executable, "-m", "emyrge.swarm", "coordinate", "--seed", "127.0.0.1:59999", "--json"],
            env=env, capture_output=True, timeout=30,
        )
        self.assertEqual(coord.returncode, 1)
        plan = json.loads(coord.stdout)
        self.assertFalse(plan["live"]["cluster_formed"])


if __name__ == "__main__":
    unittest.main()


class _FakeCompleted:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0
        self.stderr = ""


class TestDirectedSubnetBroadcasts(unittest.TestCase):
    """LAN discovery must survive multi-homed hosts (VPN next to LAN NIC)."""

    def setUp(self):
        rt._SUBNET_CACHE = []
        rt._SUBNET_CACHE_TS = 0.0

    def tearDown(self):
        rt._SUBNET_CACHE = []
        rt._SUBNET_CACHE_TS = 0.0

    def test_windows_parse_pairs_ip_with_prefix(self):
        fake = """Configuration for interface "Ethernet" (connected)
   DHCP enabled:                         Yes
   IP Address:                           192.168.8.143
   Subnet Prefix:                        192.168.8.0/24 (masked 255.255.255.0)
Configuration for interface "Tailscale" (connected)
   IP Address:                           100.79.208.5
   Subnet Prefix:                        100.79.208.5/32 (masked 255.255.255.255)
"""
        with patch.object(rt.subprocess, "run", return_value=_FakeCompleted(fake)):
            found = rt._windows_subnet_broadcasts()
        self.assertEqual(found, ["192.168.8.255"])  # /32 tailnet entry filtered

    def test_linux_parse_dedupes_and_skips_point_to_point(self):
        fake = (
            "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n"
            "2: ens3    inet 192.168.8.20/24 scope global dynamic ens3\\       valid_lft\n"
            "3: tailscale0    inet 100.93.79.19/32 scope global tailscale0\\       valid_lft\n"
        )
        with patch.object(rt.subprocess, "run", return_value=_FakeCompleted(fake)):
            found = rt._local_subnet_broadcasts()  # wrapper: skips loopback + /32
        self.assertEqual(found, ["192.168.8.255"])

    def test_announce_targets_include_local_subnet_broadcast(self):
        with patch.object(rt, "_local_subnet_broadcasts", return_value=["192.168.8.255"]):
            node = rt.SwarmNode(node_id="t", port=50052)
            targets = node._announce_targets()
        self.assertIn(("192.168.8.255", 50051), targets)
        self.assertIn(("255.255.255.255", 50051), targets)
        self.assertIn(("127.0.0.1", 50051), targets)

    def test_cache_prevents_repeated_enumeration(self):
        calls = {"n": 0}

        def boom(_args, **_kw):
            calls["n"] += 1
            raise AssertionError("enumeration should be cached")

        with patch.object(rt, "_linux_subnet_broadcasts", boom):
            node = rt.SwarmNode(node_id="t", port=50052)
            node._announce_targets()
            node._announce_targets()
        # both calls served from the 30s cache — enumeration ran at most once
        self.assertLessEqual(calls["n"], 1)
