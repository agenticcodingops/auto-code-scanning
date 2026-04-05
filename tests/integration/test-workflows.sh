#!/usr/bin/env bash
# test-workflows.sh
# Validates GitHub Actions workflow syntax and required fields.
#
# Usage:
#   bash tests/integration/test-workflows.sh
#
# Prerequisites:
#   - Running from the repo root directory
#   - Python 3.8+ with PyYAML (for YAML validation)
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
WORKFLOWS_DIR="$REPO_ROOT/.github/workflows"

PASS=0
FAIL=0
SKIP=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    PASS=$((PASS + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAIL=$((FAIL + 1))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1 ($2)"
    SKIP=$((SKIP + 1))
}

echo "=========================================="
echo " Workflow Validation Tests"
echo "=========================================="
echo ""

# ---- Test 1: Workflow files exist ----
echo "--- Required Workflow Files ---"

required_workflows=("reusable-scan.yml" "ci.yml" "performance-check.yml" "bypass-detection.yml")
for wf in "${required_workflows[@]}"; do
    if [ -f "$WORKFLOWS_DIR/$wf" ]; then
        log_pass "$wf exists"
    else
        log_fail "$wf missing"
    fi
done
echo ""

# ---- Test 2: YAML syntax validation ----
echo "--- YAML Syntax Validation ---"

if [ -n "$PYTHON_CMD" ]; then
    for wf_file in "$WORKFLOWS_DIR"/*.yml; do
        if [ ! -f "$wf_file" ]; then
            continue
        fi
        wf_name=$(basename "$wf_file")
        if $PYTHON_CMD -c "
import yaml, sys
try:
    with open(sys.argv[1], encoding='utf-8') as f:
        yaml.safe_load(f)
    sys.exit(0)
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" "$wf_file" 2>/dev/null; then
            log_pass "$wf_name: valid YAML"
        else
            log_fail "$wf_name: invalid YAML syntax"
        fi
    done
else
    log_skip "YAML validation" "python not available"
fi
echo ""

# ---- Test 3: Reusable workflow structure ----
echo "--- reusable-scan.yml Structure ---"

REUSABLE="$WORKFLOWS_DIR/reusable-scan.yml"
if [ -f "$REUSABLE" ]; then
    # Check for workflow_call trigger
    if grep -q "workflow_call" "$REUSABLE" 2>/dev/null; then
        log_pass "reusable-scan.yml: has workflow_call trigger"
    else
        log_fail "reusable-scan.yml: missing workflow_call trigger"
    fi

    # Check for required inputs
    if grep -q "cloud-provider" "$REUSABLE" 2>/dev/null; then
        log_pass "reusable-scan.yml: has cloud-provider input"
    else
        log_fail "reusable-scan.yml: missing cloud-provider input"
    fi

    if grep -q "terraform-directory" "$REUSABLE" 2>/dev/null; then
        log_pass "reusable-scan.yml: has terraform-directory input"
    else
        log_fail "reusable-scan.yml: missing terraform-directory input"
    fi

    # Check for SARIF support
    if grep -q "sarif\|SARIF" "$REUSABLE" 2>/dev/null; then
        log_pass "reusable-scan.yml: has SARIF support"
    else
        log_fail "reusable-scan.yml: missing SARIF support"
    fi

    # Check for severity-threshold input
    if grep -q "severity" "$REUSABLE" 2>/dev/null; then
        log_pass "reusable-scan.yml: has severity configuration"
    else
        log_fail "reusable-scan.yml: missing severity configuration"
    fi
else
    log_fail "reusable-scan.yml: file not found"
fi
echo ""

# ---- Test 4: CI workflow structure ----
echo "--- ci.yml Structure ---"

CI_WF="$WORKFLOWS_DIR/ci.yml"
if [ -f "$CI_WF" ]; then
    if grep -q "pull_request\|push" "$CI_WF" 2>/dev/null; then
        log_pass "ci.yml: has trigger events"
    else
        log_fail "ci.yml: missing trigger events"
    fi
else
    log_fail "ci.yml: file not found"
fi
echo ""

# ---- Test 5: Performance check workflow ----
echo "--- performance-check.yml Structure ---"

PERF_WF="$WORKFLOWS_DIR/performance-check.yml"
if [ -f "$PERF_WF" ]; then
    if grep -q "schedule\|workflow_dispatch\|push" "$PERF_WF" 2>/dev/null; then
        log_pass "performance-check.yml: has trigger events"
    else
        log_fail "performance-check.yml: missing trigger events"
    fi
else
    log_fail "performance-check.yml: file not found"
fi
echo ""

# ---- Test 6: No hardcoded secrets in workflows ----
echo "--- Secret Detection in Workflows ---"

secrets_found=0
for wf_file in "$WORKFLOWS_DIR"/*.yml; do
    if [ ! -f "$wf_file" ]; then
        continue
    fi
    # Check for common secret patterns (not references like ${{ secrets.* }})
    if grep -P "AKIA[A-Z0-9]{16}|password\s*[:=]\s*['\"][^'\"]+['\"]" "$wf_file" 2>/dev/null; then
        log_fail "$(basename "$wf_file"): contains potential hardcoded secret"
        secrets_found=1
    fi
done
if [ "$secrets_found" -eq 0 ]; then
    log_pass "No hardcoded secrets found in workflows"
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
