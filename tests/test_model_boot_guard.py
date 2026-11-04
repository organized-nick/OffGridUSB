"""Boot-time model auto-selection must not load models bigger than free RAM.

2026-11-03: the 32B tier-3 gguf staged on the USB stick wedged the windows
box at app boot (discover_model picked it, llama-server spun on the USB
metadata scan and thrashed 16GB RAM). discover_model now skips candidates
larger than available physical RAM unless explicitly requested via env.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from emyrge.ai.model_runner import ModelRunner, _available_ram_mb


def _mk_gguf(path: Path, size_mb: int = 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"GGUF")
        f.write(b"\x00" * (size_mb * 1024 * 1024 - 4))
    return path


def _runner(models_dir: Path) -> ModelRunner:
    return ModelRunner(project_root=REPO_ROOT, host="127.0.0.1", port=8082, models_dir_override=models_dir) \
        if "models_dir_override" in ModelRunner.__init__.__code__.co_varnames \
        else _runner_via_patch(models_dir)


def _runner_via_patch(models_dir: Path) -> ModelRunner:
    r = ModelRunner(project_root=REPO_ROOT, host="127.0.0.1", port=8082)
    r.models_dir = models_dir
    return r


class TestBootModelMemoryGuard(unittest.TestCase):
    def _runner(self, models_dir: Path) -> ModelRunner:
        r = ModelRunner(project_root=REPO_ROOT, host="127.0.0.1", port=8082)
        r.models_dir = models_dir
        return r

    def test_oversized_tier3_skipped_at_boot(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data" / "models"
            _mk_gguf(d / "Qwen2.5-32B-Instruct-Q4_K_M.gguf", size_mb=100)
            _mk_gguf(d / "qwen2.5-1.5b-instruct-q4_k_m.gguf", size_mb=10)
            r = self._runner(d)
            # pretend only ~50MB RAM free: the 100MB 32B must not be picked
            with patch("emyrge.ai.model_runner._available_ram_mb", return_value=50):
                self.assertEqual(r.discover_model().name, "qwen2.5-1.5b-instruct-q4_k_m.gguf")

    def test_explicit_env_override_still_wins(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data" / "models"
            _mk_gguf(d / "Qwen2.5-32B-Instruct-Q4_K_M.gguf", size_mb=100)
            _mk_gguf(d / "qwen2.5-1.5b-instruct-q4_k_m.gguf", size_mb=10)
            r = self._runner(d)
            env = {"OFFGRIDUSB_MODEL": "qwen2.5-32b", "EMYRGE_MODEL": ""}
            with patch.dict(os.environ, env, clear=False), \
                 patch("emyrge.ai.model_runner._available_ram_mb", return_value=50):
                # remove EMYRGE_MODEL from the patched env view
                os.environ.pop("EMYRGE_MODEL", None)
                self.assertEqual(r.discover_model().name, "Qwen2.5-32B-Instruct-Q4_K_M.gguf")

    def test_fallback_picks_largest_that_fits(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data" / "models"
            # no tier-pattern names at all: hit the size fallback
            _mk_gguf(d / "big-model.gguf", size_mb=100)
            _mk_gguf(d / "small-model.gguf", size_mb=10)
            r = self._runner(d)
            with patch("emyrge.ai.model_runner._available_ram_mb", return_value=50):
                self.assertEqual(r.discover_model().name, "small-model.gguf")
            with patch("emyrge.ai.model_runner._available_ram_mb", return_value=None):
                self.assertEqual(r.discover_model().name, "big-model.gguf")

    def test_normal_selection_unaffected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data" / "models"
            _mk_gguf(d / "Qwen2.5-32B-Instruct-Q4_K_M.gguf", size_mb=30)
            _mk_gguf(d / "qwen2.5-1.5b-instruct-q4_k_m.gguf", size_mb=10)
            r = self._runner(d)
            with patch("emyrge.ai.model_runner._available_ram_mb", return_value=64 * 1024):
                self.assertEqual(r.discover_model().name, "Qwen2.5-32B-Instruct-Q4_K_M.gguf")

    def test_available_ram_helper_shapes(self):
        # must return None or a positive int; never raise
        v = _available_ram_mb()
        self.assertTrue(v is None or (isinstance(v, int) and v > 0))


if __name__ == "__main__":
    unittest.main()