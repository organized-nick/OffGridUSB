#!/usr/bin/env bash
# UsbStripper.sh - POSIX customer USB hygiene auditor & LF line ending enforcer.
# Part of the OffGridUSB factory provisioning suite.

set -euo pipefail

FORBIDDEN_DIRS=(
    "provisioning"
    "scripts"
    "docs"
    "tests"
    "tmp_dl"
    ".git"
    ".github"
    ".agents"
    ".venv"
    ".pytest_cache"
    "__pycache__"
)

FORBIDDEN_ROOT_FILES=(
    "CONTRIBUTING.md"
    "TEST_READY.md"
    "PITCH_CHEATSHEET.md"
    "README.md"
    "DOWNLOAD_INTERNET_IN_A_BOX.bat"
    "FORMAT_AND_SETUP_USB.bat"
    "MAKE_USB_DRIVES.bat"
    "START_EMYRGE_WINDOWS.bat"
    "START_EMYRGE_LINUX.sh"
    "START_EMYRGE_MAC.command"
    "audit_offgrid_usb.py"
    "fetch_assets.py"
)

MANDATORY_CUSTOMER_FILES=(
    "START_OFFGRIDUSB_WINDOWS.bat"
    "START_OFFGRIDUSB_LINUX.sh"
    "START_OFFGRIDUSB_MAC.command"
    "USER_GUIDE.md"
    "manifests/product_sku.json"
)

assert_customer_usb_hygiene() {
    local target_root="$1"
    local violations=()

    if [[ ! -d "${target_root}" ]]; then
        echo "[ERROR] Target directory '${target_root}' does not exist!" >&2
        return 1
    fi

    # 1. Forbidden directories
    for d in "${FORBIDDEN_DIRS[@]}"; do
        if [[ -d "${target_root}/${d}" ]]; then
            violations+=("Forbidden directory found: ${d}")
        fi
    done

    # 2. Forbidden root files
    for f in "${FORBIDDEN_ROOT_FILES[@]}"; do
        if [[ -f "${target_root}/${f}" ]]; then
            violations+=("Forbidden root file found: ${f}")
        fi
    done

    # 3. Forbidden patterns in filenames
    while IFS= read -r -d '' file; do
        local basename
        basename=$(basename "${file}")
        case "${basename}" in
            *download*|*format*|*make_usb*|*clone*|*provision*|fetch_assets*|*.pyc|*.pyo)
                violations+=("Forbidden pattern match: ${file}")
                ;;
        esac
    done < <(find "${target_root}" -type f -print0 2>/dev/null)

    # 4. Mandatory customer files
    for req in "${MANDATORY_CUSTOMER_FILES[@]}"; do
        if [[ ! -f "${target_root}/${req}" ]]; then
            violations+=("Missing mandatory file: ${req}")
        fi
    done

    # 5. LF line endings on shell scripts
    while IFS= read -r -d '' sh_file; do
        if grep -q $'\r' "${sh_file}" 2>/dev/null; then
            violations+=("CRLF line endings detected in: ${sh_file}")
        fi
    done < <(find "${target_root}" -type f \( -name "*.sh" -o -name "*.command" \) -print0 2>/dev/null)

    if [[ "${#violations[@]}" -gt 0 ]]; then
        echo "[FAILED] Customer USB hygiene audit failed with ${#violations[@]} violation(s):" >&2
        for v in "${violations[@]}"; do
            echo "  - ${v}" >&2
        done
        return 1
    fi

    echo "[PASS] Customer USB hygiene verified 100% clean."
    return 0
}

enforce_lf_line_endings() {
    local target_root="$1"
    echo "Enforcing strict LF line endings on shell scripts in '${target_root}'..."
    while IFS= read -r -d '' file; do
        if [[ -f "${file}" ]]; then
            # Remove carriage return characters
            sed -i.bak 's/\r$//' "${file}" 2>/dev/null || tr -d '\r' < "${file}" > "${file}.tmp" && mv "${file}.tmp" "${file}"
            rm -f "${file}.bak" 2>/dev/null || true
        fi
    done < <(find "${target_root}" -type f \( -name "*.sh" -o -name "*.command" \) -print0 2>/dev/null)
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ "$#" -lt 1 ]]; then
        echo "Usage: $0 <target_mount_point>"
        exit 1
    fi
    enforce_lf_line_endings "$1"
    assert_customer_usb_hygiene "$1"
fi
