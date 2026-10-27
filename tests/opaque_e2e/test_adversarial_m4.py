"""Adversarial Verification Suite for Milestone 4: Platform Probing, Installer Safety & Download Resilience.

Authored by teamwork_preview_challenger (challenger_m4_2).
Role: Adversarial Empirical Verifier for Milestone 4.

Probing:
1. `src/emyrge/ai/model_runner.py`:
   - `probe_usb_platforms()` detects POSIX `.tar.gz` archives when loose binaries are absent.
   - Empty/truncated archives (<= 1024 bytes) are rejected.
   - `discover_model()` dynamically prioritizes Tier 2 (Llama-3.2-3B) over Tier 0 models.
   - `discover_model()` obeys `EMYRGE_TIER="0"` and explicit `OFFGRIDUSB_MODEL` overrides.
   - Non-GGUF and truncated files (< 5 MB) are discarded.
2. `scripts/gentle_usb_installer.py`:
   - Safety guards refuse to target host system drive (`C:`, `C:\`, `c:/`, `c`) or root (`/`).
   - Safe target (`D:/`) is permitted.
   - All cross-platform launchers (`START_OFFGRIDUSB_*`) are present in `root_files`.
   - All items in `root_files` exist in the repo source root.
3. Download resilience (`download_internet_in_a_box.ps1` and `fetch_assets.py`):
   - `.part` file preservation: confirm `.part` is preserved on transient exit codes (18, 28, 56).
   - Only code 33 (HTTP 416 range error) unlinks `.part`.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Ensure src/ and repo root are in sys.path
current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parent.parent
src_dir = repo_root / "src"
for p in (str(src_dir), str(repo_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from emyrge.ai.model_runner import probe_usb_platforms, ModelRunner
from emyrge.core.config import EmyrgeConfig


class TestAdversarialPlatformProbing(unittest.TestCase):
    """Empirical verification of probe_usb_platforms() against tarball structures and edge cases."""

    def test_probe_detects_posix_tarball_only_structures(self):
        """POSIX platforms MUST report ready: True when only .tar.gz archives exist (no uncompressed binaries)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)

            # Create mock structure with ONLY .tar.gz files for POSIX platforms
            posix_platforms = [
                ("linux_x86_64", "llama-ubuntu-x64.tar.gz"),
                ("linux_arm64", "llama-ubuntu-arm64.tar.gz"),
                ("macos_x86_64", "llama-macos-x64.tar.gz"),
                ("macos_arm64", "llama-macos-arm64.tar.gz"),
            ]

            for plat_dir, archive_name in posix_platforms:
                target_dir = fake_root / "bin" / plat_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                tar_file = target_dir / archive_name
                # Write fake archive 200 KB (> 1024 bytes and large enough for round(..., 2) > 0.0)
                with open(tar_file, "wb") as f:
                    f.write(b"\x1f\x8b\x08" + b"\x00" * (200 * 1024))

            results = probe_usb_platforms(fake_root)
            results_by_id = {r["id"]: r for r in results}

            for plat_dir, archive_name in posix_platforms:
                self.assertIn(plat_dir, results_by_id, f"Missing platform {plat_dir} in probe results")
                r = results_by_id[plat_dir]
                self.assertTrue(r["ready"], f"Platform {plat_dir} should be ready with {archive_name}")
                self.assertIn(archive_name, r["path"])
                self.assertGreater(r["size_mb"], 0.0)

    def test_probe_rejects_truncated_or_empty_tarballs(self):
        """Archives <= 1024 bytes MUST NOT be marked ready."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)
            target_dir = fake_root / "bin" / "linux_x86_64"
            target_dir.mkdir(parents=True, exist_ok=True)
            empty_tar = target_dir / "llama-ubuntu-x64.tar.gz"
            empty_tar.write_bytes(b"\x00" * 512)  # 512 bytes <= 1024

            results = probe_usb_platforms(fake_root)
            results_by_id = {r["id"]: r for r in results}
            self.assertFalse(results_by_id["linux_x86_64"]["ready"])

    def test_probe_detects_live_usb_drive_posix_archives(self):
        """Live verification against D: if mounted with staged tarballs."""
        d_drive = Path("D:/")
        if (d_drive / "bin" / "linux_x86_64").is_dir():
            results = probe_usb_platforms(d_drive)
            results_by_id = {r["id"]: r for r in results}
            for plat in ("linux_x86_64", "linux_arm64", "macos_x86_64", "macos_arm64"):
                self.assertIn(plat, results_by_id)
                self.assertTrue(results_by_id[plat]["ready"], f"Live D: drive platform {plat} failed readiness")


class TestAdversarialModelPrioritization(unittest.TestCase):
    """Empirical verification of ModelRunner.discover_model() dynamic tier prioritization."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fake_root = Path(self.tmp_dir.name)
        self.models_dir = self.fake_root / "data" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        cfg = EmyrgeConfig.from_env(self.fake_root)
        self.runner = ModelRunner(cfg)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_fake_gguf(self, name: str, size_bytes: int = 10 * 1024 * 1024) -> Path:
        p = self.models_dir / name
        with open(p, "wb") as f:
            f.write(b"GGUF")
            # Write up to size_bytes using sparse seek
            f.seek(size_bytes - 1)
            f.write(b"\x00")
        return p

    def test_tier2_model_prioritized_over_tier0_models(self):
        """When Tier 0 and Tier 2 models are both staged, Llama-3.2-3B MUST be selected by default."""
        self._create_fake_gguf("smollm2-135m-instruct-q8_0.gguf", 10 * 1024 * 1024)
        self._create_fake_gguf("qwen2.5-0.5b-instruct-q4_k_m.gguf", 15 * 1024 * 1024)
        tier2_model = self._create_fake_gguf("llama-3.2-3b-instruct-q4_k_m.gguf", 25 * 1024 * 1024)

        with mock.patch.dict(os.environ, {}, clear=True):
            discovered = self.runner.discover_model()
            self.assertIsNotNone(discovered)
            self.assertEqual(discovered.resolve(), tier2_model.resolve())

    def test_tier0_environment_constraint_forces_tier0(self):
        """When EMYRGE_TIER="0" is set, Qwen 0.5B or SmolLM2 MUST be selected even if Tier 2 exists."""
        self._create_fake_gguf("smollm2-135m-instruct-q8_0.gguf", 10 * 1024 * 1024)
        qwen = self._create_fake_gguf("qwen2.5-0.5b-instruct-q4_k_m.gguf", 15 * 1024 * 1024)
        self._create_fake_gguf("llama-3.2-3b-instruct-q4_k_m.gguf", 25 * 1024 * 1024)

        with mock.patch.dict(os.environ, {"EMYRGE_TIER": "0"}, clear=True):
            discovered = self.runner.discover_model()
            self.assertIsNotNone(discovered)
            self.assertEqual(discovered.resolve(), qwen.resolve())

    def test_explicit_model_override(self):
        """OFFGRIDUSB_MODEL takes precedence over all dynamic tier prioritization."""
        smollm = self._create_fake_gguf("smollm2-135m-instruct-q8_0.gguf", 10 * 1024 * 1024)
        self._create_fake_gguf("llama-3.2-3b-instruct-q4_k_m.gguf", 25 * 1024 * 1024)

        with mock.patch.dict(os.environ, {"OFFGRIDUSB_MODEL": "smollm2"}, clear=True):
            discovered = self.runner.discover_model()
            self.assertIsNotNone(discovered)
            self.assertEqual(discovered.resolve(), smollm.resolve())

    def test_invalid_header_and_truncated_files_skipped(self):
        """Files without GGUF magic or < 5MB MUST be skipped."""
        # Bad magic
        bad_magic = self.models_dir / "fake_model.gguf"
        bad_magic.write_bytes(b"BAD!" + b"\x00" * (10 * 1024 * 1024 - 4))
        # Truncated (< 5MB)
        small_file = self.models_dir / "small.gguf"
        small_file.write_bytes(b"GGUF" + b"\x00" * 1024)

        valid = self._create_fake_gguf("qwen2.5-0.5b-instruct-q4_k_m.gguf", 10 * 1024 * 1024)

        with mock.patch.dict(os.environ, {}, clear=True):
            discovered = self.runner.discover_model()
            self.assertIsNotNone(discovered)
            self.assertEqual(discovered.resolve(), valid.resolve())


class TestAdversarialGentleInstallerSafety(unittest.TestCase):
    """Empirical verification of gentle_usb_installer.py target drive guards and launcher manifests."""

    def test_installer_refuses_system_drive_and_root(self):
        """Passing C:, C:\, c:/, or / MUST cause resolve_target_root() to exit with code 1."""
        installer_script = repo_root / "scripts" / "gentle_usb_installer.py"
        self.assertTrue(installer_script.is_file())

        sys_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/").upper()

        test_cases = [
            sys_drive,
            f"{sys_drive}\\",
            f"{sys_drive}/",
            sys_drive.lower(),
            f"{sys_drive.lower()}:",
            "/",
        ]

        import scripts.gentle_usb_installer as installer

        for bad_target in test_cases:
            with self.subTest(target=bad_target):
                with mock.patch.object(sys, "argv", ["gentle_usb_installer.py", bad_target]):
                    with self.assertRaises(SystemExit) as cm:
                        installer.resolve_target_root()
                    self.assertEqual(cm.exception.code, 1, f"Failed to reject system drive target {bad_target}")

    def test_installer_accepts_valid_removable_drive(self):
        """Targeting D: or D:/ MUST resolve without error."""
        import scripts.gentle_usb_installer as installer
        for valid_target in ("D:", "D:/", "D", "e:"):
            with self.subTest(target=valid_target):
                with mock.patch.object(sys, "argv", ["gentle_usb_installer.py", valid_target]):
                    resolved = installer.resolve_target_root()
                    self.assertNotIn("C:", str(resolved).upper())

    def test_installer_root_files_manifest_completeness(self):
        """Confirm all cross-platform launchers exist in root_files and exist in the repository root."""
        installer_code = (repo_root / "scripts" / "gentle_usb_installer.py").read_text(encoding="utf-8")

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
            "README.md",
            "CONTRIBUTING.md",
            "TEST_READY.md",
        ]

        for launcher in required_launchers:
            with self.subTest(launcher=launcher):
                self.assertIn(f'"{launcher}"', installer_code, f"{launcher} missing from root_files in installer script")
                self.assertTrue((repo_root / launcher).is_file(), f"{launcher} does not exist at repo root {repo_root}")


class TestAdversarialDownloadResilience(unittest.TestCase):
    """Empirical verification of .part preservation logic on transient curl errors."""

    def test_fetch_assets_preserves_part_file_on_transient_curl_exit_codes(self):
        """Simulated transient curl exits (18, 28, 56) MUST preserve the .part file."""
        from emyrge.assets.fetch_assets import _stream_download

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "test_download.zim"
            part = dest.with_suffix(dest.suffix + ".part")

            # Create an existing 5MB partial download
            part.write_bytes(b"ZIM\x04" + b"\x00" * (5 * 1024 * 1024 - 4))
            self.assertTrue(part.is_file())

            for transient_code in (18, 28, 56):
                with self.subTest(code=transient_code):
                    # Mock subprocess.run to simulate curl exiting with transient error
                    mock_proc = mock.Mock()
                    mock_proc.returncode = transient_code

                    with mock.patch("subprocess.run", return_value=mock_proc):
                        with self.assertRaises(RuntimeError) as cm:
                            _stream_download("http://example.com/asset.zim", dest)
                        self.assertIn(f"curl exit code {transient_code}", str(cm.exception))
                        self.assertTrue(part.is_file(), f"part file was unlinked on curl exit {transient_code}!")
                        self.assertFalse(dest.is_file(), "dest file should not have been created on failed download")

    def test_fetch_assets_unlinks_part_file_on_code_33_range_error(self):
        """Curl exit code 33 (HTTP 416 range error) MUST trigger clean unlink and retry."""
        from emyrge.assets.fetch_assets import _stream_download

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "test_download.zim"
            part = dest.with_suffix(dest.suffix + ".part")

            # Create an existing 5MB partial download
            part.write_bytes(b"ZIM\x04" + b"\x00" * (5 * 1024 * 1024 - 4))

            # Simulate code 33 on resume attempt, followed by successful clean download
            first_run = mock.Mock(returncode=33)
            second_run = mock.Mock(returncode=0)

            call_count = 0
            def fake_subprocess_run(cmd, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # In first run with -C -, code 33 is returned
                    return first_run
                else:
                    # Second run (clean), simulate writing full file
                    part.write_bytes(b"ZIM\x04" + b"\x00" * 1024)
                    return second_run

            with mock.patch("subprocess.run", side_effect=fake_subprocess_run):
                _stream_download("http://example.com/asset.zim", dest)
                self.assertEqual(call_count, 2, "Expected 2 subprocess calls: failed resume and clean retry")
                self.assertTrue(dest.is_file(), "Final destination file should exist after clean retry")

    def test_ps1_preserves_part_file_on_non_33_exit_codes(self):
        """Inspect scripts/download_internet_in_a_box.ps1 logic to verify .part is not deleted on transient codes."""
        ps1_path = repo_root / "scripts" / "download_internet_in_a_box.ps1"
        self.assertTrue(ps1_path.is_file())
        ps1_text = ps1_path.read_text(encoding="utf-8")

        # Confirm Remove-Item is conditioned strictly on -eq 33
        self.assertIn("if ($LASTEXITCODE -eq 33)", ps1_text)
        self.assertIn("Remove-Item $partFile", ps1_text)
        # Confirm error message indicates file preservation
        self.assertIn("Partial file preserved at $partFile for resumption", ps1_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
