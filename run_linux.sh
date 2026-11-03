#!/usr/bin/env bash
# Re-exec under bash if invoked via `sh run_linux.sh` (e.g. dash on Debian/Raspberry Pi OS)
if [ -z "${BASH_VERSION:-}" ]; then
    exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

# ============================================================================
# OffGridUSB (offgridusb.com) — Portable Single-Click Linux Launcher (F-02)
# Zero-install, container-free air-gapped knowledge and adaptive AI harness
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -d "${SCRIPT_DIR}/src/emyrge" && -d "${SCRIPT_DIR}/../src/emyrge" ]]; then
    SCRIPT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
cd "${SCRIPT_DIR}"

# 1. Architecture Detection (x86_64, ARM64, and 32-bit Raspberry Pi ARMv7/v6 supported)
ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64|amd64)
        ARCH_DIR="linux_x86_64"
        ;;
    aarch64|arm64)
        ARCH_DIR="linux_arm64"
        ;;
    armv7*|armv8*|armv6*|arm*)
        ARCH_DIR="linux_arm64"
        echo "[INFO] Detected 32-bit ARM kernel (${ARCH}); running pure-Python web & ZIM engine."
        ;;
    *)
        echo "[WARN] Unrecognized CPU architecture: ${ARCH}; attempting portable Python fallback." >&2
        ARCH_DIR="linux_${ARCH}"
        ;;
esac

# 2. Parse Command Line Arguments
PORT="${EMYRGE_PORT:-8000}"
HOST="${EMYRGE_HOST:-127.0.0.1}"
HEADLESS=0
CHROMEBOOK=0
TIER_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "============================================================================"
            echo "OffGridUSB (offgridusb.com) Linux & Raspberry Pi Launcher"
            echo "============================================================================"
            echo "Usage: ./run_linux.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port PORT       Set backend server port (default: 8000)"
            echo "  --host HOST       Set bind address (default: 127.0.0.1, 0.0.0.0 for LAN)"
            echo "  --headless        Do not automatically open default web browser"
            echo "  --chromebook      Open pure-browser Wasm fallback shell directly"
            echo "  --tier TIER       Force hardware tier override (-1 to 4)"
            echo "  --help, -h        Display this help message"
            echo "============================================================================"
            exit 0
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --headless)
            HEADLESS=1
            shift
            ;;
        --chromebook)
            CHROMEBOOK=1
            shift
            ;;
        --tier)
            TIER_OVERRIDE="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# 3. Browser Launch Helper (Raspberry Pi OS Wayland / X11 + sudo-aware)
open_browser() {
    local target="$1"
    if [[ "${HEADLESS}" -eq 1 ]]; then
        return 0
    fi

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
            run_as_desktop_user "${b}" "${target}"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1; then
        run_as_desktop_user python3 -m webbrowser "${target}"
    fi
}

if [[ "${CHROMEBOOK}" -eq 1 ]]; then
    echo "[INFO] Launching pure-browser Wasm fallback shell..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
    exit 0
fi

# 4. Python Discovery Hierarchy (Bundled -> VirtualEnv -> System)
PYTHON_CMD=""
CANDIDATES=(
    "${SCRIPT_DIR}/bin/${ARCH_DIR}/python/bin/python3"
    "${SCRIPT_DIR}/bin/linux_${ARCH}/python/bin/python3"
    "${SCRIPT_DIR}/bin/python/bin/python3"
    "${SCRIPT_DIR}/.venv/bin/python3"
    "python3"
    "python"
)

for cmd in "${CANDIDATES[@]}"; do
    if [[ -x "${cmd}" ]] || command -v "${cmd}" >/dev/null 2>&1; then
        if "${cmd}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
            PYTHON_CMD="${cmd}"
            break
        fi
    fi
done

if [[ -z "${PYTHON_CMD}" ]]; then
    echo "[ERROR] Compatible Python 3 runtime not found (requires Python 3.9+)." >&2
    echo "Opening fallback browser shell..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
    exit 3
fi

# 5. Configure Isolated Environment (PYTHONDONTWRITEBYTECODE avoids writing .pyc files to exFAT USB)
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}"
export EMYRGE_PORT="${PORT}"
export EMYRGE_HOST="${HOST}"
if [[ -n "${TIER_OVERRIDE}" ]]; then
    export EMYRGE_TIER="${TIER_OVERRIDE}"
fi

# 6. Signal Handling for Graceful Shutdown
SERVER_PID=""
cleanup() {
    if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo "[INFO] Shutting down OffGridUSB server (PID: ${SERVER_PID})..."
        kill -TERM "${SERVER_PID}" 2>/dev/null || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup SIGINT SIGTERM EXIT

# 7. Launch Server or Fallback Interface
echo "============================================================================"
echo "OffGridUSB (offgridusb.com) — Offline Knowledge & Adaptive AI Harness"
echo "Host: ${HOST}  Port: ${PORT}  Arch: ${ARCH}"
echo "============================================================================"

if [[ -f "${SCRIPT_DIR}/src/emyrge/web/app.py" ]]; then
    APP_ARGS=(--host "${HOST}" --port "${PORT}" --headless)
    "${PYTHON_CMD}" -B -m emyrge.web.app "${APP_ARGS[@]}" &
    SERVER_PID=$!

    if [[ "${HEADLESS}" -eq 0 ]]; then
        BROWSER_HOST="${HOST}"
        if [[ "${BROWSER_HOST}" == "0.0.0.0" || -z "${BROWSER_HOST}" ]]; then
            BROWSER_HOST="127.0.0.1"
        fi
        (
            for _ in $(seq 1 120); do
                if command -v curl >/dev/null 2>&1; then
                    if curl -sf --max-time 1 "http://${BROWSER_HOST}:${PORT}/api/status" >/dev/null 2>&1; then
                        break
                    fi
                elif "${PYTHON_CMD}" -c "import urllib.request; urllib.request.urlopen('http://${BROWSER_HOST}:${PORT}/api/status', timeout=1)" >/dev/null 2>&1; then
                    break
                fi
                sleep 0.5
            done
            open_browser "http://${BROWSER_HOST}:${PORT}"
        ) &
    fi

    wait "${SERVER_PID}"
else
    echo "[INFO] Core Skeleton initialized. Launching browser interface..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
fi

exit 0
