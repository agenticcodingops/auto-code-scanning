# Automated Test Prompt for Consuming Repos

Copy and paste the prompt below into a new session opened in your **consuming Terraform repo** workspace directory (e.g., `azure-wordpress`).

## Prerequisites

Before running, ensure the scanning repo is cloned locally:
```
git clone https://github.com/agenticcodingops/auto-code-scanning "C:\Projects\azure-wordpress\auto-code-scanning"
```

Update the path in the prompt below if your scanning repo is in a different location.

---

## Prompt

```
I want you to test the auto-code-scanning solution on this repository. The scanning solution repo is located at "C:\Projects\azure-wordpress\auto-code-scanning" (tagged v1.0.0).

Work autonomously through ALL test steps below. Do NOT ask me questions -- just run each test, record the results, and move to the next. If a test fails, document the failure and continue. At the end, give me a summary table.

IMPORTANT: Create a test branch first. Do NOT modify the main branch. Clean up after all tests.

## Setup

1. Create branch `test/security-scanning-integration` from main
2. Backup `.pre-commit-config.yaml` to `.pre-commit-config.yaml.backup`

## Test 1: Setup Script

Run the setup script with `--force` to overwrite the existing pre-commit config:
```
python "C:\Projects\azure-wordpress\auto-code-scanning\scripts\setup-scanning.py" --cloud-provider aws --tier standard --force
```
Verify:
- Exit code is 0
- `.scanning/configs/` directory was created with config files (use `ls -la .scanning/configs/` in Git Bash)
- `.pre-commit-config.yaml` references `auto-code-scanning`
- Pre-commit hooks are installed (`.git/hooks/pre-commit` exists)

## Test 2: Pre-Commit Hooks (Single Module)

Run the three security hooks from the scanning repo against a single module:
```
pre-commit run trivy-iac-critical --files terraform/modules/aws/storage/s3/*.tf
pre-commit run trivy-secrets --files terraform/modules/aws/storage/s3/*.tf
pre-commit run gitleaks --files terraform/modules/aws/storage/s3/*.tf
```
Record: exit code, time taken, any findings reported. Standard tier only has pre-commit hooks (no pre-push hooks).

## Test 3: Insecure Commit Block Test

Create an intentionally insecure file to verify hooks block bad commits:
```
echo 'variable "aws_secret" { default = "AKIAIOSFODNN7EXAMPLE" }' > test-insecure.tf
git add test-insecure.tf
git commit -m "test: insecure commit"
```
Record: Did gitleaks block the commit? What findings were reported?

Then clean up:
```
git reset HEAD test-insecure.tf
rm test-insecure.tf
```

## Test 4: scan.py with Trivy

Run scan.py with trivy only:
```
python "C:\Projects\azure-wordpress\auto-code-scanning\scripts\scan.py" --cloud-provider aws --tools trivy --format json --output-file .scanning/last-scan.json --severity CRITICAL,HIGH
```
Verify: JSON output created, has `scan_id`, `tools_executed: ["trivy"]`, findings array with severity breakdown.

## Test 5: scan.py with Checkov (Single Module)

For large repos, scan a specific directory to avoid timeouts:
```
python "C:\Projects\azure-wordpress\auto-code-scanning\scripts\scan.py" terraform/modules/aws/storage/s3 --cloud-provider aws --tools checkov --format json --output-file .scanning/last-scan-checkov.json
```
Verify: checkov runs (not "command not found"), `tools_executed: ["checkov"]`, findings reported.

## Test 6: Suppression Validation

Validate the suppression file copied during setup:
```
python "C:\Projects\azure-wordpress\auto-code-scanning\scripts\validate-suppressions.py"
```
Record: exit code, validation message.

## Test 7: Checkov Direct Run

Verify checkov works with the config file (no parsing errors):
```
checkov -d terraform/modules/aws/storage/s3 --config-file .scanning/configs/.checkov.yaml 2>&1 | tail -15
```
Record: passed/failed/skipped counts, any config errors.

## Test 8: Performance

Time the trivy hook on all files:
```
time pre-commit run trivy-iac-critical --all-files
```
Record total time. Note: during normal commits, hooks only scan changed files (much faster). Full-repo scans of 1,000+ files take 3-5 minutes.

## Cleanup

After all tests:
```
cp .pre-commit-config.yaml.backup .pre-commit-config.yaml
pre-commit install
rm -rf .scanning/
rm -f .scan-suppressions.yaml .scan-results/ .pre-commit-config.yaml.backup
git checkout -- .
git checkout main
git branch -D test/security-scanning-integration
```

## Summary

Produce a summary table:

| Test | Status | Details |
|------|--------|---------|
| Test 1: Setup | PASS/FAIL | ... |
| Test 2: Pre-commit hooks | PASS/FAIL | ... |
| Test 3: Insecure commit blocked | PASS/FAIL | ... |
| Test 4: scan.py + trivy | PASS/FAIL | ... |
| Test 5: scan.py + checkov | PASS/FAIL | ... |
| Test 6: Suppressions | PASS/FAIL | ... |
| Test 7: Checkov direct | PASS/FAIL | ... |
| Test 8: Performance | PASS/FAIL | ... |

Also report:
- Total findings detected across all tests
- Top 5 most common rule_ids
- Any issues or bugs discovered
- Recommendations before team rollout
```

---

## How to Use

1. Open a new terminal session in your Terraform repo directory
2. Paste the prompt above into your coding assistant
3. Let the agent run autonomously through all 8 tests
4. Review the summary table and recommendations

The agent will:
- Create a test branch (no changes to main)
- Run all hooks and scripts against real Terraform code
- Test that insecure commits are blocked
- Verify scan.py and checkov work correctly
- Profile performance on the full repo
- Clean up everything after testing
- Produce a detailed results summary

---

## Expected Results (azure-wordpress, 2026-02-12)

| # | Test | Result | Details |
|---|------|--------|---------|
| 1 | Setup | **PASS** | 10 configs copied, 5/5 tools verified |
| 2 | Pre-commit hooks | **PASS** | trivy-secrets PASS, gitleaks 1 HIGH, trivy-iac-critical 15 CRITICAL |
| 3 | Insecure commit blocked | **PASS** | Gitleaks blocked fake AWS key |
| 4 | scan.py + trivy | **PASS** | 92 findings (15 CRITICAL, 77 HIGH) |
| 5 | scan.py + checkov | **PASS** | 170 passed, 21 failed on S3 module |
| 6 | Suppressions | **PASS** | Valid YAML, 0 entries |
| 7 | Checkov direct | **PASS** | 170/21 pass/fail, no config errors |
| 8 | Performance | **PASS** | 267s for full repo (expected for 1,494 files) |
