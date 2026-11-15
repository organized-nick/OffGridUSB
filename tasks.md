# OffGridUSB — Task List

## 1. Audit the project against AGENTS.md

Read `AGENTS.md` — it contains the latest direction of the project. Audit the repo for
places where the code diverges from it, especially:

- a. the **product list + provisioning** parts (drive ladder, SKU set, payload profiles)
- b. the **UI** (`web/static/`, Command Center tabs/feature gating)
- c. the **README** (tier table, drive sizes, feature claims)
- d. the PRD

also rebase the parallel provisioning branch with the updated AGENTS.md file etc to ensure these changes are included.

## 2. Anti-counterfeit integrity canary

Investigate the integrity canary (`data/.integrity_canary` +
`provisioning/tools/check_integrity.*`, launcher pre-flight checks):

- a. document exactly what it does (what it probes, how corruption is detected)
- b. make an explicit argument to keep it or get rid of it

## 3. Remove half-baked features (nuke from repo)

- a. **Settlement hub** (`settlement_hub`) — no dedicated module; umbrella concept over
  multi-GPU + distillation + LoRa gateway only. Remove references (catalog hidden
  features, docs).
- b. **Interactive STEM practice tutor** — remove the interactive-lesson portion; the
  Khan curriculum *content* must remain viewable (keep `knowledge/khan_curriculum.py`
  lesson data/serving).
- c. **ESP32/LoRa thin-client mesh** (`lora_mesh_agent`, mesh protocol) — protocol-
  complete but hardware-untested (`mesh/esp32_protocol.py`, `mesh/packet_chunker.py`
  stub, `handle_mesh_command()`, `format_mesh_summary()`). Remove from repo.
- d. **Survival calculators** (`survival_calculators`) — fully implemented but being
  cut from the product: remove `src/emyrge/calculators/` (water purification,
  solar/battery, medical rehydration, electrical formulas, source audit), the
  `run_calculator()` path in `web/app.py`, related UI, and their test suites.

## 4. Validate Wikipedia RAG at full scale

(from AGENTS.md TODO) The grounding harness is validated mainly on mini ZIMs; test
retrieval performance against the full large-Wikipedia ZIMs before claiming
`wikipedia_rag` support in prose docs.

## 5. Reframe distillation-on-dock as session history

(from AGENTS.md TODO) Drop the "docking" concept. Rebuild the feature as: viewing
session history with pinning. `run_distillation_on_dock()` /
`needs_distillation=1` mechanics in `memory/memory_vault.py` become an internal
upgrade path, not a user-facing concept.

