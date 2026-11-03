#!/usr/bin/env bash
# Re-exec under bash if invoked via `sh START_OFFGRIDUSB_LINUX.sh` (e.g. dash on Debian/Raspberry Pi OS)
if [ -z "${BASH_VERSION:-}" ]; then
    exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# ==============================================================================
# Fast Pre-Flight Storage Integrity Check (< 0.2s on Raspberry Pi / USB 2.0)
# ==============================================================================
get_file_size() {
    local file="$1"
    stat -c %s "${file}" 2>/dev/null || stat -f %z "${file}" 2>/dev/null || wc -c < "${file}" 2>/dev/null || echo 0
}

check_integrity() {
    local target_files=()

    # 1. High-LBA Canary file
    if [[ -f "${SCRIPT_DIR}/data/.integrity_canary" ]]; then
        target_files+=("${SCRIPT_DIR}/data/.integrity_canary")
    fi

    # 2. Sample at most 1 ZIM and 1 GGUF so USB 2.0 startup on Raspberry Pi is instant (<0.2s)
    for f in "${SCRIPT_DIR}"/data/zim/*.zim; do
        if [[ -f "${f}" ]]; then
            target_files+=("${f}")
            break
        fi
    done
    for f in "${SCRIPT_DIR}"/data/models/*.gguf; do
        if [[ -f "${f}" ]]; then
            target_files+=("${f}")
            break
        fi
    done

    for f in "${target_files[@]}"; do
        if [[ ! -s "${f}" ]]; then
            continue
        fi

        # Check Head (first 512 bytes)
        local non_null_head
        non_null_head=$(head -c 512 "${f}" 2>/dev/null | tr -d '\000' | wc -c || echo 1)
        if [[ "${non_null_head}" -eq 0 ]]; then
            return 1
        fi

        # Check Tail (last 512 bytes using tail -c so 6GB+ files never overflow 32-bit block math)
        local fsize
        fsize=$(get_file_size "${f}")
        if [[ "${fsize}" -gt 10485760 ]]; then
            local non_null_tail
            non_null_tail=$(tail -c 512 "${f}" 2>/dev/null | tr -d '\000' | wc -c || echo 1)
            if [[ "${non_null_tail}" -eq 0 ]]; then
                return 1
            fi
        fi
    done
    return 0
}

if ! check_integrity; then
    echo "" >&2
    echo "================================================================================" >&2
    echo "[ERROR] Counterfeit flash media corruption detected! Unbacked phantom sectors found on drive." >&2
    echo "Storage hardware reports capacity that exceeds real physical silicon." >&2
    echo "Critical data files sit in unbacked sectors and read back as blank null bytes (\x00)." >&2
    echo "Launch aborted to prevent silent data loss and runtime crashes." >&2
    echo "Please re-provision this bundle onto a genuine, verified flash drive or SSD." >&2
    echo "================================================================================" >&2
    echo "" >&2
    exit 1
fi

PORT="${EMYRGE_PORT:-8000}"
ARCH="$(uname -m)"

if [[ -t 1 ]]; then
    clear 2>/dev/null || true
fi
cat <<'BANNER'
================================================================================
    ____   __  __  _____      _     _ _    _  _____ ____      _______
   / __ \ / _|/ _|/ ____|    (_)   | | |  | |/ ____|  _ \    |  ___  |===+
  | |  | | |_| |_| |  __ _ __ _  __| | |  | | (___ | |_) |   | [AI+] |:::|
  | |  | |  _|  _| | |_ | '__| |/ _` | |  | |\___ \|  _ <    | [ZIM] |:::|
  | |__| | | | | | |__| | |  | | (_| | |__| |____) | |_) |   |_______|===+
   \____/|_| |_|  \_____|_|  |_|\__,_|\____/|_____/|____/   OFFGRIDUSB.COM
--------------------------------------------------------------------------------
  Signed: @TheBlindHacker  •  @johndikeman  •  @organized-nick  •  OffGridUSB Team
  [*] 100% Air-Gapped Offline Operation: Zero External Network Access Required
================================================================================
BANNER
echo "  Linux & Raspberry Pi USB Portable Edition (${ARCH} — x86_64 & ARM64)"
echo "  Local Command Center : http://127.0.0.1:${PORT}"
echo "  Offline ZIM Library  : http://127.0.0.1:8081"
echo "================================================================================"
echo ""

launch_desktop_browser() {
    local url="$1"

    # If invoked via sudo on Raspberry Pi OS / Ubuntu, resolve the desktop user's display session
    local target_user="${SUDO_USER:-}"
    local target_uid
    if [[ -n "${target_user}" && "${EUID:-$(id -u)}" -eq 0 ]]; then
        target_uid="$(id -u "${target_user}" 2>/dev/null || echo 1000)"
    else
        target_uid="${EUID:-$(id -u)}"
    fi

    if [[ -z "${XDG_RUNTIME_DIR:-}" && -d "/run/user/${target_uid}" ]]; then
        export XDG_RUNTIME_DIR="/run/user/${target_uid}"
    fi
    if [[ -z "${WAYLAND_DISPLAY:-}" && -n "${XDG_RUNTIME_DIR:-}" ]]; then
        for wl in "${XDG_RUNTIME_DIR}"/wayland-*; do
            if [[ -S "${wl}" ]]; then
                export WAYLAND_DISPLAY="$(basename "${wl}")"
                break
            fi
        done
    fi
    if [[ -z "${DISPLAY:-}" && -S "/tmp/.X11-unix/X0" ]]; then
        export DISPLAY=":0"
    fi

    if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
        return 0
    fi

    # Helper to run browser as the non-root desktop user when script was launched under sudo
    run_as_desktop_user() {
        if [[ -n "${target_user}" && "${EUID:-$(id -u)}" -eq 0 ]]; then
            sudo -u "${target_user}" \
                DISPLAY="${DISPLAY:-:0}" \
                WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
                XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${target_uid}}" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${target_uid}/bus" \
                nohup "$@" >/dev/null 2>&1 &
        else
            nohup "$@" >/dev/null 2>&1 &
        fi
    }

    for b in xdg-open chromium-browser chromium firefox firefox-esr sensible-browser x-www-browser; do
        if command -v "${b}" >/dev/null 2>&1; then
            run_as_desktop_user "${b}" "${url}"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1; then
        run_as_desktop_user python3 -m webbrowser "${url}"
    fi
}

(
    # Wait up to 60s for the HTTP server to actually answer HTTP 200 on /api/status or /
    for _ in $(seq 1 120); do
        if command -v curl >/dev/null 2>&1; then
            if curl -sf --max-time 1 "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
                break
            fi
        elif command -v python3 >/dev/null 2>&1; then
            if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/api/status', timeout=1)" >/dev/null 2>&1; then
                break
            fi
        fi
        sleep 0.5
    done
    launch_desktop_browser "http://127.0.0.1:${PORT}"
) &

RUNNER="${SCRIPT_DIR}/run_linux.sh"
if [[ ! -f "${RUNNER}" && -f "${SCRIPT_DIR}/bin/run_linux.sh" ]]; then
    RUNNER="${SCRIPT_DIR}/bin/run_linux.sh"
fi

chmod +x "${RUNNER}" 2>/dev/null || true
exec bash "${RUNNER}" --host 127.0.0.1 --port "${PORT}" --headless "$@"
