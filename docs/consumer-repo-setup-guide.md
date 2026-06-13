# Adopting `auto-code-scanning` in Your Repo — Complete Setup Guide

A detailed, step-by-step guide to adopt the **scan→fix platform** in any GitHub repository,
configured by the languages your repo contains. Works for IaC-only repos, application-code
repos (C#/.NET, TypeScript/JS, SQL), or a mix.

You get **two layers**, both driven by a single `scan-config.yaml`:

- **Layer A — Scanning** (always on): fast local pre-commit/pre-push hooks **and** CI workflows
  that scan Terraform/IaC and application code, uploading results to GitHub code scanning.
- **Layer B — Agentic fix-loop** (opt-in): a hardened workflow where an AI agent proposes a
  *minimal* fix to a flagged PR and a separate, locked-down job re-verifies and pushes it.

> **This guide assumes the platform is published and tagged `@v2.0.0`** at
> `agenticcodingops/auto-code-scanning` (replace the owner/name and tag with yours if you forked it).
> **Always pin to a release tag — never `@main`.**

---

## Table of contents

1. [Before you start (prerequisites)](#1-before-you-start-prerequisites)
2. [How it works (mental model)](#2-how-it-works-mental-model)
3. [Step 1 — Decide your configuration](#3-step-1--decide-your-configuration)
4. [Step 2 — Run one-command setup](#4-step-2--run-one-command-setup)
5. [Step 3 — Review & tune `scan-config.yaml`](#5-step-3--review--tune-scan-configyaml)
6. [Step 4 — Commit the generated files](#6-step-4--commit-the-generated-files)
7. [Step 5 — (Fix-loop only) secrets & labels](#7-step-5--fix-loop-only-secrets--labels)
8. [Step 6 — Wire & verify CI](#8-step-6--wire--verify-ci)
9. [Step 7 — Verify end-to-end](#9-step-7--verify-end-to-end-acceptance-checklist)
10. [Step 8 — Operate & maintain](#10-step-8--operate--maintain)
11. [Security model in one minute](#11-security-model-in-one-minute)
12. [Troubleshooting](#12-troubleshooting)
13. [Per-language cheat sheet](#13-per-language-cheat-sheet)
14. [Appendix — manual setup (no script)](#14-appendix--manual-setup-no-script)

---

## 1. Before you start (prerequisites)

You only need the tools for the languages you actually scan — every hook is **fail-open**, so a
missing tool warns and allows the commit rather than blocking you. Install what's relevant:

| Tool | Needed for | Install (Windows) | Install (macOS/Linux) |
|---|---|---|---|
| **git** | everything | bundled / `winget install Git.Git` | system pkg manager |
| **GitHub CLI (`gh`)**, authenticated | labels + secret verification + CI | `winget install GitHub.cli` then `gh auth login` | `brew install gh` / apt |
| **PowerShell 7 (`pwsh`)** | running the `.ps1` setup + hooks | `winget install Microsoft.PowerShell` | `brew install powershell` (optional; use the `.py`/`.sh` paths instead) |
| **Python 3.8+** with **`pyyaml`** + **`jsonschema`** | render/validate config; gate script | `winget install Python.Python.3` then `pip install pyyaml jsonschema` | `pip install pyyaml jsonschema` |
| **Lefthook** (default runner) | local hooks | `winget install evilmartians.lefthook` or `choco install lefthook` | `brew install lefthook` / `go install github.com/evilmartians/lefthook@latest` |
| **Semgrep** | C#/TS SAST hooks | `pip install semgrep` | `pip install semgrep` / `brew install semgrep` |
| **Trivy** | secret + IaC scanning | `winget install AquaSecurity.Trivy` / `choco install trivy` | `brew install trivy` |
| **.NET SDK** | C# repos (`dotnet format` / `dotnet build`) | `winget install Microsoft.DotNet.SDK.8` | `brew install dotnet-sdk` |
| **Node + npm** | TS/JS repos (`eslint`/`prettier`) | `winget install OpenJS.NodeJS` | `brew install node` |
| **tflint / checkov** | Terraform repos | `choco install tflint` / `pip install checkov` | `brew install tflint` / `pip install checkov` |

> **Pre-commit alternative:** if your team standardises on [pre-commit](https://pre-commit.com)
> instead of Lefthook, install it (`pip install pre-commit`) and pass `--hooks-runner pre-commit`
> at setup. Both runners call the **same** hook scripts.

**Get the platform locally** (so setup can copy templates and shared scripts into your repo):

```bash
git clone --branch v2.0.0 https://github.com/agenticcodingops/auto-code-scanning.git /path/to/auto-code-scanning
```

(Or add it as a git submodule if you prefer to track the version in-repo.)

---

## 2. How it works (mental model)

```
                     scan-config.yaml   ← the ONE file you own
   ┌───────────────────────┴───────────────────────────────┐
   │ languages.{terraform,csharp,typescript,sql}            │  Layer A — scanning
   │   • LOCAL:  Lefthook (default) | pre-commit  → hooks/dispatcher.sh → hooks/*.{sh,ps1}
   │   • CI:     code-security-scan.yml (app code) + reusable-scan.yml (IaC)
   │              → SARIF per tool, DISTINCT categories → GitHub code scanning
   └───────────────────────┬───────────────────────────────┘
   │ fix_loop.{...}                                         │  Layer B — agentic fix (opt-in)
   │   • IN-SESSION: .claude/ hooks scan each edit (self-correct before commit)
   │   • CI:         autonomous-fix.yml (analyze ▸ apply-and-push ▸ flag-human-review)
   └────────────────────────────────────────────────────────┘
```

- **Local hooks** scan only **staged files** (fast, <15s) and are **fail-open** (a missing tool
  or infra error never blocks you; only real findings do).
- **CI workflows** are the authoritative backstop and upload SARIF to the Security tab.
- The **dispatcher** (`hooks/dispatcher.sh`) auto-detects the OS and runs the `.ps1` on Windows or
  the `.sh` elsewhere — so the same config works for every contributor.

---

## 3. Step 1 — Decide your configuration

**(a) Languages** — pick what your repo contains:

| Your repo contains | `--languages` value | Extra flag |
|---|---|---|
| Terraform / IaC | `terraform` | `--cloud-provider aws\|azure\|gcp` |
| C# / .NET | `csharp` | (set `build.solution` after — Step 3) |
| TypeScript / JS / React Native | `typescript` | — |
| SQL | `sql` | — |
| Mixed | `csharp,typescript,terraform` | comma-separated |

**(b) Tier** — how strict the gates are:

| Tier | Blocks commit on | App-code tools | Fix-loop default |
|---|---|---|---|
| `starter` | CRITICAL | formatters + secrets | off |
| `standard` *(recommended)* | CRITICAL, HIGH | + SAST (Semgrep) | wired, off |
| `strict` | CRITICAL, HIGH, MEDIUM | + Roslyn build, full pre-push | **on** (still needs the label) |

**(c) Runner** — `lefthook` (default; single Go binary, native Windows, parallel, friction-free
for autonomous AI loops) or `pre-commit` (`--hooks-runner pre-commit`).

**(d) Fix-loop** — add `--enable-fix-loop` to wire Layer B. (You can adopt scanning first and turn
the loop on later by re-running setup.)

---

## 4. Step 2 — Run one-command setup

Run from **inside your consumer repo** (or pass `--repo-path`). The script is **idempotent** —
re-run it any time (e.g., to add a language or turn on the fix-loop).

```powershell
# Windows / PowerShell — app-code repo with the fix-loop:
pwsh /path/to/auto-code-scanning/scripts/setup-scan-fix.ps1 `
  -Languages csharp,typescript -Tier standard -HooksRunner lefthook -EnableFixLoop -RepoPath .
```
```bash
# Cross-platform — Python twin (identical flags, kebab-case):
python /path/to/auto-code-scanning/scripts/setup-scan-fix.py \
  --languages csharp,typescript --tier standard --hooks-runner lefthook --enable-fix-loop --repo-path .

# Terraform-only, scanning only (no secrets needed):
python /path/to/auto-code-scanning/scripts/setup-scan-fix.py \
  --languages terraform --cloud-provider aws --tier standard
```

**Flag reference**

| PowerShell | Python | Meaning |
|---|---|---|
| `-Languages` | `--languages` | csv: `terraform,csharp,typescript,sql` |
| `-Tier` | `--tier` | `starter` \| `standard` \| `strict` |
| `-HooksRunner` | `--hooks-runner` | `lefthook` (default) \| `pre-commit` |
| `-EnableFixLoop` | `--enable-fix-loop` | wire Layer B |
| `-CloudProvider` | `--cloud-provider` | `aws` \| `azure` \| `gcp` (Terraform) |
| `-RepoPath` | `--repo-path` | target repo (default: cwd) |
| `-Force` | `--force` | overwrite an existing `scan-config.yaml` |

**What setup creates in your repo** (review each before committing — Step 4):

| Path | What it is | Edit it? |
|---|---|---|
| `scan-config.yaml` | **Your** config seam (languages, tools, fix_loop) | **Yes** — tune in Step 3 |
| `hooks/` | Vendored dispatcher + per-tool `.sh`/`.ps1` + `lib/common.*` | No (re-vendored on upgrade) |
| `lefthook.yml` *(or `.pre-commit-config.yaml`)* | Local runner config | Rarely |
| `scripts/` | `scan-and-fix.*`, `check-fix-allowlist.py`, `validate-scan-config.py`, `render-scan-config.py` | No |
| `.claude/settings.json` + `.claude/hooks/*` | In-session self-correction bundle (fix-loop) | Keep local |
| `.github/workflows/code-security-scan.yml` | Thin **scan** caller | Pin tag |
| `.github/workflows/terraform-scan.yml` | Thin IaC scan caller (if terraform) | Pin tag |
| `.github/workflows/autonomous-fix.yml` | Thin **fix-loop** caller (if `--enable-fix-loop`) | Pin tag |

Setup also:
- installs the local runner's git hooks (`lefthook install`),
- creates the `ai-autofix` + `needs-human-review` labels (needs `gh` + a git remote),
- **verifies** (never creates) the `AUTOFIX_TOKEN` / `ANTHROPIC_API_KEY` secrets and prints exact
  creation steps if missing,
- runs `verify-scanning` to prove the install.

---

## 5. Step 3 — Review & tune `scan-config.yaml`

Setup enables the languages you chose. Set the **project-specific** bits.

### C#/.NET — point at your solution (this is the important one)

```yaml
languages:
  csharp:
    enabled: true
    build:
      solution: "api/MyApp.slnx"   # your .sln/.slnx; "" = auto-detect the nearest one
      working_dir: "api"           # directory to run `dotnet` from
```

> This is how the platform solves the "dotnet path" problem **generically** — the solution path
> comes from config, never hardcoded. For a monorepo, `working_dir` also scopes which staged files
> are passed to `dotnet format --include`.

### TypeScript/JS — point at your package root (monorepos)

```yaml
languages:
  typescript:
    enabled: true
    build:
      working_dir: "mobile"   # where package.json / eslint config lives
```

### Distinct SARIF categories

```yaml
ci:
  sarif:
    category_prefix: "myrepo-"   # KEEP THE TRAILING SEPARATOR
```

Each tool uploads under `"<category_prefix>semgrep-<lang>"` (e.g. `myrepo-semgrep-csharp`).
GitHub (since 2025-07-22) rejects same tool+category SARIF collisions, so a distinct prefix per
repo is what keeps uploads clean.

### Validate your config

```bash
python /path/to/auto-code-scanning/scripts/validate-scan-config.py   # run from your repo root
```

(The `validate-scan-config` hook also runs this automatically whenever `scan-config.yaml` is staged.)

### Fix-loop boundary (only if you enabled Layer B)

```yaml
fix_loop:
  enabled: true
  label: "ai-autofix"
  human_review_label: "needs-human-review"
  max_turns: 8
  max_iterations: 3                                  # hard cap on autofix commits per PR
  allowlist_paths: ["api/src/", "api/tests/", "mobile/"]   # ONLY these are auto-fixable
  gated_paths: ["auth","payment","crypto","security","identity","secret","credential",
                ".github/",".claude/","hooks","lefthook.yml","scan-and-fix.ps1","scripts/",".env","LICENSE"]
  build_verify_cmd: "bash scripts/ci-build-verify.sh"   # a CHECKED-IN, gated script (see below)
  claude_code_action_ref: "anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102"  # v1.0.148
```

- **`allowlist_paths`** — set these to where your *fixable application code* actually lives.
  A change outside them (or matching any `gated_paths` substring, case-insensitively) is **rejected
  to `needs-human-review`** — fail closed.
- **`build_verify_cmd`** is **executed** in CI. The loop reads it from the **base branch** (so a PR
  can't change it) and runs it **without the push token** — but it's still arbitrary CI code, so
  keep it a **checked-in script under a gated path** (e.g. `scripts/`). That way it can't be altered
  in a PR without tripping the gate. Avoid inline shell.
- Dry-run the gate against a path before trusting it:
  ```bash
  echo "api/src/Foo.cs" | python scripts/check-fix-allowlist.py --config scan-config.yaml   # exit 0 = allowed
  echo ".github/x.yml"   | python scripts/check-fix-allowlist.py --config scan-config.yaml   # exit 1 = gated
  ```

---

## 6. Step 4 — Commit the generated files

The reusable **scan** workflow checks out *your* repo and reads `scan-config.yaml` to decide which
languages to scan, and Lefthook calls the vendored `hooks/`. So these must be committed:

```bash
git add scan-config.yaml hooks/ lefthook.yml scripts/ .claude/ .github/workflows/
git commit -m "chore: adopt auto-code-scanning v2.0.0 (scan + fix-loop)"
```

> Add `.scanning/` and `.scan-results/` to your `.gitignore` (setup/hooks write runtime artifacts
> there). The platform's `.gitignore` already does this; copy those lines if your repo lacks them.

---

## 7. Step 5 — (Fix-loop only) secrets & labels

**Scanning-only adoption needs no secrets — skip this section.**

The fix-loop needs two repository secrets. Setup **checks** for them and prints these steps if
they're missing; it never creates or stores a secret value.

### `AUTOFIX_TOKEN` — a fine-grained Personal Access Token

Why a PAT and not the built-in `GITHUB_TOKEN`? A push made with `GITHUB_TOKEN` **does not
re-trigger** other workflows (GitHub's loop-prevention), so your scans/checks wouldn't re-run on
the autofix commit. A PAT (or GitHub App token) does.

Create at **GitHub → Settings → Developer settings → Fine-grained personal access tokens → Generate**:
- **Resource owner:** the org/user that owns the repo.
- **Repository access:** **Only select repositories** → *this repo only*.
- **Permissions:** **Contents → Read and write**, **Pull requests → Read and write**. Nothing else.
- **Expiration:** as short as your rotation policy allows.

Then store it as a repo secret:
```bash
gh secret set AUTOFIX_TOKEN --repo <OWNER>/<REPO>     # paste the token value when prompted (hidden)
```

> **More secure alternative:** use a **GitHub App** installation token instead of a PAT (no human
> owner, scoped permissions, no manual rotation). Install the App on the repo with Contents+PR
> write, mint a token in the workflow, and pass it as `AUTOFIX_TOKEN`. Recommended for orgs.

### `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`)

For `claude-code-action`. Create at the [Anthropic Console](https://console.anthropic.com/), then:
```bash
gh secret set ANTHROPIC_API_KEY --repo <OWNER>/<REPO>
```

### Labels

`ai-autofix` (opt a PR into the loop) and `needs-human-review` (applied when the loop stops). Setup
creates them; or manually:
```bash
gh label create ai-autofix --color 1D76DB --description "Opt this PR into the autonomous fix-loop"
gh label create needs-human-review --color B60205 --description "Autonomous fix loop stopped; needs a human"
```

> **Who can apply `ai-autofix` is your privilege boundary.** On a repo with many write-collaborators,
> remember any of them can self-apply the label. If that's too broad, restrict it (a guard job, a
> label-protection rule, or use `workflow_dispatch` only). See `docs/SECURITY-MODEL.md` §5.

---

## 8. Step 6 — Wire & verify CI

Setup drops thin caller workflows into `.github/workflows/`. Confirm they pin the platform by **tag**.

### Scan caller (all consumers)

```yaml
# .github/workflows/code-security-scan.yml
name: Code Security Scan
on:
  pull_request: { branches: [main, develop] }
  push: { branches: [main] }
  workflow_dispatch:
permissions:
  contents: read
  security-events: write    # upload SARIF
jobs:
  code-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v2.0.0
    with:
      # languages are AUTO-DETECTED from scan-config.yaml; or pin explicitly:
      # languages: "csharp,typescript"
      category-prefix: "myrepo-"
      fail-on-findings: true
```

> Note: the scan workflow reads `scan-config.yaml` itself — there is **no `config_path` input** here.
> (Terraform repos additionally use `terraform-scan.yml`, which `uses:` `reusable-scan.yml@v2.0.0`
> with `cloud-provider` + `terraform-directory`.)

### Fix-loop caller (only if `--enable-fix-loop`)

This file owns the **privilege boundary** and `uses:` the reusable two-job workflow with
`secrets: inherit`. Leave its gating `if:` intact:

```yaml
# .github/workflows/autonomous-fix.yml (excerpt — setup wrote the full file)
jobs:
  fix:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      ( github.event.pull_request.head.repo.full_name == github.repository &&
        contains(github.event.pull_request.labels.*.name, 'ai-autofix') &&
        ( /* trusted bot OR OWNER/MEMBER/COLLABORATOR */ ) )
    uses: agenticcodingops/auto-code-scanning/.github/workflows/autonomous-fix.yml@v2.0.0
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      config_path: scan-config.yaml
      scanning_repo_ref: v2.0.0
    secrets: inherit
```

### Branch protection

In **Settings → Branches → Branch protection rules** for `main`, mark the scan job a **required
status check** (it appears as `Code Security Scan / Semgrep (csharp)` etc. after the first run) so
nothing merges un-scanned. This is what turns the platform from advisory into enforced.

---

## 9. Step 7 — Verify end-to-end (acceptance checklist)

| # | Do this | Expect |
|---|---|---|
| 1 | `lefthook run pre-commit` (or `pre-commit run --all-files`) | clean run, <15s; language hooks auto-skip when nothing relevant is staged |
| 2 | Stage a mis-formatted `.cs`, `git commit` | `dotnet format` (from `working_dir`) flags it |
| 3 | Stage a fake secret (e.g. `AKIAIOSFODNN7EXAMPLE`), `git commit` | the secret hook **fails** the commit |
| 4 | Stage a `.cs` with `MD5.Create()` (or your Semgrep rule) | `semgrep-csharp` reports it, **no cp1252 crash** (native-Windows Semgrep) |
| 5 | Open a PR | the scan workflow runs; SARIF appears under your distinct category in the **Security → Code scanning** tab |
| 6 | *(fix-loop)* label a throwaway PR `ai-autofix`, have a trusted reviewer review it | the two-job loop runs; the apply push **re-triggers CI**; a patch touching `.github/` is **rejected to `needs-human-review`** |
| 7 | Make the scan check fail on a PR | branch protection **blocks merge** |

---

## 10. Step 8 — Operate & maintain

- **Upgrade the platform:** bump every `@v2.0.0` pin to the next release — the caller workflows'
  `uses:` lines, `scanning_repo_ref`, and `fix_loop.claude_code_action_ref` — and **re-run
  `setup-scan-fix`** to re-vendor the updated `hooks/`/`scripts/`. One deliberate change, inherited
  everywhere. See [`VERSION-PINNING.md`](VERSION-PINNING.md).
- **Rotate `AUTOFIX_TOKEN`** before expiry (or switch to a GitHub App to avoid rotation).
- **Tune the fix-loop scope** by widening `allowlist_paths` as you trust the loop on more paths, or
  tightening `gated_paths`. The config is gated, so the loop can't widen its own scope.
- **A stuck PR** carries `needs-human-review` with a comment explaining why (cap reached, gated
  path, build failed, secret detected, or branch advanced). Fix it by hand, then reset
  `.fix-attempts` to `0`.
- **Remove the platform:** delete `lefthook.yml`/`.pre-commit-config.yaml`, run `lefthook uninstall`
  (or `pre-commit uninstall`), and delete the caller workflows + `.claude/`. Scanning stops; no other
  cleanup needed.

---

## 11. Security model in one minute

The fix-loop is engineered for a **shared workflow with write access across many repos**:

- **Two-job split breaks the "lethal trifecta":** the `analyze` job that reads attacker-influenced PR
  text has **no write token and no egress**; the `apply-and-push` job that can push has **no untrusted
  input**, checks out with **no token on disk**, and re-verifies everything.
- **Allowlist (not denylist) path gate**, read from the **trusted base config** (a PR can't widen it).
- **Label opt-in + non-fork + trusted-reviewer** privilege boundary; hard `max_iterations` cap.
- **`build_verify_cmd`** is base-sourced and runs token-free; keep it a gated, checked-in script.
- **claude-code-action SHA-pinned** ≥ v1.0.93 (CVE-2025-66032), centralized; every action pinned.

Full detail and the "what a prompt-injected PR still cannot do" table:
[`docs/SECURITY-MODEL.md`](SECURITY-MODEL.md). Fix-loop deep dive: [`docs/FIX-LOOP.md`](FIX-LOOP.md).

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pwsh: command not found` | Use the Python twin `setup-scan-fix.py`, or install PowerShell 7. |
| `lefthook: command not found` after setup | Install Lefthook, then run `lefthook install` in the repo. |
| Hooks don't run on commit | `lefthook install` (or `pre-commit install`) wasn't run, or you committed with `-n`/`--no-verify`. |
| `python3` prints "Python was not found" (Windows Store stub) | The hooks already skip the broken alias and find real `python`; ensure a real Python 3 is installed and on PATH. |
| Setup: "could not create label: no git remotes found" | Add your GitHub remote first (`git remote add origin …`), then re-run setup (idempotent). |
| Setup: "secret AUTOFIX_TOKEN MISSING" | Expected for scanning-only; for the fix-loop, create it per Step 5. Setup never creates secrets. |
| Semgrep slow on first run | It downloads the ruleset pack once, then caches it. Subsequent runs are fast. |
| SARIF upload rejected (category collision) | Give this repo a unique `ci.sarif.category_prefix` (with a trailing separator). |
| Autofix didn't push / no CI re-run | `AUTOFIX_TOKEN` missing or lacks Contents+PR write; or the PR lacked the `ai-autofix` label / a trusted review. |
| `dotnet format` can't find the solution | Set `languages.csharp.build.solution` (and `working_dir`) in `scan-config.yaml`. |
| Config silently has no effect | Run `validate-scan-config.py` — the root schema is strict, so a typo like `fx_loop` is rejected. |

---

## 13. Per-language cheat sheet

| Language | Enable | Scanners wired | Project setting to set |
|---|---|---|---|
| Terraform | `languages.terraform.enabled: true` (+ `--cloud-provider`) | trivy (IaC+secrets), checkov, tflint, fmt/validate | `--cloud-provider` |
| C# / .NET | `languages.csharp.enabled: true` | semgrep `p/csharp`, `dotnet format`, `dotnet build` (Roslyn) | `build.solution`, `build.working_dir` |
| TypeScript/JS | `languages.typescript.enabled: true` | eslint, prettier, semgrep `p/typescript` | `build.working_dir`; lint config in repo |
| SQL | `languages.sql.enabled: true` | sqlfluff | dialect in `.sqlfluff` |

> Custom Semgrep rules: point `SEMGREP_RULESET_CSHARP` / `SEMGREP_RULESET_TYPESCRIPT` at a file or
> registry pack to override the defaults (consumer customization point).
>
> Not first-class in v2.0.0: Bicep, Swift, Python, Go, Java, PowerShell, Shell, Docker, Kubernetes.
> They follow the same plugin pattern — see [`docs/ROADMAP.md`](ROADMAP.md).

---

## 14. Appendix — manual setup (no script)

If you'd rather wire it by hand (or audit what the script does), the equivalent steps are:

1. **Config:** copy `templates/scan-config/<tier>.yaml` → your `scan-config.yaml`; set each
   language you want to `enabled: true` and fill in `build.*`. Validate with `validate-scan-config.py`.
2. **Vendor hooks:** copy the platform's `hooks/` dir and the shared `scripts/` you need
   (`scan-and-fix.*`, `check-fix-allowlist.py`, `validate-scan-config.py`) into your repo.
3. **Local runner:** copy `templates/lefthook/lefthook.yml` → `lefthook.yml` and run `lefthook install`
   (or copy a `templates/<tier>/pre-commit-config.yaml` → `.pre-commit-config.yaml` and `pre-commit install`).
4. **In-session bundle (fix-loop):** copy `templates/claude/settings.json` (Windows) or
   `settings.unix.json` (macOS/Linux) → `.claude/settings.json`, and `templates/claude/hooks/*` →
   `.claude/hooks/`.
5. **CI callers:** copy `templates/workflows/code-security-scan.yml` (+ `terraform-scan.yml`) and,
   for the fix-loop, `templates/fix-loop/autonomous-fix.yml` → `.github/workflows/`. **Pin every
   `uses:`/`scanning_repo_ref`/`claude_code_action_ref` to `@v2.0.0`.**
6. **Labels + secrets:** create `ai-autofix`/`needs-human-review`; add `AUTOFIX_TOKEN` +
   `ANTHROPIC_API_KEY` (fix-loop only).
7. **Commit** everything and open a test PR.

---

*Questions or a gap in the security model? Open a private security advisory on the platform repo
(don't post exploit detail in a public issue). See [`docs/CONTRIBUTING.md`](CONTRIBUTING.md).*
