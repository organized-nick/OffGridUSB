"""Tier 3: Cross-Feature Combinations Test Suite.

Verifies pairwise and multi-subsystem interactions across the OffGridUSB stack:
- Grounded AI Professor + Deterministic Water/Medical Calculators + ZIM RAG
- Solar Sizing + Electrical DC Voltage Drop Analysis
- Unified Knowledge Search across ZIM archives and Khan Academy
- Memory Vault FTS5 storage, retrieval, and 70B distillation pipeline
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.opaque_e2e.conftest_base import (
    BaseOpaqueTestCase,
    AuthoritativeWaterOracle,
    AuthoritativeMedicalOracle,
    AuthoritativeSolarOracle,
    AuthoritativeElectricalOracle,
    CITATION_PATTERN,
    get_repo_root,
)


class TestTier3Combinations(BaseOpaqueTestCase):
    """Pairwise cross-feature interactions across AI, calculators, and offline data."""

    def setUp(self):
        super().setUp()
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig
        from emyrge.calculators.source_audit import CalculatorRouter, SourceAudit
        from emyrge.calculators.water_purification import WaterCalculator
        from emyrge.calculators.medical_rehydration import MedicalCalculator
        from emyrge.calculators.solar_battery import SolarCalculator
        from emyrge.calculators.electrical_formulas import ElectricalCalculator

        self.cfg = EmyrgeConfig.from_env(self.repo_root)
        self.runtime = EmyrgeRuntime(self.cfg)
        self.router = CalculatorRouter
        self.audit = SourceAudit
        self.water_calc = WaterCalculator
        self.med_calc = MedicalCalculator
        self.solar_calc = SolarCalculator
        self.elec_calc = ElectricalCalculator

    def test_combo_01_professor_water_calculator_and_zim_grounding(self):
        """Combo: Professor query routes to Water Calculator, embeds oracle, and cites ZIM."""
        query = "How many drops of bleach are needed for 5 liters of turbid water?"
        # 1. Router intercepts intent
        analysis = self.router.analyze_query(query)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis["type"], "water")
        self.assertEqual(analysis["params"]["volume_liters"], 5.0)
        self.assertTrue(analysis["params"]["is_turbid"])

        # 2. Execution yields deterministic CDC oracle values
        calc_res = self.water_calc.calculate(analysis["params"])
        self.assertEqual(calc_res["drops"], 20)
        self.assertEqual(calc_res["volume_ml"], 1.0)
        self.assertEqual(calc_res["contact_time_minutes"], 60)

        # 3. Grounded response embeds oracle output and valid citation
        response = self.runtime.handle_ask(query, mode="harness")
        self.assertIn("answer", response)
        self.assert_valid_citation(response["answer"])
        # Must contain dosage from oracle
        self.assertTrue("20" in response["answer"] or "1.0" in response["answer"] or "1 mL" in response["answer"])

    def test_combo_02_professor_medical_calculator_and_adult_cap(self):
        """Combo: Professor query routes to Medical Calculator, clamps adult paracetamol, and cites reference."""
        query = "What is the paracetamol single dose for an 80kg adult with acute pain?"
        analysis = self.router.analyze_query(query)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis["type"], "medical")
        self.assertEqual(analysis["params"]["weight_kg"], 80.0)

        calc_res = self.med_calc.calculate(analysis["params"])
        # 80 * 15 = 1200mg, must be clamped to 1000mg adult maximum
        self.assertEqual(calc_res["single_dose_mg"], 1000.0)
        self.assertTrue(calc_res["clamped_to_adult_max"])

        response = self.runtime.handle_ask(query, mode="harness")
        self.assertIn("answer", response)
        self.assert_valid_citation(response["answer"])

    def test_combo_03_solar_sizing_and_electrical_voltage_drop(self):
        """Combo: Standalone solar battery sizing coupled with DC cable run voltage drop."""
        # 1. Size a remote field clinic solar system: 1200 Wh/day, 24V bus, 2 days autonomy, 80% DoD
        solar_res = self.solar_calc.calculate_system(
            daily_wh=1200.0,
            system_voltage=24.0,
            dod=0.8,
            autonomy_days=2.0,
            inverter_eff=0.90,
            peak_sun_hours=4.5,
            system_derating=0.77,
        )
        self.assertEqual(solar_res["battery_capacity_ah"], 138.89)
        self.assertEqual(solar_res["solar_array_watts"], 346.32)

        # 2. Check DC wire run from array to charge controller (15A current, 15m one-way, AWG 10)
        drop_res = self.elec_calc.calculate_voltage_drop_by_awg(
            source_voltage=24.0,
            current_a=15.0,
            one_way_length_meters=15.0,
            wire_awg="10",
        )
        # AWG 10 is 3.277 ohm/km -> loop resistance = 2 * 0.015 * 3.277 = 0.0983 ohms
        # Voltage drop = 15 * 0.0983 = 1.47 V (6.14% of 24V)
        self.assertAlmostEqual(drop_res["voltage_drop"], 1.47, places=1)
        # Check against AWG 6 heavier gauge (1.296 ohm/km -> loop = 2 * 0.015 * 1.296 = 0.0388 ohms -> drop = 0.58V / 2.43%)
        drop_heavy = self.elec_calc.calculate_voltage_drop_by_awg(
            source_voltage=24.0,
            current_a=15.0,
            one_way_length_meters=15.0,
            wire_awg="6",
        )
        self.assertTrue(drop_heavy["is_critical_acceptable"])
        self.assertLess(drop_heavy["percentage_drop"], 3.0)

    def test_combo_04_knowledge_search_across_zim_and_khan(self):
        """Combo: Unified knowledge search queries both ZIM articles and Khan curriculum."""
        results = self.runtime.handle_knowledge_search("electric power circuit")
        self.assertIn("ok", results)
        self.assertTrue(results["ok"])
        self.assertIn("zim_results", results)
        self.assertIn("khan_results", results)
        self.assertIn("total", results)

    def test_combo_05_memory_vault_interaction_storage_and_fts5_retrieval(self):
        """Combo: Interaction saved to Memory Vault is indexed and retrieved via FTS5."""
        from emyrge.memory.memory_vault import MemoryVault

        with tempfile.TemporaryDirectory() as td:
            vault = MemoryVault(Path(td))
            entry_id = vault.save_interaction(
                query="How to purify muddy floodwater?",
                answer="Add 4 drops of bleach per liter (20 drops for 5L). Wait 60 minutes. [Source: Safe Water]",
                citations=["[Source: Safe Water]"],
                tags=["water", "emergency", "flood"],
            )
            self.assertGreater(entry_id, 0)

            # Search by keyword
            search_res = vault.search("muddy floodwater")
            self.assertGreater(len(search_res["entries"]), 0)
            self.assertEqual(search_res["entries"][0]["id"], entry_id)
            self.assertIn("bleach", search_res["entries"][0]["answer"])

    def test_combo_06_distillation_pipeline_synthesizes_master_notes(self):
        """Combo: Memory Vault distillation-on-dock pipeline promotes interactions to master notes."""
        from emyrge.memory.memory_vault import MemoryVault

        with tempfile.TemporaryDirectory() as td:
            vault = MemoryVault(Path(td))
            # Seed 3 pending interactions
            for i in range(3):
                vault.save_interaction(
                    query=f"Field clinic triage note {i}",
                    answer=f"Administer ORS 75 mL/kg over 4 hours. Patient {i} recovering.",
                    citations=["[Source: WHO ORS Manual]"],
                    tags=["clinical", "triage"],
                )

            distilled = vault.run_distillation_on_dock()
            self.assertIn("upgraded_count", distilled)
            self.assertEqual(distilled["upgraded_count"], 3)
            self.assertEqual(vault.pending_count(), 0)
            self.assertGreaterEqual(len(distilled["master_notes"]), 1)


if __name__ == "__main__":
    unittest.main()
