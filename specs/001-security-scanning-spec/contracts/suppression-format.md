# Contract: Suppression Format

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)
**Date**: 2026-02-10

## Overview

Defines the contract for the `.scan-suppressions.yaml` file format, validation rules, and governance lifecycle. This file is the single source of truth for all security scan suppressions in a consuming repository.

## File Location

| Context | Path |
|---------|------|
| This repo (template) | `configs/common/.scan-suppressions.yaml` |
| Consuming repo | `.scan-suppressions.yaml` (repo root) |

## Schema (v1.0)

```yaml
# Required top-level fields
schema_version: "1.0"              # REQUIRED: Schema version for migration

# Global settings
settings:
  max_expiry_days: 180             # REQUIRED: Maximum suppression lifetime (days)
  require_security_approval:        # REQUIRED: Severity levels needing approval
    - CRITICAL
    - HIGH
  review_frequency_days: 90        # REQUIRED: Mandatory review cycle (days)

# Suppression entries grouped by tool
trivy_suppressions:                 # Array of suppression entries
  - <suppression-entry>

checkov_suppressions:               # Array of suppression entries
  - <suppression-entry>

tflint_suppressions:                # Array of suppression entries
  - <suppression-entry>

# Audit trail
suppression_history:                # Array of history entries
  - <history-entry>
```

## Suppression Entry Schema

```yaml
# Required fields
rule_id: "AVD-AWS-0057"           # Tool-specific check/rule ID
tool: "trivy"                      # "trivy" | "checkov" | "tflint"
reason: "Managed at composition layer"  # Business justification (free text)
owner: "team@company.com"         # Responsible party email
approved_date: "2026-02-01"       # ISO 8601 date (YYYY-MM-DD)
expires_date: "2026-08-01"        # ISO 8601 date (max settings.max_expiry_days from approved_date)

# Optional fields
severity: "MEDIUM"                 # CRITICAL | HIGH | MEDIUM | LOW
file_pattern: "terraform/modules/aws/**/*.tf"  # Glob pattern to scope suppression
approved_by: "security@company.com"  # Security approver (REQUIRED for HIGH/CRITICAL)
ticket: "JIRA-1234"               # Approval ticket reference
```

### Field Constraints

| Field | Type | Constraint |
|-------|------|-----------|
| `rule_id` | string | Non-empty; pattern depends on tool (see below) |
| `tool` | enum | One of: `trivy`, `checkov`, `tflint` |
| `reason` | string | Non-empty, minimum 10 characters |
| `owner` | string | Non-empty, should be email format |
| `approved_date` | string | Valid ISO 8601 date |
| `expires_date` | string | Valid ISO 8601 date, ≤ max_expiry_days from approved_date |
| `severity` | enum | One of: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `file_pattern` | string | Valid glob pattern |
| `approved_by` | string | Required when severity in `require_security_approval` |
| `ticket` | string | Free text (no format enforced) |

### Rule ID Format by Tool

| Tool | Pattern | Examples |
|------|---------|----------|
| Trivy | `AVD-*` | `AVD-AWS-0057`, `AVD-AZU-0001` |
| Checkov | `CKV_*` | `CKV_AWS_18`, `CKV_AZURE_1`, `CKV_GCP_12` |
| tflint | Any string | `terraform_naming_convention`, `aws_instance_invalid_type` |

## History Entry Schema

```yaml
rule_id: "AVD-AWS-0089"
tool: "trivy"
removed_date: "2026-01-15"        # When suppression was removed
removal_reason: "Issue resolved in module v2.0.0"
original_approved_date: "2025-07-15"
```

## Validation Rules

Enforced by `validate-suppressions.py` (and `hooks/validate-suppressions.py`):

### Errors (block)

| Rule | Description |
|------|-------------|
| V-001 | YAML must be syntactically valid |
| V-002 | `schema_version` must be present and equal to `"1.0"` |
| V-003 | All required fields must be present in each entry |
| V-004 | `tool` must be one of the allowed enum values |
| V-005 | `approved_date` and `expires_date` must be valid ISO dates |
| V-006 | `expires_date` must be ≤ `max_expiry_days` after `approved_date` |
| V-007 | `approved_by` must be present when severity is in `require_security_approval` |
| V-008 | No duplicate `(rule_id, tool)` pairs in the same tool section |
| V-009 | `rule_id` must match expected pattern for declared tool |

### Warnings (informational)

| Rule | Description |
|------|-------------|
| W-001 | Suppression expires within 30 days |
| W-002 | `ticket` field is empty |
| W-003 | `severity` field is missing (recommended) |

### Expiry Behavior

| Context | Expired Entry | Behavior |
|---------|---------------|----------|
| Pre-commit hook | `expires_date` < today | **Warning** — allow commit, print expiry notice |
| CI workflow | `expires_date` < today | **Error** — fail workflow |

**Rationale**: Local hooks warn to give teams time to renew or remediate. CI enforces strictly to prevent permanent suppressions.

## Governance Lifecycle

```
1. Developer identifies finding to suppress
       │
       ▼
2. Document business justification
       │
       ▼
3. Get approval (security team for HIGH/CRITICAL)
       │
       ▼
4. Add entry to .scan-suppressions.yaml
       │
       ▼
5. Run: python scripts/validate-suppressions.py
       │
       ▼
6. Commit with ticket reference
       │
       ▼
7. Quarterly review (every settings.review_frequency_days)
       │
       ├──▶ Renew: Update expires_date (max 180 more days)
       │
       └──▶ Remove: Move to suppression_history, delete from active
```

## Interaction with Other Entities

### Suppressions + Baseline

A finding can match both a suppression and a baseline entry. Both flags are set independently in the Unified Result:

```json
{
  "suppressed": true,
  "suppression_reason": "Managed at composition layer",
  "baseline": true
}
```

Neither mechanism overrides the other. Both are informational — the finding is reported with all applicable filter reasons.

### Suppressions + SARIF

Suppressed findings are included in SARIF output with a `suppressed` property set to `true`. GitHub Code Scanning shows these as dismissed.

### Suppressions + Metrics

Metrics include `suppressed_count` in the aggregate. This tracks suppression usage over time to detect governance drift.

## Migration Notes

When `schema_version` changes (future):
- Validator must support both old and new versions during transition
- Old-format files produce a warning (not error) for one release cycle
- Migration script provided in `scripts/`
