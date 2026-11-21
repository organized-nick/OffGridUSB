#!/usr/bin/env bash
# test_audit_lean_mode.sh - verifies the lean/SKU-profile audit fixes from the
# ogusb-e2e follow-up (2026-11-21):
#   1. lean SKU payload audits against the SKU asset list, not the tier ladder
#   2. AI-free SKUs (Product1: 0 models) SKIP the llama-server 8082 checks
#   3. --sku/--profile flags work without a staged product_sku.json
#   4. POSIX process isolation accepts host interpreters serving from the drive
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT_PY="${SCRIPT_DIR}/../tools/audit_offgrid_usb.py"
PYTHON="${PYTHON:-python3}"

pass=0; fail=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $1"; fail=$((fail+1)); }

# ---------------------------------------------------------------------------
# Build a minimal mock lean drive fixture.
# ---------------------------------------------------------------------------
build_fixture() {
    local drive="$1"           # base dir
    local with_sku_json="$2"   # write manifests/product_sku.json?
    local with_models="$3"     # stage a GGUF model (Product2-like)?

    mkdir -p "${drive}/manifests" "${drive}/data/zim" "${drive}/data/models" \
             "${drive}/bin/linux_x86_64" "${drive}/bin/polyglot" \
             "${drive}/bin/windows_x86_64/python" "${drive}/bin/windows_x86_64/kiwix" \
             "${drive}/bin/windows_x86_64/llama"

    cat > "${drive}/manifests/zim.json" <<'JSON'
{"archives": [
  {"id": "z1", "filename": "wikipedia_en_mini.zim", "size_bytes": 2048, "tier": 1},
  {"id": "z2", "filename": "medlineplus.zim", "size_bytes": 2048, "tier": 1},
  {"id": "z3", "filename": "big_archive_full_only.zim", "size_bytes": 999999999, "tier": 1},
  {"id": "z4", "filename": "another_full_only.zim", "size_bytes": 999999999, "tier": 1}
]}
JSON

    cat > "${drive}/manifests/models.json" <<'JSON'
{"models": [
  {"id": "m1", "filename": "smollm2-135m-instruct-q4_k_m.gguf", "size_bytes": 2048, "tier": 1, "sha256": ""}
]}
JSON

    if [[ "${with_sku_json}" == true ]]; then
        if [[ "${with_models}" == true ]]; then
            cat > "${drive}/manifests/product_sku.json" <<'JSON'
{"schema_version": "1.0", "sku": "Product2", "name": "FieldReady",
 "active_zim_archives": ["wikipedia_en_mini.zim", "medlineplus.zim"],
 "active_models": ["smollm2-135m-instruct-q4_k_m.gguf"]}
JSON
        else
            cat > "${drive}/manifests/product_sku.json" <<'JSON'
{"schema_version": "1.0", "sku": "Product1", "name": "PocketSurvival",
 "active_zim_archives": ["wikipedia_en_mini.zim", "medlineplus.zim"],
 "active_models": []}
JSON
        fi
    fi

    # Staged lean payload: only the 2 active zims (plus one on a full drive).
    printf 'ZIM\x04rest-of-container' > "${drive}/data/zim/wikipedia_en_mini.zim"
    printf 'ZIM\x04rest-of-container' > "${drive}/data/zim/medlineplus.zim"
    # pad to declared size so size checks (min 98% of 2048) pass
    head -c 4096 /dev/zero >> "${drive}/data/zim/wikipedia_en_mini.zim"
    head -c 4096 /dev/zero >> "${drive}/data/zim/medlineplus.zim"
    printf 'GGUF\x03\x00\x00\x00' > "${drive}/data/models/smollm2-135m-instruct-q4_k_m.gguf"

    # Launchers (LF, no BOM)
    printf 'echo off\r\n' > "${drive}/START_OFFGRIDUSB_WINDOWS.bat"
    printf 'echo off\r\n' > "${drive}/run_windows.bat"
    printf '#!/usr/bin/env bash\necho hi\n' > "${drive}/START_OFFGRIDUSB_LINUX.sh"
    printf '#!/usr/bin/env bash\necho hi\n' > "${drive}/START_OFFGRIDUSB_MAC.command"
    printf '#!/usr/bin/env bash\necho hi\n' > "${drive}/run_linux.sh"
    printf '#!/usr/bin/env bash\necho hi\n' > "${drive}/run_macos.command"

    # Windows runtime binaries (MZ/PE magic)
    for w in \
        "bin/windows_x86_64/kiwix/kiwix-serve.exe" \
        "bin/windows_x86_64/llama/llama-server.exe" \
        "bin/windows_x86_64/python/python.exe"; do
        printf 'MZ\x90\x00\x03\x00pe-payload' > "${drive}/${w}"
    done

    # Engines with plausible magic bytes
    printf 'MZqFpD-nonsense-ape-payload' > "${drive}/bin/polyglot/llamafile.exe"
    for t in \
        "bin/linux_x86_64/kiwix-tools_linux-x86_64.tar.gz" \
        "bin/linux_x86_64/llama-ubuntu-x64.tar.gz" \
        "bin/linux_arm64/kiwix-tools_linux-aarch64.tar.gz" \
        "bin/linux_arm64/llama-ubuntu-arm64.tar.gz" \
        "bin/macos_arm64/kiwix-tools_macos.tar.gz" \
        "bin/macos_arm64/llama-macos-arm64.tar.gz" \
        "bin/macos_x86_64/kiwix-tools_macos-x86_64.tar.gz" \
        "bin/macos_x86_64/llama-macos-x64.tar.gz"; do
        mkdir -p "${drive}/$(dirname "${t}")"
        # real gzip+tar member so the tarball inspection (tarfile) passes
        ( cd "${drive}" && echo "engine-archive" | tar czf "${drive}/${t}" -T - 2>/dev/null || true )
    done

    # linux run scripts shipped under bin/linux_x86_64 need LF + shebang too
    printf '#!/usr/bin/env bash\necho hi\n' > "${drive}/bin/linux_x86_64/run.sh"
}

echo "== lean audit fixture tests =="

BASE="$(mktemp -d)"
[[ "${KEEP:-0}" == 1 ]] || trap 'rm -rf "${BASE}"' EXIT

# --- Test 1: AI-free SKU (Product1, product_sku.json staged) audits clean ----
D1="${BASE}/d1_ai_free"
build_fixture "${D1}" true false
OUT_JSON="${BASE}/d1_report.json"
if "${PYTHON}" "${AUDIT_PY}" --drive "${D1}" --tier 0 --skip-live --quiet \
    --output-json "${OUT_JSON}" >/dev/null 2>&1; then
    ok "Product1 lean drive audits clean (exit 0)"
else
    bad "Product1 lean drive audits clean (exit 0) -- see ${OUT_JSON}"
fi

# Llama-server 8082 must be gated off on an AI-free SKU: resolve the SKU
# assets directly and assert ai_enabled is False and 8082 is not audited.
if "${PYTHON}" - "${AUDIT_PY}" "${D1}" <<'PYEOF'
import importlib.util, sys
mod_path, drive = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("audit_tool", mod_path)
mod = importlib.util.module_from_spec(spec)
sys.modules["audit_tool"] = mod
spec.loader.exec_module(mod)
a = mod.OffGridUSBAuditor(drive_path=drive, tier=0)
a.audit_manifests_and_assets()  # triggers _resolve_sku_assets()
assert a.ai_enabled is False, f"ai_enabled={a.ai_enabled}"
assert a.active_zims == {"wikipedia_en_mini.zim", "medlineplus.zim"}, a.active_zims
assert a.active_models == set(), a.active_models
PYEOF
then
    ok "AI-free SKU resolves ai_enabled=False + lean asset list"
else
    bad "AI-free SKU resolves ai_enabled=False + lean asset list"
fi

# Lean drive must NOT demand the full-tier zim set (3 & 4 are full-only).
if "${PYTHON}" - "${OUT_JSON}" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
fails = [r for r in data["results"] if r["status"] == "FAIL" and "big_archive_full_only" in str(r.get("target",""))]
sys.exit(1 if fails else 0)
PYEOF
then
    ok "full-tier-only zims not demanded on lean SKU"
else
    bad "full-tier-only zims not demanded on lean SKU"
fi

# --- Test 2b: Product2-style SKU (with model) keeps ai_enabled True ---------
D2="${BASE}/d2_with_models"
build_fixture "${D2}" true true
OUT_JSON2="${BASE}/d2_report.json"
"${PYTHON}" "${AUDIT_PY}" --drive "${D2}" --tier 1 --skip-live --quiet \
    --output-json "${OUT_JSON2}" >/dev/null 2>&1 || true
if "${PYTHON}" - "${AUDIT_PY}" "${D2}" <<'PYEOF'
import importlib.util, sys
mod_path, drive = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("audit_tool2", mod_path)
mod = importlib.util.module_from_spec(spec)
sys.modules["audit_tool2"] = mod
spec.loader.exec_module(mod)
a = mod.OffGridUSBAuditor(drive_path=drive, tier=1)
a.audit_manifests_and_assets()
assert a.ai_enabled is True, f"ai_enabled={a.ai_enabled}"
assert a.active_models == {"smollm2-135m-instruct-q4_k_m.gguf"}, a.active_models
PYEOF
then
    ok "AI-enabled SKU keeps 8082 checks enabled"
else
    bad "AI-enabled SKU keeps 8082 checks enabled"
fi

# --- Test 3: --sku/--profile flags without a staged product_sku.json ---------
D3="${BASE}/d3_no_sku_json"
build_fixture "${D3}" false false
rm -f "${D3}/manifests/product_sku.json"
OUT_JSON3="${BASE}/d3_report.json"
if "${PYTHON}" "${AUDIT_PY}" --drive "${D3}" --tier 0 --skip-live --quiet \
    --sku Product1 --profile lean \
    --products-json "${SCRIPT_DIR}/../../manifests/products.json" \
    --output-json "${OUT_JSON3}" >/dev/null 2>&1; then
    ok "--sku Product1 --profile lean audits clean without product_sku.json"
else
    bad "--sku Product1 --profile lean audits clean without product_sku.json"
fi

# --- Test 4: POSIX process isolation via cmdline content paths ---------------
# Mock a process table entry where the interpreter is a host python but the
# served script lives on the drive (nixos scenario).
MOCK_TABLE="${BASE}/mock_processes.json"
"${PYTHON}" - "${D1}" "${MOCK_TABLE}" <<'PYEOF'
import json, sys
drive = sys.argv[1]
table = {
    "8000": "/nix/store/abc-python/bin/python3.14",
    "8081": f"{drive}/bin/linux_x86_64/kiwix/kiwix-serve",
}
json.dump(table, open(sys.argv[2], "w"))
PYEOF
OUT_JSON4="${BASE}/d4_report.json"
if "${PYTHON}" "${AUDIT_PY}" --drive "${D1}" --tier 0 --skip-live --quiet \
    --mock-process-table "${MOCK_TABLE}" \
    --output-json "${OUT_JSON4}" >/dev/null 2>&1; then
    ok "mock isolation table with host interpreter + no 8082 passes"
else
    bad "mock isolation table with host interpreter + no 8082 passes"
fi

echo
echo "== RESULT =="
echo "  ${pass} passed, ${fail} failed"
[[ ${fail} -eq 0 ]]
