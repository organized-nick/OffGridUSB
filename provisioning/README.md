# OffGridUSB Factory Provisioning Suite (Host Only)

> **CRITICAL ARCHITECTURAL BOUNDARY:**
> The files in `provisioning/` live **exclusively on the factory builder's workstation**.
> **THEY ARE NEVER STAGED OR DISTRIBUTED ONTO CUSTOMER USB DRIVES.**
> Customer USB drives are finished, air-gapped consumer appliances and must contain zero downloader scripts, zero formatting utilities, and zero cloning tools.

---

## 1. Overview & Commercial Product Line

The Factory Provisioning Suite productizes **OffGridUSB** into three commercial SKUs across technical Tiers 0 through 4:

| Commercial SKU | SKU ID | Technical Tiers | Target Media | Formatted Min Size | Max Allowed Payload | Lean Local Payload | Target Features |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PocketSurvival** | `Product1` | Tier 0 | 8 GB USB | **7.0 GB** | **<= 6.5 GB** | ~1.39 GB | Kiwix (:8081), Grounded AI Professor (:8082), CDC Calculators |
| **FieldReady** | `Product2` | Tiers 0 & 1 | 32 GB USB (e.g. `D:`) | **28.0 GB** | **~16–20 GB** | ~4.69 GB | All Product 1 + SQLite Memory Vault, Photo OCR Vault, STEM Tutor |
| **CivilizationArk** | `Product3` | Tiers 0, 1 & 2 | 128 GB USB / SSD | **110.0 GB** | **~65–72 GB** | N/A (50.2 GB ZIM) | All Product 2 + 50.2 GB Wikipedia, Hardware Auto-Selector |
| **SwarmCluster** | `Tier3` | Tiers 0–3 | 256 GB Portable SSD | **220.0 GB** | **~88 GB** | N/A (18.9 GB GGUF)| All Product 3 + Qwen 32B + exo LAN RPC Coordinator |
| **SettlementHub** | `Tier4` | Tiers 0–4 | 512 GB Portable NVMe | **450.0 GB** | **~210+ GB** | N/A (110 GB ZIM) | All Tier 3 + Wikipedia Maxi (110 GB) + Llama 70B (40.5 GB) |

*(Note: Commercial 64 GB USB drives only offer ~57.6 GiB usable space, which cannot fit the ~65–72 GB CivilizationArk payload. Product 3 strictly requires a 128 GB drive).*

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

### Dry-Run Simulation (0 writes to disk)
```powershell
# Simulate Product 1 (PocketSurvival) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product1 -Drive D -DryRun

# Simulate Product 2 (FieldReady) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product2 -Drive D -DryRun

# Simulate Product 3 (CivilizationArk) on D:
powershell -ExecutionPolicy Bypass -File provisioning/provision_usb.ps1 -Product Product3 -Drive D -DryRun
```

### 1-Click Provisioning Execution
```powershell
# Windows PowerShell
.\provisioning\provision_product2_fieldready.ps1 -Drive D

# Windows Batch
.\provisioning\provision_product2_fieldready.bat -Drive D

# Linux / macOS Bash
./provisioning/provision_product2_fieldready.sh --drive /media/user/OFFGRIDUSB
```
