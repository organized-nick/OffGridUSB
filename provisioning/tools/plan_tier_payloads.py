#!/usr/bin/env python3
"""plan_tier_payloads.py - Per-drive-size payload planner for OffGridUSB SKUs.

Reads manifests/zim.json + manifests/models.json, computes which archives
fit on each SKU drive-size variant (32GB / 64GB / 256GB) via greedy
priority-ordered fill, and reports the space analysis.

Modes:
  default      print the capacity analysis (no files modified)
  --apply      write computed full-profile content lists into
               manifests/products.json and sync required_for_skus in
               manifests/zim.json + manifests/models.json

Design (john 2026-11-06):
  - drive ladder: 32GB (tier 0 only), 64GB, 256GB
  - tier 1 starts at 64GB; Product2-256 fits everything below illustrated wiki
  - tier 2 has a variant per drive size it fits (64GB, 256GB)
  - skimp LLM variety on lower tiers; models are the tier 2+/swarm differentiator
"""

import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFESTS = os.path.abspath(os.path.join(HERE, "..", "..", "manifests"))
GIB = 1024 ** 3

# Content priority order: essentials -> prepper -> stackexchange -> repair /
# appropriate-tech -> education -> heavy manuals & maps -> full wikipedia.
# Product3-64 overrides with the complete-wikipedia zim first (that IS tier 2).
PRIORITY_ORDER = [
    "zimgit-water", "zimgit-medicine", "zimgit-food-preparation",
    "wikipedia-medicine-mini", "wikipedia-top-mini",
    "quickguides-medicine-en", "nhs-medicines-en", "cdc-travelers-health-en",
    "fas-military-medicine-en", "zimgit-post-disaster",
    "worldfactbook-en-all", "readygov-en-all", "readygov-es-all",
    "wikipedia-medicine-maxi", "wikipedia-simple-nopic",
    "mdwiki-en", "medlineplus-en-all", "mdwiki-en-maxi",
    "trueprepper-en-all", "urban-prepper-en-all", "lrnselfreliance-en-all",
    "s2underground-en-all", "canadian-prepper-bugoutroll-en",
    "se-diy-en-all", "se-electronics-en-all", "se-outdoors-en-all",
    "se-mechanics-en-all", "se-woodworking-en-all", "se-engineering-en-all",
    "se-arduino-en-all", "se-3dprinting-en-all", "se-gis-en-all",
    "restarters-en-maxi", "ifixit-en-all", "devdocs-man-en",
    "appropedia-en-maxi",
    "cd3wd-en-all", "energypedia-en-nopic", "lowtech-solar-en",
    "100r-co-en-all", "osm-wiki-en-nopic",
    "phet-en-all", "wikiversity-en-nopic", "libretexts-k12-en",
    "libretexts-phys-en", "libretexts-chem-en", "libretexts-bio-en",
    "libretexts-med-en", "wikibooks-en-maxi",
    "armypubs-en-all", "maps-usa-en", "maps-canada-en",
    "wikipedia-en-all-nopic",
    "wikipedia-en-all-maxi",
]

TIER2_HEAD_START = ["wikipedia-en-all-nopic"]

# SKU -> (drive label, max_payload_bytes, tier, [model filenames])
# Model ladder: micro -> micro+1.5B/Phi -> +3B/VL -> +7B/9B -> +32B -> +70B.
SKUS = {
    "Product1":    ("32GB USB 3.2 Flash Drive", 29_000_000_000, 0, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
    ]),
    "Product2":    ("64GB USB 3.2 Flash Drive", 59_000_000_000, 1, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
    ]),
    "Product2-256": ("256GB Portable SSD", 230_000_000_000, 1, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
    ]),
    "Product3":    ("64GB USB 3.2 Flash Drive", 59_000_000_000, 2, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
        "llama-3.2-3b-instruct-q4_k_m.gguf",
        "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        "mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
    ]),
    "Product3-256": ("256GB Portable SSD", 230_000_000_000, 2, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
        "llama-3.2-3b-instruct-q4_k_m.gguf",
        "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        "mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
        "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "gemma-2-9b-it-Q4_K_M.gguf",
    ]),
    "Tier3":       ("256GB Portable SSD", 230_000_000_000, 3, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
        "llama-3.2-3b-instruct-q4_k_m.gguf",
        "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        "mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
        "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "gemma-2-9b-it-Q4_K_M.gguf",
        "qwen2.5-32b-instruct-q4_k_m.gguf",
    ]),
    "Tier4":       ("512GB NVMe SSD", 460_000_000_000, 4, [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
        "llama-3.2-3b-instruct-q4_k_m.gguf",
        "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        "mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
        "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "gemma-2-9b-it-Q4_K_M.gguf",
        "qwen2.5-32b-instruct-q4_k_m.gguf",
        "llama-3.3-70b-instruct-q4_k_m.gguf",
    ]),
}

# Variants that share a base SKU content ladder (256GB variants add the
# next model rung on top of their 64GB sibling). Kept as data for the
# required_for_skus model sync below.
VARIANT_PARENTS = {
    "Product2-256": "Product2",
    "Product3-256": "Product3",
}

# per-SKU drive geometry: (min_drive_capacity_bytes, max_payload_bytes,
# target_drive_size_gb). Budgets in SKUS must match max_payload_bytes here.
DRIVE_GEOMETRY = {
    "Product1":     (30_500_000_000, 29_000_000_000, 32),
    "Product2":     (61_000_000_000, 59_000_000_000, 64),
    "Product2-256": (245_000_000_000, 230_000_000_000, 256),
    "Product3":     (61_000_000_000, 59_000_000_000, 64),
    "Product3-256": (245_000_000_000, 230_000_000_000, 256),
    "Tier3":        (240_000_000_000, 230_000_000_000, 256),
    "Tier4":        (480_000_000_000, 460_000_000_000, 512),
}


def load_manifest(name):
    with open(os.path.join(MANIFESTS, name)) as f:
        return json.load(f)


def build_model_index(models_manifest):
    """filename -> model entry, with mmproj companion files exposed as
    synthetic entries so planner code can account for projector bytes."""
    idx = {m["filename"]: dict(m) for m in models_manifest["models"]}
    for m in models_manifest["models"]:
        if m.get("mmproj"):
            idx[m["mmproj"]] = {
                "filename": m["mmproj"],
                "size_bytes": m.get("mmproj_size_bytes", 0),
                "_synthetic_mmproj_of": m["filename"],
            }
    return idx


def compute_variant(zims_by_id, order, budget_bytes, model_files, models_by_file):
    """Greedy priority-ordered fill: reserve model space, then add zims
    (largest-fits-last within the priority order) while they fit."""
    model_bytes = sum(models_by_file[f]["size_bytes"] for f in model_files)
    remaining = budget_bytes - model_bytes
    chosen = []
    used = 0
    for zid in order:
        z = zims_by_id.get(zid)
        if z is None or z in chosen:
            continue
        if used + z["size_bytes"] <= remaining:
            chosen.append(z)
            used += z["size_bytes"]
    return chosen, model_bytes, used, remaining - used


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write computed content lists back into the manifests")
    args = ap.parse_args()

    zims = load_manifest("zim.json")
    models = load_manifest("models.json")
    zims_by_id = {a["id"]: a for a in zims["archives"]}
    models_by_file = build_model_index(models)

    missing = [zid for zid in PRIORITY_ORDER if zid not in zims_by_id]
    if missing:
        print(f"ERROR: priority list references unknown archive ids: {missing}",
              file=sys.stderr)
        return 1

    results = {}
    for sku, (label, budget, tier, model_files) in SKUS.items():
        order = list(PRIORITY_ORDER)
        if sku in ("Product3", "Product3-256"):
            # tier 2 differentiator is the complete wikipedia; lead with it
            for zid in reversed(TIER2_HEAD_START):
                order.remove(zid)
                order.insert(0, zid)
        chosen, mb, zb, slack = compute_variant(
            zims_by_id, order, budget, model_files, models_by_file)
        results[sku] = dict(label=label, tier=tier, budget=budget,
                            zims=chosen, models=model_files,
                            zims_bytes=zb, models_bytes=mb,
                            total=zb + mb, slack=slack + 0)
        print(f"{sku:14s} tier{tier} {label:28s} "
              f"zims {len(chosen):2d} ({zb/GIB:6.2f} GiB) + "
              f"models {len(model_files):2d} ({mb/GIB:5.2f} GiB) = "
              f"{(zb+mb)/GIB:7.2f} GiB / {budget/GIB:5.1f} GiB budget "
              f"(slack {slack/GIB:5.2f} GiB)")

    if args.apply:
        apply_results(results, zims, models)
        print("applied to manifests/products.json, manifests/zim.json, manifests/models.json")
    return 0


def apply_results(results, zims, models):
    products_path = os.path.join(MANIFESTS, "products.json")
    with open(products_path) as f:
        products = json.load(f)
    products_by_sku = {p["sku"]: p for p in products["products"]}

    # create 256GB variant SKUs as deep copies of their 64GB base SKU first,
    # so the profile-writing pass below covers every SKU uniformly
    for sku, r in results.items():
        parent_sku = VARIANT_PARENTS.get(sku)
        if parent_sku is None:
            continue
        if sku not in products_by_sku:
            v = copy.deepcopy(products_by_sku[parent_sku])
            v["sku"] = sku
            v["name"] = products_by_sku[parent_sku]["name"] + " (256 GB Drive Edition)"
            v["tagline"] = (products_by_sku[parent_sku]["tagline"]
                            + " \u2014 256 GB extended storage variant")
            products["products"].append(v)
            products_by_sku[sku] = v

    # sync required_for_skus: reset both manifests and derive membership
    # purely from the planner results
    for a in zims["archives"]:
        a["required_for_skus"] = []
    for m in models["models"]:
        m["required_for_skus"] = []

    for sku, r in results.items():
        for z in r["zims"]:
            z["required_for_skus"].append(sku)
        for mf in r["models"]:
            if mf.startswith("mmproj-"):
                continue  # projector bytes tracked via its VL model entry
            entry = next((m for m in models["models"] if m["filename"] == mf), None)
            if entry is None:
                raise SystemExit(f"model {mf} missing from models.json")
            if sku not in entry["required_for_skus"]:
                entry["required_for_skus"].append(sku)

    # write per-SKU product entries (drive geometry + full profile)
    for sku, r in results.items():
        p = products_by_sku.get(sku)
        if p is None:
            raise SystemExit(f"SKU {sku} not found in products.json")
        p["tiers"] = list(range(0, r["tier"] + 1))
        p["target_drive_type"] = r["label"]
        min_cap, max_pay, drive_gb = DRIVE_GEOMETRY[sku]
        p["min_drive_capacity_bytes"] = min_cap
        p["max_payload_bytes"] = max_pay
        p["target_drive_size_gb"] = drive_gb
        profiles = p.setdefault("payload_profiles", {})
        full = profiles.get("full", {})
        full["models"] = list(r["models"])
        full["zim_archives"] = [z["filename"] for z in r["zims"]]
        full["total_bytes"] = r["total"]
        full["total_gb"] = round(r["total"] / 1e9, 2)
        full["description"] = (
            f"Full payload for {r['label']}: {len(r['zims'])} zim archives "
            f"({r['zims_bytes']/GIB:.1f} GiB) + {len(r['models'])} model files "
            f"({r['models_bytes']/GIB:.1f} GiB), priority-ordered greedy fill "
            f"of the manifest (planner: provisioning/tools/plan_tier_payloads.py)"
        )
        profiles["full"] = full

    # re-tier archives: tier = lowest tier of any SKU that carries the archive
    tier_ladder = {sku: r["tier"] for sku, r in results.items()}
    for a in zims["archives"]:
        skus = a["required_for_skus"]
        a["tier"] = min((tier_ladder[s] for s in skus if s in tier_ladder),
                        default=2) if skus else 2

    with open(os.path.join(MANIFESTS, "zim.json"), "w") as f:
        json.dump(zims, f, indent=2)
        f.write("\n")
    with open(os.path.join(MANIFESTS, "models.json"), "w") as f:
        json.dump(models, f, indent=2)
        f.write("\n")
    with open(products_path, "w") as f:
        json.dump(products, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
