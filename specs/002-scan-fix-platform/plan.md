# Plan 002 — Reusable scan→fix platform

Implementation plan for [spec.md](spec.md). Built in dependency order; each step validated
before the next. One feature branch, one PR to `main`, no merge.

## Phasing

| Step | Deliverable | Key files |
|---|---|---|
| 0 | Migration analysis (read this repo + PR #145) | `docs/MIGRATION-ANALYSIS.md` |
| 1 | Config seam | `scan-config.yaml` (+csharp/typescript/sql/fix_loop/ci.sarif), `schemas/scan-config.schema.json`, `scripts/validate-scan-config.py`, `templates/scan-config/{starter,standard,strict}.yaml` |
| 2 | App-code hooks | `hooks/{semgrep-csharp,semgrep-typescript,dotnet-format,dotnet-build,eslint,prettier,sqlfluff,validate-scan-config}.{sh,ps1}`, `hooks/lib/common.*` helpers, `.pre-commit-hooks.yaml`, `.gitattributes` |
| 2b | App-code CI | `.github/workflows/code-security-scan.yml` (distinct SARIF) |
| 3 | Runners + in-session | `templates/lefthook/lefthook.yml`, `templates/claude/**`, `scripts/scan-and-fix.{ps1,sh}` |
| 4 | Fix-loop | `.github/workflows/autonomous-fix.yml`, `scripts/check-fix-allowlist.py`, `templates/fix-loop/`, `templates/workflows/` |
| 5 | Setup | `scripts/setup-scan-fix.{ps1,py}`, `scripts/render-scan-config.py` |
| 6 | Versioning + trust | SHA-pin own workflows, `docs/SECURITY-MODEL.md`, `CHANGELOG` 2.0.0 |
| 7 | Reference consumer | `docs/CONSUMER-MIGRATION.md` |
| 8 | Docs + tests + spec | README + docs refresh, `docs/{FIX-LOOP,APP-CODE-SCANNING}.md`, tests, this spec |

## Key decisions

1. **Add `code-security-scan.yml` rather than overload `reusable-scan.yml`.** Keeps Terraform
   scanning untouched (R1) while app-code scanning evolves independently.
2. **`setup-scan-fix` is a NEW orchestrator**, not a rewrite of `setup-scanning`. The Terraform
   installer keeps its `-CloudProvider`-mandatory contract; the new script handles languages,
   tiers, runners, fix-loop, labels, and secret verification, and delegates where useful.
3. **The path gate is a standalone, testable script** (`check-fix-allowlist.py`) reused by both
   fix-loop jobs and the test suite — one source of truth for the allowlist (R7, R10).
4. **Deterministic test rule.** Tests point `SEMGREP_RULESET_*` at a local rule so they don't
   depend on volatile remote registry packs; the env override is also a real consumer feature.
5. **Config-driven dotnet path.** `languages.csharp.build.{solution,working_dir}` + a test that
   fails on any hardcoded path (R6).
6. **Centralized action pin.** `claude-code-action` SHA lives in `autonomous-fix.yml` and is
   mirrored in `fix_loop.claude_code_action_ref`; the schema enforces a 40-char SHA (R8).

## Validation performed

- `scan-config.yaml` + all three tier templates validate against the schema; conditional
  `fix_loop.enabled` requirements enforced (negative test).
- App-code hooks: end-to-end FAIL/PASS on planted fixtures, on **both** bash and PowerShell.
- Config reader + working-python finder (skips the broken Windows Store `python3` shim).
- `setup-scan-fix.py` onboarded a throwaway repo (config rendered, hooks vendored, lefthook
  installed, bundle+callers copied, labels attempted, secrets reported missing without creating,
  idempotent re-run).
- All third-party actions SHA-pinned (repo-wide audit clean).
- Full Python suite: **127 passed**, incl. gating + path tests; app-code integration 4/4.

## Out of scope / follow-ups

- PowerShell/Shell/Docker/Kubernetes/Python/Java plugins (present-but-disabled or future) follow
  the same pattern (see `docs/ROADMAP.md`).
- Live end-to-end run of `autonomous-fix.yml` requires a consumer repo with secrets + a GitHub
  runner; validated structurally here (perms, gates, pins, injection-clean).
