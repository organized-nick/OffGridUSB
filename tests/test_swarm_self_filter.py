"""Tests for swarm self-announce filtering (duplicate node entries fix).

The bug: the swarm web UI showed the local machine twice — once as the live
"this device" node and once as a "discovered" peer. Two sources feed that
duplicate:

1. loopback announce copies (the node sends a direct copy to 127.0.0.1 so
   the same-host UI sees itself — those packets have source ip 127.0.0.1),
2. stale same-host app instances (from an earlier launch) announcing under a
   different pid-derived id — id-based dedupe can't catch them, but their
   observed source ip IS one of ours.

The fix (runtime.local_ips + is_self_announce, wired into app.py):
self-announces are dropped from swarm_status/swarm_live_nodes/swarm_scan so
each machine appears exactly once.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from emyrge.swarm.runtime import is_self_announce, local_ips

# synthetic local-ip set so tests don't depend on the host's real interfaces
LOCAL = frozenset({"192.168.8.157", "10.0.0.5"})


class TestLocalIps(unittest.TestCase):
    def test_contains_loopback(self):
        ips = local_ips()
        self.assertIn("127.0.0.1", ips)
        self.assertTrue(len(ips) >= 1)

    def test_cached_and_immutable(self):
        first = local_ips()
        second = local_ips()
        self.assertIs(first, second)  # cached frozenset, not rebuilt per call
        with self.assertRaises(AttributeError):
            first.add("1.2.3.4")  # type: ignore[attr-defined]


class TestIsSelfAnnounce(unittest.TestCase):
    def test_loopback_is_always_self(self):
        self.assertTrue(is_self_announce({"ip": "127.0.0.1"}, LOCAL))
        self.assertTrue(is_self_announce({"ip": "::1"}, LOCAL))

    def test_local_membership_is_self(self):
        self.assertTrue(is_self_announce({"ip": "192.168.8.157"}, LOCAL))
        self.assertTrue(is_self_announce({"ip": "10.0.0.5"}, LOCAL))

    def test_remote_ip_is_not_self(self):
        self.assertFalse(is_self_announce({"ip": "192.168.8.99"}, LOCAL))
        self.assertFalse(is_self_announce({"ip": ""}, LOCAL))

    def test_matching_web_port_is_self_even_with_foreign_ip(self):
        # same-app origin proof: an announce carrying OUR web app port
        self.assertTrue(
            is_self_announce({"ip": "192.168.8.99", "web_port": 8010}, LOCAL, web_port=8010)
        )

    def test_mismatched_web_port_is_not_self(self):
        self.assertFalse(
            is_self_announce({"ip": "192.168.8.99", "web_port": 9999}, LOCAL, web_port=8010)
        )

    def test_web_port_check_skipped_when_no_port_given(self):
        self.assertFalse(is_self_announce({"ip": "192.168.8.99", "web_port": 8010}, LOCAL))

    def test_garbage_web_port_falls_through_to_ip_logic(self):
        self.assertTrue(is_self_announce({"ip": "10.0.0.5", "web_port": "NaN"}, LOCAL, web_port=8010))


if __name__ == "__main__":
    unittest.main()
