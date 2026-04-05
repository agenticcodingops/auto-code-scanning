# Suppression Governance Guide

This document establishes the governance framework for managing security scan suppressions in the auto-code-scanning repository.

## Overview

Suppressions allow teams to acknowledge and temporarily accept security findings when immediate remediation isn't feasible. This governance framework ensures suppressions are:

- **Documented** with clear business justification
- **Time-limited** with mandatory expiration dates
- **Approved** by appropriate stakeholders
- **Reviewed** on a regular cadence

## Suppression Registry

All suppressions are managed in a single source of truth:

```
.scan-suppressions.yaml
```

This file replaces individual tool-specific suppression mechanisms and provides:
- Centralized visibility
- Consistent governance
- Automated compliance checking

## Required Fields

Every suppression MUST include:

| Field | Description | Example |
|-------|-------------|---------|
| `rule_id` | The check ID being suppressed | `AVD-AWS-0057`, `CKV_AWS_18` |
| `tool` | Scanner that raised the finding | `trivy`, `checkov`, `tflint` |
| `reason` | Business justification (be specific) | "S3 lifecycle managed at org level via AWS Config" |
| `owner` | Responsible party email | `platform-team@company.com` |
| `approved_date` | When approved (YYYY-MM-DD) | `2026-02-01` |
| `expires_date` | Review/renewal date (YYYY-MM-DD) | `2026-08-01` |

### Additional Fields for HIGH/CRITICAL

| Field | Description | Required For |
|-------|-------------|--------------|
| `severity` | Original finding severity | Recommended for all |
| `approved_by` | Security approver email | HIGH, CRITICAL |
| `ticket` | Tracking ticket (Jira, etc.) | HIGH, CRITICAL |
| `file_pattern` | Limit scope (glob pattern) | Optional |

## Approval Requirements

### By Severity

| Severity | Approver | Max Duration | Review Frequency |
|----------|----------|--------------|------------------|
| LOW | Module owner | 6 months | Quarterly |
| MEDIUM | Module owner | 6 months | Quarterly |
| HIGH | Security team + Module owner | 3 months | Monthly |
| CRITICAL | Security team + Engineering lead | 1 month | Weekly |

### Approval Process

1. **Developer** identifies false positive or accepted risk
2. **Developer** creates suppression entry with all required fields
3. **For HIGH/CRITICAL:** Security team reviews and approves
4. **Developer** adds approved_by field and commits
5. **CI/CD** validates suppression compliance

## Adding a Suppression

### Step 1: Document the Finding

```yaml
# .scan-suppressions.yaml
trivy_suppressions:
  - rule_id: AVD-AWS-0057
    tool: trivy
    severity: MEDIUM
    reason: "S3 lifecycle rules are configured at the composition layer through the root module, not in individual modules"
    file_pattern: "terraform/modules/aws/storage/s3/*.tf"
    owner: platform-team@company.com
    approved_date: "2026-02-01"
    expires_date: "2026-08-01"
    ticket: "BDCD-123"
```

### Step 2: Run Validation

```bash
python scripts/validate-suppressions.py .scan-suppressions.yaml
```

### Step 3: Get Approval (if required)

For HIGH/CRITICAL:
1. Create Jira ticket with finding details
2. Request security team review
3. Add `approved_by` field once approved

### Step 4: Commit

```bash
git add .scan-suppressions.yaml
git commit -m "chore: add suppression for AVD-AWS-0057 (BDCD-123)"
```

## Quarterly Review Process

### Schedule

Reviews occur on the first Monday of each quarter:
- Q1: First Monday of January
- Q2: First Monday of April
- Q3: First Monday of July
- Q4: First Monday of October

### Review Steps

1. **Generate Report**
   ```powershell
   .\scripts\generate-suppression-report.ps1
   ```

2. **Review Each Suppression**
   - Is the root cause still valid?
   - Has a fix become available?
   - Is the owner still correct?
   - Should severity be re-evaluated?

3. **Take Action**
   - **Renew:** Update `expires_date` with new review date
   - **Remove:** Delete entry if issue is resolved
   - **Archive:** Move to `suppression_history` section

4. **Document**
   - Update Jira tickets
   - Note decisions in review meeting minutes

### Review Meeting Agenda

```markdown
## Quarterly Suppression Review - [Date]

### Attendees
- Security team representative
- Platform team lead
- Module owners (as needed)

### Review Items

| Rule ID | Tool | Severity | Owner | Decision |
|---------|------|----------|-------|----------|
| AVD-AWS-0057 | trivy | MEDIUM | platform-team | Renew |
| CKV_AWS_18 | checkov | HIGH | security-team | Remove (fixed) |

### Action Items
- [ ] Update .scan-suppressions.yaml
- [ ] Close resolved Jira tickets
- [ ] Notify affected teams
```

## Generating Reports

### Suppression Report

```powershell
# Generate comprehensive report
.\scripts\generate-suppression-report.ps1

# Output includes:
# - Active suppressions by severity
# - Suppressions expiring within 30 days
# - Suppressions by owner
# - Historical trends
```

### Sample Report Output

```
========================================
  Suppression Report - 2026-02-05
========================================

Active Suppressions: 12

By Severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 7
  LOW: 3

Expiring Soon (30 days):
  - AVD-AWS-0089 (trivy) - Expires: 2026-02-28
  - CKV_AWS_145 (checkov) - Expires: 2026-03-01

By Owner:
  platform-team@company.com: 8
  security-team@company.com: 3
  data-team@company.com: 1
```

## Automation

### Pre-commit Validation

The suppression file is validated on every commit via the `validate-suppressions` hook defined in `.pre-commit-hooks.yaml`. This runs automatically when `.scan-suppressions.yaml` is staged.

### CI/CD Validation

The reusable GitHub Actions workflow (`reusable-scan.yml`) validates suppressions as part of the scan pipeline. Expired suppressions produce warnings locally but fail in CI.

### Manual Validation

```bash
# Validate suppression file
python scripts/validate-suppressions.py .scan-suppressions.yaml

# Validate with strict mode (warnings become errors)
python scripts/validate-suppressions.py --strict .scan-suppressions.yaml
```

## Best Practices

### DO

- Document specific, technical justifications
- Set conservative expiration dates
- Review suppressions when code changes
- Use file patterns to limit scope
- Track suppressions in Jira/ticketing system

### DON'T

- Suppress entire categories of checks
- Use generic reasons like "false positive"
- Let suppressions auto-renew without review
- Suppress without understanding the risk
- Forget to notify security team for HIGH/CRITICAL

## Escalation Path

If a suppression request is denied:

1. **Discuss** alternative mitigations with security team
2. **Document** the risk acceptance if proceeding
3. **Escalate** to engineering leadership if needed
4. **Track** formal risk acceptance in GRC tool

## Related Documentation

- [METRICS-DASHBOARD.md](./METRICS-DASHBOARD.md) - Track suppression metrics
- [SETUP-GUIDE.md](./SETUP-GUIDE.md) - Scanning setup overview
- [SHIFT-LEFT-BUSINESS-CASE.md](./SHIFT-LEFT-BUSINESS-CASE.md) - Why we scan
