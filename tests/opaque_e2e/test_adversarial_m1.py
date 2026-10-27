"""Adversarial Stress & Boundary Challenge Test Suite for Milestone 1.

Authored by teamwork_preview_challenger (challenger_m1_1).
Role: Adversarial Empirical Verifier for Milestone 1 Services & Calculators.

Tests:
1. Zero-volume (0L), negative volume, and extreme volume (100,000L - 1,000,000L).
2. Out-of-bounds bleach concentrations (<=0%, >15%, negative, industrial).
3. Boundary turbidity truthiness and SODIS invalidation.
4. Division-by-zero guards across all 4 calculators (Water, Medical, Solar, Electrical).
5. Command Center runtime input handling, error isolation, and crash resilience.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

# Ensure src/ and repo root are in sys.path
current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parent.parent
src_dir = repo_root / "src"
for p in (str(src_dir), str(repo_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from emyrge.calculators.water_purification import WaterCalculator, WaterParams
from emyrge.calculators.medical_rehydration import MedicalCalculator, MedicalParams
from emyrge.calculators.solar_battery import SolarCalculator, SolarParams
from emyrge.calculators.electrical_formulas import ElectricalCalculator, ElectricalParams
from emyrge.calculators.source_audit import CalculatorRouter, SourceAudit
from emyrge.core.config import EmyrgeConfig
from emyrge.web.app import EmyrgeRuntime, _to_bool, _to_float


class TestAdversarialWaterCalculator(unittest.TestCase):
    """Stress tests and boundary checks for WaterCalculator."""

    def test_adv_water_01_zero_volume_strictly_rejected(self):
        """0L volume MUST raise ValueError in all water disinfection methods."""
        for method_name, method in [
            ("bleach", lambda: WaterCalculator.calculate_bleach(0.0)),
            ("iodine", lambda: WaterCalculator.calculate_iodine(0.0)),
            ("boiling", lambda: WaterCalculator.calculate_boiling(0.0)),
            ("sodis", lambda: WaterCalculator.calculate_sodis(0.0)),
            ("unified_dict", lambda: WaterCalculator.calculate({"volume_liters": 0.0, "method": "bleach"})),
            ("unified_params", lambda: WaterCalculator.calculate(WaterParams(volume_liters=0.0))),
        ]:
            with self.subTest(method=method_name):
                with self.assertRaises(ValueError, msg=f"Method {method_name} failed to reject 0L volume"):
                    method()

    def test_adv_water_02_negative_volume_strictly_rejected(self):
        """Negative volumes must raise ValueError."""
        for neg_vol in (-0.001, -1.0, -20.0, -100000.0):
            with self.subTest(volume=neg_vol):
                with self.assertRaises(ValueError):
                    WaterCalculator.calculate_bleach(neg_vol)
                with self.assertRaises(ValueError):
                    WaterCalculator.calculate_iodine(neg_vol)
                with self.assertRaises(ValueError):
                    WaterCalculator.calculate_boiling(neg_vol)
                with self.assertRaises(ValueError):
                    WaterCalculator.calculate_sodis(neg_vol)

    def test_adv_water_03_invalid_bleach_concentrations(self):
        """Bleach concentrations outside (0, 15.0]% must raise ValueError."""
        for invalid_conc in (0.0, -1.0, -10.0, 15.01, 20.0, 50.0, 100.0):
            with self.subTest(conc=invalid_conc):
                with self.assertRaises(ValueError, msg=f"Failed to reject concentration {invalid_conc}%"):
                    WaterCalculator.calculate_bleach(volume_liters=10.0, concentration_pct=invalid_conc)

    def test_adv_water_04_valid_concentration_extremes_scaling(self):
        """Valid concentration limits (1.0% and 15.0%) scale deterministically without crashing."""
        vol = 20.0
        res_1pct = WaterCalculator.calculate_bleach(vol, is_turbid=False, concentration_pct=1.0)
        res_6pct = WaterCalculator.calculate_bleach(vol, is_turbid=False, concentration_pct=6.0)
        res_15pct = WaterCalculator.calculate_bleach(vol, is_turbid=False, concentration_pct=15.0)

        # 1% bleach is 1/6th as strong as 6% -> requires 6x drops
        self.assertEqual(res_1pct["drops"], res_6pct["drops"] * 6)
        # 15% bleach is 2.5x as strong as 6% -> requires 1/2.5 = 0.4x drops
        self.assertEqual(res_15pct["drops"], math.ceil(vol * 2 * (6.0 / 15.0)))
        self.assertLess(res_15pct["drops"], res_6pct["drops"])

    def test_adv_water_05_extreme_municipal_cistern_volumes(self):
        """Extreme large volumes (100,000L and 1,000,000L) compute exact math without overflow."""
        # 100,000 L clear water: 2 drops/L = 200,000 drops = 10,000.0 mL = 10 L bleach
        res_100k = WaterCalculator.calculate_bleach(100_000.0, is_turbid=False, concentration_pct=6.0)
        self.assertEqual(res_100k["drops"], 200_000)
        self.assertEqual(res_100k["volume_ml"], 10_000.0)
        self.assertEqual(res_100k["contact_time_minutes"], 30)

        # 100,000 L turbid water: 4 drops/L = 400,000 drops = 20,000.0 mL = 20 L bleach
        res_100k_turbid = WaterCalculator.calculate_bleach(100_000.0, is_turbid=True, concentration_pct=6.0)
        self.assertEqual(res_100k_turbid["drops"], 400_000)
        self.assertEqual(res_100k_turbid["volume_ml"], 20_000.0)
        self.assertEqual(res_100k_turbid["contact_time_minutes"], 60)

        # 1,000,000 L municipal cistern
        res_1m = WaterCalculator.calculate_bleach(1_000_000.0, is_turbid=False, concentration_pct=6.0)
        self.assertEqual(res_1m["drops"], 2_000_000)
        self.assertEqual(res_1m["volume_ml"], 100_000.0)

    def test_adv_water_06_boundary_turbidity_values(self):
        """Turbidity correctly doubles bleach dosage and contact time; invalidates SODIS."""
        clear = WaterCalculator.calculate_bleach(10.0, is_turbid=False)
        turbid = WaterCalculator.calculate_bleach(10.0, is_turbid=True)

        self.assertEqual(turbid["drops"], clear["drops"] * 2)
        self.assertEqual(turbid["contact_time_minutes"], 60)
        self.assertEqual(clear["contact_time_minutes"], 30)
        self.assertEqual(turbid["chlorine_ppm_target"], 4.0)
        self.assertEqual(clear["chlorine_ppm_target"], 2.0)

        # SODIS turbidity test
        sodis_clear = WaterCalculator.calculate_sodis(2.0, is_turbid=False)
        sodis_turbid = WaterCalculator.calculate_sodis(2.0, is_turbid=True)
        self.assertTrue(sodis_clear["is_effective"])
        self.assertFalse(sodis_turbid["is_effective"])
        self.assertEqual(sodis_turbid["exposure_hours"], 0)
        self.assertIn("turbidity prevents UV", sodis_turbid["warning"])

    def test_adv_water_07_mesh_summary_size_limit(self):
        """All mesh summaries must stay strictly under the 200-byte LoRa packet limit."""
        results = [
            WaterCalculator.calculate_bleach(100_000.0, is_turbid=True),
            WaterCalculator.calculate_iodine(50_000.0, is_turbid=True),
            WaterCalculator.calculate_boiling(1000.0, elevation_meters=3500.0),
            WaterCalculator.calculate_sodis(2.0, is_turbid=True),
            WaterCalculator.calculate_sodis(2.0, is_turbid=False, is_cloudy=True),
        ]
        for r in results:
            summary = WaterCalculator.format_mesh_summary(r)
            b_len = len(summary.encode("utf-8"))
            self.assertLessEqual(b_len, 200, f"Mesh summary exceeds 200 bytes ({b_len}B): {summary}")


class TestAdversarialMedicalCalculator(unittest.TestCase):
    """Clinical safety envelope and dosage clamping tests."""

    def test_adv_med_01_clinical_weight_envelope(self):
        """Patient weight outside [2.0 kg, 250.0 kg] must raise ValueError."""
        for invalid_wt in (0.0, -5.0, 1.99, 0.5, 250.01, 300.0, 999.0):
            with self.subTest(weight=invalid_wt):
                with self.assertRaises(ValueError):
                    MedicalCalculator.calculate_ors(invalid_wt)
                with self.assertRaises(ValueError):
                    MedicalCalculator.calculate_paracetamol(invalid_wt)
                with self.assertRaises(ValueError):
                    MedicalCalculator.calculate_ibuprofen(invalid_wt)

    def test_adv_med_02_weight_boundary_inclusion(self):
        """Exact boundaries 2.0 kg and 250.0 kg must calculate cleanly."""
        ors_min = MedicalCalculator.calculate_ors(2.0)
        self.assertEqual(ors_min["total_ors_ml_4h"], 150.0)
        self.assertEqual(ors_min["hourly_rate_ml"], 37.5)

        ors_max = MedicalCalculator.calculate_ors(250.0)
        self.assertEqual(ors_max["total_ors_ml_4h"], 18750.0)
        self.assertEqual(ors_max["hourly_rate_ml"], 4687.5)

    def test_adv_med_03_adult_paracetamol_dose_clamping(self):
        """Paracetamol single dose must cap at 1000.0 mg; daily dose at 4000.0 mg."""
        # 60 kg: 60 * 15 = 900 mg (unclamped)
        res_60 = MedicalCalculator.calculate_paracetamol(60.0)
        self.assertEqual(res_60["single_dose_mg"], 900.0)
        self.assertFalse(res_60["clamped_to_adult_max"])

        # 66.7 kg threshold: 66.7 * 15 = 1000.5 mg -> clamped to 1000.0 mg
        res_67 = MedicalCalculator.calculate_paracetamol(66.7)
        self.assertEqual(res_67["single_dose_mg"], 1000.0)
        self.assertTrue(res_67["clamped_to_adult_max"])

        # 120 kg adult: 120 * 15 = 1800 -> clamped to 1000.0 mg; 120 * 60 = 7200 -> clamped to 4000.0 mg
        res_120 = MedicalCalculator.calculate_paracetamol(120.0)
        self.assertEqual(res_120["single_dose_mg"], 1000.0)
        self.assertEqual(res_120["max_daily_mg"], 4000.0)
        self.assertTrue(res_120["clamped_to_adult_max"])

    def test_adv_med_04_adult_ibuprofen_dose_clamping(self):
        """Ibuprofen single dose must cap at 400.0 mg; daily dose at 1200.0 mg."""
        # 30 kg: 30 * 10 = 300 mg (unclamped)
        res_30 = MedicalCalculator.calculate_ibuprofen(30.0)
        self.assertEqual(res_30["single_dose_mg"], 300.0)
        self.assertFalse(res_30["clamped_to_adult_max"])

        # 40.1 kg: 40.1 * 10 = 401 mg -> clamped to 400.0 mg
        res_41 = MedicalCalculator.calculate_ibuprofen(40.1)
        self.assertEqual(res_41["single_dose_mg"], 400.0)
        self.assertTrue(res_41["clamped_to_adult_max"])

        # 90 kg adult: 90 * 10 = 900 -> clamped to 400.0 mg; 90 * 40 = 3600 -> clamped to 1200.0 mg
        res_90 = MedicalCalculator.calculate_ibuprofen(90.0)
        self.assertEqual(res_90["single_dose_mg"], 400.0)
        self.assertEqual(res_90["max_daily_mg"], 1200.0)
        self.assertTrue(res_90["clamped_to_adult_max"])


class TestAdversarialSolarAndElectrical(unittest.TestCase):
    """Division-by-zero guards and boundary tests for Solar and Electrical calculators."""

    def test_adv_solar_01_division_by_zero_guards(self):
        """Non-positive parameters must be rejected before division."""
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=0.0)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, system_voltage=0.0)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, peak_sun_hours=0.0)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, dod=0.0)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, inverter_eff=0.0)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, system_derating=0.0)

    def test_adv_solar_02_efficiency_exceeding_unity(self):
        """Factors > 1.0 must be rejected."""
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, dod=1.01)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, inverter_eff=1.05)
        with self.assertRaises(ValueError):
            SolarCalculator.calculate_system(daily_wh=500.0, system_derating=1.1)

    def test_adv_elec_01_short_circuit_prevention(self):
        """Resistance <= 0 must raise ValueError to prevent short-circuit calculations."""
        with self.assertRaises(ValueError):
            ElectricalCalculator.solve_ohms_law(v=12.0, r=0.0)
        with self.assertRaises(ValueError):
            ElectricalCalculator.solve_ohms_law(v=12.0, r=-2.5)

    def test_adv_elec_02_zero_current_division_guard(self):
        """Zero current when calculating resistance must raise ValueError."""
        with self.assertRaises(ValueError):
            ElectricalCalculator.solve_ohms_law(v=12.0, i=0.0)

    def test_adv_elec_03_unknown_awg_gauge(self):
        """Unknown AWG gauge string must raise ValueError listing available gauges."""
        with self.assertRaises(ValueError) as cm:
            ElectricalCalculator.calculate_voltage_drop_by_awg(12.0, 10.0, 15.0, "99_AWG")
        self.assertIn("Available gauges", str(cm.exception))


class TestAdversarialCommandCenterRuntime(unittest.TestCase):
    """Adversarial challenge of Command Center web runtime and API contracts."""

    @classmethod
    def setUpClass(cls):
        cfg = EmyrgeConfig.from_env(repo_root)
        cls.runtime = EmyrgeRuntime(cfg)

    def test_adv_runtime_01_zero_volume_strictly_rejected(self):
        """ADV-1: run_calculator('water', volume=0) must raise ValueError rather than coercing to 5L."""
        for zero_payload in (
            {"volume_liters": 0.0},
            {"volume": 0.0},
            {"liters": 0.0},
            {"volume_gallons": 0.0},
            {"volume_gallons": "0.0"},
            {"volume_gallons": 0},
        ):
            with self.subTest(payload=zero_payload):
                with self.assertRaises(ValueError) as cm:
                    self.runtime.run_calculator("water", zero_payload)
                self.assertIn("Water volume must be strictly positive", str(cm.exception))

    def test_adv_runtime_02_negative_volume_strictly_rejected(self):
        """ADV-1: run_calculator('water', volume<0) must raise ValueError rather than clamping to 0.1L."""
        for neg_payload in (
            {"volume_liters": -1.0},
            {"volume_liters": -25.0},
            {"volume_liters": -100.0},
            {"volume_gallons": -1.0},
            {"volume_gallons": -100.0},
            {"volume_gallons": "-5.0"},
        ):
            with self.subTest(payload=neg_payload):
                with self.assertRaises(ValueError) as cm:
                    self.runtime.run_calculator("water", neg_payload)
                self.assertIn("Water volume must be strictly positive", str(cm.exception))

    def test_adv_runtime_03_invalid_concentration_strictly_rejected(self):
        """ADV-2: Bleach concentrations <= 0% or > 15% must raise ValueError rather than silent clamping."""
        for inv_conc in (0.0, -1.0, -2.0, -5.0, 15.01, 16.0, 50.0, 100.0):
            with self.subTest(conc=inv_conc):
                with self.assertRaises(ValueError) as cm:
                    self.runtime.run_calculator("water", {"volume_liters": 10.0, "concentration_pct": inv_conc})
                self.assertIn("Concentration must be between 1% and 15%", str(cm.exception))

    def test_adv_runtime_08_http_api_calc_validation_and_route_alias(self):
        """ADV-1, ADV-2, ADV-3: HTTP API validation errors return 400; route alias returns 200 parity."""
        import json
        import threading
        import urllib.request
        import urllib.error
        from emyrge.web.app import create_server

        server_cfg = EmyrgeConfig.from_env(repo_root)
        server_cfg.host = "127.0.0.1"
        server_cfg.port = 0  # Bind to ephemeral free port
        server, _ = create_server(server_cfg)
        actual_port = server.server_port

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        base_url = f"http://127.0.0.1:{actual_port}"

        def post_json(endpoint: str, payload: dict) -> tuple[int, dict]:
            req = urllib.request.Request(
                f"{base_url}{endpoint}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode("utf-8"))

        try:
            # 1. ADV-1: volume 0.0, -1.0, -100.0 return HTTP 400
            for bad_vol in (0.0, -1.0, -100.0):
                status, data = post_json("/api/calc", {"type": "water", "volume_liters": bad_vol})
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "Water volume must be strictly positive")

            # 2. ADV-1: volume_gallons 0.0, -1.0, -100.0 return HTTP 400
            for bad_gal in (0.0, -1.0, -100.0):
                status, data = post_json("/api/calc", {"type": "water", "volume_gallons": bad_gal})
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "Water volume must be strictly positive")

            # 3. ADV-2: concentration 0.0%, -5.0%, 16.0%, 50.0% return HTTP 400
            for bad_conc in (0.0, -5.0, 16.0, 50.0):
                status, data = post_json("/api/calc", {"type": "water", "volume_liters": 10.0, "concentration_pct": bad_conc})
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])
                self.assertIn("Concentration must be between 1% and 15%", data["error"])

            # 4. ADV-3: route alias /api/calculator/water_purification matches /api/calc
            calc_status, calc_data = post_json("/api/calc", {"type": "water", "volume_liters": 20.0, "method": "bleach", "clarity": "clear"})
            alias_status, alias_data = post_json("/api/calculator/water_purification", {"volume_liters": 20.0, "method": "bleach", "clarity": "clear"})

            self.assertEqual(calc_status, 200)
            self.assertEqual(alias_status, 200)
            self.assertEqual(alias_data["result"]["drops"], 40)
            self.assertEqual(alias_data["result"]["volume_ml"], 2.0)
            self.assertEqual(alias_data["result"], calc_data["result"])

            # 5. ADV-3: route alias invalid volume (0.0, -1.0, -100.0, gallons) returns HTTP 400
            for bad_alias_payload in (
                {"volume_liters": 0.0},
                {"volume_liters": -1.0},
                {"volume_liters": -100.0},
                {"volume_gallons": 0.0},
                {"volume_gallons": -1.0},
            ):
                alias_err_status, alias_err_data = post_json("/api/calculator/water_purification", bad_alias_payload)
                self.assertEqual(alias_err_status, 400)
                self.assertEqual(alias_err_data["error"], "Water volume must be strictly positive")

            # 6. ADV-3: route alias invalid concentration (0.0%, -5.0%, 16.0%, 50.0%) returns HTTP 400
            for bad_conc in (0.0, -5.0, 16.0, 50.0):
                alias_err_status, alias_err_data = post_json(
                    "/api/calculator/water_purification", {"volume_liters": 10.0, "concentration_pct": bad_conc}
                )
                self.assertEqual(alias_err_status, 400)
                self.assertIn("Concentration must be between 1% and 15%", alias_err_data["error"])

        finally:
            server.shutdown()
            server.server_close()

    def test_adv_runtime_04_turbidity_string_coercion(self):
        """Verifies _to_bool correctly coerces adversarial string variations."""
        for truthy_val in ("turbid", "TURBID", "cloudy", "1", "true", "yes", "on", True, 1):
            self.assertTrue(_to_bool(truthy_val), f"Failed to parse truthy: {truthy_val}")
        for falsy_val in ("clear", "false", "0", "off", "no", None, "", False, 0, "banana"):
            self.assertFalse(_to_bool(falsy_val), f"Failed to parse falsy: {falsy_val}")

    def test_adv_runtime_05_unsupported_calculator_type_raises(self):
        """Unsupported calculator type raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self.runtime.run_calculator("quantum_teleportation", {})
        self.assertIn("Unsupported calculator type", str(cm.exception))

    def test_adv_runtime_06_sql_injection_and_malformed_input_safety(self):
        """SQL injection strings in queries and calculator params do not crash the engine."""
        malicious = "'; DROP TABLE interactions; --"
        route = CalculatorRouter.analyze_query(malicious)
        self.assertEqual(route.route, "general")

        # Memory search with SQL injection payload
        res = self.runtime.memory_vault.search(malicious)
        self.assertIsInstance(res, dict)
        self.assertIn("entries", res)

    def test_adv_runtime_07_source_audit_detects_hallucinated_dosages(self):
        """SourceAudit correctly flags ungrounded hallucinated numbers."""
        # Grounding passage states 20 drops
        sources = ["CDC: Add 20 drops (1.0 mL) of 6% bleach to 5 liters of turbid water. Wait 60 minutes."]
        # Hallucinated answer states 50 drops (dangerous overdose)
        hallucinated = "Add 50 drops (2.5 mL) of 6% bleach to 5 liters of turbid water. Wait 60 minutes."

        audit = SourceAudit.audit(hallucinated, sources)
        self.assertFalse(audit.is_clean, "SourceAudit failed to flag hallucinated 50 drops")
        self.assertGreater(len(audit.flagged_claims), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
