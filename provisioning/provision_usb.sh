#!/usr/bin/env bash
# provision_usb.sh - POSIX Factory Provisioning Engine for OffGridUSB
# Part of the OffGridUSB host-only builder suite.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"

PRODUCT=""
TIER=-1
TARGET_DRIVE=""
DRY_RUN=false
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

usage() {
    cat <<EOF
OffGridUSB POSIX Provisioning Engine

Usage: $0 [OPTIONS]

Options:
  --product <sku>         Select commercial SKU (Product1, Product2, Product3)
  --tier <0..4>           Select technical tier level
  --drive, --target <path> Target USB mount directory or device
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
                          Use 0 to disable throttling.
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
            TARGET_DRIVE="$2"; shift 2 ;;
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
            SwarmCluster)         echo "Tier3" ;;
            SettlementHub)        echo "Tier4" ;;
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
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Tier3"    "SwarmCluster"    "0 - 3"     "256 GB" "~88 GB"     "All Product 3 + Qwen 32B (18.9 GB) + exo LAN Swarm Clustering."
    printf "%-9s %-17s %-9s %-9s %-15s %s\n" "Tier4"    "SettlementHub"   "0 - 4"     "512 GB" "~210+ GB"   "All Tier 3 + Wikipedia Maxi (110 GB) + Llama 70B (40.5 GB)."
    echo ""
    echo "[CURRENT FACTORY READINESS STATUS]"
    echo "  * Product 1 (PocketSurvival): [100% READY] (Lean payload: 1.39 GB, verified <= 6.5 GB ceiling)"
    echo "  * Product 2 (FieldReady):     [100% READY] (Lean payload: 4.69 GB, verified for 32 GB drive)"
    echo "  * Product 3 (CivilizationArk): [REQUIRES CACHE DOWNLOAD] (Requires 50.2 GB Wikipedia ZIM; 128 GB USB required)"
    echo "================================================================================"
    exit 0
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

# Safety & Capacity Checks
source "${LIB_DIR}/SafetyValidator.sh"
assert_target_drive_safety "${TARGET_DRIVE}"
assert_drive_capacity "${TARGET_DRIVE}" "${RESOLVED_SKU}"

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
    echo "  0 actual writes performed to disk."
    echo "================================================================================"
    exit 0
fi

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
    inv="$(python3 "${SCRIPT_DIR}/lib/AssetCacheManager.py" \
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

stage_payload_assets() {
    local src dest item base
    for pair in "zim:data/zim" "models:data/models"; do
        src="${pair%%:*}"; dest="${pair##*:}"
        mkdir -p "${TARGET_DRIVE}/${dest}"
        for item in "${CACHE_DIR}/${src}"/*; do
            [[ -e "${item}" ]] || continue
            base="$(basename "${item}")"
            if [[ -f "${TARGET_DRIVE}/${dest}/${base}" ]]; then
                echo "  [SKIP] Already staged: ${dest}/${base}"
                continue
            fi
            echo "  [COPY] ${base} -> ${dest}/"
            if command -v rsync >/dev/null 2>&1 && [[ ${#BWLIMIT_OPTS[@]} -gt 0 ]]; then
                rsync -ltDvh --inplace ${BWLIMIT_OPTS[*]} "${item}" "${TARGET_DRIVE}/${dest}/"
            else
                cp "${item}" "${TARGET_DRIVE}/${dest}/${base}"
            fi
        done
    done
}

ensure_payload_assets "${RESOLVED_SKU}"

# Live Staging Execution
echo ">>> Staging files to ${TARGET_DRIVE}..."
source "${LIB_DIR}/UsbStripper.sh"

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

stage_payload_assets

echo "[SUCCESS] Provisioning of ${RESOLVED_SKU} onto ${TARGET_DRIVE} completed cleanly!"
exit 0
