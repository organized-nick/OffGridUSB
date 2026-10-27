"""Milestone 3 Verification Test Suite: Command Center Server & SKU-Aware UI Hygiene.

Verifies:
1. Manifest SKU integration (manifests/product_sku.json) and graceful fallback.
2. Server API endpoints: GET /api/status, GET /api/product, POST /api/professor,
   POST /api/calc, POST /api/memory, GET /api/vision.
3. Air-gap hygiene: Zero buy links, zero links to offgridusb.com, zero download/upgrade buttons.
4. Dynamic tab gating & model filtering invariants.
5. Customer-only USER_GUIDE.md verification.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from emyrge.server import DEFAULT_PRODUCT_DESCRIPTOR, load_product_sku, create_server
from emyrge.core.config import EmyrgeConfig


class TestMilestone3SkuBackend(unittest.TestCase):
    """Verifies backend SKU loading and REST API contracts."""

    @classmethod
    def setUpClass(cls):
        cls.config = EmyrgeConfig.from_env(project_root=REPO_ROOT)
        cls.config.port = 8765
        cls.config.headless = True
        cls.server, cls.runtime = create_server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _api_get(self, path: str) -> dict:
        url = f"http://127.0.0.1:{self.config.port}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def _api_post(self, path: str, payload: dict) -> dict:
        url = f"http://127.0.0.1:{self.config.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def test_01_load_product_sku_live(self):
        """Verifies live loading of manifests/product_sku.json."""
        sku_data = load_product_sku(REPO_ROOT)
        self.assertIsInstance(sku_data, dict)
        self.assertEqual(sku_data.get("sku"), "Product2")
        self.assertIn("FieldReady", sku_data.get("name", ""))
        self.assertEqual(sku_data.get("tiers"), [0, 1])
        self.assertIn("active_models", sku_data)
        self.assertGreaterEqual(len(sku_data["active_models"]), 2)
        self.assertIn("features", sku_data)
        self.assertIn("hidden_features", sku_data)

    def test_02_load_product_sku_fallback(self):
        """Verifies graceful fallback when manifests/product_sku.json does not exist."""
        fallback = load_product_sku(Path("non_existent_directory_xyz"))
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback.get("sku"), "Product2")
        self.assertEqual(fallback.get("name"), "OffGridUSB — FieldReady")
        self.assertEqual(fallback.get("tiers"), [0, 1])
        self.assertIn("smollm2-135m-instruct-q4_k_m.gguf", fallback.get("active_models", []))

    def test_03_get_api_status_includes_product(self):
        """Verifies GET /api/status returns product metadata object."""
        res = self._api_get("/api/status")
        self.assertTrue(res.get("ok"))
        self.assertIn("product", res)
        p = res["product"]
        self.assertIn("sku", p)
        self.assertIn("name", p)
        self.assertIn("tiers", p)
        self.assertIn("features", p)
        self.assertIn("hidden_features", p)
        self.assertIn("active_models", p)
        self.assertEqual(p["sku"], "Product2")
        self.assertIn("swarm_cluster", p["hidden_features"])
        self.assertIn("distillation_on_dock", p["hidden_features"])

    def test_04_get_api_product_endpoint(self):
        """Verifies dedicated GET /api/product returns full product descriptor."""
        res = self._api_get("/api/product")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("sku"), "Product2")
        self.assertIn("name", res)
        self.assertIn("active_models", res)
        self.assertIn("features", res)
        self.assertIn("hidden_features", res)

    def test_05_post_api_calc(self):
        """Verifies POST /api/calc runs deterministic CDC water calculator."""
        res = self._api_post("/api/calc", {
            "type": "water",
            "params": {"volume_liters": 20, "is_cloudy": True, "method": "bleach"}
        })
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("type"), "water")
        result = res.get("result", {})
        self.assertEqual(result.get("drops"), 80)
        self.assertEqual(result.get("volume_liters"), 20.0)

    def test_06_post_api_professor(self):
        """Verifies POST /api/professor returns grounded citation answer."""
        res = self._api_post("/api/professor", {
            "query": "water purification",
            "mode": "direct"
        })
        self.assertTrue(res.get("ok"))
        self.assertIn("answer", res)
        self.assertIn("source", res)

    def test_07_post_api_memory(self):
        """Verifies POST /api/memory supports store and query actions."""
        # Store
        store_res = self._api_post("/api/memory", {
            "action": "store",
            "text": "Water chlorine contact time is 30m clear, 60m cloudy",
            "citations": ["[Source: Water purification#Emergency disinfection]"]
        })
        self.assertTrue(store_res.get("ok"))
        self.assertEqual(store_res.get("action"), "store")
        self.assertIn("id", store_res)

        # Query
        query_res = self._api_post("/api/memory", {
            "action": "query",
            "text": "chlorine"
        })
        self.assertTrue(query_res.get("ok"))
        self.assertEqual(query_res.get("action"), "query")
        self.assertIn("entries", query_res)

    def test_08_get_api_vision(self):
        """Verifies GET /api/vision returns offline indexed visual vault photos."""
        res = self._api_get("/api/vision")
        self.assertTrue(res.get("ok"))
        self.assertIn("photos", res)
        self.assertIsInstance(res["photos"], list)

    def test_09_post_api_calc_invalid_volume_returns_400(self):
        """Verifies POST /api/calc with negative volume returns HTTP 400."""
        url = f"http://127.0.0.1:{self.config.port}/api/calc"
        data = json.dumps({"type": "water", "params": {"volume_liters": -5}}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 400)
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 400)

    def test_10_module_imports_from_server(self):
        """Verifies emyrge.server exports required symbols."""
        import emyrge.server as srv
        self.assertTrue(callable(srv.load_product_sku))
        self.assertTrue(callable(srv.create_server))
        self.assertTrue(callable(srv.main))
        self.assertIn("DEFAULT_PRODUCT_DESCRIPTOR", srv.__all__)


class TestMilestone3FrontendHygiene(unittest.TestCase):
    """Verifies air-gap hygiene, zero buy links, zero download buttons, and tab gating."""

    def setUp(self):
        self.index_html = (REPO_ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
        self.app_js = (REPO_ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    def test_01_no_commercial_buy_links_in_index_html(self):
        """Verifies zero commercial buy links and zero links to https://offgridusb.com."""
        self.assertNotIn("cta-buy-pill", self.index_html, "Found prohibited cta-buy-pill in index.html")
        self.assertNotIn("https://offgridusb.com", self.index_html, "Found prohibited external url in index.html")
        self.assertNotIn("support-cta-footer", self.index_html, "Found prohibited support-cta-footer in index.html")

    def test_02_zero_download_buttons_in_index_html(self):
        """Verifies zero download, provision, upgrade, or install buttons exist."""
        banned = re.compile(r"<button[^>]*>.*?(download|provision|upgrade|install).*?</button>", re.IGNORECASE | re.DOTALL)
        matches = banned.findall(self.index_html)
        # Filter out legitimate buttons like distillDockBtn which is gated
        violating = [m for m in matches if "distill" not in m.lower()]
        self.assertEqual(len(violating), 0, f"Found prohibited button text: {violating}")

    def test_03_app_js_sku_gating_present(self):
        """Verifies applySkuGating and tab gating logic exist in app.js."""
        self.assertIn("function applySkuGating", self.app_js)
        self.assertIn("hidden-sku-tab", self.app_js)
        self.assertIn("hidden-sku-feature", self.app_js)
        self.assertIn("modelSelect", self.app_js)
        self.assertIn("sanitizeAirGapHygiene", self.app_js)

    def test_04_app_js_synced_in_js_directory(self):
        """Verifies web/static/js/app.js exists and matches web/static/app.js."""
        js_app = REPO_ROOT / "web" / "static" / "js" / "app.js"
        self.assertTrue(js_app.exists(), "web/static/js/app.js must exist")
        self.assertEqual(js_app.read_text(encoding="utf-8"), self.app_js)

    def test_05_sku_tab_ids_in_index_html(self):
        """Verifies essential navigation and feature IDs exist in index.html for SKU gating."""
        expected_ids = [
            'id="nav-harness"',
            'id="nav-iiab"',
            'id="nav-calc"',
            'id="nav-memory"',
            'id="nav-vision"',
            'id="nav-swarm"',
            'id="nav-distill"',
            'id="subtab-khan"',
            'id="modelSelect"',
            'id="skuBadge"',
            'id="brandTitle"',
            'id="brandSub"',
        ]
        for eid in expected_ids:
            self.assertIn(eid, self.index_html, f"Missing expected gating ID in index.html: {eid}")


class TestMilestone3UserGuideHygiene(unittest.TestCase):
    """Verifies customer USER_GUIDE.md contains zero builder instructions or buy links."""

    def test_user_guide_is_strictly_customer_facing(self):
        content = (REPO_ROOT / "USER_GUIDE.md").read_text(encoding="utf-8")
        # Must not contain builder / cloning / formatting commands
        prohibited_phrases = [
            "clone_to_usb",
            "format_and_setup_usb",
            "download_internet_in_a_box",
            "fetch_assets.py",
            "pip install",
            "apt-get install",
            "git clone",
            "https://offgridusb.com",
        ]
        for phrase in prohibited_phrases:
            self.assertNotIn(phrase, content, f"USER_GUIDE.md contains prohibited phrase: {phrase}")

        # Must contain consumer plug & play instructions
        self.assertIn("START_OFFGRIDUSB_WINDOWS.bat", content)
        self.assertIn("START_OFFGRIDUSB_MAC.command", content)
        self.assertIn("START_OFFGRIDUSB_LINUX.sh", content)
        self.assertIn("http://127.0.0.1:8000", content)


if __name__ == "__main__":
    unittest.main()
