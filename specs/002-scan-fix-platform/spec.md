# Spec 002 — Reusable scan→fix platform

**Status:** Implemented (PR: `feat: reusable scan→fix platform`). **Supersedes scope of** 001
(Terraform scanning) by extending, not replacing, it.

## Problem

`auto-code-scanning` (spec 001) is a strong distribution machine for **Terraform-only,
scan-only** security. It cannot scan application code and cannot *fix* anything. We want a
reusable, configurable, multi-consumer **scan-AND-fix platform** — optimised for friction-free
autonomous Claude Code loops and public release — without losing working Terraform scanning.

## Goals

1. **App-code scanning (Layer A):** C#/.NET first, plus TypeScript/JS and SQL, implemented as
   plugins under the existing config-driven plugin/adapter design and dispatcher convention.
2. **Agentic fix-loop (Layer B):** port the proven two-job autonomous-fix design (workout-
   trackroutinely PR #145) generically, driven by config, opt-in and hardened.
3. **One config seam:** a single `scan-config.yaml` drives both layers, both runners, and CI.
4. **Lefthook default** local runner; pre-commit kept as a supported alternative; both invoke
   the same dispatcher scripts.
5. **One-command, idempotent onboarding** that verifies (never creates) secrets.
6. **Public-ready trust model:** allowlist gate, label opt-in, SHA-pinned actions, least
   privilege; everything documented.

## Non-goals

- Refactors/feature work by the fix-loop (it does minimal, targeted fixes only).
- Replacing Terraform scanning interfaces (they are preserved; consumers are new).
- Storing or provisioning any secret.

## Requirements (acceptance)

| # | Requirement | Verified by |
|---|---|---|
| R1 | Terraform scanning still works end-to-end | existing terraform fixtures + hooks unchanged |
| R2 | `scan-config.yaml` validates against `schemas/scan-config.schema.json`; tiers resolve | `validate-scan-config`, `test_*`, tier templates validate |
| R3 | csharp + typescript plugins run via BOTH Lefthook and pre-commit using the same dispatcher | `tests/integration/test-app-code-hooks.sh`; lefthook.yml + .pre-commit-hooks.yaml |
| R4 | Hooks stay < 15s on a sample change (staged-only, parallel) | hook design; Semgrep native-Windows |
| R5 | App-code scanners emit DISTINCT SARIF categories | `code-security-scan.yml` `<prefix>semgrep-<lang>` |
| R6 | `dotnet-format` path is config-driven, never hardcoded | `tests/python/test_dotnet_format_path.py` |
| R7 | analyze job has NO write token; apply enforces the allowlist + only pushes on the `ai-autofix` label | `autonomous-fix.yml` perms; caller `if:`; `check-fix-allowlist.py` |
| R8 | claude-code-action SHA-pinned ≥ v1.0.93 (CVE-2025-66032), centralized | `autonomous-fix.yml` pin + `fix_loop.claude_code_action_ref` + schema |
| R9 | Setup onboards a sample repo, creates labels, VERIFIES secrets | `setup-scan-fix.{ps1,py}` (tested against a throwaway repo) |
| R10 | Fix-loop gating: a patch touching `.github/` → needs-human-review; allowlist paths pass | `tests/python/test_check_fix_allowlist.py` |
| R11 | No secret, no consumer-specific path, no unpinned third-party action in the repo | repo-wide audit (all actions SHA-pinned) |

## Design summary

```
scan-config.yaml  (the seam)
├── languages.{terraform,csharp,typescript,sql}.{enabled,file_patterns,tools,build}
│     → local: Lefthook (default) | pre-commit (alt)  → hooks/dispatcher.sh → hooks/*.{sh,ps1}
│     → CI:    reusable-scan.yml (IaC) + code-security-scan.yml (app-code, distinct SARIF)
├── ci.sarif.category_prefix
└── fix_loop.{enabled,label,allowlist_paths,gated_paths,max_iterations,claude_code_action_ref,…}
      → in-session: templates/claude/ (.claude PostToolUse exit 2 / Stop guarded)
      → CI:         autonomous-fix.yml (analyze ▸ apply-and-push ▸ flag-human-review)
                    + templates/fix-loop/ caller (privilege boundary)
```

Plugins map onto the existing design (Config Loader → Scanner Engine → Results Aggregator →
Language Plugins → Tool Adapters): a "plugin" = a `languages.<lang>` block; a "tool adapter" =
a `hooks/<tool>.{sh,ps1}` pair sharing `hooks/lib/common`. See `docs/MIGRATION-ANALYSIS.md`.

## Risks & mitigations

See `docs/MIGRATION-ANALYSIS.md` §6 and `docs/SECURITY-MODEL.md`. Headlines: Terraform
preserved (additive); Windows/Semgrep native path + `PYTHONUTF8=1`; config-driven dotnet path;
two-job split + allowlist + label + SHA pins against prompt injection across the blast radius.
