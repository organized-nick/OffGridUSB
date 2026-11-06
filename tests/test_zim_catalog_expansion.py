"""Tests for the extended offline-content catalog (manifests/zim.json).

Verifies the content-catalog contract:
- every archive entry is schema-complete and well-formed
- the 2026-11-04 extended content set exists, is hashed, and is claimed
  by at least one SKU (per-drive-size separation, john 2026-11-06)
- SKU set includes the per-drive-size variants (Product2-256, Product3-256)
- fetch_assets.load_manifests() still parses the manifest cleanly
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIM_MANIFEST = ROOT / "manifests" / "zim.json"
PRODUCTS_MANIFEST = ROOT / "manifests" / "products.json"
MODELS_MANIFEST = ROOT / "manifests" / "models.json"

REQUIRED_FIELDS = {
    "id", "name", "filename", "tier", "category", "size_bytes", "size_mb",
    "sha256", "magic_header", "verified_local", "required_for_skus", "url",
    "description",
}

EXTENDED_IDS = [
    "armypubs-en-all", "cd3wd-en-all", "appropedia-en-maxi", "energypedia-en-nopic",
    "readygov-en-all", "readygov-es-all", "medlineplus-en-all", "worldfactbook-en-all",
    "maps-usa-en", "maps-canada-en", "ifixit-en-all", "se-diy-en-all",
    "se-electronics-en-all", "se-outdoors-en-all", "libretexts-med-en",
    "phet-en-all", "wikiversity-en-nopic", "s2underground-en-all",
    "trueprepper-en-all", "mdwiki-en-maxi", "100r-co-en-all", "devdocs-man-en",
]

ALL_SKUS = {
    "Product1", "Product2", "Product2-256", "Product3", "Product3-256",
    "Tier3", "Tier4",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_manifest() -> dict:
    return json.loads(ZIM_MANIFEST.read_text(encoding="utf-8"))


def _load_fetch_assets_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_assets", ROOT / "provisioning" / "tools" / "fetch_assets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_parses_and_entries_are_schema_complete():
    data = _load_manifest()
    assert data["schema_version"] == "1.0"
    assert len(data["archives"]) >= 50, "catalog expansion should have grown the archive list"
    for a in data["archives"]:
        missing = REQUIRED_FIELDS - set(a)
        assert not missing, f"{a.get('id')} missing fields {missing}"


def test_ids_and_filenames_unique():
    data = _load_manifest()
    ids = [a["id"] for a in data["archives"]]
    filenames = [a["filename"] for a in data["archives"]]
    assert len(ids) == len(set(ids)), "duplicate archive ids"
    assert len(filenames) == len(set(filenames)), "duplicate archive filenames"


def test_new_entries_present_hashed_and_claimed_by_at_least_one_sku():
    data = _load_manifest()
    by_id = {a["id"]: a for a in data["archives"]}
    for ident in EXTENDED_IDS:
        assert ident in by_id, f"missing extended archive {ident}"
        a = by_id[ident]
        assert SHA256_RE.match(a["sha256"]), f"{ident} must carry a real sha256"
        assert a["url"].startswith("https://download.kiwix.org/zim/")
        assert a["url"].endswith(a["filename"])
        assert a["size_bytes"] > 1024 * 1024
        assert a["required_for_skus"], f"{ident} must be served by at least one SKU"
        assert a["tier"] in (0, 1, 2), f"{ident} tier out of catalog range"


def test_variant_skus_exist_and_profiles_fit_drive_budgets():
    """Drive-size separation (john 2026-11-06): 32GB = tier 0 only,
    tier 1 & tier 2 get a variant per drive size."""
    products = {p["sku"]: p for p in
                json.loads(PRODUCTS_MANIFEST.read_text())["products"]}
    for sku in ALL_SKUS:
        assert sku in products, f"missing SKU {sku}"
    p1 = products["Product1"]
    assert p1["target_drive_size_gb"] == 32
    assert p1["tiers"] == [0], "32 GB drive can only be tier 0"
    for sku in ("Product2", "Product3"):
        assert products[sku]["target_drive_size_gb"] == 64
        assert products[f"{sku}-256"]["target_drive_size_gb"] == 256

    zims = {a["filename"]: a for a in _load_manifest()["archives"]}
    models = {m["filename"]: m for m in
              json.loads(MODELS_MANIFEST.read_text())["models"]}
    for sku, p in products.items():
        assert p["max_payload_bytes"] > 0
        full = p["payload_profiles"]["full"]
        assert full["total_bytes"] <= p["max_payload_bytes"], \
            f"{sku} full profile exceeds drive budget"
        assert full["zim_archives"], f"{sku} full profile has no zim archives"
        for f in full["zim_archives"]:
            assert f in zims, f"{sku} references unknown zim {f}"
        mmproj_files = {m["mmproj"] for m in models.values() if m.get("mmproj")}
        for mf in full["models"]:
            assert mf in models or mf in mmproj_files, \
                f"{sku} references unknown model {mf}"
        # every referenced archive must list this SKU (planner sync check)
        for f in full["zim_archives"]:
            assert sku in zims[f]["required_for_skus"], \
                f"{f} not marked required_for {sku}"
    # LLM ladder: higher tiers have strictly more model variety
    assert len(products["Product1"]["payload_profiles"]["full"]["models"]) <= \
        len(products["Product2-256"]["payload_profiles"]["full"]["models"]) <= \
        len(products["Tier4"]["payload_profiles"]["full"]["models"])


def test_required_for_skus_are_subset_of_known_sku_set():
    data = _load_manifest()
    models = json.loads(MODELS_MANIFEST.read_text())["models"]
    for a in data["archives"]:
        bad = set(a["required_for_skus"]) - ALL_SKUS
        assert not bad, f"{a['id']} lists unknown SKUs {bad}"
    for m in models:
        bad = set(m.get("required_for_skus", [])) - ALL_SKUS
        assert not bad, f"model {m['filename']} lists unknown SKUs {bad}"


def test_existing_baseline_entries_untouched():
    """The original 12 shipped archives keep their ids."""
    data = _load_manifest()
    ids = {a["id"] for a in data["archives"]}
    for ident in [
        "zimgit-water", "zimgit-medicine", "wikipedia-medicine-mini",
        "wikipedia-top-mini", "zimgit-food-preparation", "mdwiki-en",
        "wikipedia-simple-nopic", "wikibooks-en-maxi", "wikipedia-medicine-maxi",
        "zimgit-post-disaster", "wikipedia-en-all-nopic", "wikipedia-en-all-maxi",
    ]:
        assert ident in ids


def test_fetch_assets_load_manifests_still_works():
    mod = _load_fetch_assets_module()
    manifests = mod.load_manifests(ROOT)
    assert len(manifests["archives"]) >= 50
    assert all("filename" in z for z in manifests["archives"])
