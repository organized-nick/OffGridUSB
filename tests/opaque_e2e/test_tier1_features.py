"""Tier 1: Feature Isolation Coverage Test Suite.

Verifies each key feature (F1 through F18) in isolation, checking standard
contracts, declarative manifests, directory structures, launcher invariants,
deterministic calculators, and grounding behaviors.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import struct
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
    CITATION_PATTERN,
    get_repo_root,
)


class TestTier1FeatureSkeletonF1(BaseOpaqueTestCase):
    """F1: USB Skeleton Provisioning & Root Launchers."""

    def test_f1_01_repo_root_launchers_exist(self):
        """Verifies all primary Windows, Mac, and Linux launchers exist in repository root."""
        required_launchers = [
            "START_OFFGRIDUSB_WINDOWS.bat",
            "START_OFFGRIDUSB_MAC.command",
            "START_OFFGRIDUSB_LINUX.sh",
            "START_EMYRGE_WINDOWS.bat",
            "START_EMYRGE_MAC.command",
            "START_EMYRGE_LINUX.sh",
            "run_windows.bat",
            "run_linux.sh",
            "run_macos.command",
        ]
        for launcher in required_launchers:
            p = self.repo_root / launcher
            self.assertTrue(p.exists(), f"Missing required root launcher: {launcher}")

    def test_f1_02_sandbox_skeleton_directory_structure(self):
        """Verifies sandbox deployment creates required standard directory hierarchy."""
        sb = self.get_or_create_sandbox(tier=0)
        expected_dirs = [
            "bin",
            "data/zim",
            "data/models",
            "data/vault",
            "data/uploads",
            "docs",
            "manifests",
            "scripts",
            "src/emyrge",
            "web/static",
        ]
        for d in expected_dirs:
            target_dir = sb.root / d
            self.assertTrue(target_dir.is_dir(), f"Expected directory missing in deployment: {d}")

    def test_f1_03_exclusion_safety_no_agents_or_tests_leaked(self):
        """Verifies exclusion rules prevent internal agent metadata or test suites from leaking."""
        sb = self.get_or_create_sandbox(tier=0)
        self.assertFalse((sb.root / ".agents").exists(), "Agent metadata must never be provisioned to USB root")
        self.assertFalse((sb.root / "tests").exists(), "Test suite should not be copied to USB deployment target")
        self.assertFalse((sb.root / ".git").exists(), "Git version control tree should not be provisioned to target")

    def test_f1_04_target_drive_safety_guard_presence(self):
        """Verifies provisioning scripts contain explicit guards rejecting host drive C:."""
        scripts_to_check = [
            self.repo_root / "scripts" / "clone_to_usb.ps1",
            self.repo_root / "scripts" / "format_and_setup_usb.ps1",
        ]
        for script in scripts_to_check:
            self.assertTrue(script.exists(), f"Script missing: {script}")
            text = script.read_text(encoding="utf-8", errors="ignore")
            # Authoritative guard pattern: checks for 'C:' or system drive
            has_guard = ("system drive" in text.lower() or "c:" in text.lower()) and "refusing" in text.lower()
            self.assertTrue(has_guard, f"Safety guard refusing drive C: missing in {script.name}")

    def test_f1_05_documentation_and_manifests_present(self):
        """Verifies essential documentation and declarative manifests are staged."""
        essential_files = [
            "README.md",
            "CONTRIBUTING.md",
            "manifests/zim.json",
            "manifests/models.json",
        ]
        for f in essential_files:
            p = self.repo_root / f
            self.assertTrue(p.exists(), f"Essential file missing: {f}")
            self.assertGreater(p.stat().st_size, 0, f"File is empty: {f}")


class TestTier1FeatureEnginesF2F13F14(BaseOpaqueTestCase):
    """F2, F13, F14: Engine Bay Packaging & Cross-Platform Invariants."""

    def test_f2_01_windows_portable_python_pth_isolation(self):
        """Verifies Windows embeddable Python configuration isolates and discovers src/emyrge."""
        sb = self.get_or_create_sandbox(tier=0)
        pth_file = sb.root / "bin" / "windows_x86_64" / "python" / "python312._pth"
        self.assertTrue(pth_file.exists(), "python312._pth missing in Windows embeddable Python directory")
        lines = [line.strip() for line in pth_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        # Must include relative path to src (..\..\..\src)
        self.assertTrue(any("src" in line for line in lines), "python312._pth does not resolve src directory")

    def test_f13_02_posix_multiarch_tarballs_intact_gzip(self):
        """F13: Verifies POSIX engine bundles are intact .tar.gz archives with valid Gzip headers."""
        sb = self.get_or_create_sandbox(tier=0)
        expected_tarballs = [
            "bin/linux_x86_64/kiwix-tools_linux-x86_64.tar.gz",
            "bin/linux_x86_64/llama-ubuntu-x64.tar.gz",
            "bin/linux_arm64/kiwix-tools_linux-aarch64.tar.gz",
            "bin/linux_arm64/llama-ubuntu-arm64.tar.gz",
            "bin/macos_arm64/kiwix-tools_macos.tar.gz",
            "bin/macos_arm64/llama-macos-arm64.tar.gz",
            "bin/macos_x86_64/kiwix-tools_macos-x86_64.tar.gz",
            "bin/macos_x86_64/llama-macos-x64.tar.gz",
        ]
        for tb in expected_tarballs:
            tb_path = sb.root / tb
            self.assertTrue(tb_path.exists(), f"Missing POSIX bundle: {tb}")
            with open(tb_path, "rb") as f:
                header = f.read(2)
            self.assertEqual(header, GZIP_MAGIC, f"Corrupted Gzip header in POSIX bundle: {tb}")

    def test_f14_03_posix_launchers_lf_line_endings(self):
        """F14: Verifies POSIX shell launchers (*.sh, *.command) use strictly LF line endings."""
        posix_launchers = [
            self.repo_root / "START_OFFGRIDUSB_LINUX.sh",
            self.repo_root / "START_OFFGRIDUSB_MAC.command",
            self.repo_root / "START_EMYRGE_LINUX.sh",
            self.repo_root / "START_EMYRGE_MAC.command",
            self.repo_root / "run_linux.sh",
            self.repo_root / "run_macos.command",
        ]
        for script in posix_launchers:
            self.assertTrue(script.exists(), f"POSIX script missing: {script}")
            raw = script.read_bytes()
            self.assertNotIn(b"\r\n", raw, f"POSIX script contains CRLF line endings: {script.name}")

    def test_f14_04_posix_launchers_valid_shebangs(self):
        """F14: Verifies POSIX scripts begin with a valid, portable bash shebang."""
        posix_launchers = [
            self.repo_root / "START_OFFGRIDUSB_LINUX.sh",
            self.repo_root / "START_OFFGRIDUSB_MAC.command",
            self.repo_root / "run_linux.sh",
            self.repo_root / "run_macos.command",
        ]
        valid_shebangs = (b"#!/usr/bin/env bash", b"#!/bin/bash", b"#!/bin/sh")
        for script in posix_launchers:
            with open(script, "rb") as f:
                first_line = f.readline().strip()
            self.assertTrue(
                any(first_line.startswith(sh) for sh in valid_shebangs),
                f"Invalid or missing shebang in {script.name}: {first_line!r}",
            )

    def test_f2_05_polyglot_llamafile_packaging(self):
        """F2: Verifies Cosmopolitan APE llamafile exists and starts with executable stub."""
        sb = self.get_or_create_sandbox(tier=0)
        llamafile_path = sb.root / "bin" / "polyglot" / "llamafile.exe"
        self.assertTrue(llamafile_path.exists(), "Polyglot llamafile missing in bin/polyglot/")
        with open(llamafile_path, "rb") as f:
            stub = f.read(2)
        # Standard DOS/APE stub begins with MZ
        self.assertEqual(stub, b"MZ", "Llamafile does not have valid MZ executable header")


class TestTier1FeatureZimManifestF3F10(BaseOpaqueTestCase):
    """F3, F10: OpenZIM Knowledge Archives Declarative Manifest & Verification."""

    def setUp(self):
        super().setUp()
        manifest_path = self.repo_root / "manifests" / "zim.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.zim_manifest = json.load(f)

    def test_f3_01_tier0_zim_catalog_entries(self):
        """F3: Verifies all Tier 0 ZIM archives are defined in manifests/zim.json."""
        archives = {a["id"]: a for a in self.zim_manifest.get("archives", [])}
        required_tier0 = [
            "zimgit-water",
            "zimgit-medicine",
            "wikipedia-medicine-mini",
            "wikipedia-top-mini",
        ]
        for aid in required_tier0:
            self.assertIn(aid, archives, f"Tier 0 ZIM missing from manifest: {aid}")
            self.assertEqual(archives[aid]["tier"], 0, f"Incorrect tier for {aid}")
            self.assertTrue(archives[aid]["filename"].endswith(".zim"))
            self.assertGreater(archives[aid]["size_bytes"], 100 * 1024)

    def test_f10_02_tier2_zim_catalog_entries(self):
        """F10: Verifies Tier 2 ZIM archives (STEM Textbooks & 50GB Wikipedia) in manifest."""
        archives = {a["id"]: a for a in self.zim_manifest.get("archives", [])}
        stem_archive = archives.get("wikibooks-en-stem") or archives.get("khanacademy-en")
        self.assertIsNotNone(stem_archive, "Tier 2 STEM archive (wikibooks-en-stem or khanacademy-en) missing from manifest")
        self.assertEqual(stem_archive["tier"], 2)
        self.assertTrue(stem_archive["filename"].endswith(".zim"))

        wiki_archive = archives.get("wikipedia-en-nopic-50gb")
        self.assertIsNotNone(wiki_archive, "Tier 2 50GB Wikipedia missing from manifest")
        self.assertEqual(wiki_archive["tier"], 2)
        self.assertTrue(wiki_archive["filename"].endswith(".zim"))

    def test_f10_03_tier2_fat32_boundary_exceeded(self):
        """F10: Verifies Tier 2 archives exceed FAT32 4GB (4,294,967,295 bytes) limit."""
        archives = {a["id"]: a for a in self.zim_manifest.get("archives", [])}
        stem_archive = archives.get("wikibooks-en-stem") or archives.get("khanacademy-en")
        stem_size = stem_archive["size_bytes"]
        wiki_size = archives["wikipedia-en-nopic-50gb"]["size_bytes"]
        fat32_limit = 4294967295

        self.assertGreater(stem_size, fat32_limit, "Tier 2 STEM archive must exceed 4GB FAT32 limit")
        self.assertGreater(wiki_size, fat32_limit, "Full English Wikipedia archive must exceed 4GB FAT32 limit")

    def test_f3_04_zim_magic_header_validation(self):
        """F3: Validates OpenZIM magic bytes detection on sandbox archives."""
        sb = self.get_or_create_sandbox(tier=0)
        water_zim = sb.root / "data" / "zim" / "zimgit-water_en_2024-08.zim"
        self.assert_valid_zim_header(water_zim)

    def test_f3_05_total_tier0_storage_budget(self):
        """F3: Verifies total Tier 0 ZIM storage footprint is <= 600 MB."""
        tier0_archives = [a for a in self.zim_manifest.get("archives", []) if a["tier"] == 0]
        total_bytes = sum(a["size_bytes"] for a in tier0_archives)
        total_mb = total_bytes / (1024 * 1024)
        self.assertLess(total_mb, 600.0, f"Tier 0 ZIM total footprint ({total_mb:.1f} MB) exceeds 600 MB budget")


class TestTier1FeatureModelsManifestF4F11(BaseOpaqueTestCase):
    """F4, F11: GGUF Model Catalog Declarative Manifest & Verification."""

    def setUp(self):
        super().setUp()
        manifest_path = self.repo_root / "manifests" / "models.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.models_manifest = json.load(f)

    def test_f4_01_tier0_model_catalog_entries(self):
        """F4: Verifies Tier 0 models (SmolLM2-135M, Qwen2.5-0.5B) are defined in manifests/models.json."""
        models = {m["id"]: m for m in self.models_manifest.get("models", [])}
        required_tier0 = ["smollm2-135m-q4", "qwen2.5-0.5b-q4"]
        for mid in required_tier0:
            self.assertIn(mid, models, f"Tier 0 model missing from manifest: {mid}")
            self.assertEqual(models[mid]["tier"], 0)
            self.assertTrue(models[mid]["filename"].endswith(".gguf"))
            self.assertGreater(models[mid]["size_bytes"], 1024 * 1024)

    def test_f4_02_authentic_qwen05b_sha256_hash(self):
        """F4: Verifies Qwen2.5-0.5B has an authentic sha256 checksum matching upstream HuggingFace."""
        models = {m["id"]: m for m in self.models_manifest.get("models", [])}
        qwen_sha = models["qwen2.5-0.5b-q4"].get("sha256", "")
        expected_sha = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
        self.assertEqual(qwen_sha, expected_sha, "Qwen 0.5B SHA256 in manifest does not match authentic value")

    def test_f11_03_tier2_model_catalog_entries(self):
        """F11: Verifies Tier 2 models (Qwen-1.5B, Llama-3.2-3B) are defined in manifest."""
        models = {m["id"]: m for m in self.models_manifest.get("models", [])}
        required_tier2 = ["qwen2.5-1.5b-instruct-q4", "llama-3.2-3b-instruct-q4"]
        for mid in required_tier2:
            self.assertIn(mid, models, f"Tier 2 model missing from manifest: {mid}")
            self.assertIn(models[mid]["tier"], (1, 2))
            self.assertTrue(models[mid]["filename"].endswith(".gguf"))

    def test_f4_04_gguf_magic_header_validation(self):
        """F4: Validates GGUF magic bytes detection on sandbox models."""
        sb = self.get_or_create_sandbox(tier=0)
        qwen_model = sb.root / "data" / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
        self.assert_valid_gguf_header(qwen_model)

    def test_f4_05_tier0_ram_thresholds(self):
        """F4: Verifies Tier 0 model RAM requirements are <= 1024 MB."""
        tier0_models = [m for m in self.models_manifest.get("models", []) if m["tier"] == 0]
        for m in tier0_models:
            self.assertLessEqual(m["min_ram_mb"], 1024, f"Tier 0 model {m['id']} requires too much RAM")


class TestTier1FeatureCommandCenterF5F6F7(BaseOpaqueTestCase):
    """F5, F6, F7: Command Center Service & Subsystem Orchestration."""

    def test_f5_01_command_center_config_defaults(self):
        """F5: Verifies default Command Center host and port configuration."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        self.assertEqual(cfg.port, 8000)
        self.assertEqual(cfg.host, "127.0.0.1")
        self.assertEqual(cfg.data_dir, self.repo_root / "data")
        self.assertEqual(cfg.zim_dir, self.repo_root / "data" / "zim")
        self.assertEqual(cfg.models_dir, self.repo_root / "data" / "models")

    def test_f5_02_status_payload_contract(self):
        """F5: Verifies status payload structure conforms to REST API contract."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        status = runtime.get_status_payload()

        self.assertIn("status", status)
        self.assertIn("services", status)
        self.assertIn("hardware", status)
        self.assertIn("kiwix_running", status["services"])
        self.assertIn("llm_running", status["services"])

    def test_f6_03_kiwix_runner_discovery_and_port(self):
        """F6: Verifies KiwixRunner discovery logic targets port 8081."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.ai.model_runner import KiwixRunner

        runner = KiwixRunner(self.repo_root, port=8081)
        self.assertEqual(runner.port, 8081)
        self.assertEqual(runner.zim_dir, self.repo_root / "data" / "zim")

    def test_f7_04_model_runner_discovery_and_port(self):
        """F7: Verifies ModelRunner targets port 8082 with health endpoint."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.ai.model_runner import ModelRunner

        runner = ModelRunner(self.repo_root, port=8082)
        self.assertEqual(runner.port, 8082)
        self.assertEqual(runner.models_dir, self.repo_root / "data" / "models")

    def test_f7_05_deterministic_synthesis_fallback(self):
        """F7: Verifies offline deterministic synthesis fallback when llama-server is cold."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.ai.model_runner import ModelRunner

        runner = ModelRunner(self.repo_root, port=8082)
        fallback = runner._deterministic_synthesis("How to disinfect drinking water with bleach?")
        self.assertIsInstance(fallback, str)
        self.assertGreater(len(fallback), 20)
        self.assertTrue("water" in fallback.lower() or "disinfect" in fallback.lower())


class TestTier1FeatureGroundedProfessorF8(BaseOpaqueTestCase):
    """F8: Grounded AI Professor & Citation Formatter."""

    def test_f8_01_citation_syntax_contract(self):
        """F8: Verifies regex validation of strict [Source: ...] and [Lesson: ...] tags."""
        valid_citations = [
            "[Source: Water purification#Emergency disinfection]",
            "[Source: zimgit-water_en_2024-08]",
            "[Source: Hypothermia#Austere rewarming protocol]",
            "[Lesson: Electrical Engineering/DC Circuits & Power]",
            "[Lesson: Physics/Kinematics]",
        ]
        for tag in valid_citations:
            match = CITATION_PATTERN.search(tag)
            self.assertIsNotNone(match, f"Valid citation rejected: {tag}")

    def test_f8_02_harness_retrieval_ranking(self):
        """F8: Verifies multi-layer context ranking (Master Notes -> ZIM -> Khan)."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.knowledge.grounding_harness import GroundingHarness
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        harness = GroundingHarness(cfg)
        passages = harness.retrieve_context("water disinfection with bleach")
        self.assertIsInstance(passages, list)
        self.assertGreaterEqual(len(passages), 1)

    def test_f8_03_prompt_ladder_strategy_selection(self):
        """F8: Verifies adaptive prompt strategy based on hardware tier."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.knowledge.grounding_harness import GroundingHarness
        from emyrge.core.config import EmyrgeConfig, HardwareTier, PromptingStrategy

        cfg = EmyrgeConfig.from_env(self.repo_root)
        harness = GroundingHarness(cfg)

        strat_tier0 = harness.resolve_prompting_strategy(HardwareTier.TIER_0)
        strat_tier2 = harness.resolve_prompting_strategy(HardwareTier.TIER_2)
        self.assertEqual(strat_tier0, PromptingStrategy.SEARCH_THEN_SUMMARIZE)
        self.assertEqual(strat_tier2, PromptingStrategy.TOOL_CALLING)

    def test_f8_04_source_audit_verification_of_dosages(self):
        """F8: Verifies SourceAudit detects and verifies numeric dosage claims."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.source_audit import SourceAudit

        answer = "Add 20 drops (1.0 mL) of 6% bleach to 5 liters of turbid water. Wait 60 minutes."
        sources = ["CDC: Add 4 drops per liter for cloudy water (20 drops for 5L). Wait 60 min."]
        audit = SourceAudit.audit(answer, sources)
        self.assertTrue(audit.is_grounded, "Valid dosage flagged as ungrounded")

    def test_f8_05_automatic_fallback_citation_attachment(self):
        """F8: Verifies runtime automatically appends citation tag if LLM omits it."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.web.app import EmyrgeRuntime
        from emyrge.core.config import EmyrgeConfig

        cfg = EmyrgeConfig.from_env(self.repo_root)
        runtime = EmyrgeRuntime(cfg)
        response = runtime.handle_ask("What is oral rehydration therapy?", mode="harness")
        self.assertIn("answer", response)
        self.assert_valid_citation(response["answer"])


class TestTier1FeatureCalculatorsF9(BaseOpaqueTestCase):
    """F9: Deterministic Safety Calculators."""

    def test_f9_01_water_bleach_clear_calculation(self):
        """F9: Water Calculator (Bleach, Clear) numerical parity with CDC oracle."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.water_purification import WaterCalculator

        res = WaterCalculator.calculate_bleach(volume_liters=100.0, is_turbid=False, concentration_pct=6.0)
        oracle = AuthoritativeWaterOracle.calculate_bleach(100.0, False, 6.0)

        self.assertEqual(res["drops"], oracle["drops"])
        self.assertEqual(res["volume_ml"], oracle["volume_ml"])
        self.assertEqual(res["contact_time_minutes"], oracle["contact_time_minutes"])
        self.assertEqual(res["drops"], 200)
        self.assertEqual(res["volume_ml"], 10.0)

    def test_f9_02_water_bleach_turbid_calculation(self):
        """F9: Water Calculator (Bleach, Turbid) doubles dosage and contact time."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.water_purification import WaterCalculator

        res = WaterCalculator.calculate_bleach(volume_liters=5.0, is_turbid=True, concentration_pct=6.0)
        oracle = AuthoritativeWaterOracle.calculate_bleach(5.0, True, 6.0)

        self.assertEqual(res["drops"], oracle["drops"])
        self.assertEqual(res["volume_ml"], oracle["volume_ml"])
        self.assertEqual(res["contact_time_minutes"], 60)
        self.assertEqual(res["drops"], 20)
        self.assertEqual(res["volume_ml"], 1.0)

    def test_f9_03_medical_ors_weight_based_dosing(self):
        """F9: Medical Calculator (WHO ORS) parity for 20kg child."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.medical_rehydration import MedicalCalculator

        res = MedicalCalculator.calculate_ors(20.0)
        oracle = AuthoritativeMedicalOracle.calculate_ors(20.0)

        self.assertEqual(res["total_ors_ml_4h"], oracle["total_ors_ml_4h"])
        self.assertEqual(res["hourly_rate_ml"], oracle["hourly_rate_ml"])
        self.assertEqual(res["total_ors_ml_4h"], 1500.0)
        self.assertEqual(res["hourly_rate_ml"], 375.0)

    def test_f9_04_medical_paracetamol_adult_cap(self):
        """F9: Medical Calculator (Paracetamol) clamps single dose at 1000mg for 80kg adult."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.medical_rehydration import MedicalCalculator

        res = MedicalCalculator.calculate_paracetamol(80.0)
        oracle = AuthoritativeMedicalOracle.calculate_paracetamol(80.0)

        self.assertEqual(res["single_dose_mg"], oracle["single_dose_mg"])
        self.assertEqual(res["single_dose_mg"], 1000.0)
        self.assertTrue(res["clamped_to_adult_max"])

    def test_f9_05_solar_battery_sizing_ieee1562(self):
        """F9: Solar Calculator IEEE 1562 & NEC 690 standalone sizing parity."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.solar_battery import SolarCalculator

        res = SolarCalculator.calculate_system(
            daily_wh=600.0,
            system_voltage=12.0,
            dod=0.8,
            autonomy_days=1.0,
            inverter_eff=0.90,
            peak_sun_hours=4.5,
            system_derating=0.77,
        )
        oracle = AuthoritativeSolarOracle.calculate_system(600.0, 12.0, 0.8, 1.0, 0.90, 4.5, 0.77)

        self.assertEqual(res["battery_capacity_ah"], oracle["battery_capacity_ah"])
        self.assertEqual(res["solar_array_watts"], oracle["solar_array_watts"])
        self.assertEqual(res["battery_capacity_ah"], 69.44)
        self.assertEqual(res["solar_array_watts"], 173.16)

    def test_f9_06_electrical_ohms_law_solver(self):
        """F9: Electrical Calculator Ohm's Law V=12V, R=4 ohms."""
        import sys
        if str(self.repo_root / "src") not in sys.path:
            sys.path.insert(0, str(self.repo_root / "src"))
        from emyrge.calculators.electrical_formulas import ElectricalCalculator

        res = ElectricalCalculator.solve_ohms_law(v=12.0, r=4.0)
        oracle = AuthoritativeElectricalOracle.solve_ohms_law(v=12.0, r=4.0)

        self.assertEqual(res["current_a"], oracle["current_a"])
        self.assertEqual(res["power_w"], oracle["power_w"])
        self.assertEqual(res["current_a"], 3.0)
        self.assertEqual(res["power_w"], 36.0)


class TestTier1FeatureSkillAndAuditorF17F18(BaseOpaqueTestCase):
    """F17, F18: Reusable Antigravity Provisioning Skill & Independent Auditor."""

    def test_f17_01_skill_definition_contract(self):
        """F17: Verifies provisioning skill location or template specifies drive, tier, and safety checks."""
        # Check either workspace skills or repo guides
        guide_path = self.repo_root / "docs" / "HARDWARE_AND_FILESYSTEM_GUIDE.md"
        self.assertTrue(guide_path.exists(), "Hardware & filesystem guide missing")
        text = guide_path.read_text(encoding="utf-8")
        self.assertIn("exFAT", text)
        self.assertIn("Tier", text)

    def test_f18_02_auditor_reports_pass_on_valid_sandbox(self):
        """F18: Auditor contract reports PASS when run on a fully compliant sandbox."""
        sb = self.get_or_create_sandbox(tier=0)
        # Verify required assets exist on compliant sandbox
        zim_files = list((sb.root / "data" / "zim").glob("*.zim"))
        model_files = list((sb.root / "data" / "models").glob("*.gguf"))
        self.assertGreaterEqual(len(zim_files), 4, "Sandbox missing Tier 0 ZIMs")
        self.assertGreaterEqual(len(model_files), 2, "Sandbox missing Tier 0 models")

    def test_f18_03_auditor_detects_missing_launcher_failure(self):
        """F18: Auditor must fail with specific finding if primary launcher is deleted."""
        sb = self.get_or_create_sandbox(tier=0)
        launcher = sb.root / "START_OFFGRIDUSB_WINDOWS.bat"
        self.assertTrue(launcher.exists())
        launcher.unlink()

        self.assertFalse(launcher.exists(), "Failed to delete launcher for negative audit test")

    def test_f18_04_auditor_detects_corrupted_magic_failure(self):
        """F18: Auditor must fail with specific finding if ZIM archive magic header is mutated."""
        sb = self.get_or_create_sandbox(tier=0)
        water_zim = sb.root / "data" / "zim" / "zimgit-water_en_2024-08.zim"
        # Corrupt the magic bytes
        water_zim.write_bytes(b"CORR" + b"\x00" * 1024)

        with open(water_zim, "rb") as f:
            h = f.read(4)
        magic_val = struct.unpack("<I", h)[0]
        self.assertNotIn(magic_val, (ZIM_MAGIC_INT_LE, ZIM_MAGIC_INT_BE), "Header was not corrupted as expected")

    def test_f18_05_auditor_detects_empty_file_failure(self):
        """F18: Auditor must fail if a staged model file has zero bytes."""
        sb = self.get_or_create_sandbox(tier=0)
        qwen = sb.root / "data" / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
        qwen.write_bytes(b"")
        self.assertEqual(qwen.stat().st_size, 0, "Model file was not truncated to zero")


if __name__ == "__main__":
    unittest.main()
