# Research: Reusable Terraform Security Scanning Solution

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Date**: 2026-02-10 | **Status**: Complete (all items resolved)

## Purpose

This document consolidates technical research performed during planning. All "NEEDS CLARIFICATION" items from the plan template were resolved during the deep interview (30 decisions) and speckit.clarify sessions (5 decisions). No outstanding research questions remain.

## Research Areas

### R-001: Hook Shell Architecture

**Question**: What shell strategy provides cross-platform hook execution?
**Resolution**: Dual-wrapper with OS-detecting dispatcher

| Option | Pros | Cons | Selected |
|--------|------|------|----------|
| Bash-only | Simple, Unix-native | Fails on Windows without WSL/Git Bash | No |
| PowerShell-only | Windows-native | Unavailable on default macOS/Linux | No |
| Python entry points | Cross-platform, no shell dependency | Slower startup, pre-commit already manages Python | No |
| **Dual .sh/.ps1 wrappers** | Full platform coverage, native performance | More files to maintain (~12 hook scripts) | **Yes** |

**Details**: Each hook has a `.sh` and `.ps1` implementation. `hooks/dispatcher.sh` detects the OS and routes to the appropriate script. The pre-commit framework invokes the dispatcher. On Windows Git Bash, the dispatcher detects PowerShell availability and calls the `.ps1` variant.

**Source**: Deep interview decision, Kiro design `dispatcher.sh` reference implementation.

### R-002: Checkov Configuration Strategy

**Question**: Should Checkov configs use an allowlist (explicit check IDs) or blocklist (skip-check) approach?
**Resolution**: Blocklist approach

| Option | Pros | Cons | Selected |
|--------|------|------|----------|
| **Allowlist** (current) | Precise control, no surprises | New checks ignored on upgrade; stale configs | No (migrate away) |
| **Blocklist** | New checks auto-activate; smaller config | Must track noisy checks to exclude | **Yes** |

**Details**: Current AWS config lists ~60 explicit `check:` IDs. Converting to blocklist means removing the `check:` section entirely and using only `skip-check:` for known-noisy or org-inapplicable checks. Shared `noisy-checks-{provider}.yaml` lists maintained in this repo reduce per-team curation.

**Impact**: All 3 provider configs (AWS, Azure, GCP) need conversion. Breaking change for consuming repos — document migration in CHANGELOG.

### R-003: Trivy Database Management

**Question**: How should Trivy DB freshness be balanced against hook performance?
**Resolution**: Skip locally, update in CI

| Context | DB Behavior | Rationale |
|---------|-------------|-----------|
| Pre-commit hooks | `--skip-db-update` | Performance (<5s target); DB updated via CI or manual `trivy image --download-db-only` |
| Pre-push hooks | `--skip-db-update` | Same rationale; push shouldn't block on network |
| CI workflows | Default (update DB) | CI has network, freshness matters for authoritative scan |

**Retry logic**: On Trivy DB lock contention (parallel hook execution), retry once after 2-second backoff. Detect via stderr grep for "database locked" pattern.

**Source**: Deep interview decision, Kiro design error handling patterns.

### R-004: Baseline Matching Algorithm

**Question**: What tuple should be used for matching baseline findings against current scan results?
**Resolution**: `(rule_id, file_path)` only — no line numbers

| Option | Pros | Cons | Selected |
|--------|------|------|----------|
| `(rule_id, file, line)` | Precise | Breaks on any refactoring that moves lines | No |
| `(rule_id, file, resource)` | Resource-aware | Resource names not always available (tflint) | No |
| **`(rule_id, file_path)`** | Refactoring-resilient, simple | May suppress different findings with same rule in same file | **Yes** |

**Details**: Baseline stored as set of `(rule_id, file_path)` hashes. O(1) lookup during scan. Multiple findings of the same rule in the same file are all considered baselined — acceptable tradeoff for resilience.

**Source**: Deep interview decision, Kiro design correctness property P-19.

### R-005: Cross-Platform Setup Script

**Question**: What language should the cross-platform setup script use?
**Resolution**: Python (setup-scanning.py)

| Option | Pros | Cons | Selected |
|--------|------|------|----------|
| PowerShell only | Windows-native, existing scripts | Requires PS7+ on macOS/Linux (not default) | No |
| Bash only | Unix-native | Fails on Windows | No |
| **Python** | Available everywhere (pre-commit requires it) | Another language in the project | **Yes** |

**Details**: Python is guaranteed available because pre-commit and Checkov both require it. The setup script detects the OS and uses: Homebrew (macOS), apt (Linux), delegates to existing PowerShell scripts (Windows). Version range enforcement (e.g., `trivy>=0.48.0`) via subprocess version check.

**Source**: Deep interview decision.

### R-006: Suppression Validation Language

**Question**: Should suppression validation stay in PowerShell or be rewritten?
**Resolution**: Rewrite in Python (PyYAML)

**Rationale**: PowerShell's `powershell-yaml` module is an extra dependency. Python's `PyYAML` is already required by Checkov. Cross-platform validation ensures the same behavior on all OSes. The validation is syntax-only (schema checks, expiry date validation) — no cross-reference to actual findings.

**Source**: Deep interview decision.

### R-007: Fail-Open Error Handling

**Question**: How should infrastructure errors (tool crashes, network failures, DB locks) be distinguished from actual security findings?
**Resolution**: Exit code classification

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| `0` | No findings | Allow |
| `1` | Security findings detected | Block (fail-closed) |
| Any other non-zero | Infrastructure error | Warn + allow (fail-open) |

**Details**: Each hook wrapper catches the underlying tool's exit code. If the tool returns an unexpected code (segfault, network error, etc.), the wrapper outputs a warning to stderr and exits 0. Only exit code 1 (explicitly set by the wrapper when findings exceed the severity threshold) blocks the commit.

**Source**: Deep interview decision, Kiro design error handling table.

### R-008: SARIF Truncation Strategy

**Question**: How should SARIF uploads handle GitHub's size limits?
**Resolution**: Priority-based truncation

| Limit | Value | Source |
|-------|-------|--------|
| File size | 25 MB | GitHub SARIF upload limit |
| Result count | 5,000 results | GitHub Code Scanning limit |

**Algorithm**: When either limit is exceeded: (1) sort findings by severity (CRITICAL first), (2) truncate to fit within limits, (3) add a `warning` level annotation noting truncation and total count. Low-severity findings are dropped first.

**Source**: Kiro design, FR-033c.

### R-009: AI Agent Integration Architecture

**Question**: How should AI coding agents consume scan results?
**Resolution**: Dual-path — hooks + standalone script

| Path | Entry Point | Trigger | Output |
|------|-------------|---------|--------|
| Git workflow | Pre-commit hooks | `git commit` | `.scanning/last-scan.json` |
| Direct invocation | `scripts/scan.py` | Agent calls directly | `.scanning/last-scan.json` + terminal summary |

**Details**: Both paths produce identical JSON output conforming to `schemas/last-scan.schema.json`. The `scan.py` script adds `--format json`, `--auto-fix` (Checkov `--fix`), and `--output-file` flags. Auto-fix modifies files in-place for Checkov-fixable checks; unfixable findings are reported for agent review.

**Source**: Deep interview decisions (3 questions on AI agent integration).

### R-010: Cross-Tool Deduplication

**Question**: How should duplicate findings across tools be handled?
**Resolution**: Match on `(file, resource, category)` tuple

**Details**: When multiple tools detect the same issue (e.g., Trivy and Checkov both flag unencrypted S3), findings are merged into a single result with a `detected_by` array listing all detecting tools. The highest severity across tools is used. This reduces noise in reports without losing tool coverage information.

**Source**: Kiro design, FR-067.

### R-011: Config Layering Strategy

**Question**: How should universal security checks be separated from organization-specific policy?
**Resolution**: Two-file layering per provider

| File | Purpose | Managed By |
|------|---------|------------|
| `.checkov.yaml` (skip-check only) | Universal security blocklist (noisy/inapplicable checks) | This repo (shared) |
| `policy-overlay.yaml` | Organization-specific rules (tagging, naming conventions) | Consuming repo replaces |

**Details**: The setup script copies both files. Consuming repos are expected to replace `policy-overlay.yaml` with their organization's standards. Universal security checks in `.checkov.yaml` are maintained centrally and inherited by all consumers.

**Source**: Deep interview decision, FR-020a.

### R-012: Version Pinning Strategy

**Question**: How strictly should tool versions be pinned?
**Resolution**: Minimum version ranges, not exact pins

| Tool | Minimum | Format |
|------|---------|--------|
| Trivy | >=0.48.0 | SemVer range |
| Checkov | >=3.0.0 | SemVer range |
| tflint | >=0.50.0 | SemVer range |
| pre-commit | >=3.0.0 | SemVer range |

**Rationale**: Exact pins create upgrade friction and don't reflect actual compatibility. Minimum ranges ensure required features are available while allowing patch/minor upgrades. The setup script validates versions at install time. Templates pin to a specific release tag (`rev: v1.0.0`) for reproducibility of *this repo's* hooks.

**Source**: Deep interview decision, NFR-017.

## Tool Compatibility Matrix

| Tool | macOS | Linux | Windows | Notes |
|------|-------|-------|---------|-------|
| Trivy | Homebrew | apt/snap | Chocolatey/Scoop | Standalone binary |
| Checkov | pip | pip | pip | Python package |
| tflint | Homebrew | curl install | Chocolatey | Standalone binary + plugins |
| Gitleaks | Homebrew | apt/snap | Chocolatey | Standalone binary |
| pre-commit | pip | pip | pip | Python package |
| PyYAML | pip | pip | pip | Python package (Checkov dep) |

## Decisions Log

| # | Decision | Rationale | Reversible |
|---|----------|-----------|------------|
| D-001 | Dual .sh/.ps1 wrappers | Full cross-platform coverage | Yes (can consolidate later) |
| D-002 | Blocklist Checkov configs | Auto-activate new checks | No (breaking change for consumers) |
| D-003 | Skip Trivy DB in hooks | Performance <5s target | Yes (flag change) |
| D-004 | (rule_id, file_path) baseline | Refactoring resilience | Yes (can tighten matching later) |
| D-005 | Python setup-scanning.py | Cross-platform guarantee | Yes (can add alternatives) |
| D-006 | Python suppression validation | Cross-platform PyYAML | Yes (keep PS1 as fallback) |
| D-007 | Fail-open error handling | Don't block developers for infra errors | Yes (can make strict mode) |
| D-008 | Priority SARIF truncation | GitHub limits are hard constraints | No (GitHub requirement) |
| D-009 | Dual agent paths (hooks + scan.py) | Flexibility for different workflows | Yes |
| D-010 | (file, resource, category) dedup | Noise reduction | Yes (can disable dedup) |
| D-011 | Two-file config layering | Separation of concerns | Yes (can merge) |
| D-012 | Minimum version ranges | Upgrade flexibility | Yes (can exact-pin later) |

## Open Questions

None. All 35 clarification decisions (5 from speckit.clarify + 30 from deep interview) have been encoded into the spec and plan.
