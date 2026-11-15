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

## Product list

These are the products that will go to production at launch.

- Online download: download runtime as a standalone package
- 64 gig USB: AI free zim version, assembled via the info priorities in the provisioning script, no AI features included
- 64 gig USB: zim version WITH AI models (note: should be straight superset info-wise as the 0 AI version, leave space on 0 AI if you need to
- 256 gig USB: more info + models + swarm functionality

## Feature list

 - Offline Kiwix reader (kiwix_reader) — implemented. ai/model_runner.py manages kiwix-serve lifecycle on :8081; data/library.xml built at provisioning; ZIM reader in knowledge/zim_reader.py. Actively served.                                                    
 - Grounded AI professor / RAG chat (grounded_ai_professor) — implemented. handle_ask() in web/app.py +                              
   knowledge/grounding_harness.py (728 lines) with citations from ZIMs/seed corpus; llama-server managed on :8082.                   
 - Survival calculators (survival_calculators) — implemented. Four calculators (water purification, solar/battery, medical           
   rehydration, electrical formulas) + calculators/source_audit.py auto-router, exposed via run_calculator().                        
 - Memory vault (memory_vault) — implemented. memory/memory_vault.py (645 lines): SQLite + FTS5 search, seeded field-history         
   entries, data/vault/memory.sqlite ships on drive.                                                                                 
 - Photo/OCR vault (photo_ocr_vault) — implemented. vision/visual_vault.py (514 lines): pure-Python EXIF/GPS parsing, observation    
   extraction via extract_visual_observation().                                                                                      
 - STEM tutor (stem_tutor) — implemented. knowledge/khan_curriculum.py (472 lines) with seeded lessons, instantiated in the runtime. 
 - Local LLM serving + model boot guard — implemented. llama-server lifecycle, model boot guard (test_model_boot_guard.py), model    
   files ship in data/models/.                                                                                                       
 - Offline maps — implemented. MapLibre + pmtiles vendored in web/static/vendor/maps/; /api/maps + /api/maps/search (gazetteer) in   
   web/app.py.                                                                                                                       
 - Multi-model hardware auto-selector (multi_model_auto_selector) — implemented. core/hardware_probe.py (497 lines): CPU probing     
   (incl. Windows registry, WASM profiles), dynamic tier selection, mock profiles for testing.                                       
 - Safe eject/shutdown — implemented. core/usb_eject.py + trigger_safe_shutdown_and_eject(), client heartbeat/tab-close grace.       
 - Anti-counterfeit integrity canary — implemented. Launchers probe data/.integrity_canary; checks in                                
   provisioning/tools/check_integrity.*.                                                                                             
 - WASM fallback UI — implemented. web/static/wasm/chromebook.html + wasm_runner.js; served as fallback root page for browser-only   
   hosts.                                                                                                                            
 - Swarm cluster / LAN mesh RPC (swarm_cluster, lan_mesh_rpc) — implemented and the most heavily tested subsystem: swarm/runtime.py  
   (863 lines, exo P2P ring), inference.py (distributed inference UI orchestration), watchdog.py (peer health/recovery),             
   cluster_sim.py (RPC ring coordinator); ~8 test files cover membership, self-filtering, runtime, watchdog, inference. Live run     
   documented in docs/two-machine-swarm-test.md and docs/live-rpc-inference-run.md.  


 - Wikipedia RAG at full scale (wikipedia_rag) — implemented in the harness, but validated mainly on mini ZIMs; full 50 GB+          
   Wikipedia retrieval performance is untested in-repo.        (TODO)

 - Distillation-on-dock (distillation_on_dock) — implemented. run_distillation_on_dock() in memory_vault.py upgrades low-tier drafts 
   queued as needs_distillation=1 using a stronger model callback. Tested at unit level; real cross-tier docking flow lightly        
   exercised.    TODO:  develop this feature, ditch the docking bit, but a concept of viewing session history and pinning. 
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

## Out-of-sync flags (do not fix in this run; verify before relying on them)

- The attestation says the product ships on **256 GB or 64 GB** drives, but the repo
  also defines **Product1 on a 32 GB drive** (`plan_tier_payloads.py` SKUS map and
  `products.json`), and README/provisioning docs still describe an 8 GB Product1 and a
  128 GB Product3 / 512 GB Tier4 ladder. Decide the canonical drive ladder and align
  README ↔ products.json ↔ planner.
- The committed `manifests/product_sku.json` says `Product2 / fieldready` with
  `target_drive_size_gb: 32`, while `products.json` defines Product2 as a **64 GB**
  SKU — the committed runtime descriptor appears stale relative to the current catalog.
- README tier table (8/32/128/256/512 GB) and `provisioning/README.md` SKU table were
  written before the 64/256 GB planner redesign; treat `products.json` + planner as
  source of truth and update prose docs separately.
