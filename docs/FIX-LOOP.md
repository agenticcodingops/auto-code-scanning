# Fix-Loop (LAYER B) — the agentic scan→fix loop

The fix-loop is the optional second layer of the platform. It turns *detection* into
*remediation*: an AI agent proposes a minimal fix and the platform re-verifies and pushes
it, with safety enforced **mechanically** (not by trusting a prompt). It has two surfaces
you can adopt independently:

1. **In-session** (`templates/claude/`) — Claude Code fixes its own edits *before* they're
   ever committed. Lowest risk, highest day-to-day value. Adopt this first.
2. **CI** (`.github/workflows/autonomous-fix.yml`) — a hardened multi-job workflow fixes a PR
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
  build_verify_cmd: "cd api && dotnet build App.slnx --nologo"   # authoritative re-verify in the verify job (no secrets)
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

## 3. CI loop — the split-job workflow

`autonomous-fix.yml` (reusable `workflow_call`) reproduces the proven split-job design generically.
A consumer drops in the thin caller `templates/fix-loop/autonomous-fix.yml`, which owns the
privilege boundary and `uses:` the reusable workflow at a pinned tag.

```
   pull_request_review ──▶ caller `if:` (label + non-fork + trusted App or person)
                               │
                               ▼
   ┌──────────────┐   ┌──────────┐  patch +   ┌──────────────┐ result ┌────────────────────┐
   │ config       │──▶│ analyze  │──────────▶ │ verify       │──────▶ │ apply-and-push     │──▶ push
   │ (read config)│   │ read-only│  SHA-256   │ build, no    │  only  │ gate + scan + push │  (AUTOFIX)
   └──────────────┘   └──────────┘            │ secrets      │        │ no project code    │
                          │                   └──────────────┘        └────────────────────┘
                          │ cap/gate/fail (any job)
                          └──────────▶ flag-human-review
```

| Job | Token / secrets | Runs the PR's code? | Output |
|---|---|---|---|
| `config` | read-only | no (reads **base** ref) | trusted `fix_loop` config + its SHA-256 |
| `analyze` | **read-only**; model credentials in the agent step only | **no** (the agent reads and edits; it cannot build, test or run packages) | a patch artifact + its SHA-256 |
| `verify` | read-only, **no secrets**, **no Actions cache** | **yes** (`build_verify_cmd`) | pass/fail only |
| `apply-and-push` | **AUTOFIX_TOKEN** (push step only) | **no** | a commit pushed to the PR head |
| `flag-human-review` | issues/PR write | no | `needs-human-review` label + comment |

> **Trust boundary (hardened).** `fix_loop` config — `build_verify_cmd`, `allowlist_paths`,
> `gated_paths`, `max_iterations` — is read from the **base ref**, so a PR cannot change the gate
> or the executed build command via its own head diff. `build_verify_cmd` runs in the `verify`
> job, which holds **no secret** and hands the push job nothing but its result. `apply-and-push`
> runs no project code: it checks the artifacts' digests, builds one tree from the head and the
> patch, gates and secret-scans that tree, commits it with `git commit-tree`, and pushes that
> commit with hooks off; `AUTOFIX_TOKEN` is injected only into the final push URL. Point
> `build_verify_cmd` at a checked-in script under a gated path (e.g.
> `bash scripts/ci-build-verify.sh`) so it can't be altered in-PR either. See
> [SECURITY-MODEL.md](SECURITY-MODEL.md) §3, §7.1.

Key enforcement (all mechanical, independent of the prompt):
- `analyze` runs `claude-code-action` **FIX-ONLY** with a **scoped tool allowlist** (no umbrella
  `Bash`, no build, test, package or interpreter commands, no `WebSearch`/`WebFetch`, no
  `git push/commit`). The model credentials reach that step only. The agent's config files
  (`.claude/`, `.mcp.json`, `CLAUDE.md`, …) are removed from the checkout, and the session
  loads user-level settings only, with a workflow-owned tool guard and only the action's own MCP servers.
  The guard confines reads and writes to the checkout outside `.git`, resolves links and parent paths,
  and permits only the four exact PR read commands in the prompt. Links and nested agent configuration
  are removed before the session starts. Its Bun runtime is a checksum-verified download,
  never an Actions-cache entry. Before upload, a checksum-verified secret scanner checks the patch outside the checkout,
  without its configuration or ignore files. Findings, scanner errors and missing reports stop publication.
  The agent cannot build or test its fix; `verify` does that.
- The **allowlist gate** (`scripts/check-fix-allowlist.py`) runs in `analyze` **and again** in
  `apply-and-push` (defense in depth): a file must be inside `allowlist_paths` **and** clear of
  every `gated_paths` substring, else → `needs-human-review`. A patch that adds or changes a
  submodule entry is refused.
- `verify` checks out the **exact analyzed SHA**, applies the patch and runs `build_verify_cmd`.
  It runs with `cache-mode: none`: GitHub gives it a cache token that can neither save nor
  restore, so the build cannot leave a cache entry for another job or workflow, even on a
  `workflow_dispatch` run whose cache scope is the default branch. `actions/cache` and the
  `@actions/cache` toolkit skip a save the mode does not allow and carry on; another cache
  client may treat the refused request as an error and fail the build, which fails `verify`
  and stops the push. Keep `build_verify_cmd` free of Actions cache saves. The workflow sets
  `cache-mode: none` for its other jobs too, since none of them uses the cache.
- `apply-and-push` checks out the same SHA, re-gates and re-scans for secrets the exact tree it
  commits, bumps `.fix-attempts` (hard cap `max_iterations`), and pushes with `AUTOFIX_TOKEN`.
  It restores nothing from the Actions cache, which the PR's code can write to in other runs
  (for example the PR's own CI).
- The reusable workflow refuses to run for the shared `github-actions[bot]` identity, whatever
  the caller's `if:` says.

## 4. Enable it (checklist)

1. `setup-scan-fix … -EnableFixLoop` (creates labels, verifies secrets, copies the caller).
2. Create the two secrets in the consumer repo:
   - `AUTOFIX_TOKEN` — a **fine-grained PAT**: *Contents: RW, Pull requests: RW, that repo only*.
   - `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`).
   The platform **verifies** these via `gh secret list` — it never stores them.
3. Set `fix_loop.enabled: true` and tune `allowlist_paths` / `build_verify_cmd` for your repo.
4. Pin the caller's `uses:` and its `scanning_repo_ref` input to the current release. If
   you call your own copy of the platform, set `scanning_repo` to it as well. The template
   grants `contents: read`, `actions: read`, `pull-requests: write` and `issues: write`
   on its `fix` job, covering the reusable workflow's job-specific requests. Keep these
   grants when copying the caller: they are the called workflow's permission ceiling.
   Callers copied from v2.3.6 or earlier grant only `contents: read` by default;
   add all four grants under `jobs.fix.permissions` when using those releases.
   See [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#autonomous-fixyml).
5. Add the **`ai-autofix`** label to a PR. After a trusted review (CodeRabbit/SonarCloud or an
   OWNER/MEMBER/COLLABORATOR), the loop runs. A review or dispatch made with a workflow's
   `GITHUB_TOKEN` (the `github-actions[bot]` login) never starts it: give a review workflow its
   own GitHub App and list that App's `<app>[bot]` login in the caller's `if:` instead.

## 5. Operating the loop

- **Stuck PR?** It will carry `needs-human-review` with a comment explaining why (cap reached,
  gated path, build failed, secret detected, a changed artifact, or branch advanced). Fix it by hand, then reset
  `.fix-attempts` to `0`.
- **Tighten/loosen scope** by editing `allowlist_paths` / `gated_paths` (config is gated, so the
  loop can't widen its own scope).
- **Bump the agent version** deliberately: change `fix_loop.claude_code_action_ref` *and* the pin
  in `autonomous-fix.yml` together, and check that the release bundles Claude Code 1.0.93 or
  later (CVE-2025-66032 is a CLI flaw; the action's own version number does not tell you).
  See [VERSION-PINNING.md](VERSION-PINNING.md#the-centralized-claude-code-action-pin-layer-b) for every file to change.

## 6. Limits & non-goals

- The loop applies **small, targeted** fixes for genuine flagged defects — not refactors or
  feature work.
- It never touches security-sensitive areas, CI, hooks, secrets, or `LICENSE` (gated).
- It is **opt-in** and **capped**; on any doubt it defers to a human.
