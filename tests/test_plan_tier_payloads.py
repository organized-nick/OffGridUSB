"""Tests for provisioning/tools/plan_tier_payloads.py (per-drive-size planner)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_planner():
    spec = importlib.util.spec_from_file_location(
        "plan_tier_payloads", ROOT / "provisioning" / "tools" / "plan_tier_payloads.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_priority_order_references_known_archives():
    planner = _load_planner()
    import json
    zims = json.loads((ROOT / "manifests" / "zim.json").read_text())
    ids = {a["id"] for a in zims["archives"]}
    for zid in planner.PRIORITY_ORDER:
        assert zid in ids, f"priority list references unknown archive {zid}"


def test_sku_budgets_match_drive_geometry():
    planner = _load_planner()
    for sku, (_, budget, _, _) in planner.SKUS.items():
        min_cap, max_pay, _ = planner.DRIVE_GEOMETRY[sku]
        assert max_pay == budget, f"{sku}: SKUS budget must equal DRIVE_GEOMETRY max_payload_bytes"
        assert min_cap > max_pay, f"{sku}: min drive capacity must exceed payload budget"


def test_greedy_fill_respects_budget():
    planner = _load_planner()
    import json
    zims = json.loads((ROOT / "manifests" / "zim.json").read_text())
    models = json.loads((ROOT / "manifests" / "models.json").read_text())
    zims_by_id = {a["id"]: a for a in zims["archives"]}
    models_by_file = planner.build_model_index(models)
    for sku, (label, budget, tier, model_files) in planner.SKUS.items():
        chosen, model_bytes, used, slack = planner.compute_variant(
            zims_by_id, planner.PRIORITY_ORDER, budget, model_files, models_by_file)
        assert model_bytes + used <= budget, f"{sku}: greedy fill overran budget"
        assert chosen, f"{sku}: greedy fill chose nothing"
        assert all(z in chosen for z in chosen), "duplicates in fill"


def test_model_ladder_monotonic():
    """john 2026-11-06: skimp LLM variety on lower tiers; LLM+swarm are
    the differentiators for higher tiers."""
    planner = _load_planner()
    ladder = {sku: tuple(files) for sku, (_, _, _, files) in planner.SKUS.items()}
    order = ["Product1", "Product2", "Product3"]
    for prev, nxt in zip(order, order[1:]):
        assert set(ladder[prev]) <= set(ladder[nxt]), \
            f"model ladder not monotonic: {prev} -> {nxt}"
    assert "qwen2.5-32b-instruct-q4_k_m.gguf" in ladder["Product3"]
    assert len(ladder["Product1"]) < len(ladder["Product3"]), "tier 0 must not carry the top LLM variety"


def test_sku_set_matches_agents_md_product_list():
    """AGENTS.md (post-2026-11-16 revert) defines exactly three USB SKUs:
    Product1 (64 GB AI-free), Product2 (64 GB with AI), Product3 (256 GB swarm)."""
    planner = _load_planner()
    assert set(planner.SKUS) == {"Product1", "Product2", "Product3"}
    assert planner.DRIVE_GEOMETRY["Product1"][2] == 64
    assert planner.DRIVE_GEOMETRY["Product2"][2] == 64
    assert planner.DRIVE_GEOMETRY["Product3"][2] == 256
    assert planner.SKUS["Product1"][3] == [], "Product1 must be AI-free"
    assert not planner.VARIANT_PARENTS, "no -256 drive-ladder variants per AGENTS.md"
