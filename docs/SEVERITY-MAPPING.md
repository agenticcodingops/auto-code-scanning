# Severity Normalization Mapping

How each scanner's severity is turned into one of four levels. The 5 core tools (Trivy, Checkov, tflint, Gitleaks, Snyk) are used by hooks; Snyk is optional and requires a license. PSScriptAnalyzer, ShellCheck and hadolint are mapped only by the local PowerShell aggregator (`scripts/aggregate-scan-results.ps1`); no hook runs them yet.

Normalization is implemented in three places, which differ in a few edge cases. Each difference is noted below:

| Where | Used by | Tools covered |
|---|---|---|
| `scripts/aggregate_scan.py` | CI: the aggregate step of `reusable-scan.yml` | Trivy (IaC and secrets), Checkov, tflint, Snyk |
| `scripts/scan.py` | Local on-demand scans and AI agents | Trivy, Checkov, Snyk |
| `scripts/aggregate-scan-results.ps1` | Local PowerShell aggregation | All tools on this page |

## Normalized Levels

All tools map to four levels: **CRITICAL**, **HIGH**, **MEDIUM**, **LOW**

## Tool Mappings

### Trivy

| Source Value | Normalized |
|-------------|------------|
| CRITICAL | CRITICAL |
| HIGH | HIGH |
| MEDIUM | MEDIUM |
| LOW | LOW |
| UNKNOWN | LOW locally; kept as UNKNOWN in CI |

Trivy provides native 4-level severity that maps directly. `UNKNOWN` (rare) is treated as LOW by `scan.py` and the PowerShell aggregator. The CI aggregator keeps it as `UNKNOWN`: it is reported but counted in no severity bucket, so it never blocks the CI gate.

### Checkov

| Source Value | Normalized |
|-------------|------------|
| CRITICAL | CRITICAL |
| HIGH | HIGH |
| MEDIUM | MEDIUM |
| LOW | LOW |
| (missing or empty) | HIGH in CI and `scan.py`; in the PowerShell aggregator, MEDIUM when missing and LOW when empty ([#158](https://github.com/agenticcodingops/auto-code-scanning/issues/158)) |

Checkov 3.0+ provides native severity levels that map directly. Many Checkov checks carry no severity unless a Prisma Cloud API key is configured. The CI aggregator and `scan.py` treat a missing severity as HIGH, so missing metadata cannot weaken the gate. `scan.py` maps any other unrecognized value to MEDIUM. The local `checkov` and `checkov-strict` hooks block on any failed check whatever its severity; their summary line counts a missing severity as LOW.

### tflint

| Source Value | Normalized |
|-------------|------------|
| error | HIGH |
| warning | MEDIUM |
| notice | LOW |

tflint uses a 3-level system. No tflint finding maps to CRITICAL since tflint focuses on linting rather than security vulnerabilities.

### Gitleaks

| Source Value | Normalized |
|-------------|------------|
| (all secrets) | HIGH |

Gitleaks does not provide severity levels. The PowerShell aggregator normalizes all Gitleaks findings to HIGH because leaked credentials are a significant security risk. The local `gitleaks` hook blocks on any finding, and CI secret scanning uses Trivy rather than Gitleaks.

### Snyk

| Source Value | Normalized |
|-------------|------------|
| critical | CRITICAL |
| high | HIGH |
| medium | MEDIUM |
| low | LOW |

Snyk IaC provides native 4-level severity (lowercase) that maps directly. Snyk is optional and requires a license.

### PSScriptAnalyzer

| Source Value | Normalized |
|-------------|------------|
| Error | HIGH |
| Warning | MEDIUM |
| Information | LOW |

PSScriptAnalyzer is used for PowerShell script quality. No finding maps to CRITICAL.

### ShellCheck

| Source Value | Normalized |
|-------------|------------|
| error | HIGH |
| warning | MEDIUM |
| info | LOW |
| style | LOW |

ShellCheck is used for shell script quality. Both `info` and `style` map to LOW.

### hadolint

| Source Value | Normalized |
|-------------|------------|
| error | HIGH |
| warning | MEDIUM |
| info | LOW |
| style | LOW |

hadolint is used for Dockerfile quality. Same mapping pattern as ShellCheck.

## Summary Table

| Tool | CRITICAL | HIGH | MEDIUM | LOW |
|------|----------|------|--------|-----|
| **Trivy** | CRITICAL | HIGH | MEDIUM | LOW, UNKNOWN (local only) |
| **Checkov** | CRITICAL | HIGH | MEDIUM | LOW |
| **tflint** | -- | error | warning | notice |
| **Gitleaks** | -- | (all secrets) | -- | -- |
| **Snyk** | critical | high | medium | low |
| **PSScriptAnalyzer** | -- | Error | Warning | Information |
| **ShellCheck** | -- | error | warning | info, style |
| **hadolint** | -- | error | warning | info, style |

## Blocking Thresholds

Different contexts block at different severity levels:

| Context | Blocks On | Rationale |
|---------|-----------|-----------|
| Pre-commit (starter) | CRITICAL | Minimal friction, catch only the worst issues |
| Pre-push (standard) | Per tool config | Broader coverage at push time |
| Pre-push (strict) | CRITICAL, HIGH | Strict enforcement for mature teams |
| CI/CD | CRITICAL, HIGH | Consistent with strict tier |

## Cross-Tool Deduplication

The PowerShell aggregator merges findings that share the same file, resource and category. The CI aggregator does not merge findings across tools. When findings are merged, severity is resolved as follows:
1. Each tool's native severity is normalized using the mappings above
2. The **highest** normalized severity across tools is used for the merged finding
3. The original tool-specific severity is preserved in the `original_severity` field

Example: If Trivy reports a finding as HIGH and Checkov reports the same finding as CRITICAL, the merged finding severity is CRITICAL.

## Implementation Reference

The severity normalization logic is implemented in:
- `scripts/aggregate_scan.py` -- the CI aggregator; covers Trivy, Checkov, tflint and Snyk, and gates on CRITICAL and HIGH
- `scripts/scan.py` (`TRIVY_SEVERITY_MAP`, `CHECKOV_SEVERITY_MAP`, `SNYK_SEVERITY_MAP`) -- covers Trivy, Checkov and Snyk
- `scripts/aggregate-scan-results.ps1` (`Get-NormalizedSeverity` function) -- covers Trivy, Checkov, tflint, Gitleaks, Snyk, PSScriptAnalyzer, ShellCheck, hadolint

The code is the authoritative source. If this page and the code disagree, the code wins; please open an issue.
