# Fix-Loop (LAYER B) — the agentic scan→fix loop

The fix-loop is the optional second layer of the platform. It turns *detection* into
*remediation*: an AI agent proposes a minimal fix and the platform re-verifies and pushes
it, with safety enforced **mechanically** (not by trusting a prompt). It has two surfaces
you can adopt independently:

1. **In-session** (`templates/claude/`) — Claude Code fixes its own edits *before* they're
   ever committed. Lowest risk, highest day-to-day value. Adopt this first.
2. **CI** (`.github/workflows/autonomous-fix.yml`) — a hardened two-job workflow fixes a PR
   after a review. Opt-in per PR via the `ai-autofix` label.

Read **[SECURITY-MODEL.md](SECURITY-MODEL.md)** alongside this — it explains *why* each
control exists and what an attacker still cannot do.

---

## 1. Configure it in one place

Everything is driven by the `fix_loop:` block in `scan-config.yaml`:

```yaml
fix_loop:
  enabled: false                 # master switch (Layer B is off by default)
  label: "ai-autofix"            # PR opt-in label
  human_review_label: "needs-human-review"
  max_turns: 8                   # claude-code-action --max-turns per analyze run
  max_iterations: 3              # hard cap on autofix commits per PR (.fix-attempts)
  allowlist_paths: ["src/", "tests/", "app/", "lib/"]   # ONLY these may be auto-fixed
  gated_paths: ["auth","payment","crypto","security","identity","secret","credential",
                ".github/",".claude/","hooks","lefthook.yml","scan-and-fix.ps1","scripts/",".env","LICENSE"]
  claude_code_action_ref: "anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102"  # v1.0.148
  build_verify_cmd: "cd api && dotnet build App.slnx --nologo"   # authoritative re-verify in apply job
  required_secrets: ["AUTOFIX_TOKEN", "ANTHROPIC_API_KEY"]
```

The schema **requires** `allowlist_paths` and a SHA-pinned `claude_code_action_ref` whenever
`enabled: true`, so you can't ship an under-specified loop.

---

## 2. In-session loop (the friction-free core)

Copied into a consumer by `setup-scan-fix` as `.claude/`:

```
.claude/settings.json            # wires the hooks
.claude/hooks/posttooluse-scan.{ps1,sh}
.claude/hooks/stop-scan.{ps1,sh}
```

- **`PostToolUse`** (matcher `Write|Edit|MultiEdit`) scans *only* the file Claude just edited —
  Semgrep `p/csharp` / `p/typescript` by extension, plus a single-file secret check — and
  **exits 2** with the findings on stderr. Claude reads that and **fixes it in the same turn**.
- **`Stop`** runs the shared `scan-and-fix` (default scan type `secrets`) as a final gate. It is
  **guarded by `stop_hook_active`** so it blocks at most once per stop-chain (no infinite loop),
  and **exits 2** to keep Claude from declaring "done" while a secret is present.

Escape hatches for noisy local environments: `CC_SKIP_SEMGREP_HOOK=1`, `CC_SKIP_SECRET_HOOK=1`,
`CC_STOP_SCAN_TYPE=secrets|semgrep|all`, and `SEMGREP_RULESET_CSHARP` / `SEMGREP_RULESET_TYPESCRIPT`.

> `.claude/` is in `fix_loop.gated_paths`, so the CI loop can never modify the very hooks that
> guard the agent.

## 3. CI loop — the two-job workflow

`autonomous-fix.yml` (reusable `workflow_call`) reproduces the proven two-job design generically.
A consumer drops in the thin caller `templates/fix-loop/autonomous-fix.yml`, which owns the
privilege boundary and `uses:` the reusable workflow at a pinned tag.

```
   pull_request_review ──▶ caller `if:` (label + non-fork + trusted reviewer)
                               │
                               ▼
   ┌──────────────┐   patch    ┌───────────────────┐        ┌────────────────────┐
   │ config       │──▶│ analyze │───────────▶│ apply-and-push  │──▶ push (AUTOFIX) │
   │ (read config)│   │ read-only│  artifact  │ re-verify+gate  │                   │
   └──────────────┘   └──────────┘            └─────────────────┘                   │
                          │ cap/gate/fail            │                              │
                          └──────────▶ flag-human-review ◀──────────────────────────┘
```

| Job | Token | Sees untrusted input? | Egress? | Output |
|---|---|---|---|---|
| `config` | read-only | no (reads **base** ref) | no | trusted `fix_loop` config |
| `analyze` | **read-only** | yes (PR/review text, as DATA) | **no** | a patch artifact |
| `apply-and-push` | **AUTOFIX_TOKEN** (push step only) | **no** | no | a commit pushed to the PR head |
| `flag-human-review` | issues/PR write | no | no | `needs-human-review` label + comment |

> **Trust boundary (hardened).** `fix_loop` config — `build_verify_cmd`, `allowlist_paths`,
> `gated_paths`, `max_iterations` — is read from the **base ref**, so a PR cannot change the gate
> or the executed build command via its own head diff. In `apply-and-push` the checkout uses
> `persist-credentials: false`; the gate, secret scan, and `build_verify_cmd` run **token-free**,
> and `AUTOFIX_TOKEN` is injected only into the final push URL. Point `build_verify_cmd` at a
> checked-in script under a gated path (e.g. `bash scripts/ci-build-verify.sh`) so it can't be
> altered in-PR either. See [SECURITY-MODEL.md](SECURITY-MODEL.md) §3, §7.1.

Key enforcement (all mechanical, independent of the prompt):
- `analyze` runs `claude-code-action` **FIX-ONLY** with a **scoped tool allowlist** (no umbrella
  `Bash`, no `WebSearch`/`WebFetch`, no `git push/commit`). It emits a patch only.
- The **allowlist gate** (`scripts/check-fix-allowlist.py`) runs in `analyze` **and again** in
  `apply-and-push` (defense in depth): a file must be inside `allowlist_paths` **and** clear of
  every `gated_paths` substring, else → `needs-human-review`.
- `apply-and-push` re-checks out the **exact analyzed SHA** (no TOCTOU), re-scans changed files
  for secrets, runs `build_verify_cmd`, bumps `.fix-attempts` (hard cap `max_iterations`), and
  pushes with `AUTOFIX_TOKEN`.

## 4. Enable it (checklist)

1. `setup-scan-fix … -EnableFixLoop` (creates labels, verifies secrets, copies the caller).
2. Create the two secrets in the consumer repo:
   - `AUTOFIX_TOKEN` — a **fine-grained PAT**: *Contents: RW, Pull requests: RW, that repo only*.
   - `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`).
   The platform **verifies** these via `gh secret list` — it never stores them.
3. Set `fix_loop.enabled: true` and tune `allowlist_paths` / `build_verify_cmd` for your repo.
4. Pin the caller's `uses:` to `@v2.0.0`.
5. Add the **`ai-autofix`** label to a PR. After a trusted review (CodeRabbit/SonarCloud or an
   OWNER/MEMBER/COLLABORATOR), the loop runs.

## 5. Operating the loop

- **Stuck PR?** It will carry `needs-human-review` with a comment explaining why (cap reached,
  gated path, build failed, secret detected, or branch advanced). Fix it by hand, then reset
  `.fix-attempts` to `0`.
- **Tighten/loosen scope** by editing `allowlist_paths` / `gated_paths` (config is gated, so the
  loop can't widen its own scope).
- **Bump the agent version** deliberately: change `fix_loop.claude_code_action_ref` *and* the pin
  in `autonomous-fix.yml` together (keep ≥ v1.0.93). See [VERSION-PINNING.md](VERSION-PINNING.md).

## 6. Limits & non-goals

- The loop applies **small, targeted** fixes for genuine flagged defects — not refactors or
  feature work.
- It never touches security-sensitive areas, CI, hooks, secrets, or `LICENSE` (gated).
- It is **opt-in** and **capped**; on any doubt it defers to a human.
