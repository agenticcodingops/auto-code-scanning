# Severity Normalization Mapping

Consistent severity mapping across scanning tools. The 5 core tools (Trivy, Checkov, tflint, Gitleaks, Snyk) are actively used by hooks; Snyk is optional and requires a license. The 3 additional tools (PSScriptAnalyzer, ShellCheck, hadolint) are mapped in the aggregation script for future v1.1.0 support.

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

Trivy provides native 4-level severity that maps directly. `UNKNOWN` (rare) is treated as LOW.

### Checkov

| Source Value | Normalized |
|-------------|------------|
| CRITICAL | CRITICAL |
| HIGH | HIGH |
| MEDIUM | MEDIUM |
| LOW | LOW |

Checkov 3.0+ provides native severity levels that map directly.

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

Gitleaks does not provide severity levels. All detected secrets are normalized to HIGH because leaked credentials represent a significant security risk.

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
| **Trivy** | CRITICAL | HIGH | MEDIUM | LOW, UNKNOWN |
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

When multiple tools detect the same finding, severity is resolved as follows:
1. Each tool's native severity is normalized using the mappings above
2. The **highest** normalized severity across tools is used for the merged finding
3. The original tool-specific severity is preserved in the `original_severity` field

Example: If Trivy reports a finding as HIGH and Checkov reports the same finding as CRITICAL, the merged finding severity is CRITICAL.

## Implementation Reference

The severity normalization logic is implemented in:
- `scripts/aggregate-scan-results.ps1` (`Get-NormalizedSeverity` function) -- covers Trivy, Checkov, tflint, Gitleaks, Snyk, PSScriptAnalyzer, ShellCheck, hadolint
- `scripts/scan.py` (Python equivalent) -- covers Trivy, Checkov, tflint, Gitleaks, Snyk

The mapping table in `data-model.md` is the authoritative source for all normalization rules.
