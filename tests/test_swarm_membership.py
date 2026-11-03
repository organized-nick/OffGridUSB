"""Cluster-membership announcements: peers' UIs reflect that they joined a swarm.

Covers:
- POST /api/swarm/cluster/announce records membership (task 7),
- membership expires after MEMBERSHIP_TTL_SEC,
- swarm_status reports state "member" for a peer with no local cluster,
- the watchdog's on_cycle hook fires with alive peers each probe cycle,
- the HTTP endpoint accepts the coordinator's announce payload.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestSwarmMembership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from emyrge.core.config import EmyrgeConfig
        from emyrge.server import create_server as _create_server
        cls.config = EmyrgeConfig.from_env(project_root=REPO_ROOT)
        cls.config.port = _free_port()
        cls.config.headless = True
        cls.server, cls.runtime = _create_server(cls.config)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post_announce(self, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.config.port}/api/swarm/cluster/announce",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def test_01_announce_records_membership_and_member_state(self):
        res = self._post_announce({
            "coordinator": "offgrid-111", "coordinator_web_port": 8000,
            "peers": [{"id": "a", "ip": "192.168.8.10", "port": 50052}],
        })
        self.assertTrue(res["ok"])
        status = self.runtime.swarm_status()
        self.assertEqual(status["membership"]["coordinator"], "offgrid-111")
        self.assertEqual(status["cluster_state"], "member")
        self.assertEqual(len(status["membership"]["peers"]), 1)

    def test_02_membership_expires_after_ttl(self):
        from emyrge.web.app import MEMBERSHIP_TTL_SEC
        self.runtime.swarm_cluster_announce({"coordinator": "offgrid-1", "peers": []})
        with self.runtime._lock:
            self.runtime.swarm_membership["updated_at"] = time.time() - (MEMBERSHIP_TTL_SEC + 5)
        status = self.runtime.swarm_status()
        self.assertIsNone(status["membership"])
        self.assertEqual(status["cluster_state"], "idle")

    def test_03_watchdog_on_cycle_receives_alive_peers(self):
        from emyrge.swarm.watchdog import SwarmWatchdog
        seen = []
        wd = SwarmWatchdog(
            peers=[{"id": "ghost", "ip": "127.0.0.1", "port": 1, "web_port": 1}],
            interval=0.05,
            probe_timeout=0.1,
            on_cycle=lambda alive: seen.append(list(alive)),
        )
        wd.probe_once()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], [])  # nothing alive on port 1

    def test_04_reannounce_refreshes_not_duplicates(self):
        self.runtime.swarm_cluster_announce({"coordinator": "offgrid-2", "peers": []})
        first_ts = self.runtime.swarm_status()["membership"]["updated_at"]
        time.sleep(0.01)
        self._post_announce({"coordinator": "offgrid-2", "peers": []})
        second = self.runtime.swarm_status()["membership"]
        self.assertGreaterEqual(second["updated_at"], first_ts)
        self.assertEqual(second["coordinator"], "offgrid-2")


if __name__ == "__main__":
    unittest.main()
