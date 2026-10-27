# `scripts/` — Build, Download, Safe USB Formatting & Multi-Drive Cloning Suite

All provisioning, `exFAT`/`FAT32` formatting, and mass-replication scripts for **OffGridUSB (`offgridusb.com`)** live in `scripts/`. Every script enforces **hard OS disk safety blocks** (never touches `C:`, `/`, `/System`, `/boot`, `/dev/disk0`, or `/dev/disk1`).

| Script | Platform / Format | Purpose & Example Usage |
| :--- | :--- | :--- |
| **[`download_internet_in_a_box.ps1`](download_internet_in_a_box.ps1)** | Windows PowerShell (`CRLF`) | Resumable (`curl -C -`) downloader + magic-header (`ZIM\x04` / `GGUF`) verifier for portable engines, ZIM archives, and GGUF weights. Also launched via **`DOWNLOAD_INTERNET_IN_A_BOX.bat`**. |
| **[`download_internet_in_a_box.sh`](download_internet_in_a_box.sh)** | Linux / Pi / macOS Bash (`LF`) | POSIX resumable provisioner (`--tier 0..4`, `--engines-only`, `--zim-only`, `--models-only`, `--current-os-only`, `--verify`). |
| **[`format_and_setup_usb.ps1`](format_and_setup_usb.ps1)** | Windows PowerShell (`CRLF`) | Interactive safe USB formatter (`exFAT` with `128 KB` cluster size or `FAT32`) + automatic >4 GB file check + UAC elevation + Robocopy provisioner. Launched via **`FORMAT_AND_SETUP_USB.bat`**. |
| **[`clone_to_usb.ps1`](clone_to_usb.ps1)** | Windows PowerShell (`CRLF`) | High-speed 16-thread `robocopy /MT:16` multi-drive cloner (`< 45s` per USB stick for Tier 0). Loops cleanly to stamp out 2, 5, or 20 drives in a row. Launched via **`MAKE_USB_DRIVES.bat`**. |
| **[`setup_usb_unix.sh`](setup_usb_unix.sh)** | Linux / Pi / macOS Bash (`LF`) | Lists removable USB devices (`--list`), formats external drives as `exFAT` (`--format-exfat`), and syncs runtime via `rsync` (`--copy`). |
| **[`stage_pitch_assets.ps1`](stage_pitch_assets.ps1)** | Windows PowerShell (`CRLF`) | Non-interactive shortcut wrapper around `download_internet_in_a_box.ps1 -Tier 0 -NonInteractive` for rapid staging. |

## Script Line-Ending Standards (Enforced by [`.gitattributes`](../.gitattributes))
- **Windows Batch & PowerShell (`.bat`, `.ps1`):** `CRLF` (`\r\n`) — ensures `cmd.exe` labels and multi-line blocks parse cleanly on all Windows 10/11 builds.
- **POSIX Shell & macOS Command (`.sh`, `.command`):** `LF` (`\n`, no UTF-8 BOM) — ensures `#!/usr/bin/env bash` executes cleanly on Linux, Raspberry Pi OS, and macOS without `\r` errors.

---
*Signed — `@TheBlindHacker` • `@johndikeman` • `@organized-nick` • The OffGridUSB Team (`offgridusb.com`)*
