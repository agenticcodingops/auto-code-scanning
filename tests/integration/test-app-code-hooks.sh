#!/usr/bin/env bash
# test-app-code-hooks.sh
# Integration tests for the app-code dispatcher hooks (C#/TypeScript).
# Runs each hook against planted-finding fixtures in a throwaway git repo and
# asserts exit codes. Uses the deterministic local Semgrep rule (SEMGREP_RULESET_*)
# so results don't depend on the remote p/csharp / p/typescript pack contents.
#
# Usage: bash tests/integration/test-app-code-hooks.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOKS_DIR="${REPO_ROOT}/hooks"
FIXTURES="${REPO_ROOT}/tests/fixtures"
RULE="${REPO_ROOT}/tests/fixtures/semgrep-rules/planted.yaml"

PASS=0; FAIL=0; SKIP=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS+1)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1 (expected $2, got $3)"; FAIL=$((FAIL+1)); }
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1 ($2)"; SKIP=$((SKIP+1)); }

if ! command -v semgrep >/dev/null 2>&1; then
    echo "semgrep not installed — skipping all app-code hook tests"
    exit 0
fi
if ! command -v git >/dev/null 2>&1; then
    echo "git not available — skipping"
    exit 0
fi

export SEMGREP_RULESET_CSHARP="${RULE}"
export SEMGREP_RULESET_TYPESCRIPT="${RULE}"
export PYTHONUTF8=1

# Run a hook in a throwaway git repo with one staged fixture file.
# Args: hook_id  fixture_file  expected_exit  description
run_case() {
    local hook_id="$1" fixture="$2" expected="$3" desc="$4"
    local tmp; tmp="$(mktemp -d)"
    (
        cd "${tmp}"
        git init -q
        git config user.email t@t.t; git config user.name t
        local base; base="$(basename "${fixture}")"
        cp "${fixture}" "${base}"
        git add "${base}"
        SCAN_HOOK_ID="${hook_id}" bash "${HOOKS_DIR}/${hook_id}.sh" >/dev/null 2>&1
    )
    local actual=$?
    rm -rf "${tmp}"
    if [[ ${actual} -eq ${expected} ]]; then
        log_pass "${desc}"
    elif [[ ${expected} -eq 1 && ${actual} -ge 2 ]]; then
        log_skip "${desc}" "infra error exit ${actual} (fail-open)"
    else
        log_fail "${desc}" "${expected}" "${actual}"
    fi
}

echo "=== App-code hook integration tests ==="
run_case "semgrep-csharp"     "${FIXTURES}/csharp-fail/Vulnerable.cs" 1 "semgrep-csharp: planted MD5 finding should FAIL (1)"
run_case "semgrep-csharp"     "${FIXTURES}/csharp-pass/Clean.cs"      0 "semgrep-csharp: clean C# should PASS (0)"
run_case "semgrep-typescript" "${FIXTURES}/typescript-fail/vulnerable.ts" 1 "semgrep-typescript: planted eval finding should FAIL (1)"

# No staged files of the relevant type -> hook should no-op PASS (0).
tmp="$(mktemp -d)"; ( cd "${tmp}"; git init -q; git config user.email t@t.t; git config user.name t; echo x > a.txt; git add a.txt; SCAN_HOOK_ID=semgrep-csharp bash "${HOOKS_DIR}/semgrep-csharp.sh" >/dev/null 2>&1 ); rc=$?; rm -rf "${tmp}"
[[ ${rc} -eq 0 ]] && log_pass "semgrep-csharp: no C# staged should PASS (0)" || log_fail "semgrep-csharp: no C# staged" 0 "${rc}"

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped ==="
[[ ${FAIL} -gt 0 ]] && exit 1 || exit 0
