#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# OffGridUSB (offgridusb.com) — Linux & macOS Safe USB Formatter & Provisioner
#
# Examples:
#   ./scripts/setup_usb_unix.sh --list
#   ./scripts/setup_usb_unix.sh --copy /Volumes/OFFGRIDUSB          # macOS copy
#   ./scripts/setup_usb_unix.sh --copy /media/$USER/OFFGRIDUSB      # Linux copy
#   ./scripts/setup_usb_unix.sh --format-exfat /dev/disk4           # macOS format + copy
#   ./scripts/setup_usb_unix.sh --format-exfat /dev/sdb1            # Linux format part
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"

LABEL="OFFGRIDUSB"
ACTION=""
TARGET=""

show_help() {
    cat <<'EOF'
================================================================================
OffGridUSB (offgridusb.com) — Linux & macOS USB Formatter & Cloner
================================================================================
Usage:
  ./scripts/setup_usb_unix.sh --list
  ./scripts/setup_usb_unix.sh --copy <USB_MOUNT_PATH>
  ./scripts/setup_usb_unix.sh --format-exfat <DEVICE_NODE> [--label OFFGRIDUSB]

Options:
  --list                     List external/removable USB drives & mountpoints
  --copy <MOUNT_PATH>        Non-destructively sync OffGridUSB onto mounted USB
  --format-exfat <DEV_NODE>  Safely format external USB device as exFAT
                             • macOS example : --format-exfat /dev/disk4
                             • Linux example : --format-exfat /dev/sdb1
  --label <NAME>             Volume label when formatting (default: OFFGRIDUSB)
  --help, -h                 Display this help guide
================================================================================
EOF
}

if [[ $# -eq 0 ]]; then
    ACTION="list"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --list)
            ACTION="list"
            shift
            ;;
        --copy)
            ACTION="copy"
            TARGET="$2"
            shift 2
            ;;
        --format-exfat)
            ACTION="format"
            TARGET="$2"
            shift 2
            ;;
        --label)
            LABEL="$2"
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            show_help
            exit 1
            ;;
    esac
done

list_usb_drives() {
    echo "================================================================================"
    echo "OffGridUSB (offgridusb.com) — Detected External / Removable Storage"
    echo "================================================================================"
    if [[ "${OS_NAME}" == "darwin" ]]; then
        diskutil list external physical || diskutil list
        echo ""
        echo "Currently Mounted External Volumes (/Volumes):"
        ls -la /Volumes
    else
        if command -v lsblk >/dev/null 2>&1; then
            lsblk -o NAME,RM,TRAN,SIZE,FSTYPE,LABEL,MOUNTPOINT,MODEL
        else
            df -h
        fi
    fi
    echo "================================================================================"
}

copy_to_mount() {
    local dst="$1"
    if [[ -z "${dst}" || "${dst}" == "/" || "${dst}" == "/System" || "${dst}" == "/boot" || "${dst}" == "${HOME}" ]]; then
        echo "[SAFETY BLOCK] Refusing to copy directly into protected path '${dst}'." >&2
        exit 1
    fi
    if [[ ! -d "${dst}" ]]; then
        echo "[ERROR] Mount directory '${dst}' does not exist or is not mounted." >&2
        exit 1
    fi

    echo "================================================================================"
    echo ">>> Provisioning OffGridUSB + Internet-in-a-Box onto: ${dst}"
    echo "================================================================================"

    if command -v rsync >/dev/null 2>&1; then
        rsync -rltDvh --modify-window=2 \
            --exclude='.git/' \
            --exclude='.agents/' \
            --exclude='.venv/' \
            --exclude='__pycache__/' \
            --exclude='.pytest_cache/' \
            --exclude='tests/' \
            --exclude='tmp_dl/' \
            --exclude='*.pyc' \
            --exclude='.DS_Store' \
            --exclude='*-DESKTOP-*' \
            --exclude='*-JoeWorkTop*' \
            --include='START_OFFGRIDUSB_WINDOWS.bat' \
            --include='START_OFFGRIDUSB_MAC.command' \
            --include='START_OFFGRIDUSB_LINUX.sh' \
            --include='START_EMYRGE_WINDOWS.bat' \
            --include='START_EMYRGE_MAC.command' \
            --include='START_EMYRGE_LINUX.sh' \
            --include='MAKE_USB_DRIVES.bat' \
            --include='FORMAT_AND_SETUP_USB.bat' \
            --include='DOWNLOAD_INTERNET_IN_A_BOX.bat' \
            --include='run_windows.bat' \
            --include='run_linux.sh' \
            --include='run_macos.command' \
            --include='README.md' \
            --include='CONTRIBUTING.md' \
            --include='PITCH_CHEATSHEET.md' \
            --include='docs/***' \
            --include='manifests/***' \
            --include='scripts/***' \
            --include='src/***' \
            --include='web/***' \
            --include='bin/***' \
            --include='data/***' \
            --exclude='*' \
            "${ROOT_DIR}/" "${dst}/"
    else
        echo "[INFO] rsync not found; falling back to portable cp -R..."
        for f in START_OFFGRIDUSB_WINDOWS.bat START_OFFGRIDUSB_MAC.command START_OFFGRIDUSB_LINUX.sh START_EMYRGE_WINDOWS.bat START_EMYRGE_MAC.command START_EMYRGE_LINUX.sh MAKE_USB_DRIVES.bat FORMAT_AND_SETUP_USB.bat DOWNLOAD_INTERNET_IN_A_BOX.bat run_windows.bat run_linux.sh run_macos.command README.md CONTRIBUTING.md PITCH_CHEATSHEET.md; do
            [[ -f "${ROOT_DIR}/${f}" ]] && cp -f "${ROOT_DIR}/${f}" "${dst}/"
        done
        for d in docs manifests scripts src web bin data; do
            [[ -d "${ROOT_DIR}/${d}" ]] && cp -Rf "${ROOT_DIR}/${d}" "${dst}/"
        done
    fi

    mkdir -p "${dst}/data/vault" "${dst}/data/uploads" "${dst}/data/models" "${dst}/data/zim"
    chmod +x "${dst}/START_OFFGRIDUSB_LINUX.sh" "${dst}/START_OFFGRIDUSB_MAC.command" "${dst}/START_EMYRGE_LINUX.sh" "${dst}/START_EMYRGE_MAC.command" "${dst}/run_linux.sh" "${dst}/run_macos.command" 2>/dev/null || true
    sync

    echo ""
    echo "================================================================================"
    echo "[OK] OffGridUSB Ready at: ${dst}"
    echo "     • Linux / Pi : ${dst}/START_OFFGRIDUSB_LINUX.sh"
    echo "     • macOS      : ${dst}/START_OFFGRIDUSB_MAC.command"
    echo "     • Windows    : ${dst}/START_OFFGRIDUSB_WINDOWS.bat"
    echo "     • Chromebook : ${dst}/web/static/wasm/chromebook.html"
    echo "================================================================================"
}

format_exfat_device() {
    local dev="$1"
    if [[ "${OS_NAME}" == "darwin" ]]; then
        if [[ "${dev}" == "/dev/disk0"* || "${dev}" == "/dev/disk1"* ]]; then
            echo "[SAFETY BLOCK] Refusing to format internal macOS boot/synthesized disk (${dev})!" >&2
            exit 1
        fi
        if ! diskutil info "${dev}" | grep -qiE "External|Removable"; then
            echo "[SAFETY BLOCK] ${dev} is not reported as an External/Removable disk by diskutil!" >&2
            exit 1
        fi
        echo "================================================================================"
        echo "[DESTRUCTIVE WARNING] ALL DATA ON ${dev} WILL BE ERASED -> exFAT (${LABEL})"
        echo "================================================================================"
        read -r -p "Type 'FORMAT ${dev}' (exact) to erase and format: " confirm
        if [[ "${confirm}" != "FORMAT ${dev}" ]]; then
            echo "[CANCELLED] Drive was not modified."
            exit 0
        fi
        diskutil eraseDisk ExFAT "${LABEL}" MBR "${dev}"
        if [[ -d "/Volumes/${LABEL}" ]]; then
            copy_to_mount "/Volumes/${LABEL}"
        fi
    else
        # Linux safety checks: block root device & non-removable internal disks
        local root_src
        root_src="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
        if [[ -n "${root_src}" && "${root_src}" == "${dev}"* ]]; then
            echo "[SAFETY BLOCK] ${dev} backs the active root filesystem (${root_src})!" >&2
            exit 1
        fi
        if ! command -v mkfs.exfat >/dev/null 2>&1; then
            echo "[ERROR] mkfs.exfat not found. Install exfatprogs first:" >&2
            echo "        sudo apt install exfatprogs   # Debian / Ubuntu / Raspberry Pi OS" >&2
            echo "        sudo dnf install exfatprogs   # Fedora / RHEL" >&2
            exit 1
        fi
        echo "================================================================================"
        echo "[DESTRUCTIVE WARNING] ALL DATA ON ${dev} WILL BE ERASED -> exFAT (${LABEL})"
        echo "================================================================================"
        read -r -p "Type 'FORMAT ${dev}' (exact) to erase and format: " confirm
        if [[ "${confirm}" != "FORMAT ${dev}" ]]; then
            echo "[CANCELLED] Drive was not modified."
            exit 0
        fi
        sudo umount "${dev}" 2>/dev/null || true
        sudo mkfs.exfat -L "${LABEL}" "${dev}"
        echo "[OK] Formatted ${dev} as exFAT (${LABEL})."
        echo "     Mount the partition and run: ./scripts/setup_usb_unix.sh --copy <MOUNT_PATH>"
    fi
}

case "${ACTION}" in
    list)
        list_usb_drives
        ;;
    copy)
        copy_to_mount "${TARGET}"
        ;;
    format)
        format_exfat_device "${TARGET}"
        ;;
esac
