# Contract: CLI Interface

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)
**Date**: 2026-02-10

## Overview

Defines the command-line interface contracts for all scripts in the `scripts/` directory. These scripts are invoked by developers, CI workflows, and AI agents.

## setup-scanning.py (Cross-Platform Setup)

### Invocation

```bash
python scripts/setup-scanning.py --cloud-provider <provider> [options]
```

### Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--cloud-provider` | string | Yes | — | `aws`, `azure`, or `gcp` |
| `--tier` | string | No | `starter` | `starter`, `standard`, or `strict` |
| `--skip-tools` | flag | No | — | Skip tool installation (config only) |
| `--verbose` | flag | No | — | Show detailed output |
| `--dry-run` | flag | No | — | Show what would be done without executing |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Setup completed successfully |
| `1` | Setup failed (missing dependency, permission error) |
| `2` | Partial setup (some tools installed, some failed) |

### Behavior

1. Detect OS (Windows → delegate to PowerShell, macOS → Homebrew, Linux → apt)
2. Install tools: Trivy, Checkov, tflint, Gitleaks, pre-commit
3. Verify tool versions meet minimums (see data-model.md)
4. Copy cloud-specific configs to `.scanning/configs/`
5. Copy tier template to `.pre-commit-config.yaml` (if not exists)
6. Run `pre-commit install`
7. Print summary with installed versions

### Partial Failure Recovery

If tool installation fails:
- Continue with remaining tools
- Print warning for each failed tool
- Exit code `2` (partial)
- Per-tool idempotent: re-running skips already-installed tools

### Output (stdout)

```
Setting up security scanning for AWS (starter tier)...
  [OK] Trivy v0.57.0 (>= 0.48.0)
  [OK] Checkov v3.2.1 (>= 3.0.0)
  [WARN] tflint installation failed - run manually: brew install tflint
  [OK] Gitleaks v8.18.0
  [OK] pre-commit v3.6.0 (>= 3.0.0)
  [OK] Configs copied to .scanning/configs/
  [OK] pre-commit hooks installed

Setup complete (4/5 tools). Run 'git commit' to test hooks.
```

## setup-scanning.ps1 (Windows Setup)

### Invocation

```powershell
.\scripts\setup-scanning.ps1 -CloudProvider <provider> [-Tier <tier>] [-SkipTools] [-Verbose]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `-CloudProvider` | string | Yes | — | `aws`, `azure`, or `gcp` |
| `-Tier` | string | No | `starter` | `starter`, `standard`, or `strict` |
| `-SkipTools` | switch | No | — | Skip tool installation |
| `-Verbose` | switch | No | — | Verbose output |

### Exit Codes

Same as `setup-scanning.py`.

## scan.py (AI Agent Scanning Interface)

### Invocation

```bash
python scripts/scan.py [options] [directory]
```

### Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `directory` | positional | No | `.` | Directory to scan |
| `--format` | string | No | `text` | `text` or `json` |
| `--severity` | string | No | `CRITICAL,HIGH` | Comma-separated severity filter |
| `--auto-fix` | flag | No | — | Apply Checkov `--fix` for fixable findings |
| `--output-file` | string | No | `.scanning/last-scan.json` | JSON output path |
| `--cloud-provider` | string | No | auto-detect | `aws`, `azure`, or `gcp` |
| `--tools` | string | No | `trivy,checkov` | Comma-separated tool list |
| `--skip-baseline` | flag | No | — | Ignore baseline filtering |
| `--skip-suppressions` | flag | No | — | Ignore suppression filtering |

**Design note (KC-007)**: `cloud-provider` is intentionally optional in scan.py (auto-detects from `.scanning/configs/` or Terraform provider blocks) but required in reusable-scan.yml (no auto-detection in CI; explicit is safer). This asymmetry is by design.

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No findings above threshold |
| `1` | Findings detected above threshold |
| `2` | Tool error (fail-open: findings may exist but couldn't be determined) |

### Output (--format text, stdout)

```
Scanning terraform/ with trivy, checkov...

Findings: 3 (1 CRITICAL, 2 HIGH, 0 MEDIUM, 0 LOW)
  CRITICAL: terraform/main.tf:42 - S3 bucket missing encryption (CKV_AWS_19) [checkov]
  HIGH:     terraform/main.tf:58 - Security group allows 0.0.0.0/0 (AVD-AWS-0107) [trivy]
  HIGH:     terraform/vpc.tf:12 - VPC flow logs disabled (CKV_AWS_23) [checkov]

Auto-fix: 1 finding fixed (CKV_AWS_19)
Remaining: 2 findings require manual remediation

Results written to .scanning/last-scan.json
```

### Output (--format json, stdout)

Outputs the Agent Report JSON conforming to `schemas/last-scan.schema.json`. See data-model.md for schema.

### Auto-Fix Behavior

When `--auto-fix` is specified:
1. Run Checkov with `--fix` flag
2. Checkov modifies Terraform files in-place for fixable checks
3. Report which findings were fixed vs. unfixable
4. Re-scan to verify fixes (optional, controlled by `--verify-fix` flag)

## validate-suppressions.py (Suppression Validation)

### Invocation

```bash
python scripts/validate-suppressions.py [options] [file]
```

or as pre-commit hook:
```bash
python hooks/validate-suppressions.py
```

### Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `file` | positional | No | `.scan-suppressions.yaml` | Suppression file path |
| `--strict` | flag | No | — | Treat warnings as errors |
| `--check-expiry` | flag | No | — | Warn on suppressions expiring within 30 days |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All suppressions valid |
| `1` | Validation errors found |

### Validation Rules

1. YAML syntax valid (parseable by PyYAML)
2. All required fields present per suppression entry
3. `expires_date` is valid ISO date and ≤ `max_expiry_days` from `approved_date`
4. `approved_by` present when severity in `require_security_approval` list
5. `rule_id` format matches expected pattern for declared tool
6. No duplicate `(rule_id, tool)` pairs

**Note**: Validation is syntax-only. No cross-reference to actual scan findings.

### Expiry Behavior

| Context | Expired Suppression |
|---------|-------------------|
| Pre-commit hook | Warning only (allow commit) |
| CI workflow | Error (fail workflow) |

## create-baseline.ps1 (Baseline Management)

### Invocation

```powershell
.\scripts\create-baseline.ps1 [-ScanResultsPath <path>] [-OutputDir <path>] [-CloudProvider <string>]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `-ScanResultsPath` | string | No | `.scan-results/` | Input scan results |
| `-OutputDir` | string | No | `.scan-baseline/` | Output baseline directory |
| `-CloudProvider` | string | No | auto-detect | Cloud provider for scoping |
| `-MonorepoScope` | string | No | — | Scope baseline to specific subdirectory |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Baseline created/updated |
| `1` | Error (no scan results, invalid format) |

### Output

Creates/overwrites `.scan-baseline/baseline.json` conforming to Baseline entity schema (see data-model.md).

## aggregate-scan-results.ps1 (Result Aggregation)

### Invocation

```powershell
.\scripts\aggregate-scan-results.ps1 [-RunScans] [-InputDir <path>] [-OutputFile <path>]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `-RunScans` | switch | No | — | Run scans before aggregating |
| `-InputDir` | string | No | `.scan-results/` | Input directory |
| `-OutputFile` | string | No | `.scan-results/unified-results.json` | Output file |

### Cross-Tool Deduplication

When the same finding is detected by multiple tools:
1. Match on `(file, resource, category)` tuple
2. Merge into single finding with `detected_by: ["trivy", "checkov"]`
3. Use highest severity across tools
4. Keep most detailed remediation text

### Output

JSON conforming to `schemas/unified-results.schema.json`. See data-model.md for schema.

## collect-scan-metrics.ps1 (Metrics Collection)

### Invocation

```powershell
.\scripts\collect-scan-metrics.ps1 [-ScanResultsPath <path>] [-OutputDir <path>] [-UploadArtifact]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `-ScanResultsPath` | string | No | `.scan-results/` | Scan results path |
| `-OutputDir` | string | No | `.scan-results/metrics/` | Metrics output |
| `-UploadArtifact` | switch | No | — | Upload as GitHub Actions artifact |

### Output

JSON conforming to Metric entity schema (see data-model.md).
