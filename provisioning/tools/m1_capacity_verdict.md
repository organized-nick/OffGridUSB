# Milestone 1 Verdict: Physical NAND Capacity & Clamped Geometry

**Generated**: 2026-10-27T02:43:01Z  
**Prober**: `scripts/probe_physical_capacity.py` (Direct Uncached Win32 Sector I/O)  
**Target Media**: Disk 1 (`\\.\D:`) — Mass Storage Device (Serial: `121220160204`)  
**Host Protection**: Disk 0 (WD Green SN350 1TB 2G0C) strictly guarded and excluded.

---

## 1. Executive Capacity Verdict

| Parameter | Binary (MiB / GiB / Bytes) | Decimal (MB / GB) | Sectors (512B) |
| :--- | :--- | :--- | :--- |
| **Reported Media Size** | 999.22 GiB (`1,072,902,963,200` B) | 1,072.90 GB | 2,095,513,600 |
| **Verified Physical NAND** | **121.59 MiB** (0.1187 GiB / `127,500,288` B) | **127.5 MB** | **249,024** |
| **Recommended Safe Clamped Partition** | **115 MiB** (0.1123 GiB / `120,586,240` B) | **120.59 MB** | **235,520** |
| **Safety Margin Below Cutoff** | 6.08 MiB (`6,375,014` B) | - | 12,451 |
| **Unallocated Phantom Space** | **999.11 GiB** (`1,072,782,376,960` B) | 1,072.78 GB | 2,095,278,080 |

---

## 2. Flash Controller Behavior & Forensic Findings

- **Firmware Overflow Behavior**: `BLACKHOLE_DISCARD_ZEROES`
- **Modulo Wrap-Around Detected**: `False`
- **Canary Baseline Verification**: PASSED (4 low-LBA canaries at 1MB, 2MB, 4MB, 8MB backed up and restored)
- **Windows Cache Bypass**: Direct Win32 uncached I/O (`FILE_FLAG_NO_BUFFERING` | `FILE_FLAG_WRITE_THROUGH`) with 4KB `VirtualAlloc` alignment.
- **Probe Duration**: 4.60 seconds (10 sector test points).
- **Forensic Diagnosis**: The target storage device presents a hacked SCSI Inquiry / Read Capacity table reporting 1,072.9 GB ($0x7CE9A800$ sectors). In reality, the physical silicon is a **128 MB (nominal) NAND flash chip** ($128,053,248$ bytes / 122.12 MiB). All logical sector writes beyond offset $128,053,248$ are silently discarded into a bit-bucket (`0x00` null bytes) by the storage controller while returning false `GOOD` SCSI acknowledgments.

---

## 3. Recommended Geometry for Milestone 2 Partitioning

To guarantee 100% data integrity and eliminate any possibility of writing into unbacked phantom space:

1. **Wipe Partition Table**: Clean Disk 1 completely (`Clear-Disk` / `diskpart clean`).
2. **Create Clamped Primary Partition**:
   - Size: **`115` MB** (`120,586,240` bytes / `235,520` sectors).
   - Remaining `1,072,782,376,960` bytes **MUST REMAIN UNALLOCATED**.
3. **Format Filesystem**:
   - Filesystem: `FAT32`
   - Allocation Unit Size: `4096` bytes (4 KB)
   - Volume Label: `OFFGRIDUSB`
