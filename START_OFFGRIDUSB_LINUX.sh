#!/usr/bin/env bash
# Re-exec under bash if invoked via `sh START_OFFGRIDUSB_LINUX.sh` (e.g. dash on Debian/Raspberry Pi OS)
if [ -z "${BASH_VERSION:-}" ]; then
    exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# ==============================================================================
# 0. Desktop File Manager Auto-Terminal Support
# If double-clicked via GUI "Execute" (no TTY attached and TERM unset/dumb),
# automatically spawn a visible desktop terminal emulator so logs populate live.
# ==============================================================================
WANT_HEADLESS=0
for _arg in "$@"; do
    case "${_arg}" in
        --headless|--help|-h|--chromebook)
            WANT_HEADLESS=1
            ;;
    esac
done

ensure_gui_display_env() {
    local uid="${EUID:-$(id -u)}"
    if [[ -z "${XDG_RUNTIME_DIR:-}" && -d "/run/user/${uid}" ]]; then
        export XDG_RUNTIME_DIR="/run/user/${uid}"
    fi
    if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "/run/user/${uid}/bus" ]]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${uid}/bus"
    fi
    if [[ -z "${WAYLAND_DISPLAY:-}" && -n "${XDG_RUNTIME_DIR:-}" ]]; then
        for wl in "${XDG_RUNTIME_DIR}"/wayland-*; do
            if [[ -S "${wl}" ]]; then
                export WAYLAND_DISPLAY="$(basename "${wl}")"
                break
            fi
        done
    fi
    if [[ -z "${DISPLAY:-}" ]]; then
        for xs in /tmp/.X11-unix/X*; do
            if [[ -S "${xs}" ]]; then
                export DISPLAY=":${xs##*X}"
                break
            fi
        done
    fi
}

if [[ "${WANT_HEADLESS}" -eq 0 && ! -t 0 && ! -t 1 && -z "${OFFGRIDUSB_IN_TERMINAL:-}" && -z "${OFFGRIDUSB_NO_TERMINAL:-}" && ( -z "${TERM:-}" || "${TERM:-}" == "dumb" ) ]]; then
    ensure_gui_display_env
    if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
        export OFFGRIDUSB_IN_TERMINAL=1
        export OFFGRIDUSB_LAUNCH_SCRIPT="${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh"
        spawned_term=0
        if command -v lxterminal >/dev/null 2>&1; then
            lxterminal --title="OffGridUSB Command Center" -e /bin/bash -c 'exec /bin/bash "$OFFGRIDUSB_LAUNCH_SCRIPT"' >/dev/null 2>&1 &
            spawned_term=1
        elif command -v xfce4-terminal >/dev/null 2>&1; then
            xfce4-terminal --title="OffGridUSB Command Center" -x /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v gnome-terminal >/dev/null 2>&1; then
            gnome-terminal --title="OffGridUSB Command Center" -- /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v ptyxis >/dev/null 2>&1; then
            ptyxis -- /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v kgx >/dev/null 2>&1; then
            kgx -- /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v mate-terminal >/dev/null 2>&1; then
            mate-terminal -x /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v konsole >/dev/null 2>&1; then
            konsole -e /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v tilix >/dev/null 2>&1; then
            tilix -e /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v kitty >/dev/null 2>&1; then
            kitty /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v alacritty >/dev/null 2>&1; then
            alacritty -e /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        elif command -v x-terminal-emulator >/dev/null 2>&1; then
            x-terminal-emulator -e /bin/bash -c 'exec /bin/bash "$OFFGRIDUSB_LAUNCH_SCRIPT"' >/dev/null 2>&1 &
            spawned_term=1
        elif command -v xterm >/dev/null 2>&1; then
            xterm -T "OffGridUSB Command Center" -e /bin/bash "${SCRIPT_DIR}/START_OFFGRIDUSB_LINUX.sh" "$@" >/dev/null 2>&1 &
            spawned_term=1
        fi
        if [[ "${spawned_term}" -eq 1 ]]; then
            sleep 0.3
            exit 0
        fi
    fi
fi

pause_if_interactive() {
    if [[ -t 0 && -t 1 ]]; then
        echo ""
        read -r -p "  Press Enter to close this window..." _ || true
    fi
}

# ==============================================================================
# 1. Populate Terminal Immediately (Zero Blank Window Delay on Slow USB Ports)
# ==============================================================================
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
  Signed: @TheBlindHacker  *  @johndikeman  *  @organized-nick  *  OffGridUSB Team
  [*] 100% Air-Gapped Offline Operation: Zero External Network Access Required
================================================================================
BANNER
echo "  Linux & Raspberry Pi USB Portable Edition (${ARCH} — x86_64 & ARM64)"
echo "  Active USB Mount     : ${SCRIPT_DIR}"
echo "  Offline ZIM Library  : http://127.0.0.1:8081"
echo "================================================================================"
echo "  [1/2] Verifying flash media integrity..."

# ==============================================================================
# 2. Fast Pre-Flight Storage Integrity Check (< 0.2s on Raspberry Pi / USB 2.0)
# ==============================================================================
get_file_size() {
    local file="$1"
    stat -c %s "${file}" 2>/dev/null || stat -f %z "${file}" 2>/dev/null || wc -c < "${file}" 2>/dev/null || echo 0
}

check_integrity() {
    local target_files=()

    if [[ -f "${SCRIPT_DIR}/data/.integrity_canary" ]]; then
        target_files+=("${SCRIPT_DIR}/data/.integrity_canary")
    fi

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

        local non_null_head
        non_null_head=$(head -c 512 "${f}" 2>/dev/null | LC_ALL=C tr -d '\000' | wc -c || echo 1)
        if [[ "${non_null_head}" -eq 0 ]]; then
            return 1
        fi

        local fsize
        fsize=$(get_file_size "${f}")
        if [[ "${fsize}" -gt 10485760 ]]; then
            local non_null_tail
            non_null_tail=$(tail -c 512 "${f}" 2>/dev/null | LC_ALL=C tr -d '\000' | wc -c || echo 1)
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
    pause_if_interactive
    exit 1
fi

echo "  [2/2] Starting OffGridUSB Engine & opening web client..."
echo "        (Keep this terminal window open while using OffGridUSB. Press Ctrl+C to stop.)"
echo ""

RUNNER="${SCRIPT_DIR}/run_linux.sh"
if [[ ! -f "${RUNNER}" && -f "${SCRIPT_DIR}/bin/run_linux.sh" ]]; then
    RUNNER="${SCRIPT_DIR}/bin/run_linux.sh"
fi

if [[ ! -f "${RUNNER}" ]]; then
    echo "[ERROR] Launcher script run_linux.sh not found in ${SCRIPT_DIR}." >&2
    pause_if_interactive
    exit 1
fi

chmod +x "${RUNNER}" 2>/dev/null || true
cd /tmp 2>/dev/null || true
set +e
/usr/bin/env bash "${RUNNER}" "$@"
EXIT_CODE=$?
set -e

if [[ "${EXIT_CODE}" -ne 0 && "${EXIT_CODE}" -ne 130 && "${EXIT_CODE}" -ne 143 ]]; then
    echo "" >&2
    echo "================================================================================" >&2
    echo "  [WARN] OffGridUSB exited with status code ${EXIT_CODE}." >&2
    echo "================================================================================" >&2
    pause_if_interactive
fi
exit "${EXIT_CODE}"
