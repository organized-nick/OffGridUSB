# repo audit vs AGENTS.md — 2026-11-15

one-off audit run (dude, discord-invoked) against AGENTS.md @ 2e7668c.
scope: tasks.md task 1 (a. products/provisioning, b. UI, c. README, d. PRD).
verdict codes: 🔴 divergent / 🟡 out-of-sync (known flag confirmed) / 🟢 aligned.

## a. product list + provisioning

- 🟢 `manifests/products.json` matches the new ladder: Product1 (32 GB), Product2 (64),
  Product3 (64), Tier3 (256), Tier4 (512), plus Product2-256 / Product3-256.
  planner `SKUS` map agrees with products.json drive sizes.
- 🟢 `plan_tier_payloads.py` is wired as the generator; AGENTS.md rule 2 satisfied.
- 🔴 **Product1 drive size conflict**: AGENTS.md product list says launch products are
  64/64/256 GB, but planner + products.json define Product1 on **32 GB**. also AGENTS.md
  itself says "64 gig USB: AI free" while products.json Product1 is the AI-free SKU on 32 GB.
  needs a john decision: is Product1 32 GB (keep planner) or 64 GB (re-run planner)?
- 🔴 **payload planners aside — product list omits the -256 variants**: Product2-256 /
  Product3-256 exist in products.json + planner but aren't mentioned in AGENTS.md product list.
- 🟡 committed `manifests/product_sku.json` still says Product2/fieldready with
  `target_drive_size_gb: 32` while products.json defines Product2 as 64 GB — stale runtime
  descriptor (flagged in AGENTS.md, still true). regenerating at next provisioning run fixes it.
- 🟢 provisioning engine pair ps1/sh present, wrappers + mirrored wrappers present,
  lib modules all match AGENTS.md's list. no `provisioning/` files staged for USB.
- 🟢 provision_usb.ps1/sh alignment looks maintained (recent commits touched both).

## b. UI (web/static)

- 🔴 **calculator tab still live**: `index.html` `#nav-calc` tab + `js/app.js` feature gating
  includes `survival_calculators` as an active feature. task 3d removes calculators — UI
  must be cut alongside the module.
- 🔴 **removed-feature names still gated in UI lists**: `settlement_hub`, `lora_mesh_agent`,
  `lan_mesh_rpc`, `distillation_on_dock` appear in the feature-register lists in app.js
  (both copies: web/static/app.js and web/static/js/app.js — note the repo has TWO app.js
  copies that must be kept in sync; currently identical but a drift risk).
- 🔴 `res.queued_for_distillation` + `needs_distillation` badges still surfaced in UI
  (`app.js` ~1435, ~2592) — conflicts with task 5 reframe (session history with pinning).
- 🟢 offline maps, library tab, safe-eject header, matrix theme all match AGENTS.md.
- 🟢 wasm fallback present (`web/static/wasm/chromebook.html` + vendored pmtiles/maplibre).

## c. README (root)

- 🔴 **tier table completely stale** (lines ~50-55): 8 GB Product1, 32 GB Product2,
  128 GB Product3, 256 GB Tier3, 512 GB Tier4 — the pre-planner ladder. products.json is
  source of truth (32/64/64/256/512 + -256 variants). README also advertises calculator
  features per-SKU and "Interactive STEM Practice Tutor" (task 3b cut).
- 🔴 Tier4 SettlementHub row still advertises "Multi-GPU Settlement Hub, Distillation-on-Dock,
  LoRa / Meshtastic query gateway" — all slated for removal per task 3.
- 🔴 provisioning quick-commands reference "8 GB", "32 GB", "128 GB" targets — stale.
- 🟢 factory-vs-customer separation section matches AGENTS.md two-halves rule.

## d. PRD (docs/PRD_ARD.md)

- 🔴 **feature register desync confirmed**: module docstrings reference F-08, F-13…F-16,
  F-29…F-36, F-41; grep of PRD_ARD.md shows zero F-XX IDs. the register is entirely
  out of sync with the code (AGENTS.md "Other known gaps" confirmed).
- 🔴 PRD still describes calculators, mesh, settlement hub as features (per
  CONTENT_CATALOG + PRD wording) — needs the task-3 removals reflected after they land.

## cross-cutting

- 🔴 dual `web/static/app.js` + `web/static/js/app.js` (and index.html/style.css shipped
  twice?) — two copies of the UI source in repo. if one is a build artifact, document;
  if both are edited, they will drift.
- 🟢 tests: `tests/test_plan_tier_payloads.py` + `tests/test_zim_catalog_expansion.py`
  green (11 passed) on rebased main.

## recommended fix order (follow-up tasks)

1. john decides drive ladder (32 vs 64 GB Product1) → regenerate products.json if needed.
2. task 3 removals land → then sweep UI lists, README tier table, PRD, provisioning/README
   in one alignment commit (prose-only; planner untouched).
3. regenerate product_sku.json at next factory run to clear the stale descriptor.
4. collapse the dual app.js / ui-source duplication.

---

## RESOLUTION PASS — 2026-11-15 (same PR, self-contained)

john's ruling: AGENTS.md is #1 source of truth. Product1 = 64 GB, **no 32 GB tiers
anymore**. Resolved in this PR:

- planner: `SKUS["Product1"]` → 64 GB drive, tier 0, **empty model list** (AI-free per
  AGENTS.md); `DRIVE_GEOMETRY["Product1"]` → (61 GB min, 59 GB budget, 64).
- `manifests/products.json` regenerated via `plan_tier_payloads.py --apply` (full
  profiles recomputed); Product1 top-level metadata updated (64 GB / 61 GB min /
  active_features minus grounded_ai_professor / lean profile now ZIM-only).
- `manifests/zim.json` + `manifests/models.json` required_for_skus re-synced by planner.
- Product1 provisioning: `provision_product1_pocketsurvival.ps1` header,
  `provision_usb.ps1` SKU inventory/menu strings, `provision_usb.sh` sku table/menu,
  `lib/SafetyValidator.ps1` Product1 capacity + labels + 29→59 GiB clamp comments.
- `manifests/product_sku.json` refreshed to Product2 @ 64 GB (61 GB min).
- README tier table rewritten against planner output (64/64/64/256/512 + -256 variants,
  no calculators / distillation-on-dock / LoRa claims in active feature columns).
- provisioning/README.md SKU table rewritten (7 SKUs incl. -256 variants).
- PRD: Appendix A feature register added — maps F-04…F-41 docstring IDs to code
  anchors; F-19..F-24 / F-37..F-40 flagged as no-code-anchor PRD-era IDs.
- AGENTS.md updated per standing orders: product list gains Product3 + -256 variants +
  "no 32 GB tiers" rule; out-of-sync flags section marked resolved with pointers to
  what stays open (task 3 UI gating).
- tests: `test_zim_catalog_expansion.py` drive-ladder assertions updated to the new
  ladder + new assertion that Product1 full profile ships zero models. suite green:
  352 passed, same 16 pre-existing opaque-e2e/environment failures as main baseline
  (zero regressions introduced).
