# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - Unreleased

### Added

- **Dual-wrapper hook architecture**: Each hook has both `.sh` (bash) and `.ps1` (PowerShell) entry scripts with an OS-detecting dispatcher (`hooks/dispatcher.sh`) for cross-platform support
- **All 9 security scanning hooks**: trivy-iac-critical, trivy-iac-full, trivy-secrets, checkov, checkov-strict, validate-suppressions, tflint, gitleaks, snyk-iac
- **Optional Snyk IaC hook**: `snyk-iac` pre-push hook for projects with a Snyk license. Fail-open when Snyk is not installed or not authenticated. Dual `.sh`/`.ps1` wrappers, JSON output to `.scanning/last-scan.json`
- **Snyk CI integration**: Optional `scan-snyk` job in `reusable-scan.yml`, activated with `enable-snyk: true` input and `SNYK_TOKEN` secret
- **Snyk in scan.py**: AI agent interface supports `--tools snyk` for Snyk IaC scanning with severity normalization
- **Snyk severity mapping**: CRITICAL/HIGH/MEDIUM/LOW direct mapping from Snyk lowercase severity values
- **Fail-open error handling**: Infrastructure errors (tool crashes, DB corruption) exit 0 with a warning; only actual security findings block commits
- **JSON output for hooks**: All hooks write structured findings to `.scanning/last-scan.json` for machine consumption
- **Cross-platform Python setup**: `scripts/setup-scanning.py` for macOS (Homebrew), Linux (apt), and Windows (delegates to PowerShell)
- **Cross-platform suppression validation**: `scripts/validate-suppressions.py` using PyYAML for all platforms
- **Config layering**: Universal security checks separated from organization-specific policy overlays (`policy-overlay.yaml`)
- **Shared noisy-checks exclusion lists**: Per-provider curated lists of known false-positive checks (`configs/common/noisy-checks-{provider}.yaml`)
- **Cross-tool finding deduplication**: Aggregation matches on (file, resource, category) and merges findings with a `detected_by` array
- **Severity normalization for 8 tools**: Trivy, Checkov, tflint, Gitleaks, Snyk, PSScriptAnalyzer, ShellCheck, hadolint mapped to CRITICAL/HIGH/MEDIUM/LOW
- **Remediation URL generation**: Auto-generated docs.checkov.io URLs for Checkov findings, avd.aquasec.com URLs for Trivy findings
- **Baseline management with hash matching**: `scripts/create-baseline.ps1` uses SHA-256(rule_id|file_path) for O(1) lookup; line numbers excluded for refactoring resilience
- **Monorepo-scoped baselines**: `-MonorepoScope` parameter for scoping baselines to specific Terraform modules
- **GitHub Actions artifact upload**: Metrics JSON uploaded as artifacts for cross-repo aggregation
- **Reusable scan workflow**: Converted to `workflow_call` trigger with configurable inputs (cloud-provider, severity, upload-sarif, post-pr-comment, fail-on-findings)
- **SARIF truncation**: Automatic truncation to highest-severity findings when exceeding GitHub's 25MB/5000 result limits
- **CI suppression integration**: Dedicated `apply-suppressions` job filters actively suppressed findings
- **Performance validation workflow**: CI timing tests for all hooks against test fixtures with 5-second threshold enforcement
- **Per-provider test fixtures**: Valid, critical, and failure fixtures for AWS, Azure, and GCP
- **Unified results JSON schema**: `schemas/unified-results.schema.json` with scan_id UUID, duration_ms, detected_by array, baseline/suppressed flags
- **Agent report schema**: `schemas/last-scan.schema.json` with auto_fix fields for AI agent consumption
- **Developer satisfaction survey template**: `docs/DEVELOPER-SURVEY.md`
- **Troubleshooting guide**: `docs/TROUBLESHOOTING.md` covering top 10 common issues
- **Tier upgrade guide**: `docs/TIER-UPGRADE-GUIDE.md` with exact hooks to add per transition

### Changed

- **Checkov configs converted to blocklist**: All checks run by default; config lists exclusions only. New checks auto-activate on tool update
- **Hook entry points**: All hooks now use `hooks/dispatcher.sh {hook-id}` with `language: script` instead of direct tool invocation
- **Hook file pattern**: Changed from `\.tf$` to all files with directory exclusions (`.terraform/`, `node_modules/`, `.git/`); scanning tools determine relevance
- **`pass_filenames: false`**: Hooks scan directories, not individual files
- **Suppression validation command**: Changed from `validate-suppressions.ps1` to `python scripts/validate-suppressions.py` for cross-platform support
- **Metrics output schema**: Conformed to Metric entity schema with `schema_version`, `commit_sha`, `cloud_provider`, `adoption_tier`, `hook_results`, `aggregate` structure
- **Performance profiler**: Now measures all 9 hooks (was only trivy-iac-critical); reports per-stage totals vs targets
- **Baseline format**: Single `baseline.json` file with SHA-256 hash entries (was per-tool raw scan output files)
- **tflint configs**: Added `tflint-ruleset-terraform` plugin for common Terraform rules across all providers
- **Standard template**: Removed `no-commit-to-branch` hook (branch protection is a workflow preference, not security)
- **Strict template**: `commitizen` hook is now commented out (opt-in, not default)

### Migration Guide

If upgrading from the pre-1.0 version:

1. **Re-run setup**: `.\scripts\setup-scanning.ps1 -CloudProvider <your-provider>` to get new hook wrappers and configs
2. **Checkov config**: If you customized `.checkov.yaml`, remove the `check:` section (blocklist approach keeps only `skip-check:`)
3. **Baseline refresh**: Old baselines are incompatible. Run `.\scripts\create-baseline.ps1 -Force` to recreate
4. **Template update**: If using tiered templates, review the new hook list for your tier in `docs/TIER-UPGRADE-GUIDE.md`
5. **Suppression validation**: Update any CI scripts from `validate-suppressions.ps1` to `python scripts/validate-suppressions.py`

### Dependency Requirements

- pre-commit >= 3.0.0
- Trivy >= 0.48.0
- Checkov >= 3.0.0
- tflint >= 0.50.0
- Python >= 3.8 (required for cross-platform scripts)
- PowerShell >= 7.0 (Windows scripts)
