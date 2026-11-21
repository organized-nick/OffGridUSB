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
[[ $(norm Product1       -1) == "Product1" ]]           && ok "Product1     -> itself"     || bad "Product1 passthrough"
[[ $(norm Product2       -1) == "Product2" ]]           && ok "Product2     -> itself"     || bad "Product2 passthrough"
[[ $(norm Product3       -1) == "Product3" ]]           && ok "Product3     -> itself"     || bad "Product3 passthrough"
[[ $(norm ""            0 ) == "Product1" ]]            && ok "tier 0  -> Product1"        || bad "tier 0 mapping"
[[ $(norm ""            1 ) == "Product2" ]]            && ok "tier 1  -> Product2"        || bad "tier 1 mapping"
[[ $(norm ""            2 ) == "Product3" ]]            && ok "tier 2  -> Product3"        || bad "tier 2 mapping"

echo "== 2) SafetyValidator.sh capacity ladder (golden bytes vs ps1) =="
# Sourcing SafetyValidator.sh leaks its `set -euo pipefail` into this shell;
# restore the test's own options (-e would abort on the expected non-zero
# validator CLI exits below).
source "${VALIDATOR_SH}" >/dev/null
set +e
check_cap() {
    local sku="$1" want="$2"
    if [[ "${SKU_MIN_BYTES[${sku}]:-MISSING}" == "${want}" ]]; then
        ok "${sku}: min bytes ${want}"
    else
        bad "${sku}: expected ${want}, got '${SKU_MIN_BYTES[${sku}]:-MISSING}'"
    fi
}
# Golden values lifted from lib/SafetyValidator.ps1 SkuMinCapacityBytes
# (64 / 64 / 256 GB ladder per AGENTS.md product list, 2026-11-16).
check_cap "Product1"         61000000000
check_cap "PocketSurvival"   61000000000
check_cap "Product2"         61000000000
check_cap "FieldReady"       61000000000
check_cap "Product3"         245000000000
check_cap "CivilizationArk"  245000000000

echo "== 3) provision_usb.sh --info readiness table includes every SKU =="
INFO_OUT="$(bash "${PROVISION_SH}" --info 2>&1)"
for sku in "Product1" "Product2" "Product3"; do
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

echo "== 6) parallel orchestrator: multi-drive dry-run with a fake drive list =="
ORCH_OUT="$(bash "${PROVISION_SH}" --dry-run --non-interactive --product PocketSurvival \
    --target /tmp/fakeusb1 --target /tmp/fakeusb2 2>&1; echo "RC=$?")"
[[ ${ORCH_OUT} == *"PARALLEL PROVISIONING SUMMARY"* ]] && ok "orchestrator summary printed" || bad "orchestrator summary missing"
[[ ${ORCH_OUT} == *"SUCCESS"* ]] && ok "children reported SUCCESS" || bad "children did not report SUCCESS"
[[ ${ORCH_OUT} == *"RC=0"* ]] && ok "orchestrator exits 0" || bad "orchestrator exited nonzero"
[[ ${ORCH_OUT} == *"2 drives"* ]] && ok "both drives in orchestrator" || bad "drive count wrong"
ls "${SCRIPT_DIR}/../logs/" 2>/dev/null | grep -q "Product1" && ok "per-drive logs created" || bad "per-drive logs missing"
rm -f "${SCRIPT_DIR}/../logs/"*.log 2>/dev/null || true

echo "== 7) parse_drive_spec: per-drive SKU overrides =="
PD() {
    local spec="$1"
    (
        cd "${SCRIPT_DIR}/.."
        bash -c "
            RESOLVED_SKU='Product1'
            source <(sed -n '/^declare -A SKU_MIN_BYTES=/,/^}/p' 'lib/SafetyValidator.sh')
            source <(sed -n '/^parse_drive_spec() {$/,/^}/p' 'provision_usb.sh')
            source <(sed -n '/^normalize_sku() {$/,/^}/p' 'provision_usb.sh')
            parse_drive_spec \"${spec}\"
        "
    ) 2>/dev/null
}
OUT=$(PD "/media/usb/d1")
[[ "$(echo "$OUT" | head -1)" == "/media/usb/d1" && "$(echo "$OUT" | tail -1)" == "Product1" ]] && ok "plain drive spec" || bad "plain drive spec"
OUT=$(PD "/media/usb/d1:Product2")
[[ "$(echo "$OUT" | head -1)" == "/media/usb/d1" && "$(echo "$OUT" | tail -1)" == "Product2" ]] && ok "per-drive SKU override" || bad "per-drive SKU override"
OUT=$(PD "/media/usb/d1:Product3")
[[ "$(echo "$OUT" | tail -1)" == "Product3" ]] && ok "per-drive SKU override (Product3)" || bad "per-drive SKU override (Product3)"
OUT=$(PD "/media/usb/d1")
[[ "$(echo "$OUT" | tail -1)" == "Product1" ]] && ok "default SKU applied" || bad "default SKU"

echo "== 8) gate_drive: per-drive safety gate (via SafetyValidator CLI) =="
# gate_drive() wraps assert_target_drive_safety + assert_drive_capacity. Its
# dry-run behavior is covered by the orchestrator dry-run test (section 6).
# Here we verify the underlying SafetyValidator CLI gates directly.
VALIDATOR_SH="${SCRIPT_DIR}/../lib/SafetyValidator.sh"
bash "${VALIDATOR_SH}" "/" "Product1" >/dev/null 2>&1
[[ $? -ne 0 ]] && ok "safety gate fails on OS root path" || bad "safety gate root path"
bash "${VALIDATOR_SH}" "/tmp/does_not_exist_mount" "Product1" >/dev/null 2>&1
[[ $? -ne 0 ]] && ok "safety gate fails on nonexistent mount" || bad "safety gate nonexistent mount"
bash "${VALIDATOR_SH}" "/tmp/does_not_exist_mount" "Product3" >/dev/null 2>&1
[[ $? -ne 0 ]] && ok "capacity gate fails for nonexistent mount (256GB SKU)" || bad "capacity gate 256GB SKU"
bash "${VALIDATOR_SH}" "${SCRIPT_DIR}" "Product1" >/dev/null 2>&1
[[ $? -eq 0 ]] && ok "capacity gate passes for Product1 on a real volume" || bad "capacity gate Product1"

echo "== 9) copy_writethrough: temp + rename semantics =="
TMP="$(mktemp -d)"
echo "hello world payload" > "${TMP}/src.txt"
CW() {
    (
        cd "${SCRIPT_DIR}/.."
        bash -c "
            BWLIMIT='2048'
            source <(sed -n '/^copy_writethrough() {$/,/^}/p' 'provision_usb.sh')
            copy_writethrough \"${1}\" \"${2}\"
        "
    )
}
if CW "${TMP}/src.txt" "${TMP}/dst/sub.txt"; then
    [[ -f "${TMP}/dst/sub.txt" ]] && ok "copy_writethrough copies to dst" || bad "copy_writethrough dst"
    [[ ! -f "${TMP}/dst/sub.txt.tmp" ]] && ok "copy_writethrough cleans up tmp" || bad "copy_writethrough tmp"
    [[ "$(cat "${TMP}/dst/sub.txt")" == "hello world payload" ]] && ok "copy_writethrough preserves content" || bad "copy_writethrough content"
else
    bad "copy_writethrough failed"
fi
rm -rf "${TMP}"

echo "== 10) parity functions defined =="
for fn in prune_non_sku_assets build_library_xml verify_magic_header import_legacy_cache_assets safe_eject_drive gate_drive emit_whitelist_plan drive_slug; do
    grep -q "${fn}" "${PROVISION_SH}" && ok "${fn} in provision_usb.sh" || bad "${fn} in provision_usb.sh"
done
grep -q "safe_eject_drive" "${SCRIPT_DIR}/../lib/UsbStripper.sh" && ok "safe_eject_drive in UsbStripper.sh" || bad "safe_eject_drive in UsbStripper.sh"
grep -q "import_legacy_cache_assets" "${SCRIPT_DIR}/../lib/UsbStripper.sh" && ok "import_legacy_cache_assets in UsbStripper.sh" || bad "import_legacy_cache_assets in UsbStripper.sh"

echo "== 11) orchestrator: eject gating + per-drive bwlimit =="
grep -q 'safe_eject_drive "${target_list\[$i\]}"' "${PROVISION_SH}" && ok "orchestrator ejects succeeded drives" || bad "orchestrator eject"
grep -q 'DRY_RUN}" != true' "${PROVISION_SH}" && ok "eject skipped in dry-run" || bad "eject skipped in dry-run"
grep -q 'per-drive bandwidth budget' "${PROVISION_SH}" && ok "per-drive bwlimit documented" || bad "per-drive bwlimit documented"

echo "== 12) provision_usb.ps1 parallel orchestrator (-Drives mode) =="
PS1_SH="${SCRIPT_DIR}/../provision_usb.ps1"
PS1GREP() { grep -q "$1" "${PS1_SH}"; }
PS1GREP 'string\]\$Drives'            && ok "ps1 -Drives parameter declared" || bad "ps1 -Drives param missing"
PS1GREP 'Parse-DriveSpec'             && ok "ps1 drive-spec parser (letter + :SKU override)" || bad "ps1 Parse-DriveSpec missing"
PS1GREP 'perDriveBw = if (\$BwLimitKBps -gt 0) { \$BwLimitKBps } else { 2048 }' && ok "ps1 per-drive bw default 2048 KB/s" || bad "ps1 per-drive bw default missing"
PS1GREP '\${timeStamp}_\$(\$r.Sku)_\$(\$r.Drive).log' && ok "ps1 per-drive log naming <ts>_<sku>_<drive>.log" || bad "ps1 log naming missing"
PS1GREP 'Start-Process -FilePath "powershell.exe"' && ok "ps1 spawns one child engine per drive" || bad "ps1 child spawn missing"
PS1GREP '\-PassThru' && ok "ps1 captures child process for wait/aggregate" || bad "ps1 PassThru missing"
PS1GREP 'WaitForExit()'               && ok "ps1 waits and aggregates child exit codes" || bad "ps1 exit-code aggregation missing"
PS1GREP 'PARALLEL PROVISIONING SUMMARY' && ok "ps1 summary table" || bad "ps1 summary table missing"
PS1GREP 'Invoke-SafeUsbEject -Drive \$r.Drive' && ok "ps1 safe-eject for succeeded drives" || bad "ps1 eject gating missing"
PS1GREP 'NOT eject_usb.ps1' && ok "ps1 eject sourced from lib (not the eject script body)" || bad "ps1 eject sourcing"
PS1GREP 'if (\$Drives -and -not \$Info)' && ok "ps1 -Info takes precedence over -Drives" || bad "ps1 -Info precedence missing"
PS1GREP 'Status = if (\$r.Process.ExitCode -eq 0)' && ok "ps1 SUCCESS/FAIL per drive from exit code" || bad "ps1 per-drive status missing"
# Regression: without -Drives the single-drive flow is untouched (no new guard in front of it).
PS1GREP 'Assert-TargetDriveSafety -DriveLetter \$Drive' && ok "ps1 single-drive safety gate unchanged" || bad "ps1 single-drive gate changed"
# Parse-DriveSpec regex accepts letters and :SKU, rejects paths.
grep -qF 'Spec -match "^([A-Za-z])(?::([A-Za-z0-9-]+))?$"' "${PS1_SH}" && ok "ps1 drive-spec regex guards against paths" || bad "ps1 drive-spec regex missing"

echo "== 12b) parallel gate: exit-code gating + transport-tolerant safety =="
# Regression (ogusb-e2e r4, nixos): gate_drive output was string-matched
# against "PASSED*" while it echoes multi-line "[PASS] ..." validator output,
# so live-mode parallel provisioning misclassified every drive as FAIL.
grep -q 'if gate_drive "${target}" "${sku}"; then' "${PROVISION_SH}" \
    && ok "orchestrator gates on gate_drive exit code" \
    || bad "orchestrator gates on gate_drive exit code"
! grep -q 'gate_msg}" == PASSED\*' "${PROVISION_SH}" \
    && ok "stdout string-match on PASSED* removed" \
    || bad "stdout string-match on PASSED* still present"
# Transport check must be informational (WARNING, non-fatal) and resolve the
# device via findmnt with a df -P fallback (nixos gave empty TRAN).
grep -q 'informational' "${SCRIPT_DIR}/../lib/SafetyValidator.sh" \
    && ok "transport check documented as informational" \
    || bad "transport check not informational"
grep -q 'df -P "${target}"' "${SCRIPT_DIR}/../lib/SafetyValidator.sh" \
    && ok "device resolution falls back to df -P" \
    || bad "device resolution df -P fallback missing"

# Functional: safety gate must PASS (exit 0) for a valid non-root target even
# when lsblk cannot resolve the transport (simulated by a plain directory).
gate_out="$(bash "${SCRIPT_DIR}/../lib/SafetyValidator.sh" "${SCRIPT_DIR}" "Product1" 2>&1)"
gate_rc=$?
[[ ${gate_rc} -eq 0 ]] && ok "safety gate passes for real dir despite transport" || bad "safety gate failed on real dir (rc=${gate_rc}): ${gate_out}"

echo "== 12c) provisioner: free-space guard before cache prefill =="
# Regression (ogusb-e2e r4): full-profile cache prefill had no df guard and
# filled the host root fs to 100%.
grep -q 'Insufficient free space for cache prefill' "${PROVISION_SH}" \
    && ok "bash provisioner aborts on insufficient cache free space" \
    || bad "bash free-space guard missing"
grep -q 'profile_key=$(python3' "${PROVISION_SH}" \
    && ok "bash provisioner fetches the resolved profile payload (not whole tier)" \
    || bad "bash profile resolution missing"
grep -q 'fetch_assets.py" --sku "${sku}" --profile "${profile_key}"' "${PROVISION_SH}" \
    && ok "bash fetch_assets called with --sku/--profile" \
    || bad "bash fetch_assets not profile-scoped"
PS1GREP 'Insufficient free space for cache prefill' \
    && ok "ps1 provisioner aborts on insufficient cache free space" \
    || bad "ps1 free-space guard missing"

echo "== 13) bash -n parse =="
bash -n "${PROVISION_SH}" && ok "provision_usb.sh parses" || bad "provision_usb.sh syntax"
bash -n "${VALIDATOR_SH}" && ok "SafetyValidator.sh parses" || bad "SafetyValidator.sh syntax"
bash -n "${SCRIPT_DIR}/../lib/UsbStripper.sh" && ok "UsbStripper.sh parses" || bad "UsbStripper.sh syntax"

echo ""
echo "== RESULT =="
echo "  ${PASS} passed, ${FAIL} failed"
[[ ${FAIL} -eq 0 ]] || exit 1
