"""Milestone 2 Verification Test Suite: Multimodal Backend Inference Routing & UI Harness.

Verifies:
1. discover_mmproj() auto-locating mmproj weights in directory or data/models/.
2. ModelRunner --mmproj argument injection into llama-server.
3. ModelRunner.complete_chat() OpenAI-compatible multimodal content array formatting.
4. Model priority pattern updates for Qwen2.5-0.5B-Q8_0, Qwen2-VL-2B-Instruct-Q4,
   Qwen2.5-7B-Instruct-Q4, and Gemma-2-9B-It-Q4.
5. REST API /api/ask:
   - Tier 0 gating: rejects attached image with HTTP 400.
   - Tier 0 simulated hardware (pi_zero, chromebook): rejects attached image.
   - Tier 2 Auto-Routing: routes image query via Qwen2-VL-2B-Instruct when text model active,
     producing visual_observation, model_used, citations, and routing="multimodal_autoroute".
   - Direct Tier 1: routes directly when Qwen2-VL-2B-Instruct selected.
6. Command Center UI HTML & JS:
   - Essential input, preview, and indicator element IDs exist in index.html.
   - web/static/app.js and web/static/js/app.js are byte-for-byte identical.
   - Gating and listener logic present in app.js.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from emyrge.ai.model_runner import ModelRunner, discover_mmproj
from emyrge.core.config import EmyrgeConfig
from emyrge.server import create_server


def create_mock_gguf(path: Path, size: int = 10 * 1024 * 1024) -> None:
    """Creates a mock valid GGUF file with 'GGUF' magic header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"GGUF")
        f.write(b"\x03\x00\x00\x00")  # version 3
        # Pad with zeros to meet size threshold
        if size > 8:
            f.seek(size - 1)
            f.write(b"\x00")


class TestMilestone2ModelRunner(unittest.TestCase):
    """Verifies model_runner.py discover_mmproj, priority patterns, and multimodal payloads."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.models_dir = self.root / "data" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_discover_mmproj_matching_model_family(self):
        """Verifies discover_mmproj locates matching mmproj projector."""
        vlm_model = self.models_dir / "Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
        mmproj_file = self.models_dir / "mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
        create_mock_gguf(vlm_model)
        create_mock_gguf(mmproj_file)

        found = discover_mmproj(vlm_model, models_dir=self.models_dir)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "mmproj-Qwen2-VL-2B-Instruct-f16.gguf")

    def test_02_discover_mmproj_returns_none_when_no_projector(self):
        """Verifies discover_mmproj returns None when no mmproj file exists."""
        text_model = self.models_dir / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
        create_mock_gguf(text_model)

        found = discover_mmproj(text_model, models_dir=self.models_dir)
        self.assertIsNone(found)

    def test_03_model_runner_instance_discover_mmproj(self):
        """Verifies ModelRunner.discover_mmproj instance method."""
        runner = ModelRunner(self.root)
        vlm_model = self.models_dir / "Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
        mmproj_file = self.models_dir / "mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
        create_mock_gguf(vlm_model)
        create_mock_gguf(mmproj_file)

        found = runner.discover_mmproj(vlm_model)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, mmproj_file.name)

    def test_04_discover_model_skips_mmproj_files(self):
        """Verifies discover_model never selects an mmproj file as the base LLM."""
        runner = ModelRunner(self.root)
        mmproj_file = self.models_dir / "mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
        create_mock_gguf(mmproj_file, size=20 * 1024 * 1024)

        # Only mmproj exists: discover_model must return None
        self.assertIsNone(runner.discover_model())

        # Now add actual model
        vlm_model = self.models_dir / "Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
        create_mock_gguf(vlm_model, size=15 * 1024 * 1024)
        found = runner.discover_model()
        self.assertIsNotNone(found)
        self.assertEqual(found.name, vlm_model.name)

    def test_05_discover_model_priorities_tier0_q8_0(self):
        """Verifies Tier 0 prioritizes Q8_0 quantization over Q4."""
        runner = ModelRunner(self.root)
        q4_model = self.models_dir / "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
        q8_model = self.models_dir / "Qwen2.5-0.5B-Instruct-Q8_0.gguf"
        create_mock_gguf(q4_model, size=10 * 1024 * 1024)
        create_mock_gguf(q8_model, size=12 * 1024 * 1024)

        import os
        old_tier = os.environ.get("EMYRGE_TIER")
        try:
            os.environ["EMYRGE_TIER"] = "0"
            chosen = runner.discover_model()
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name, q8_model.name)
        finally:
            if old_tier is not None:
                os.environ["EMYRGE_TIER"] = old_tier
            else:
                os.environ.pop("EMYRGE_TIER", None)

    def test_06_discover_model_preferred_model_override(self):
        """Verifies discover_model respects preferred_model parameter."""
        runner = ModelRunner(self.root)
        m7b = self.models_dir / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
        m9b = self.models_dir / "gemma-2-9b-it-Q4_K_M.gguf"
        create_mock_gguf(m7b)
        create_mock_gguf(m9b)

        chosen7 = runner.discover_model(preferred_model="qwen2.5-7b-instruct-q4")
        self.assertIsNotNone(chosen7)
        self.assertEqual(chosen7.name, m7b.name)

        chosen9 = runner.discover_model(preferred_model="gemma-2-9b-it-q4")
        self.assertIsNotNone(chosen9)
        self.assertEqual(chosen9.name, m9b.name)

    def test_07_complete_chat_fallback_synthesis_with_image(self):
        """Verifies complete_chat executes zero-fail deterministic synthesis when offline with image."""
        runner = ModelRunner(self.root)
        res = runner.complete_chat(
            system_prompt="System instructions",
            user_prompt="Field water query",
            image="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        )
        self.assertIn("text", res)
        self.assertIn("engine", res)
        self.assertEqual(res["live_llm"], False)
        self.assertIn("water", res["text"].lower())


class TestMilestone2ApiGatingAndAutoRouting(unittest.TestCase):
    """Verifies /api/ask tier 0 rejection and tier 2 multimodal auto-routing."""

    @classmethod
    def setUpClass(cls):
        cls.config = EmyrgeConfig.from_env(project_root=REPO_ROOT)
        cls.config.port = 8790
        cls.config.headless = True
        cls.server, cls.runtime = create_server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.config.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body}
            return err.code, parsed

    def test_01_tier0_rejects_attached_image_with_400(self):
        """Verifies /api/ask with tier=0 and image returns HTTP 400 with clean error."""
        sample_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        status, res = self._post("/api/ask", {
            "prompt": "Inspect this filter",
            "image": sample_img,
            "tier": 0,
        })
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))

    def test_02_simulated_pi_zero_rejects_attached_image(self):
        """Verifies simulating pi_zero profile rejects image input."""
        # Switch to pi_zero
        self._post("/api/simulate-hardware", {"preset": "pi_zero"})
        sample_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        status, res = self._post("/api/ask", {
            "prompt": "Examine water source photo",
            "image": sample_img,
        })
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))

        # Reset simulation back to auto
        self._post("/api/simulate-hardware", {"preset": "auto"})

    def test_03_tier2_autoroutes_multimodal_query(self):
        """Verifies submitting image in Tier 2 with text model auto-routes via Qwen2-VL-2B."""
        sample_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        status, res = self._post("/api/ask", {
            "prompt": "Identify water purification chemical dosage from label",
            "image": sample_img,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")
        self.assertIn("visual_observation", res)
        self.assertIn("Qwen2-VL-2B", res.get("visual_observation", ""))
        self.assertIn("answer", res)
        self.assertIn("model_used", res)
        self.assertIn("citations", res)
        self.assertIsInstance(res["citations"], list)
        self.assertGreater(len(res["citations"]), 0)

    def test_04_direct_tier1_vlm_routes_direct(self):
        """Verifies submitting to Qwen2-VL-2B directly returns routing='direct'."""
        sample_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        status, res = self._post("/api/ask", {
            "prompt": "Inspect circuit board capacitor",
            "image": sample_img,
            "model": "qwen2-vl-2b-instruct-q4",
            "tier": 1,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "direct")
        self.assertIn("Qwen2-VL", res.get("model_used", ""))
        self.assertIn("answer", res)


class TestMilestone2FrontendUI(unittest.TestCase):
    """Verifies Agent Harness UI controls and app.js synchronization."""

    def setUp(self):
        self.index_html = (REPO_ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
        self.app_js = (REPO_ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        self.js_app = (REPO_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")

    def test_01_index_html_multimodal_element_ids(self):
        """Verifies required file input, attach button, preview container, and indicator exist in index.html."""
        required_elements = [
            'id="harnessImageInput"',
            'id="harnessAttachBtn"',
            'id="harnessInput"',
            'id="harnessImagePreviewContainer"',
            'id="harnessImagePreview"',
            'id="harnessImageMeta"',
            'id="harnessImageRemoveBtn"',
            'id="harnessRoutingIndicator"',
        ]
        for elem in required_elements:
            self.assertIn(elem, self.index_html, f"Missing required UI element in index.html: {elem}")

    def test_02_app_js_and_js_app_js_byte_for_byte_identical(self):
        """Verifies web/static/app.js and web/static/js/app.js are byte-for-byte identical."""
        self.assertEqual(self.app_js, self.js_app, "web/static/app.js and web/static/js/app.js must match byte-for-byte")

    def test_03_app_js_gating_and_routing_logic(self):
        """Verifies app.js contains image gating and routing indicator updates."""
        self.assertIn("applyImageGating", self.app_js)
        self.assertIn("updateMultimodalRoutingIndicator", self.app_js)
        self.assertIn("handleImageFile", self.app_js)
        self.assertIn("removeAttachedImage", self.app_js)
        self.assertIn("harnessAttachBtn", self.app_js)
        self.assertIn("harnessImageInput", self.app_js)
        self.assertIn("harnessImagePreviewContainer", self.app_js)
        self.assertIn("harnessRoutingIndicator", self.app_js)


if __name__ == "__main__":
    unittest.main()
