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
  human_review_label: "needs-human-review"
  max_turns: 8                   # claude-code-action --max-turns per analyze run
  max_iterations: 3              # hard cap on autofix commits per PR (.fix-attempts)
  allowlist_paths: ["src/", "tests/", "app/", "lib/"]   # ONLY these may be auto-fixed
  gated_paths: ["auth","payment","crypto","security","identity","secret","credential",
                ".github/",".claude/","hooks","lefthook.yml","scan-and-fix.ps1","scripts/",".env","LICENSE"]
  claude_code_action_ref: "anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102"  # v1.0.148
  build_verify_cmd: "cd api && dotnet build App.slnx --nologo"   # authoritative re-verify in the verify job (no secrets)
```

The schema **requires** `allowlist_paths` and a SHA-pinned `claude_code_action_ref` whenever
`enabled: true`, so you can't ship an under-specified loop.

What the workflow actually reads in release v3.1.2 (the `config` job's `Parse fix_loop`
step): `enabled`, `max_turns`, `max_iterations`, `build_verify_cmd` and
`human_review_label`; the path gate reads `allowlist_paths` and `gated_paths`.
The action reference is a required mirror; two retired keys remain accepted for compatibility:

- `claude_code_action_ref` is only checked for format by the schema. The action version
  the loop runs is hard-coded in the `analyze` job's `Run Claude Code (FIX-ONLY)` step
  of the reusable workflow, so it changes only when you pin a newer platform release.
- `required_secrets` is deprecated and ignored; setup checks supported secret names directly.
- `label` is deprecated and ignored: the opt-in label `ai-autofix` is written into the caller
  template's `if:`. To use another label, change it there.

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
> patch, gates fix paths and secret-scans changed files from that tree, commits it with `git commit-tree`, and pushes that
> commit with hooks off; `AUTOFIX_TOKEN` is injected only into the final push URL. Point
> `build_verify_cmd` at a checked-in script under a gated path (e.g.
> `bash scripts/ci-build-verify.sh`) so the fix-loop's own generated patch cannot alter it.
> `verify` still runs PR-head code, so a PR's own commits can still change that script
> before the fix-loop runs; the gate protects against the agent, not against the PR itself.
> See [SECURITY-MODEL.md](SECURITY-MODEL.md) §3, §7.1.

Key enforcement (all mechanical, independent of the prompt):
- `analyze` runs `claude-code-action` **FIX-ONLY** with a **scoped tool allowlist** (no umbrella
  `Bash`, no build, test, package or interpreter commands, no `WebSearch`/`WebFetch`, no
  `git push/commit`). The model credentials reach that step only. The agent's config files
  (`.claude/`, `.mcp.json`, `CLAUDE.md`, …) are removed from the checkout, and the session
  loads user-level settings only, with a workflow-owned tool guard and only the action's own MCP servers.
  The guard confines reads and writes to the checkout outside `.git`, resolves links and parent paths,
  and permits only the four exact PR read commands in the prompt. Links and nested agent configuration
  are removed before the session starts. Its Bun runtime is a checksum-verified download,
  never an Actions-cache entry. Patch capture rejects binary files and any byte outside supported
  regular text, without printing the rejected content; links are removed earlier, from the pre-agent
  checkout, not rejected here. `apply-and-push` separately rejects a submodule entry, on the vetted
  tree it builds from the head and the patch. Diff generation disables
  external drivers and text conversion. Before upload, a checksum-verified secret scanner
  checks the patch outside the checkout,
  without its configuration or ignore files. Findings, scanner errors and missing reports stop artifact upload. After upload,
  `apply-and-push` scans changed, non-deleted files from the vetted tree under
  original and neutral filenames before pushing. This retains filename-sensitive
  detection without allowing default filename exclusions to hide those files.
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
- `apply-and-push` checks out the same SHA, re-gates fix paths and secret-scans added/modified files from the exact tree it
  commits, bumps `.fix-attempts` (hard cap `max_iterations`), and pushes with `AUTOFIX_TOKEN`.
  It restores nothing from the Actions cache, which the PR's code can write to in other runs
  (for example the PR's own CI).
- The reusable workflow refuses to run for the shared `github-actions[bot]` identity, whatever
  the caller's `if:` says.

A build runs only when the trusted base sets a nonempty `build_verify_cmd`.
The standard template leaves it empty, so a successful `verify` job alone does
not prove a build ran. Configure the reviewed command and inspect its step output
if build verification is required.

## 4. Enable it (checklist)

1. Run setup from the platform clone with the fix loop on, from your repository root:
   `python <platform-clone>/scripts/setup-scan-fix.py --languages <yours> --enable-fix-loop`
   (plus your usual `--tier`, `--cloud-provider` and `--hooks-runner`). It copies the
   caller to `.github/workflows/autonomous-fix.yml`, sets `fix_loop.enabled: true` in a
   newly written `scan-config.yaml`, and, if `gh` is installed and signed in, creates the
   `ai-autofix` and `needs-human-review` labels and checks that the secrets exist. It
   does not change an existing `scan-config.yaml` unless you add `--force`.
2. Create the secrets in your repository (see [Secrets](#secrets)). Setup only
   **checks** that they exist with `gh secret list`; it never reads or stores them.
3. Set `fix_loop.enabled: true` and tune `allowlist_paths` / `build_verify_cmd` for your repo.
   The loop reads this from the base branch, so merge it before you expect a run.
4. Pin the caller's `uses:` and its `scanning_repo_ref` input to the current release. If
   you call your own copy of the platform, set `scanning_repo` to it as well. The template
   grants `contents: read`, `actions: read`, `pull-requests: write` and `issues: write`
   on its `fix` job, covering the reusable workflow's job-specific requests. Keep these
   grants when copying the caller: they are the called workflow's permission ceiling.
   Callers copied from v2.3.6 or earlier grant only `contents: read` by default;
   add all four grants under `jobs.fix.permissions` when using those releases.
   See [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#autonomous-fixyml).
5. **Review the trusted reviewers** in the caller (see below), then add the **`ai-autofix`**
   label to a PR. After a review from a trusted bot or from an OWNER/MEMBER/COLLABORATOR,
   the loop runs. A review or dispatch made with a workflow's `GITHUB_TOKEN` (the
   `github-actions[bot]` login) never starts it: give a review workflow its own GitHub App
   and list that App's `<app>[bot]` login in the caller's `if:` instead.

> **Review these defaults before you enable the loop.** The caller template
> (`templates/fix-loop/autonomous-fix.yml`) lets a review or review comment from any of
> these GitHub App accounts start the loop on a labelled pull request:
> `coderabbitai[bot]`, `sonarqubecloud[bot]` and `sonarcloud[bot]`. It also trusts any
> user whose association with the repository is `OWNER`, `MEMBER` or `COLLABORATOR`.
> Each start can push a commit to the pull request's branch and spends model tokens on
> your account. To narrow it, edit the two `fromJSON('[...]')` bot lists in the `fix`
> job's `if:`: remove the Apps you do not use (both lists must match), or replace them
> with `[]` so that only people can start the loop. To trust fewer people, remove
> `MEMBER` or `COLLABORATOR` from the two association lists. Keep the
> `head.repo.full_name == github.repository` and `ai-autofix` label conditions.

## Secrets

Create these in your repository (Settings > Secrets and variables > Actions, or
`gh secret set NAME`, which prompts for the value):

| Secret | What to create |
|---|---|
| `AUTOFIX_TOKEN` (required) | A **fine-grained personal access token** with access to **only this repository** and **Contents: Read and write**. The reusable workflow uses it in exactly one step, a `git push` of the vetted commit to the pull request's branch; Contents write is what that push needs. Metadata read is automatic. Do not add Workflows access: fixes to workflow files are meant to fail. This narrow scope has not been tested on github.com. Set a short expiry and rotate it. A push made with the built-in `GITHUB_TOKEN` would not start your other workflows, which is why a separate token is used. |
| `ANTHROPIC_API_KEY` **or** `CLAUDE_CODE_OAUTH_TOKEN` | A model credential for the agent step. Only the `Run Claude Code (FIX-ONLY)` step receives it. Without one, the agent produces no patch and the run ends with no change. |

Setup checks `AUTOFIX_TOKEN` independently and accepts either `ANTHROPIC_API_KEY` or
`CLAUDE_CODE_OAUTH_TOKEN` for the model credential. It reports which names were found.
Organisation secrets are not listed; check their repository access separately. If
listing fails, setup says it could not verify secrets rather than reporting them missing.

**Cost.** Every run of the agent step uses the model credential you supply, so model
usage is billed to your Anthropic account (API key) or counts against your Claude
plan (OAuth token). `fix_loop.max_turns` caps the turns per run and
`fix_loop.max_iterations` caps the fix commits per pull request. The jobs also use
your GitHub Actions minutes. This project publishes no cost estimate; watch your
first runs.

## 5. Operating the loop

- **Stuck PR?** It will carry `needs-human-review` with a comment explaining why (cap reached,
  gated path, build failed, secret detected, a changed artifact, or branch advanced). Fix it by hand, then reset
  `.fix-attempts` to `0`.
- **Tighten/loosen scope** by editing `allowlist_paths` / `gated_paths` (config is gated, so the
  loop can't widen its own scope).
- **The agent version comes with the platform release.** The `claude-code-action` commit
  is fixed inside the reusable `autonomous-fix.yml`; your `scan-config.yaml` cannot change
  it. To get a newer agent, move your caller's `uses:` and `scanning_repo_ref` to a newer
  platform release. Editing `fix_loop.claude_code_action_ref` changes nothing at run time.
  Maintainers bumping the pin in this repository follow
  [VERSION-PINNING.md](VERSION-PINNING.md#the-centralized-claude-code-action-pin-layer-b).
- **Commit authorship.** Fix commits are authored and committed as
  `auto-code-scanning-autofix[bot] <autofix@auto-code-scanning.invalid>`.
  The address is non-routable, so it links to no account. Consumers whose rules require
  a linked author, a CLA or a co-author line may need an exception. A squash merge
  can add GitHub's own co-author line.

## 6. Limits & non-goals

- The loop applies **small, targeted** fixes for genuine flagged defects — not refactors or
  feature work.
- It never touches security-sensitive areas, CI, hooks, secrets, or `LICENSE` (gated).
- It is **opt-in** and **capped**; on any doubt it defers to a human.
