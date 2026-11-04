"""Tests for the extended offline-content catalog (manifests/zim.json).

Verifies the content-catalog expansion PR contract:
- every archive entry is schema-complete and well-formed
- the 2026-11-04 extended content set exists and is available on ALL SKUs
  (product direction: content is not a tier differentiator — LLM + swarm is)
- fetch_assets.load_manifests() still parses the manifest cleanly
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIM_MANIFEST = ROOT / "manifests" / "zim.json"

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

ALL_SKUS = {"Product1", "Product2", "Product3", "Tier3", "Tier4"}

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


def test_new_entries_present_tier0_all_skus_and_hashed():
    data = _load_manifest()
    by_id = {a["id"]: a for a in data["archives"]}
    for ident in EXTENDED_IDS:
        assert ident in by_id, f"missing extended archive {ident}"
        a = by_id[ident]
        assert a["tier"] == 0, f"{ident} must be tier 0 (content on all tiers)"
        assert set(a["required_for_skus"]) == ALL_SKUS, f"{ident} must serve every SKU"
        assert SHA256_RE.match(a["sha256"]), f"{ident} must carry a real sha256"
        assert a["url"].startswith("https://download.kiwix.org/zim/")
        assert a["url"].endswith(a["filename"])
        assert a["size_bytes"] > 1024 * 1024


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
