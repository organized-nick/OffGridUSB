"""Adversarial Verification Test Suite for Milestone 4: API Validation & Calculators.

Authored by teamwork_preview_challenger (challenger_m4_1).
Adversarial empirical challenge of:
- ADV-1: Volume edge cases (0.0, -1.0, -100.0, 0.0 gallons, negative gallons) strictly raising ValueError / HTTP 400.
- ADV-2: Concentration edge cases (0.0%, -5.0%, 16.0%, 50.0%) strictly raising ValueError / HTTP 400.
- ADV-3: Route aliases (/api/calculator/water_purification and /api/calc) mapping and error handling parity.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request

# Ensure src/ and repo root are in sys.path
current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parent.parent
src_dir = repo_root / "src"
for p in (str(src_dir), str(repo_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from emyrge.calculators.water_purification import WaterCalculator, WaterParams
from emyrge.core.config import EmyrgeConfig
from emyrge.web.app import EmyrgeRuntime, create_server


class TestMilestone4AdversarialValidation(unittest.TestCase):
    """Rigorous empirical validation of Milestone 4 edge cases and route aliases."""

    @classmethod
    def setUpClass(cls):
        cfg = EmyrgeConfig.from_env(repo_root)
        cls.runtime = EmyrgeRuntime(cfg)

        # Spin up test HTTP server on ephemeral port
        server_cfg = EmyrgeConfig.from_env(repo_root)
        server_cfg.host = "127.0.0.1"
        server_cfg.port = 0
        cls.server, _ = create_server(server_cfg)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post_json(self, endpoint: str, payload: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    # -------------------------------------------------------------------------
    # 1. Volume Edge Cases (0.0, -1.0, -100.0, 0.0 gallons, negative gallons)
    # -------------------------------------------------------------------------

    def test_adv_volume_liters_zero(self):
        """0.0 Liters MUST raise ValueError in run_calculator and HTTP 400 at API."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": 0.0})
        self.assertIn("Water volume must be strictly positive", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": 0.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Water volume must be strictly positive")

    def test_adv_volume_liters_negative_one(self):
        """-1.0 Liters MUST raise ValueError in run_calculator and HTTP 400 at API."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": -1.0})
        self.assertIn("Water volume must be strictly positive", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": -1.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Water volume must be strictly positive")

    def test_adv_volume_liters_negative_hundred(self):
        """-100.0 Liters MUST raise ValueError in run_calculator and HTTP 400 at API."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": -100.0})
        self.assertIn("Water volume must be strictly positive", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": -100.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Water volume must be strictly positive")

    def test_adv_volume_gallons_zero(self):
        """0.0 Gallons MUST raise ValueError in run_calculator and HTTP 400 at API."""
        for zero_val in (0.0, 0, "0.0", "0"):
            with self.subTest(zero_val=zero_val):
                with self.assertRaises(ValueError) as cm:
                    self.runtime.run_calculator("water", {"volume_gallons": zero_val})
                self.assertIn("Water volume must be strictly positive", str(cm.exception))

                status, data = self._post_json("/api/calc", {"type": "water", "volume_gallons": zero_val})
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "Water volume must be strictly positive")

    def test_adv_volume_gallons_negative(self):
        """Negative gallons (-1.0, -100.0) MUST raise ValueError and HTTP 400."""
        for neg_val in (-1.0, -100.0, "-1.0", "-100.0"):
            with self.subTest(neg_val=neg_val):
                with self.assertRaises(ValueError) as cm:
                    self.runtime.run_calculator("water", {"volume_gallons": neg_val})
                self.assertIn("Water volume must be strictly positive", str(cm.exception))

                status, data = self._post_json("/api/calc", {"type": "water", "volume_gallons": neg_val})
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "Water volume must be strictly positive")

    # -------------------------------------------------------------------------
    # 2. Concentration Edge Cases (0.0%, -5.0%, 16.0%, 50.0%)
    # -------------------------------------------------------------------------

    def test_adv_concentration_zero_percent(self):
        """0.0% bleach concentration MUST raise ValueError and HTTP 400."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": 10.0, "concentration_pct": 0.0})
        self.assertIn("Concentration must be between 1% and 15%", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": 10.0, "concentration_pct": 0.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("Concentration must be between 1% and 15%", data["error"])

    def test_adv_concentration_negative_five_percent(self):
        """-5.0% bleach concentration MUST raise ValueError and HTTP 400."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": 10.0, "concentration_pct": -5.0})
        self.assertIn("Concentration must be between 1% and 15%", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": 10.0, "concentration_pct": -5.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("Concentration must be between 1% and 15%", data["error"])

    def test_adv_concentration_sixteen_percent(self):
        """16.0% bleach concentration (out of bound >15%) MUST raise ValueError and HTTP 400."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": 10.0, "concentration_pct": 16.0})
        self.assertIn("Concentration must be between 1% and 15%", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": 10.0, "concentration_pct": 16.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("Concentration must be between 1% and 15%", data["error"])

    def test_adv_concentration_fifty_percent(self):
        """50.0% bleach concentration (industrial) MUST raise ValueError and HTTP 400."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("water", {"volume_liters": 10.0, "concentration_pct": 50.0})
        self.assertIn("Concentration must be between 1% and 15%", str(cm.exception))

        status, data = self._post_json("/api/calc", {"type": "water", "volume_liters": 10.0, "concentration_pct": 50.0})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("Concentration must be between 1% and 15%", data["error"])

    # -------------------------------------------------------------------------
    # 3. Route Aliases & Error Parity (/api/calculator/water_purification & /api/calc)
    # -------------------------------------------------------------------------

    def test_adv_route_aliases_success_parity(self):
        """Both endpoints return HTTP 200 with identical results for valid inputs."""
        payload_calc = {"type": "water", "volume_liters": 20.0, "method": "bleach", "clarity": "clear"}
        payload_alias = {"volume_liters": 20.0, "method": "bleach", "clarity": "clear"}

        status_calc, resp_calc = self._post_json("/api/calc", payload_calc)
        status_alias, resp_alias = self._post_json("/api/calculator/water_purification", payload_alias)

        self.assertEqual(status_calc, 200)
        self.assertEqual(status_alias, 200)
        self.assertTrue(resp_calc["ok"])
        self.assertTrue(resp_alias["ok"])
        self.assertEqual(resp_calc["result"], resp_alias["result"])
        self.assertEqual(resp_alias["result"]["drops"], 40)
        self.assertEqual(resp_alias["result"]["volume_ml"], 2.0)

    def test_adv_route_alias_error_parity(self):
        """All invalid inputs to /api/calculator/water_purification return HTTP 400 matching /api/calc."""
        invalid_cases = [
            ({"volume_liters": 0.0}, "Water volume must be strictly positive"),
            ({"volume_liters": -1.0}, "Water volume must be strictly positive"),
            ({"volume_liters": -100.0}, "Water volume must be strictly positive"),
            ({"volume_gallons": 0.0}, "Water volume must be strictly positive"),
            ({"volume_gallons": -1.0}, "Water volume must be strictly positive"),
            ({"volume_gallons": -100.0}, "Water volume must be strictly positive"),
            ({"volume_liters": 10.0, "concentration_pct": 0.0}, "Concentration must be between 1% and 15%"),
            ({"volume_liters": 10.0, "concentration_pct": -5.0}, "Concentration must be between 1% and 15%"),
            ({"volume_liters": 10.0, "concentration_pct": 16.0}, "Concentration must be between 1% and 15%"),
            ({"volume_liters": 10.0, "concentration_pct": 50.0}, "Concentration must be between 1% and 15%"),
        ]

        for payload, expected_err_sub in invalid_cases:
            with self.subTest(payload=payload):
                status_alias, resp_alias = self._post_json("/api/calculator/water_purification", payload)
                self.assertEqual(status_alias, 400, f"Expected 400 for {payload}, got {status_alias}")
                self.assertFalse(resp_alias["ok"])
                self.assertIn(expected_err_sub, resp_alias["error"])

                # Test parity on /api/calc
                calc_payload = {"type": "water", **payload}
                status_calc, resp_calc = self._post_json("/api/calc", calc_payload)
                self.assertEqual(status_calc, 400)
                self.assertEqual(resp_calc["error"], resp_alias["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
