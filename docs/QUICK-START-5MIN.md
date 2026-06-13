# Quick Start (5 Minutes)

Get the scan->fix platform running in your repository in under 5 minutes.

As of **v2.0.0** this is a reusable **scan->fix platform**, not just a Terraform
scanner. It scans application code (C#/.NET, TypeScript/JS, SQL) and Terraform,
runs locally via **Lefthook** (default) or **pre-commit**, and can open an
optional autonomous **fix-loop** on opted-in PRs. The fastest way in is the
one-command orchestrator `setup-scan-fix`.

> **Pin consumers to `@v2.0.0`, never `@main`.** The caller workflows that
> `setup-scan-fix` copies in already reference `@v2.0.0`; keep them pinned.

## Prerequisites

- A Git repository
- Python 3.8+ (used to render `scan-config.yaml` and by some hooks)
- [Lefthook](https://github.com/evilmartians/lefthook) on your PATH (default runner) — `choco install lefthook`, `go install github.com/evilmartians/lefthook@latest`, or `brew install lefthook`. (Or use `--hooks pre-commit` instead.)
- For the fix-loop only: the [GitHub CLI](https://cli.github.com/) (`gh`), authenticated
- Internet access (first-time setup only)

## Step 1: Run the one-command setup

`setup-scan-fix` is idempotent and re-runnable. It writes `scan-config.yaml`
from a tier template, vendors `hooks/` + shared `scripts/` into your repo,
installs your chosen local runner, copies the Claude Code in-session bundle
(`.claude/`) and the thin caller workflows, and (for the fix-loop) creates the
`ai-autofix` / `needs-human-review` labels and **verifies** the required secrets.

### Windows (PowerShell)

```powershell
# App code (C#/.NET + TypeScript), standard tier, fix-loop enabled
.\scripts\setup-scan-fix.ps1 -Languages csharp,typescript -Tier standard -EnableFixLoop
```

### macOS / Linux (cross-platform Python twin)

```bash
python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard --enable-fix-loop
```

### Common variations

```powershell
# Terraform only (pick your cloud)
.\scripts\setup-scan-fix.ps1 -Languages terraform -CloudProvider aws

# Use pre-commit instead of the default Lefthook runner
.\scripts\setup-scan-fix.ps1 -Languages csharp -HooksRunner pre-commit

# SQL linting too, strict tier
.\scripts\setup-scan-fix.ps1 -Languages csharp,typescript,sql -Tier strict
```

**Parameters** (PowerShell `-Name` / Python `--name`):

| Parameter | Values | Notes |
|-----------|--------|-------|
| `-Languages` / `--languages` | csv of `csharp,typescript,terraform,sql` | Languages to enable in `scan-config.yaml` |
| `-Tier` / `--tier` | `starter` \| `standard` \| `strict` | Defaults to `standard` |
| `-HooksRunner` / `--hooks-runner` | `lefthook` \| `pre-commit` | Defaults to `lefthook` |
| `-EnableFixLoop` / `--enable-fix-loop` | flag | Turns on `fix_loop`, copies `autonomous-fix.yml`, creates labels, verifies secrets |
| `-CloudProvider` / `--cloud-provider` | `aws` \| `azure` \| `gcp` | Terraform only; also implies `terraform` is enabled |
| `-RepoPath` / `--repo-path` | path | Target consumer repo (defaults to current dir) |
| `-Force` / `--force` | flag | Overwrite an existing `scan-config.yaml` |

### What this does

1. Renders `scan-config.yaml` from `templates/scan-config/<tier>.yaml` (via `scripts/render-scan-config.py`), enabling the languages you chose plus `fix_loop` if requested.
2. Vendors `hooks/` and the shared scripts (`scan-and-fix`, `check-fix-allowlist.py`, `validate-scan-config.py`, `render-scan-config.py`) into your repo.
3. Installs the local runner — **Lefthook** (copies `lefthook.yml`, runs `lefthook install`) or **pre-commit** (writes `.pre-commit-config.yaml`, runs `pre-commit install`). Both call the **same** `hooks/dispatcher.sh` scripts.
4. Copies the Claude Code in-session bundle to `.claude/` and the thin caller workflows (`code-security-scan.yml`, `terraform-scan.yml` when Terraform is enabled, and `autonomous-fix.yml` when the fix-loop is on).
5. For the fix-loop: creates the `ai-autofix` and `needs-human-review` labels via `gh label create`, and **verifies** (never creates) the `AUTOFIX_TOKEN` and `ANTHROPIC_API_KEY` secrets via `gh secret list` — printing exact creation steps if either is missing.
6. Runs `verify-scanning` to prove the install.

> **Terraform-only? Already on the legacy scanner?** The classic tool installer
> `setup-scanning.ps1` / `.py` (Chocolatey/pip installs of Trivy, Checkov,
> tflint, Gitleaks, pre-commit) still works — see the
> [Terraform quickstart](#terraform-only-quickstart-legacy-installer) below.
> `setup-scan-fix` is the new platform orchestrator and is the recommended path.

## Step 2: Make a Commit

```bash
git add .
git commit -m "feat: add new module"
# Hooks scan staged files for secrets and CRITICAL issues
```

Hooks run automatically on commit (Lefthook by default; pre-commit if you chose it):
- **trivy-secrets / gitleaks**: Block committed secrets in any file
- **trivy-iac-critical**: Blocks CRITICAL Terraform misconfigurations
- **semgrep-csharp / semgrep-typescript**: SAST for app code
- **dotnet-format / prettier / eslint**: Formatting + lint (auto-fixable hooks re-stage their fixes)
- **sqlfluff**: SQL linting

If all checks pass, the commit succeeds. If a CRITICAL/HIGH finding is detected, the commit is blocked with details about what to fix.

## Step 3: Review Results

After any hook run, check the scan report:

```bash
# Human-readable summary was printed to terminal
# Machine-readable JSON is under the results dir (.scan-results by default)
cat .scan-results/last-scan.json
```

## Step 4: Push (Standard/Strict Tiers)

Standard and strict tiers add pre-push hooks:

```bash
git push
```

Pre-push runs heavier checks:
- **checkov**: Policy-as-code checks (Terraform)
- **tflint**: Terraform linting
- **dotnet-build**: Roslyn build/analyzer checks (C#)

CI (the `code-security-scan.yml` / `terraform-scan.yml` callers) is the authoritative backstop.

## What Happens at Each Stage

| Stage | Hooks | Target Time |
|-------|-------|-------------|
| **pre-commit** | trivy-secrets, gitleaks, trivy-iac-critical, semgrep-*, dotnet-format, prettier, eslint, sqlfluff, validate-scan-config | <10s total |
| **pre-push** | checkov, tflint, dotnet-build | <60s total |

## The Optional Fix-Loop

With `-EnableFixLoop`, an opt-in autonomous fix-loop runs in CI on PRs:

1. Add the **`ai-autofix`** label to a PR to opt it in.
2. A trusted review (a known bot, or an OWNER/MEMBER/COLLABORATOR) triggers the reusable `autonomous-fix.yml`, which uses Claude Code to fix findings within an allowlist of safe paths.
3. If it can't safely proceed, it stops and adds **`needs-human-review`**.

Required CI secrets (the platform **verifies**, never stores them):
- **`AUTOFIX_TOKEN`** — a fine-grained PAT scoped to **this repo only** with **Contents: Read/Write** and **Pull requests: Read/Write**.
- **`ANTHROPIC_API_KEY`** (or `CLAUDE_CODE_OAUTH_TOKEN`).

If `gh secret list` shows either missing, setup prints the exact `gh secret set ...` command to run.

## What to Do When a Finding Blocks You

1. **Fix it**: Follow the remediation guidance in the terminal output
2. **Suppress it**: Add an entry to `.scan-suppressions.yaml` with business justification (see [Suppression Format](../specs/001-security-scanning-spec/contracts/suppression-format.md))
3. **Baseline it**: Run `.\scripts\create-baseline.ps1` to mark existing findings as known

## Emergency Bypass

```bash
# Lefthook (default runner)
LEFTHOOK=0 git commit -m "emergency: hotfix for production"

# pre-commit
git commit --no-verify -m "emergency: hotfix for production"
```

Bypasses are audited and reported via metrics — prefer fixing the finding.

## Tier Comparison

| Capability | Starter | Standard | Strict |
|-----------|---------|----------|--------|
| Secret detection (trivy-secrets, gitleaks) | Block | Block | Block |
| CRITICAL IaC findings | Block | Block | Block |
| App-code SAST (semgrep) + formatters/lint | Block | Block | Block |
| Full IaC scan (checkov, tflint) | -- | Pre-push | Pre-push |
| Checkov strict (CRITICAL+HIGH fail) | -- | -- | Pre-push |
| dotnet-build / Roslyn (C#) | -- | Pre-push | Pre-push |
| Blocking severities | CRITICAL | CRITICAL,HIGH | CRITICAL,HIGH |

## Terraform-Only Quickstart (Legacy Installer)

If you only need Terraform scanning and want the classic tool installer that
installs Trivy/Checkov/tflint/Gitleaks/pre-commit directly, use
`setup-scanning` instead of `setup-scan-fix`.

### macOS / Linux

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier starter
```

Replace `aws` with `azure` or `gcp`, and `starter` with `standard` or `strict`.

### Windows (PowerShell)

```powershell
# Admin install (uses Chocolatey)
.\scripts\setup-scanning.ps1 -CloudProvider aws -Tier starter

# Non-admin install (uses Scoop/pip)
.\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws -Tier starter
```

This installs the security tools, copies cloud-specific configs to
`.scanning/configs/`, creates `.pre-commit-config.yaml` from a tier template,
and runs `pre-commit install`. See [SETUP-GUIDE.md](SETUP-GUIDE.md) for full details.

## Next Steps

- **Upgrade tier**: See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for upgrade instructions
- **Customize**: Edit `scan-config.yaml` (languages, tools, `fix_loop`) — `csharp.build.solution`/`working_dir` make the `dotnet` path generic
- **CI/CD**: The caller workflows are already copied in; pin them to `@v2.0.0` (see [SETUP-GUIDE.md](SETUP-GUIDE.md#cicd-integration))
- **AI agents**: Use `python scripts/scan.py` for programmatic scanning (see [AI-AGENT-GUIDE.md](AI-AGENT-GUIDE.md))
- **All hooks**: See [HOOK-REFERENCE.md](HOOK-REFERENCE.md) for the complete hook reference
