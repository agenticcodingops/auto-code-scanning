# Security Scanning Metrics Dashboard

This document describes the key metrics tracked for the local security scanning infrastructure and how to interpret them.

## Overview

The metrics framework tracks adoption and effectiveness of shift-left security scanning. All metrics are based on industry research including DORA findings, Forrester TEI studies, and DevSecOps best practices.

## Key Metrics

### 1. Bypass Rate

| Metric | Target | Description |
|--------|--------|-------------|
| **Bypass Rate** | < 5% | Percentage of commits that bypass pre-commit hooks |

**What it measures:** How often developers use `--no-verify` or other methods to skip security checks.

**Why it matters:** High bypass rates indicate friction with the scanning process. Research shows teams with <5% bypass rates catch 60% more issues in development.

**How to improve:**
- Optimize hook execution time (target <5 seconds)
- Ensure false positive rate is low
- Provide clear bypass documentation for legitimate cases
- Move slow checks to pre-push stage

### 2. Hook Pass Rate

| Metric | Target | Description |
|--------|--------|-------------|
| **First Attempt Pass Rate** | > 80% | Percentage of commits that pass all hooks on first try |

**What it measures:** Developer experience and code quality before commit.

**Why it matters:** Low pass rates indicate either overly strict checks or code quality issues. Research shows 80%+ pass rates correlate with developer satisfaction.

**How to improve:**
- Document common failures and fixes
- Provide auto-fix where possible (terraform fmt)
- Adjust severity thresholds appropriately
- Offer IDE integration for earlier feedback

### 3. CI Build Failure Trend

| Metric | Target | Description |
|--------|--------|-------------|
| **Security-related CI Failures** | 40% reduction | Trend in CI failures due to security issues |

**What it measures:** Effectiveness of local scanning at catching issues before CI.

**Why it matters:** Forrester TEI research shows organizations achieve 40%+ reduction in CI failures after implementing shift-left scanning.

**How to track:**
- Compare security scan failures in CI before/after implementation
- Track month-over-month trend
- Exclude infrastructure failures (network, runner issues)

### 4. Pre-commit Execution Time

| Metric | Target | Description |
|--------|--------|-------------|
| **Total Pre-commit Time** | < 10 seconds | Total time for all pre-commit hooks |
| **Per-hook Time** | < 5 seconds | Maximum time for any single hook |

**What it measures:** Developer experience during commit workflow.

**Why it matters:** Research shows developers bypass checks that take >30 seconds. Keeping under 10 seconds maintains adoption.

**How to optimize:**
- Use `scripts/profile-hook-performance.ps1` to identify slow hooks
- Move slow checks (>10s) to pre-push stage
- Enable caching where supported
- Run checks in parallel

## Collecting Metrics

### Automated Collection

Run the metrics collection script:

```powershell
# Collect metrics for last 30 days (default)
.\scripts\collect-scan-metrics.ps1

# Collect metrics for last 90 days
.\scripts\collect-scan-metrics.ps1 -Days 90

# Detailed output
.\scripts\collect-scan-metrics.ps1 -Detailed
```

### Output Location

Metrics are stored in `.scan-results/metrics/`:
- `metrics-YYYY-MM-DD.json` - Daily snapshots
- `metrics-latest.json` - Most recent collection

### Metrics Schema

```json
{
  "collection_timestamp": "2026-02-05T10:30:00Z",
  "period_days": 30,
  "repository": "auto-code-scanning",
  "branch": "main",
  "targets": {
    "bypass_rate_max": 5.0,
    "hook_pass_rate_min": 80.0,
    "ci_failure_reduction": 40.0,
    "pre_commit_time_max": 5.0
  },
  "commit_metrics": {
    "total_commits": 150,
    "conventional_commits": 145,
    "potential_bypasses": 5,
    "bypass_rate": 3.33
  },
  "hook_metrics": {
    "total_runs": 200,
    "successful_first_attempt": 175,
    "failures": 25,
    "pass_rate": 87.5
  },
  "finding_metrics": {
    "total_findings": 12,
    "critical": 0,
    "high": 2,
    "medium": 7,
    "low": 3
  }
}
```

## Dashboard Views

### Weekly Summary

| Metric | This Week | Last Week | Trend |
|--------|-----------|-----------|-------|
| Bypass Rate | 3.2% | 4.1% | ↓ Better |
| Pass Rate | 85% | 82% | ↑ Better |
| CRITICAL Findings | 0 | 1 | ↓ Better |
| HIGH Findings | 2 | 4 | ↓ Better |

### Monthly Trend Chart

Track these metrics monthly:
1. Bypass rate trend (target: decreasing to <5%)
2. Pass rate trend (target: increasing to >80%)
3. Finding count by severity (target: decreasing)
4. CI failure rate (target: 40% reduction over baseline)

## Alerts and Thresholds

### Warning Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Bypass Rate | > 5% | > 10% |
| Pass Rate | < 80% | < 70% |
| CRITICAL Findings | > 0 | - |
| HIGH Findings | > 5 | > 10 |
| Pre-commit Time | > 10s | > 30s |

### Actions When Thresholds Exceeded

**Bypass Rate > 5%:**
1. Review hook execution times
2. Check false positive rates
3. Survey developers for friction points
4. Consider moving checks to pre-push

**Pass Rate < 80%:**
1. Analyze common failure reasons
2. Improve documentation/auto-fixes
3. Review severity thresholds
4. Provide training on common issues

**CRITICAL Findings > 0:**
1. Immediate review required
2. Block merge until resolved
3. Notify security team
4. Document remediation

## Research References

Metrics targets are based on:

1. **DORA State of DevOps Reports** (2023-2025)
   - High-performing teams: <5% security bypass rate
   - Correlation between scanning adoption and deployment frequency

2. **Forrester TEI Studies**
   - 40% reduction in security-related CI failures
   - 60% reduction in production security incidents

3. **NIST Bug Fix Cost Study**
   - 30x cost multiplier for production vs. development fixes
   - ROI of early detection: $100K+ annually for mid-size teams

4. **IBM Cost of a Data Breach Report (2025)**
   - Average US breach cost: $10.22M
   - DevSecOps reduces breach cost by 24%

## Related Documentation

- [SHIFT-LEFT-BUSINESS-CASE.md](./SHIFT-LEFT-BUSINESS-CASE.md) - Full ROI analysis
- [PERFORMANCE-OPTIMIZATION.md](./PERFORMANCE-OPTIMIZATION.md) - Hook optimization guide
- [SUPPRESSION-GOVERNANCE.md](./SUPPRESSION-GOVERNANCE.md) - Managing suppressions
