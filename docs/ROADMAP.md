# Roadmap

## v2.0.0 (Current Release) — Reusable scan→fix platform

A major evolution from a Terraform-only, scan-only POC into a reusable, configurable,
multi-consumer **scan-AND-fix platform**. Terraform scanning is preserved unchanged.
**Pin consumers to `@v2.0.0` (or a SHA) — never `@main`.**

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
- [x] `claude-code-action` **SHA-pinned v1.0.148** (`>= 1.0.93`, CVE-2025-66032 / GHSA-xq4m-mc3c-vvg3)
- [x] `docs/SECURITY-MODEL.md` (two-job "lethal trifecta" threat model)

### Delivered — runners, setup, docs

- [x] **Lefthook is the default local runner** (`templates/lefthook/lefthook.yml`), calling the same dispatcher scripts; **pre-commit kept as a supported alternative**
- [x] One-command `setup-scan-fix.{ps1,py}` (idempotent: writes config from a tier template, installs runner + `.claude` bundle + caller workflows, creates labels, **verifies** secrets, runs verify-scanning)
- [x] All third-party actions SHA-pinned across this repo's own workflows
- [x] Docs: `SECURITY-MODEL.md`, `FIX-LOOP.md`, `APP-CODE-SCANNING.md`, `MIGRATION-ANALYSIS.md`, `CONSUMER-MIGRATION.md`; `specs/002-scan-fix-platform/`
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

## Future

Additional language plugins follow the same `languages.*` config pattern, dispatcher
hooks, and reusable-workflow approach now established in v2.0.0. Config scaffolding
already exists in `scan-config.yaml` (disabled) for several of these:

- [ ] PowerShell scanning hooks (PSScriptAnalyzer)
- [ ] Shell/Bash scanning hooks (ShellCheck, shfmt)
- [ ] Docker scanning hooks (hadolint, Trivy image)
- [ ] Kubernetes manifest scanning (kubeconform, kube-linter)
- [ ] Python application scanning (bandit, black)
- [ ] Java application scanning (SpotBugs, checkstyle)

> **Note:** C#/.NET and JavaScript/TypeScript application scanning — originally
> planned here as a *separate* repository — were **delivered in v2.0.0** as Layer A
> language plugins in this repo (see above), alongside the agentic fix-loop (Layer B).
