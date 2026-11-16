#!/usr/bin/env bash
# SafetyValidator.sh - POSIX Drive Safety, Capacity, and Root Protection Validator
# Used by OffGridUSB provisioning engine on Linux and macOS.

set -euo pipefail

# Required Minimum Volume Capacities (bytes)
# Mirrors lib/SafetyValidator.ps1 SKU ladder. Keep in sync when adding SKUs.
declare -A SKU_MIN_BYTES=(
    ["Product1"]=28000000000        # 32 GB USB (~28.99 GB full payload)
    ["PocketSurvival"]=28000000000
    ["Tier0"]=28000000000
    ["Product2"]=60000000000        # 64 GB USB (~58.58 GB full payload)
    ["FieldReady"]=60000000000
    ["Tier1"]=60000000000
    ["Product2-256"]=220000000000   # 256 GB USB/SSD (~160 GB full payload)
    ["Product3"]=60000000000        # 64 GB USB (~58.8 GB Wikipedia-first payload)
    ["CivilizationArk"]=60000000000
    ["Tier2"]=60000000000
    ["Product3-256"]=220000000000   # 256 GB USB/SSD (~175 GB full payload)
    ["Tier3"]=220000000000          # 256 GB SSD (~195 GB Swarm payload)
    ["SwarmCluster"]=220000000000
    ["Tier4"]=450000000000          # 512 GB NVMe (~357 GB SettlementHub payload)
    ["SettlementHub"]=450000000000
)

declare -A SKU_TARGET_LABEL=(
    ["Product1"]="32 GB USB Flash Drive"
    ["PocketSurvival"]="32 GB USB Flash Drive"
    ["Tier0"]="32 GB USB Flash Drive"
    ["Product2"]="64 GB USB Flash Drive"
    ["FieldReady"]="64 GB USB Flash Drive"
    ["Tier1"]="64 GB USB Flash Drive"
    ["Product2-256"]="256 GB USB Flash Drive or SSD"
    ["Product3"]="64 GB USB Flash Drive"
    ["CivilizationArk"]="64 GB USB Flash Drive"
    ["Tier2"]="64 GB USB Flash Drive"
    ["Product3-256"]="256 GB USB Flash Drive or SSD"
    ["Tier3"]="256 GB Portable SSD"
    ["SwarmCluster"]="256 GB Portable SSD"
    ["Tier4"]="512 GB Portable NVMe"
    ["SettlementHub"]="512 GB Portable NVMe"
)

# Print the SKU ladder: "SKU<TAB>min_bytes<TAB>label"
print_sku_ladder() {
    local sku
    for sku in "Product1" "PocketSurvival" "Tier0" "Product2" "FieldReady" "Tier1" "Product2-256" "Product3" "CivilizationArk" "Tier2" "Product3-256" "Tier3" "SwarmCluster" "Tier4" "SettlementHub"; do
        printf '%s\t%s\t%s\n' "$sku" "${SKU_MIN_BYTES[$sku]}" "${SKU_TARGET_LABEL[$sku]}"
    done
}

# Print required minimum bytes for a SKU (0 if unknown).
get_sku_min_bytes() {
    echo "${SKU_MIN_BYTES[$1]:-0}"
}

assert_target_drive_safety() {
    local target="$1"
    
    if [[ -z "${target}" ]]; then
        echo "[FATAL SAFETY VIOLATION] Target mount point or device cannot be empty!" >&2
        return 1
    fi

    # Gate 1: Refuse root or home directory targets
    if [[ "${target}" == "/" || "${target}" == "/root" || "${target}" == "$HOME" || "${target}" == "/System"* ]]; then
        echo "[FATAL SAFETY VIOLATION] Target '${target}' is an OS system path! Operations strictly prohibited." >&2
        return 1
    fi

    # Gate 2: OS Block Device Inspection
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS Safety Verification
        local dev_node
        dev_node=$(df "${target}" | tail -n 1 | awk '{print $1}')
        if [[ "${dev_node}" == *"/dev/disk0"* || "${dev_node}" == *"/dev/disk1"* ]]; then
            echo "[FATAL SAFETY VIOLATION] Mount '${target}' resides on internal Apple boot disk (${dev_node})!" >&2
            return 1
        fi
        
        # Check diskutil info
        if command -v diskutil >/dev/null 2>&1; then
            local is_removable
            is_removable=$(diskutil info "${dev_node}" 2>/dev/null | grep -i "Removable Media" | awk '{print $NF}' || echo "No")
            local is_internal
            is_internal=$(diskutil info "${dev_node}" 2>/dev/null | grep -i "Internal" | awk '{print $NF}' || echo "Yes")
            if [[ "${is_internal}" == "Yes" && "${is_removable}" != "Removable" ]]; then
                echo "[WARNING] Target device ${dev_node} is reported as internal storage." >&2
            fi
        fi
    else
        # Linux Safety Verification
        local root_src
        root_src=$(findmnt -n -o SOURCE / 2>/dev/null || echo "")
        local target_src
        target_src=$(findmnt -n -o SOURCE "${target}" 2>/dev/null || echo "${target}")
        
        if [[ -n "${root_src}" && "${target_src}" == "${root_src}"* ]]; then
            echo "[FATAL SAFETY VIOLATION] Target '${target}' (${target_src}) is the active Linux root filesystem!" >&2
            return 1
        fi
        
        if command -v lsblk >/dev/null 2>&1; then
            local tran
            tran=$(lsblk -no TRAN "${target_src}" 2>/dev/null || echo "unknown")
            if [[ "${tran}" != "usb" ]]; then
                echo "[WARNING] Target device ${target_src} has transport '${tran}' (Expected 'usb')." >&2
            fi
        fi
    fi

    echo "[PASS] Drive target '${target}' passed pre-flight safety assertions."
    return 0
}

# Auto-detect the single candidate USB drive mount point.
# Prints the mount point if exactly one candidate exists; prints nothing otherwise.
# Exit code 0 if exactly one candidate, 1 if none or multiple.
detect_single_candidate_drive() {
    local candidates=()
    if command -v lsblk >/dev/null 2>&1; then
        # List USB-transport devices, then their mount points.
        while IFS= read -r mnt; do
            [[ -n "${mnt}" ]] && candidates+=("${mnt}")
        done < <(lsblk -no TRAN,RM,MOUNTPOINT 2>/dev/null | awk '$1=="usb" && $2=="1" && $3!="" {print $3}')
    fi
    if [[ ${#candidates[@]} -eq 1 ]]; then
        echo "${candidates[0]}"
        return 0
    elif [[ ${#candidates[@]} -eq 0 ]]; then
        echo "[ERROR] No candidate USB drive detected (no removable usb-transport device with a mount point)." >&2
        return 1
    else
        echo "[ERROR] ${#candidates[@]} candidate USB drives detected: ${candidates[*]}" >&2
        echo "[ERROR] Specify --target explicitly to disambiguate." >&2
        return 1
    fi
}

assert_drive_capacity() {
    local target="$1"
    local sku="$2"
    
    local req_bytes="${SKU_MIN_BYTES[${sku}]:-0}"
    if [[ "${req_bytes}" -eq 0 ]]; then
        echo "[ERROR] Unknown SKU '${sku}' for capacity validation." >&2
        return 1
    fi

    local avail_kb
    avail_kb=$(df -k "${target}" | tail -n 1 | awk '{print $2}')
    local avail_bytes=$(( avail_kb * 1024 ))

    if [[ "${avail_bytes}" -lt "${req_bytes}" ]]; then
        local actual_gb=$(( avail_bytes / 1000000000 ))
        local req_gb=$(( req_bytes / 1000000000 ))
        echo "[ERROR] Target '${target}' capacity (${actual_gb} GB) is below minimum required (${req_gb} GB) for ${sku}!" >&2
        if [[ "${sku}" == "Product2" || "${sku}" == "FieldReady" || "${sku}" == "Tier1" || "${sku}" == "Product3" || "${sku}" == "CivilizationArk" || "${sku}" == "Tier2" ]]; then
            echo "Note: Commercial 32 GB USB drives only offer ~28.8 GiB and cannot fit Product 2/3 payloads. A 64 GB USB drive (or larger) is required." >&2
        elif [[ "${sku}" == "Product2-256" || "${sku}" == "Product3-256" || "${sku}" == "Tier3" || "${sku}" == "SwarmCluster" ]]; then
            echo "Note: 256 GB media (or larger) is required for this SKU." >&2
        elif [[ "${sku}" == "Tier4" || "${sku}" == "SettlementHub" ]]; then
            echo "Note: 512 GB NVMe is required for this SKU." >&2
        fi
        return 1
    fi

    echo "[PASS] Target '${target}' capacity satisfies minimum requirements for ${sku}."
    return 0
}

# If executed directly, run basic CLI
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ "$#" -lt 1 ]]; then
        echo "Usage: $0 <target_mount_point> [sku]"
        echo "       $0 --detect"
        echo "       $0 --ladder"
        exit 1
    fi
    if [[ "$1" == "--detect" ]]; then
        detect_single_candidate_drive
        exit $?
    fi
    if [[ "$1" == "--ladder" ]]; then
        print_sku_ladder
        exit 0
    fi
    assert_target_drive_safety "$1"
    if [[ "$#" -ge 2 ]]; then
        assert_drive_capacity "$1" "$2"
    fi
fi
