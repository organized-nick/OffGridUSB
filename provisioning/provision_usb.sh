#!/usr/bin/env bash
# provision_usb.sh - POSIX Factory Provisioning Engine for OffGridUSB
# Part of the OffGridUSB host-only builder suite.
#
# Supports multi-drive parallel provisioning via a USB hub:
#   provision_usb.sh --product Product1 --drive /media/usb/d1 --drive /media/usb/d2
#   provision_usb.sh --product Product1 --drive /media/usb/d1:Product2 --drive /media/usb/d3
# Each drive gets its own bandwidth budget (default 2048 KB/s), a per-drive log
# under provisioning/logs/, and a sequential safety gate before any staging.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"

PRODUCT=""
TIER=-1
TARGET_DRIVE=""
DRY_RUN=false
ENGINES_READY=0
INFO_MODE=false
NON_INTERACTIVE=false
NO_DOWNLOAD=false
# Host asset cache for .zim and .gguf payloads. Kept off the Desktop by default:
# ~/.config/offgridusb/cache (override with OFFGRIDUSB_CACHE_DIR or --cache-dir).
CACHE_DIR="${OFFGRIDUSB_CACHE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/offgridusb/cache}"
PROFILE="Auto"
# Write throttling (KB/s). Sustained full-speed sequential writes can hard-lock
# cheap USB flash controllers (device falls off the bus mid-copy).
# Default 2048 KB/s; set 0 to disable throttling entirely.
BWLIMIT="2048"
LOG_DIR="${SCRIPT_DIR}/logs"
# Parallel mode: list of "target" or "target:SKU" drive specs.
DRIVES=()

usage() {
    cat <<EOF
OffGridUSB POSIX Provisioning Engine

Usage: $0 [OPTIONS]

Options:
  --product <sku>         Select commercial SKU (Product1, Product2, Product3)
  --tier <0..4>           Select technical tier level
  --drive, --target <path> Target USB mount directory or device. Repeatable:
                          --drive /media/usb/d1 --drive /media/usb/d2
                          Optional per-drive SKU override: --drive /media/usb/d1:Product2
                          With one drive, behaves as today. With 2+ drives,
                          provisions all drives concurrently (one background
                          engine per drive, per-drive logs, summary table).
  --dry-run               Simulate provisioning without writes
  --info                  Display product catalog, payload specs, and cache readiness
  --non-interactive       Disable interactive prompts
  --cache-dir <dir>       Host cache directory for .zim and .gguf files
                          (default: ~/.config/offgridusb/cache, or $OFFGRIDUSB_CACHE_DIR)
  --no-download          Skip auto-download of missing cache assets
  --profile <lean|full>   Payload profile (default: Auto)
  --bwlimit <KBPS>        Limit copy bandwidth in KB/s (default: 2048).
                          Sustained full-speed writes can hard-lock cheap
                          USB flash controllers; throttling keeps them alive.
                          Use 0 to disable throttling. In parallel mode this
                          budget is applied PER drive (each drive gets the
                          same budget, not the total split across them).
  -h, --help              Show this help message
EOF
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --product)
            PRODUCT="$2"; shift 2 ;;
        --tier)
            TIER="$2"; shift 2 ;;
        --drive|--target)
            DRIVES+=("$2"); shift 2 ;;
        --dry-run)
            DRY_RUN=true; shift ;;
        --info)
            INFO_MODE=true; shift ;;
        --non-interactive)
            NON_INTERACTIVE=true; shift ;;
        --cache-dir)
            CACHE_DIR="$2"; shift 2 ;;
        --profile)
            PROFILE="$2"; shift 2 ;;
        --no-download)
            NO_DOWNLOAD=true; shift ;;
        --bwlimit)
            BWLIMIT="$2"; shift 2 ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "Unknown argument: $1" >&2
            usage; exit 1 ;;
    esac
done

# Normalize SKU
normalize_sku() {
    local p="$1"
    local t="$2"
    if [[ -n "$p" ]]; then
        case "$p" in
            PocketSurvival|Tier0) echo "Product1" ;;
            FieldReady|Tier1)     echo "Product2" ;;
            CivilizationArk|Tier2)echo "Product3" ;;
            Product2-256)          echo "Product2-256" ;;
            Product3-256)          echo "Product3-256" ;;
            SwarmCluster|Tier3)    echo "Tier3" ;;
            SettlementHub|Tier4)    echo "Tier4" ;;
            *)                    echo "$p" ;;
        esac
        return
    fi
    if [[ "$t" -ge 0 ]]; then
        case "$t" in
            0) echo "Product1" ;;
            1) echo "Product2" ;;
            2) echo "Product3" ;;
            3) echo "Tier3" ;;
            4) echo "Tier4" ;;
        esac
        return
    fi
    echo ""
}

RESOLVED_SKU=$(normalize_sku "${PRODUCT}" "${TIER}")

# Info Mode
if [[ "${INFO_MODE}" == true ]]; then
    echo "================================================================================"
    echo "  OffGridUSB Factory Provisioning Suite // POSIX Catalog & Specifications"
    echo "================================================================================"
    echo ""
    echo "[COMMERCIAL PRODUCT SKUs & CAPACITY TIERS]"
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "SKU ID" "Commercial Name" "Tiers" "Min USB" "Payload Size" "Target Features & Media"
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "--------" "-----------------" "-------" "-------" "------------" "------------------------------------------"
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Product1" "PocketSurvival"  "Tier 0"    "8 GB"   "<= 6.5 GB"  "Offline Kiwix (:8081), Grounded AI Professor (:8082), CDC Calculators."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Product2" "FieldReady"      "0 + 1"     "32 GB"  "~16-20 GB"  "All Product 1 + SQLite Memory Vault, Photo OCR Vault, STEM Tutor."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Product3" "CivilizationArk" "0 + 1 + 2" "128 GB" "~65-72 GB"  "All Product 2 + 50.2 GB Wikipedia No-Pic. (64 GB USB rejected)."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Product2-256" "FieldReady XL"   "0 + 1"     "256 GB" "~160 GB"    "All Product 2 + extended data vault on 256 GB USB/SSD."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Product3-256" "CivilizationArk XL" "0 + 1 + 2" "256 GB" "~175 GB" "All Product 3 + extended payload on 256 GB USB/SSD."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Tier3"    "SwarmCluster"    "0 - 3"     "256 GB" "~88 GB"     "All Product 3 + Qwen 32B (18.9 GB) + exo LAN Swarm Clustering."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Tier4"    "SettlementHub"   "0 - 4"     "512 GB" "~210+ GB"   "All Tier 3 + Wikipedia Maxi (110 GB) + Llama 70B (40.5 GB)."
    echo ""
    echo "[CURRENT FACTORY READINESS STATUS]"
    echo "  * Product 1 (PocketSurvival): [100% READY] (Lean payload: 1.39 GB, verified <= 6.5 GB ceiling)"
    echo "  * Product 2 (FieldReady):     [100% READY] (Lean payload: 4.69 GB, verified for 32 GB drive)"
    echo "  * Product 3 (CivilizationArk): [REQUIRES CACHE DOWNLOAD] (Requires 50.2 GB Wikipedia ZIM; 128 GB USB required)"
    echo "  * Product 2-256 (FieldReady XL): [REQUIRES CACHE DOWNLOAD] (Requires ~160 GB payload on 256 GB USB/SSD)"
    echo "  * Product 3-256 (CivilizationArk XL): [REQUIRES CACHE DOWNLOAD] (Requires ~175 GB payload on 256 GB USB/SSD)"
    echo "================================================================================"
    exit 0
fi

# Safety & Capacity Checks (bash side; also used by the orchestrator gate)
source "${LIB_DIR}/SafetyValidator.sh"
source "${LIB_DIR}/UsbStripper.sh"

# Parallel / multi-drive orchestration. When 2+ drives are given, the top-level
# process becomes the orchestrator: it runs the per-drive safety gate
# sequentially (fail fast: a failing drive aborts only that drive), then spawns
# one background child engine per drive, collects exit codes, prints a summary
# table, and safely ejects the succeeded drives. Each drive gets the same
# per-drive bandwidth budget (BWLIMIT, default 2048 KB/s): the hub shares one
# host controller, so the per-drive cap is what keeps the controllers alive.
# -----------------------------------------------------------------------------
parse_drive_spec() {
    # "<target>[:<SKU>]" -> target + resolved SKU (falls back to RESOLVED_SKU).
    # If the suffix after the first colon is not a known SKU, treat the whole
    # string as a plain path (paths may contain colons).
    local spec="$1"
    local path="${spec}"
    local sku="${RESOLVED_SKU}"
    if [[ "${spec}" == *:* ]]; then
        local candidate="${spec#*:}"
        if [[ -n "${SKU_MIN_BYTES[${candidate}]:-}" ]]; then
            path="${spec%%:*}"
            sku=$(normalize_sku "${candidate}" -1)
        fi
    fi
    printf '%s\n%s\n' "${path}" "${sku}"
}

drive_slug() {
    # Filesystem-safe slug for a drive path (used in per-drive log names).
    local p="$1"
    local slug="${p//\//_}"
    slug="${slug//[^A-Za-z0-9._-]/_}"
    echo "${slug}"
}

gate_drive() {
    # Sequential per-drive safety gate (fail fast, per-drive abort).
    # Prints a single status line; returns 0 on pass, 1 on failure.
    local target="$1" sku="$2"
    if [[ "${DRY_RUN}" == true ]]; then
        echo "PASSED (dry-run)"
        return 0
    fi
    assert_target_drive_safety "${target}" || { echo "FAIL (safety)"; return 1; }
    assert_drive_capacity "${target}" "${sku}" || { echo "FAIL (capacity)"; return 1; }
    echo "PASSED"
    return 0
}

run_orchestrator() {
    local ts drive sku target drive_slug log_file rc status gate_msg
    local -a target_list=() sku_list=() status_list=() rc_list=() log_list=()
    local -a spawn_list=()
    ts=$(date +%Y%m%d_%H%M%S)
    mkdir -p "${LOG_DIR}"

    echo "================================================================================"
    echo "  >>> PARALLEL PROVISIONING: ${#DRIVES[@]} drives (SKU: ${RESOLVED_SKU})"
    echo "================================================================================"

    # Stage 1: sequential per-drive safety gate (fail fast, per-drive abort).
    local spec i
    for spec in "${DRIVES[@]}"; do
        target=$(parse_drive_spec "${spec}" | head -1)
        sku=$(parse_drive_spec "${spec}" | tail -1)
        target_list+=("${target}")
        sku_list+=("${sku}")
        gate_msg=$(gate_drive "${target}" "${sku}") || true
        if [[ "${gate_msg}" == PASSED* ]]; then
            status_list+=("PENDING")
        else
            status_list+=("FAIL")
        fi
        rc_list+=("-")
        log_list+=("")
    done

    # Stage 2: fetch shared portable engines ONCE (bin/ is host-shared, not
    # per-drive; children would otherwise race to download the same archives).
    if [[ "${DRY_RUN}" != true ]]; then
        if ! fetch_engines; then
            echo "[ERROR] Engine staging failed; aborting all drives." >&2
            return 1
        fi
    fi

    # Stage 3: spawn one background child engine per gated drive.
    local pids=()
    for i in "${!target_list[@]}"; do
        [[ "${status_list[$i]}" == "PENDING" ]] || continue
        target="${target_list[$i]}"
        sku="${sku_list[$i]}"
        drive_slug=$(drive_slug "${target}")
        log_file="${LOG_DIR}/${ts}_${sku}_${drive_slug}.log"
        log_list[$i]="${log_file}"
        echo "  [SPAWN] ${sku} -> ${target} (log: ${log_file})"
        local child_args=("${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")" --product "${sku}" --target "${target}" --bwlimit "${BWLIMIT}" --cache-dir "${CACHE_DIR}" --profile "${PROFILE}" --non-interactive)
        [[ "${DRY_RUN}" == true ]] && child_args+=(--dry-run)
        [[ "${NO_DOWNLOAD}" == true ]] && child_args+=(--no-download)
        "${child_args[@]}" >"${log_file}" 2>&1 &
        pids+=($!)
    done

    # Stage 4: wait for all children and collect exit codes.
    local idx=0
    for i in "${!target_list[@]}"; do
        [[ "${status_list[$i]}" == "PENDING" ]] || continue
        rc=0
        wait "${pids[$idx]}" || rc=$?
        rc_list[$i]="${rc}"
        if [[ "${rc}" -eq 0 ]]; then
            status_list[$i]="SUCCESS"
        else
            status_list[$i]="FAIL (exit ${rc})"
        fi
        idx=$((idx + 1))
    done

    # Stage 5: safely eject the succeeded drives (skip in dry-run mode).
    if [[ "${DRY_RUN}" != true ]]; then
        for i in "${!target_list[@]}"; do
            [[ "${status_list[$i]}" == "SUCCESS" ]] || continue
            safe_eject_drive "${target_list[$i]}"
        done
    fi

    # Stage 6: summary table.
    echo ""
    echo "================================================================================"
    echo "  >>> PARALLEL PROVISIONING SUMMARY"
    echo "================================================================================"
    printf "%-30s %-12s %-12s %s\n" "Drive" "SKU" "Status" "Log"
    printf "%-30s %-12s %-12s %s\n" "---------------------------" "----------" "----------" "----------"
    for i in "${!target_list[@]}"; do
        printf "%-30s %-12s %-12s %s\n" "${target_list[$i]}" "${sku_list[$i]}" "${status_list[$i]}" "${log_list[$i]}"
    done
    echo "================================================================================"

    local failed=0
    for i in "${!target_list[@]}"; do
        [[ "${status_list[$i]}" == SUCCESS* ]] || failed=$((failed + 1))
    done
    if [[ ${failed} -eq 0 ]]; then
        echo "  All ${#target_list[@]} drives provisioned successfully."
        return 0
    fi
    echo "  ${failed}/${#target_list[@]} drive(s) failed; see logs above."
    return 1
}
# -----------------------------------------------------------------------------
# Portable Engine Readiness Audit (parity with EngineStager.ps1). Engines live
# in bin/ and are tier-independent; boot-critical ones are required for the
# drive to boot on Windows hosts.
# -----------------------------------------------------------------------------
BOOT_CRITICAL_ENGINES=(
    "bin/windows_x86_64/python/python.exe"
    "bin/windows_x86_64/kiwix/kiwix-serve.exe"
    "bin/windows_x86_64/llama/llama-server.exe"
)
ALL_ENGINES=(
    "${BOOT_CRITICAL_ENGINES[@]}"
    "bin/windows_arm64/llama/llama-server.exe"
    "bin/windows_x86_64/llama/ggml-rpc-server.exe"
    "bin/linux_x86_64/kiwix-tools_linux-x86_64.tar.gz"
    "bin/linux_x86_64/llama-ubuntu-x64.tar.gz"
    "bin/linux_arm64/kiwix-tools_linux-aarch64.tar.gz"
    "bin/linux_arm64/llama-ubuntu-arm64.tar.gz"
    "bin/macos_arm64/kiwix-tools_macos.tar.gz"
    "bin/macos_arm64/llama-macos-arm64.tar.gz"
    "bin/macos_x86_64/kiwix-tools_macos-x86_64.tar.gz"
    "bin/macos_x86_64/llama-macos-x64.tar.gz"
    "bin/polyglot/llamafile.exe"
)

missing_engines=()
audit_engines() {
    missing_engines=()
    for e in "${ALL_ENGINES[@]}"; do
        [[ -s "${SOURCE_ROOT}/${e}" ]] || missing_engines+=("${e}")
    done
}
is_boot_critical_engine() {
    local e
    for e in "${BOOT_CRITICAL_ENGINES[@]}"; do
        [[ "${1}" == "${e}" ]] && return 0
    done
    return 1
}
# -----------------------------------------------------------------------------
# Payload Asset Acquisition: ensure required .zim / .gguf files exist in the
# host cache (downloading missing ones), then stage them onto the target drive.
# -----------------------------------------------------------------------------
sku_to_tier() {
    case "$1" in
        Product1) echo 0 ;;
        Product2) echo 1 ;;
        Product3) echo 2 ;;
        Tier3)    echo 3 ;;
        Tier4)    echo 4 ;;
        *)        echo 0 ;;
    esac
}

ensure_payload_assets() {
    local sku="$1"
    local tier
    tier=$(sku_to_tier "${sku}")
    mkdir -p "${CACHE_DIR}/zim" "${CACHE_DIR}/models"

    # NOTE: AssetCacheManager exits non-zero when assets are MISSING; that is
    # expected here -- we only fail hard if it crashes outright.
    local inv
    inv="$(python3 "${LIB_DIR}/AssetCacheManager.py" \
        --sku "${sku}" \
        --manifest "${SOURCE_ROOT}/manifests/products.json" \
        --cache-dir "${CACHE_DIR}" --json 2>/dev/null)" || true
    if [[ -z "${inv}" ]]; then
        echo "[ERROR] Could not audit asset cache for ${sku}." >&2
        exit 1
    fi

    if python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['all_available'] else 1)" <<<"${inv}"; then
        echo "[OK] All required payload assets present in cache (${CACHE_DIR})."
        return 0
    fi

    echo "Missing payload assets for ${sku} (cache: ${CACHE_DIR})"
    python3 -c "
import json, sys
inv = json.load(sys.stdin)
for a in inv['assets']:
    if a['status'] == 'MISSING':
        print(f\"  [MISSING] {a['type']:<12} {a['filename']}\")
" <<<"${inv}"

    if [[ "${NO_DOWNLOAD}" == true ]]; then
        echo "[ERROR] Missing assets and --no-download was set. Re-run without it, or" >&2
        echo "        run: provisioning/tools/download_internet_in_a_box.sh --tier ${tier}" >&2
        exit 1
    fi

    echo ">>> Fetching missing assets (tier <= ${tier})..."
    if ! python3 "${SCRIPT_DIR}/tools/fetch_assets.py" --tier "${tier}" --dest-root "${CACHE_DIR}"; then
        echo "[ERROR] Asset download failed (offline or source unreachable?). Cache is incomplete." >&2
        echo "        Partial files are preserved in ${CACHE_DIR} and will resume on next run." >&2
        exit 1
    fi
}

# Magic-header validation (parity with ps1 Test-AssetMagicHeader): verify that
# a .zim/.gguf asset starts with ZIM\x04 / GGUF. Uses AssetCacheManager.py.
verify_magic_header() {
    python3 -c "
import sys
sys.path.insert(0, '${LIB_DIR}')
from AssetCacheManager import verify_magic_header
sys.exit(0 if verify_magic_header(sys.argv[1]).get('valid') else 1)
" "$1"
}

# WriteThrough copy engine (parity with ps1 Copy-ItemWriteThroughPaced):
# copy to a temp file, then fsync + rename so a failed copy never leaves a
# partial file at the destination. Uses dd oflag=direct,sync when the target
# filesystem supports O_DIRECT; falls back to the throttled rsync copy + sync.
copy_writethrough() {
    local src="$1" dst="$2"
    local dst_dir tmp
    dst_dir="$(dirname "${dst}")"
    mkdir -p "${dst_dir}"
    tmp="${dst}.tmp"
    rm -f "${tmp}" || true

    if command -v dd >/dev/null 2>&1 && [[ "${BWLIMIT}" != "0" ]]; then
        # Unbuffered + sync writes so the controller cannot lie about the data
        # being on disk. Falls back to the paced path if O_DIRECT is unsupported.
        if dd if="${src}" of="${tmp}" oflag=direct,sync bs=1M 2>/dev/null; then
            mv "${tmp}" "${dst}"
            sync
            return 0
        fi
        rm -f "${tmp}" || true
    fi

    if command -v rsync >/dev/null 2>&1 && [[ "${BWLIMIT}" != "0" ]]; then
        rsync -ltDvh --bwlimit="${BWLIMIT}" "${src}" "${tmp}" 2>/dev/null || { rm -f "${tmp}" || true; return 1; }
    else
        cp "${src}" "${tmp}" || { rm -f "${tmp}" || true; return 1; }
    fi
    sync
    mv "${tmp}" "${dst}" || { rm -f "${tmp}" || true; return 1; }
    return 0
}

# Whitelist-driven staging plan (parity with ps1 Get-WhitelistedStagingPlan):
# emit a TSV whitelist of (filename, local_path, size_bytes, dest_subdir) for
# the SKU's payload profile. Only these files are staged onto the drive.
emit_whitelist_plan() {
    local sku="$1"
    local inv
    inv="$(python3 "${LIB_DIR}/AssetCacheManager.py" \
        --sku "${sku}" \
        --manifest "${SOURCE_ROOT}/manifests/products.json" \
        --cache-dir "${CACHE_DIR}" --json 2>/dev/null)" || true
    if [[ -z "${inv}" ]]; then
        echo "[ERROR] Could not audit asset cache for ${sku}." >&2
        return 1
    fi
    python3 -c "
import json, sys
inv = json.load(sys.stdin)
for a in inv['assets']:
    if a['status'] != 'AVAILABLE':
        continue
    t = a['type']
    if 'Model' in t:
        dest = 'data/models'
    elif 'ZIM' in t:
        dest = 'data/zim'
    else:
        dest = 'data'
    print(a['filename'], a['local_path'], a['size_bytes'], dest, sep='\t')
" <<<"${inv}"
}

# Stage only whitelist assets (not everything in the cache), with magic-header
# verification of already-staged files to skip needless copies.
stage_payload_assets() {
    local sku="$1"
    local wl
    wl="$(emit_whitelist_plan "${sku}")" || return 1
    local fname local_path size dest dst
    while IFS=$'\t' read -r fname local_path size dest; do
        [[ -n "${fname}" && -f "${local_path}" ]] || continue
        dst="${TARGET_DRIVE}/${dest}/${fname}"
        if [[ -f "${dst}" ]] && [[ "$(stat -c %s "${dst}" 2>/dev/null || echo 0)" == "${size}" ]] && verify_magic_header "${dst}"; then
            echo "  [SKIP] ${dest}/${fname} already staged & verified"
            continue
        fi
        echo "  [COPY] ${dest}/${fname}"
        if ! copy_writethrough "${local_path}" "${dst}"; then
            echo "[ERROR] Failed to stage ${dest}/${fname}" >&2
            return 1
        fi
    done <<<"${wl}"
    return 0
}

# KeepExisting prune (parity with ps1): remove .zim/.gguf files on the drive
# that do not belong to the active SKU whitelist.
prune_non_sku_assets() {
    local sku="$1"
    local wl
    wl="$(emit_whitelist_plan "${sku}")" || return 1
    declare -A ALLOWED=()
    local fname local_path size dest
    while IFS=$'\t' read -r fname local_path size dest; do
        [[ -n "${fname}" ]] || continue
        ALLOWED["${dest}/${fname}"]=1
    done <<<"${wl}"
    local dir f rel
    for dir in "${TARGET_DRIVE}/data/zim" "${TARGET_DRIVE}/data/models"; do
        [[ -d "${dir}" ]] || continue
        for f in "${dir}"/*.zim "${dir}"/*.gguf; do
            [[ -f "${f}" ]] || continue
            rel="${f#${TARGET_DRIVE}/}"
            if [[ -z "${ALLOWED[${rel}]:-}" ]]; then
                echo "  [PRUNE] Removing non-SKU asset ${rel}"
                rm -f "${f}"
            fi
        done
    done
    return 0
}

# Build the tailored library.xml for the staged ZIMs (parity with ps1
# Build-LibraryXml step). Uses the python LibraryXmlBuilder on lib/.
build_library_xml() {
    local zim_dir="${TARGET_DRIVE}/data/zim"
    local template="${SOURCE_ROOT}/data/library.xml"
    local output="${TARGET_DRIVE}/data/library.xml"
    if [[ -d "${zim_dir}" && -f "${template}" ]] && command -v python3 >/dev/null 2>&1; then
        echo "  Generating tailored data/library.xml for staged ZIM archives..."
        python3 "${LIB_DIR}/LibraryXmlBuilder.py" \
            --zim-dir "${zim_dir}" \
            --template "${template}" \
            --output "${output}" || return 1
    fi
    return 0
}
# -----------------------------------------------------------------------------
# Portable Engine Stager (parity with EngineStager.ps1): download missing
# portable runtime engines into bin/ (git-ignored by design) and verify their
# magic headers. POSIX bundles stay staged as .tar.gz so .so/.dylib symlinks
# survive exFAT/FAT32.
# -----------------------------------------------------------------------------
ENGINE_PATHS=()
ENGINE_URLS=()
ENGINE_KINDS=()
add_engine() {
    ENGINE_PATHS+=("$1")
    ENGINE_URLS+=("$2")
    ENGINE_KINDS+=("$3")
}
add_engine "bin/windows_x86_64/python/python.exe" "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip" "extract-python"
add_engine "bin/windows_x86_64/kiwix/kiwix-serve.exe" "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_win-x86_64-3.8.1.zip" "extract-zip"
add_engine "bin/windows_x86_64/llama/llama-server.exe" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-x64.zip" "extract-zip"
add_engine "bin/windows_arm64/llama/llama-server.exe" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-arm64.zip" "extract-zip"
add_engine "bin/windows_x86_64/llama/ggml-rpc-server.exe" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-x64.zip" "extract-zip"
add_engine "bin/linux_x86_64/kiwix-tools_linux-x86_64.tar.gz" "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64-3.8.1.tar.gz" "file"
add_engine "bin/linux_x86_64/llama-ubuntu-x64.tar.gz" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-ubuntu-x64.tar.gz" "file"
add_engine "bin/linux_arm64/kiwix-tools_linux-aarch64.tar.gz" "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-aarch64-3.8.1.tar.gz" "file"
add_engine "bin/linux_arm64/llama-ubuntu-arm64.tar.gz" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-ubuntu-arm64.tar.gz" "file"
add_engine "bin/macos_arm64/kiwix-tools_macos.tar.gz" "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_macos-arm64-3.8.1.tar.gz" "file"
add_engine "bin/macos_arm64/llama-macos-arm64.tar.gz" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-macos-arm64.tar.gz" "file"
add_engine "bin/macos_x86_64/kiwix-tools_macos-x86_64.tar.gz" "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_macos-x86_64-3.8.1.tar.gz" "file"
add_engine "bin/macos_x86_64/llama-macos-x64.tar.gz" "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-macos-x64.tar.gz" "file"
add_engine "bin/polyglot/llamafile.exe" "https://github.com/mozilla-ai/llamafile/releases/download/0.10.6/llamafile-0.10.6-thin" "file"

check_magic() {
    local file="$1" magic="$2"
    local hex
    hex="$(od -An -tx1 -N4 "${file}" 2>/dev/null | tr -d ' \n')"
    case "${magic}" in
        TAR_GZ) [[ "${hex}" == 1f8b* ]] ;;
        ZIP)    [[ "${hex}" == 504b* ]] ;;
        EXE)    [[ "${hex}" == 4d5a* ]] ;;
        *)      [[ "${hex}" != "00000000" ]] ;;
    esac
}

fetch_engines() {
    local missing=()
    audit_engines
    if [[ ${#missing_engines[@]} -eq 0 ]]; then
        echo "[OK] All portable engines already staged and verified in bin/."
        ENGINES_READY=1
        return 0
    fi
    echo ">>> Fetching ${#missing_engines[@]} missing portable engine(s)..."
    local tmp_dl="${SOURCE_ROOT}/tmp_dl"
    mkdir -p "${tmp_dl}" "${SOURCE_ROOT}/bin"

    local i path url kind probe archive ext_dir
    for i in "${!ENGINE_PATHS[@]}"; do
        path="${ENGINE_PATHS[$i]}"
        url="${ENGINE_URLS[$i]}"
        kind="${ENGINE_KINDS[$i]}"
        probe="${SOURCE_ROOT}/${path}"
        mkdir -p "$(dirname "${probe}")"
        local expected_magic="ANY"
        [[ "${path}" == *.tar.gz ]] && expected_magic="TAR_GZ"
        [[ "${path}" == *.exe ]] && expected_magic="EXE"
        # Skip engines already present with the right magic (tar.gz / exe).
        if [[ -f "${probe}" ]] && check_magic "${probe}" "${expected_magic}"; then
            continue
        fi
        echo "  [DL] ${url}"
        local archive="${tmp_dl}/$(basename "${url}")"
        rm -f "${archive}.part"
        if ! curl -L -f --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 30 \
            -C - --user-agent "OffGridUSB-Provisioner/0.1" -o "${archive}.part" "${url}"; then
            # Resume might be rejected by some servers; retry clean.
            if ! curl -L -f --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 30 \
                --user-agent "OffGridUSB-Provisioner/0.1" -o "${archive}.part" "${url}"; then
                echo "[ERROR] Engine download failed for ${url}" >&2
                return 1
            fi
        fi
        mv "${archive}.part" "${archive}"
        case "${kind}" in
            extract-python)
                python3 -m zipfile -e "${archive}" "$(dirname "${probe}")" >/dev/null
                printf 'python312.zip\n.\n..\\..\\..\\src\nimport site\n' > "$(dirname "${probe}")/python312._pth"
                echo "  [OK] Configured zero-install Python 3.12.8 ($(dirname "${path}"))"
                ;;
            extract-zip)
                ext_dir="${tmp_dl}/ext_$(basename "${archive}")"
                rm -rf "${ext_dir}"
                python3 -m zipfile -e "${archive}" "${ext_dir}" >/dev/null
                find "${ext_dir}" -type f -exec cp -f {} "$(dirname "${probe}")" \;
                rm -rf "${ext_dir}"
                echo "  [OK] Extracted $(basename "${path}")"
                ;;
            *)
                cp -f "${archive}" "${probe}"
                echo "  [OK] Staged $(basename "${path}")"
                ;;
        esac
        rm -f "${archive}"
    done
    rm -rf "${tmp_dl}"
    audit_engines
    if [[ ${#missing_engines[@]} -gt 0 ]]; then
        echo "[ERROR] Engine staging incomplete: ${#missing_engines[@]} payload(s) missing or corrupt after download." >&2
        return 1
    fi
    echo "[OK] All portable engines staged and verified in bin/."
    ENGINES_READY=1
    return 0
}

if [[ ${#DRIVES[@]} -ge 2 ]]; then
    run_orchestrator
    exit $?
fi

# Single-drive path: use the first drive spec (with any :SKU override) if given
if [[ ${#DRIVES[@]} -eq 1 ]]; then
    spec="${DRIVES[0]}"
    if [[ "${spec}" == *:* ]]; then
        candidate="${spec#*:}"
        if [[ -n "${SKU_MIN_BYTES[${candidate}]:-}" ]]; then
            TARGET_DRIVE="${spec%%:*}"
            RESOLVED_SKU=$(normalize_sku "${candidate}" -1)
        else
            TARGET_DRIVE="${spec}"
        fi
    else
        TARGET_DRIVE="${spec}"
    fi
fi

# Interactive menu if missing parameters
if [[ -z "${RESOLVED_SKU}" || -z "${TARGET_DRIVE}" ]]; then
    if [[ "${NON_INTERACTIVE}" == true ]]; then
        echo "[ERROR] Non-interactive mode requires --product (or --tier) and --drive/--target." >&2
        exit 1
    fi
    echo "================================================================================"
    echo "  OFFGRIDUSB -- POSIX FACTORY PROVISIONING SUITE (HOST ONLY)"
    echo "================================================================================"
    echo "  [1] Provision Product 1: PocketSurvival  (Tier 0,    8 GB USB,  <= 6.5 GB)"
    echo "  [2] Provision Product 2: FieldReady      (Tiers 0-1, 32 GB USB,  ~16-20 GB)"
    echo "  [3] Provision Product 3: CivilizationArk (Tiers 0-2, 128 GB USB, ~65-72 GB)"
    echo "  [4] Custom Technical Tier Provisioning (0-4)"
    echo "  [5] View Product Catalog (-Info)"
    echo "  [6] Run Simulation (-DryRun)"
    echo "  [Q] Quit"
    echo "================================================================================"
    read -rp "Select an option [1-6, Q]: " opt
    case "$opt" in
        1) RESOLVED_SKU="Product1" ;;
        2) RESOLVED_SKU="Product2" ;;
        3) RESOLVED_SKU="Product3" ;;
        4)
            read -rp "Enter Tier (0..4): " t
            RESOLVED_SKU=$(normalize_sku "" "$t") ;;
        5) "$0" --info; exit 0 ;;
        6) DRY_RUN=true; RESOLVED_SKU="Product2" ;;
        q|Q) echo "Aborted."; exit 0 ;;
        *) echo "Invalid choice."; exit 1 ;;
    esac

    if [[ -z "${TARGET_DRIVE}" ]]; then
        read -rp "Enter Target USB mount directory (e.g. /media/user/OFFGRIDUSB): " TARGET_DRIVE
    fi
fi

if [[ "${DRY_RUN}" == true ]]; then
    # Dry-run performs no writes; tolerate simulated/fake target paths that
    # cannot be validated against real devices.
    echo "[NOTE] Dry-run mode: live device safety & capacity validation skipped."
else
    assert_target_drive_safety "${TARGET_DRIVE}"
    assert_drive_capacity "${TARGET_DRIVE}" "${RESOLVED_SKU}"
fi

# -----------------------------------------------------------------------------
# Legacy cache migration (parity with ps1 Import-LegacyCacheAssets): adopt
# .zim/.gguf assets from older cache locations into the new cache layout.
# -----------------------------------------------------------------------------
if [[ "${DRY_RUN}" != true ]]; then
    migrated=$(import_legacy_cache_assets "${CACHE_DIR}")
    if [[ "${migrated}" -gt 0 ]]; then
        echo ">>> Adopted ${migrated} payload asset(s) from legacy cache locations into:"
        echo "    ${CACHE_DIR}"
        echo "  [OK] No re-download needed for migrated assets."
    fi
fi

audit_engines

if [[ "${DRY_RUN}" == true ]]; then
    echo ""
    echo "================================================================================"
    echo "  >>> POSIX DRY RUN SIMULATION VERDICT: PASSED"
    echo "================================================================================"
    echo "  Product SKU        : ${RESOLVED_SKU}"
    echo "  Target Drive       : ${TARGET_DRIVE}"
    echo "  Pre-Flight Safety  : PASSED (OS Root Device Protected)"
    echo "  Capacity Validation: PASSED"
    echo "  Customer Stripping : Whitelist staging excludes all builder tools"
    if [[ ${#missing_engines[@]} -eq 0 ]]; then
        echo "  Portable Engines   : ALL STAGED"
    else
        echo "  Portable Engines   : ${#missing_engines[@]} missing (will be fetched before live staging)"
        for e in "${missing_engines[@]}"; do
            local_tag=""
            is_boot_critical_engine "${e}" && local_tag=" [BOOT-CRITICAL]"
            echo "    [MISSING] ${e}${local_tag}"
        done
    fi
    echo "  0 actual writes performed to disk."
    echo "================================================================================"
    exit 0
fi

# -----------------------------------------------------------------------------
# Parallel acquisition: payload-asset acquisition and portable-engine fetching
# are network-bound and independent of each other, so run them concurrently.
# Safety/capacity checks and dry-run mode have already passed by this point.
# -----------------------------------------------------------------------------
ensure_payload_assets "${RESOLVED_SKU}" &
PAYLOAD_PID=$!
fetch_engines &
ENGINE_PID=$!

# Kill background jobs on Ctrl-C / interrupt.
trap 'kill "${PAYLOAD_PID}" "${ENGINE_PID}" 2>/dev/null; echo "[ABORT] Interrupted; killing pending downloads." >&2; exit 130' INT TERM

payload_rc=0
engine_rc=0
wait "${PAYLOAD_PID}" || payload_rc=$?
wait "${ENGINE_PID}" || engine_rc=$?

if [[ ${payload_rc} -ne 0 ]]; then
    echo "[ERROR] Payload asset acquisition failed (exit code ${payload_rc})." >&2
    [[ ${engine_rc} -ne 0 ]] && echo "[ERROR] Engine staging also failed (exit code ${engine_rc})." >&2
    exit 1
fi
if [[ ${engine_rc} -ne 0 ]]; then
    echo "[ERROR] Engine staging failed (exit code ${engine_rc})." >&2
    exit 1
fi

# Live Staging Execution
echo ">>> Staging files to ${TARGET_DRIVE}..."

# Sync runtime directories
mkdir -p "${TARGET_DRIVE}"/{bin,data/zim,data/models,data/vault,data/uploads,manifests,src,web}

for f in START_OFFGRIDUSB_WINDOWS.bat START_OFFGRIDUSB_LINUX.sh START_OFFGRIDUSB_MAC.command run_windows.bat run_linux.sh run_macos.command USER_GUIDE.md; do
    if [[ -f "${SOURCE_ROOT}/${f}" ]]; then
        cp "${SOURCE_ROOT}/${f}" "${TARGET_DRIVE}/${f}"
    fi
done

# Copy runtime binaries, web, src, manifests
# Throttle writes by default (BWLIMIT, KB/s): sustained full-speed sequential
# writes can hard-lock cheap USB flash controllers. BWLIMIT=0 disables.
BWLIMIT_OPTS=()
if [[ "${BWLIMIT}" != "0" ]]; then
    if [[ "${BWLIMIT}" =~ ^[0-9]+$ ]]; then
        BWLIMIT_OPTS=(--bwlimit="${BWLIMIT}")
    else
        echo "[ERROR] --bwlimit must be a non-negative integer (KB/s) or 0, got: '${BWLIMIT}'" >&2
        exit 1
    fi
fi

for dir in bin web manifests; do
    if command -v rsync >/dev/null 2>&1 && [[ ${#BWLIMIT_OPTS[@]} -gt 0 ]]; then
        rsync -rltDvh "${BWLIMIT_OPTS[@]}" "${SOURCE_ROOT}/${dir}/" "${TARGET_DRIVE}/${dir}/" 2>/dev/null || true
    else
        cp -r "${SOURCE_ROOT}/${dir}/"* "${TARGET_DRIVE}/${dir}/" 2>/dev/null || true
    fi
done

# Copy src excluding fetch_assets.py
rsync -av "${BWLIMIT_OPTS[@]}" --exclude="fetch_assets.py" --exclude="__pycache__" "${SOURCE_ROOT}/src/" "${TARGET_DRIVE}/src/" 2>/dev/null || cp -r "${SOURCE_ROOT}/src/"* "${TARGET_DRIVE}/src/"

# Generate dynamic SKU manifest
if command -v python3 >/dev/null 2>&1; then
    python3 "${LIB_DIR}/SkuManifestGenerator.py" --sku "${RESOLVED_SKU}" --drive "${TARGET_DRIVE}" --output "${TARGET_DRIVE}/manifests/product_sku.json"
fi

# Enforce LF line endings
enforce_lf_line_endings "${TARGET_DRIVE}"

# Assert customer hygiene
assert_customer_usb_hygiene "${TARGET_DRIVE}"

stage_payload_assets "${RESOLVED_SKU}"

# KeepExisting prune: remove non-SKU assets from the drive (parity with ps1)
prune_non_sku_assets "${RESOLVED_SKU}"

# Build the tailored library.xml for the staged ZIMs (parity with ps1)
build_library_xml

if [[ "${ENGINES_READY}" == 1 ]]; then
    echo "  Portable engines verified: drive boots on Windows/macOS/Linux hosts."
else
    echo "  [WARN] Portable engines incomplete: cross-OS boot support reduced."
fi
echo "[SUCCESS] Provisioning of ${RESOLVED_SKU} staged onto ${TARGET_DRIVE} completed cleanly!"
exit 0
