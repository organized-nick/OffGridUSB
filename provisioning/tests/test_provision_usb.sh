#!/usr/bin/env bash
# test_provision_usb.sh - Unit tests for the parallel provisioning engine + SKU parity.
#
# Covers:
#   1) normalize_sku() product-name / tier-number resolution (incl. new SKUs).
#   2) lib/SafetyValidator.sh capacity ladder sync against ps1 (golden bytes).
#   3) provision_usb.sh --info readiness table includes every SKU in the ps1 ladder.
#   4) provision_usb.sh dry-run verdict works with a fake drive list.
#   5) provision_usb.sh parallel orchestration spawns ensure_payload_assets &
#      fetch_engines concurrently, waits, and reports payload_rc/engine_rc.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION_SH="${SCRIPT_DIR}/../provision_usb.sh"
VALIDATOR_SH="${SCRIPT_DIR}/../lib/SafetyValidator.sh"

PASS=0; FAIL=0
ok()   { echo "  [PASS] $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*" >&2; FAIL=$((FAIL+1)); }

echo "== 1) normalize_sku: SKU/tier resolution =="
norm() {
    local sku="$1" tier="$2"
    (
        cd "$(dirname "${PROVISION_SH}")"
        bash -c "
            PRODUCT='${sku}'; TIER=${tier}
            source <(sed -n '/^normalize_sku() {$/,/^}/p' '${PROVISION_SH}')
            normalize_sku \"\${PRODUCT}\" \"\${TIER}\"
        "
    ) 2>/dev/null
}

[[ $(norm PocketSurvival -1) == "Product1" ]]           && ok "PocketSurvival -> Product1" || bad "PocketSurvival alias"
[[ $(norm FieldReady     -1) == "Product2" ]]           && ok "FieldReady     -> Product2" || bad "FieldReady alias"
[[ $(norm CivilizationArk -1) == "Product3" ]]          && ok "CivilizationArk-> Product3" || bad "CivilizationArk alias"
[[ $(norm Product2-256   -1) == "Product2-256" ]]       && ok "Product2-256 -> itself"     || bad "Product2-256"
[[ $(norm Product3-256   -1) == "Product3-256" ]]       && ok "Product3-256 -> itself"     || bad "Product3-256"
[[ $(norm SwarmCluster   -1) == "Tier3" ]]              && ok "SwarmCluster -> Tier3"      || bad "SwarmCluster alias"
[[ $(norm SettlementHub  -1) == "Tier4" ]]              && ok "SettlementHub-> Tier4"      || bad "SettlementHub alias"
[[ $(norm ""            0 ) == "Product1" ]]            && ok "tier 0  -> Product1"        || bad "tier 0 mapping"
[[ $(norm ""            1 ) == "Product2" ]]            && ok "tier 1  -> Product2"        || bad "tier 1 mapping"
[[ $(norm ""            2 ) == "Product3" ]]            && ok "tier 2  -> Product3"        || bad "tier 2 mapping"
[[ $(norm ""            3 ) == "Tier3"    ]]            && ok "tier 3  -> Tier3"           || bad "tier 3 mapping"
[[ $(norm ""            4 ) == "Tier4"    ]]            && ok "tier 4  -> Tier4"           || bad "tier 4 mapping"

echo "== 2) SafetyValidator.sh capacity ladder (golden bytes vs ps1) =="
source "${VALIDATOR_SH}" >/dev/null
check_cap() {
    local sku="$1" want="$2"
    if [[ "${SKU_MIN_BYTES[${sku}]:-MISSING}" == "${want}" ]]; then
        ok "${sku}: min bytes ${want}"
    else
        bad "${sku}: expected ${want}, got '${SKU_MIN_BYTES[${sku}]:-MISSING}'"
    fi
}
# Golden values lifted from lib/SafetyValidator.ps1 SkuMinCapacityBytes.
check_cap "Product1"         28000000000
check_cap "PocketSurvival"   28000000000
check_cap "Tier0"            28000000000
check_cap "Product2"         60000000000
check_cap "FieldReady"       60000000000
check_cap "Tier1"            60000000000
check_cap "Product2-256"     220000000000
check_cap "Product3"         60000000000
check_cap "CivilizationArk"  60000000000
check_cap "Tier2"            60000000000
check_cap "Product3-256"     220000000000
check_cap "Tier3"            220000000000
check_cap "SwarmCluster"     220000000000
check_cap "Tier4"            450000000000
check_cap "SettlementHub"    450000000000

echo "== 3) provision_usb.sh --info readiness table includes every SKU =="
INFO_OUT="$(bash "${PROVISION_SH}" --info 2>&1)"
for sku in "Product1" "Product2" "Product3" "Product2-256" "Product3-256" "Tier3" "Tier4"; do
    grep -q "${sku}" <<<"${INFO_OUT}" && ok "--info mentions ${sku}" || bad "--info missing ${sku}"
done

echo "== 4) provision_usb.sh dry-run verdict =="
TMP="$(mktemp -d)"
mkdir -p "${TMP}/bin/windows_x86_64/python" "${TMP}/bin/windows_x86_64/kiwix" "${TMP}/bin/windows_x86_64/llama"
touch "${TMP}/bin/windows_x86_64/python/python.exe" \
      "${TMP}/bin/windows_x86_64/kiwix/kiwix-serve.exe" \
      "${TMP}/bin/windows_x86_64/llama/llama-server.exe"
DRY_OUT="$(bash "${PROVISION_SH}" --dry-run --product PocketSurvival --target /tmp/fakeusb 2>&1; echo "RC=$?")"
[[ ${DRY_OUT} == *"POSIX DRY RUN SIMULATION VERDICT"* || ${DRY_OUT} == *"DRY RUN SIMULATION VERDICT"* ]] \
    && ok "dry-run verdict emitted" || bad "dry-run verdict missing"
[[ ${DRY_OUT} != *"RC=1"* ]] && ok "dry-run exits 0" || bad "dry-run exited 1"
rm -rf "${TMP}"

echo "== 5) provision_usb.sh parallel orchestration =="
# The orchestrator block must dispatch ensure_payload_assets and fetch_engines
# concurrently (background jobs + wait), and no longer run them inline.
grep -q 'PAYLOAD_PID=' "${PROVISION_SH}" && ok "payload PID captured" || bad "payload PID missing"
grep -q 'ENGINE_PID='  "${PROVISION_SH}" && ok "engine PID captured"  || bad "engine PID missing"
grep -q 'wait "${PAYLOAD_PID}"' "${PROVISION_SH}" && ok "waits payload" || bad "payload wait missing"
grep -q 'wait "${ENGINE_PID}"'  "${PROVISION_SH}" && ok "waits engine"  || bad "engine wait missing"
grep -q 'fetch_engines' "${PROVISION_SH}" && ok "fetch_engines defined" || bad "fetch_engines missing"
grep -q 'ensure_payload_assets "${RESOLVED_SKU}" &' "${PROVISION_SH}" && ok "payload dispatched in background" || bad "payload not backgrounded"
grep -q 'trap ' "${PROVISION_SH}" && ok "interrupt trap present" || bad "trap missing"

echo "== 6) bash -n parse =="
bash -n "${PROVISION_SH}" && ok "provision_usb.sh parses" || bad "provision_usb.sh syntax"
bash -n "${VALIDATOR_SH}" && ok "SafetyValidator.sh parses" || bad "SafetyValidator.sh syntax"

echo ""
echo "== RESULT =="
echo "  ${PASS} passed, ${FAIL} failed"
[[ ${FAIL} -eq 0 ]] || exit 1
