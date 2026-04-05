# AI Agent Integration Guide

How to integrate automated agents with the security scanning solution using `scan.py`.

## Overview

The scanning solution provides two integration paths:

1. **Pre-commit hooks**: Run automatically on `git commit` / `git push` (developer workflow)
2. **scan.py**: Programmatic scanning interface for automated agents (agent workflow)

Both paths produce the same JSON output format, enabling consistent tooling.

## scan.py Usage

### Basic Scanning

```bash
# Scan current directory with default settings
python scripts/scan.py

# Scan a specific directory
python scripts/scan.py terraform/

# JSON output for programmatic consumption
python scripts/scan.py --format json

# Filter by severity
python scripts/scan.py --severity CRITICAL,HIGH

# Specify cloud provider (auto-detected by default)
python scripts/scan.py --cloud-provider aws
```

### Auto-Fix Workflow

```bash
# Scan and apply Checkov auto-fixes
python scripts/scan.py --auto-fix

# Scan with auto-fix, output JSON for agent consumption
python scripts/scan.py --auto-fix --format json
```

When `--auto-fix` is specified:
1. Checkov runs with the `--fix` flag
2. Fixable findings are remediated in-place (Terraform files modified)
3. The report indicates which findings were fixed vs. unfixable
4. The agent can then commit the fixes and re-scan

### All Options

| Argument | Default | Description |
|----------|---------|-------------|
| `directory` | `.` | Directory to scan (positional) |
| `--format` | `text` | Output format: `text` or `json` |
| `--severity` | `CRITICAL,HIGH` | Comma-separated severity filter |
| `--auto-fix` | off | Apply Checkov `--fix` for fixable findings |
| `--output-file` | `.scanning/last-scan.json` | JSON output file path |
| `--cloud-provider` | auto-detect | `aws`, `azure`, or `gcp` |
| `--tools` | `trivy,checkov` | Comma-separated list of tools to run |
| `--skip-baseline` | off | Ignore baseline filtering |
| `--skip-suppressions` | off | Ignore suppression filtering |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No findings above threshold |
| `1` | Findings detected above threshold |
| `2` | Tool error (fail-open: couldn't determine findings) |

## JSON Output Format

scan.py writes results to `.scanning/last-scan.json` (configurable via `--output-file`). The schema is defined in `schemas/last-scan.schema.json`.

### Example Output

```json
{
  "scan_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "scan_timestamp": "2026-02-10T14:30:00Z",
  "directory": "terraform/",
  "cloud_provider": "aws",
  "tools_executed": ["trivy", "checkov"],
  "severity_filter": ["CRITICAL", "HIGH"],
  "duration_ms": 4523,
  "summary": {
    "total_findings": 3,
    "by_severity": {
      "CRITICAL": 1,
      "HIGH": 2,
      "MEDIUM": 0,
      "LOW": 0
    },
    "suppressed": 0,
    "baselined": 1,
    "auto_fix_applied": true,
    "auto_fix_count": 1
  },
  "findings": [
    {
      "id": "f1a2b3c4-d5e6-7890-abcd-ef1234567890",
      "tool": "checkov",
      "rule_id": "CKV_AWS_19",
      "severity": "CRITICAL",
      "original_severity": "CRITICAL",
      "title": "S3 bucket missing encryption",
      "file": "terraform/main.tf",
      "line": 42,
      "resource": "aws_s3_bucket.data",
      "remediation": "Add server_side_encryption_configuration block",
      "remediation_url": "https://docs.checkov.io/docs/CKV_AWS_19",
      "suppressed": false,
      "baseline": false,
      "fixable": true,
      "fixed": true,
      "detected_by": ["checkov"]
    },
    {
      "id": "a9b8c7d6-e5f4-3210-abcd-ef0987654321",
      "tool": "trivy",
      "rule_id": "AVD-AWS-0107",
      "severity": "HIGH",
      "original_severity": "HIGH",
      "title": "Security group allows unrestricted ingress",
      "file": "terraform/main.tf",
      "line": 58,
      "resource": "aws_security_group.web",
      "remediation": "Restrict ingress CIDR blocks",
      "suppressed": false,
      "baseline": false,
      "fixable": false,
      "fixed": false,
      "detected_by": ["trivy"]
    }
  ]
}
```

### Key Fields for Agents

| Field | Usage |
|-------|-------|
| `summary.total_findings` | Quick pass/fail check |
| `summary.auto_fix_count` | Number of findings automatically remediated |
| `findings[].fixable` | Whether the agent can auto-fix this finding |
| `findings[].fixed` | Whether auto-fix was already applied |
| `findings[].file` + `findings[].line` | Exact location for manual remediation |
| `findings[].remediation` | Human-readable fix guidance |
| `findings[].remediation_url` | Link to detailed documentation |
| `findings[].rule_id` | Stable identifier for suppression or baseline |

## Typical Agent Workflow

### 1. Initial Scan

```bash
python scripts/scan.py --format json --severity CRITICAL,HIGH
```

### 2. Read Results

Parse `.scanning/last-scan.json` and categorize findings:
- **Fixable**: `fixable == true` -- can be auto-remediated
- **Unfixable**: `fixable == false` -- requires manual intervention or suppression

### 3. Auto-Fix

```bash
python scripts/scan.py --auto-fix --format json
```

Review `fixed` field in each finding to confirm remediation.

### 4. Verify Fixes

```bash
python scripts/scan.py --format json --severity CRITICAL,HIGH
```

Confirm `summary.total_findings` decreased after fixes.

### 5. Handle Remaining Findings

For unfixable findings, the agent can:
- Add entries to `.scan-suppressions.yaml` (with business justification)
- Create baseline entries via `scripts/create-baseline.ps1`
- Flag for human review

## Cloud Provider Auto-Detection

When `--cloud-provider` is not specified, scan.py auto-detects the provider by:
1. Checking `.scanning/configs/` for provider-specific files
2. Scanning Terraform provider blocks in `.tf` files

This is intentional for local/agent use. In CI (reusable-scan.yml), the cloud provider is always required explicitly for deterministic behavior.

## Integration with Pre-Commit Hooks

scan.py and pre-commit hooks share the same `.scanning/last-scan.json` output path. The last writer wins. This means:

- After a `git commit`, `.scanning/last-scan.json` contains results from the last pre-commit hook that ran
- After running `python scripts/scan.py`, it contains scan.py results

Agents should run scan.py directly rather than relying on hook output for comprehensive results.

## Suppression and Baseline Filtering

By default, scan.py applies both suppression and baseline filtering:

- **Suppressions**: Findings matching entries in `.scan-suppressions.yaml` are marked `suppressed: true` and excluded from the total count
- **Baselines**: Findings matching entries in `.scan-baseline/baseline.json` are marked `baseline: true` and excluded from the total count

Use `--skip-suppressions` and `--skip-baseline` to see all raw findings regardless of governance state.
