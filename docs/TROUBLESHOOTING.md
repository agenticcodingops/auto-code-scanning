# Troubleshooting Guide

Common issues and their resolutions for the Terraform security scanning solution.

## Issue 1: Hook Timeout

**Symptom**: Pre-commit hook hangs or takes longer than 5 seconds.

**Causes and Fixes**:

- **Trivy database download**: Hooks run with `--skip-check-update` (IaC scanning) to avoid downloading check bundles on every run, but the first run after installation requires an initial database. Run `trivy image --download-db-only` once to initialize.
- **Large repository**: If scanning many directories, use the `exclude` pattern in `.pre-commit-config.yaml` to limit scan scope to Terraform directories only.
- **Network issues**: Trivy and Checkov may attempt external connections. Ensure `--skip-check-update` (for `trivy config`) and `download-external-modules: false` (for Checkov) are set.

```bash
# Verify hook timing
.\scripts\profile-hook-performance.ps1 -Iterations 3
```

## Issue 2: Trivy Database Lock

**Symptom**: Error message containing "database locked" or "faiss database is locked".

**Causes and Fixes**:

- **Concurrent Trivy runs**: Multiple hooks or parallel processes accessing the Trivy DB simultaneously. The hook wrapper automatically retries once after a 2-second wait.
- **Stale lock file**: If a previous Trivy process crashed, the lock file may persist.

```bash
# Clear Trivy cache
trivy clean --all

# Re-download database
trivy image --download-db-only
```

## Issue 3: Tool Not Found

**Symptom**: Hook fails with "command not found" for trivy, checkov, tflint, or gitleaks.

**Causes and Fixes**:

- **Not installed**: Run the setup script to install all tools.
- **Not in PATH**: Ensure tool installation directories are in your system PATH.
- **Version too old**: Minimum versions: trivy>=0.48.0, checkov>=3.0.0, tflint>=0.50.0, pre-commit>=3.0.0.

```bash
# Windows (admin)
.\scripts\setup-scanning.ps1 -CloudProvider aws

# Windows (no admin)
.\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws

# Cross-platform
python scripts/setup-scanning.py --cloud-provider aws

# Verify installations
trivy --version
checkov --version
tflint --version
gitleaks version
pre-commit --version
```

## Issue 4: Config Not Copied

**Symptom**: Hooks fail with "config file not found" or scans run without provider-specific rules.

**Causes and Fixes**:

- **Setup not run**: Run `setup-scanning.ps1 -CloudProvider <provider>` to copy configs to `.scanning/configs/`.
- **Pre-commit cache not populated**: Ensure `pre-commit install` completed successfully before config copy.
- **Wrong provider**: Verify the correct cloud provider was specified during setup.

```bash
# Verify configs exist
ls .scanning/configs/

# Re-run setup to copy configs
.\scripts\setup-scanning.ps1 -CloudProvider aws

# Manual config copy from pre-commit cache
pre-commit run --all-files  # This triggers cache population
```

## Issue 5: Permission Denied

**Symptom**: Script or hook fails with "access denied" or "permission denied".

**Causes and Fixes**:

- **Windows execution policy**: Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
- **Git hook not executable**: Run `chmod +x .git/hooks/pre-commit` (Unix) or ensure Git is configured to run hooks.
- **Admin required**: Use `setup-scanning-no-admin.ps1` for Scoop/pip-based installation without elevation.

```powershell
# Check execution policy
Get-ExecutionPolicy -List

# Set for current user (no admin needed)
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Issue 6: Python Version Mismatch

**Symptom**: `ModuleNotFoundError`, `SyntaxError`, or "Python 3.8+ required" errors.

**Causes and Fixes**:

- **Python 2 default**: Ensure `python` or `python3` resolves to Python 3.8+.
- **Missing PyYAML**: Install with `pip install pyyaml`.
- **Virtual environment**: If using venv, ensure it's activated before running hooks.

```bash
# Check Python version
python --version
python3 --version

# Install required packages
pip install pyyaml pre-commit checkov
```

## Issue 7: Pre-commit Not Installed

**Symptom**: `git commit` runs without any hooks, or "pre-commit: command not found".

**Causes and Fixes**:

- **Not installed system-wide**: Install with `pip install pre-commit`.
- **Hooks not activated**: Run `pre-commit install` and `pre-commit install --hook-type pre-push`.
- **Wrong git directory**: Ensure you're in the repository root when installing hooks.

```bash
# Install pre-commit
pip install pre-commit

# Activate hooks
pre-commit install
pre-commit install --hook-type pre-push

# Verify hooks are installed
ls .git/hooks/pre-commit
pre-commit run --all-files  # Test all hooks
```

## Issue 8: SARIF Upload Fails

**Symptom**: GitHub Actions workflow fails at SARIF upload step with permission errors.

**Causes and Fixes**:

- **Missing permission**: The workflow requires `security-events: write` permission. If your repository doesn't grant this, set `upload-sarif: false` in the workflow input.
- **SARIF too large**: GitHub limits SARIF to 25MB or 5000 results. The workflow automatically truncates, but very large codebases may exceed limits.

```yaml
# In your workflow file, disable SARIF upload
uses: ./.github/workflows/reusable-scan.yml
with:
  cloud-provider: aws
  upload-sarif: false  # Disable if permissions not available
```

## Issue 9: Suppression Validation Errors

**Symptom**: `validate-suppressions` hook fails with field validation errors.

**Causes and Fixes**:

- **Missing required field**: Ensure every suppression entry has `rule_id`, `tool`, `reason`, `owner`, `approved_date`, and `expires_date`.
- **Invalid date format**: Dates must be ISO 8601 format: `YYYY-MM-DD`.
- **Missing approval**: HIGH/CRITICAL suppressions require the `approved_by` field.
- **Expiry too far**: `expires_date` must be within 180 days of `approved_date`.
- **Wrong rule_id format**: Trivy rules start with `AVD-`, Checkov rules with `CKV_`.

```bash
# Validate suppression file
python scripts/validate-suppressions.py .scan-suppressions.yaml

# Validate with strict mode (warnings become errors)
python scripts/validate-suppressions.py --strict .scan-suppressions.yaml
```

## Issue 10: Hooks Not Running on Push

**Symptom**: Pre-push hooks (trivy-iac-full, checkov, tflint) don't execute on `git push`.

**Causes and Fixes**:

- **Pre-push hook not installed**: Run `pre-commit install --hook-type pre-push`.
- **Wrong stage in config**: Verify the hook's `stages` field is set to `pre-push` in your `.pre-commit-config.yaml`.
- **Standard tier**: If using the starter template, pre-push hooks are not included. Upgrade to standard or strict tier.

```bash
# Install pre-push hooks
pre-commit install --hook-type pre-push

# Verify pre-push hook exists
ls .git/hooks/pre-push

# Test pre-push hooks manually
pre-commit run --hook-stage pre-push --all-files
```

## Getting Additional Help

If your issue is not listed above:

1. Run with verbose output: `SCAN_VERBOSE=1 pre-commit run --all-files`
2. Check pre-commit logs: `~/.cache/pre-commit/pre-commit.log`
3. Run the performance profiler: `.\scripts\profile-hook-performance.ps1`
4. Generate a suppression report: `.\scripts\generate-suppression-report.ps1`
5. Consult the [Hook Reference](HOOK-REFERENCE.md) for detailed hook behavior
6. Review the [Setup Guide](SETUP-GUIDE.md) for installation steps
