# Code Review Styleguide & Architectural Standards

This styleguide defines the architectural conventions, security boundaries, and coding standards for `auto-code-scanning`. All pull requests and automated reviews must evaluate incoming changes against these standards.

---

## 1. Architecture & Core Principles

- **Single Source of Truth (`scan-config.yaml`)**:
  - Scanning configuration across all four enforcement layers (pre-commit, pre-push, in-session agent hooks, and CI reusable workflows) must derive from `scan-config.yaml`.
  - Schema adherence is mandatory: changes to configuration structures must validate against `schemas/scan-config.schema.json`.
- **Defense in Depth**:
  - Local hooks shift enforcement left for developer velocity, but **CI is the authoritative gatekeeper**.
  - Local hooks must fail open on missing environment/infrastructure prerequisites, while CI reusable workflows fail closed.
- **Cross-Platform Parity**:
  - Scripts and tooling must support native Windows (PowerShell Core / Windows PowerShell 5.1) and Unix (Linux / macOS Bash).
  - Use `hooks/dispatcher.sh` as the OS-detecting entrypoint for local execution.

---

## 2. GitHub Actions & CI/CD Security

- **Action SHA Pinning**:
  - All external GitHub Actions in `.github/workflows/` must be pinned to full 40-character commit SHAs with semantic version comments (e.g., `uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`).
- **Reusable Workflow Semantics**:
  - Consumer references to reusable workflows (`reusable-scan.yml`, etc.) must always pin to a released tag (e.g., `@v2.3.0`) or a 40-character SHA—never `@main`.
  - Reusable workflows must maintain backward compatibility for consumer inputs and declare explicit `workflow_call` contracts.
- **Least-Privilege Permissions**:
  - Every workflow must declare top-level `permissions` explicitly with minimal required scopes (`contents: read`, etc.). Job-level escalations must be tightly scoped and justified.
- **SARIF Category Isolation**:
  - SARIF uploads to GitHub Code Scanning must use distinct category prefixes (`scan-trivy`, `scan-checkov`, `scan-semgrep`) to avoid clobbering findings across tools.

---

## 3. Trust Boundary & Autonomous Fix Loop (Layer B)

- **Strict Boundary Isolation**:
  - The autonomous fix loop must never execute arbitrary agent code with write credentials.
  - Fix generation and fix verification/pushing must remain strictly decoupled across separate jobs.
- **Allowlist & Path Verification**:
  - Only files matching approved path patterns may be touched by automated fixes (`test_autonomous_fix_trust_boundary.py` and `test_check_fix_allowlist.py` must pass).
  - Fixes must be gated behind explicit PR labels (e.g., `ai-autofix`) and dry-run validations.
- **Secret & Token Safety**:
  - Never log, echo, or expose GitHub tokens, API keys, or scanning credentials in workflow step outputs or script logs.

---

## 4. Python Standards (`scripts/`, `tests/python/`)

- **Language Level**: Python 3.10+ typed syntax.
- **Encoding Safety**:
  - Always specify `encoding="utf-8"` on all file read/write operations to avoid Windows `cp1252` encoding traps.
- **Defensive Subprocess Execution**:
  - Use `subprocess.run(..., check=True, text=True, capture_output=True)` with explicit error handling.
  - Never use `shell=True` when passing external or user-controllable inputs.
- **Testing Requirements**:
  - All script changes or new features must include unit and integration tests under `tests/python/` using `pytest`.
  - Ensure tests are isolated and clean up temporary test directories or fixtures.

---

## 5. Shell & PowerShell Scripting Standards

- **PowerShell (`.ps1`)**:
  - Must begin with `$ErrorActionPreference = 'Stop'`.
  - Use explicit parameter declarations with `[CmdletBinding()]` and typed parameters.
  - Avoid command aliases in script files (e.g., use `Get-ChildItem` instead of `gci`/`dir`, `Select-Object` instead of `select`).
- **Bash / Shell (`.sh`)**:
  - Must include `set -euo pipefail` near the top.
  - All variable expansions must be quoted to prevent word splitting and globbing.
  - Ensure POSIX compliance where portable execution across macOS and Linux is required.

---

## 6. Infrastructure-as-Code (Terraform) Standards

- **Policy Compliance**:
  - Terraform configurations and test fixtures must align with Checkov and TFLint policies in `configs/`.
  - No unrestricted network access (`0.0.0.0/0`) on ingress or egress without explicit justification.
  - Enforce minimum TLS versions (TLS 1.2+) and encryption at rest for storage, compute, and database resources.
- **Suppression Discipline**:
  - Suppressions in `.scan-suppressions.yaml` or `.trivyignore` must specify the exact rule ID, legitimate architectural justification, and an expiration date. Blind suppression of findings is prohibited.

---

## 7. Commit & PR Hygiene

- **Conventional Commits**: Format commit messages using conventional prefixes: `feat:`, `fix:`, `ci:`, `docs:`, `refactor:`, `test:`.
- **Branding & Metadata Guard**:
  - Do not include AI assistant names or robot emojis in commit messages, PR titles, or branch names.
  - Author and committer metadata must strictly match authorized project contributors.
