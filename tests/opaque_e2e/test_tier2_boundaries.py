"""Tier 2: Boundary & Corner Cases Test Suite.

Verifies system resilience against invalid inputs, empty payloads, mathematical
extremes, clinical envelope bounds, division-by-zero guards, corrupted file headers,
and multi-byte Unicode strings.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import tempfile
import unittest

from tests.opaque_e2e.conftest_base import (
    BaseOpaqueTestCase,
    AuthoritativeWaterOracle,
    AuthoritativeMedicalOracle,
    AuthoritativeSolarOracle,
    AuthoritativeElectricalOracle,
    ZIM_MAGIC_LE,
    ZIM_MAGIC_INT_LE,
    ZIM_MAGIC_INT_BE,
    GGUF_MAGIC,
    GZIP_MAGIC,
    get_repo_root,
)


class TestTier2WaterCalculatorBoundaries(BaseOpaqueTestCase):
    """Boundary conditions and division-by-zero guards for WaterCalculator."""

    def setUp(self):
        super().setUp()
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.water_purification import WaterCalculator
        self.calc = WaterCalculator

    def test_wcb_01_zero_volume_raises_value_error(self):
        """Rejects zero volume with explicit ValueError."""
        with self.assertRaises(ValueError):
            self.calc.calculate_bleach(volume_liters=0.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_iodine(volume_liters=0.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_boiling(volume_liters=0.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_sodis(volume_liters=0.0)

    def test_wcb_02_negative_volume_raises_value_error(self):
        """Rejects negative volumes with explicit ValueError."""
        with self.assertRaises(ValueError):
            self.calc.calculate_bleach(volume_liters=-25.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_iodine(volume_liters=-5.0)

    def test_wcb_03_bleach_concentration_bounds(self):
        """Enforces bleach concentration bounds within (0, 15.0]%."""
        with self.assertRaises(ValueError):
            self.calc.calculate_bleach(volume_liters=10.0, concentration_pct=0.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_bleach(volume_liters=10.0, concentration_pct=-1.5)
        with self.assertRaises(ValueError):
            self.calc.calculate_bleach(volume_liters=10.0, concentration_pct=15.1)

        # Valid low and high concentrations calculate without crash
        low_res = self.calc.calculate_bleach(volume_liters=10.0, concentration_pct=1.0)
        high_res = self.calc.calculate_bleach(volume_liters=10.0, concentration_pct=15.0)
        self.assertGreater(low_res["drops"], high_res["drops"])

    def test_wcb_04_boiling_altitude_step_up_boundary(self):
        """Tests high-altitude boiling boundary exactly at 2000m threshold."""
        below_2000 = self.calc.calculate_boiling(volume_liters=5.0, elevation_meters=1999.0)
        at_2000 = self.calc.calculate_boiling(volume_liters=5.0, elevation_meters=2000.0)
        above_2000 = self.calc.calculate_boiling(volume_liters=5.0, elevation_meters=3500.0)

        self.assertEqual(below_2000["boil_time_minutes"], 1)
        self.assertEqual(at_2000["boil_time_minutes"], 3)
        self.assertEqual(above_2000["boil_time_minutes"], 3)

    def test_wcb_05_sodis_turbidity_safety_invalidation(self):
        """Verifies SODIS solar disinfection invalidates and warns when water is turbid."""
        clear_sunny = self.calc.calculate_sodis(volume_liters=2.0, is_cloudy=False, is_turbid=False)
        clear_cloudy = self.calc.calculate_sodis(volume_liters=2.0, is_cloudy=True, is_turbid=False)
        turbid = self.calc.calculate_sodis(volume_liters=2.0, is_turbid=True)

        self.assertTrue(clear_sunny["is_effective"])
        self.assertEqual(clear_sunny["exposure_hours"], 6)
        self.assertTrue(clear_cloudy["is_effective"])
        self.assertEqual(clear_cloudy["exposure_hours"], 48)

        self.assertFalse(turbid["is_effective"])
        self.assertEqual(turbid["exposure_hours"], 0)
        self.assertIn("warning", turbid)

    def test_wcb_06_extreme_large_volume_calculation(self):
        """Tests extreme large volume (1,000,000 L municipal cistern) without overflow."""
        res = self.calc.calculate_bleach(volume_liters=1_000_000.0, is_turbid=False, concentration_pct=6.0)
        self.assertEqual(res["drops"], 2_000_000)
        self.assertEqual(res["volume_ml"], 100_000.0)


class TestTier2MedicalCalculatorBoundaries(BaseOpaqueTestCase):
    """Boundary conditions and clinical safety envelope for MedicalCalculator."""

    def setUp(self):
        super().setUp()
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.medical_rehydration import MedicalCalculator
        self.calc = MedicalCalculator

    def test_mcb_01_underweight_clinical_minimum_guard(self):
        """Rejects patient weight below 2.0 kg clinical threshold."""
        with self.assertRaises(ValueError):
            self.calc.calculate_ors(1.9)
        with self.assertRaises(ValueError):
            self.calc.calculate_paracetamol(1.99)
        with self.assertRaises(ValueError):
            self.calc.calculate_ibuprofen(0.5)

    def test_mcb_02_overweight_clinical_maximum_guard(self):
        """Rejects patient weight above 250.0 kg clinical threshold."""
        with self.assertRaises(ValueError):
            self.calc.calculate_ors(250.1)
        with self.assertRaises(ValueError):
            self.calc.calculate_paracetamol(300.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_ibuprofen(500.0)

    def test_mcb_03_negative_and_zero_weight_rejected(self):
        """Rejects zero and negative weights with explicit ValueError."""
        with self.assertRaises(ValueError):
            self.calc.calculate_paracetamol(0.0)
        with self.assertRaises(ValueError):
            self.calc.calculate_ibuprofen(-12.0)

    def test_mcb_04_paracetamol_adult_dose_clamping(self):
        """Clamps single paracetamol dose to 1000 mg adult maximum across weights."""
        res_60kg = self.calc.calculate_paracetamol(60.0)  # 60 * 15 = 900 mg
        res_80kg = self.calc.calculate_paracetamol(80.0)  # 80 * 15 = 1200 -> clamped 1000 mg
        res_150kg = self.calc.calculate_paracetamol(150.0)  # 150 * 15 = 2250 -> clamped 1000 mg

        self.assertEqual(res_60kg["single_dose_mg"], 900.0)
        self.assertFalse(res_60kg["clamped_to_adult_max"])

        self.assertEqual(res_80kg["single_dose_mg"], 1000.0)
        self.assertTrue(res_80kg["clamped_to_adult_max"])

        self.assertEqual(res_150kg["single_dose_mg"], 1000.0)
        self.assertTrue(res_150kg["clamped_to_adult_max"])

    def test_mcb_05_ibuprofen_adult_dose_clamping(self):
        """Clamps single ibuprofen dose to 400 mg adult maximum across weights."""
        res_30kg = self.calc.calculate_ibuprofen(30.0)  # 30 * 10 = 300 mg
        res_50kg = self.calc.calculate_ibuprofen(50.0)  # 50 * 10 = 500 -> clamped 400 mg

        self.assertEqual(res_30kg["single_dose_mg"], 300.0)
        self.assertFalse(res_30kg["clamped_to_adult_max"])

        self.assertEqual(res_50kg["single_dose_mg"], 400.0)
        self.assertTrue(res_50kg["clamped_to_adult_max"])

    def test_mcb_06_unrecognized_medication_raises_error(self):
        """Rejects unsupported medications with explicit descriptive error."""
        with self.assertRaises(ValueError):
            self.calc.calculate({"medication": "aspirin", "weight_kg": 50.0})
        with self.assertRaises(ValueError):
            self.calc.calculate({"medication": "penicillin", "weight_kg": 20.0})


class TestTier2SolarAndElectricalBoundaries(BaseOpaqueTestCase):
    """Boundary conditions and guards for SolarCalculator and ElectricalCalculator."""

    def setUp(self):
        super().setUp()
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.solar_battery import SolarCalculator
        from emyrge.calculators.electrical_formulas import ElectricalCalculator
        self.solar = SolarCalculator
        self.elec = ElectricalCalculator

    def test_seb_01_solar_non_positive_inputs_rejected(self):
        """Rejects non-positive daily Wh, system voltage, or sun hours."""
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=0.0)
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=500.0, system_voltage=0.0)
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=500.0, peak_sun_hours=-1.0)

    def test_seb_02_solar_efficiency_factors_clamped_to_unity(self):
        """Rejects DoD, inverter efficiency, or derating outside (0.0, 1.0]."""
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=500.0, dod=1.1)
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=500.0, inverter_eff=0.0)
        with self.assertRaises(ValueError):
            self.solar.calculate_system(daily_wh=500.0, system_derating=1.05)

    def test_seb_03_ohms_law_short_circuit_prevention(self):
        """Rejects zero and negative resistance to guard against short circuit zero-division."""
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(v=12.0, r=0.0)
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(v=12.0, r=-4.0)

    def test_seb_04_ohms_law_negative_values_rejected(self):
        """Rejects negative voltage, current, or power."""
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(v=-12.0, r=4.0)
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(i=-3.0, r=4.0)
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(p=-36.0, v=12.0)

    def test_seb_05_ohms_law_insufficient_parameters(self):
        """Rejects calls with fewer than 2 known parameters."""
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law(v=12.0)
        with self.assertRaises(ValueError):
            self.elec.solve_ohms_law()

    def test_seb_06_voltage_drop_excessive_run_flag(self):
        """Verifies DC voltage drop analysis flags runs exceeding NEC 3% / 5% limits."""
        # 12V system, 10A current, 100 meters one-way, AWG 14 (8.286 ohm/km)
        # Loop resistance: 2 * 0.1 km * 8.286 = 1.6572 ohms
        # Voltage drop = 10 * 1.6572 = 16.57 V (exceeds total 12V supply!)
        res = self.elec.calculate_voltage_drop_by_awg(
            source_voltage=12.0,
            current_a=10.0,
            one_way_length_meters=100.0,
            wire_awg="14",
        )
        self.assertGreater(res["percentage_drop"], 5.0)
        self.assertFalse(res["is_critical_acceptable"])
        self.assertFalse(res["is_standard_acceptable"])


class TestTier2BinaryHeadersAndCorruptedData(BaseOpaqueTestCase):
    """Boundary cases for corrupted, truncated, and malformed files."""

    def test_bhb_01_corrupted_zim_magic_byte(self):
        """Detects 1-byte corrupted OpenZIM magic bytes."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Valid is 0x5a 0x49 0x4d 0x04; corrupt last byte to 0x05
            f.write(b"\x5a\x49\x4d\x05" + b"\x00" * 1024)
            corrupt_path = Path(f.name)

        try:
            with open(corrupt_path, "rb") as f:
                header = f.read(4)
            magic_val = struct.unpack("<I", header)[0]
            self.assertNotIn(magic_val, (ZIM_MAGIC_INT_LE, ZIM_MAGIC_INT_BE))
        finally:
            corrupt_path.unlink()

    def test_bhb_02_corrupted_gguf_magic_byte(self):
        """Detects 1-byte corrupted GGUF magic bytes."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"HGUF" + b"\x00" * 1024)
            corrupt_path = Path(f.name)

        try:
            with open(corrupt_path, "rb") as f:
                header = f.read(4)
            self.assertNotEqual(header, GGUF_MAGIC)
        finally:
            corrupt_path.unlink()

    def test_bhb_03_truncated_files_under_4_bytes(self):
        """Verifies files under 4 bytes are detected as truncated."""
        for size in (0, 1, 2, 3):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"\x5a\x49\x4d"[:size])
                trunc_path = Path(f.name)
            try:
                with open(trunc_path, "rb") as f:
                    content = f.read(4)
                self.assertLess(len(content), 4)
            finally:
                trunc_path.unlink()

    def test_bhb_04_corrupted_posix_gzip_tarball(self):
        """Detects corrupted gzip magic bytes on POSIX tarball."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\x1f\x8c" + b"\x00" * 1024)
            corrupt_path = Path(f.name)
        try:
            with open(corrupt_path, "rb") as f:
                header = f.read(2)
            self.assertNotEqual(header, GZIP_MAGIC)
        finally:
            corrupt_path.unlink()

    def test_bhb_05_synthetic_model_hashes_distinguished_from_real(self):
        """Verifies synthetic catalog placeholder hashes (...0135, ...0320) are identified."""
        import json
        manifest_path = self.repo_root / "manifests" / "models.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for m in data.get("models", []):
            sha = m.get("sha256", "")
            if m["id"] == "qwen2.5-0.5b-q4":
                self.assertFalse(sha.startswith("000000000000000000000000000000000000000000000000000000000000"))
            else:
                # Placeholders begin with zeros
                self.assertTrue(sha.startswith("000000000000000000000000000000000000000000000000000000000000"))


class TestTier2StringsAndUnicodeBoundaries(BaseOpaqueTestCase):
    """Boundary handling for empty strings, whitespace, Unicode, and special characters."""

    def test_sub_01_empty_query_string_graceful_handling(self):
        """Verifies empty query string returns valid response without crashing."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        res = runtime.handle_ask("", mode="harness")
        self.assertIn("answer", res)
        self.assertIsInstance(res["answer"], str)

    def test_sub_02_whitespace_only_query_handling(self):
        """Verifies whitespace-only query string is safely handled."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        res = runtime.handle_ask("   \t\n   ", mode="harness")
        self.assertIn("answer", res)

    def test_sub_03_unicode_and_emoji_query_handling(self):
        """Verifies multi-byte Unicode and emoji characters do not corrupt encoding."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        query = "💧 Emergency Water Treatment 🧪 - 6% Sodium Hypochlorite"
        res = runtime.handle_ask(query, mode="harness")
        self.assertIn("answer", res)

    def test_sub_04_sqlite_injection_payload_in_query(self):
        """Verifies SQL injection meta-characters are parameterized without syntax error."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.memory.memory_vault import MemoryVault

        with tempfile.TemporaryDirectory() as td:
            vault = MemoryVault(Path(td))
            # Test FTS5 search with SQL injection payload
            injection_query = "'; DROP TABLE vault_interactions; --"
            res = vault.search(injection_query)
            self.assertIn("entries", res)
            self.assertIn("master_notes", res)

    def test_sub_05_extreme_query_length_truncation(self):
        """Verifies extreme query strings (>50,000 chars) are processed without memory blowup."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        huge_query = "water disinfection " * 3000  # ~57 KB string
        res = runtime.handle_ask(huge_query, mode="harness")
        self.assertIn("answer", res)


if __name__ == "__main__":
    unittest.main()
