# AGENTS.md — OffGridUSB Development Guide


## What this repo is

OffGridUSB is a standalone, air-gapped USB drive product: a portable webserver serving
local Kiwix (ZIM) knowledge content plus local LLM capability (llama.cpp / GGUF) for
working with that data. It also supports llama.cpp **RPC** so multiple computers on the
same LAN can share inference (swarm / cluster mode). The product ships on **64 GB or
256 GB** drives (see "Out-of-sync flags" below regarding other sizes that appear in docs).

Two strictly separated halves live in this repo:

- **Factory suite (`provisioning/`)** — host-only. Never staged onto customer drives.
- **Customer USB runtime** — `bin/`, `data/`, `manifests/`, `src/`, `web/`, launchers,
  `USER_GUIDE.md`. Copied to the drive by provisioning.

## STANDING ORDERS
keep this file up-to-date, when any changes to the repo are requested that conflict with this file's directives, flag it, and ensure that the file is updated to reflect reality in all cases.

## Git usage

This is a multi-agent project. always check the origin before making extensive changes, others may have pushed work that should be considered to avoid duplicating efforts.

origin/main is our trunk branch, all work should be committed to it. never force-push. prefer rebase over merge commit.

## Product list

These are the products that will go to production at launch.

- Online download: download runtime as a standalone package
- 64 gig USB: AI free zim version, assembled via the info priorities in the provisioning script, no AI features included
- 64 gig USB: zim version WITH AI models (note: should be straight superset info-wise as the 0 AI version, leave space on 0 AI if you need to
- 256 gig USB: more info + models + swarm functionality

## Feature list (by product)

All features below are implemented in the codebase today unless noted. Features are
listed under the first (cheapest) product that supports them; every product is a
superset of the ones above it in this list.

### All products (Online download, 64 gig USB AI-free, 64 gig USB with AI, 256 gig USB)

- Offline Kiwix reader (`kiwix_reader`) — implemented. `ai/model_runner.py` manages
  kiwix-serve lifecycle on :8081; `data/library.xml` built at provisioning; ZIM reader
  in `knowledge/zim_reader.py`.
- Offline maps — implemented. MapLibre + pmtiles vendored in `web/static/vendor/maps/`;
  `/api/maps` + `/api/maps/search` (gazetteer) in `web/app.py`.
- Anti-counterfeit integrity canary — implemented. Launchers probe
  `data/.integrity_canary`; checks in `provisioning/tools/check_integrity.*`.
- Safe eject/shutdown — implemented. `core/usb_eject.py` +
  `trigger_safe_shutdown_and_eject()`, client heartbeat/tab-close grace.
- WASM fallback UI — implemented. `web/static/wasm/chromebook.html` + `wasm_runner.js`;
  served as fallback root page for browser-only hosts.

### Online download (runtime package) — same feature set as 64 gig USB AI-free

- Shipped as a standalone package instead of flashed media; content assembly follows
  the same provisioning priorities as the AI-free USB build.

### 64 gig USB — AI-free zim edition

- Same as "all products" above. No models, no llama-server; calculators run in
  deterministic mode.

### 64 gig USB — with AI models

- Everything above, plus:
- Local LLM serving + model boot guard — implemented. llama-server lifecycle on :8082,
  boot guard (`test_model_boot_guard.py`), model files ship in `data/models/`.
- Grounded AI professor / RAG chat (`grounded_ai_professor`) — implemented.
  `handle_ask()` in `web/app.py` + `knowledge/grounding_harness.py` (728 lines) with
  citations from ZIMs/seed corpus.
- STEM tutor (`stem_tutor`) — implemented. `knowledge/khan_curriculum.py` (472 lines)
  with seeded lessons, instantiated in the runtime.
- Memory vault (`memory_vault`) — implemented. `memory/memory_vault.py` (645 lines):
  SQLite + FTS5 search, seeded field-history entries, `data/vault/memory.sqlite` ships
  on drive.
- Photo/OCR vault (`photo_ocr_vault`) — implemented. `vision/visual_vault.py` (514
  lines): pure-Python EXIF/GPS parsing, observation extraction via
  `extract_visual_observation()`.
- Wikipedia RAG (`wikipedia_rag`) — implemented in the harness, validated mainly on
  mini ZIMs; full large-Wikipedia retrieval performance untested in-repo
  (task 4 in `tasks.md`).

### 256 gig USB

- Everything above, plus:
- Multi-model hardware auto-selector (`multi_model_auto_selector`) — implemented.
  `core/hardware_probe.py` (497 lines): CPU probing (incl. Windows registry, WASM
  profiles), dynamic tier selection, mock profiles for testing.
- Swarm cluster / LAN mesh RPC (`swarm_cluster`, `lan_mesh_rpc`) — implemented and the
  most heavily tested subsystem: `swarm/runtime.py` (863 lines, exo P2P ring),
  `inference.py` (distributed inference orchestration), `watchdog.py` (peer
  health/recovery), `cluster_sim.py` (RPC ring coordinator); ~8 test files cover
  membership, self-filtering, runtime, watchdog, inference. Live runs documented in
  `docs/two-machine-swarm-test.md` and `docs/live-rpc-inference-run.md`.
- Session history & distillation (`distillation_on_dock`) — implemented at unit level:
  `run_distillation_on_dock()` in `memory_vault.py` upgrades low-tier drafts queued as
  `needs_distillation=1` using a stronger model callback. Product direction (task 5 in
  `tasks.md`): reframe as session-history viewing with pinning; the "docking" concept
  goes away.

### Slated for removal (per `tasks.md` task 3)

These are referenced in the catalog/docs but are being dropped from the repo:

- Settlement hub (`settlement_hub`) — no dedicated module; umbrella concept only.
- Interactive STEM practice tutor — remove the interactive-lesson portion; Khan
  curriculum content stays viewable.
- Survival calculators (`survival_calculators`) — fully implemented, but cut from the
  product: `src/emyrge/calculators/`, `run_calculator()` in `web/app.py`, related UI
  and tests go.
- ESP32/LoRa thin-client mesh — protocol-complete, hardware-untested:
  `mesh/esp32_protocol.py` + `mesh/packet_chunker.py` (stub),
  `handle_mesh_command()`, calculator `format_mesh_summary()`.

### Other known gaps

- Feature register: module docstrings reference PRD feature IDs (F-09 … F-36) that do
  not appear in `docs/PRD_ARD.md` — register is out of sync with the code.
- Companion task file: `tasks.md` holds the current task list (repo audit vs this
  file, integrity-canary writeup/verdict, removals, validation work).
## Provisioning (factory side)

- Primary engines: `provisioning/provision_usb.ps1` (Windows) and
  `provisioning/provision_usb.sh` (Linux/macOS). These **must stay aligned in
  functionality** — any feature added to one must be mirrored in the other.
- Windows entry point: `provisioning/PROVISION_OFFGRID_USB.bat` (interactive wizard).
- 1-Click SKU wrappers exist in `provisioning/` and mirrored in `provisioning/wrappers/`
  (`.bat`/`.ps1`/`.sh` for Product1/2/3).
- `provisioning/lib/` modules: `SafetyValidator.*` (Disk 0 / OS-drive guard, capacity
  checks), `AssetCacheManager.*` (magic-header validation ZIM\x04 / GGUF, cache audit),
  `SkuManifestGenerator.*` (generates `manifests/product_sku.json`),
  `LibraryXmlBuilder.*` (builds `data/library.xml` for staged ZIMs), `UsbStripper.*`
  (staging whitelist / customer-drive hygiene audit, LF enforcement).
- `provisioning/tools/` holds legacy/forensic tooling: capacity probes, integrity
  canary checks, auditors, downloaders, and the payload planner (below).

### Payload planning

`provisioning/tools/plan_tier_payloads.py` reads `manifests/zim.json` +
`manifests/models.json` and generates `manifests/products.json` via a greedy,
priority-ordered fill of content files per SKU/drive size. `--apply` writes the
computed content lists back into `products.json` and syncs `required_for_skus` in
`zim.json` / `models.json`. The `PRIORITY_ORDER` list at the top of that script is the
canonical content priority.

## Manifests

- `manifests/zim.json` — master OpenZIM content catalog: ids, tiers, sizes, sha256,
  magic headers, Kiwix download URLs, `required_for_skus`.
- `manifests/models.json` — master GGUF model catalog: same shape, HF URLs, RAM/context
  requirements.
- `manifests/products.json` — the commercial SKU catalog (Product1 PocketSurvival,
  Product2 FieldReady, Product2-256, Product3 CivilizationArk, Product3-256, Tier3
  SwarmCluster, Tier4 SettlementHub) with tier membership, drive requirements,
  `payload_profiles` (lean/full), and active/hidden feature flags. **Generated by
  `plan_tier_payloads.py` — do not hand-edit sizes/lists; re-run the planner.**
- `manifests/product_sku.json` — see answer below; this is the *runtime* descriptor
  for a provisioned drive, generated by `SkuManifestGenerator.*` at provisioning time.

## Runtime (customer side)

- `src/emyrge/` — pure-stdlib Python package ("emyrge"):
  - `server.py` — loads product_sku.json, server bootstrap helpers.
  - `web/app.py` — Command Center HTTP server (port 8000).
  - `ai/model_runner.py` — llama-server management, model selection.
  - `knowledge/` — zim_reader, seed_corpus, khan_curriculum, grounding harness (RAG).
  - `calculators/` — solar/battery, water purification, medical rehydration,
    electrical formulas (+ source audit).
  - `memory/memory_vault.py` — SQLite semantic memory vault (`data/vault/memory.sqlite`).
  - `vision/visual_vault.py` — photo OCR/EXIF vault.
  - `swarm/` — LAN cluster runtime: `runtime.py`, `inference.py`, `watchdog.py`,
    `cluster_sim.py`; llama.cpp RPC-based multi-machine inference.
  - `mesh/` — ESP32 protocol + packet chunker (meshtastic-style experiment).
  - `core/` — config, hardware probe, USB eject.
- `web/static/` — Command Center UI (index.html, js/app.js, style.css, vendored
  MapLibre + pmtiles for offline maps under `vendor/maps/`, WASM runner).
- Launchers: `START_OFFGRIDUSB_WINDOWS.bat` / `_LINUX.sh` / `_MAC.command` (repo-root
  `run_*` variants are dev/run equivalents). They perform a pre-flight counterfeit-media
  integrity check (`data/.integrity_canary`) before starting services.
- Ports: 8000 Command Center, 8081 kiwix-serve, 8082 llama-server — all loopback-bound.
- `bin/` — vendored cross-platform engines per OS/arch (python, kiwix-tools,
  llama.cpp binaries incl. `ggml-rpc-server`), plus `bin/polyglot/llamafile.exe`.

## Docs & tests

- `docs/` — PRD/ARD, content catalog, hardware/filesystem guide, RPC swarm run logs.
- `USER_GUIDE.md` — customer manual.
- `tests/` — pytest suites (swarm, calculators, planner, e2e tiers);
  `tests/opaque_e2e/` has its own runner for gated air-gap/e2e checks;
  `provisioning/tools/*_testing.*` are dry-run/testing variants of the host tools.

## Development rules

1. Keep `provision_usb.ps1` and `provision_usb.sh` functionally aligned.
2. Regenerate `products.json` via `plan_tier_payloads.py` after changing `zim.json` /
   `models.json` or SKU sizing; never hand-edit its payload lists.
3. `provisioning/` must never be staged onto customer drives (UsbStripper enforces).
4. All runtime bindings stay on loopback; zero telemetry, zero CDN dependencies.
5. New content/models: add to `zim.json` / `models.json` with size, sha256, magic
   header, and `required_for_skus`, then re-run the planner.

## Out-of-sync flags (status as of the 2026-11-15 audit, tasks.md task 1)

All three flags below were **resolved** in PR #21 (drive ladder decided by john:
Product1 = 64 GB AI-free, no 32 GB tiers):

- Drive ladder aligned: `plan_tier_payloads.py` SKUS/DRIVE_GEOMETRY, `products.json`,
  `provision_usb.ps1/.sh` display strings + `SafetyValidator.*` capacities, README tier
  table, `provisioning/README.md` table.
- `manifests/product_sku.json` refreshed to Product2 @ 64 GB.
- README tier table and `provisioning/README.md` SKU table rewritten against
  `products.json` + planner output.

Still open (tracked in `tasks.md`):

- Feature register: partially resolved — `docs/PRD_ARD.md` Appendix A now maps all
  F-XX IDs found in module docstrings to code anchors; F-19..F-24 and F-37..F-40 have
  no code anchor and remain PRD-era only.
- UI feature lists still gate slated-for-removal features (`survival_calculators`,
  `settlement_hub`, `lora_mesh_agent`, `distillation_on_dock`) — resolves when
  tasks.md task 3 lands.
- Companion task file: `tasks.md` holds the current task list (repo audit vs this
  file — task 1 done in PR #21 — integrity-canary writeup/verdict, removals, validation work).
