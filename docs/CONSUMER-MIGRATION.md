# Consumer Migration — adopting the platform (reference: workout-trackroutinely)

This guide shows how an existing repo that **inlined** the scan→fix machinery
(workout-trackroutinely, PR #145) switches to **consuming** `auto-code-scanning`
as a versioned platform. It is the proof that the platform reproduces the inline
design with **zero project specifics left in workflow YAML** — everything
consumer-specific moves into `scan-config.yaml`.

> Run these steps **in the consumer repo** (workout-trackroutinely). Do **not** open
> that repo's PR from this repository.

---

## 0. What changes (at a glance)

| Inline today (PR #145) | After migration |
|---|---|
| `.github/workflows/autonomous-fix.yml` (full two-job logic, ~250 lines) | thin **caller** (~30 lines) that `uses:` the reusable workflow `@v2.0.0` |
| Allowlist `api/src,api/tests,mobile` **baked into YAML** | `fix_loop.allowlist_paths` in `scan-config.yaml` |
| Sensitive denylist baked into YAML | `fix_loop.gated_paths` in `scan-config.yaml` |
| `api/`, `TrackRoutinely.slnx`, `dotnet build` baked into hooks/workflow | `languages.csharp.build.{solution,working_dir}` + `fix_loop.build_verify_cmd` |
| `lefthook.yml` calling tools directly | `lefthook.yml` calling shared `hooks/dispatcher.sh` |
| `.claude/` hooks (local) | **unchanged** — `.claude/` stays local per repo |
| claude-code-action pin maintained by hand | inherited from the platform's centralized pin |

Net effect: the consumer keeps **one config file** (`scan-config.yaml`) and a handful of
**thin, pinned callers**; all the hardened logic lives in the platform at a pinned tag.

---

## 1. Add `scan-config.yaml` with the project specifics

```yaml
# workout-trackroutinely/scan-config.yaml
schema_version: "1.0"
languages:
  csharp:
    enabled: true
    file_patterns: ["**/*.cs", "**/*.csproj", "**/*.slnx"]
    build:
      solution: "api/TrackRoutinely.slnx"   # <- was hardcoded in hooks; now config
      working_dir: "api"
    tools:
      dotnet_format:  { enabled: true, args: ["--verify-no-changes", "--no-restore"], stage: pre-commit }
      semgrep_csharp: { enabled: true, args: ["--config=p/csharp", "--error", "--metrics=off"], stage: pre-commit }
      dotnet_build:   { enabled: true, args: ["--nologo"], stage: pre-push }
  typescript:
    enabled: true            # mobile/ React Native
    build: { working_dir: "mobile" }
    tools:
      eslint:   { enabled: true, auto_fix: true, args: ["--fix"], stage: pre-commit }
      prettier: { enabled: true, auto_fix: true, args: ["--write"], stage: pre-commit }
      semgrep_typescript: { enabled: true, args: ["--config=p/typescript", "--error", "--metrics=off"], stage: pre-commit }
ci:
  sarif: { category_prefix: "scan-" }
fix_loop:
  enabled: true
  label: "ai-autofix"
  human_review_label: "needs-human-review"
  max_turns: 12            # PR #145 used --max-turns 12
  max_iterations: 3
  allowlist_paths: ["api/src/", "api/tests/", "mobile/"]   # <- was in YAML; now config
  gated_paths: ["auth", "payment", "crypto", "security", "identity", "secret", "credential",
                ".github/", ".claude/", "hooks", "lefthook.yml", "scan-and-fix.ps1", "scripts/", ".env", "LICENSE"]
  claude_code_action_ref: "anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102"
  build_verify_cmd: "cd api && dotnet build TrackRoutinely.slnx --nologo"
```

Validate it: `python scripts/validate-scan-config.py` (or just commit — the
`validate-scan-config` hook runs it).

## 2. Replace the inline `autonomous-fix.yml` with a thin caller

Delete the ~250-line inline workflow and drop in
`templates/fix-loop/autonomous-fix.yml`, adjusting the owner/labels if needed:

```yaml
# .github/workflows/autonomous-fix.yml  (now ~30 lines)
name: Autonomous Fix (caller)
on:
  pull_request_review: { types: [submitted] }
  pull_request_review_comment: { types: [created] }
  workflow_dispatch: { inputs: { pr_number: { required: true, type: string } } }
permissions: { contents: read }
jobs:
  fix:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      ( github.event.pull_request.head.repo.full_name == github.repository &&
        contains(github.event.pull_request.labels.*.name, 'ai-autofix') &&
        ( contains(fromJSON('["coderabbitai[bot]","sonarqubecloud[bot]","sonarcloud[bot]"]'), github.event.review.user.login) ||
          contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.review.author_association) ) )
    uses: agenticcodingops/auto-code-scanning/.github/workflows/autonomous-fix.yml@v2.0.0
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      scanning_repo_ref: v2.0.0
    secrets: inherit
```

The two-job analyze/apply logic, the allowlist gate, the secret re-scan, the
`.fix-attempts` cap, and the `flag-human-review` job now come from the platform.

## 3. Switch local hooks to the shared dispatcher

Replace the hand-written `lefthook.yml` commands that call tools directly with the
platform template (`templates/lefthook/lefthook.yml`), which calls
`hooks/dispatcher.sh <id>`. Vendor `hooks/` + shared `scripts/` via:

```powershell
# from the consumer repo root
path/to/auto-code-scanning/scripts/setup-scan-fix.ps1 `
  -Languages csharp,typescript -Tier strict -HooksRunner lefthook -EnableFixLoop
```

`setup-scan-fix` also creates the labels and **verifies** `AUTOFIX_TOKEN` /
`ANTHROPIC_API_KEY` (it never creates them).

## 4. Keep `.claude/` local

The `.claude/settings.json` + `.claude/hooks/` stay in the consumer repo (they're in
`fix_loop.gated_paths`, so the fix-loop can never touch them). If you used the
platform bundle, the per-file PostToolUse scan + the `stop-scan` gate behave the same;
the only change is that `scan-and-fix` is now the shared, versioned script.

## 5. Add the scan callers

Drop in `templates/workflows/code-security-scan.yml` (app-code SARIF with distinct
categories) and remove any bespoke `security-scan.yml` that duplicated it. Terraform
repos add `terraform-scan.yml` similarly.

## 6. Verify parity

- [ ] `scan-config.yaml` validates; `csharp`/`typescript` enabled; `fix_loop.enabled: true`.
- [ ] Local commit runs the same scanners (now via `hooks/dispatcher.sh`) in < 15s.
- [ ] CI uploads **distinct SARIF categories** (`scan-semgrep-csharp`, `scan-semgrep-typescript`, …).
- [ ] A PR labelled `ai-autofix` triggers the reusable two-job workflow; `analyze` has
      **no write token**; `apply-and-push` enforces `api/src,api/tests,mobile` and pushes
      only via `AUTOFIX_TOKEN`.
- [ ] A patch touching `.github/` or `*Auth*` is rejected to `needs-human-review`.

## 7. What you can delete

- The inline `autonomous-fix.yml` body (replaced by the caller).
- Hardcoded paths in hooks/scripts (now in `scan-config.yaml`).
- Any locally-maintained copy of the allowlist/denylist gate (now `check-fix-allowlist.py`).

Pin everything to `@v2.0.0`. Bump deliberately per `docs/VERSION-PINNING.md`.
