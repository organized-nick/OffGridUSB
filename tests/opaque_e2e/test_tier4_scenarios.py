"""Tier 4: Real-World Application Scenarios Test Suite.

End-to-end integration scenarios simulating authentic off-grid emergency operations:
1. Hurricane / Flood Disaster Community Water Disinfection (500L Tank)
2. Remote Wilderness Pediatric Diarrheal Outbreak Triage (12.5 kg Toddler)
3. Off-Grid Field Hospital Solar & Battery Microgrid Sizing (1800 Wh/day)
4. Austere Radio Mesh Telemetry Triage (LoRa / Meshtastic Packet <=200B)
5. Offline Disaster School STEM Lesson & Exercise Evaluation
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


class TestTier4RealWorldScenarios(BaseOpaqueTestCase):
    """End-to-end real world offline survival and disaster response workflows."""

    def setUp(self):
        super().setUp()
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig
        from emyrge.calculators.water_purification import WaterCalculator
        from emyrge.calculators.medical_rehydration import MedicalCalculator
        from emyrge.calculators.solar_battery import SolarCalculator
        from emyrge.calculators.electrical_formulas import ElectricalCalculator
        from emyrge.memory.memory_vault import MemoryVault

        self.cfg = EmyrgeConfig.from_env(self.repo_root)
        self.runtime = EmyrgeRuntime(self.cfg)
        self.water_calc = WaterCalculator
        self.med_calc = MedicalCalculator
        self.solar_calc = SolarCalculator
        self.elec_calc = ElectricalCalculator

    def test_scenario_01_hurricane_disaster_water_disinfection(self):
        """Scenario 1: Hurricane / Flood Disaster Community Water Disinfection.

        An emergency responder needs to disinfect a 500-liter communal container of
        turbid river water using 6% household bleach.
        """
        # Step 1: Run deterministic calculation
        params = {"volume_liters": 500.0, "is_turbid": True, "method": "bleach", "concentration_pct": 6.0}
        result = self.water_calc.calculate(params)

        # Expected: 4 drops/L * 500 = 2000 drops, 100.0 mL, 60 minutes contact time
        self.assertEqual(result["drops"], 2000)
        self.assertEqual(result["volume_ml"], 100.0)
        self.assertEqual(result["contact_time_minutes"], 60)
        self.assertEqual(result["chlorine_ppm_target"], 4.0)

        # Step 2: Generate radio mesh summary (must fit in <= 200B LoRa packet)
        mesh_summary = self.water_calc.format_mesh_summary(result)
        self.assertLessEqual(len(mesh_summary.encode("utf-8")), 200)
        self.assertIn("2000 drops", mesh_summary)
        self.assertIn("100.0 mL", mesh_summary)
        self.assertIn("60 min", mesh_summary)

        # Step 3: Query Grounded Professor for field instructions
        query = "How do we treat 500 liters of turbid floodwater using standard bleach?"
        response = self.runtime.handle_ask(query, mode="harness")
        self.assertIn("answer", response)
        self.assert_valid_citation(response["answer"])

        # Step 4: Persist log entry into field Memory Vault
        with tempfile.TemporaryDirectory() as td:
            vault = self.runtime.memory_vault
            entry_id = vault.save_interaction(
                query=query,
                answer=response["answer"],
                citations=[c["raw_tag"] if isinstance(c, dict) else c.raw_tag for c in response.get("citations", [])],
                tags=["water", "hurricane_response", "500L"],
            )
            self.assertGreater(entry_id, 0)

    def test_scenario_02_remote_pediatric_diarrheal_triage(self):
        """Scenario 2: Remote Wilderness Pediatric Diarrheal Outbreak Triage.

        A 12.5 kg toddler presents with mild-to-moderate dehydration from gastroenteritis
        and a high fever in an austere offline clinic.
        """
        weight_kg = 12.5

        # Step 1: WHO ORS Rehydration Protocol
        ors_res = self.med_calc.calculate_ors(weight_kg)
        # 12.5 * 75 = 937.5 mL over 4h, hourly rate = 234.4 mL/h
        self.assertEqual(ors_res["total_ors_ml_4h"], 937.5)
        self.assertEqual(ors_res["hourly_rate_ml"], 234.4)
        self.assertEqual(ors_res["reassessment_interval_hours"], 4)

        # Step 2: Paracetamol Antipyretic Dosing
        para_res = self.med_calc.calculate_paracetamol(weight_kg)
        # 12.5 * 15 = 187.5 mg single dose, max daily = 12.5 * 60 = 750.0 mg
        self.assertEqual(para_res["single_dose_mg"], 187.5)
        self.assertEqual(para_res["max_daily_mg"], 750.0)
        self.assertFalse(para_res["clamped_to_adult_max"])

        # Step 3: Mesh Radio Format for Village Health Workers
        ors_mesh = self.med_calc.format_mesh_summary(ors_res)
        para_mesh = self.med_calc.format_mesh_summary(para_res)
        self.assertLessEqual(len(ors_mesh.encode("utf-8")), 200)
        self.assertLessEqual(len(para_mesh.encode("utf-8")), 200)
        self.assertIn("937.5 mL over 4h", ors_mesh)
        self.assertIn("187.5 mg", para_mesh)

        # Step 4: Verify AI Guidance
        query = "What is the oral rehydration solution amount for a 12.5 kg child with diarrhea?"
        response = self.runtime.handle_ask(query, mode="harness")
        self.assert_valid_citation(response["answer"])

    def test_scenario_03_field_hospital_solar_microgrid_sizing(self):
        """Scenario 3: Off-Grid Field Hospital Solar & Battery Microgrid Sizing.

        A disaster field hospital requires standalone power for vaccine refrigeration,
        lighting, and telemetry monitors (1800 Wh/day total demand).
        """
        # Step 1: IEEE 1562 Battery & NEC 690 Solar Array Sizing
        daily_wh = 1800.0
        system_voltage = 24.0  # 24V bus
        dod = 0.80  # 80% usable depth of discharge (LiFePO4)
        autonomy_days = 2.0  # 2 days reserve without sun
        inverter_eff = 0.90
        peak_sun_hours = 4.0
        system_derating = 0.77

        sizing = self.solar_calc.calculate_system(
            daily_wh=daily_wh,
            system_voltage=system_voltage,
            dod=dod,
            autonomy_days=autonomy_days,
            inverter_eff=inverter_eff,
            peak_sun_hours=peak_sun_hours,
            system_derating=system_derating,
        )

        # Battery capacity: (1800 * 2) / (24 * 0.8 * 0.9) = 208.33 Ah
        # Solar array: 1800 / (4.0 * 0.77) = 584.42 W
        self.assertEqual(sizing["battery_capacity_ah"], 208.33)
        self.assertEqual(sizing["solar_array_watts"], 584.42)

        # Step 2: Cable Run DC Voltage Drop Verification (10m one-way, 25A current)
        array_current_a = round(sizing["solar_array_watts"] / system_voltage, 1)  # ~24.4 A
        drop_awg8 = self.elec_calc.calculate_voltage_drop_by_awg(
            source_voltage=system_voltage,
            current_a=array_current_a,
            one_way_length_meters=10.0,
            wire_awg="8",  # 2.061 ohm/km
        )
        # Loop resistance: 2 * 0.010 km * 2.061 = 0.04122 ohms
        # Drop = 24.4 * 0.04122 = 1.01 V (4.19% of 24V) -> acceptable for standard (<5%), but not critical (<3%)
        self.assertTrue(drop_awg8["is_standard_acceptable"])
        self.assertFalse(drop_awg8["is_critical_acceptable"])

        # Upgrade to AWG 4 (0.815 ohm/km) -> loop = 2 * 0.010 * 0.815 = 0.0163 ohms -> drop = 0.40 V (1.66%)
        drop_awg4 = self.elec_calc.calculate_voltage_drop_by_awg(
            source_voltage=system_voltage,
            current_a=array_current_a,
            one_way_length_meters=10.0,
            wire_awg="4",
        )
        self.assertTrue(drop_awg4["is_critical_acceptable"])
        self.assertLess(drop_awg4["percentage_drop"], 3.0)

    def test_scenario_04_austere_radio_mesh_command_triage(self):
        """Scenario 4: Austere Radio Mesh Telemetry Triage (LoRa / Meshtastic Packet).

        A field responder sends a command via LoRa packet: `@calc water volume_liters=20 is_turbid=true`.
        """
        command_payload = "@calc water volume_liters=20 is_turbid=true"
        mesh_response = self.runtime.handle_mesh_command(command_payload)

        self.assertIn("ok", mesh_response)
        self.assertTrue(mesh_response["ok"])
        self.assertIn("message", mesh_response)

        # Output message must fit within strict 200-byte LoRa packet limit
        msg_bytes = mesh_response["message"].encode("utf-8")
        self.assertLessEqual(len(msg_bytes), 200)
        self.assertTrue("Bleach: 80 drops" in mesh_response["message"] or "80" in mesh_response["message"])
        self.assertTrue("60 min" in mesh_response["message"] or "60" in mesh_response["message"])

    def test_scenario_05_offline_disaster_school_stem_curriculum(self):
        """Scenario 5: Offline Disaster School STEM Lesson & Exercise Evaluation.

        Stranded students in an austere schoolhouse access the Khan Academy STEM index
        and evaluate DC electric circuit exercises.
        """
        curriculum = self.runtime.khan_curriculum
        subjects = curriculum.get_subjects()
        self.assertGreater(len(subjects), 0)

        topics = curriculum.get_topics()
        self.assertGreater(len(topics), 0)

        # Student queries explanation of Ohm's law
        query = "Explain Ohm's law and how to calculate DC circuit power"
        response = self.runtime.handle_ask(query, mode="harness")
        self.assertIn("answer", response)
        self.assert_valid_citation(response["answer"])

        # Student evaluates exercise answer
        lessons = list(curriculum._lessons.values())
        if lessons and lessons[0].exercises:
            ex = lessons[0].exercises[0]
            eval_res = curriculum.evaluate_exercise(lessons[0].lesson_id, ex.id, ex.answer)
            self.assertTrue(eval_res.is_correct)


if __name__ == "__main__":
    unittest.main()
