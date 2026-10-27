# `bin/` — Zero-Install Cross-Platform Engine Bay

**OffGridUSB (`offgridusb.com`)** stores all portable, zero-install native execution engines inside `bin/` so a single `exFAT` USB stick can boot directly across **Windows (`x86_64` & `ARM64`), macOS (`Apple Silicon` & `Intel`), Linux (`x86_64`), and Raspberry Pi (`ARM64`)** without Docker, root/admin privileges, or `pip` installs.

```text
bin/
├── windows_x86_64/   # Python 3.12.8 Embeddable + kiwix-serve.exe + llama-server.exe
├── windows_arm64/    # Native Snapdragon / Surface ARM64 llama-server.exe
├── linux_x86_64/     # Static kiwix-serve + POSIX .tar.gz runtime bundle
├── linux_arm64/      # Raspberry Pi 4/5 ARM64 kiwix-serve + llama-ubuntu-arm64.tar.gz
├── macos_arm64/      # Apple Silicon M1–M4 Metal llama-macos-arm64.tar.gz
├── macos_x86_64/     # Intel Mac native / polyglot runtime slot
└── polyglot/         # Mozilla llamafile Cosmopolitan universal x86_64+ARM64 binary
```

## How to Populate `bin/`

Binary payloads are ignored by Git to keep repository clones lightweight. Populate all cross-OS binaries automatically in one command:

- **Windows:** Double-click **`DOWNLOAD_INTERNET_IN_A_BOX.bat`** or run:
  ```powershell
  .\scripts\download_internet_in_a_box.ps1 -EnginesOnly -NonInteractive
  ```
- **Linux / Raspberry Pi / macOS:**
  ```bash
  ./scripts/download_internet_in_a_box.sh --engines-only
  ```

## `noexec` & `exFAT` Symlink Safety

Because `exFAT` and `FAT32` USB flash drives do not support Unix shared-library symlinks (`.so.0`, `.dylib`) and many Linux desktops mount USB drives with `noexec`, `KiwixRunner` and `ModelRunner` (`src/emyrge/ai/model_runner.py`) automatically extract the staged `.tar.gz` bundles into `/tmp/emyrge_runtime/` in RAM on POSIX hosts and set `+x` permissions transparently.

---
*Signed — `@TheBlindHacker` • `@johndikeman` • `@organized-nick` • The OffGridUSB Team (`offgridusb.com`)*
