# Contract: Workflow Interface

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)
**Date**: 2026-02-10

## Overview

Defines the interface contract for reusable GitHub Actions workflows provided by this repo. Consuming repos call these workflows via `workflow_call` triggers.

## Reusable Scan Workflow (reusable-scan.yml)

### Invocation

```yaml
# In consuming repo's workflow
jobs:
  security-scan:
    uses: {org}/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
    with:
      terraform-directory: "terraform/"
      cloud-provider: "aws"
      severity: "CRITICAL,HIGH"
    permissions:
      contents: read
      security-events: write    # Required for SARIF upload
      pull-requests: write      # Required for PR comments
```

### Input Parameters

| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `terraform-directory` | string | No | `"."` | Root directory containing Terraform files |
| `cloud-provider` | string | Yes | — | `aws`, `azure`, or `gcp` |
| `severity` | string | No | `"CRITICAL,HIGH,MEDIUM,LOW"` | Comma-separated severity filter |
| `fail-on-findings` | boolean | No | `true` | Whether findings cause workflow failure |
| `upload-sarif` | boolean | No | `true` | Upload SARIF to GitHub Code Scanning |
| `post-pr-comment` | boolean | No | `true` | Post findings summary as PR comment |
| `apply-suppressions` | boolean | No | `true` | Apply .scan-suppressions.yaml filtering |
| `apply-baseline` | boolean | No | `true` | Filter baseline findings |
| `upload-metrics` | boolean | No | `true` | Upload metrics as artifact |

### Output Parameters

| Output | Type | Description |
|--------|------|-------------|
| `findings-count` | string | Total findings after filtering |
| `critical-count` | string | CRITICAL findings count |
| `high-count` | string | HIGH findings count |
| `scan-passed` | string | `"true"` or `"false"` |
| `sarif-uploaded` | string | `"true"` or `"false"` |

### Permissions Required

| Permission | Level | Purpose | Opt-Out |
|-----------|-------|---------|---------|
| `contents` | `read` | Read repository code | Cannot opt out |
| `security-events` | `write` | SARIF upload to Code Scanning | Set `upload-sarif: false` |
| `pull-requests` | `write` | Post PR comments | Set `post-pr-comment: false` |

### Job Structure

```
reusable-scan.yml
├── setup           # Install tools, download configs
├── scan-trivy      # Run Trivy (all severities)
├── scan-checkov    # Run Checkov
├── scan-tflint     # Run tflint
├── aggregate       # Merge results, deduplicate, apply suppressions/baseline
├── sarif-upload    # Upload SARIF (if enabled, with truncation)
├── pr-comment      # Post PR comment (if enabled, always new comment)
└── metrics         # Upload metrics artifact (if enabled)
```

### SARIF Truncation Contract

When SARIF output exceeds GitHub limits:

| Limit | Threshold | Action |
|-------|-----------|--------|
| File size | 25 MB | Truncate findings, highest severity first |
| Result count | 5,000 | Truncate findings, highest severity first |

When truncation occurs, a `warning` level SARIF annotation is added:
```
"Scan results truncated: {total} findings found, showing top {shown} by severity. Run locally for full results."
```

### PR Comment Format

```markdown
## Security Scan Results

| Severity | Count |
|----------|-------|
| CRITICAL | N |
| HIGH     | N |
| MEDIUM   | N |
| LOW      | N |

**Tools**: Trivy, Checkov, tflint
**Suppressions applied**: N
**Baseline filtered**: N

<details>
<summary>Top findings (click to expand)</summary>

| File | Rule | Severity | Tool | Remediation |
|------|------|----------|------|-------------|
| ... | ... | ... | ... | [Link](url) |

</details>
```

**Comment policy**: Always create a new comment. Previous scan comments are not updated or collapsed.

### Metrics Artifact

Artifact name: `scan-metrics-{cloud-provider}-{date}`
Retention: GitHub Actions default (90 days)
Format: JSON conforming to Metric entity schema (see data-model.md)

## Bypass Detection Workflow (bypass-detection.yml)

### Trigger

Runs on `push` to default branch. Detects commits that bypassed pre-commit hooks.

### Detection Method

Heuristic: Check if the commit has corresponding pre-commit hook output. This is a best-effort detection — CI re-scanning is the authoritative enforcement.

### Output

Adds a check annotation (warning level) if bypass is suspected. Does not block the push.

## Performance Check Workflow (performance-check.yml)

### Trigger

Runs on pull requests that modify files in `hooks/`, `scripts/`, or `configs/`.

### Contract

| Check | Threshold | Failure Mode |
|-------|-----------|-------------|
| Per-hook duration | <5 seconds | Fail PR check |
| Total pre-commit | <10 seconds | Fail PR check |
| Total pre-push | <60 seconds | Fail PR check |

Measured against `tests/fixtures/terraform-valid/` on `ubuntu-latest`.

## CI Workflow (ci.yml)

### Trigger

Runs on all pull requests to this repo.

### Jobs

1. **lint**: Validate YAML, JSON schemas, PowerShell syntax
2. **test-hooks**: Run each hook against all test fixtures, verify expected outcomes
3. **test-scripts**: Run Pester tests (PowerShell) + pytest (Python)
4. **integration**: Simulate consuming repo setup + scan cycle
5. **performance**: Run performance check workflow
