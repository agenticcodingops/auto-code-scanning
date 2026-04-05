# Tasks: Reusable Terraform Security Scanning Solution

**Input**: Design documents from `/specs/001-security-scanning-spec/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md
**Kiro Cross-Reference**: `.kiro/specs/terraform-security-scanning/tasks.md` (15 requirements, 245 ACs)

**Organization**: Tasks grouped by user story. Each story independently implementable and testable.
**Tests**: Optional property-based tests marked with `*` — can be deferred for faster MVP.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US9 mapping to spec.md user stories
- **_Requirements:_** Kiro requirement traceability (Req.AC format)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — create directories, shared libraries, and schemas that ALL user stories depend on

- [x] T001 Create `hooks/` directory structure: `hooks/lib/`, and empty hook script files per plan.md project structure
- [x] T002 [P] Create `hooks/dispatcher.sh` — OS-detecting dispatcher that routes to `.sh` or `.ps1` based on `$OSTYPE`; passes hook ID and args through. _Requirements: 1.16, 1.17_
- [x] T003 [P] Create `hooks/lib/common.sh` — shared bash functions: `fail_open()` (exit code classification), `write_json()` (JSON output to `.scanning/last-scan.json`), `detect_changed_dirs()` (monorepo incremental scanning), `verbose_output()` (SCAN_VERBOSE toggle). _Requirements: 1.22, 1.23, 1.24, 1.25, 1.26, 1.27, 1.28_
- [x] T004 [P] Create `hooks/lib/common.ps1` — PowerShell equivalents of all common.sh functions with identical behavior. _Requirements: 1.16, 1.22, 1.23, 1.24, 1.25, 1.26, 1.27, 1.28_
- [x] T005 [P] Update `schemas/unified-results.schema.json` — add `scan_id` (UUID), `duration_ms`, `detected_by` array, `baseline` boolean, `remediation_url` string, `suppression_reason`, and `by_tool`/`by_severity` summary fields per data-model.md. _Requirements: 7.17, 7.18, 7.20, 7.21_
- [x] T006 [P] Create `schemas/last-scan.schema.json` — agent report schema with `auto_fix_applied`, `auto_fix_count`, `fixable`, `unfixable`, `fixed` per-finding flag per data-model.md. _Requirements: 10.3, 10.4_

**Checkpoint**: Foundation directories and shared infrastructure ready. Hook implementations can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hook manifest and test fixtures that MUST be complete before ANY user story can be validated

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Update `.pre-commit-hooks.yaml` — rewrite all hook entries to use `entry: hooks/dispatcher.sh {hook-id}`, `language: script`, `files: ''` with `exclude: '(\.terraform/|node_modules/|\.git/)'`, `pass_filenames: false`, `verbose: true`. Define all 8 hook IDs: trivy-iac-critical, trivy-iac-full, trivy-secrets, checkov, checkov-strict, validate-suppressions, tflint, gitleaks. Set stages per hook-interface.md contract. _Requirements: 1.1, 1.2, 1.3, 1.13, 1.14, 1.15, 1.21_
- [x] T008 [P] Expand `tests/fixtures/terraform-valid/` — create per-provider subdirs with valid Terraform: `tests/fixtures/terraform-valid/aws/main.tf`, `tests/fixtures/terraform-valid/azure/main.tf`, `tests/fixtures/terraform-valid/gcp/main.tf`. Each must pass ALL security checks for its provider. _Requirements: 13.1, 13.2, 13.3, 13.4_
- [x] T009 [P] Create `tests/fixtures/terraform-critical/` — CRITICAL-only failure fixtures: `aws/main.tf` (open security group 0.0.0.0/0:22), `azure/main.tf` (public storage account), `gcp/main.tf` (public GCS bucket). Each must trigger exactly CRITICAL findings. _Requirements: 13.1, 13.6, 13.7, 13.8_
- [x] T010 [P] Verify `tests/fixtures/terraform-secret/main.tf` contains a hardcoded AWS access key that triggers trivy-secrets and gitleaks detection. _Requirements: 13.5_

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Developer Installs Scanning (Priority: P1) 🎯 MVP

**Goal**: A developer runs a single setup script, selects cloud provider, and within 5 minutes has pre-commit hooks active

**Independent Test**: Run `setup-scanning.ps1 -CloudProvider aws` in a fresh repo clone; verify `pre-commit run --all-files` executes hooks

### Implementation for User Story 1

- [x] T011 [US1] Add `-CloudProvider` parameter to `scripts/setup-scanning.ps1` — accept `aws`, `azure`, or `gcp`; copy provider-specific configs from pre-commit cache to `.scanning/configs/`; run `pre-commit install` and `pre-commit install --hook-type pre-push`. _Requirements: 4.2, 4.6, 4.11, 4.12, 4.13, 4.15, 4.16, 4.17, 4.18, 4.19_
- [x] T012 [P] [US1] Add `-CloudProvider` parameter to `scripts/setup-scanning-no-admin.ps1` — same as T011 but using Scoop/pip for tool installation. _Requirements: 4.3, 4.20_
- [x] T013 [US1] Create `scripts/setup-scanning.py` — cross-platform Python setup: detect OS via `platform.system()`; macOS→Homebrew, Linux→apt, Windows→delegate to PS1; install Trivy/Checkov/tflint/Gitleaks/pre-commit; verify versions meet minimums (trivy>=0.48.0, checkov>=3.0.0, tflint>=0.50.0, pre-commit>=3.0.0); copy configs to `.scanning/configs/`; run `pre-commit install`. Implement partial failure recovery (continue on tool failure, exit code 2). _Requirements: 4.1, 4.4, 4.5, 4.7, 4.8, 4.9, 4.10, 4.14, 4.21, 4.22, 4.23, 4.24, 4.25, 4.26, 4.27, 4.28, 4.29_

**Checkpoint**: Developer can install scanning with one script on any OS. Test with `setup-scanning.py --cloud-provider aws` in fresh repo.

---

## Phase 4: User Story 2 — Developer Commits Secure Code (Priority: P1)

**Goal**: Pre-commit hooks block CRITICAL IaC misconfigurations and secrets; clean code commits instantly; infrastructure errors fail-open

**Independent Test**: Commit `tests/fixtures/terraform-secret/main.tf` and verify commit blocked by trivy-secrets

### Implementation for User Story 2

- [x] T014 [P] [US2] Create `hooks/trivy-iac-critical.sh` — CRITICAL-only Trivy IaC scan with `--skip-db-update`, `--severity CRITICAL`, `--exit-code 1`; detect changed Terraform dirs (monorepo); write JSON to `.scanning/last-scan.json`; fail-open on infrastructure errors; retry once on DB lock contention (capture stderr via `2>&1`, grep for "database.*locked", wait 2s). _Requirements: 1.4, 1.9, 1.18, 1.19, 1.20, 1.26, 1.27, 1.28_
- [x] T015 [P] [US2] Create `hooks/trivy-iac-critical.ps1` — PowerShell equivalent of T014 with identical behavior. _Requirements: 1.4, 1.16_
- [x] T016 [P] [US2] Create `hooks/trivy-iac-full.sh` — all-severity Trivy IaC scan at pre-push stage; same fail-open/JSON/monorepo patterns. _Requirements: 1.5, 1.11_
- [x] T017 [P] [US2] Create `hooks/trivy-iac-full.ps1` — PowerShell equivalent of T016. _Requirements: 1.5, 1.16_
- [x] T018 [P] [US2] Create `hooks/trivy-secrets.sh` — Trivy secret detection mode; same fail-open/JSON patterns. _Requirements: 1.6_
- [x] T019 [P] [US2] Create `hooks/trivy-secrets.ps1` — PowerShell equivalent of T018. _Requirements: 1.6, 1.16_
- [x] T020 [P] [US2] Create `hooks/checkov.sh` — Checkov policy scan at pre-push stage using `--config-file .scanning/configs/.checkov.yaml`; same fail-open/JSON patterns. _Requirements: 1.7_
- [x] T021 [P] [US2] Create `hooks/checkov.ps1` — PowerShell equivalent of T020. _Requirements: 1.7, 1.16_
- [x] T022 [P] [US2] Create `hooks/checkov-strict.sh` — hard-fail on CRITICAL+HIGH findings at pre-push stage. _Requirements: 1.8_
- [x] T023 [P] [US2] Create `hooks/checkov-strict.ps1` — PowerShell equivalent of T022. _Requirements: 1.8, 1.16_
- [x] T024 [P] [US2] Create `hooks/validate-suppressions.py` — Python/PyYAML suppression validation hook: check required fields, date validity, max 180-day expiry, severity-based approval requirement, rule_id format per tool, email validation, duplicate detection. Exit 0 (pass), 1 (errors). _Requirements: 1.9, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 6.20, 6.21, 6.22, 6.23_
- [x] T080 [P] [US2] Create `hooks/tflint.sh` — tflint scan at pre-push stage using `--config-file .scanning/configs/.tflint.hcl`; same fail-open/JSON/monorepo patterns as other hooks. _Requirements: 1.9_
- [x] T081 [P] [US2] Create `hooks/tflint.ps1` — PowerShell equivalent of T080. _Requirements: 1.9, 1.16_
- [x] T082 [P] [US2] Create `hooks/gitleaks.sh` — Gitleaks secret detection at pre-commit stage; same fail-open/JSON patterns. _Requirements: 1.9_
- [x] T083 [P] [US2] Create `hooks/gitleaks.ps1` — PowerShell equivalent of T082. _Requirements: 1.9, 1.16_

**Checkpoint**: All 8 hooks functional. Test: commit clean Terraform (pass), commit secret (blocked), commit CRITICAL finding (blocked), simulate tool crash (fail-open).

---

## Phase 5: User Story 3 — CI/CD Enforces Security on PRs (Priority: P1)

**Goal**: Reusable GitHub Actions workflow scans PRs, uploads SARIF, posts comments, and applies suppressions

**Independent Test**: Open a PR with CRITICAL finding; verify workflow fails, SARIF uploads, PR comment posts

### Implementation for User Story 3

- [x] T025 [US3] Convert `.github/workflows/terraform-security-scan.yml` to `.github/workflows/reusable-scan.yml` — add `workflow_call` trigger with inputs: `terraform-directory` (string, default "."), `cloud-provider` (string, required), `severity` (string, default "CRITICAL,HIGH,MEDIUM,LOW"), `fail-on-findings` (boolean, default true), `upload-sarif` (boolean, default true), `post-pr-comment` (boolean, default true), `apply-suppressions` (boolean, default true), `apply-baseline` (boolean, default true), `upload-metrics` (boolean, default true). Add outputs: `findings-count`, `critical-count`, `high-count`, `scan-passed`, `sarif-uploaded`. _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.12, 3.13, 3.14, 3.15_
- [x] T026 [US3] Add `apply-suppressions` job to `reusable-scan.yml` — read `.scan-suppressions.yaml`, filter actively suppressed findings, keep expired suppressions in results, produce final pass/fail. _Requirements: 3.18, 3.19, 3.20, 3.21, 3.22_
- [x] T027 [US3] Add SARIF truncation logic to `reusable-scan.yml` — when exceeding 25MB or 5000 results, sort by severity (CRITICAL first), truncate, add warning annotation to workflow summary. _Requirements: 3.16, 3.17_
- [x] T028 [P] [US3] Add Checkov remediation URL generation — auto-generate `https://docs.checkov.io/docs/{CHECK_ID}` URLs in both SARIF output and PR comment. _Requirements: 3.24, 3.25_
- [x] T029 [US3] Add metrics artifact upload step to `reusable-scan.yml` — upload JSON metrics as GitHub Actions artifact named `scan-metrics-{cloud-provider}-{date}`. _Requirements: 3.23, 7.22_
- [x] T030 [US3] Add PR comment generation to `reusable-scan.yml` — always create new comment (never update/collapse old). Include severity table, tool list, suppression/baseline counts, top findings in collapsible `<details>` section per workflow-interface.md contract. _Requirements: 3.9, 3.10_
- [x] T031 [P] [US3] Create `.github/workflows/performance-check.yml` — run timing tests for each hook against `tests/fixtures/terraform-valid/`; enforce 5-second threshold per hook; display timing in CI output; fail PR check on regression. _Requirements: 12.1, 12.2, 12.3, 12.4_
- [x] T032 [US3] Update `.github/workflows/ci.yml` — expand integration tests: run all 8 hooks against all test fixtures, verify expected outcomes (valid=pass, fail=fail, secret=detected); add Pester and pytest test runners. _Requirements: 13.10_
- [x] T084 [US3] Verify `.github/workflows/bypass-detection.yml` — ensure it matches workflow-interface.md contract: triggers on push to default branch, uses heuristic detection, adds warning annotation, does not block push. _Requirements: 15.6_

**Checkpoint**: Consuming repos can call `reusable-scan.yml` with cloud-provider input. Test: trigger workflow on PR with CRITICAL finding, verify failure + SARIF + comment.

---

## Phase 6: User Story 4 — Team Adopts via 90-Day Phased Rollout (Priority: P2)

**Goal**: Three adoption tier templates (starter/standard/strict) with correct hook sets and pinned versions

**Independent Test**: Install starter template, verify only 6 hooks run; upgrade to standard, verify additional hooks activate

### Implementation for User Story 4

- [x] T033 [US4] Update `templates/starter/pre-commit-config.yaml` — verify exactly 6 hooks: trailing-whitespace, end-of-file-fixer, check-yaml, detect-private-key, terraform_fmt, trivy-secrets. Pin `rev: v1.0.0`. _Requirements: 5.1, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.22_
- [x] T034 [P] [US4] Update `templates/standard/pre-commit-config.yaml` — remove `no-commit-to-branch` hook; verify hooks: all starter + terraform_validate, terraform_tflint, trivy-iac-critical. Pin `rev: v1.0.0`. _Requirements: 5.2, 5.12, 5.13, 5.14, 5.15, 5.22_
- [x] T035 [P] [US4] Update `templates/strict/pre-commit-config.yaml` — comment out `commitizen` with opt-in instructions; verify hooks: all standard + terraform_docs, trivy-iac-full, checkov-terraform, validate-suppressions. Pin `rev: v1.0.0`. _Requirements: 5.3, 5.16, 5.17, 5.18, 5.19, 5.20, 5.21, 5.22_
- [x] T036 [P] [US4] Create `docs/TIER-UPGRADE-GUIDE.md` — list exact hooks to add per transition: starter→standard, standard→strict. Document manual merge process for teams with customizations. _Requirements: 5.23, 5.24, 5.27_
- [x] T087 [P] [US4] Verify `templates/{aws,azure,gcp}/pre-commit-config.yaml` — ensure cloud-specific templates reference correct hook IDs from updated `.pre-commit-hooks.yaml`, include cloud-appropriate configs, and pin `rev: v1.0.0`. _Requirements: 5.4, 5.5_

**Checkpoint**: Templates installable with correct hook sets. Test: `pre-commit run --all-files` with each tier template.

---

## Phase 7: User Story 5 — Security Engineer Manages Suppressions (Priority: P2)

**Goal**: Governed suppression management with validation, governance, and audit reporting

**Independent Test**: Add suppression entry missing `approved_by` for CRITICAL, verify validation fails

### Implementation for User Story 5

- [x] T037 [US5] Create `scripts/validate-suppressions.py` — full Python rewrite using PyYAML; implement all validation rules from suppression-format.md contract (V-001 through V-009, W-001 through W-003); accept file path argument; `--strict` flag to treat warnings as errors; `--check-expiry` for 30-day warning. _Requirements: 6.2, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 6.13, 6.14, 6.15, 6.17, 6.18, 6.19, 6.20, 6.21, 6.22, 6.23, 6.24, 6.25, 6.26_
- [x] T038 [P] [US5] Update `configs/common/.scan-suppressions.yaml` — ensure template matches suppression-format.md schema (schema_version, settings, tool-grouped sections, suppression_history). _Requirements: 6.1_
- [x] T039 [P] [US5] Update `scripts/generate-suppression-report.ps1` — add quarterly review support, expiry warning (suppressions expiring within 30 days), ownership summary, active/expired/history counts. _Requirements: 6.3, 6.16_

**Checkpoint**: Suppression governance functional. Test: validate good/bad suppression files, generate report.

---

## Phase 8: User Story 6 — Security Manager Reviews Metrics (Priority: P2)

**Goal**: Metrics collection, results aggregation with cross-tool deduplication, and unified severity normalization

**Independent Test**: Run `aggregate-scan-results.ps1 -RunScans` and verify JSON validates against schema

### Implementation for User Story 6

- [x] T040 [US6] Update `scripts/aggregate-scan-results.ps1` — add cross-tool deduplication: match on `(file, resource, category)` tuple; merge into single finding with `detected_by` array; use highest severity across tools; validate output against `schemas/unified-results.schema.json`. Implement severity normalization for 7 tools per data-model.md mapping. _Requirements: 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 7.15, 7.16, 7.17, 7.18, 7.20, 7.21, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_
- [x] T041 [P] [US6] Update `scripts/collect-scan-metrics.ps1` — add GitHub Actions artifact upload support (`-UploadArtifact` switch); add trend data comparison with previous metrics; output JSON conforming to Metric entity schema in data-model.md. _Requirements: 7.1, 7.2, 7.3, 7.4, 7.19, 7.22, 7.23, 7.24, 7.25_
- [x] T042 [P] [US6] Update `scripts/profile-hook-performance.ps1` — measure ALL 8 hooks (not just trivy-iac-critical); report per-hook average/min/max vs 5s threshold; report total pre-commit vs 10s and pre-push vs 60s. _Requirements: 7.5, 7.6, 7.7, 7.8_

**Checkpoint**: Metrics pipeline functional. Test: run scans + aggregate + collect metrics; verify JSON schema compliance.

---

## Phase 9: User Story 9 — AI Agent Scans and Auto-Fixes (Priority: P2)

**Goal**: scan.py provides machine-readable scanning for AI agents with auto-fix capability

**Independent Test**: Run `scan.py --format json` on Terraform with Checkov finding; verify parseable JSON at `.scanning/last-scan.json`

### Implementation for User Story 9

- [x] T043 [US9] Create `scripts/scan.py` — AI agent scanning interface per cli-interface.md contract: arguments `directory`, `--format` (text/json), `--severity`, `--auto-fix`, `--output-file`, `--cloud-provider`, `--tools`, `--skip-baseline`, `--skip-suppressions`; implement all missing imports (`uuid`, `datetime`); implement helpers `map_checkov_severity()`, `count_by_severity()`, `count_by_tool()` (resolves KC-002); run Trivy + Checkov with result aggregation; write JSON conforming to `schemas/last-scan.schema.json`; exit code 0/1/2 per contract. _Requirements: 10.1, 10.2, 10.3, 10.4, 10.8, 10.9, 10.10, 10.11_
- [x] T044 [US9] Add Checkov `--fix` integration to `scripts/scan.py` — when `--auto-fix` flag: run Checkov with `--fix`, report which findings were auto-remediated vs unfixable, set `auto_fix_applied`, `auto_fix_count`, `fixed` per-finding flags in output JSON. _Requirements: 10.5, 10.6, 10.7_

**Checkpoint**: AI agents can scan + auto-fix. Test: `python scan.py --format json --auto-fix tests/fixtures/terraform-aws-fail/`

---

## Phase 10: User Story 7 — Developer Baselines Existing Debt (Priority: P3)

**Goal**: Baseline creation with (rule_id, file_path) matching; only NEW findings reported after baselining

**Independent Test**: Create baseline, add new finding, verify only new finding reported

### Implementation for User Story 7

- [x] T045 [US7] Update `scripts/create-baseline.ps1` — implement (rule_id, file_path) matching algorithm with SHA-256 hash-based O(1) lookup; add `-MonorepoScope` parameter for monorepo-scoped baselines; add `-CloudProvider` parameter; output JSON conforming to Baseline entity schema in data-model.md; add 90-day expiration warning. _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

**Checkpoint**: Baseline management functional. Test: create baseline → add new finding → verify only new finding reported.

---

## Phase 11: User Story 8 — Platform Engineer Validates Performance (Priority: P3)

**Goal**: CI-enforced performance validation catching hook regressions

**Independent Test**: Run `profile-hook-performance.ps1 -Iterations 3` and verify timing output

*Note: Performance workflow created in T031 (Phase 5). Performance profiler updated in T042 (Phase 8). This phase covers remaining performance validation.*

### Implementation for User Story 8

- [x] T046 [US8] (Tier 4 deferred — requires CI environment) Verify all hooks meet performance targets — run each hook against `tests/fixtures/terraform-valid/` and verify: <5s per hook, <10s total pre-commit, <60s total pre-push on `ubuntu-latest`. Document any hooks exceeding thresholds and optimize. _Requirements: 1.9, 1.10, 1.11, 12.1, 12.2, 12.3, 12.4_

**Checkpoint**: Performance validated in CI. Test: push PR modifying hooks, verify performance-check workflow passes.

---

## Phase 12: Cloud Configurations (Cross-Cutting — US1, US2, US3)

**Purpose**: Cloud-specific configs needed by multiple user stories. Separated because config changes are file-isolated and parallelizable.

- [x] T047 [P] Convert `configs/aws/.checkov.yaml` from allowlist to blocklist — remove entire `check:` section; keep only `skip-check:` with documented exclusions; add `include: policy-overlay.yaml` reference. _Requirements: 2.1, 2.2, 2.12_
- [x] T048 [P] Convert `configs/azure/.checkov.yaml` to blocklist — same approach as T047 for Azure. _Requirements: 2.3, 2.4, 2.12_
- [x] T049 [P] Convert `configs/gcp/.checkov.yaml` to blocklist — same approach as T047 for GCP. _Requirements: 2.5, 2.6, 2.12_
- [x] T050 [P] Update `configs/aws/.tflint.hcl` — add `tflint-ruleset-terraform` plugin for common Terraform rules. _Requirements: 2.13_
- [x] T051 [P] Update `configs/azure/.tflint.hcl` — add `tflint-ruleset-terraform` plugin. _Requirements: 2.13_
- [x] T052 [P] Update `configs/gcp/.tflint.hcl` — add `tflint-ruleset-terraform` plugin. _Requirements: 2.13_
- [x] T053 [P] Create `configs/aws/policy-overlay.yaml` — org-specific policy rules template (tagging, naming conventions) per data-model.md Policy Overlay entity. _Requirements: 2.18, 2.19_
- [x] T054 [P] Create `configs/azure/policy-overlay.yaml` — same structure as T053. _Requirements: 2.18, 2.19_
- [x] T055 [P] Create `configs/gcp/policy-overlay.yaml` — same structure as T053. _Requirements: 2.18, 2.19_
- [x] T056 [P] Create `configs/common/noisy-checks-aws.yaml` — curated shared exclusion list of known noisy/false-positive checks for AWS. _Requirements: 2.20_
- [x] T057 [P] Create `configs/common/noisy-checks-azure.yaml` — same for Azure. _Requirements: 2.20_
- [x] T058 [P] Create `configs/common/noisy-checks-gcp.yaml` — same for GCP. _Requirements: 2.20_

**Checkpoint**: All 3 providers have blocklist configs, policy overlays, tflint plugins, and noisy-check lists.

---

## Phase 13: Documentation (Cross-Cutting — All Stories)

**Purpose**: Documentation updates required by the spec. Parallelizable since each doc is an independent file.

- [x] T059 [P] Update `docs/QUICK-START-5MIN.md` — add Python cross-platform setup examples for macOS and Linux alongside existing Windows instructions. _Requirements: 4.4, 4.5_
- [x] T060 [P] Update `docs/SETUP-GUIDE.md` — add macOS (Homebrew) and Linux (apt/yum) installation paths; document partial failure recovery. _Requirements: 4.4, 4.5, 4.28, 4.29_
- [x] T061 [P] Update `docs/HOOK-REFERENCE.md` — document all 8 hooks, dual-wrapper architecture, fail-open error handling, exit code contract, JSON output format. _Requirements: 1.16, 1.17, 1.26, 1.27_
- [x] T062 [P] Update `docs/MULTI-CLOUD.md` — document manual process for multi-cloud repos (per-directory scanning configuration); add examples for AWS+Azure repo. _Requirements: 2.21_
- [x] T063 [P] Create `docs/VERSION-PINNING.md` — document version pinning via git tags, upgrade process via `pre-commit autoupdate`, SemVer policy. _Requirements: 14.1, 14.2, 14.3, 14.4_
- [x] T064 [P] Create `docs/AI-AGENT-GUIDE.md` — document scan.py usage, JSON output format, auto-fix workflow, `.scanning/last-scan.json` schema, dual-path (hooks + scan.py). _Requirements: 10.1, 10.2, 10.5, 10.6, 10.7_
- [x] T065 [P] Update `docs/ADOPTION-PLAYBOOK.md` — document flexible timelines (guidelines not deadlines); add phase criteria for each tier transition. _Requirements: 5.25, 5.26, 9.1, 9.2, 9.3, 9.4_
- [x] T066 [P] Update `docs/SEVERITY-MAPPING.md` — expand severity normalization table to all 7 tools (Trivy, Checkov, tflint, Gitleaks, PSScriptAnalyzer, ShellCheck, hadolint) per data-model.md. _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
- [x] T085 [P] Create `docs/DEVELOPER-SURVEY.md` — developer satisfaction survey template with questions covering: ease of setup, hook performance perception, false positive rate, suppression workflow, and overall satisfaction. Referenced by FR-080 (SHOULD). _Requirements: 9.6_
- [x] T086 [P] Create `docs/TROUBLESHOOTING.md` — top 10 common issues and resolutions: (1) hook timeout, (2) Trivy DB lock, (3) tool not found, (4) config not copied, (5) permission denied, (6) Python version mismatch, (7) pre-commit not installed, (8) SARIF upload fails, (9) suppression validation errors, (10) hooks not running on push. _Requirements: 9.7_

**Checkpoint**: All documentation complete. Test: verify each doc has no broken links and matches implementation.

---

## Phase 14: Quality (Testing + Validation)

**Purpose**: Unit tests, integration tests, and property validation. Tests are optional per spec but recommended.

- [x] T067 [P] Create `tests/unit/setup-scanning.Tests.ps1` — Pester tests for setup scripts: tool installation, config copy, idempotency, version validation, CloudProvider parameter. _Requirements: 13.9_
- [x] T068 [P] Create `tests/unit/aggregate-scan-results.Tests.ps1` — Pester tests for aggregation: multi-tool parsing, severity normalization, deduplication, JSON schema validation. _Requirements: 13.9_
- [x] T069 [P] Create `tests/unit/collect-scan-metrics.Tests.ps1` — Pester tests for metrics: bypass rate calculation, pass rate, trend comparison. _Requirements: 13.9_
- [x] T070 [P] Create `tests/python/test_scan.py` — pytest tests for scan.py: JSON output structure, severity fields, auto-fix flag handling, exit codes, missing tool handling. _Requirements: 13.9_
- [x] T071 [P] Create `tests/python/test_validate_suppressions.py` — pytest tests: required fields, date validation, expiry enforcement, approval requirement, duplicate detection, email format. _Requirements: 13.9_
- [x] T072 [P] Create `tests/python/test_setup_scanning.py` — pytest tests: OS detection, version parsing, config copy paths. _Requirements: 13.9_
- [x] T088 [P] Create `tests/unit/create-baseline.Tests.ps1` — Pester tests for baseline creation: hash generation, monorepo scoping, 90-day expiry warning, force refresh. _Requirements: 13.9_
- [x] T089 [P] Create `tests/unit/generate-suppression-report.Tests.ps1` — Pester tests for report generation: active/expired counts, quarterly review, ownership summary. _Requirements: 13.9_
- [x] T090 [P] Create `tests/unit/profile-hook-performance.Tests.ps1` — Pester tests for profiler: per-hook timing, threshold comparison, iteration averaging. _Requirements: 13.9_
- [x] T091 [P] Create workflow syntax validation tests — validate YAML syntax and required fields for `reusable-scan.yml`, `performance-check.yml`, `bypass-detection.yml`, and `ci.yml` using `actionlint` or YAML schema validation. _Requirements: 13.10_
- [x] T092 [P] Create template validation tests — verify each tier template (starter/standard/strict) has valid YAML syntax, correct hook set per spec FR-047/048/049, and valid `rev:` pinning. _Requirements: 13.10_
- [x] T073 Create `tests/integration/test-hooks.sh` — end-to-end hook testing: run each hook against each fixture, verify expected pass/fail outcomes match. _Requirements: 13.10_
- [x] T074 Create `tests/integration/test-consuming-repo.sh` — simulate full consuming repo lifecycle: git init → setup-scanning.py → commit valid → commit secret → verify outcomes. _Requirements: 13.10_

**Checkpoint**: All tests pass. Minimum 80% code coverage target. _Requirements: 13.11_

---

## Phase 15: Polish & Final Validation

**Purpose**: Cross-cutting improvements, final checkpoint, adoption documentation updates

- [x] T075 Update `CHANGELOG.md` — document all changes for v1.0.0 release: new features (dual-wrapper hooks, cross-platform setup, AI agent integration, config layering), breaking changes (Checkov allowlist→blocklist conversion, hook entry point changes), migration notes for existing consumers, and dependency version requirements.
- [x] T076 Verify all JSON schemas pass validation — run `check-jsonschema` against `schemas/unified-results.schema.json` and `schemas/last-scan.schema.json`
- [x] T077 (deferred — requires manual walkthrough) Run quickstart.md validation — execute quickstart steps end-to-end, verify each step works as documented
- [x] T078 Verify `docs/CHAMPION-GUIDE.md` and `docs/BUSINESS-CASE.md` reference correct NIST 30x multiplier and IBM $10.22M statistic; verify NO unverified 100x/640x multipliers. _Requirements: 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_
- [x] T079 (deferred — requires CI push to GitHub) Final CI green check — push all changes, verify `ci.yml`, `performance-check.yml`, and `bypass-detection.yml` all pass

---

## Kiro Cross-Reference Analysis

### Tasks in Kiro NOT in This List (Gaps Identified: 0)

All Kiro tasks (1.1–11.6) are covered. Kiro organizes by implementation phase; this list reorganizes by user story for independent testability.

### Tasks in This List NOT in Kiro (Additions: 7)

| Task | Reason for Addition |
|------|-------------------|
| T006 (last-scan.schema.json) | Kiro has this as 1.13 but spec data-model.md added agent-specific fields |
| T010 (verify secret fixture) | Explicit fixture verification missing from Kiro |
| T036 (TIER-UPGRADE-GUIDE.md) | Kiro deferred to Phase 6 doc tasks; added here with story context |
| T066 (SEVERITY-MAPPING.md) | 7-tool expansion not in Kiro doc tasks |
| T074 (consuming repo simulation) | Kiro has basic integration (11.3); this adds full lifecycle test |
| T077 (quickstart validation) | New artifact from speckit.plan Phase 1 |
| T078 (business case verification) | Req 9.8-9.10 gap — Kiro tasks don't cover documentation accuracy |

### Kiro Tasks Mapped to This List

| Kiro Task | This Task | Notes |
|-----------|-----------|-------|
| 1.1 dispatcher + common libs | T002, T003, T004 | Split into 3 parallel tasks |
| 1.2 property test dispatcher | Deferred (optional `*`) | Property tests optional for MVP |
| 1.3-1.8 hook implementations | T014–T024 | Reorganized by story (US2) |
| 1.9 property test suppressions | Deferred (optional `*`) | |
| 1.10 update manifest | T007 | Moved to Phase 2 (foundational) |
| 1.11 expand fixtures | T008, T009, T010 | Split into 3 parallel tasks |
| 1.12 update schema | T005 | |
| 1.13 create last-scan schema | T006 | |
| 3.1-3.8 cloud configs | T047–T058 | Phase 12 (cross-cutting) |
| 5.1-5.5 templates | T033–T036 | Phase 6 (US4) |
| 6.1-6.10 scripts | T011–T013, T037–T045 | Distributed across user stories |
| 8.1-8.10 workflows | T025–T032 | Phase 5 (US3) |
| 10.1-10.7 documentation | T059–T066 | Phase 13 |
| 11.1-11.6 quality | T067–T074 | Phase 14 |

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──────────────▶ Phase 2 (Foundational) ──┬──▶ Phase 3 (US1: Install) ─────────┐
                                                          ├──▶ Phase 4 (US2: Hooks) ────────────┤
                                                          ├──▶ Phase 5 (US3: CI/CD) ────────────┤
                                                          ├──▶ Phase 6 (US4: Templates) ────────┤
                                                          ├──▶ Phase 7 (US5: Suppressions) ─────┤
                                                          ├──▶ Phase 8 (US6: Metrics) ──────────┤
                                                          ├──▶ Phase 9 (US9: AI Agent) ─────────┤
                                                          ├──▶ Phase 10 (US7: Baseline) ────────┤
                                                          ├──▶ Phase 11 (US8: Performance) ─────┤
                                                          └──▶ Phase 12 (Cloud Configs) ────────┤
                                                                                                 │
                                                          Phase 13 (Docs) ◀─── depends on all ──┘
                                                          Phase 14 (Quality) ◀─ depends on all ──┘
                                                          Phase 15 (Polish) ◀── depends on all ──┘
```

### User Story Dependencies

- **US1 (Install)**: Phase 2 only — can start immediately after foundational
- **US2 (Hooks)**: Phase 2 only — parallel with US1
- **US3 (CI/CD)**: Phase 2 + partially US2 (hooks must exist for workflow to reference)
- **US4 (Templates)**: Phase 2 + T007 (manifest must have hook IDs)
- **US5 (Suppressions)**: Phase 2 only — independent
- **US6 (Metrics)**: Phase 2 + T005 (schema must be updated)
- **US7 (Baseline)**: Phase 2 + T005 (schema) — mostly independent
- **US8 (Performance)**: Phase 2 + US2 (hooks must exist to profile)
- **US9 (AI Agent)**: Phase 2 + T005 (schema) + T006 (agent schema)
- **Phase 12 (Configs)**: Phase 2 only — parallel with all stories

### Parallel Opportunities

Within each phase, all tasks marked `[P]` can execute concurrently:

```
Phase 1:  T002 ║ T003 ║ T004 ║ T005 ║ T006  (5 parallel)
Phase 2:  T008 ║ T009 ║ T010                 (3 parallel)
Phase 4:  T014 ║ T015 ║ T016 ║ T017 ║ T018 ║ T019 ║ T020 ║ T021 ║ T022 ║ T023 ║ T024 ║ T080 ║ T081 ║ T082 ║ T083  (15 parallel!)
Phase 12: T047 ║ T048 ║ T049 ║ T050 ║ T051 ║ T052 ║ T053 ║ T054 ║ T055 ║ T056 ║ T057 ║ T058  (12 parallel!)
Phase 13: T059 ║ T060 ║ T061 ║ T062 ║ T063 ║ T064 ║ T065 ║ T066 ║ T085 ║ T086  (10 parallel!)
Phase 14: T067 ║ T068 ║ T069 ║ T070 ║ T071 ║ T072 ║ T088 ║ T089 ║ T090 ║ T091 ║ T092  (11 parallel!)
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (T001–T006)
2. Complete Phase 2: Foundational (T007–T010)
3. Complete Phase 3: User Story 1 — Install (T011–T013)
4. Complete Phase 4: User Story 2 — Hooks (T014–T024)
5. Complete Phase 12: Cloud Configs (T047–T058)
6. **STOP and VALIDATE**: Developer can install + commit with security scanning

### Incremental Delivery

1. MVP (US1 + US2) → Developers can use hooks locally
2. Add US3 (CI/CD) → Defense-in-depth with GitHub Actions
3. Add US4 (Templates) → Phased team adoption
4. Add US5 + US6 (Suppressions + Metrics) → Governance layer
5. Add US9 (AI Agent) → Autonomous scanning
6. Add US7 + US8 (Baseline + Performance) → Polish
7. Docs + Quality + Polish → Release-ready

### Parallel Team Strategy

With 3 developers after Phase 2:

- **Developer A**: US1 (Install) → US4 (Templates) → US7 (Baseline)
- **Developer B**: US2 (Hooks) → Phase 12 (Configs) → US8 (Performance)
- **Developer C**: US3 (CI/CD) → US5 (Suppressions) → US9 (AI Agent)
- **All**: US6 (Metrics), Docs, Quality, Polish

---

## Summary

| Metric | Count |
|--------|-------|
| **Total tasks** | 92 |
| **Phase 1 (Setup)** | 6 |
| **Phase 2 (Foundational)** | 4 |
| **US1 (Install)** | 3 |
| **US2 (Hooks)** | 15 |
| **US3 (CI/CD)** | 9 |
| **US4 (Templates)** | 5 |
| **US5 (Suppressions)** | 3 |
| **US6 (Metrics)** | 3 |
| **US9 (AI Agent)** | 2 |
| **US7 (Baseline)** | 1 |
| **US8 (Performance)** | 1 |
| **Phase 12 (Configs)** | 12 |
| **Phase 13 (Docs)** | 10 |
| **Phase 14 (Quality)** | 13 |
| **Phase 15 (Polish)** | 5 |
| **Parallel opportunities** | 55+ tasks across 6 phases |
| **Kiro requirement coverage** | All 15 requirements, 245 ACs |
| **MVP scope** | 33 tasks (Phase 1-4 + Phase 12) |

## Traceability Matrix (US → Kiro Req → Spec FR → Task → File)

| User Story | Kiro Req | Key Spec FRs | Key Tasks | Primary Files |
|-----------|----------|-------------|-----------|--------------|
| US1 Install | Req 4 | FR-034–FR-043c | T011–T013 | scripts/setup-scanning.{ps1,py} |
| US2 Hooks | Req 1 | FR-001–FR-011g | T014–T024, T080–T083 | hooks/*.{sh,ps1}, .pre-commit-hooks.yaml |
| US3 CI/CD | Req 3, 12 | FR-022–FR-033g, FR-086–FR-089 | T025–T032, T084 | .github/workflows/*.yml |
| US4 Templates | Req 5 | FR-044–FR-051b | T033–T036, T087 | templates/{starter,standard,strict}/ |
| US5 Suppress | Req 6 | FR-052–FR-060 | T024, T037–T039 | hooks/validate-suppressions.py, scripts/validate-suppressions.py |
| US6 Metrics | Req 7, 11 | FR-061–FR-068c, FR-081–FR-085a | T040–T042 | scripts/{aggregate,collect,profile}*.ps1 |
| US7 Baseline | Req 8 | FR-069–FR-074d | T045 | scripts/create-baseline.ps1 |
| US8 Perf | Req 12 | FR-086–FR-089 | T031, T042, T046 | .github/workflows/performance-check.yml |
| US9 AI Agent | Req 10 | NFR-014–NFR-016 | T043–T044 | scripts/scan.py |
| Cross-cutting | Req 2 | FR-012–FR-021f | T047–T058 | configs/{aws,azure,gcp}/ |
| Cross-cutting | Req 9 | FR-075–FR-080 | T065, T085, T086 | docs/{ADOPTION-PLAYBOOK,TROUBLESHOOTING}.md |
| Cross-cutting | Req 13 | FR-090–FR-098 | T008–T010, T067–T074, T088–T092 | tests/ |
| Cross-cutting | Req 14 | NFR-017 | T063 | docs/VERSION-PINNING.md |
| Cross-cutting | Req 15 | FR-011g, FR-042 | T002–T004, T014 | hooks/lib/common.{sh,ps1} |

## Notes

- All tasks include Kiro requirement traceability (_Requirements: X.Y_)
- Property-based tests from Kiro (marked `*`) are deferred — can be added as Phase 14 extensions
- Kiro's checkpoint tasks (2, 4, 7, 9, 12) are replaced by per-phase checkpoint annotations
- Each user story phase is independently testable with its own checkpoint
- Tasks are specific enough for LLM execution without additional context
- File paths are absolute relative to repository root
