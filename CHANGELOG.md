# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.1] - Patch — review hardening (security + correctness)

Fixes from the workout-trackroutinely PR #145 consumer review. No breaking changes;
consumers should bump the pin from `@v2.0.0` to `@v2.0.1` and re-vendor `hooks/`,
`scripts/`, `schemas/`.

### Security

- **`check-fix-allowlist.py`: boundary-aware allowlist matching.** A bare
  `startswith` let a sibling path bypass the gate (e.g. `api/src-malicious/x` matched
  allowlist `api/src`). Now matches the entry itself or a path under it (`a` or `a/…`)
  regardless of trailing slashes. Also **fails closed** (exit 2) on a malformed/unreadable
  config instead of crashing with a traceback.
- **Stop leaking raw secret values in hook output/findings.** `gitleaks.{ps1,sh}`,
  `lib/common.{ps1,sh}` (Trivy secret printer), and `scripts/scan-and-fix.ps1`
  (`.claude/scan-findings.json`) no longer emit the matched secret content — only
  rule + `file:line`.

### Correctness

- **`validate-scan-config.py`** now **fails closed** (exit 1) on a missing config when
  `STRICT=1` (CI), instead of silently passing.
- **`scan-and-fix.sh`** unknown scan type now exits 1 (was 0 — typos silently skipped
  scanning). **`scan-and-fix.ps1`** `-ScanType all` now includes the C# and TypeScript scans.
- **`eslint.ps1` / `prettier.ps1`**: resolve `working_dir` to an absolute path before
  `Push-Location` (fixes a doubled `mobile/mobile/node_modules/…` path) and find the
  POSIX local binary, not just `*.cmd`.
- **`sqlfluff.{ps1,sh}`**: only force `--dialect ansi` when no `.sqlfluff` config exists
  (a CLI dialect overrides project config).
- **`trivy-secrets.{ps1,sh}`**: count + warn on staged-file export failures instead of
  silently dropping them from the scan.
- **`validate-suppressions.py`**: add `snyk` to `ALLOWED_TOOLS` + a rule-id pattern
  (the `snyk_suppressions` section was otherwise un-validatable).
- **`validate-suppressions.sh`**: fall back to `./.scan-suppressions.yaml` (repo root)
  when not under `SCAN_CONFIG_DIR`.
- **`lib/common.{ps1,sh}`**: directory-change detection falls back to the push range
  (`@{push}`/`@{upstream}..HEAD`) when the index is empty, so **pre-push** Terraform
  hooks actually scan the pushed commits.
- **`render-scan-config.py`**: rename ambiguous loop var (`l` → `lang_name`, Ruff E741).

## [2.0.0] - Unreleased — Reusable scan→fix platform

A major evolution from a Terraform-only, scan-only POC into a reusable,
configurable, multi-consumer **scan-AND-fix platform**. Terraform scanning is
preserved unchanged. **Pin consumers to `@v2.0.0` (or a SHA) — never `@main`.**

### Added — LAYER A: application-code scanning

- **C#/.NET, TypeScript/JS, and SQL language plugins** in `scan-config.yaml`
  (`languages.csharp`, `languages.typescript`, `languages.sql`), each with a
  per-project `build.{solution,working_dir}` so the dotnet-format path is solved by
  **config, never hardcoded** (the generic fix for the PR #145 `api/` path bug).
- **New dispatcher hooks** (`.sh` + `.ps1`, same staged-only fail-open pattern):
  `semgrep-csharp`, `semgrep-typescript`, `dotnet-format`, `dotnet-build` (Roslyn),
  `eslint`, `prettier`, `sqlfluff`, `validate-scan-config`. Registered in
  `.pre-commit-hooks.yaml`. Semgrep runs the **native-Windows path** with `PYTHONUTF8=1`.
- **`code-security-scan.yml`** reusable workflow: auto-detects enabled languages from
  `scan-config.yaml`, runs Semgrep per language, and uploads SARIF under **distinct
  categories** (`ci.sarif.category_prefix`, post-2025-07 GitHub rule).
- **`schemas/scan-config.schema.json`** + `scripts/validate-scan-config.py`: configs
  validated in a hook and in CI; `fix_loop.enabled` requires an allowlist + a SHA-pinned
  action ref.

### Added — LAYER B: agentic fix-loop (opt-in)

- **`fix_loop:` config section**: `enabled`, `label`, `human_review_label`, `max_turns`,
  `max_iterations`, `allowlist_paths`, `gated_paths`, `claude_code_action_ref`,
  `build_verify_cmd`, `required_secrets`.
- **`autonomous-fix.yml`** reusable two-job workflow (generic PR #145 design): a
  read-only `analyze` job (no push creds, no egress, scoped tools, untrusted-text-as-data)
  that emits a patch artifact, and an `apply-and-push` job that re-checks out the exact
  SHA, re-enforces the allowlist gate, re-verifies (secret scan + build), and pushes with
  `AUTOFIX_TOKEN`; plus a `flag-human-review` job. claude-code-action **SHA-pinned
  v1.0.148** (CVE-2025-66032). `scripts/check-fix-allowlist.py` is the shared gate.
- **`templates/fix-loop/` + `templates/workflows/`**: thin caller workflows (privilege
  boundary: `ai-autofix` label + non-fork + trusted reviewer), pinned `uses:`.

### Added — runners, in-session loop, setup

- **Lefthook is the default local runner** (`templates/lefthook/lefthook.yml`), calling
  the SAME dispatcher scripts; **pre-commit kept as a supported alternative**.
- **Claude Code in-session bundle** (`templates/claude/`): `PostToolUse` scans each
  edited file (exit 2 → self-correct), `Stop` runs the shared `scan-and-fix` guarded by
  `stop_hook_active`. Shared `scripts/scan-and-fix.{ps1,sh}`.
- **One-command `setup-scan-fix.{ps1,py}`**: idempotent; writes config from a tier
  template, installs the runner + bundle + caller workflows, creates labels, VERIFIES
  (never creates) secrets, runs verify-scanning. `render-scan-config.py` renders configs.
- **`docs/SECURITY-MODEL.md`, `docs/FIX-LOOP.md`, `docs/APP-CODE-SCANNING.md`,
  `docs/MIGRATION-ANALYSIS.md`, `docs/CONSUMER-MIGRATION.md`**; `specs/002-scan-fix-platform/`.

### Changed

- **All third-party actions SHA-pinned** across this repo's own workflows
  (`terraform-security-scan.yml` was on `@v4`/`@master`).
- **`.gitattributes`** enforces LF on shell scripts (Unix/CI execution).
- Tier templates extended with app-code + `fix_loop` defaults
  (`templates/scan-config/{starter,standard,strict}.yaml`).

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
