# OffGridUSB — Consumer User Guide
**Universal Portable Offline Knowledge & Adaptive AI Drive**

Welcome to **OffGridUSB**, a zero-cloud, 100% air-gapped portable knowledge vault and local AI engine. OffGridUSB runs entirely from this flash drive across any USB port or drive letter without installing software, Docker containers, or cloud dependencies on your host computer.

---

## 1. Quick Start (Plug & Play — Any USB Port)

Connect this drive to any USB port on Windows, macOS, or Linux / Raspberry Pi and launch the corresponding runner:

### Windows 10 / 11 (AMD64 & ARM64)
1. Open the **OFFGRIDUSB** drive in File Explorer (works on any assigned drive letter: `D:\`, `E:\`, `F:\`, etc.).
2. Double-click **`START_OFFGRIDUSB_WINDOWS.bat`**.
3. The console window will populate immediately, start the local engines, and open your default web browser to **`http://127.0.0.1:8000`** (or the next free port if `8000` is in use).
4. Keep the console window open while using OffGridUSB. Press `Ctrl+C` to stop.

### Linux & Raspberry Pi (Ubuntu, Debian, Raspberry Pi OS, Mint, Fedora — x86_64 & ARM64)
- **Desktop Double-Click:** Double-click **`START_OFFGRIDUSB_LINUX.desktop`** (*Start OffGridUSB*) or **`START_OFFGRIDUSB_LINUX.sh`** in your file manager. If prompted for trust/launch, choose **Execute in Terminal** / **Allow Launching**.
- **From Any Terminal (Works Even on `noexec` USB Mounts):** Open a terminal in the USB drive folder (e.g., right-click inside the USB folder -> *Open in Terminal*) and run:
  ```bash
  bash START_OFFGRIDUSB_LINUX.sh
  ```
- The terminal window will populate immediately and automatically open your web browser to **`http://127.0.0.1:8000`**.

### macOS (Apple Silicon & Intel)
1. Open the **OFFGRIDUSB** drive in Finder.
2. Double-click **`START_OFFGRIDUSB_MAC.command`** (or run `bash START_OFFGRIDUSB_MAC.command` in Terminal).
3. Your browser will open automatically to **`http://127.0.0.1:8000`**.

---

## 2. Core Services & Endpoints

When OffGridUSB is active, three isolated air-gapped engines run on your local machine:

| Service | Default Address | Description |
| :--- | :--- | :--- |
| **Command Center** | `http://127.0.0.1:8000` | Web dashboard, multi-turn chat, emergency calculators, and Grounded AI Professor |
| **Kiwix Knowledge Server** | `http://127.0.0.1:8081` | Full-text searchable offline OpenZIM encyclopedias |
| **Local LLM Inference Engine** | `http://127.0.0.1:8082` | Native `llama-server` / polyglot `llamafile` OpenAI-compatible API |

*(If ports `8000`, `8081`, or `8082` are already used by another program on your computer, OffGridUSB automatically binds to the next open local port.)*

---

## 3. Built-In Offline Emergency Tools

### Grounded AI Professor (Multi-Turn Chat)
Ask questions in natural language and continue follow-up turns inline. Answers are strictly grounded in offline OpenZIM knowledge with direct source citations (`[Source: ...]`), preventing hallucinations.

### CDC Deterministic Safety Calculators
- **Water Purification:** Precise sodium hypochlorite / household bleach dosing based on volume and clarity.
- **Oral Rehydration Salts (ORS):** WHO standard water, salt, and sugar formulations for clinical dehydration.
- **Solar & Battery Sizing:** Load calculations, watt-hour requirements, and battery bank sizing for off-grid power.

---

## 4. Clean Shutdown & Safe Eject

1. Close your browser tabs.
2. In the command prompt or terminal window, press **`Ctrl+C`**.
3. Wait for the services to shut down cleanly, then safely eject the USB drive.

---

*OffGridUSB is an open-source project by @TheBlindHacker, @johndikeman, @organized-nick, and the OffGridUSB team.*  
*100% Air-gapped offline emergency survival knowledge & intelligence platform.*
