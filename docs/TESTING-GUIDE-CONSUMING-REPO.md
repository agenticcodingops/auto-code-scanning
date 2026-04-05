# Testing Guide: Security Scanning on Consuming Repositories

This guide walks through testing the `auto-code-scanning` solution on a real Terraform repository. It was validated against `azure-wordpress` (1,494 .tf files across 11 AWS module categories) on 2026-02-12.

## Prerequisites

| Requirement | Check Command | Minimum Version |
|------------|---------------|-----------------|
| Python | `python --version` | 3.8+ |
| Git | `git --version` | 2.0+ |
| pre-commit | `pre-commit --version` | 3.0+ |
| Trivy | `trivy --version` | 0.48.0+ |
| Checkov | `checkov --version` | 3.0.0+ |
| tflint | `tflint --version` | 0.50.0+ |
| Gitleaks | `gitleaks version` | 8.0+ |
| Snyk CLI (optional) | `snyk --version` | 1.0+ |

Install missing tools:

```bash
# macOS
brew install trivy tflint gitleaks
pip install pre-commit checkov
# Optional: Snyk CLI (requires license)
npm install -g snyk && snyk auth

# Windows (admin)
choco install trivy tflint gitleaks -y
pip install pre-commit checkov
# Optional: Snyk CLI (requires license)
npm install -g snyk
snyk auth

# Windows (no admin)
scoop install trivy tflint gitleaks
pip install pre-commit checkov
# Optional: Snyk CLI (requires license)
npm install -g snyk
snyk auth
```

---

## Test 1: Setup

### 1A. Create a test branch

```bash
cd "<your-terraform-repo>"
git checkout -b test/security-scanning-integration
```

### 1B. Backup existing pre-commit config

```bash
cp .pre-commit-config.yaml .pre-commit-config.yaml.backup
```

### 1C. Run the setup script

The `--force` flag overwrites any existing `.pre-commit-config.yaml` with the tier template. Without `--force`, the script preserves the existing config.

```bash
python "<path-to-scanning-repo>/scripts/setup-scanning.py" \
  --cloud-provider aws \
  --tier standard \
  --force
```

On Windows PowerShell:
```powershell
python "<path-to-scanning-repo>\scripts\setup-scanning.py" `
  --cloud-provider aws `
  --tier standard `
  --force
```
OR
```
python "C:\Projects\azure-wordpress\auto-code-scanning\scripts\setup-scanning.py" --cloud-provider aws --tier standard --force
```

### 1D. Verify setup

```bash
# Check configs were copied (use ls -la on Linux/Mac, dir on Windows)
ls -la .scanning/configs/

# Check .pre-commit-config.yaml references the scanning repo
cat .pre-commit-config.yaml

# Check hooks are installed
ls .git/hooks/pre-commit
```

### Expected Results

| Check | Expected |
|-------|----------|
| `.scanning/configs/` contents | `.checkov.yaml`, `.tflint.hcl`, `.tflint-aws.hcl` (or cloud variant), `.trivyignore`, `policy-overlay.yaml`, `noisy-checks-aws.yaml` (or cloud variant), `.scan-suppressions.yaml` |
| `.pre-commit-config.yaml` | References `auto-code-scanning` with `rev: v1.0.0` |
| `.git/hooks/pre-commit` | File exists |
| Setup exit code | 0 (all tools verified) |

### Actual Results (azure-wordpress)

**PASS** - All 10 config files copied, 5/5 tools verified (Trivy 0.68.2, Checkov 3.2.497, tflint 0.60.0, Gitleaks 8.30.0, pre-commit 4.5.1).

---

## Test 2: Pre-Commit Hook Execution

The **standard tier** includes these pre-commit hooks from the scanning repo:
- `trivy-secrets` - Secret detection in Terraform files
- `gitleaks` - Credential/secret leak detection
- `trivy-iac-critical` - CRITICAL-severity IaC misconfigurations only

Plus standard hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-json, detect-private-key, terraform_fmt, terraform_validate, terraform_tflint.

### 2A. Run specific security hooks on a single module

```bash
# CRITICAL-only Trivy scan
pre-commit run trivy-iac-critical --files terraform/modules/aws/storage/s3/*.tf

# Secret detection
pre-commit run trivy-secrets --files terraform/modules/aws/storage/s3/*.tf

# Gitleaks
pre-commit run gitleaks --files terraform/modules/aws/storage/s3/*.tf
```

### 2B. Run all pre-commit hooks on full repo (optional, slow)

```bash
# WARNING: This takes 4-5 minutes on a large repo (~1,500 files)
pre-commit run --all-files
```

### Expected Results

- Each hook reports findings with severity, file path, and rule ID
- Infrastructure errors (tool not found, DB issues) exit 0 with warning (fail-open)
- Security findings cause exit code 1 (fail-closed)

### Actual Results (azure-wordpress)

| Hook | Result | Duration | Details |
|------|--------|----------|---------|
| trivy-secrets | PASS | 22.7s | No secrets above threshold |
| gitleaks | FAIL (findings) | 61.3s | 1 HIGH finding (pre-existing leaked credential) |
| trivy-iac-critical | FAIL (findings) | 267s | 15 CRITICAL findings (pre-existing IaC issues) |

**Note:** The "FAIL" results above are the hooks **correctly detecting** pre-existing security issues in the consuming repo. This is expected behavior - the scanning solution is working as designed.

---

## Test 3: Pre-Push Hooks

**Important:** The **standard tier has no pre-push hooks**. Pre-push hooks (trivy-iac-full, checkov, checkov-strict, tflint, validate-suppressions) are only available in the **strict tier**.

The **snyk-iac** hook is available as an optional pre-push hook in both Standard and Strict tiers when uncommented and Snyk CLI is installed.

### To test pre-push hooks

Upgrade to strict tier first:

```bash
python "<path-to-scanning-repo>/scripts/setup-scanning.py" \
  --cloud-provider aws \
  --tier strict \
  --force
```

Then run pre-push hooks:

```bash
pre-commit run checkov --all-files --hook-stage pre-push
pre-commit run validate-suppressions --all-files --hook-stage pre-push

# Optional: Test Snyk IaC hook (requires Snyk CLI + auth)
pre-commit run snyk-iac --all-files --hook-stage pre-push
```

### Actual Results (azure-wordpress, strict tier)

| Hook | Result | Details |
|------|--------|---------|
| checkov | FAIL (findings) | 186 passed, 49 failed checks |
| validate-suppressions | PASS | 0 suppression entries, valid YAML |

---

## Test 4: Insecure Commit Block Test

This test verifies that hooks correctly block commits containing security issues.

### 4A. Create an intentionally insecure file

```bash
echo 'variable "aws_secret" { default = "AKIAIOSFODNN7EXAMPLE" }' > test-insecure.tf
```

### 4B. Stage and attempt to commit

```bash
git add test-insecure.tf
git commit -m "test: insecure commit"
```

### 4C. Expected: commit is BLOCKED

The `gitleaks` hook should detect the hardcoded AWS access key and block the commit.

### 4D. Clean up

```bash
git reset HEAD test-insecure.tf
rm test-insecure.tf
```

### Actual Results (azure-wordpress)

**PASS** - Gitleaks blocked the commit: `FAIL: 1 findings (0 critical, 1 high, 0 medium, 0 low)`. The fake AWS access key `AKIAIOSFODNN7EXAMPLE` was correctly detected and the commit was rejected.

---

## Test 5: scan.py Interface

`scan.py` is the programmatic scanning interface for automation and agent integration.

### 5A. Run scan.py with trivy

```bash
python "<path-to-scanning-repo>/scripts/scan.py" \
  --cloud-provider aws \
  --tools trivy \
  --format json \
  --output-file .scanning/last-scan.json \
  --severity CRITICAL,HIGH
```

### 5B. Run scan.py with checkov (single module recommended)

For large repos, scan a specific directory to avoid timeouts:

```bash
python "<path-to-scanning-repo>/scripts/scan.py" \
  terraform/modules/aws/storage/s3 \
  --cloud-provider aws \
  --tools checkov \
  --format json \
  --output-file .scanning/last-scan-checkov.json
```

### 5C. Run scan.py with all tools

```bash
python "<path-to-scanning-repo>/scripts/scan.py" \
  --cloud-provider aws \
  --tools trivy,checkov \
  --format json \
  --output-file .scanning/last-scan-all.json \
  --severity CRITICAL,HIGH
```

### 5D. Run scan.py with Snyk (optional)

If Snyk CLI is installed and authenticated:

```bash
python "<path-to-scanning-repo>/scripts/scan.py" \
  --cloud-provider aws \
  --tools trivy,checkov,snyk \
  --format json \
  --output-file .scanning/last-scan-all.json \
  --severity CRITICAL,HIGH
```

### 5E. Verify JSON output

```bash
cat .scanning/last-scan.json
```

### Expected Results

| Field | Expected |
|-------|----------|
| `schema_version` | `"1.0"` |
| `scan_id` | UUID string |
| `tools_executed` | Array of tools that ran |
| `summary.total_findings` | Number of findings |
| `summary.by_severity` | Breakdown by CRITICAL/HIGH/MEDIUM/LOW |
| `findings[]` | Array with `rule_id`, `tool`, `severity`, `file`, `message`, `line` |
| Exit code | 0 = no findings, 1 = findings above threshold |

### Actual Results (azure-wordpress)

| Test | Result | Details |
|------|--------|---------|
| scan.py + trivy | **PASS** | 92 findings (15 CRITICAL, 77 HIGH), 72.5s, `tools_executed: ["trivy"]` |
| scan.py + checkov (S3 module) | **PASS** | 170 passed, 21 failed, `tools_executed: ["checkov"]` |
| scan.py + checkov (full repo) | **PARTIAL** | Checkov invoked successfully but timed out at 300s on ~1,494 files. Use directory argument for large repos. |

---

## Test 6: Suppression Validation

### 6A. Validate the suppression file

The setup script copies a suppression template to `.scan-suppressions.yaml`.

```bash
python "<path-to-scanning-repo>/scripts/validate-suppressions.py"
```

### 6B. Add a test suppression (optional)

Edit `.scan-suppressions.yaml` to add an entry for a finding from Test 2 or Test 5:

```yaml
trivy_suppressions:
  - rule_id: AVD-AWS-0132        # Replace with actual rule_id
    tool: trivy
    severity: HIGH
    reason: "S3 CMK encryption managed at org level via AWS Config"
    file_pattern: "terraform/modules/aws/storage/s3/*.tf"
    owner: your-email@company.com
    approved_date: "2026-02-12"
    expires_date: "2026-08-12"
```

Then re-validate:

```bash
python "<path-to-scanning-repo>/scripts/validate-suppressions.py"
```

### Expected Results

- Empty suppression file: "Validation passed: .scan-suppressions.yaml (0 entries)"
- Valid entries: Passes with entry count
- Invalid entries: Clear error messages for missing/invalid fields
- Expired dates: Warnings (not errors) locally

### Actual Results (azure-wordpress)

**PASS** - "Validation passed: .scan-suppressions.yaml (0 entries)"

---

## Test 7: Checkov Direct Run

Verify checkov works with the copied config (no `no-guide` errors).

```bash
checkov -d terraform/modules/aws/storage/s3 \
  --config-file .scanning/configs/.checkov.yaml
```

### Expected Results

- Checkov runs without config parsing errors
- Reports passed/failed/skipped checks
- No "unrecognized arguments" or "no-guide" errors

### Actual Results (azure-wordpress)

**PASS** - 170 passed, 21 failed, 0 skipped, Checkov 3.2.497. No config errors.

---

## Test 8: Performance

### 8A. Time security hooks on full repo

```bash
time pre-commit run trivy-iac-critical --all-files
time pre-commit run trivy-secrets --all-files
```

### Performance Expectations

| Scope | Expected Time | Notes |
|-------|--------------|-------|
| Single module (~20 files) | 2-5 seconds | Normal commit workflow |
| Full repo `--all-files` (~1,500 files) | 3-5 minutes | First-time scan or CI only |
| Changed files only (typical commit) | 5-30 seconds | Default pre-commit behavior |

**Important:** During normal git commits, pre-commit only scans **changed files**, not the entire repo. The `--all-files` flag is for initial validation only.

### Actual Results (azure-wordpress, --all-files)

| Hook | Duration | Findings |
|------|----------|----------|
| trivy-iac-critical | 267s | 15 CRITICAL |
| trivy-secrets | 22.7s | 0 |
| gitleaks | 61.3s | 1 HIGH |

---

## Cleanup

After testing is complete:

```bash
# Restore original pre-commit config
cp .pre-commit-config.yaml.backup .pre-commit-config.yaml
pre-commit install

# Remove scanning artifacts
rm -rf .scanning/
rm -f .scan-suppressions.yaml
rm -f .pre-commit-config.yaml.backup

# Discard any formatting changes made by terraform_fmt
git checkout -- .

# Delete test branch
git checkout main
git branch -D test/security-scanning-integration
```

---

## Results Summary (azure-wordpress, 2026-02-12)

| # | Test | Result | Details |
|---|------|--------|---------|
| 1 | Setup | **PASS** | All 10 configs copied, 5/5 tools verified |
| 2 | Pre-commit hooks | **PASS** | trivy-secrets PASS, gitleaks detected 1 HIGH, trivy-iac-critical detected 15 CRITICAL |
| 3 | Pre-push hooks | **PASS** | Standard tier correctly has no pre-push hooks; strict tier: checkov 186/49 pass/fail |
| 4 | Insecure commit block | **PASS** | Gitleaks blocked fake AWS key `AKIAIOSFODNN7EXAMPLE` |
| 5 | scan.py | **PASS** | Trivy: 92 findings, Checkov: works on modules, JSON output valid |
| 6 | Suppression validation | **PASS** | Validated empty file and template correctly |
| 7 | Checkov direct | **PASS** | 170/21 pass/fail, no config errors |
| 8 | Performance | **PASS** | Full-repo times expected for 1,494 files; normal commits scan only changed files |

**Note**: Snyk IaC tests were not included in this validation run (Snyk is optional and requires a separate license). When enabled, Snyk findings appear alongside Trivy/Checkov results in the scan output.

### Top 5 Findings by Frequency (Trivy)

| Rule ID | Description | Count |
|---------|-------------|-------|
| AVD-AWS-0132 | S3 encryption should use Customer Managed Keys | 12 |
| AVD-AWS-0086 | S3 Access block should block public ACL | 8 |
| AVD-AWS-0088 | Unencrypted S3 bucket | 7 |
| AVD-AWS-0087 | S3 Access block should block public policy | 6 |
| AVD-AWS-0104 | Security group allows unrestricted egress | 5 |

### Known Issues / Notes

1. **Checkov timeout on large repos:** scan.py has a 300s timeout per tool. For repos with 1,000+ .tf files, pass a specific directory to scan.py instead of scanning the entire repo.

2. **terraform_fmt auto-fixes:** The standard tier includes `terraform_fmt` which auto-formats files. On a repo with many unformatted files, this generates many unstaged changes. Run `git checkout -- .` to discard or commit the fixes separately.

3. **Pre-existing findings block commits:** If the consuming repo has existing security issues, hooks will block commits that include affected files. Use the suppression workflow (`.scan-suppressions.yaml`) or the starter tier to reduce initial friction.

4. **Windows hidden files:** On Windows PowerShell, `ls` does not show dotfiles (`.checkov.yaml`, `.tflint.hcl`). Use `ls -Force` or Git Bash `ls -la` to verify config files.

---

## Troubleshooting

If any test fails, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.

Key things to check:
- Tool versions meet minimums (`trivy --version`, `checkov --version`)
- `.scanning/configs/` directory has the cloud-specific config files
- No stale Trivy DB locks (`trivy clean --all` to reset)
- Python 3.8+ is available (`python --version`)
- On Windows, restart shell after installing tools via pip (PATH refresh)
