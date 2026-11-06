# Offline Content Catalog — Expansion (2026-11-04, revised 2026-11-06)

what changed: `manifests/zim.json` grew from 12 to 54 archives (+42), all
sourced from the live kiwix/openZIM catalog.

2026-11-06 revision (john's direction): the catalog is now integrated with
the drive-size SKU ladder. content is fitted per **drive size** — 32 GB /
64 GB / 256 GB — via a priority-ordered greedy fill of the manifest
(`provisioning/tools/plan_tier_payloads.py --apply` regenerates everything).
the LLM + swarm stack remains the tier differentiator: lower tiers skimp on
LLM variety, tier 2+ and the swarm tiers ramp the model ladder.

## drive-size SKU ladder

| SKU | drive | zim archives | models | full payload | budget |
|---|---|---|---|---|---|
| Product1 (tier 0) | 32 GB | 26 | 3 files (micro: 135M/0.5B) | ~28.5 GB | 29 GB |
| Product2 (tier 1) | 64 GB | 43 | +1.5B, Phi-3.5 | ~58.5 GB | 59 GB |
| Product2-256 (tier 1) | 256 GB | 53 | same as Product2 | ~160 GB | 230 GB |
| Product3 (tier 2) | 64 GB | 37 | +3B, Qwen2-VL (+mmproj) | ~58.8 GB | 59 GB |
| Product3-256 (tier 2) | 256 GB | 53 | +7B, gemma-2-9B | ~175 GB | 230 GB |
| Tier3 (tier 3) | 256 GB | 53 | +Qwen2.5-32B (swarm) | ~195 GB | 230 GB |
| Tier4 (tier 4) | 512 GB | 54 | +Llama-3.3-70B | ~357 GB | 460 GB |

rules encoded in the planner:

- **32 GB drives can only be tier 0** — tier 1 starts at 64 GB.
- **tier 1 and tier 2 each get a variant per drive size** (64 GB and 256 GB);
  the 256 GB variants fit everything below the 110 GiB illustrated Wikipedia.
- **fit as much data as possible on every tier**; the 256 GB tier-1 variant
  trades model variety for content (models stay at the 64 GB tier-1 rung).
- **Product3-64 leads with `wikipedia-en-all-nopic`** (the 49 GiB complete
  wikipedia IS the tier-2 differentiator, then fills around it).
- illustrated Wikipedia (`wikipedia-en-all-maxi`, 110 GiB) is tier-4
  exclusive — no smaller SKU can carry it alongside anything else.
- tiers 0–2 with 64 GB drives: full tier-1 and tier-2 runs have ~0.2–0.4 GiB
  slack — the ladder is genuinely budget-bound at 32/64 GB.

content priority order (greedy): essentials (water/food/medicine/minis) →
prepper/community → stackexchange → repair/appropriate-tech/education →
heavy manuals (armypubs) + maps → complete wikipedia → illustrated wikipedia.
see `PRIORITY_ORDER` in `plan_tier_payloads.py`; per-archive membership lives
in `required_for_skus` on each zim + model entry, refreshed by `--apply`.

## what's in the expansion

- **maps**: OSM country map zims (united-states 15.8GB, canada 10.4GB) —
  browsable in kiwix-serve like any other zim, zero new serving infra.
- **manuals / military pubs**: armypubs_en_all (7.9GB, US-gov public domain),
  FAS military-medicine reference.
- **engineering / appropriate tech**: cd3wd (541MB), appropedia maxi,
  energypedia, 100r.co (hundred rabbits), solar low-tech magazine.
- **medical**: medlineplus, mdwiki maxi, NHS medicines A-to-Z, CDC travelers'
  health, quick-guides-for-medicine.
- **prepper / community**: trueprepper, canadian-prepper bugout roll,
  urban prepper, S2 Underground, learning-self-reliance, ready.gov (EN+ES).
- **repair**: iFixit English (3.4GB), restarters wiki.
- **education**: libretexts (chem/phys/bio/med/k12), phet sims, wikiversity.
- **Q&A depth**: stackexchange zims — diy, electronics, outdoors, woodworking,
  mechanics, engineering, arduino, 3dprinting, gis.
- **software stack**: devdocs linux man pages.

full list w/ sizes + descriptions: see `manifests/zim.json`.

## provenance & integrity

- sizes come from download.kiwix.org/library/library_zim.xml (2026-11-04).
- sha256 for every new entry comes from the official `.zim.sha256` sidecar
  published next to each zim on the kiwix mirror — no download needed to pin.
- entries are `verified_local: false` until actually staged; fetch_assets.py
  verifies magic header + sha256 on download as before.

## regenerating

- `provisioning/tools/plan_tier_payloads.py` (no args) prints the capacity
  analysis; `--apply` recomputes all SKU full profiles, re-tiers
  `zim.json` archives, and syncs `required_for_skus` in zim + models
  manifests. idempotent.
- `provisioning/tools/refresh_zim_catalog.py` re-fetches the live kiwix
  catalog and appends any selection additions (idempotent on filenames,
  never touches existing entries). new entries land as tier 0 / all-SKUs
  and get re-normalized by the planner on its next `--apply`. edit the
  `SELECTION` list to grow the catalog.
