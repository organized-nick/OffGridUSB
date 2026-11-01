#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

# ==============================================================================
# Pre-Flight Storage Integrity Check: Detect Counterfeit Phantom Sectors (<2.0s)
# ==============================================================================
check_integrity() {
    local target_files=()
    
    # 1. High-LBA Canary file
    if [[ -f "${SCRIPT_DIR}/data/.integrity_canary" ]]; then
        target_files+=("${SCRIPT_DIR}/data/.integrity_canary")
    fi
    
    # 2. Large content assets (ZIM and GGUF)
    for f in "${SCRIPT_DIR}"/data/zim/*.zim "${SCRIPT_DIR}"/data/models/*.gguf; do
        if [[ -f "${f}" ]]; then
            target_files+=("${f}")
        fi
    done
    
    # 3. Fallback to bin archives if no data assets staged yet
    if [[ ${#target_files[@]} -eq 0 ]]; then
        for f in "${SCRIPT_DIR}"/bin/*/*.tar.gz "${SCRIPT_DIR}"/bin/*/*/*; do
            if [[ -f "${f}" ]]; then
                target_files+=("${f}")
                if [[ ${#target_files[@]} -ge 4 ]]; then break; fi
            fi
        done
    fi
    
    for f in "${target_files[@]}"; do
        if [[ ! -s "${f}" ]]; then
            continue
        fi
        
        # Check Head (first 512 bytes)
        local non_null_head
        non_null_head=$(dd if="${f}" bs=512 count=1 2>/dev/null | tr -d '\000' | wc -c)
        if [[ "${non_null_head}" -eq 0 ]]; then
            return 1
        fi
        
        # Check Tail for large files (> 10MB)
        local fsize
        fsize=$(wc -c < "${f}" 2>/dev/null || echo 0)
        if [[ "${fsize}" -gt 10485760 ]]; then
            local non_null_tail
            local blocks=$(( fsize / 512 ))
            if [[ "${blocks}" -gt 0 ]]; then
                local skip_blocks=$(( blocks - 1 ))
                non_null_tail=$(dd if="${f}" bs=512 skip="${skip_blocks}" count=1 2>/dev/null | tr -d '\000' | wc -c)
                if [[ "${non_null_tail}" -eq 0 ]]; then
                    return 1
                fi
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
  Signed: @TheBlindHacker  •  @johndikeman  •  @organized-nick  •  OffGridUSB Team
  [*] 100% Air-Gapped Offline Operation: Zero External Network Access Required
================================================================================
BANNER
echo "  Local Command Center : http://127.0.0.1:${PORT}"
echo "  Offline ZIM Library  : http://127.0.0.1:8081"
echo "================================================================================"
echo ""

(
    for _ in {1..30}; do
        if curl -sf "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true
) &

RUNNER="${SCRIPT_DIR}/run_macos.command"
if [[ ! -f "${RUNNER}" && -f "${SCRIPT_DIR}/bin/run_macos.command" ]]; then
    RUNNER="${SCRIPT_DIR}/bin/run_macos.command"
fi

chmod +x "${RUNNER}" 2>/dev/null || true
exec bash "${RUNNER}" --host 127.0.0.1 --port "${PORT}" --headless
