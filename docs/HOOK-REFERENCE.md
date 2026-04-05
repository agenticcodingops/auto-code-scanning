# Hook Reference

Complete reference for all 9 hooks provided by auto-code-scanning.

## Architecture

All hooks use a dual-wrapper architecture:
1. `.pre-commit-hooks.yaml` defines hook entries with `language: script`
2. Each hook entry calls `hooks/dispatcher.sh <hook-id>`
3. The dispatcher detects the OS and routes to the appropriate implementation:
   - Unix/macOS: `hooks/<hook-id>.sh`
   - Windows (PowerShell available): `hooks/<hook-id>.ps1`
4. Shared functions are loaded from `hooks/lib/common.sh` (Bash) or `hooks/lib/common.ps1` (PowerShell)

## Exit Code Contract

All hooks follow the fail-open error handling model:

| Exit Code | Meaning | Behavior |
|-----------|---------|----------|
| `0` | No findings (pass) | Allow commit/push |
| `1` | Security findings detected | Block commit/push |
| `2+` | Infrastructure error (tool crash, DB lock, network issue) | Allow commit/push (fail-open) |

**Exit code 1** is reserved exclusively for actual security findings exceeding the configured severity threshold. Tool errors, network failures, and parse errors use exit code 2+ to avoid blocking developers on infrastructure issues.

## JSON Output

Every hook writes a JSON report to `.scanning/last-scan.json` (overwritten by each hook; last hook wins). The output conforms to `schemas/last-scan.schema.json`.

## Environment Variables

The dispatcher sets these environment variables for hook scripts:

| Variable | Value | Purpose |
|----------|-------|---------|
| `SCAN_HOOK_ID` | Hook ID string | Identifies current hook |
| `SCAN_VERBOSE` | `0` or `1` | Verbosity flag |
| `SCAN_CONFIG_DIR` | Path to `.scanning/configs/` | Config directory location |

## Available Hooks

### Pre-Commit Hooks

#### trivy-iac-critical

- **Purpose**: Quick scan for CRITICAL Terraform misconfigurations only
- **Stage**: pre-commit
- **Tool**: Trivy (IaC scanner mode)
- **Target**: <5 seconds
- **Severity filter**: CRITICAL only
- **Flags**: `--skip-check-update`, `--severity CRITICAL`, `--exit-code 1`, `--quiet`
- **Retry**: On Trivy DB lock error, waits 2 seconds and retries once
- **Monorepo**: Detects changed Terraform directories via `detect_changed_dirs()`

#### trivy-secrets

- **Purpose**: Detects hardcoded secrets, API keys, and credentials in files
- **Stage**: pre-commit
- **Tool**: Trivy (secret scanner mode)
- **Target**: <5 seconds
- **Flags**: `--scanners secret`, `--severity HIGH,CRITICAL`, `--exit-code 1`, `--quiet`
- **Retry**: Same DB lock retry as trivy-iac-critical

#### gitleaks

- **Purpose**: Detects leaked credentials and secrets using pattern matching
- **Stage**: pre-commit
- **Tool**: Gitleaks
- **Target**: <5 seconds
- **Note**: Complements trivy-secrets with different detection patterns

#### validate-suppressions

- **Purpose**: Validates `.scan-suppressions.yaml` format, fields, and expiration dates
- **Stage**: pre-commit
- **Tool**: Python (PyYAML)
- **Target**: <3 seconds
- **Implementation**: `hooks/validate-suppressions.py`
- **Validation rules**:
  - YAML syntax valid
  - All required fields present per entry
  - `expires_date` is valid ISO date and within 180-day maximum
  - `approved_by` present when severity is HIGH or CRITICAL
  - `rule_id` format matches expected pattern for declared tool (AVD-* for Trivy, CKV_* for Checkov)
  - No duplicate `(rule_id, tool)` pairs
- **Expiry behavior**: Expired suppressions produce warnings locally (allow commit); errors in CI (fail workflow)

### Pre-Push Hooks

#### trivy-iac-full

- **Purpose**: Full IaC scan across all severity levels
- **Stage**: pre-push
- **Tool**: Trivy (IaC scanner mode)
- **Target**: <30 seconds
- **Severity filter**: All (CRITICAL, HIGH, MEDIUM, LOW)
- **Flags**: `--skip-check-update`, `--exit-code 1`, `--quiet`
- **Retry**: Same DB lock retry as trivy-iac-critical
- **Monorepo**: Same `detect_changed_dirs()` support

#### checkov

- **Purpose**: Policy-as-code checks against CIS Benchmarks and best practices
- **Stage**: pre-push
- **Tool**: Checkov
- **Target**: <30 seconds
- **Config**: Uses `.scanning/configs/.checkov.yaml` (blocklist approach -- all checks enabled, config lists exclusions)
- **Flags**: `--config-file .scanning/configs/.checkov.yaml`, `--framework terraform`, `--quiet`, `--compact`

#### checkov-strict

- **Purpose**: Strict mode Checkov -- hard-fails on CRITICAL and HIGH findings
- **Stage**: pre-push
- **Tool**: Checkov
- **Target**: <30 seconds
- **Config**: Same as `checkov` plus `--hard-fail-on CRITICAL,HIGH`
- **Used in**: Strict tier only

#### tflint

- **Purpose**: Terraform-specific linting (provider-aware rules, deprecated syntax, naming)
- **Stage**: pre-push
- **Tool**: tflint
- **Target**: <15 seconds
- **Config**: Uses `.scanning/configs/.tflint.hcl` (cloud-specific ruleset and rules)
- **Monorepo**: Runs per detected Terraform directory

#### snyk-iac (Optional)

| Property | Value |
|----------|-------|
| **Purpose** | Snyk IaC scan for Terraform misconfigurations |
| **Stage** | `pre-push` |
| **Tool** | Snyk CLI (`snyk iac test`) |
| **Severity** | All (CRITICAL, HIGH, MEDIUM, LOW) |
| **Prerequisites** | Snyk CLI (`npm install -g snyk`), authenticated (`snyk auth` or `SNYK_TOKEN`) |
| **Policy file** | `.snyk` in repo root (Snyk convention) |
| **Optional** | Yes — fail-open if not installed or not authenticated |

This hook is **optional**. It is included as a commented-out entry in standard and strict tier templates. Projects without a Snyk license can safely ignore it. When Snyk CLI is not installed or not authenticated, the hook exits 0 with a warning message and does not block the push.

**Authentication check order**:
1. Check `SNYK_TOKEN` environment variable (zero subprocess overhead)
2. Fall back to `snyk whoami` (checks keychain/config)
3. If neither succeeds: warn and exit 0 (fail-open)

## Performance Targets

| Stage | Max Per Hook | Max Total |
|-------|-------------|-----------|
| pre-commit | 5 seconds | 10 seconds |
| pre-push | 30 seconds | 60 seconds |
| pre-push (snyk-iac) | 30 seconds | (included in pre-push total) |

Measured on CI runner (`ubuntu-latest`). Local times may vary.

## Overriding Hook Configuration

Consuming repos can override any hook's args, stages, or files in their `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v1.0.0
    hooks:
      - id: trivy-iac-critical
        stages: [pre-push]          # Override: move to pre-push
        args: ["--severity", "HIGH"] # Override: change severity
      - id: checkov
        exclude: 'legacy/.*'        # Override: skip legacy directory
```

All fields in the consuming repo's config override the manifest defaults.

## Config Resolution Order

Hooks resolve configuration files in this priority:

1. `.scanning/configs/{file}` (consuming repo's downloaded configs)
2. Explicit `--config-file` argument (if provided via `args:` override)
3. Tool defaults (fallback)

## Stdout Output Format

All hooks produce human-readable output:

**Pass**:
```
[trivy-iac-critical] Scanning... (12 files in 3 directories)
[trivy-iac-critical] PASS: No findings above threshold
```

**Fail**:
```
[trivy-iac-critical] Scanning... (12 files in 3 directories)
[trivy-iac-critical] FAIL: 2 findings (2 critical, 0 high, 0 medium, 0 low)
```

**Infrastructure error (fail-open)**:
```
[trivy-iac-critical] WARNING: Tool error (exit code 127) - allowing commit (fail-open)
```
