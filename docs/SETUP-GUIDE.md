# Setup Guide

Detailed setup instructions for auto-code-scanning.

As of **v2.0.0**, auto-code-scanning is a reusable **scan->fix platform**: it
scans application code (C#/.NET, TypeScript/JS, SQL) **and** Terraform, runs
locally via **Lefthook** (default) or **pre-commit**, and can open an optional
autonomous **fix-loop** on opted-in PRs. The recommended entry point is the
one-command orchestrator `setup-scan-fix`.

> **Pin consumers to `@v2.0.0`, never `@main`.**

## Prerequisites

| Requirement | Minimum Version | Used by |
|------------|----------------|---------|
| Python | 3.8+ | `scan-config.yaml` rendering, several hooks |
| Git | 2.0+ | hooks |
| Lefthook | 1.6+ | default local runner |
| pre-commit | 3.0+ | alternative local runner (`--hooks pre-commit`) |
| GitHub CLI (`gh`) | latest | fix-loop label + secret verification |
| Trivy | 0.48.0+ | Terraform/secrets scanning |
| Checkov | 3.0.0+ | Terraform policy scanning |
| tflint | 0.50.0+ | Terraform linting |
| Gitleaks | 8.0+ | secret detection |
| semgrep | 1.60.0+ | app-code SAST (C#, TypeScript) |
| .NET SDK | 8.0+ | C# format/build (dotnet-format, dotnet-build) |
| Node.js / npm | LTS | TypeScript (eslint, prettier) |
| sqlfluff | 3.0+ | SQL linting |
| Snyk CLI (optional) | 1.0+ | optional Terraform scanning |

## Platform Orchestrator: `setup-scan-fix` (Recommended)

`setup-scan-fix` is the one-command onboarding for the scan->fix platform. It is
**idempotent and re-runnable**. There is a PowerShell script and a cross-platform
Python twin with identical behavior.

```powershell
# Windows (PowerShell)
.\scripts\setup-scan-fix.ps1 -Languages csharp,typescript -Tier standard -EnableFixLoop
```

```bash
# macOS / Linux (Python twin)
python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard --enable-fix-loop
```

```powershell
# Terraform only, AWS
.\scripts\setup-scan-fix.ps1 -Languages terraform -CloudProvider aws

# Use pre-commit instead of the default Lefthook runner
.\scripts\setup-scan-fix.ps1 -Languages csharp -HooksRunner pre-commit
```

**Parameters** (PowerShell `-Name` / Python `--name`):

| Parameter | Values | Notes |
|-----------|--------|-------|
| `-Languages` / `--languages` | csv of `csharp,typescript,terraform,sql` | Languages to enable in `scan-config.yaml` |
| `-Tier` / `--tier` | `starter` \| `standard` \| `strict` | Defaults to `standard` |
| `-HooksRunner` / `--hooks-runner` | `lefthook` \| `pre-commit` | Defaults to `lefthook` |
| `-EnableFixLoop` / `--enable-fix-loop` | flag | Turns on `fix_loop`; copies `autonomous-fix.yml`; creates labels; verifies secrets |
| `-CloudProvider` / `--cloud-provider` | `aws` \| `azure` \| `gcp` | Terraform only; implies `terraform` is enabled |
| `-RepoPath` / `--repo-path` | path | Target consumer repo (defaults to current dir) |
| `-Force` / `--force` | flag | Overwrite an existing `scan-config.yaml` |

**What it does (in order):**

1. **Renders `scan-config.yaml`** from `templates/scan-config/<tier>.yaml` via `scripts/render-scan-config.py`, flipping `enabled: true` for your chosen languages (and `fix_loop`, if requested). Re-running with the same args is deterministic.
2. **Vendors `hooks/` + shared scripts** (`scan-and-fix`, `check-fix-allowlist.py`, `validate-scan-config.py`, `render-scan-config.py`) into the consumer repo so the runner and Claude bundle have what they need.
3. **Installs the local runner.** Lefthook (default): copies `templates/lefthook/lefthook.yml` to `lefthook.yml` and runs `lefthook install`. pre-commit: writes `.pre-commit-config.yaml` from the tier template and runs `pre-commit install` (+ `--hook-type pre-push`). Both call the **same** `hooks/dispatcher.sh` scripts.
4. **Copies the Claude Code in-session bundle** (`templates/claude` -> `.claude/`) and the thin caller workflows: `code-security-scan.yml`, `terraform-scan.yml` (when Terraform is enabled), and `autonomous-fix.yml` (when the fix-loop is on).
5. **Fix-loop only:** creates the `ai-autofix` + `needs-human-review` labels via `gh label create`, then **verifies** (never creates) `AUTOFIX_TOKEN` and `ANTHROPIC_API_KEY` via `gh secret list`, printing exact creation steps if either is missing.
6. **Runs `verify-scanning`** to prove the install.

The caller workflows it copies already reference `@v2.0.0` — keep them pinned.

### Local Runner: Lefthook (default) vs pre-commit

**Lefthook** is the default: a single Go binary with native Windows support
(no Python/cp1252 fragility), parallel hook execution, and friction-free
behavior for autonomous Claude Code loops. **pre-commit** is the fully supported
alternative (`-HooksRunner pre-commit`). They share the same dispatcher hooks, so
there is no logic duplication — the dispatcher OS-detects and routes to `.ps1`
on Windows or `.sh` elsewhere. Bypass: `LEFTHOOK=0 git commit ...` (Lefthook) or
`git commit --no-verify` (pre-commit); both are audited.

### App-Code Scanning

App-code support is configured under `languages.*` in `scan-config.yaml`:

| Language | Tools |
|----------|-------|
| **C# / .NET** | semgrep (`p/csharp`), dotnet-format, dotnet-build (Roslyn analyzers) |
| **TypeScript / JS** | eslint, prettier, semgrep (`p/typescript`) |
| **SQL** | sqlfluff |
| **Terraform** | trivy, tflint, terraform fmt/validate, checkov |

For C#, `csharp.build.solution` and `csharp.build.working_dir` in
`scan-config.yaml` make the `dotnet` path generic — point them at your solution
and directory and the same hooks work in any repo layout.

### Fix-Loop Secrets

The optional fix-loop requires two CI secrets. **The platform verifies them; it
never stores them.**

| Secret | What it is |
|--------|-----------|
| **`AUTOFIX_TOKEN`** | A fine-grained PAT scoped to **this repo only**, with **Contents: Read/Write** and **Pull requests: Read/Write**. Used by the reusable workflow to push fixes and update PRs. |
| **`ANTHROPIC_API_KEY`** | Claude API key (or `CLAUDE_CODE_OAUTH_TOKEN`). |

If either is missing, setup prints the exact `gh secret set ...` command. Add the
`ai-autofix` label to a PR to opt it into the loop; the loop adds
`needs-human-review` when it can't safely proceed.

## Terraform Tool Installer: `setup-scanning` (Legacy)

The original `setup-scanning.ps1` / `.py` remains the **Terraform tool
installer** — it performs Chocolatey/pip installs of Trivy, Checkov, tflint,
Gitleaks, and pre-commit, and wires up the Terraform pre-commit config. Use it
when you only need Terraform scanning, or to install the underlying tools. Its
header points users to `setup-scan-fix` for the full platform.

### Method 1: Cross-Platform Python Setup (Recommended for Terraform-only)

The Python setup script works on macOS, Linux, and Windows.

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier starter
```

**What it does by OS**:

| OS | Package Manager | Tool Installation |
|----|----------------|-------------------|
| macOS | Homebrew | `brew install trivy tflint gitleaks` |
| Linux (Debian/Ubuntu) | apt | `apt-get install trivy` + pip for others |
| Linux (RHEL/Fedora) | yum/dnf | Similar to apt path |
| Windows | Delegates to PS1 | Calls `setup-scanning.ps1` automatically |

**Optional**: If you have a Snyk license, the setup script also installs Snyk CLI via npm (requires Node.js/npm).

**Options**:

```bash
# Dry run (show what would be done)
python scripts/setup-scanning.py --cloud-provider azure --dry-run

# Skip tool installation (config only)
python scripts/setup-scanning.py --cloud-provider gcp --skip-tools

# Force overwrite existing .pre-commit-config.yaml with tier template
python scripts/setup-scanning.py --cloud-provider aws --tier standard --force

# Verbose output
python scripts/setup-scanning.py --cloud-provider aws --tier standard --verbose
```

### Method 2: Windows PowerShell (Admin)

```powershell
.\scripts\setup-scanning.ps1 -CloudProvider aws -Tier starter
```

Uses Chocolatey for tool installation. Requires administrator privileges.

### Method 3: Windows PowerShell (Non-Admin)

```powershell
.\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws -Tier starter
```

Uses Scoop and pip for tool installation. No administrator privileges required.

### Method 4: Manual Installation

1. Install required tools:

   **macOS**:
   ```bash
   brew install trivy tflint gitleaks
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk && snyk auth
   ```

   **Linux (Debian/Ubuntu)**:
   ```bash
   # Trivy
   sudo apt-get install wget apt-transport-https gnupg lsb-release
   wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
   echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
   sudo apt-get update && sudo apt-get install trivy

   # tflint
   curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

   # Gitleaks
   brew install gitleaks  # or download from GitHub releases

   # Checkov and pre-commit
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk && snyk auth
   ```

   **Windows (Chocolatey)**:
   ```powershell
   choco install trivy tflint gitleaks -y
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk
   snyk auth
   ```

2. Copy cloud-specific configs:
   ```bash
   mkdir -p .scanning/configs
   cp configs/aws/.checkov.yaml .scanning/configs/
   cp configs/aws/.tflint.hcl .scanning/configs/
   cp configs/aws/policy-overlay.yaml .scanning/configs/
   ```

3. Copy a tier template:
   ```bash
   cp templates/starter/pre-commit-config.yaml .pre-commit-config.yaml
   ```

4. Install hooks:
   ```bash
   pre-commit install
   pre-commit install --hook-type pre-push
   ```

## Cloud Provider Configuration

During setup, specify your cloud provider to get the correct tool configurations:

```bash
python scripts/setup-scanning.py --cloud-provider azure
```

This copies provider-specific files to `.scanning/configs/`:
- `.checkov.yaml` - Checkov check exclusions for your cloud
- `.tflint.hcl` - tflint ruleset and rules for your cloud
- `policy-overlay.yaml` - Organization-specific policy rules

See [Multi-Cloud Configuration](MULTI-CLOUD.md) for multi-cloud repositories.

## Tier Selection

Tiers map to `templates/scan-config/<tier>.yaml`. `setup-scan-fix` renders the
chosen tier and enables your languages; the legacy `setup-scanning` installer
uses the matching Terraform pre-commit tier template.

| Tier | What runs | Blocking severities | Best For |
|------|-----------|---------------------|----------|
| **starter** | Secret gate (trivy-secrets, gitleaks) + CRITICAL IaC + app-code SAST/format | CRITICAL | New adopters, minimal friction |
| **standard** | All starter + full IaC (checkov, tflint) + dotnet-build at pre-push | CRITICAL,HIGH | Most teams |
| **strict** | All standard + checkov-strict | CRITICAL,HIGH | Security-sensitive projects |

App-code hooks (semgrep, dotnet-format, eslint, prettier, sqlfluff) run for any
language you enable in `scan-config.yaml`, regardless of tier; the tier mainly
governs the heavier pre-push/IaC checks and blocking severities. Snyk IaC remains
optional. See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for upgrade instructions.

## Partial Failure Recovery

If the setup script encounters errors installing some tools:

- **Exit code 0**: All tools installed successfully
- **Exit code 1**: Setup failed completely (missing dependency, permission error)
- **Exit code 2**: Partial setup (some tools installed, some failed)

On partial failure:
1. The script continues installing remaining tools
2. Warnings are printed for each failed tool with manual install instructions
3. Re-running the script is safe (idempotent) -- it skips already-installed tools
4. Fix the failed tools manually, then re-run to verify

Example partial failure output:
```
Setting up security scanning for AWS (starter tier)...
  [OK] Trivy v0.57.0 (>= 0.48.0)
  [OK] Checkov v3.2.1 (>= 3.0.0)
  [WARN] tflint installation failed - run manually: brew install tflint
  [OK] Gitleaks v8.18.0
  [OK] pre-commit v3.6.0 (>= 3.0.0)
  [OK] Configs copied to .scanning/configs/
  [OK] pre-commit hooks installed

Setup complete (4/5 tools). Run 'git commit' to test hooks.
```

## CI/CD Integration

`setup-scan-fix` copies **thin caller workflows** into `.github/workflows/` that
`uses:` the reusable workflows in this repo at a pinned tag. **Always pin to
`@v2.0.0`, never `@main`.**

- **`code-security-scan.yml`** — app-code scanner (C#/TS/SQL). Omit `languages`
  to auto-detect from `scan-config.yaml`, or pin them explicitly.
- **`terraform-scan.yml`** — Terraform/IaC scanner (copied when Terraform is enabled).
- **`autonomous-fix.yml`** — the opt-in fix-loop caller (copied with `-EnableFixLoop`).
  It owns the privilege boundary and `uses:` the reusable fix-loop at `@v2.0.0`.

App-code caller (`code-security-scan.yml`):

```yaml
name: Code Security Scan
on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  security-events: write   # upload SARIF
  pull-requests: write     # PR annotations

jobs:
  code-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v2.0.0
    with:
      # Omit `languages` to auto-detect from scan-config.yaml, or pin explicitly:
      # languages: "csharp,typescript"
      category-prefix: "scan-"
      fail-on-findings: true
```

Terraform caller (`terraform-scan.yml`):

```yaml
jobs:
  terraform-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v2.0.0
    with:
      terraform-directory: "."
      cloud-provider: "aws"          # aws | azure | gcp
      severity: "CRITICAL,HIGH"
      scanning-repo-ref: "v2.0.0"
    # Optional Snyk IaC (needs SNYK_TOKEN secret):
    # secrets:
    #   SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

The fix-loop caller (`autonomous-fix.yml`) runs only when a PR carries the
`ai-autofix` label and a trusted review/comment triggers it; it passes
`AUTOFIX_TOKEN` and `ANTHROPIC_API_KEY` via `secrets: inherit`. See
[SECURITY-MODEL.md](SECURITY-MODEL.md) for the privilege boundary,
[CONSUMER-MIGRATION.md](CONSUMER-MIGRATION.md) for end-to-end fix-loop setup, and the
[workflow interface contract](../specs/001-security-scanning-spec/contracts/workflow-interface.md)
for all inputs and outputs.

## Verification

After setup, verify everything is working. `setup-scan-fix` runs
`verify-scanning` automatically, but you can re-run it any time:

```bash
# Re-run the install verifier (PowerShell)
pwsh -NoProfile -File scripts/verify-scanning.ps1
```

```bash
# Lefthook (default runner): run a stage against all files
lefthook run pre-commit --all-files

# pre-commit alternative
pre-commit run --all-files
pre-commit run trivy-iac-critical --all-files

# Test the optional Snyk hook (requires Snyk CLI + authentication)
pre-commit run snyk-iac --all-files --hook-stage pre-push
```

## Updating

**Platform version (caller workflows):** the copied callers `uses: ...@v2.0.0`.
To move to a new release, bump that tag deliberately (and the `scanning-repo-ref` /
`scanning_repo_ref` inputs where present). Never use `@main`. Re-running
`setup-scan-fix` refreshes the vendored `hooks/`, scripts, and `.claude/` bundle
idempotently.

**pre-commit hooks** (legacy Terraform path):

```bash
# Update hooks to latest version
pre-commit autoupdate

# Update to a specific version
# Edit .pre-commit-config.yaml and change rev: to desired tag
```

See [VERSION-PINNING.md](VERSION-PINNING.md) for version management guidance.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.
