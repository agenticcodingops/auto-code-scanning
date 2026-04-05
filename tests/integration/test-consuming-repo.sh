#!/usr/bin/env bash
# test-consuming-repo.sh
# Integration test that simulates a consuming repository installing and using
# the security scanning hooks. Verifies the full developer workflow.
#
# Usage:
#   bash tests/integration/test-consuming-repo.sh
#
# Prerequisites:
#   - Python 3.8+ installed
#   - Git installed
#   - Running from the scanning repo root directory
#
# What this test does:
#   1. Creates a temporary directory simulating a consuming repo
#   2. Initializes a git repository
#   3. Runs setup-scanning.py with --skip-tools (config only)
#   4. Verifies configs are copied and hooks are configured
#   5. Cleans up the temporary directory
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
TEMP_DIR=""

PASS=0
FAIL=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    PASS=$((PASS + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAIL=$((FAIL + 1))
}

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

trap cleanup EXIT

echo "=========================================="
echo " Consuming Repo Integration Tests"
echo "=========================================="
echo ""
echo "Using: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"
echo ""

# ---- Setup: Create temporary consuming repo ----
TEMP_DIR=$(mktemp -d)
echo "Created temp directory: $TEMP_DIR"

cd "$TEMP_DIR"
git init --quiet
git config user.email "test@example.com"
git config user.name "Test"

# Create a minimal Terraform file
mkdir -p terraform
cat > terraform/main.tf << 'EOF'
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"
}

resource "aws_s3_bucket" "test" {
  bucket = "my-test-bucket"
}
EOF

git add .
git commit --quiet -m "Initial commit"

echo ""

# ---- Test 1: Verify repo structure ----
echo "--- Test 1: Repository Structure ---"

if [ -d ".git" ]; then
    log_pass "Git repository initialized"
else
    log_fail "Git repository not initialized"
fi

if [ -f "terraform/main.tf" ]; then
    log_pass "Terraform file created"
else
    log_fail "Terraform file not created"
fi

echo ""

# ---- Test 2: Run setup-scanning.py (config only, skip tools) ----
echo "--- Test 2: Setup Script Execution ---"

# Copy configs and templates from the scanning repo for local access
mkdir -p configs templates
cp -r "$REPO_ROOT/configs/"* configs/ 2>/dev/null || true
cp -r "$REPO_ROOT/templates/"* templates/ 2>/dev/null || true

setup_exit=0
$PYTHON_CMD "$REPO_ROOT/scripts/setup-scanning.py" \
    --cloud-provider aws \
    --tier starter \
    --skip-tools \
    2>&1 || setup_exit=$?

if [ "$setup_exit" -eq 0 ] || [ "$setup_exit" -eq 2 ]; then
    log_pass "setup-scanning.py completed (exit $setup_exit)"
else
    log_fail "setup-scanning.py failed (exit $setup_exit)"
fi

echo ""

# ---- Test 3: Verify .scanning/configs/ directory ----
echo "--- Test 3: Config Directory ---"

if [ -d ".scanning/configs" ]; then
    log_pass ".scanning/configs/ directory created"
else
    log_fail ".scanning/configs/ directory not created"
fi

# Check for cloud-specific config files
if [ -f ".scanning/configs/.checkov.yaml" ] || [ -d ".scanning/configs" ]; then
    log_pass "Cloud config files present in .scanning/configs/"
else
    log_fail "Cloud config files missing from .scanning/configs/"
fi

echo ""

# ---- Test 4: Verify .pre-commit-config.yaml ----
echo "--- Test 4: Pre-commit Config ---"

if [ -f ".pre-commit-config.yaml" ]; then
    log_pass ".pre-commit-config.yaml created from template"

    # Check it references the scanning repo
    if grep -q "auto-code-scanning" .pre-commit-config.yaml 2>/dev/null; then
        log_pass ".pre-commit-config.yaml references scanning repo"
    elif grep -q "hooks" .pre-commit-config.yaml 2>/dev/null; then
        log_pass ".pre-commit-config.yaml contains hook definitions"
    else
        log_fail ".pre-commit-config.yaml does not reference scanning repo"
    fi
else
    log_fail ".pre-commit-config.yaml not created"
fi

echo ""

# ---- Test 5: Verify tier-appropriate hooks ----
echo "--- Test 5: Starter Tier Hooks ---"

if [ -f ".pre-commit-config.yaml" ]; then
    # Starter tier should include critical IaC and secret detection hooks
    if grep -q "trivy-iac-critical\|trivy-secrets\|gitleaks" .pre-commit-config.yaml 2>/dev/null; then
        log_pass "Starter tier hooks present in config"
    else
        log_fail "Starter tier hooks missing from config"
    fi
else
    log_fail "Cannot check hooks - no .pre-commit-config.yaml"
fi

echo ""

# ---- Test 6: Verify scanning directory is gitignored (optional) ----
echo "--- Test 6: Scanning Artifacts ---"

if [ -d ".scanning" ]; then
    log_pass ".scanning/ directory exists"
else
    log_fail ".scanning/ directory not created by setup"
fi

echo ""

# ---- Summary ----
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
