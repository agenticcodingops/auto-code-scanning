# Severity Normalization Mapping

How each scanner's severity is turned into one of four levels. The 5 core tools (Trivy, Checkov, tflint, Gitleaks, Snyk) are used by hooks; Snyk is optional and requires a license. PSScriptAnalyzer, ShellCheck and hadolint are mapped only by the local PowerShell aggregator (`scripts/aggregate-scan-results.ps1`); no hook runs them yet.

The Python entry points share `scripts/scan_reports.py`. PowerShell aggregation, baseline creation and hook summaries use the same table, with the compatibility exceptions below.

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
| UNKNOWN | LOW |

Trivy provides native four-level severity. `UNKNOWN` maps to LOW in every reporting path. CI, `scan.py` and baseline scanner validation still reject absent, null, empty, lowercase and other invalid Trivy values. The local aggregator and hook summaries retain their permissive LOW fallback.

### Checkov

| Source Value | Normalized |
|-------------|------------|
| CRITICAL | CRITICAL |
| HIGH | HIGH |
| MEDIUM | MEDIUM |
| LOW | LOW |
| (missing, null or empty) | HIGH |
| Any other string, including INFO and NONE | MEDIUM |

Checkov 3.0+ provides native severity levels that map directly. Many Checkov checks carry no severity unless a Prisma Cloud API key is configured. The CI aggregator and `scan.py` treat a missing severity as HIGH, so missing metadata cannot weaken the gate. Unrecognized Checkov strings map to MEDIUM. Hook summary lines count a missing severity as HIGH.

### tflint

| Source Value | Normalized |
|-------------|------------|
| error | HIGH |
| warning | MEDIUM |
| info, notice | LOW |
| Missing or other value | MEDIUM |

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

Snyk IaC provides native four-level severity (lowercase). CI and `scan.py` retain validation that rejects invalid or absent values. Hook summaries and the local aggregator count absent or unknown values as MEDIUM. Snyk is optional and requires a license.

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
| **Trivy** | CRITICAL | HIGH | MEDIUM | LOW, UNKNOWN |
| **Checkov** | CRITICAL | HIGH, missing/null/empty | MEDIUM, other strings | LOW |
| **tflint** | -- | error | warning, missing/other | info, notice |
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
- `scripts/scan_reports.py` (`normalize_severity`, `count_by_severity`) -- shared by CI, `scan.py` and baseline finalization
- `hooks/lib/common.sh` and `hooks/lib/common.ps1` -- normalized summary counts and detail labels
- `scripts/aggregate-scan-results.ps1` (`Get-NormalizedSeverity` function) -- covers Trivy, Checkov, tflint, Gitleaks, Snyk, PSScriptAnalyzer, ShellCheck, hadolint

The code is the authoritative source. If this page and the code disagree, the code wins; please open an issue.

## Compatibility exceptions

Normalization itself does not fold letter case. CI retains its Checkov uppercase
conversion, while `scan.py` treats lowercase Checkov strings as MEDIUM. Bash
summaries retain case-sensitive comparisons; PowerShell comparisons remain
case-insensitive. TFLint in CI retains its case-sensitive source mapping.

Non-string handling is also retained: truthy numeric or list Checkov severities
fail in CI's uppercase conversion; `scan.py` maps a number to MEDIUM and rejects
an unhashable list during mapping. Falsy Checkov values retain the existing HIGH
fallback in those parsers. Baseline finalization preserves supplied non-string
metadata; severity is not part of occurrence identity. Its PowerShell summary
retains the existing failure on a numeric severity, or on a list holding a non-text
value; a list of strings succeeds, as before. PowerShell reporting
casts scalar metadata to text and compares case-insensitively; a singleton
`["HIGH"]` therefore still matches HIGH. Bash summaries use typed, case-sensitive
comparisons, with non-string values assigned the tool's fallback bucket. No
validator is relaxed.

## Upgrade

Labels and `by_severity` counts change once when upgrading: Checkov missing values
are HIGH, unrecognized strings are MEDIUM, Trivy UNKNOWN is LOW, and TFLint info
is LOW. Scripts that read `by_severity` may see different numbers. Re-vendor
`scan.py` and `scan_reports.py` together, and upgrade the shared hook libraries
with their wrappers. Baseline and suppression identities remain unchanged.

The PowerShell aggregator's `total_findings` is corrected when there is exactly one
finding: it used to report that finding's field count (for example 18) and now
reports 1, and `findings` is always an array. Scripts that read either may need
adjusting.

`aggregate-scan-results.ps1` and `create-baseline.ps1` need `hooks/lib/common.ps1`
from the same release. They stop with an error if it is older, so re-vendor them
together. Re-vendor `hooks/` as a whole directory: a new hook beside an older
`hooks/lib` still blocks on findings, but its counts are wrong.
