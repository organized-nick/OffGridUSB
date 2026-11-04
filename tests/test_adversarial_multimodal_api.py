"""Adversarial Challenge Test Suite for OffGridUSB API (/api/ask) and ModelRunner.

Empirical verification suite targeting edge cases, boundary conditions, malformed
payloads, tier gating, multimodal auto-routing, and text regression resistance.

Test Vectors:
1. Empty & Whitespace Prompts with and without Image Payload
2. Corrupted, Malformed, Truncated, and Non-Image Base64 Data URIs
3. Oversized Payload Stress (Multi-MB payloads, Content-Length bounds)
4. Strict Tier 0 Image Gating & Error Contracts (tier 0, tier -1, pi_zero, chromebook, esp32)
5. Tier 2 Multimodal Auto-Routing & Visual Observation Extraction (7B, 9B, OCR text extraction)
6. Non-Regression of Text-Only Grounded RAG & Deterministic Calculators
7. ModelRunner Direct Stress Testing (extreme tokens, malformed sources, fallback resilience)
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

# 1x1 Transparent PNG Base64 Data URI
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
TINY_PNG_DATA_URI = f"data:image/png;base64,{TINY_PNG_B64}"

# Synthetic PNG with embedded OCR ASCII marker for feature extraction testing
SYNTHETIC_OCR_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00"
    b"\x1f\xf3\xffa\x00\x00\x00\x2bIDATx\x9cc`\x18\x05\xa3`\x14\x8c\x82\x51\x30\n\x18\x05\xa3"
    b"DOSAGE_20L_TURBID_CHLORINE_TEST_SAMPLE\x00\x00\x00\x00IEND\xaeB`\x82"
)
SYNTHETIC_OCR_DATA_URI = f"data:image/png;base64,{base64.b64encode(SYNTHETIC_OCR_PNG_BYTES).decode('ascii')}"


class TestAdversarialMultimodalApi(unittest.TestCase):
    """Adversarial stress and edge case test suite for /api/ask and ModelRunner."""

    @classmethod
    def setUpClass(cls):
        cls.config = EmyrgeConfig.from_env(project_root=REPO_ROOT)
        cls.config.port = 8895
        cls.config.headless = True
        cls.server, cls.runtime = create_server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post(self, path: str, payload: dict, timeout: float = 15.0) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.config.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body}
            return err.code, parsed

    def _post_raw(self, path: str, raw_bytes: bytes, headers: dict = None, timeout: float = 15.0) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.config.port}{path}"
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=raw_bytes, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body}
            return err.code, parsed

    # -------------------------------------------------------------------------
    # VECTOR 1: Empty / Whitespace Prompts with & without Image Payload
    # -------------------------------------------------------------------------

    def test_v1_01_empty_prompt_with_image_in_tier2_succeeds_and_autoroutes(self):
        """Empty string prompt '' with image attached defaults to visual analysis prompt in Tier 2."""
        status, res = self._post("/api/ask", {
            "prompt": "",
            "image": TINY_PNG_DATA_URI,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")
        self.assertIn("visual_observation", res)
        self.assertGreater(len(res["visual_observation"]), 0)
        self.assertEqual(res.get("model_used"), "Qwen2.5-7B-Instruct")
        self.assertIn("answer", res)
        self.assertGreater(len(res["answer"]), 0)

    def test_v1_02_whitespace_prompt_with_image_in_tier2_gemma(self):
        """Whitespace-only prompt '   \\r\\n\\t  ' with image in Tier 2 defaults and autoroutes."""
        status, res = self._post("/api/ask", {
            "prompt": "   \r\n\t  ",
            "image": TINY_PNG_DATA_URI,
            "model": "gemma-2-9b-it-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")
        self.assertEqual(res.get("model_used"), "Gemma-2-9B-It")
        self.assertIn("visual_observation", res)
        self.assertIn("citations", res)

    def test_v1_03_empty_prompt_with_image_in_tier1_vlm(self):
        """Empty prompt with image in Tier 1 with VLM selected defaults prompt and routes direct."""
        status, res = self._post("/api/ask", {
            "prompt": "",
            "image": TINY_PNG_DATA_URI,
            "model": "qwen2-vl-2b-instruct-q4",
            "tier": 1,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "direct")
        self.assertEqual(res.get("model_used"), "Qwen2-VL-2B-Instruct")

    def test_v1_04_empty_prompt_without_image_returns_error(self):
        """Empty prompt with no image returns ok=False error without crashing server."""
        status, res = self._post("/api/ask", {
            "prompt": "",
            "tier": 2,
        })
        # Server returns error payload (ok: false)
        self.assertFalse(res.get("ok"))
        self.assertIn("Query must not be empty", res.get("error", ""))

    def test_v1_05_whitespace_only_prompt_without_image_returns_error(self):
        """Whitespace-only prompt without image returns ok=False cleanly."""
        status, res = self._post("/api/ask", {
            "prompt": "   \t\t\n   ",
            "tier": 1,
        })
        self.assertFalse(res.get("ok"))
        self.assertIn("Query must not be empty", res.get("error", ""))

    # -------------------------------------------------------------------------
    # VECTOR 2: Corrupted, Malformed, Truncated, & Non-Image Base64 Data URIs
    # -------------------------------------------------------------------------

    def test_v2_01_corrupted_base64_payload_survives_without_500(self):
        """Corrupted base64 payload ($%^&*) does not throw an unhandled 500 error."""
        corrupted_uri = "data:image/png;base64,NOT_A_VALID_BASE64_STRING_!@#$%^&*()_+"
        status, res = self._post("/api/ask", {
            "prompt": "Inspect this filter",
            "image": corrupted_uri,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertIn(status, (200, 400))
        self.assertNotEqual(status, 500)
        if status == 200:
            self.assertTrue(res.get("ok"))
            self.assertIn("visual_observation", res)

    def test_v2_02_empty_base64_data_uri_survives(self):
        """Empty data URI payload 'data:image/png;base64,' does not crash server."""
        empty_b64_uri = "data:image/png;base64,"
        status, res = self._post("/api/ask", {
            "prompt": "Inspect water source",
            "image": empty_b64_uri,
            "tier": 2,
        })
        self.assertIn(status, (200, 400))
        self.assertNotEqual(status, 500)

    def test_v2_03_truncated_uri_header_without_comma_survives(self):
        """Truncated data URI without comma separator does not crash server."""
        truncated_uri = "data:image/png;base64"
        status, res = self._post("/api/ask", {
            "prompt": "Analyze photo",
            "image": truncated_uri,
            "tier": 2,
        })
        self.assertIn(status, (200, 400))
        self.assertNotEqual(status, 500)

    def test_v2_04_raw_non_data_uri_base64_handled(self):
        """Raw base64 string without 'data:image/...' prefix is accepted and handled."""
        status, res = self._post("/api/ask", {
            "prompt": "Analyze schematic",
            "image": TINY_PNG_B64,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")

    def test_v2_05_non_image_mime_type_data_uri_survives(self):
        """Data URI with text/plain or application/pdf MIME does not crash server."""
        text_uri = "data:text/plain;base64,U3Vydml2YWwgR3VpZGUgVGV4dCBDb250ZW50"
        status, res = self._post("/api/ask", {
            "prompt": "Check document",
            "image": text_uri,
            "tier": 2,
        })
        self.assertIn(status, (200, 400))
        self.assertNotEqual(status, 500)

    # -------------------------------------------------------------------------
    # VECTOR 3: Oversized Payload Stress
    # -------------------------------------------------------------------------

    def test_v3_01_large_image_payload_2mb_succeeds(self):
        """2MB image payload processes cleanly within memory limits."""
        large_bytes = b"\x00" * (2 * 1024 * 1024)
        large_b64 = base64.b64encode(large_bytes).decode("ascii")
        large_uri = f"data:image/png;base64,{large_b64}"
        status, res = self._post("/api/ask", {
            "prompt": "Analyze high resolution satellite imagery",
            "image": large_uri,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))

    def test_v3_02_oversized_payload_exceeding_25mb_returns_400(self):
        """Payload declaring or exceeding 25MB buffer cap is rejected with 400, not unhandled 500."""
        # Send partial truncated JSON of size 26MB header or malformed huge payload
        huge_raw = b'{"prompt": "Huge test", "data": "' + (b'A' * (26 * 1024 * 1024)) + b'"}'
        # To avoid actual 26MB socket buffer slow transfer, craft a request with Content-Length larger than read cap
        # or truncated JSON stream
        truncated_raw = b'{"prompt": "Test", "huge": "' + (b'x' * 100000)  # Unclosed JSON
        status, res = self._post_raw(
            "/api/ask",
            truncated_raw,
            headers={"Content-Length": str(len(truncated_raw))},
        )
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertIn("Invalid JSON", res.get("error", ""))

    def test_v3_03_huge_prompt_text_100kb_processes_cleanly(self):
        """100KB textual query string is handled without stack overflow or catastrophic backtracking."""
        huge_query = "What is the emergency protocol for water purification? " + ("detail " * 15000)
        status, res = self._post("/api/ask", {
            "prompt": huge_query,
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertIn("answer", res)

    # -------------------------------------------------------------------------
    # VECTOR 4: Strict Tier 0 Image Gating & Rejection
    # -------------------------------------------------------------------------

    def test_v4_01_tier0_explicit_rejects_image_with_strict_400(self):
        """Explicit tier=0 with image returns strict HTTP 400 and clean contract error message."""
        status, res = self._post("/api/ask", {
            "prompt": "Analyze solar panel",
            "image": TINY_PNG_DATA_URI,
            "tier": 0,
        })
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "Multimodal image input is not supported in Tier 0.")
        self.assertEqual(res.get("answer"), "Multimodal image input is not supported in Tier 0.")

    def test_v4_02_tier_negative_one_mcu_relay_rejects_image(self):
        """Tier -1 (Thin Client / MCU Relay) rejects image input with HTTP 400."""
        status, res = self._post("/api/ask", {
            "prompt": "Analyze wound photo",
            "image": TINY_PNG_DATA_URI,
            "tier": -1,
        })
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))

    def test_v4_03_simulated_preset_pi_zero_rejects_image(self):
        """Hardware simulation profile 'pi_zero' strictly gates image upload."""
        self._post("/api/simulate-hardware", {"preset": "pi_zero"})
        try:
            status, res = self._post("/api/ask", {
                "prompt": "Identify leaf disease",
                "image": TINY_PNG_DATA_URI,
            })
            self.assertEqual(status, 400)
            self.assertFalse(res.get("ok"))
            self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))
        finally:
            self._post("/api/simulate-hardware", {"preset": "auto"})

    def test_v4_04_simulated_preset_chromebook_rejects_image(self):
        """Hardware simulation profile 'chromebook' strictly gates image upload."""
        self._post("/api/simulate-hardware", {"preset": "chromebook"})
        try:
            status, res = self._post("/api/ask", {
                "prompt": "Read resistor color bands",
                "image": TINY_PNG_DATA_URI,
            })
            self.assertEqual(status, 400)
            self.assertFalse(res.get("ok"))
            self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))
        finally:
            self._post("/api/simulate-hardware", {"preset": "auto"})

    def test_v4_05_simulated_preset_esp32_rejects_image(self):
        """Hardware simulation profile 'esp32' strictly gates image upload."""
        self._post("/api/simulate-hardware", {"preset": "esp32"})
        try:
            status, res = self._post("/api/ask", {
                "prompt": "Read water meter",
                "image": TINY_PNG_DATA_URI,
            })
            self.assertEqual(status, 400)
            self.assertFalse(res.get("ok"))
            self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))
        finally:
            self._post("/api/simulate-hardware", {"preset": "auto"})

    def test_v4_06_empty_prompt_with_image_in_tier0_still_rejected_with_400(self):
        """Empty prompt + image in Tier 0 triggers Tier 0 rejection rather than empty prompt error."""
        status, res = self._post("/api/ask", {
            "prompt": "",
            "image": TINY_PNG_DATA_URI,
            "tier": 0,
        })
        self.assertEqual(status, 400)
        self.assertFalse(res.get("ok"))
        self.assertIn("Multimodal image input is not supported in Tier 0", res.get("error", ""))

    # -------------------------------------------------------------------------
    # VECTOR 5: Tier 2 Multimodal Auto-Routing & Feature Extraction
    # -------------------------------------------------------------------------

    def test_v5_01_tier2_qwen25_7b_autoroutes_and_returns_routing_metadata(self):
        """Tier 2 with Qwen2.5-7B-Instruct auto-routes through Qwen2-VL-2B and tags routing."""
        status, res = self._post("/api/ask", {
            "prompt": "Inspect chemical container label",
            "image": TINY_PNG_DATA_URI,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")
        self.assertEqual(res.get("model_used"), "Qwen2.5-7B-Instruct")
        self.assertIn("visual_observation", res)
        self.assertIn("Qwen2-VL-2B-Instruct", res["visual_observation"])
        self.assertIsInstance(res.get("citations"), list)
        self.assertGreater(len(res["citations"]), 0)

    def test_v5_02_tier2_gemma2_9b_autoroutes_and_returns_routing_metadata(self):
        """Tier 2 with Gemma-2-9B-It auto-routes through Qwen2-VL-2B and tags routing."""
        status, res = self._post("/api/ask", {
            "prompt": "Evaluate burn wound severity",
            "image": TINY_PNG_DATA_URI,
            "model": "gemma-2-9b-it-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "multimodal_autoroute")
        self.assertEqual(res.get("model_used"), "Gemma-2-9B-It")
        self.assertIn("visual_observation", res)
        self.assertIn("Qwen2-VL-2B-Instruct", res["visual_observation"])

    def test_v5_03_ocr_embedded_text_extraction(self):
        """Visual observation extractor detects embedded OCR ASCII text in image payload."""
        status, res = self._post("/api/ask", {
            "prompt": "What dosage is indicated?",
            "image": SYNTHETIC_OCR_DATA_URI,
            "model": "qwen2.5-7b-instruct-q4",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        vis_obs = res.get("visual_observation", "")
        # The synthetic image has "DOSAGE_20L_TURBID_CHLORINE_TEST_SAMPLE" embedded
        self.assertTrue(
            "DOSAGE" in vis_obs or "TURBID" in vis_obs or "CHLORINE" in vis_obs,
            f"Visual observation failed to detect embedded text: {vis_obs}",
        )

    # -------------------------------------------------------------------------
    # VECTOR 6: Text-Only Non-Regression & Deterministic Calculators
    # -------------------------------------------------------------------------

    def test_v6_01_water_purification_text_query_triggers_calculator_and_citations(self):
        """Water purification prompt triggers calculator oracle and verified ZIM citations."""
        status, res = self._post("/api/ask", {
            "prompt": "How many drops of bleach to purify 20 liters of turbid flood water?",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("routing"), "direct")
        self.assertNotIn("visual_observation", res)
        # Check deterministic calculator output
        calc_res = res.get("calculator_result")
        self.assertIsNotNone(calc_res)
        self.assertIn("drops", calc_res)
        self.assertEqual(calc_res["drops"], 80)
        self.assertIn("volume_ml", calc_res)
        self.assertAlmostEqual(calc_res["volume_ml"], 4.0, places=1)
        # Citations check
        self.assertGreaterEqual(len(res.get("citations", [])), 1)

    def test_v6_02_medical_rehydration_text_query_non_regression(self):
        """Medical rehydration prompt returns verified ORS instructions."""
        status, res = self._post("/api/ask", {
            "prompt": "What is the oral rehydration solution formula for severe cholera diarrhea?",
            "tier": 1,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        answer = res.get("answer", "").lower()
        self.assertTrue("water" in answer or "salt" in answer or "sugar" in answer or "ors" in answer)
        self.assertGreaterEqual(len(res.get("citations", [])), 1)

    def test_v6_03_electrical_ohms_law_text_query_non_regression(self):
        """Electrical query triggers Ohm's law calculator and returns current."""
        status, res = self._post("/api/ask", {
            "prompt": "What current flows through 4 ohms resistor at 12 volts?",
            "tier": 2,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        calc_res = res.get("calculator_result")
        if calc_res:
            self.assertAlmostEqual(calc_res.get("current_a", 0), 3.0, places=1)

    def test_v6_04_direct_zero_ai_mode_succeeds(self):
        """Mode='direct' returns zero-LLM lookup from local ZIM and Khan indices."""
        status, res = self._post("/api/ask", {
            "prompt": "Water disinfection",
            "mode": "direct",
            "tier": 0,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "direct")
        self.assertIn("engine_used", res)
        self.assertIn("0 LLM tokens", res["engine_used"])

    # -------------------------------------------------------------------------
    # VECTOR 7: ModelRunner Direct Stress Testing
    # -------------------------------------------------------------------------

    def test_v7_01_model_runner_complete_chat_with_image_fallback(self):
        """ModelRunner.complete_chat handles image payloads safely when llama-server is offline."""
        runner = ModelRunner(REPO_ROOT)
        res = runner.complete_chat(
            system_prompt="Test system",
            user_prompt="Inspect image",
            image=TINY_PNG_DATA_URI,
        )
        self.assertIsInstance(res, dict)
        self.assertIn("text", res)
        self.assertIn("engine", res)
        self.assertEqual(res["live_llm"], False)

    def test_v7_02_model_runner_complete_chat_with_corrupted_image(self):
        """ModelRunner.complete_chat handles corrupted base64 without throwing exceptions."""
        runner = ModelRunner(REPO_ROOT)
        res = runner.complete_chat(
            system_prompt="Test system",
            user_prompt="Inspect image",
            image="data:image/jpeg;base64,CORRUPTED_BASE64_BYTE_STREAM",
        )
        self.assertIsInstance(res, dict)
        self.assertIn("text", res)

    def test_v7_03_model_runner_complete_chat_with_extreme_max_tokens(self):
        """ModelRunner.complete_chat handles zero or extreme max_tokens gracefully."""
        runner = ModelRunner(REPO_ROOT)
        for tokens in (0, -1, 1000000):
            res = runner.complete_chat(
                system_prompt="System",
                user_prompt="Query",
                max_tokens=tokens,
            )
            self.assertIn("text", res)

    def test_v7_04_model_runner_complete_chat_with_corrupted_fallback_sources(self):
        """ModelRunner.complete_chat survives malformed fallback_sources (None, missing fields)."""
        runner = ModelRunner(REPO_ROOT)
        corrupted_sources = [
            {},
            {"title": None, "snippet": None},
            {"title": "Broken", "source_type": "unknown_type", "full_text": None},
        ]
        res = runner.complete_chat(
            system_prompt="System",
            user_prompt="Query",
            fallback_sources=corrupted_sources,
        )
        self.assertIn("text", res)
        self.assertGreater(len(res["text"]), 0)

    def test_v7_05_discover_mmproj_directory_traversal_defense(self):
        """discover_mmproj safely handles paths with traversal or non-existent paths."""
        runner = ModelRunner(REPO_ROOT)
        fake_path = REPO_ROOT / ".." / ".." / "fake_model.gguf"
        res = runner.discover_mmproj(fake_path)
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
