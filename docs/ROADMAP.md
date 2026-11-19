# Roadmap

This page lists what each major version delivered and what may come next. The
[changelog](../CHANGELOG.md) is the exact record of every release. To adopt the
platform, start with [Getting started](SETUP-GUIDE.md).

> The v2 and v1 checklists below are historical. Some of their job, network and
> error-handling descriptions no longer match the code; the current references in the
> [documentation index](README.md) describe how it works today.

## v3 — shipped (v3.0.0 to v3.1.2)

v3.0.0 was a breaking release that made local and CI scans stricter and harder to
bypass by accident. Later v3 releases fixed bugs and added pin maintenance. Highlights,
from the [changelog](../CHANGELOG.md):

- **Incomplete scans block.** A scanner that fails, writes no report or writes an
  invalid one blocks the commit, push or CI run instead of passing (v3.0.0).
- **Push hooks scan what is pushed.** Pre-push hooks read Git's ref update and scan the
  exact commits being pushed, and only the files each pushed ref changes (v3.0.0, v3.0.1).
- **Trusted policy and exact approvals.** Pull-request scans read exceptions and
  baselines from the base commit. Suppressions and baselines use schema 2.0, where each
  approval covers one fingerprinted finding (v3.0.0). See
  [suppression governance](SUPPRESSION-GOVERNANCE.md).
- **Inline Checkov skips from the trusted base** are honoured when unchanged; new or
  edited skips stay visible until approved (v3.0.1, v3.0.2).
- **Hardened fix loop.** Agent file tools are confined to the source checkout, and the
  patch must pass a secret scan before upload (v3.0.3).
- **Verified scanner downloads.** CI installs Trivy from the GitHub release with a pinned
  checksum, and hooks check interpreter and scanner paths before running them
  (v3.0.3, v3.0.5).
- **Clearer platform requirements.** Hooks require Bash 4.4 or later; setup, scans and hooks decode tool
  and Git output as UTF-8 (v3.0.6 to v3.0.9).
- **Pin freshness report.** A weekly workflow reports hand-kept version pins that have
  newer upstream releases (v3.1.0). See [pin freshness](PIN-FRESHNESS.md).
- **Updated scanners and tooling** (v3.1.1, v3.1.2).

## v2.0.0 milestone — Reusable scan→fix platform

A major evolution from a Terraform-only, scan-only POC into a reusable, configurable,
multi-consumer **scan-AND-fix platform**. Terraform scanning is preserved unchanged.
**Pin consumers to a release tag or a SHA — never `@main`.** The current release is in [VERSION-PINNING.md](VERSION-PINNING.md).

### Delivered — Layer A: application-code scanning

- [x] **C#/.NET application scanning** (Semgrep `p/csharp`, `dotnet format`, `dotnet build` Roslyn analyzers) — `languages.csharp` in `scan-config.yaml`
- [x] **TypeScript/JavaScript application scanning** (Semgrep `p/typescript`, ESLint, Prettier) — `languages.typescript`
- [x] **SQL scanning** (SQLFluff) — `languages.sql`
- [x] App-code dispatcher hooks (`.sh` + `.ps1`): `semgrep-csharp`, `semgrep-typescript`, `dotnet-format`, `dotnet-build`, `eslint`, `prettier`, `sqlfluff`, `validate-scan-config` — registered in `.pre-commit-hooks.yaml`
- [x] Per-project `build.{solution,working_dir}` so the dotnet path is solved by **config, never hardcoded**
- [x] `code-security-scan.yml` reusable workflow — auto-detects enabled languages, uploads SARIF under **distinct categories** (post-2025-07 GitHub rule)
- [x] `schemas/scan-config.schema.json` + `scripts/validate-scan-config.py` (validated in a hook and in CI)

### Delivered — Layer B: agentic fix-loop (opt-in)

- [x] **In-session Claude Code bundle** (`templates/claude/`): `PostToolUse` per-file scan (exit 2 → in-session self-correct) + `Stop` final gate via shared `scan-and-fix` (guarded by `stop_hook_active`)
- [x] **`autonomous-fix.yml`** reusable two-job CI fix-loop: read-only `analyze` (no push creds, no egress, scoped tools, untrusted-text-as-data → patch artifact) + `apply-and-push` (re-checkout exact SHA, re-enforce allowlist gate, re-verify secret scan + `build_verify_cmd`, push with `AUTOFIX_TOKEN`) + `flag-human-review`
- [x] **`fix_loop:` config block** (`enabled`, `label`, `human_review_label`, `max_turns`, `max_iterations`, `allowlist_paths`, `gated_paths`, `claude_code_action_ref`, `build_verify_cmd`, `required_secrets`)
- [x] `scripts/check-fix-allowlist.py` shared allowlist gate (allowlist + fail-closed gated paths); opt-in per PR via `ai-autofix` label; hard `max_iterations` cap → `needs-human-review`
- [x] `claude-code-action` **SHA-pinned v1.0.148** (CVE-2025-66032 / GHSA-xq4m-mc3c-vvg3 is a Claude Code CLI flaw, fixed in CLI 1.0.93; the action's own version is unrelated)
- [x] `docs/SECURITY-MODEL.md` (two-job "lethal trifecta" threat model)

### Delivered — runners, setup, docs

- [x] **Lefthook is the default local runner** (`templates/lefthook/lefthook.yml`), calling the same dispatcher scripts; **pre-commit kept as a supported alternative**
- [x] One-command `setup-scan-fix.{ps1,py}` (idempotent: writes config from a tier template, installs runner + `.claude` bundle + caller workflows, creates labels, **verifies** secrets, runs verify-scanning)
- [x] Third-party actions SHA-pinned across this repo's own workflows, the semgrep image pinned by digest, and the Snyk CLI pinned to an exact version (see [VERSION-PINNING.md](VERSION-PINNING.md#third-party-action-pinning-this-repo))
- [x] Docs: `SECURITY-MODEL.md`, `FIX-LOOP.md`, `APP-CODE-SCANNING.md`, `CONSUMER-MIGRATION.md`; the migration analysis and `specs/002-scan-fix-platform/` (now in [archive/](../archive/README.md))
- [x] Tests: `tests/integration/test-app-code-hooks.sh`, `tests/python/test_check_fix_allowlist.py`, `tests/python/test_dotnet_format_path.py`

## v1.0.0

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

## Possible future work

These are plans, not commitments, and have no dates. Additional language plugins would
follow the same `languages.*` config pattern, dispatcher hooks and reusable workflows
as the existing languages. Config scaffolding already exists in `scan-config.yaml`
(disabled) for several of these:

- [ ] PowerShell scanning hooks (PSScriptAnalyzer)
- [ ] Shell/Bash scanning hooks (ShellCheck, shfmt)
- [ ] Docker scanning hooks (hadolint, Trivy image)
- [ ] Kubernetes manifest scanning (kubeconform, kube-linter)
- [ ] Python application scanning (bandit, black)
- [ ] Java application scanning (SpotBugs, checkstyle)

C#/.NET and JavaScript/TypeScript scanning, once planned as a separate repository,
were delivered in v2.0.0 as language plugins in this repository.

To suggest or discuss an item, open a feature request.
