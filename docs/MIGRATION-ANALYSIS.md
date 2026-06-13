# Migration Analysis — From Terraform Scan‑Only POC to Reusable Scan→Fix Platform

**Status:** Analysis for `specs/002-scan-fix-platform`
**Audience:** maintainers of `auto-code-scanning`; engineers adopting the platform.
**Method:** Full read of this repository plus the proven fix‑loop reference in
`workout-trackroutinely` (PR #145). Nothing below is aspirational — it mirrors
what exists today and states exactly what changes.

---

## 1. What this repo is today

`auto-code-scanning` is a **distribution machine for Terraform/IaC security
scanning**. It already does the hard, unglamorous parts well:

| Capability | Where it lives | Verdict |
|---|---|---|
| OS‑detecting hook dispatch (Win→`.ps1`, else `.sh`) | `hooks/dispatcher.sh` | **Reuse as‑is** |
| Shared hook library (`require_tool`, `hook_log`, `start_timer`, fail‑open exit codes, `last-scan.json` writers, staged‑file dir detection) | `hooks/lib/common.{sh,ps1}` | **Reuse + extend** |
| Staged‑files‑only scanning via a git‑index temp dir | `hooks/trivy-secrets.{sh,ps1}` | **Reuse pattern verbatim** |
| Per‑tool hook scripts (trivy, checkov, tflint, gitleaks, snyk) | `hooks/*.{sh,ps1}` | **Reuse as‑is** |
| pre‑commit manifest | `.pre-commit-hooks.yaml` | **Keep as supported alternative runner** |
| Reusable `workflow_call` scanner (severity, sarif, suppressions, baseline, snyk, PR comment, metrics) | `.github/workflows/reusable-scan.yml` | **Generalize, don't rewrite** |
| Config‑driven multi‑language framework (enabled/file_patterns/tools/stage) | `scan-config.yaml` | **Extend in existing shape** |
| Result contract | `schemas/{unified-results,last-scan}.schema.json` | **Extend for app‑code tools** |
| Cloud config overlays (aws/azure/gcp `.checkov.yaml`, `.tflint.hcl`, policy overlays) | `configs/**` | **Reuse as‑is** |
| Setup / verify / aggregate / metrics tooling | `scripts/*.ps1`, `scripts/scan.py` | **Extend** |
| Tiered templates (starter/standard/strict + per‑cloud) | `templates/**` | **Extend with new runners** |
| Spec‑driven layout | `specs/001-security-scanning-spec/**` | **Add `specs/002-…`** |

**The two gaps** the platform must close:

1. **Application‑code scanning.** `scan-config.yaml` ships `terraform` enabled and
   `powershell/shell/docker/python/kubernetes` present‑but‑disabled. There is **no
   `csharp` and no `typescript`** language block, and no app‑code hook scripts.
2. **The agentic fix‑loop.** There is **no `fix_loop:` config section, no Lefthook
   runner, no `.claude/` in‑session bundle, and no `autonomous-fix.yml`.** Scanning
   today is *detect‑only*.

> **No back‑compat obligation.** There are no real consumers (the only `rev: v1.0.0`
> references are in this repo's own templates/docs). We may restructure freely; the
> single capability we must not lose is **working Terraform scanning**.

---

## 2. The reference fix‑loop (workout‑trackroutinely PR #145)

PR #145 is the **source of truth** for the fix‑loop. Its proven shape:

### 2.1 Two‑job `autonomous-fix.yml` — breaks the "lethal trifecta"

The trifecta = *untrusted input* + *write credentials* + *egress*. PR #145 splits
these so no single job holds all three:

- **JOB A `analyze`** — context: **untrusted input**.
  - Permissions: `contents: read`, `pull-requests: read`, `actions: read`. **No write token, no `AUTOFIX_TOKEN`.**
  - `checkout` with `persist-credentials: false`, pinned to the **immutable head SHA**.
  - Runs `claude-code-action` as a **FIX‑ONLY** agent. Review/PR/issue comment text is
    fetched via scoped `gh api` and treated as **UNTRUSTED DATA** — the prompt explicitly
    forbids obeying instructions embedded in comments.
  - Tool allowlist is **scoped** (`Read,Edit,Bash(gh pr diff:*),Bash(dotnet build:*),…`) with
    **no umbrella `Bash`, no `WebSearch`/`WebFetch`, no `git push/commit/reset`**.
  - Output: a **patch artifact only** (`git diff --cached --binary > autofix.patch`).
  - An **allowlist path gate** runs in‑job; if the patch touches anything outside the
    allowlist or matching the sensitive denylist, `gated=true`.
- **JOB B `apply-and-push`** — context: **write credentials**, *no* untrusted input.
  - `needs: analyze`, runs only if `capped != true && has_changes == true && gated != true`.
  - Re‑checks out the **exact same head SHA** (no TOCTOU) using `AUTOFIX_TOKEN`.
  - Downloads + `git apply` the vetted patch, then **re‑enforces the allowlist gate**
    (defense in depth), **re‑runs the secret scan on changed files**, and **re‑runs the build**.
  - Bumps `.fix-attempts` (hard cap **3**), commits, and pushes with `AUTOFIX_TOKEN`.
- **JOB C `flag-human-review`** — adds `needs-human-review` label + explanatory comment
  whenever capped / gated / a job failed.

**Trigger / privilege boundary:** opt‑in per PR via the **`ai-autofix`** label; non‑fork,
owner‑repo head; trusted bot or OWNER/MEMBER/COLLABORATOR reviewer; `workflow_dispatch`
fallback. Hard `max_iterations` cap → `needs-human-review`.

**Pin:** `anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102 # v1.0.148`
(≥ 1.0.93 fixes CVE‑2025‑66032 / GHSA‑xq4m‑mc3c‑vvg3). Every third‑party action is SHA‑pinned.

### 2.2 Lefthook as the local runner

`lefthook.yml`: `parallel: true`, glob‑scoped commands, `root:` per language dir,
`stage_fixed: true` for formatters. A **mandatory secret gate** runs on every commit.
Commands invoke project scripts (`secret-scan-staged.ps1`) and tools directly
(`dotnet format`, `eslint --fix && prettier --write`, `semgrep --config p/csharp`).

### 2.3 In‑session Claude Code bundle (`.claude/`)

- `settings.json` wires **`PostToolUse`** (matcher `Write|Edit|MultiEdit`) → a per‑file
  scan that **`exit 2`** to feed findings back for *in‑session self‑correction*, and
  **`Stop`** → a final `scan-and-fix` guarded by **`stop_hook_active`** (loop guard).
- `posttooluse-scan.ps1` routes by file extension: `.cs` → `dotnet build` + `dotnet format
  --verify-no-changes` + `semgrep --config p/csharp` (with `PYTHONUTF8=1` for native Windows);
  `.tf` → `terraform validate`.
- `scan-and-fix.ps1` is a modular scanner emitting a stable `.claude/scan-findings.json`.

### 2.4 The path bug we must fix generically

PR #145's hooks hardcode `api/` and `TrackRoutinely.slnx`. That is the **`dotnet-format`
path bug**: it only works for one repo. The platform must read the solution and working
directory **from config** (`languages.csharp.build.{solution,working_dir}`), never hardcode.

---

## 3. Reusable as‑is / Parameterize / Consumer‑local

### 3.1 Reuse as‑is (no change needed to keep working)
- `hooks/dispatcher.sh`, `hooks/lib/common.{sh,ps1}` (extended, not rewritten).
- All Terraform hooks and the `configs/**` cloud overlays.
- The aggregate/SARIF/PR‑comment/metrics machinery in `reusable-scan.yml`.
- Suppression + baseline tooling (`scripts/`, `hooks/validate-suppressions.*`).

### 3.2 Parameterize (move hardcoded/POC values into `scan-config.yaml`)
| Today (POC / PR #145) | Becomes config |
|---|---|
| Terraform‑only languages | `languages.csharp`, `languages.typescript` blocks |
| `api/`, `TrackRoutinely.slnx` hardcoded | `languages.csharp.build.{solution,working_dir}` |
| Allowlist `api/src,api/tests,mobile` baked into YAML | `fix_loop.allowlist_paths` |
| Sensitive denylist baked into YAML | `fix_loop.gated_paths` |
| `ai-autofix` / cap `3` / `--max-turns 12` baked in | `fix_loop.{label,human_review_label,max_iterations,max_turns}` |
| `claude-code-action` SHA baked into one repo | `fix_loop.claude_code_action_ref` (centralized pin) |
| `build_verify` = `dotnet build` baked in | `fix_loop.build_verify_cmd` (derived from `languages.*.build`) |
| Single SARIF category strings | `ci.sarif.category_prefix` → distinct per‑tool categories |

### 3.3 Must live in the **consumer** repo (never in this shared repo)
- **Secrets:** `AUTOFIX_TOKEN`, `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`),
  optional `SNYK_TOKEN`. The platform **verifies** them (`gh secret list`) — never stores them.
- **Project paths / solution names** — expressed only via the consumer's `scan-config.yaml`.
- **`.claude/settings.json` + `.claude/hooks/`** — **copied** into the consumer (per‑repo, may
  reference local paths). Heavy logic stays in versioned shared scripts; the copied layer is thin.
- **The thin caller workflows** (`uses:` the reusable workflows at a pinned tag).
- **The `ai-autofix` / `needs-human-review` labels** (created in the consumer by setup).

---

## 4. Mapping new languages onto the existing plugin/adapter design

`docs/ai-research/2-Generic-Scanning-Framework-Design.md` already names a **C#/.NET plugin
(`dotnet format` + Roslyn)** and a **TS plugin (ESLint + Prettier)** under the
*Config Loader → Scanner Engine → Results Aggregator → Language Plugins → Tool Adapters*
model. We implement them **as that design renders in this repo today**: a "plugin" =
a `languages.<lang>` block in `scan-config.yaml`; a "tool adapter" = a pair of
`hooks/<tool>.{sh,ps1}` dispatcher scripts sharing `hooks/lib/common`.

| Design concept | Concrete artifact in this repo |
|---|---|
| C#/.NET Language Plugin | `languages.csharp` in `scan-config.yaml` |
| → `dotnet format` Tool Adapter | `hooks/dotnet-format.{sh,ps1}` (reads `build.solution`/`build.working_dir`) |
| → Roslyn Analyzer Tool Adapter | `hooks/dotnet-build.{sh,ps1}` (`/p:AnalysisMode=AllEnabledByDefault`) |
| → Semgrep SAST Tool Adapter | `hooks/semgrep-csharp.{sh,ps1}` (`--config p/csharp`, `PYTHONUTF8=1`) |
| TypeScript Language Plugin | `languages.typescript` in `scan-config.yaml` |
| → ESLint / Prettier Tool Adapters | `hooks/eslint.{sh,ps1}`, `hooks/prettier.{sh,ps1}` |
| → Semgrep SAST Tool Adapter | `hooks/semgrep-typescript.{sh,ps1}` (`--config p/typescript`) |
| SQL Tool Adapter (bonus, from PR #145) | `hooks/sqlfluff.{sh,ps1}` |
| Results Aggregator | extended `reusable-scan.yml` aggregate job + `schemas/*` |

Every new hook follows the **trivy‑secrets pattern**: `require_tool || exit 0` (fail‑open),
`git diff --cached` staged files, export to a temp git‑index dir, scan only that, emit
`last-scan.json`, classify exit codes (0 pass / 1 findings / 2+ fail‑open). New shared
helpers (`Get-StagedFiles`, `Read-ScanConfigValue`, `Export-StagedFilesToTempDir`) go in
`hooks/lib/common.{sh,ps1}` so the scripts stay thin.

---

## 5. Two layers, one config seam

```
                 scan-config.yaml  (the single seam)
                 ├── languages.*   →  LAYER A: scanning
                 │     terraform | csharp | typescript | …
                 │        ├─ local:  Lefthook (default) | pre-commit (alt) → hooks/dispatcher.sh
                 │        └─ CI:     reusable-scan.yml (+ code-security-scan.yml)
                 └── fix_loop.*     →  LAYER B: agentic fix (opt-in)
                       ├─ in-session: templates/claude/ (.claude PostToolUse/Stop)
                       └─ CI:         autonomous-fix.yml (two-job) + templates/fix-loop/ caller
```

**LAYER A** (scanning) is always on. **LAYER B** (fix) is opt‑in via `fix_loop.enabled`
and the `ai-autofix` PR label. Both layers read the **same** `scan-config.yaml`, so a
consumer configures the whole platform in one file.

---

## 6. Risks & how we retire them

| Risk | Mitigation |
|---|---|
| Breaking Terraform scanning | New languages are additive; Terraform hooks/workflow paths untouched; validation runs the existing terraform fixtures. |
| Windows/Semgrep friction (WSL, cp1252) | Native‑Windows Semgrep path; `PYTHONUTF8=1` in hook env; staged‑only keeps hooks <15s so agents never bypass. |
| `dotnet-format` path bug recurring | Path comes from `languages.csharp.build.*`; a config‑driven test asserts no hardcoded solution. |
| Prompt‑injected consumer PR | Two‑job split, read‑only analyze, allowlist (not denylist) gate, label opt‑in, SHA‑pinned action ≥1.0.93 — documented in `docs/SECURITY-MODEL.md`. |
| Unpinned action supply‑chain | Every third‑party action SHA‑pinned in this repo; consumers pin `uses:` to `@vX.Y.Z`. |

---

## 7. Deliverables (tracked in `specs/002-scan-fix-platform`)

STEP 1 config seam · STEP 2 app‑code hooks + generalized CI scan · STEP 3 Lefthook +
`.claude/` bundle · STEP 4 two‑job `autonomous-fix.yml` + caller · STEP 5 one‑command
setup · STEP 6 versioning + `SECURITY-MODEL.md` + SHA pins · STEP 7 `CONSUMER-MIGRATION.md`
· STEP 8 docs refresh + tests + spec.
