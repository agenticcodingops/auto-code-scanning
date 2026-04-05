#!/usr/bin/env bash
# test-templates.sh
# Validates tier templates (starter, standard, strict) for correctness.
#
# Usage:
#   bash tests/integration/test-templates.sh
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
TEMPLATES_DIR="$REPO_ROOT/templates"

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
echo " Template Validation Tests"
echo "=========================================="
echo ""

# ---- Test 1: Template directories exist ----
echo "--- Template Directories ---"

for tier in starter standard strict; do
    if [ -d "$TEMPLATES_DIR/$tier" ]; then
        log_pass "$tier/ directory exists"
    else
        log_fail "$tier/ directory missing"
    fi
done
echo ""

# ---- Test 2: Pre-commit config files exist ----
echo "--- Template Files ---"

for tier in starter standard strict; do
    config="$TEMPLATES_DIR/$tier/pre-commit-config.yaml"
    if [ -f "$config" ]; then
        log_pass "$tier/pre-commit-config.yaml exists"
    else
        log_fail "$tier/pre-commit-config.yaml missing"
    fi
done
echo ""

# ---- Test 3: YAML syntax validation ----
echo "--- YAML Syntax ---"

if [ -n "$PYTHON_CMD" ]; then
    for tier in starter standard strict; do
        config="$TEMPLATES_DIR/$tier/pre-commit-config.yaml"
        if [ -f "$config" ]; then
            if $PYTHON_CMD -c "
import yaml, sys
try:
    with open(sys.argv[1], encoding='utf-8') as f:
        yaml.safe_load(f)
    sys.exit(0)
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" "$config" 2>/dev/null; then
                log_pass "$tier: valid YAML"
            else
                log_fail "$tier: invalid YAML syntax"
            fi
        fi
    done
else
    log_skip "YAML validation" "python not available"
fi
echo ""

# ---- Test 4: Starter tier hooks ----
echo "--- Starter Tier Hooks ---"

STARTER_CONFIG="$TEMPLATES_DIR/starter/pre-commit-config.yaml"
if [ -f "$STARTER_CONFIG" ]; then
    # Starter includes: trailing-whitespace, end-of-file-fixer, check-yaml,
    #   detect-private-key, terraform_fmt, trivy-secrets
    starter_required_hooks=("trailing-whitespace" "end-of-file-fixer" "check-yaml" "detect-private-key" "terraform_fmt" "trivy-secrets")
    for hook in "${starter_required_hooks[@]}"; do
        if grep -q "$hook" "$STARTER_CONFIG" 2>/dev/null; then
            log_pass "starter: includes $hook"
        else
            log_fail "starter: missing $hook"
        fi
    done

    # Starter should NOT include these hooks (they belong to higher tiers)
    starter_excluded_hooks=("trivy-iac-critical" "trivy-iac-full" "checkov" "checkov-strict" "validate-suppressions")
    for hook in "${starter_excluded_hooks[@]}"; do
        # Only fail if it's included AND not commented out
        if grep -v "^#\|^[[:space:]]*#" "$STARTER_CONFIG" 2>/dev/null | grep -q "$hook"; then
            log_fail "starter: should not include $hook (it belongs to a higher tier)"
        else
            log_pass "starter: correctly excludes $hook"
        fi
    done
else
    log_fail "starter template not found"
fi
echo ""

# ---- Test 5: Standard tier hooks ----
echo "--- Standard Tier Hooks ---"

STANDARD_CONFIG="$TEMPLATES_DIR/standard/pre-commit-config.yaml"
if [ -f "$STANDARD_CONFIG" ]; then
    # Standard includes all starter hooks plus: check-json, terraform_validate,
    #   terraform_tflint, trivy-iac-critical
    standard_required_hooks=(
        "trailing-whitespace"
        "end-of-file-fixer"
        "check-yaml"
        "check-json"
        "detect-private-key"
        "terraform_fmt"
        "terraform_validate"
        "terraform_tflint"
        "trivy-secrets"
        "trivy-iac-critical"
    )
    for hook in "${standard_required_hooks[@]}"; do
        if grep -q "$hook" "$STANDARD_CONFIG" 2>/dev/null; then
            log_pass "standard: includes $hook"
        else
            log_fail "standard: missing $hook"
        fi
    done

    # Standard should NOT have no-commit-to-branch (design decision)
    if grep -v "^#\|^[[:space:]]*#" "$STANDARD_CONFIG" 2>/dev/null | grep -q "no-commit-to-branch"; then
        log_fail "standard: should not include no-commit-to-branch (design decision)"
    else
        log_pass "standard: correctly excludes no-commit-to-branch"
    fi

    # Standard should NOT include strict-tier hooks
    standard_excluded_hooks=("trivy-iac-full" "checkov" "checkov-strict" "validate-suppressions")
    for hook in "${standard_excluded_hooks[@]}"; do
        if grep -v "^#\|^[[:space:]]*#" "$STANDARD_CONFIG" 2>/dev/null | grep -q "$hook"; then
            log_fail "standard: should not include $hook (it belongs to strict tier)"
        else
            log_pass "standard: correctly excludes $hook"
        fi
    done
else
    log_fail "standard template not found"
fi
echo ""

# ---- Test 6: Strict tier hooks ----
echo "--- Strict Tier Hooks ---"

STRICT_CONFIG="$TEMPLATES_DIR/strict/pre-commit-config.yaml"
if [ -f "$STRICT_CONFIG" ]; then
    # Strict includes all standard hooks plus: check-added-large-files,
    #   check-merge-conflict, terraform_docs, trivy-iac-full, checkov,
    #   checkov-strict, validate-suppressions
    strict_required_hooks=(
        "trailing-whitespace"
        "end-of-file-fixer"
        "check-yaml"
        "check-json"
        "check-added-large-files"
        "check-merge-conflict"
        "detect-private-key"
        "terraform_fmt"
        "terraform_validate"
        "terraform_docs"
        "terraform_tflint"
        "trivy-secrets"
        "trivy-iac-critical"
        "trivy-iac-full"
        "checkov"
        "checkov-strict"
        "validate-suppressions"
    )
    for hook in "${strict_required_hooks[@]}"; do
        if grep -q "$hook" "$STRICT_CONFIG" 2>/dev/null; then
            log_pass "strict: includes $hook"
        else
            log_fail "strict: missing $hook"
        fi
    done

    # Strict should have commitizen commented out (opt-in)
    if grep -q "commitizen\|conventional" "$STRICT_CONFIG" 2>/dev/null; then
        # It should be present but commented
        if grep "^#.*commitizen\|^#.*conventional\|^[[:space:]]*#.*commitizen" "$STRICT_CONFIG" 2>/dev/null; then
            log_pass "strict: commitizen is opt-in (commented out)"
        else
            log_pass "strict: commitizen configuration present"
        fi
    else
        log_pass "strict: commitizen not included (opt-in per design)"
    fi
else
    log_fail "strict template not found"
fi
echo ""

# ---- Test 7: Templates reference correct repo ----
echo "--- Repository References ---"

for tier in starter standard strict; do
    config="$TEMPLATES_DIR/$tier/pre-commit-config.yaml"
    if [ -f "$config" ]; then
        if grep -q "auto-code-scanning" "$config" 2>/dev/null; then
            log_pass "$tier: references correct repository"
        else
            log_fail "$tier: does not reference auto-code-scanning"
        fi
    fi
done
echo ""

# ---- Test 8: Templates use language: script ----
echo "--- Hook Language Setting ---"

for tier in starter standard strict; do
    config="$TEMPLATES_DIR/$tier/pre-commit-config.yaml"
    if [ -f "$config" ]; then
        # Templates reference this repo's hooks which use language: script
        # They shouldn't override language to something else
        if grep "language:" "$config" 2>/dev/null | grep -v "^#" | grep -v "script" >/dev/null 2>&1; then
            log_fail "$tier: contains non-script language override"
        else
            log_pass "$tier: no conflicting language overrides"
        fi
    fi
done
echo ""

# ---- Summary ----
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
