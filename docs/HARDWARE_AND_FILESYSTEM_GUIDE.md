# Hardware Sizing, USB Flash NAND & `exFAT` Filesystem Guide

**OffGridUSB (`offgridusb.com`)** is engineered to run off a single pocketable drive across **Windows (`x86_64` & `ARM64`), macOS (`Apple Silicon` & `Intel`), Linux (`x86_64`), Raspberry Pi (`ARM64`), and locked Chromebooks (`WebAssembly`)**. Choosing the right flash medium and filesystem format makes a dramatic difference in boot speed, model memory-mapping (`mmap`), and >4 GB archive support.

---

## 1. Filesystem Format Matrix (Why `exFAT` @ `128 KB` Wins)

| Filesystem | Max Single File | Windows 10/11 | macOS | Linux / Pi OS | ChromeOS | Verdict for OffGridUSB |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`exFAT` (`128 KB` cluster)** | `16 EB` (Unlimited) | Native R/W | Native R/W | Native R/W (`exfatprogs`) | Native R/W | **RECOMMENDED FOR ALL TIERS** |
| **`FAT32`** | **`4.0 GB` Hard Limit** | Native R/W | Native R/W | Native R/W | Native R/W | OK *only* for Tier 0/1 (`< 4 GB` files); **blocks Wikipedia & 3B+ models!** |
| **`NTFS`** | `16 TB` | Native R/W | Read-Only by default | Requires `ntfs3`/`ntfs-3g` | Read-Only | Avoid — breaks SQLite Vault writes on macOS! |
| **`APFS` / `ext4`** | Unlimited | Unsupported | macOS only / Linux only | Linux only | Unsupported | Avoid — breaks cross-OS portability! |

> **Why `128 KB` Allocation Unit Size?**  
> Both `llama-server` (`.gguf` neural weights) and `kiwix-serve` (`.zim` Zstandard-compressed article clusters) stream large sequential chunks directly off flash storage. Formatting `exFAT` with a **`128 KB` (`131072`-byte) cluster size** (automated by `FORMAT_AND_SETUP_USB.bat`) reduces FAT table lookups and boosts USB sequential read speeds by 15–35% on consumer NAND sticks.

---

## 2. Recommended Physical USB Drives by Tier

1. **Tier 0–1 Pocket Kits (`16 GB – 64 GB`):**
   - High-endurance metal USB 3.2 Gen 1/2 sticks: *Samsung BAR Plus*, *SanDisk Extreme PRO USB 3.2*, *Kingston DataTraveler Max*.
   - Look for sustained sequential reads `>= 150 MB/s` so `Qwen2.5-0.5B` (`~469 MB`) loads into RAM in `< 3 seconds`.
2. **Tier 2–4 Schoolhouse, Swarm & Settlement Hubs (`128 GB – 1 TB+`):**
   - External **USB-C / USB-A NVMe SSD Enclosures** (*Samsung T7 Shield*, *Crucial X9/X10 Pro*, or an *M.2 NVMe SSD inside a Realtek RTL9210 USB 3.2 enclosure*).
   - Sustained reads of `400–1,000 MB/s` + proper wear-leveling controller + thermal dissipation for continuous multi-user LAN serving and `32B`/`70B` model loading.

---

## 3. POSIX `noexec` & Gatekeeper Notes

- **Linux `noexec` Auto-Mounts:** Desktop automounters (`udisks2` on Ubuntu, Mint, Fedora, Crostini) frequently mount `exFAT`/`FAT32` USB drives with `noexec`. OffGridUSB's launchers (`exec bash ...`) and Python runners (`_extract_posix_tar_runtime` -> `/tmp/emyrge_runtime/`) bypass `noexec` automatically without requiring `sudo mount -o remount,exec`.
- **macOS Gatekeeper Quarantine:** If you downloaded a `.zip` through Safari/Chrome before copying to USB, clear the quarantine xattr once:
  ```bash
  xattr -dr com.apple.quarantine /Volumes/OFFGRIDUSB
  ```

---
> **🛒 Prefer a Ready-Made, Pre-Tested Drive?** Skip downloading 50 GB–110 GB yourself and support our open-source engineering team — **please visit [https://offgridusb.com](https://offgridusb.com) to purchase an official OffGridUSB drive!**

*Signed — `@TheBlindHacker` • `@johndikeman` • `@organized-nick` • The OffGridUSB Team (`offgridusb.com`)*
