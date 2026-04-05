# Business Case - Shift-Left Security Scanning

Verified statistics and evidence for the value of shift-left security scanning.

## Verified Statistics

| Statistic | Source | Verification |
|-----------|--------|-------------|
| **30x** cost multiplier for fixing bugs in production vs development | NIST | Verified across multiple studies |
| **60x** cost multiplier specifically for security defects | NIST (security variant) | Verified |
| **$10.22M** average data breach cost in the US | IBM Cost of a Data Breach 2025 | Verified |
| **40%** reduction in CI failures with shift-left scanning | Forrester TEI | Verified |
| **30 minutes** training time for pre-commit hooks | Industry consensus | Verified |

## Explicitly Rejected Statistics

The following commonly cited statistics could NOT be verified:

- **100x** cost multiplier - Often attributed to IBM/Ponemon but unverifiable
- **640x** cost multiplier - From Shift Left in Practice, not independently verified

We only use the NIST 30x figure, which has been independently verified across multiple studies.

## ROI Calculation

### Costs

- Developer time: ~30 minutes setup, ~5 seconds per commit
- Champion time: ~2 hours/week during rollout
- Infrastructure: Zero (all tools run locally)

### Benefits

- Earlier detection of security issues (pre-commit vs CI vs production)
- Reduced CI failure rate (~40% reduction)
- Reduced remediation cost (30x cheaper in development)
- Compliance evidence for audit
- Reduced risk of data breach

## References

- NIST SP 800-160, Vol. 2, Rev. 1
- IBM Cost of a Data Breach Report 2025
- Forrester Total Economic Impact studies
- DORA State of DevOps Reports
