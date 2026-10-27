# Contributing to OffGridUSB (`offgridusb.com`)

```text
   ____   __  __  _____      _     _ _    _  _____ ____  
  / __ \ / _|/ _|/ ____|    (_)   | | |  | |/ ____|  _ \ 
 | |  | | |_| |_| |  __ _ __ _  __| | |  | | (___ | |_) |
 | |  | |  _|  _| | |_ | '__| |/ _` | |  | |\___ \|  _ < 
 | |__| | | | | | |__| | |  | | (_| | |__| |____) | |_) |
  \____/|_| |_|  \_____|_|  |_|\__,_|\____/|_____/|____/ 
   Zero-Install • Single-Click USB • 100% Air-Gapped AI
```

Welcome! **OffGridUSB** is built so human knowledge (Wikipedia, WikiMed, Khan Academy STEM), deterministic life-safety math, and adaptive local AI (`0.13B` → `70B`) run with **one click off any USB drive** on whatever hardware survives—with **zero Docker, zero cloud calls, and zero `pip` installation dependencies** on target machines.

---

## Core Architectural Guardrails

Before opening a Pull Request, please verify that your changes uphold these four pillars:

1. **100% Pure Python Standard Library Backend (`src/emyrge/`):**
   - Target Windows laptops run OffGridUSB using the bundled **Python 3.12 Embeddable** zip (`bin/windows_x86_64/python/python.exe`) with **zero `pip` packages installed**.
   - Never import third-party runtime dependencies (`fastapi`, `requests`, `pydantic`, `numpy`, `pillow`, etc.) inside `src/emyrge/`. Use `http.server`, `urllib.request`, `sqlite3`, `json`, `struct`, `tarfile`, etc. (`pytest` is permitted solely inside `tests/`.)
2. **100% Air-Gapped Frontend (`web/static/`):**
   - Never reference external CDNs, Google Fonts, external analytics, or remote scripts in `index.html`, `style.css`, `app.js`, or `wasm/chromebook.html`. Every UI asset must load cleanly with Wi-Fi physically disabled.
3. **Deterministic Life-Safety Math (`src/emyrge/calculators/`):**
   - Medical dosages (WHO ORS / pediatric mg/kg), water chlorination (CDC bleach drops/mL), solar/battery sizing (IEEE 1562), and DC wire voltage drop (NEC) must **always** be computed deterministically in Python and verified by `SourceAudit`—never left to raw LLM token guessing.
4. **Strict Cross-Platform Line Endings ([`.gitattributes`](.gitattributes)):**
   - `.bat` and `.ps1` scripts **must** use `CRLF` (`\r\n`).
   - `.sh` and `.command` scripts **must** use `LF` (`\n`) with no UTF-8 BOM so `#!/usr/bin/env bash` never fails on Linux, Raspberry Pi, or macOS.

---

## Local Development & Verification

```bash
# 1. Clone the repository
git clone https://github.com/TheBlindHacker/offgridUSB.com.git
cd offgridUSB.com

# 2. Stage Tier 0 portable engines, ZIM encyclopedias & Qwen2.5-0.5B GGUF
#    • Windows: .\scripts\download_internet_in_a_box.ps1 -Tier 0 -NonInteractive
#    • Linux / macOS: ./scripts/download_internet_in_a_box.sh --tier 0

# 3. Run the automated unit & E2E test suites (755 tests)
python -m pytest tests/unit tests/e2e -q

# 4. Launch locally on http://127.0.0.1:8000
PYTHONPATH=src python -m emyrge.web.app --host 127.0.0.1 --port 8000
```

---

## Founding Team & Core Contributors

- **[@TheBlindHacker](https://github.com/TheBlindHacker)** — Creator, Lead Architect & Security/Systems Engineering
- **[@johndikeman](https://github.com/johndikeman)** (*John*) — Core Contributor & Distributed Systems / Hardware Engineering
- **[@organized-nick](https://github.com/organized-nick)** (*Nick*) — Core Contributor & Product Strategy / Field Operations
- **The OffGridUSB Product & Engineering Team** — [`offgridusb.com`](https://offgridusb.com) • [`github.com/TheBlindHacker/offgridUSB.com`](https://github.com/TheBlindHacker/offgridUSB.com)

> **⚡ Support the Project:** Want to back open-source offline resilience *and* get a ready-to-run pre-flashed drive? **Please visit [https://offgridusb.com](https://offgridusb.com) and purchase an official OffGridUSB drive!**
