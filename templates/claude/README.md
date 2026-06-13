# Claude Code in-session bundle (`templates/claude/`)

This is the **friction-free core** of the platform: a thin, per-repo Claude Code
layer that scans the agent's edits *inside the session* and self-corrects before
anything is committed.

`setup-scanning` copies these into a consumer repo as:

```
.claude/
├── settings.json              # wires PostToolUse + Stop hooks
└── hooks/
    ├── posttooluse-scan.ps1   # per-file scan after each Write/Edit (exit 2 -> self-correct)
    ├── posttooluse-scan.sh    # bash twin
    ├── stop-scan.ps1          # final gate before "done" (guarded by stop_hook_active)
    └── stop-scan.sh           # bash twin
```

## How it works

| Hook | Fires | What it does | Exit code |
|------|-------|--------------|-----------|
| **PostToolUse** | after `Write\|Edit\|MultiEdit` | scans ONLY the edited file by language (`p/csharp`, `p/typescript`) + a secret check | `2` = surface findings to Claude for in-session fixing; `0` = clean |
| **Stop** | when Claude tries to finish | runs the shared `scan-and-fix` (default `secrets`) as a final gate; guarded by `stop_hook_active` so it blocks at most once | `2` = block "done", list findings; `0` = allow |

**Heavy logic stays in versioned shared scripts** (`scripts/scan-and-fix.{ps1,sh}` +
`hooks/`); these copied files are deliberately thin so a consumer can read them at a glance.

## Cross-platform

`settings.json` uses `pwsh` (PowerShell 7 — cross-platform). On a host without
`pwsh`, point the commands at the `.sh` twins instead, e.g.:

```json
"command": "bash .claude/hooks/posttooluse-scan.sh"
```

## Escape hatches (for noisy local environments)

- `CC_SKIP_SEMGREP_HOOK=1` — skip the per-file Semgrep scan
- `CC_SKIP_SECRET_HOOK=1` — skip the per-file secret scan
- `CC_STOP_SCAN_TYPE=secrets|semgrep|all` — choose the Stop gate scan (default `secrets`)
- `SEMGREP_RULESET_CSHARP` / `SEMGREP_RULESET_TYPESCRIPT` — override the ruleset (custom rules)

> Keep `.claude/settings.json` and `.claude/hooks/` in the **consumer** repo. They are
> in `fix_loop.gated_paths`, so the autonomous fix-loop can never modify them.
