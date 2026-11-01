#!/usr/bin/env bash
# Dedicated 1-command POSIX wrapper for Product 1 (PocketSurvival, Tier 0)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/provision_usb.sh" ]]; then
    ENGINE="${SCRIPT_DIR}/provision_usb.sh"
else
    ENGINE="${SCRIPT_DIR}/../provision_usb.sh"
fi
exec "${ENGINE}" --product Product1 "$@"
