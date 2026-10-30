#!/usr/bin/env bash
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

# 1. Architecture Validation (x86_64 and ARM64 supported)
ARCH="$(uname -m)"
if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "aarch64" && "${ARCH}" != "arm64" ]]; then
    echo "[ERROR] Unsupported CPU architecture: ${ARCH}." >&2
    echo "OffGridUSB requires a 64-bit architecture (x86_64 or aarch64/arm64)." >&2
    exit 2
fi

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
            echo "OffGridUSB (offgridusb.com) Linux Launcher"
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

# 3. Pure Chromebook Browser Wasm Fallback Request
open_browser() {
    local target="$1"
    if [[ "${HEADLESS}" -eq 1 ]]; then
        return 0
    fi
    if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "${target}" >/dev/null 2>&1 &
        elif command -v sensible-browser >/dev/null 2>&1; then
            sensible-browser "${target}" >/dev/null 2>&1 &
        elif command -v python3 >/dev/null 2>&1; then
            python3 -m webbrowser "${target}" >/dev/null 2>&1 &
        fi
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
    "${SCRIPT_DIR}/bin/linux_${ARCH}/python/bin/python3"
    "${SCRIPT_DIR}/bin/python/bin/python3"
    "${SCRIPT_DIR}/.venv/bin/python3"
    "python3"
    "python"
)

for cmd in "${CANDIDATES[@]}"; do
    if [[ -x "${cmd}" ]] || command -v "${cmd}" >/dev/null 2>&1; then
        if "${cmd}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
            PYTHON_CMD="${cmd}"
            break
        fi
    fi
done

if [[ -z "${PYTHON_CMD}" ]]; then
    echo "[ERROR] Compatible Python 3 runtime not found (requires Python 3.10+)." >&2
    echo "Opening fallback browser shell..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
    exit 3
fi

# 5. Configure Isolated Environment
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
    "${PYTHON_CMD}" -m emyrge.web.app --host "${HOST}" --port "${PORT}" &
    SERVER_PID=$!
    sleep 0.5
    open_browser "http://${HOST}:${PORT}"
    wait "${SERVER_PID}"
else
    echo "[INFO] Core Skeleton initialized. Launching browser interface..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
fi

exit 0
