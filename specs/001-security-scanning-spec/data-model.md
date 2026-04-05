# Data Model: Reusable Terraform Security Scanning Solution

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Date**: 2026-02-10

## Overview

This system uses file-based data storage exclusively — no databases. All entities are represented as YAML or JSON files stored in the repository or consuming repository's `.scanning/` directory. Relationships are implicit (file co-location, naming conventions, and reference by ID).

## Entity Diagram

```
┌─────────────────────┐     references      ┌──────────────────────┐
│   Hook              │─────────────────────▶│   Cloud Config       │
│ (.pre-commit-hooks  │                      │ (configs/{provider}/)│
│  .yaml)             │                      │                      │
└─────────┬───────────┘                      └──────────┬───────────┘
          │ produces                                    │ layered with
          ▼                                             ▼
┌─────────────────────┐     conforms to      ┌──────────────────────┐
│   Unified Result    │─────────────────────▶│   JSON Schema        │
│ (.scan-results/)    │                      │ (schemas/)           │
└─────────┬───────────┘                      └──────────────────────┘
          │ filtered by                               ▲
          ▼                                           │ conforms to
┌─────────────────────┐                      ┌──────────────────────┐
│   Suppression       │                      │   Agent Report       │
│ (.scan-suppressions │                      │ (.scanning/          │
│  .yaml)             │                      │  last-scan.json)     │
└─────────────────────┘                      └──────────────────────┘
          │ interacts with                            ▲
          ▼                                           │ produces
┌─────────────────────┐                      ┌──────────────────────┐
│   Baseline          │                      │   scan.py            │
│ (.scan-baseline/)   │                      │ (scripts/)           │
└─────────────────────┘                      └──────────────────────┘

┌─────────────────────┐     generated from   ┌──────────────────────┐
│   Adoption Tier     │─────────────────────▶│   Template           │
│ (consuming repo     │                      │ (templates/          │
│  .pre-commit-config │                      │  {starter,standard,  │
│  .yaml)             │                      │   strict}/)          │
└─────────────────────┘                      └──────────────────────┘

┌─────────────────────┐     uploaded to      ┌──────────────────────┐
│   Metric            │─────────────────────▶│   GitHub Actions     │
│ (.scan-results/     │                      │   Artifacts          │
│  metrics/)          │                      │                      │
└─────────────────────┘                      └──────────────────────┘

┌─────────────────────┐     scoped by        ┌──────────────────────┐
│   Scanning Dir      │─────────────────────▶│   Scan Config        │
│ (.scanning/)        │                      │ (.scan-config.yaml)  │
└─────────────────────┘                      └──────────────────────┘

┌─────────────────────┐
│   Policy Overlay    │
│ (configs/{provider}/│
│  policy-overlay     │
│  .yaml)             │
└─────────────────────┘
```

## Entity Definitions

### 1. Hook

**Location**: `.pre-commit-hooks.yaml` (this repo)
**Format**: YAML (pre-commit framework schema)

```yaml
# Schema per hook entry
id: string              # Unique hook ID (e.g., "trivy-iac-critical")
name: string            # Human-readable name
entry: string           # Entry command (e.g., "hooks/dispatcher.sh trivy-iac-critical")
language: string        # "script" (uses dispatcher)
files: string           # File pattern (empty string = all files)
exclude: string         # Directory exclusion regex
types: [string]         # File type filters (e.g., ["file"])
stages: [string]        # pre-commit | pre-push
pass_filenames: boolean # false (hooks scan directories, not individual files)
verbose: boolean        # true (show output on success)
```

**Hooks defined** (8 total):

| ID | Stage | Severity Filter | Tool |
|----|-------|----------------|------|
| `trivy-iac-critical` | pre-commit | CRITICAL only | Trivy |
| `trivy-iac-full` | pre-push | All severities | Trivy |
| `trivy-secrets` | pre-commit | N/A (binary) | Trivy (secret mode) |
| `checkov` | pre-push | Per config | Checkov |
| `checkov-strict` | pre-push | CRITICAL + HIGH fail | Checkov |
| `validate-suppressions` | pre-commit | N/A (syntax check) | Python/PyYAML |
| `tflint` | pre-push | Per config | tflint |
| `gitleaks` | pre-commit | N/A (binary) | Gitleaks |

### 2. Cloud Config

**Location**: `configs/{aws,azure,gcp}/` (this repo) → copied to `.scanning/configs/` (consuming repo)
**Format**: Tool-specific (YAML for Checkov, HCL for tflint)

**Per-provider files**:

| File | Tool | Format | Key Fields |
|------|------|--------|------------|
| `.checkov.yaml` | Checkov | YAML | `skip-check`, `skip-path`, `framework`, `output` |
| `.tflint.hcl` | tflint | HCL | `plugin`, `rule`, `config` |
| `policy-overlay.yaml` | Custom | YAML | `tagging_rules`, `naming_conventions` |

**Checkov config (blocklist approach)**:
```yaml
# No `check:` section — all checks run by default
skip-download: true
no-guide: true
framework: [terraform]
output: [cli, json]
output-file-path: .scan-results
deep-analysis: true
download-external-modules: false
evaluate-variables: true

skip-check:
  - CKV_AWS_XXX   # Justification for each skipped check

skip-path:
  - .terraform
  - .git
  - .scan-results
```

### 3. Adoption Tier (Template)

**Location**: `templates/{starter,standard,strict}/pre-commit-config.yaml` (this repo)
**Format**: YAML (pre-commit config schema)

**Tier composition**:

**Note**: This table lists only hooks defined in this repository's `.pre-commit-hooks.yaml`. Templates also include third-party hooks from `pre-commit/pre-commit-hooks` and `antonbabenko/pre-commit-terraform` (e.g., trailing-whitespace, end-of-file-fixer, check-yaml, detect-private-key, terraform_fmt, terraform_validate, terraform_tflint, terraform_docs). See spec.md FR-047 through FR-049 for the complete hook list per tier.

| Tier | Hooks Enabled | Stage Distribution |
|------|--------------|-------------------|
| Starter | `trivy-secrets` (+ 4 third-party) | All pre-commit |
| Standard | Starter + `gitleaks`, `trivy-iac-critical` (+ 2 third-party) | All pre-commit |
| Strict | Standard + `trivy-iac-full`, `checkov-strict`, `validate-suppressions` (+ 1 third-party) | Mixed pre-commit/pre-push |

```yaml
# Template structure (consumed by consuming repos)
repos:
  - repo: https://github.com/{org}/auto-code-scanning
    rev: v1.0.0     # Pinned to release tag
    hooks:
      - id: trivy-iac-critical
        # args: []   # Override point for consuming repos
      - id: trivy-secrets
      # ... tier-specific hooks
```

### 4. Suppression

**Location**: `configs/common/.scan-suppressions.yaml` (this repo, template) → `.scan-suppressions.yaml` (consuming repo)
**Format**: YAML

```yaml
schema_version: "1.0"

settings:
  max_expiry_days: 180              # integer, max days before expiry
  require_security_approval: [string]  # severity levels requiring approval
  review_frequency_days: 90         # integer, review cycle

trivy_suppressions:                 # array of Suppression entries
  - rule_id: string                 # REQUIRED: Tool-specific check ID
    tool: string                    # REQUIRED: "trivy" | "checkov" | "tflint"
    severity: string                # OPTIONAL: CRITICAL | HIGH | MEDIUM | LOW
    reason: string                  # REQUIRED: Business justification
    file_pattern: string            # OPTIONAL: Glob pattern for file scope
    owner: string                   # REQUIRED: Responsible party email
    approved_date: string           # REQUIRED: ISO date (YYYY-MM-DD)
    expires_date: string            # REQUIRED: ISO date (max 180 days from approved)
    approved_by: string             # OPTIONAL (required for HIGH/CRITICAL)
    ticket: string                  # OPTIONAL: JIRA/issue reference

checkov_suppressions: []            # Same schema as above
tflint_suppressions: []             # Same schema as above

suppression_history:                # Audit trail
  - rule_id: string
    tool: string
    removed_date: string
    removal_reason: string
    original_approved_date: string
```

**Validation rules** (enforced by `validate-suppressions.py`):
- All REQUIRED fields must be present
- `expires_date` must be ≤ `max_expiry_days` from `approved_date`
- `expires_date` must be a future date (CI: fail if expired; local hooks: warn)
- `approved_by` required when severity is in `require_security_approval` list
- `rule_id` format validated per tool (regex: `AVD-*` for Trivy, `CKV_*` for Checkov)

### 5. Baseline

**Location**: `.scan-baseline/` (consuming repo)
**Format**: JSON

```json
{
  "schema_version": "1.0",
  "created_date": "2026-02-10T12:00:00Z",
  "created_by": "create-baseline.ps1",
  "cloud_provider": "aws",
  "entries": [
    {
      "hash": "string",           // SHA-256 of (rule_id + file_path)
      "rule_id": "string",        // e.g., "AVD-AWS-0057"
      "file_path": "string",      // Relative path from repo root
      "tool": "string",           // Source tool
      "severity": "string",       // Severity at baseline time
      "baselined_date": "string"  // ISO date
    }
  ]
}
```

**Matching algorithm**: Hash lookup — `SHA-256(rule_id + "|" + file_path)`. O(1) per finding. Line numbers intentionally excluded for refactoring resilience.

### 6. Unified Result

**Location**: `.scan-results/` (consuming repo) | Schema: `schemas/unified-results.schema.json`
**Format**: JSON

```json
{
  "schema_version": "1.0",
  "scan_id": "string (UUID)",
  "scan_timestamp": "string (ISO 8601)",
  "duration_ms": 0,
  "scan_directory": "string",
  "tools_executed": ["trivy", "checkov"],
  "summary": {
    "total_findings": 0,
    "by_severity": {
      "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0
    },
    "by_tool": {
      "trivy": 0, "checkov": 0
    },
    "suppressed": 0,
    "baselined": 0
  },
  "findings": [
    {
      "id": "string (UUID)",
      "tool": "string (enum)",
      "rule_id": "string",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "original_severity": "string",
      "title": "string",
      "description": "string",
      "message": "string",
      "file": "string (relative path)",
      "line": 0,
      "resource": "string (Terraform resource address)",
      "remediation": "string",
      "remediation_url": "string (URI)",
      "url": "string (URI)",
      "suppressed": false,
      "suppression_reason": "string | null",
      "baseline": false,
      "detected_by": ["trivy", "checkov"]
    }
  ]
}
```

**Field notes**:
- `detected_by`: Array of tool names when cross-tool deduplication merges findings. Single-tool findings have a 1-element array.
- `suppressed` / `baseline`: Boolean flags set independently. A finding can be both suppressed AND baselined.
- `original_severity`: Tool's native severity before normalization mapping.
- `remediation_url`: Auto-generated for Checkov (`docs.checkov.io/docs/{CHECK_ID}`), tool docs URL for others.

### 7. Agent Report

**Location**: `.scanning/last-scan.json` (consuming repo) | Schema: `schemas/last-scan.schema.json`
**Format**: JSON (subset of Unified Result)

```json
{
  "schema_version": "1.0",
  "scan_id": "string (UUID)",
  "scan_timestamp": "string (ISO 8601)",
  "duration_ms": 0,
  "scan_directory": "string",
  "tools_executed": ["trivy", "checkov"],
  "auto_fix_applied": false,
  "auto_fix_count": 0,
  "summary": {
    "total_findings": 0,
    "by_severity": {
      "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0
    },
    "by_tool": {},
    "fixable": 0,
    "unfixable": 0
  },
  "findings": [
    {
      "rule_id": "string",
      "tool": "string",
      "severity": "string",
      "file": "string",
      "line": 0,
      "message": "string",
      "remediation_url": "string",
      "fixable": false,
      "fixed": false
    }
  ]
}
```

**Agent-specific fields**:
- `auto_fix_applied`: Whether `--auto-fix` was used
- `auto_fix_count`: Number of findings auto-remediated by Checkov `--fix`
- `fixable` / `unfixable`: Summary counts of Checkov-fixable vs. unfixable findings
- `fixed`: Per-finding flag indicating whether auto-fix was applied

### 8. Metric

**Location**: `.scan-results/metrics/` (consuming repo) → uploaded as GitHub Actions artifact
**Format**: JSON

```json
{
  "schema_version": "1.0",
  "timestamp": "string (ISO 8601)",
  "repository": "string",
  "branch": "string",
  "commit_sha": "string",
  "cloud_provider": "string",
  "adoption_tier": "starter | standard | strict",
  "hook_results": {
    "trivy-iac-critical": {
      "exit_code": 0,
      "duration_ms": 0,
      "findings_count": 0,
      "bypassed": false
    }
  },
  "aggregate": {
    "total_findings": 0,
    "by_severity": {},
    "bypass_rate": 0.0,
    "pass_rate": 0.0,
    "suppressed_count": 0,
    "baselined_count": 0
  }
}
```

### 9. Scan Config

**Location**: `.scan-config.yaml` (consuming repo, optional)
**Format**: YAML

```yaml
schema_version: "1.0"
cloud_provider: "aws"            # aws | azure | gcp

scan_directories:                 # Directories containing Terraform
  include:
    - "terraform/"
    - "infrastructure/"
  exclude:
    - "terraform/legacy/"
    - "terraform/experimental/"

options:
  incremental: true               # Only scan changed directories
  verbose: false                   # Extra debug output
```

### 10. Policy Overlay

**Location**: `configs/{provider}/policy-overlay.yaml` (this repo, template) → `.scanning/configs/policy-overlay.yaml` (consuming repo)
**Format**: YAML

```yaml
schema_version: "1.0"
organization: "string"

tagging_rules:
  required_tags:
    - "Environment"
    - "Owner"
    - "CostCenter"
  tag_format:
    Environment: "^(dev|staging|prod)$"

naming_conventions:
  resource_prefix: "string"
  enforce: true

custom_checks: []                 # Future: org-specific Checkov custom policies
```

**Design**: This file is explicitly designed to be replaced by consuming repos. The version in this repo serves as a documented template.

### 11. Scanning Directory

**Location**: `.scanning/` (consuming repo)
**Format**: Directory structure

```
.scanning/
├── configs/                # Copied from this repo during setup
│   ├── .checkov.yaml
│   ├── .tflint.hcl
│   └── policy-overlay.yaml
├── last-scan.json          # Agent report (overwritten each scan)
└── cache/                  # Hook-specific cache (gitignored)
```

**VCS policy**: Team choice — can be committed (reproducible configs) or gitignored (ephemeral). The setup script does not add `.scanning/` to `.gitignore` by default.

## Severity Normalization Mapping

All tools map to the unified 4-level severity scale:

| Tool | Source Value | Normalized |
|------|------------|------------|
| **Trivy** | CRITICAL | CRITICAL |
| | HIGH | HIGH |
| | MEDIUM | MEDIUM |
| | LOW | LOW |
| | UNKNOWN | LOW |
| **Checkov** | CRITICAL | CRITICAL |
| | HIGH | HIGH |
| | MEDIUM | MEDIUM |
| | LOW | LOW |
| **tflint** | error | HIGH |
| | warning | MEDIUM |
| | notice | LOW |
| **Gitleaks** | (all secrets) | HIGH |
| **PSScriptAnalyzer** | Error | HIGH |
| | Warning | MEDIUM |
| | Information | LOW |
| **ShellCheck** | error | HIGH |
| | warning | MEDIUM |
| | info | LOW |
| | style | LOW |
| **hadolint** | error | HIGH |
| | warning | MEDIUM |
| | info | LOW |
| | style | LOW |

## Cross-Tool Deduplication Rules

When multiple tools detect the same issue, findings are merged:

1. **Match key**: `(file, resource, category)` where category is a normalized grouping (e.g., "encryption", "public-access")
2. **Merge behavior**: Keep highest severity, merge `detected_by` arrays, keep most detailed `remediation`
3. **Identity**: Merged finding gets a new UUID; original tool-specific IDs preserved in `detected_by`

## File Location Summary

| Entity | This Repo | Consuming Repo |
|--------|-----------|----------------|
| Hook manifest | `.pre-commit-hooks.yaml` | N/A (referenced by URL) |
| Cloud configs | `configs/{provider}/` | `.scanning/configs/` |
| Templates | `templates/{tier}/` | `.pre-commit-config.yaml` (copy) |
| Suppressions | `configs/common/.scan-suppressions.yaml` | `.scan-suppressions.yaml` |
| Baseline | N/A | `.scan-baseline/` |
| Unified results | N/A | `.scan-results/` |
| Agent report | N/A | `.scanning/last-scan.json` |
| Metrics | N/A | `.scan-results/metrics/` |
| Scan config | N/A | `.scan-config.yaml` |
| Policy overlay | `configs/{provider}/policy-overlay.yaml` | `.scanning/configs/policy-overlay.yaml` |
| Scanning dir | N/A | `.scanning/` |
| JSON schemas | `schemas/` | N/A (referenced, not copied) |
