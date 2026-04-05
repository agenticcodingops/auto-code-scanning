# Roadmap

## v1.0.0 (Current Release)

- [x] Pre-commit hook manifest (8 hooks via dispatcher.sh)
- [x] AWS cloud configuration (Checkov, tflint, policy-overlay)
- [x] Azure cloud configuration (Checkov, tflint, policy-overlay)
- [x] GCP cloud configuration (Checkov, tflint, policy-overlay)
- [x] Tiered adoption templates (starter/standard/strict)
- [x] PowerShell setup scripts (admin + no-admin)
- [x] Cross-platform Python setup script (setup-scanning.py)
- [x] Suppression governance framework
- [x] Metrics and performance scripts
- [x] Reusable GitHub Actions workflows (reusable-scan.yml, bypass-detection.yml, performance-check.yml)
- [x] Test fixtures for all clouds (valid, critical, secret)
- [x] Pester unit tests for PowerShell scripts
- [x] Python pytest tests for all Python scripts
- [x] Integration tests for hook execution
- [x] Performance CI validation
- [x] All tests passing in CI
- [x] Documentation complete and validated
- [x] Hook performance validated (<5s each)
- [x] Baseline management feature (create-baseline.ps1)
- [x] Severity normalization in aggregation script
- [x] AI agent scanning interface (scan.py)
- [x] Suppression validation rewritten in Python (validate-suppressions.py)

## v1.1.0

- [ ] PowerShell scanning hooks (PSScriptAnalyzer)
- [ ] Shell/Bash scanning hooks (ShellCheck, shfmt)
- [ ] Docker scanning hooks (hadolint)

## Future: Application Security Scanning Repository

A separate repository (`auto-code-scanning`) for:

- Python (bandit, black)
- Java (SpotBugs, checkstyle)
- C# (Roslyn analyzers)
- JavaScript/TypeScript (eslint-security)
- Same tiered template approach
- Same reusable workflow pattern
