#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# OffGridUSB (offgridusb.com) — Portable Single-Click macOS Launcher (F-03)
# Zero-install, container-free air-gapped knowledge and adaptive AI harness
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -d "${SCRIPT_DIR}/src/emyrge" && -d "${SCRIPT_DIR}/../src/emyrge" ]]; then
    SCRIPT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
cd "${SCRIPT_DIR}"
export PYTHONDONTWRITEBYTECODE=1

ARCH="$(uname -m)"
if [[ "${ARCH}" != "arm64" && "${ARCH}" != "x86_64" ]]; then
    echo "[ERROR] Unsupported CPU architecture: ${ARCH}." >&2
    exit 2
fi

PORT="${EMYRGE_PORT:-8000}"
EXPLICIT_PORT=0
if [[ -n "${EMYRGE_PORT:-}" ]]; then
    EXPLICIT_PORT=1
fi
HOST="${EMYRGE_HOST:-127.0.0.1}"
HEADLESS=0
CHROMEBOOK=0
TIER_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "============================================================================"
            echo "OffGridUSB (offgridusb.com) macOS Launcher"
            echo "============================================================================"
            echo "Usage: ./run_macos.command [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port PORT       Set backend server port (default: 8000, auto-fallback if busy)"
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
            EXPLICIT_PORT=1
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

open_browser() {
    local target="$1"
    if [[ "${HEADLESS}" -eq 1 ]]; then
        return 0
    fi
    open "${target}" >/dev/null 2>&1 &
}

if [[ "${CHROMEBOOK}" -eq 1 ]]; then
    echo "[INFO] Launching pure-browser Wasm fallback shell..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
    exit 0
fi

PYTHON_CMD=""
CANDIDATES=(
    "${SCRIPT_DIR}/bin/macos_${ARCH}/python/bin/python3"
    "${SCRIPT_DIR}/bin/python/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
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

BROWSER_HOST="${HOST}"
if [[ "${BROWSER_HOST}" == "0.0.0.0" || -z "${BROWSER_HOST}" ]]; then
    BROWSER_HOST="127.0.0.1"
fi

if [[ "${EXPLICIT_PORT}" -eq 0 ]]; then
    PORT_PROBE="$("${PYTHON_CMD}" -B -c "
import json, socket, sys, urllib.request
host, port = sys.argv[1], int(sys.argv[2])
probe_host = '127.0.0.1' if host in ('0.0.0.0', '') else host
def is_open(h, p):
    try:
        with socket.create_connection((h, p), timeout=0.25):
            return True
    except OSError:
        return False
if is_open(probe_host, port):
    for ep in ('/api/ping', '/api/status'):
        try:
            with urllib.request.urlopen(f'http://{probe_host}:{port}{ep}', timeout=1.5) as r:
                d = json.loads(r.read().decode('utf-8', 'ignore'))
                if d.get('service') == 'offgridusb' or 'product' in d or 'hardware' in d:
                    print(f'EXISTING:{port}')
                    sys.exit(0)
        except Exception:
            pass
    for cand in range(port + 1, port + 21):
        if not is_open(probe_host, cand):
            print(f'FREE:{cand}')
            sys.exit(0)
print(f'FREE:{port}')
" "${HOST}" "${PORT}" 2>/dev/null || echo "FREE:${PORT}")"

    if [[ "${PORT_PROBE}" == EXISTING:* ]]; then
        PORT="${PORT_PROBE#EXISTING:}"
        echo "[INFO] OffGridUSB Engine is already running at http://${BROWSER_HOST}:${PORT}"
        open_browser "http://${BROWSER_HOST}:${PORT}"
        exit 0
    elif [[ "${PORT_PROBE}" == FREE:* ]]; then
        PORT="${PORT_PROBE#FREE:}"
    fi
fi

export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}"
export EMYRGE_PORT="${PORT}"
export EMYRGE_HOST="${HOST}"
if [[ -n "${TIER_OVERRIDE}" ]]; then
    export EMYRGE_TIER="${TIER_OVERRIDE}"
fi

SERVER_PID=""
WATCHER_PID=""
cleanup() {
    if [[ -n "${WATCHER_PID}" ]] && kill -0 "${WATCHER_PID}" 2>/dev/null; then
        kill -TERM "${WATCHER_PID}" 2>/dev/null || true
    fi
    if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo "[INFO] Shutting down OffGridUSB server (PID: ${SERVER_PID})..."
        kill -TERM "${SERVER_PID}" 2>/dev/null || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup SIGINT SIGTERM EXIT

echo "============================================================================"
echo "OffGridUSB (offgridusb.com) — Offline Knowledge & Adaptive AI Harness"
echo "Command Center : http://${BROWSER_HOST}:${PORT}"
echo "Host: ${HOST}  Port: ${PORT}  Arch: ${ARCH}  Mount: ${SCRIPT_DIR}"
echo "============================================================================"

if [[ -f "${SCRIPT_DIR}/src/emyrge/web/app.py" ]]; then
    cd /tmp 2>/dev/null || true
    APP_ARGS=(--host "${HOST}" --port "${PORT}" --headless)
    if [[ -n "${TIER_OVERRIDE}" ]]; then
        APP_ARGS+=(--tier "${TIER_OVERRIDE}")
    fi
    "${PYTHON_CMD}" -B -m emyrge.web.app "${APP_ARGS[@]}" &
    SERVER_PID=$!

    if [[ "${HEADLESS}" -eq 0 ]]; then
        (
            ready=0
            for _ in $(seq 1 60); do
                if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
                    exit 0
                fi
                if curl -sf --max-time 3 "http://${BROWSER_HOST}:${PORT}/api/ping" >/dev/null 2>&1 || \
                   curl -sf --max-time 3 "http://${BROWSER_HOST}:${PORT}/api/status" >/dev/null 2>&1; then
                    ready=1
                    break
                fi
                sleep 0.4
            done
            if [[ "${ready}" -eq 1 ]]; then
                open_browser "http://${BROWSER_HOST}:${PORT}"
            fi
        ) &
        WATCHER_PID=$!
    fi
    wait "${SERVER_PID}"
else
    echo "[INFO] Core Skeleton initialized. Launching browser interface..."
    open_browser "${SCRIPT_DIR}/web/static/wasm/chromebook.html"
fi

exit 0
