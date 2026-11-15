# OffGridUSB Factory Provisioning Suite (Host Only)

> **CRITICAL ARCHITECTURAL BOUNDARY:**
> The files in `provisioning/` live **exclusively on the factory builder's workstation**.
> **THEY ARE NEVER STAGED OR DISTRIBUTED ONTO CUSTOMER USB DRIVES.**
> Customer USB drives are finished, air-gapped consumer appliances and must contain zero downloader scripts, zero formatting utilities, and zero cloning tools.

---

## 1. Overview & Commercial Product Line

The Factory Provisioning Suite productizes **OffGridUSB** into seven commercial SKUs across technical Tiers 0 through 4:

| Commercial SKU | SKU ID | Technical Tiers | Target Media | Formatted Min Size | Max Allowed Payload | Lean Local Payload | Target Features |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PocketSurvival** | `Product1` | Tier 0 | 64 GB USB | **59.0 GB** | **~54.0 GB** | ~1.39 GB | AI-free: Offline Kiwix (:8081) + ZIM knowledge. No models. |
| **FieldReady** | `Product2` | Tiers 0 & 1 | 64 GB USB (e.g. `D:`) | **59.0 GB** | **~54.5 GB** | ~4.69 GB | All Product 1 + Memory Vault, Photo OCR Vault, STEM Tutor, local AI (:8082) |
| **CivilizationArk** | `Product3` | Tiers 0, 1 & 2 | 64 GB USB / SSD | **59.0 GB** | **~54.8 GB** | N/A | All Product 2 + Wikipedia No-Pic + Hardware Auto-Selector |
| **FieldReady 256** | `Product2-256` | Tiers 0 & 1 | 256 GB Portable SSD | **214.2 GB** | **~149.6 GB** | ~4.69 GB | Same features as Product2, full 145.5 GB ZIM catalog |
| **CivilizationArk 256** | `Product3-256` | Tiers 0, 1 & 2 | 256 GB Portable SSD | **214.2 GB** | **~163.4 GB** | N/A | Same features as Product3, full catalog + 7B/9B models |
| **SwarmCluster** | `Tier3` | Tiers 0–3 | 256 GB Portable SSD | **214.2 GB** | **~182 GB** | N/A | All Product 3 + Qwen 32B + exo LAN RPC Coordinator |
| **SettlementHub** | `Tier4` | Tiers 0–4 | 512 GB NVMe | **428.4 GB** | **~332 GB** | N/A | All Tier 3 + Wikipedia Maxi + Llama 70B |


*(Note: drive ladder per AGENTS.md — 64 GB AI-free Product1, 64 GB Product2/Product3, 256 GB variants + Tier3, 512 GB Tier4. No 32 GB tiers anymore.)*

---

## 2. Directory Structure

```text
provisioning/
├── README.md                                 # Factory Operator & Builder Manual (this file)
├── PROVISION_OFFGRID_USB.bat                 # Interactive Windows menu launcher (1-click)
├── provision_usb.ps1                         # Primary PowerShell Provisioning Engine
├── provision_usb.sh                          # Primary POSIX Bash Provisioning Engine
│
├── provision_product1_pocketsurvival.*       # 1-Click SKU 1 wrappers (.bat, .ps1, .sh)
├── provision_product2_fieldready.*           # 1-Click SKU 2 wrappers (.bat, .ps1, .sh)
├── provision_product3_civilizationark.*      # 1-Click SKU 3 wrappers (.bat, .ps1, .sh)
│
├── wrappers/                                 # Mirrored dedicated SKU wrappers
│   ├── provision_product1_pocketsurvival.*
│   ├── provision_product2_fieldready.*
│   └── provision_product3_civilizationark.*
│
├── lib/                                      # Modular Helper Subroutines & Modules
│   ├── SafetyValidator.ps1                   # Disk 0 guard, capacity checks, process locks
│   ├── SafetyValidator.sh                    # POSIX safety validator
│   ├── AssetCacheManager.ps1 / .py           # Binary magic validation (ZIM\x04, GGUF) & cache audit
│   ├── SkuManifestGenerator.ps1 / .py        # Generates active manifests/product_sku.json
│   ├── LibraryXmlBuilder.ps1 / .py           # Generates tailored data/library.xml for staged ZIMs
│   ├── UsbStripper.ps1                       # Whitelist staging & customer hygiene verification
│   └── UsbStripper.sh                        # POSIX hygiene audit & LF line ending enforcer
│
└── tools/                                    # Historical & forensic development tooling
    ├── probe_physical_capacity.py            # UNCACIO physical NAND flash capacity tester
    ├── check_integrity.ps1 / .py             # Pre-flight integrity canary probe
    ├── audit_offgrid_usb.py                  # Standalone multi-tier auditor
    └── fetch_assets.py                       # Legacy developer asset fetcher
```

---

## 3. Hardware Safety Architecture (Triple-Gate Guard)

To prevent accidental modification or wiping of host drives, every provisioning execution enforces three strict gates:
1. **Gate 1: Drive Letter Block:** Rejects `C:` and `$env:SystemDrive`.
2. **Gate 2: Physical Disk 0 Block:** Queries the partition table and physical disk; if `DiskNumber == 0` (e.g. `WD Green SN350 1TB NVMe`), the script terminates immediately with a fatal exception.
3. **Gate 3: OS Flag Guard:** Rejects disks flagged with `IsBoot == True` or `IsSystem == True`.
4. **Non-Elevated Safe Execution:** When running without UAC Administrator rights, the engine inspects the target drive. If already formatted as `exFAT` (such as `D:`), it executes a recursive clean wipe (`Remove-Item -Recurse -Force`) rather than calling privileged format cmdlets.

---

## 4. Usage Instructions

### Interactive Menu
Double-click `PROVISION_OFFGRID_USB.bat` or run:
```cmd
PROVISION_OFFGRID_USB.bat
```

### View Catalog & Hardware Specifications (-Info)
```powershell
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Info
```

```bash
# POSIX (Linux / macOS) — full feature parity with the PowerShell engine
./provisioning/provision_usb.sh --info
```

### Dry-Run Simulation (0 writes to disk)
```powershell
# Simulate Product 1 (PocketSurvival) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product1 -Drive D -DryRun

# Simulate Product 2 (FieldReady) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product2 -Drive D -DryRun

# Simulate Product 3 (CivilizationArk) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product3 -Drive D -DryRun
```

```bash
# POSIX equivalent — --drive is the USB MOUNT POINT, not a device node
./provisioning/provision_usb.sh --product Product2 --dry-run --drive /media/$USER/OFFGRIDUSB
```

### Parallel Multi-Drive Provisioning (USB hub)
Provision several USB drives on one hub concurrently. One child engine runs per
drive (own bandwidth budget — default 2048 KB/s each, which is what keeps
shared-hub flash controllers alive), its own log under `provisioning/logs/`, a
sequential safety gate before any staging, a summary table at the end, and safe
eject of succeeded drives. A failed drive never aborts the others.

```powershell
# Windows: same SKU on 3 drives (per-drive SKU override: "D:Product1,E:Product2")
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product1 -Drives "D,E,F"

# Linux / macOS: mount paths with optional per-drive SKU override (path:SKU)
./provisioning/provision_usb.sh --product Product1 --drive /media/usb/d1 --drive /media/usb/d2:Product2
```

Without `-Drives` / `--drive` lists, both engines behave exactly as before
(single drive). `--dry-run` works in parallel mode with fake drive paths, so
the whole flow is testable without live hardware. `--bwlimit` applies per
drive in parallel mode (not divided across drives).

### 1-Click Provisioning Execution
```powershell
# Windows PowerShell
.\provisioning\provision_product2_fieldready.ps1 -Drive D

# Windows Batch
.\provisioning\provision_product2_fieldready.bat -Drive D

# Linux / macOS Bash
./provisioning/provision_product2_fieldready.sh --drive /media/user/OFFGRIDUSB
```

### Engine Staging Parity (all platforms)
Both the PowerShell (`provision_usb.ps1`) and POSIX (`provision_usb.sh`) provisioning
engines automatically stage the portable cross-platform engines (`bin/`: Windows x64
Python 3.12 embeddable + kiwix-serve + llama-server, Windows ARM64, Linux x86_64 &
ARM64, macOS ARM64 & Intel bundles, polyglot llamafile) into the source tree before
whitelist staging, so **one provisioning run on either host OS yields a universally
bootable drive**. Missing boot-critical engines abort live runs; `--dry-run` reports
them without downloading.
