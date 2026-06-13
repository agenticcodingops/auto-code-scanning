# AI Agent Integration Guide

How to integrate automated agents with the security scanning solution.

> **v2.0.0 — two layers.** This repo is now a reusable **scan→fix platform**, not
> just a scanner. **Layer A** is scanning (Terraform *plus* app-code: C#/.NET,
> TypeScript/JS, SQL). **Layer B** is an optional **agentic fix-loop**. For agents,
> the two most important additions are the **in-session Claude Code bundle**
> (`templates/claude/`, which self-corrects edits *inside the session*) and the
> **CI fix-loop** (`.github/workflows/autonomous-fix.yml`). The `scan.py` interface
> below is unchanged. Everything is configured in one file, `scan-config.yaml`.
> **Pin consumers to `@v2.0.0` (or a SHA) — never `@main`.**

## Overview

The scanning solution provides several integration paths:

1. **Pre-commit / Lefthook hooks**: Run automatically on `git commit` / `git push`
   (developer workflow). Lefthook is the default local runner in v2.0.0; pre-commit
   remains a supported alternative. Both call the same `hooks/dispatcher.sh` scripts.
2. **scan.py**: Programmatic scanning interface for automated agents (agent workflow)
3. **In-session Claude Code bundle** (`templates/claude/`): hooks that scan an agent's
   edits *inside the same session* so Claude self-corrects before committing (Layer A/B
   bridge — see [In-Session Self-Correction](#in-session-self-correction-claude-code-bundle))
4. **CI fix-loop** (`autonomous-fix.yml`): an opt-in, hardened workflow where an agent
   proposes a minimal fix for a labelled PR (Layer B — see [CI Fix-Loop](#ci-fix-loop-autonomous-fixyml))

The first two paths produce the same JSON output format, enabling consistent tooling.

## scan.py Usage

### Basic Scanning

```bash
# Scan current directory with default settings
python scripts/scan.py

# Scan a specific directory
python scripts/scan.py terraform/

# JSON output for programmatic consumption
python scripts/scan.py --format json

# Filter by severity
python scripts/scan.py --severity CRITICAL,HIGH

# Specify cloud provider (auto-detected by default)
python scripts/scan.py --cloud-provider aws
```

### Auto-Fix Workflow

```bash
# Scan and apply Checkov auto-fixes
python scripts/scan.py --auto-fix

# Scan with auto-fix, output JSON for agent consumption
python scripts/scan.py --auto-fix --format json
```

When `--auto-fix` is specified:
1. Checkov runs with the `--fix` flag
2. Fixable findings are remediated in-place (Terraform files modified)
3. The report indicates which findings were fixed vs. unfixable
4. The agent can then commit the fixes and re-scan

### All Options

| Argument | Default | Description |
|----------|---------|-------------|
| `directory` | `.` | Directory to scan (positional) |
| `--format` | `text` | Output format: `text` or `json` |
| `--severity` | `CRITICAL,HIGH` | Comma-separated severity filter |
| `--auto-fix` | off | Apply Checkov `--fix` for fixable findings |
| `--output-file` | `.scanning/last-scan.json` | JSON output file path |
| `--cloud-provider` | auto-detect | `aws`, `azure`, or `gcp` |
| `--tools` | `trivy,checkov` | Comma-separated list of tools to run |
| `--skip-baseline` | off | Ignore baseline filtering |
| `--skip-suppressions` | off | Ignore suppression filtering |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No findings above threshold |
| `1` | Findings detected above threshold |
| `2` | Tool error (fail-open: couldn't determine findings) |

## JSON Output Format

scan.py writes results to `.scanning/last-scan.json` (configurable via `--output-file`). The schema is defined in `schemas/last-scan.schema.json`.

### Example Output

```json
{
  "scan_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "scan_timestamp": "2026-02-10T14:30:00Z",
  "directory": "terraform/",
  "cloud_provider": "aws",
  "tools_executed": ["trivy", "checkov"],
  "severity_filter": ["CRITICAL", "HIGH"],
  "duration_ms": 4523,
  "summary": {
    "total_findings": 3,
    "by_severity": {
      "CRITICAL": 1,
      "HIGH": 2,
      "MEDIUM": 0,
      "LOW": 0
    },
    "suppressed": 0,
    "baselined": 1,
    "auto_fix_applied": true,
    "auto_fix_count": 1
  },
  "findings": [
    {
      "id": "f1a2b3c4-d5e6-7890-abcd-ef1234567890",
      "tool": "checkov",
      "rule_id": "CKV_AWS_19",
      "severity": "CRITICAL",
      "original_severity": "CRITICAL",
      "title": "S3 bucket missing encryption",
      "file": "terraform/main.tf",
      "line": 42,
      "resource": "aws_s3_bucket.data",
      "remediation": "Add server_side_encryption_configuration block",
      "remediation_url": "https://docs.checkov.io/docs/CKV_AWS_19",
      "suppressed": false,
      "baseline": false,
      "fixable": true,
      "fixed": true,
      "detected_by": ["checkov"]
    },
    {
      "id": "a9b8c7d6-e5f4-3210-abcd-ef0987654321",
      "tool": "trivy",
      "rule_id": "AVD-AWS-0107",
      "severity": "HIGH",
      "original_severity": "HIGH",
      "title": "Security group allows unrestricted ingress",
      "file": "terraform/main.tf",
      "line": 58,
      "resource": "aws_security_group.web",
      "remediation": "Restrict ingress CIDR blocks",
      "suppressed": false,
      "baseline": false,
      "fixable": false,
      "fixed": false,
      "detected_by": ["trivy"]
    }
  ]
}
```

### Key Fields for Agents

| Field | Usage |
|-------|-------|
| `summary.total_findings` | Quick pass/fail check |
| `summary.auto_fix_count` | Number of findings automatically remediated |
| `findings[].fixable` | Whether the agent can auto-fix this finding |
| `findings[].fixed` | Whether auto-fix was already applied |
| `findings[].file` + `findings[].line` | Exact location for manual remediation |
| `findings[].remediation` | Human-readable fix guidance |
| `findings[].remediation_url` | Link to detailed documentation |
| `findings[].rule_id` | Stable identifier for suppression or baseline |

## Typical Agent Workflow

### 1. Initial Scan

```bash
python scripts/scan.py --format json --severity CRITICAL,HIGH
```

### 2. Read Results

Parse `.scanning/last-scan.json` and categorize findings:
- **Fixable**: `fixable == true` -- can be auto-remediated
- **Unfixable**: `fixable == false` -- requires manual intervention or suppression

### 3. Auto-Fix

```bash
python scripts/scan.py --auto-fix --format json
```

Review `fixed` field in each finding to confirm remediation.

### 4. Verify Fixes

```bash
python scripts/scan.py --format json --severity CRITICAL,HIGH
```

Confirm `summary.total_findings` decreased after fixes.

### 5. Handle Remaining Findings

For unfixable findings, the agent can:
- Add entries to `.scan-suppressions.yaml` (with business justification)
- Create baseline entries via `scripts/create-baseline.ps1`
- Flag for human review

## In-Session Self-Correction (Claude Code bundle)

The **core feature for autonomous Claude Code loops** is the in-session bundle in
`templates/claude/`. `setup-scanning` / `setup-scan-fix` copies it into a consumer
repo as `.claude/settings.json` + `.claude/hooks/`. It scans the agent's own edits
*as it makes them* so Claude fixes findings **in the same session**, before anything
is committed — no PR round-trip required.

`.claude/settings.json` wires two Claude Code hooks (cross-platform via `pwsh`; `.sh`
twins exist for hosts without PowerShell 7):

| Hook | Matcher / fires | What it does | Exit code |
|------|-----------------|--------------|-----------|
| **PostToolUse** | `Write\|Edit\|MultiEdit` | Scans **only the edited file** by language — Semgrep `p/csharp` for `.cs`, `p/typescript` for `.ts/.tsx/.js/.jsx` — plus a single-file secret check (`trivy fs --scanners secret`) on every edit | `2` = surface findings on stderr so Claude self-corrects in-session; `0` = clean |
| **Stop** | when Claude tries to finish | Runs the shared `scripts/scan-and-fix.{ps1,sh}` (default scan type `secrets`) as a **final gate**, guarded by `stop_hook_active` so it blocks **at most once** per stop-chain (no loops) | `2` = block "done", list findings; `0` = allow finishing |

The hooks are deliberately **thin** — they route to the right tool/ruleset and the
heavy logic lives in the versioned shared scripts (`scripts/scan-and-fix.{ps1,sh}`
and `hooks/`). They **fail open** if a tool (semgrep/trivy) is missing, so a
developer without the tools is never hard-blocked, but **fail closed** on real
findings.

### How an agent experiences it

1. Claude writes/edits a `.cs` or `.ts` file.
2. **PostToolUse** scans just that file. If Semgrep or the secret check finds an
   issue, the hook exits `2` and the findings are fed back to Claude on stderr —
   Claude reads them and edits again, looping until the file is clean.
3. When Claude signals it's done, **Stop** runs the shared `scan-and-fix` secret
   gate over the working tree. On findings it exits `2`, blocks completion, and
   writes machine-readable findings to `.claude/scan-findings.json` for the agent
   to act on. `stop_hook_active` ensures this can only block once.

### Escape hatches (for noisy local environments)

| Env var | Effect |
|---------|--------|
| `CC_SKIP_SEMGREP_HOOK=1` | Skip the per-file Semgrep scan in PostToolUse |
| `CC_SKIP_SECRET_HOOK=1` | Skip the per-file secret scan in PostToolUse |
| `CC_STOP_SCAN_TYPE=secrets\|semgrep\|all` | Choose the Stop gate scan (default `secrets`) |
| `SEMGREP_RULESET_CSHARP` / `SEMGREP_RULESET_TYPESCRIPT` | Override the ruleset (e.g. point at custom rules) |

> Keep `.claude/settings.json` and `.claude/hooks/` in the **consumer** repo. They
> are listed in `fix_loop.gated_paths`, so the autonomous CI fix-loop can never
> modify them.

## CI Fix-Loop (autonomous-fix.yml)

`.github/workflows/autonomous-fix.yml` is a reusable (`workflow_call`) **Layer B**
workflow: on an **opt-in** PR (labelled `ai-autofix`) an agent proposes the minimal
code change that resolves genuine flagged defects, then the workflow re-verifies and
pushes it. It is **off by default** — it runs only when `fix_loop.enabled: true` in
`scan-config.yaml` **and** the PR carries the `ai-autofix` label.

It is a hardened **two-job design** that deliberately breaks the "lethal trifecta"
(untrusted input + write credentials + egress never share a job):

| Job | Context | Token | What it does |
|-----|---------|-------|--------------|
| **analyze** | untrusted PR/review text | **read-only**, no push creds, no egress | Runs `claude-code-action` with a scoped tool allowlist; treats every PR/review/issue comment as **untrusted data** (never as instructions); emits a vetted **patch artifact** only |
| **apply-and-push** | trusted artifact only | `AUTOFIX_TOKEN` (push) | Re-checks out the **exact analyzed SHA**, re-enforces the allowlist gate via `scripts/check-fix-allowlist.py`, re-verifies the **secret scan + `build_verify_cmd`**, bumps `.fix-attempts`, and pushes |
| **flag-human-review** | — | issues/PR write | Labels `needs-human-review` and comments on cap / gate / failure |

Key guarantees for an agent operating in this flow:

- **Allowlist, not denylist**: only files under `fix_loop.allowlist_paths` may be
  auto-fixed, and any path matching a `fix_loop.gated_paths` substring
  (`auth`, `payment`, `crypto`, `.github/`, `.claude/`, `hooks`, `scripts/`, …) is
  **never** auto-fixed even inside an allowlisted dir. A patch touching, e.g.,
  `.github/` is gated → `needs-human-review`.
- **Hard iteration cap**: `fix_loop.max_iterations` (tracked in `.fix-attempts`).
  On cap the PR is flagged `needs-human-review` instead of looping forever.
- **`claude-code-action` is SHA-pinned to v1.0.148** (`>= 1.0.93`, fixes
  CVE-2025-66032 / GHSA-xq4m-mc3c-vvg3). This pin is the single source of truth and
  must match `fix_loop.claude_code_action_ref`.

The full threat model and the two-job rationale are in
[SECURITY-MODEL.md](SECURITY-MODEL.md).

### One-file configuration

Both layers are driven by **one file, `scan-config.yaml`**:

- `languages.*` — enable Terraform / `csharp` / `typescript` / `sql` scanning; the
  `csharp` block carries `build.solution` / `build.working_dir` so the dotnet path is
  solved by config, never hardcoded.
- `fix_loop.*` — `enabled`, `label`, `human_review_label`, `max_turns`,
  `max_iterations`, `allowlist_paths`, `gated_paths`, `claude_code_action_ref`,
  `build_verify_cmd`, `required_secrets`.

One-command onboarding installs the runner (Lefthook by default), the in-session
`.claude` bundle, and the caller workflows:

```bash
python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard --enable-fix-loop
# PowerShell twin: scripts/setup-scan-fix.ps1
```

## Cloud Provider Auto-Detection

When `--cloud-provider` is not specified, scan.py auto-detects the provider by:
1. Checking `.scanning/configs/` for provider-specific files
2. Scanning Terraform provider blocks in `.tf` files

This is intentional for local/agent use. In CI (reusable-scan.yml), the cloud provider is always required explicitly for deterministic behavior.

## Integration with Pre-Commit Hooks

scan.py and pre-commit hooks share the same `.scanning/last-scan.json` output path. The last writer wins. This means:

- After a `git commit`, `.scanning/last-scan.json` contains results from the last pre-commit hook that ran
- After running `python scripts/scan.py`, it contains scan.py results

Agents should run scan.py directly rather than relying on hook output for comprehensive results.

## Suppression and Baseline Filtering

By default, scan.py applies both suppression and baseline filtering:

- **Suppressions**: Findings matching entries in `.scan-suppressions.yaml` are marked `suppressed: true` and excluded from the total count
- **Baselines**: Findings matching entries in `.scan-baseline/baseline.json` are marked `baseline: true` and excluded from the total count

Use `--skip-suppressions` and `--skip-baseline` to see all raw findings regardless of governance state.
