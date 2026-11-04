#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"
export PYTHONDONTWRITEBYTECODE=1

clear 2>/dev/null || true
cat <<'BANNER'
================================================================================
    ____   __  __  _____      _     _ _    _  _____ ____      _______
   / __ \ / _|/ _|/ ____|    (_)   | | |  | |/ ____|  _ \    |  ___  |===+
  | |  | | |_| |_| |  __ _ __ _  __| | |  | | (___ | |_) |   | [AI+] |:::|
  | |  | |  _|  _| | |_ | '__| |/ _` | |  | |\___ \|  _ <    | [ZIM] |:::|
  | |__| | | | | | |__| | |  | | (_| | |__| |____) | |_) |   |_______|===+
   \____/|_| |_|  \_____|_|  |_|\__,_|\____/|_____/|____/   OFFGRIDUSB.COM
--------------------------------------------------------------------------------
  macOS USB Portable Edition (Apple Silicon ARM64 & Intel x86_64)
  Zero Docker  |  Zero Cloud  |  100% Air-Gapped
  Signed: @TheBlindHacker  *  @johndikeman  *  @organized-nick  *  OffGridUSB Team
  [*] 100% Air-Gapped Offline Operation: Zero External Network Access Required
================================================================================
BANNER
echo "  Active USB Mount     : ${SCRIPT_DIR}"
echo "  Offline ZIM Library  : http://127.0.0.1:8081"
echo "================================================================================"
echo "  [1/2] Verifying flash media integrity..."

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
        fsize=$(stat -f %z "${f}" 2>/dev/null || wc -c < "${f}" 2>/dev/null || echo 0)
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
    echo "" >&2
    exit 1
fi

echo "  [2/2] Starting OffGridUSB Engine & opening web client..."
echo ""

RUNNER="${SCRIPT_DIR}/run_macos.command"
if [[ ! -f "${RUNNER}" && -f "${SCRIPT_DIR}/bin/run_macos.command" ]]; then
    RUNNER="${SCRIPT_DIR}/bin/run_macos.command"
fi

chmod +x "${RUNNER}" 2>/dev/null || true
exec /bin/bash "${RUNNER}" "$@"
