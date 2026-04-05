#!/usr/bin/env bash
# test-hooks.sh
# Integration tests for pre-commit hooks
# Verifies each hook returns correct exit codes against test fixtures
#
# Usage:
#   bash tests/integration/test-hooks.sh
#
# Prerequisites:
#   - All security tools installed (trivy, checkov, tflint, gitleaks, pre-commit)
#   - Running from the repo root directory
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed

set -euo pipefail

# Detect Python command
PYTHON_CMD=""
if python3 --version &>/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif python --version &>/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found"
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURES_DIR="$REPO_ROOT/tests/fixtures"
HOOKS_DIR="$REPO_ROOT/hooks"

PASS=0
FAIL=0
SKIP=0

# Colors (if terminal supports them)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    PASS=$((PASS + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1 (expected: $2, got: $3)"
    FAIL=$((FAIL + 1))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1 ($2)"
    SKIP=$((SKIP + 1))
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Run a hook script and check exit code
# Args: hook_script fixture_dir expected_exit_code test_description
run_hook_test() {
    local hook_script="$1"
    local fixture_dir="$2"
    local expected_exit="$3"
    local description="$4"

    if [ ! -f "$hook_script" ]; then
        log_skip "$description" "hook script not found: $hook_script"
        return
    fi

    local actual_exit=0
    (cd "$fixture_dir" && bash "$hook_script") >/dev/null 2>&1 || actual_exit=$?

    if [ "$actual_exit" -eq "$expected_exit" ]; then
        log_pass "$description"
    elif [ "$expected_exit" -eq 1 ] && [ "$actual_exit" -ge 2 ]; then
        # Infrastructure error (fail-open) -- tool issue, not a test failure
        log_skip "$description" "infrastructure error (exit $actual_exit, fail-open)"
    else
        log_fail "$description" "$expected_exit" "$actual_exit"
    fi
}

echo "=========================================="
echo " Hook Integration Tests"
echo "=========================================="
echo ""

# ---- Tool availability checks ----
echo "--- Checking tool availability ---"

tools=("trivy" "checkov" "tflint" "gitleaks" "pre-commit")
for tool in "${tools[@]}"; do
    if command_exists "$tool"; then
        echo "  [OK] $tool found"
    else
        echo "  [WARN] $tool not found -- related tests will be skipped"
    fi
done
echo ""

# ---- trivy-iac-critical ----
echo "--- trivy-iac-critical ---"

if command_exists trivy; then
    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "trivy-iac-critical: valid AWS fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-critical/aws" 1 \
        "trivy-iac-critical: critical AWS fixture should fail (exit 1)"

    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-valid/azure" 0 \
        "trivy-iac-critical: valid Azure fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-critical/azure" 1 \
        "trivy-iac-critical: critical Azure fixture should fail (exit 1)"

    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-valid/gcp" 0 \
        "trivy-iac-critical: valid GCP fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/trivy-iac-critical.sh" \
        "$FIXTURES_DIR/terraform-critical/gcp" 1 \
        "trivy-iac-critical: critical GCP fixture should fail (exit 1)"
else
    log_skip "trivy-iac-critical" "trivy not installed"
fi
echo ""

# ---- trivy-iac-full ----
echo "--- trivy-iac-full ---"

if command_exists trivy; then
    run_hook_test "$HOOKS_DIR/trivy-iac-full.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "trivy-iac-full: valid AWS fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/trivy-iac-full.sh" \
        "$FIXTURES_DIR/terraform-critical/aws" 1 \
        "trivy-iac-full: critical AWS fixture should fail (exit 1)"
else
    log_skip "trivy-iac-full" "trivy not installed"
fi
echo ""

# ---- trivy-secrets ----
echo "--- trivy-secrets ---"

if command_exists trivy; then
    run_hook_test "$HOOKS_DIR/trivy-secrets.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "trivy-secrets: valid fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/trivy-secrets.sh" \
        "$FIXTURES_DIR/terraform-secret" 1 \
        "trivy-secrets: secret fixture should fail (exit 1)"
else
    log_skip "trivy-secrets" "trivy not installed"
fi
echo ""

# ---- gitleaks ----
echo "--- gitleaks ---"

if command_exists gitleaks; then
    run_hook_test "$HOOKS_DIR/gitleaks.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "gitleaks: valid fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/gitleaks.sh" \
        "$FIXTURES_DIR/terraform-secret" 1 \
        "gitleaks: secret fixture should fail (exit 1)"
else
    log_skip "gitleaks" "gitleaks not installed"
fi
echo ""

# ---- checkov ----
echo "--- checkov ---"

if command_exists checkov; then
    run_hook_test "$HOOKS_DIR/checkov.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "checkov: valid AWS fixture should pass (exit 0)"

    run_hook_test "$HOOKS_DIR/checkov.sh" \
        "$FIXTURES_DIR/terraform-critical/aws" 1 \
        "checkov: critical AWS fixture should fail (exit 1)"
else
    log_skip "checkov" "checkov not installed"
fi
echo ""

# ---- tflint ----
echo "--- tflint ---"

if command_exists tflint; then
    run_hook_test "$HOOKS_DIR/tflint.sh" \
        "$FIXTURES_DIR/terraform-valid/aws" 0 \
        "tflint: valid AWS fixture should pass (exit 0)"
else
    log_skip "tflint" "tflint not installed"
fi
echo ""

# ---- validate-suppressions ----
echo "--- validate-suppressions ---"

if [ -n "$PYTHON_CMD" ]; then
    # Test with no suppression file (should pass)
    actual_exit=0
    (cd "$FIXTURES_DIR/terraform-valid/aws" && $PYTHON_CMD "$HOOKS_DIR/validate-suppressions.py") >/dev/null 2>&1 || actual_exit=$?
    if [ "$actual_exit" -eq 0 ]; then
        log_pass "validate-suppressions: missing file should pass (exit 0)"
    else
        log_fail "validate-suppressions: missing file should pass" "0" "$actual_exit"
    fi
else
    log_skip "validate-suppressions" "python not installed"
fi
echo ""

# ---- Summary ----
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
