#!/usr/bin/env bash
# SafetyValidator.sh - POSIX Drive Safety, Capacity, and Root Protection Validator
# Used by OffGridUSB provisioning engine on Linux and macOS.

set -euo pipefail

# Required Minimum Volume Capacities (bytes)
declare -A SKU_MIN_BYTES=(
    ["Product1"]=7000000000
    ["PocketSurvival"]=7000000000
    ["Tier0"]=7000000000
    ["Product2"]=28000000000
    ["FieldReady"]=28000000000
    ["Tier1"]=28000000000
    ["Product3"]=110000000000
    ["CivilizationArk"]=110000000000
    ["Tier2"]=110000000000
    ["Tier3"]=220000000000
    ["SwarmCluster"]=220000000000
    ["Tier4"]=450000000000
    ["SettlementHub"]=450000000000
)

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
        if [[ "${sku}" == "Product3" || "${sku}" == "CivilizationArk" || "${sku}" == "Tier2" ]]; then
            echo "Note: Commercial 64 GB USB drives only offer ~57.6 GiB and cannot fit Product 3. A 128 GB USB or SSD is required." >&2
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
        exit 1
    fi
    assert_target_drive_safety "$1"
    if [[ "$#" -ge 2 ]]; then
        assert_drive_capacity "$1" "$2"
    fi
fi
