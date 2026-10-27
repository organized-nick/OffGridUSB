# OffGridUSB — Consumer User Guide
**Universal Portable Offline Knowledge & Adaptive AI Drive**

Welcome to **OffGridUSB**, a zero-cloud, 100% air-gapped portable knowledge vault and local AI engine. OffGridUSB runs entirely from this flash drive without installing any software, docker containers, or cloud dependencies on your host computer.

---

## 1. Quick Start (Plug & Play)

Connect this drive to any computer (Windows, macOS, or Linux / Raspberry Pi) and launch the corresponding runner:

### Windows 10 / 11 (AMD64 & ARM64)
1. Open this drive in File Explorer (`D:\`).
2. Double-click **`START_OFFGRIDUSB_WINDOWS.bat`**.
3. The command prompt window will start the core services and automatically open your default web browser to the Command Center dashboard at **`http://127.0.0.1:8000`**.
4. Keep the command prompt window open while using OffGridUSB. Press `Ctrl+C` to stop.

### macOS (Apple Silicon & Intel)
1. Open this drive in Finder.
2. Double-click **`START_OFFGRIDUSB_MAC.command`**.
3. Your browser will open automatically to **`http://127.0.0.1:8000`**.

### Linux & Raspberry Pi (x86_64 & aarch64)
1. Open a terminal on the drive.
2. Run:
   ```bash
   ./START_OFFGRIDUSB_LINUX.sh
   ```
3. Your browser will open automatically to **`http://127.0.0.1:8000`**.

---

## 2. Core Services & Endpoints

When OffGridUSB is active, three isolated air-gapped engines run on your local machine:

| Service | Address | Description |
| :--- | :--- | :--- |
| **Command Center** | `http://127.0.0.1:8000` | Web dashboard, emergency calculators, and Grounded AI Professor |
| **Kiwix Knowledge Server** | `http://127.0.0.1:8081` | Full-text searchable offline OpenZIM encyclopedias |
| **Local LLM Inference Engine** | `http://127.0.0.1:8082` | Native llama.cpp / llama-server OpenAI-compatible API |

---

## 3. Staged Offline Knowledge & AI Models

This drive is provisioned with complete offline assets across Tiers 0, 1, and 2:

### Offline OpenZIM Encyclopedias (`data/zim/`)
- **Full English Wikipedia (No-Pictures)** (50.2 GB) — Millions of encyclopedia articles.
- **Wikibooks STEM & K-12 Textbooks** (5.8 GB) — Mathematics, physics, engineering, and computer science.
- **Wikipedia Medicine Mini** (~174 MB) — Clinical medical and triage reference.
- **Wikipedia Top Articles Mini** (~296 MB) — Essential general knowledge articles.
- **ZimGit Austere Field Medicine** (~70 MB) — Emergency wilderness & disaster first aid.
- **ZimGit Safe Water & Sanitation** (~20 MB) — Water purification, chlorination, and sanitation guides.

### Local AI Neural Models (`data/models/`)
- **Llama-3.2-3B-Instruct (Q4_K_M)** (1.93 GB) — Tier 2 high-capability instruction model with AVX2/Metal acceleration.
- **Qwen2.5-1.5B-Instruct (Q4_K_M)** (1.06 GB) — Tier 1 efficient model for older laptops (4GB RAM / SSE4.2).
- **Qwen2.5-0.5B-Instruct (Q4_K_M)** (~380 MB) — Tier 0 ultra-lightweight universal micro-model.
- **SmolLM2-135M-Instruct (Q4_K_M)** (~101 MB) — Ultra-micro fast fallback model.

---

## 4. Built-In Offline Emergency Tools

### Grounded AI Professor
Ask questions in natural language. Answers are strictly grounded in offline OpenZIM knowledge with direct source citations (`[Source: ...]`), preventing hallucinations.

### CDC Deterministic Safety Calculators
- **Water Purification:** Precise sodium hypochlorite / household bleach dosing based on volume and clarity.
- **Oral Rehydration Salts (ORS):** WHO standard water, salt, and sugar formulations for clinical dehydration.
- **Solar & Battery Sizing:** Load calculations, watt-hour requirements, and battery bank sizing for off-grid power.

---

## 5. Clean Shutdown

1. Close your browser tabs.
2. In the command prompt or terminal window, press **`Ctrl+C`**.
3. Wait for the services to shut down cleanly.
4. Press any key to close the window, then safely eject your USB drive.

---

*OffGridUSB is an open-source project by @TheBlindHacker, @johndikeman, @organized-nick, and the OffGridUSB team.*  
*100% Air-gapped offline emergency survival knowledge & intelligence platform.*
