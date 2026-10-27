# OffGridUSB // Universal Offline Knowledge & Adaptive AI Harness
**Zero Cloud • Zero Docker • Zero Setup • 100% Air-Gapped Survival Intelligence**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20|%20macOS%20|%20Linux%20|%20Raspberry%20Pi-green.svg)](#cross-platform-support)
[![Air-Gapped Certified](https://img.shields.io/badge/Air--Gapped-100%25%20Offline-orange.svg)](#air-gap-and-security-guarantee)

OffGridUSB productizes emergency survival literature, complete STEM curriculum, medical encyclopedias, and local neural network inference into a plug-and-play, portable USB appliance. Connect this drive to any computer and double-click to launch—with **zero downloads, zero package installations, and zero internet connectivity required**.

---

## Dual Architecture: Factory Suite vs. Customer USB

OffGridUSB strictly separates the **builder's host environment** from the **customer's physical drive**:

```
Repository Root (github.com/organized-nick/OffGridUSB)
├── provisioning/                     <-- HOST-ONLY FACTORY SUITE (Never on USB)
│   ├── PROVISION_OFFGRID_USB.bat     # Operator 1-click provisioning wizard
│   ├── provision_usb.ps1             # PowerShell SKU & Tier flash engine
│   ├── provision_usb.sh              # POSIX flash engine (Linux/macOS)
│   ├── wrappers/                     # 1-Click SKU provisioners (Product 1, 2, 3)
│   ├── lib/                          # Hardware probers, asset cache & validators
│   └── tools/                        # Legacy formatters, downloaders & auditors
│
└── Customer USB Runtime Files        <-- COPIED TO CUSTOMER USB DRIVE (D:\)
    ├── START_OFFGRIDUSB_WINDOWS.bat  # 1-Click Windows Command Center launcher
    ├── START_OFFGRIDUSB_LINUX.sh     # 1-Click Linux / Raspberry Pi launcher (LF)
    ├── START_OFFGRIDUSB_MAC.command  # 1-Click macOS launcher (LF)
    ├── USER_GUIDE.md                 # Pure customer operational manual
    ├── bin/                          # Cross-platform engines (Python, Kiwix, Llama)
    ├── data/                         # Pre-staged ZIM encyclopedias & GGUF models
    ├── manifests/                    # SKU descriptor (product_sku.json) & catalogs
    ├── src/emyrge/                   # 100% stdlib Python Command Center server
    └── web/                          # Tactical responsive Command Center UI
```

### Why This Separation Matters
- **Zero Leakage:** Customer drives contain **zero** provisioning scripts, downloader tools, formatting utilities, or developer READMEs.
- **Accidental Wipe Prevention:** Customers cannot accidentally format or erase their drives by running an errant host script.
- **Pure Appliance Experience:** The customer sees only native launchers and a clear user guide.

---

## Cumulative Tier 0–4 Hierarchy & Commercial SKUs

OffGridUSB scales dynamically across hardware tiers and commercial product editions:

| SKU / Tier | Edition Name | Target USB | Usable Payload | Included Offline Knowledge (.zim) | Local Neural Models (.gguf) | Active Command Center Features |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| **Product 1**<br>(Tier 0) | **PocketSurvival** | **8 GB** | **<= 6.5 GB** | Safe Water, Food Prep, Wilderness First Aid, Clinical WikiMed Mini, Top Articles Mini (~570 MB) | SmolLM2-135M (~101 MB)<br>Qwen2.5-0.5B (~469 MB) | Offline Kiwix Reader (:8081)<br>Grounded AI Professor (:8082)<br>CDC Water Chlorination Calc<br>WHO Oral Rehydration Calc<br>Solar & Battery Sizing Calc |
| **Product 2**<br>(Tiers 0+1) | **FieldReady** | **32 GB** | **~16–20 GB** | *All Tier 0 content PLUS:*<br>Wikibooks STEM & Textbooks (~5.8 GB)<br>Full Illustrated WikiMed (~1.8 GB) | *All Tier 0 models PLUS:*<br>Qwen2.5-1.5B (1.06 GB)<br>Phi-3.5-mini / Llama-3.2-3B (~2 GB) | *All Product 1 features PLUS:*<br>SQLite Semantic Memory Vault<br>Offline Photo OCR & EXIF Vault<br>Interactive STEM Practice Tutor |
| **Product 3**<br>(Tiers 0+1+2) | **CivilizationArk** | **128 GB** | **~65–72 GB** | *All Tier 0+1 content PLUS:*<br>Full English Wikipedia No-Pic (~50.2 GB, 6.8M articles) | Dual 3B/3.8B models<br>(Llama-3.2-3B + Phi-3.5-mini) | Full 6.8M Article RAG Retrieval<br>Hardware Auto-Selector<br>Multi-model fallback routing |
| **Tier 3** | **SwarmCluster** | **256 GB SSD** | **~88 GB** | All Tiers 0–2 knowledge | Qwen2.5-32B-Instruct (18.9 GB) | Heterogeneous LAN clustering via `exo`/`llama.cpp` RPC layer splitting |
| **Tier 4** | **SettlementHub** | **512 GB NVMe** | **~210+ GB** | All Tiers 0–3 + Full Illustrated English Wikipedia Maxi (~110 GB) | Llama-3.3-70B-Instruct (40.5 GB) | Multi-GPU Settlement Hub<br>Distillation-on-Dock<br>LoRa / Meshtastic query gateway |

---

## Factory Provisioning Guide (For Builders & Operators)

To provision a fresh USB flash drive from the host factory suite:

### 1. Interactive Provisioning Wizard (Windows)
Double-click `provisioning\PROVISION_OFFGRID_USB.bat` or run:
```powershell
.\provisioning\provision_usb.ps1
```
The wizard inspects attached removable storage, prevents targeting OS drive `C:`, displays available SKUs, verifies drive capacity, formats exFAT @ 128 KB cluster size, and stages only the chosen product assets.

### 2. One-Click Product Shortcuts
- **Provision Product 1 (PocketSurvival, 8 GB):**
  ```powershell
  .\provisioning\wrappers\provision_product1_pocketsurvival.ps1 -Drive D:
  ```
- **Provision Product 2 (FieldReady, 32 GB):**
  ```powershell
  .\provisioning\wrappers\provision_product2_fieldready.ps1 -Drive D:
  ```
- **Provision Product 3 (CivilizationArk, 128 GB):**
  ```powershell
  .\provisioning\wrappers\provision_product3_civilizationark.ps1 -Drive D:
  ```

### 3. Dry-Run & Payload Sizing Inspection
To check asset sizes, magic header integrity, and hardware requirements without writing to disk:
```powershell
.\provisioning\provision_usb.ps1 -Info
```

---

## Customer Quick Start (Plug & Play)

Connect the provisioned OffGridUSB drive to any host machine:

### Windows 10 / 11 (x86_64 & ARM64)
1. Open the drive in File Explorer (`D:\`).
2. Double-click **`START_OFFGRIDUSB_WINDOWS.bat`**.
3. Your default web browser opens automatically to **`http://127.0.0.1:8000`**.

### macOS (Apple Silicon & Intel)
1. Open the drive in Finder.
2. Double-click **`START_OFFGRIDUSB_MAC.command`**.
3. Browser opens automatically to **`http://127.0.0.1:8000`**.

### Linux & Raspberry Pi (x86_64 & aarch64)
1. Open terminal on the USB drive.
2. Run:
   ```bash
   ./START_OFFGRIDUSB_LINUX.sh
   ```
3. Browser opens automatically to **`http://127.0.0.1:8000`**.

---

## Core Services & Port Orchestration

When active, OffGridUSB runs three isolated, zero-dependency background daemons bound strictly to loopback:

| Port | Service | Process Path | Function |
| :---: | :--- | :--- | :--- |
| **`8000`** | **Command Center** | `bin/windows_x86_64/python/python.exe` (or system `python3`) | Pure Python stdlib HTTP server serving UI, RAG citations, OCR, and calculators |
| **`8081`** | **Kiwix Knowledge Server** | `bin/*/kiwix-serve` | Fast full-text search and article rendering from indexed `.zim` archives |
| **`8082`** | **Local LLM Engine** | `bin/*/llama-server` | Native OpenAI-compatible HTTP inference for active `.gguf` neural models |

Press **`Ctrl+C`** in the launcher terminal window to trigger clean shutdown of all three daemons within 2 seconds.

---

## Hardware Anti-Counterfeit Safeguards

Low-cost USB flash media often suffers from fake microcontroller firmware reporting inflated physical capacity (e.g. 1 TB reported on a 32 GB NAND chip).
- Every OffGridUSB launcher includes a **sub-2-second pre-flight storage integrity check**.
- Launchers inspect high-LBA files (`data/.integrity_canary`, `.zim`, `.gguf`) for unbacked `\x00` null byte corruption before starting engines.
- If counterfeit media corruption is detected, launch is aborted with an actionable diagnostic warning to protect user data from silent loss.

---

## Air-Gap & Security Guarantee

1. **Zero External Network Traffic:** All server bindings are restricted strictly to loopback `127.0.0.1`.
2. **Zero Telemetry:** No analytics, tracker pixels, pingbacks, or external font/CDN dependencies.
3. **Container-Free:** No Docker, Podman, or WSL dependencies required.
4. **Read-Only Media Compatible:** Can operate from hardware write-locked USB drives and SD cards.

---

## Repository & Development

- **Issue Tracker & Discussions:** [github.com/organized-nick/OffGridUSB/issues](https://github.com/organized-nick/OffGridUSB/issues)
- **Official Website:** [offgridusb.com](https://offgridusb.com)
- **Authors & Contributors:** @TheBlindHacker, @johndikeman, @organized-nick, and the OffGridUSB team.
