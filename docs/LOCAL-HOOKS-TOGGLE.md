# Turning local scanning on/off

Local pre-commit / pre-push scanning (the lefthook hooks that run `hooks/dispatcher.sh`)
is **independent of CI**. You can pause it without uninstalling anything and without
affecting the reusable CI workflows or the fix-loop.

## The config switch (recommended)

`scan-config.yaml`:

```yaml
global:
  local_hooks_enabled: false   # default true; set false to skip ALL local hooks
```

`hooks/dispatcher.sh` checks this first and exits `0` immediately when it is `false`, so
**every** local pre-commit/pre-push hook is skipped in that repo. CI scanning
(`code-security-scan.yml` / `reusable-scan.yml`) and the agentic fix-loop are **not**
affected. Flip it back to `true` (or remove the line) to re-enable. Only an explicit
`false` disables — a missing key keeps scanning on.

Use this when in-progress work needs to commit/push without the hooks blocking it.

## Other quick toggles (no config change)

| Scope | Off | On |
|---|---|---|
| One command | `LEFTHOOK=0 git commit …` | (default) |
| Whole shell session | `export LEFTHOOK=0` | `unset LEFTHOOK` |
| Per-developer, file-based | add a gitignored `lefthook-local.yml` with `pre-commit: {skip: true}` and `pre-push: {skip: true}` | delete it |
| Remove the git-hook shims | `lefthook uninstall` | `lefthook install` |

## What is NOT covered by this switch

- **CI scanning** — separate workflows; disable by toggling the workflow or its triggers.
- **The fix-loop** — gated by the `ai-autofix` label + `fix_loop.enabled`; remove the
  label / set `fix_loop.enabled: false` to pause it.
- **Claude Code in-session hooks** (`.claude/hooks/*`) — session-only, not git hooks;
  skip via `CC_SKIP_BUILD_HOOK=1` / `CC_SKIP_SEMGREP_HOOK=1` or by editing `.claude/settings.json`.
