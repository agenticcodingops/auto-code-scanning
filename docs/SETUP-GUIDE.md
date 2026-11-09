# Getting started

Use this guide to add auto-code-scanning to a repository. A **consumer** is a repository
that uses the platform. A **hook** is a program Git runs before a commit or push.
**CI** (continuous integration) repeats security checks on the hosted pull request.
Start with scanning; enable the optional automatic fix workflow only after scans work.

> **Pin consumers to a release tag or commit SHA, never `@main`.** The current release is `v3.0.9`. <!-- x-release-please-version -->

## 1. Prerequisites

Install tools outside the consumer checkout, including Python virtual environments
(isolated Python package directories). Verified tools inside the checkout, or links
into it, are refused even with `SCAN_ALLOW_TOOL_ERRORS=1`. Keep the platform clone
outside the consumer too. These are supported floors, not a claim that every release
combination has been tested; the release's exact scanner versions are in
[version pinning](VERSION-PINNING.md#scanner-versions-in-the-terraform-scan).

| Tool | Version | Needed for |
|---|---|---|
| Bash | 4.4+ | Dispatcher and shell hooks, including Git Bash on Windows |
| Python | 3.11+ with PyYAML and jsonschema | Setup, snapshots and validation |
| PowerShell (`pwsh`) | 7+ | Setup verification on every OS; native Windows hooks |
| Git | 2.0+ | Repository, index and hooks |
| Trivy | 0.48.0+; release lock selects 0.75.0 | Secrets and Terraform security |
| Checkov | 3.0.0+ | Terraform policy and setup verification |
| TFLint | 0.50.0+; release lock selects 0.64.0 | Terraform lint and setup verification |
| Gitleaks | 8+; release lock selects 8.30.1 | Additional local secret checks |
| Lefthook **or** pre-commit | 1.6+ **or** 3.0+ | Git hook runner; Lefthook is the default |
| Terraform | Match your project's `required_version` | Terraform formatting, validation and setup verification |
| terraform-docs | Compatible with the pinned pre-commit-terraform revision | Required only for the strict pre-commit runner's `terraform_docs` hook |
| Node.js / npm | Supported long-term support (LTS) release | JavaScript runtime/package manager; external Prettier for Lefthook |
| Semgrep | 1.60+ | C# and TypeScript security checks |
| .NET SDK | 8+ or your project's required SDK | C# formatting and builds |
| SQLFluff | 3+ | SQL linting, if selected |
| GitHub CLI (`gh`) | Current supported release | Optional fix-loop labels and secret verification |

For strict pre-commit, install `terraform-docs` from your managed package source
and check `terraform-docs --version` before staging Terraform. Lefthook does not
require it merely because its configuration tier is strict.

The setup verifier currently checks Terraform tools even in an application-only
consumer. Provision them when using that verifier. Local tool versions come from
PATH; they are not set by `scan-config.yaml`.

On Windows, install Git for Windows (including Git Bash), Python and PowerShell 7
from your managed package source. Open a new PowerShell 7 terminal after installation.
Ensure `bash` selects Git Bash rather than the WSL launcher. On macOS:

```bash
brew install bash powershell python git lefthook terraform node
export PATH="$(brew --prefix bash)/bin:$PATH"
bash --version
```

Persist that PATH in your shell startup file: macOS `/bin/bash` is too old. On Linux,
install Bash, Git, Python with venv support, PowerShell 7, Terraform, Node.js and your
runner from their supported packages. Use `python3` instead of `python` below if
that is your Python 3.11+ command. On all platforms check `bash --version`,
`python --version`, `pwsh --version`, `git --version` and `terraform --version`.

Install PyYAML, jsonschema and Checkov into an external environment. Example for
PowerShell (keep this environment active for subsequent steps):

```powershell
python -m venv "$HOME/.venvs/auto-code-scanning"
& "$HOME/.venvs/auto-code-scanning/Scripts/Activate.ps1"
python -m pip install PyYAML==6.0.3 jsonschema==4.25.1 checkov==3.3.19
```

macOS/Linux equivalent:

```bash
python3 -m venv "$HOME/.venvs/auto-code-scanning"
. "$HOME/.venvs/auto-code-scanning/bin/activate"
python -m pip install PyYAML==6.0.3 jsonschema==4.25.1 checkov==3.3.19
```

Install Lefthook from your managed package source. If choosing pre-commit instead,
keep it in a separate external environment: its virtualenv dependency can require
a newer `packaging` package than Checkov accepts. In PowerShell:

```powershell
python -m venv "$HOME/.venvs/acs-pre-commit"
& "$HOME/.venvs/acs-pre-commit/Scripts/python.exe" -m pip install pre-commit==4.3.0
$env:PATH = "$HOME/.venvs/auto-code-scanning/Scripts;$HOME/.venvs/acs-pre-commit/Scripts;$env:PATH"
pre-commit --version
```

macOS/Linux:

```bash
python -m venv "$HOME/.venvs/acs-pre-commit"
"$HOME/.venvs/acs-pre-commit/bin/python" -m pip install pre-commit==4.3.0
export PATH="$HOME/.venvs/auto-code-scanning/bin:$HOME/.venvs/acs-pre-commit/bin:$PATH"
pre-commit --version
```

These paths assume the scanner environment above. Keep its Python first on PATH
if using different paths, while making the separate runner available. Scanner
installation commands follow in step 4, after obtaining the verified release clone.

## 2. Choose a tier and runner

A **tier** is a starting configuration, not a timer. Choose `standard` unless your
team needs a smaller initial set or stricter policy. The runner manifests and
`scan-config.yaml` are separate: changing a language's `enabled` flag does not
remove commands from the installed manifest.

| Tier | Configuration defaults | Terraform pre-commit template |
|---|---|---|
| starter | CRITICAL threshold; formatters; Semgrep disabled | Secrets with Trivy, private-key detection, basic hygiene, Terraform formatting |
| standard | CRITICAL/HIGH; Semgrep enabled; Checkov/TFLint configured | Adds Gitleaks, Trivy IaC, Terraform validation and push TFLint |
| strict | CRITICAL/HIGH/MEDIUM; build enabled; fix-loop setting enabled | Adds full push IaC, strict Checkov, suppression validation and terraform-docs |

Lefthook installs the **same manifest for every tier**: secret gates, file-triggered
language/formatter hooks, and push Checkov, TFLint and .NET build. The tier does not
rewrite that manifest or make every wrapper read its severity setting. In particular,
Trivy's `trivy-iac-critical` hook is CRITICAL-only. The pre-commit tier templates are
Terraform-focused; add application hooks deliberately using [the hook reference](HOOK-REFERENCE.md).
See [tier upgrades](TIER-UPGRADE-GUIDE.md) for exact template differences.

## 3. Choose languages and repository visibility

For Terraform choose `--languages terraform --cloud-provider aws` (or `azure` / `gcp`).
For application code choose `--languages csharp,typescript`; combine all three for
a mixed repository. SQL linting is available locally with `sql`. Hosted application
security scanning uses Semgrep for C#/TypeScript and a separate secret scan; it
does not run all local formatters or SQLFluff.

A public repository can upload SARIF (Static Analysis Results Interchange Format)
reports to the Security > Code scanning view. For a private repository, confirm
code scanning is available and enabled for that repository under its plan. If it
is unavailable, set `upload-sarif: false` on **both** scan callers; scans and their
gates still run. Terraform upload failures fail its separate Upload SARIF job by
default; require that check and keep `allow-sarif-upload-errors: false` if delivery
must block merging. The required check still does not prove delivery of every category:
missing SARIF files can skip individual uploads. Inspect expected artifacts and
categories as well as the check result. Application SARIF upload
steps tolerate delivery failures, so successful app scan jobs do not prove upload.
Inspect their upload logs separately. `fail-on-findings: false` only
relaxes finding thresholds; incomplete scans still fail.

Every explicit caller permission ceiling, including intermediate reusable callers,
needs `contents: read`, `actions: read` and `security-events: write`. Keep these even
when uploads are disabled: the called jobs request them unconditionally. The Terraform
caller also needs `pull-requests: write`, for its PR findings-comment job; no job in
the application-code caller currently uses it, though the shipped template still
requests it. Private SARIF uploads also read workflow-run metadata
and therefore need `actions: read`. Scanning alone needs no repository secrets.

## 4. Obtain and pin the release

Run from a directory **outside** your consumer. A release tag names a release;
a full commit SHA identifies its exact contents. Resolve the tag, then keep this
clone at that SHA. The commands below use PowerShell:

```powershell
$Platform = Join-Path $env:TEMP 'acs-platform'
git -c core.autocrlf=false clone https://github.com/agenticcodingops/auto-code-scanning.git $Platform
$Release = (Get-Content "$Platform/version.txt").Trim()
git -C $Platform fetch origin --tags
$ScanSha = (git -C $Platform rev-parse "refs/tags/v${Release}^{commit}").Trim()
git -C $Platform checkout --detach $ScanSha
$ScanSha
python "$Platform/scripts/install-scanner.py" trivy
python "$Platform/scripts/install-scanner.py" tflint
python "$Platform/scripts/install-scanner.py" gitleaks
$env:PATH = "$HOME/.local-scanning-tools/bin;$env:PATH"
```

Inspect the release notes before choosing a release; `version.txt` on the fetched
default branch identifies the last release. If adopting a different release, set
`$Release` to its version without the `v` prefix before resolving the tag. If the
clone directory already exists, use a clean external clone or a different path.
The locked installers support Windows AMD64 (x64), not native Windows ARM64:
`scanner-downloads.json` has no `windows-arm64` entries. Do not assume these
commands support an ARM64 Python installation. Use a supported platform for this
path; no native Windows ARM64 installation has been verified here.

The installer verifies each archive against the committed SHA-256 before extracting
the binary. Do not substitute an unverified download script.

macOS/Linux:

```bash
PLATFORM="$(mktemp -d)/auto-code-scanning"
git -c core.autocrlf=false clone https://github.com/agenticcodingops/auto-code-scanning.git "$PLATFORM"
RELEASE="$(cat "$PLATFORM/version.txt" | tr -d '\r\n')"
git -C "$PLATFORM" fetch origin --tags
SCAN_SHA="$(git -C "$PLATFORM" rev-parse "refs/tags/v${RELEASE}^{commit}")"
git -C "$PLATFORM" checkout --detach "$SCAN_SHA"
printf '%s\n' "$SCAN_SHA"
python "$PLATFORM/scripts/install-scanner.py" trivy
python "$PLATFORM/scripts/install-scanner.py" tflint
python "$PLATFORM/scripts/install-scanner.py" gitleaks
export PATH="$HOME/.local-scanning-tools/bin:$PATH"
```

Keep the resulting SHA for the caller workflows in step 6. Persist the scanner PATH
and trusted environment variables below in your developer environment.

### Windows setup output fix

Release `v3.0.6`'s Python setup can fail while reading or forwarding tool output
on Windows with a non-UTF-8 console code page. The fix in
[PR 104](https://github.com/agenticcodingops/auto-code-scanning/pull/104) is newer
than that release tag. If your selected release does not include the fix, choose
a newer release that includes it or use this exact reviewed commit for Windows
setup and all consumer pins. For the latter, after the clone commands above run:

```powershell
$ScanSha = '8321adf7020025a5a7a6c7cd8d1780015b18a07a'
git -C $Platform checkout --detach $ScanSha
```

Continue with step 5 from that clone. Keep `$ScanSha` for every pin in step 6;
do not copy the affected setup script from the older release into the consumer.
The scanner lock is unchanged by this fix. Other platforms and releases that
include this commit can use the release pin above without this override.

## 5. Install local hooks

First provision **trusted** TFLint inputs outside the consumer. Review the selected
cloud configuration and its plugin sources and versions; it must contain no
`plugin_dir` setting. PowerShell:

```powershell
$Trusted = Join-Path $HOME '.config/auto-code-scanning/aws'
New-Item -ItemType Directory -Force $Trusted | Out-Null
Copy-Item "$Platform/configs/aws/.tflint.hcl" "$Trusted/tflint.hcl"
$env:SCAN_TFLINT_CONFIG = "$Trusted/tflint.hcl"
$env:SCAN_TFLINT_PLUGIN_DIR = "$Trusted/plugins"
```

macOS/Linux:

```bash
TRUSTED="$HOME/.config/auto-code-scanning/aws"
mkdir -p "$TRUSTED"
cp "$PLATFORM/configs/aws/.tflint.hcl" "$TRUSTED/tflint.hcl"
export SCAN_TFLINT_CONFIG="$TRUSTED/tflint.hcl"
export SCAN_TFLINT_PLUGIN_DIR="$TRUSTED/plugins"
```

Use your selected provider consistently in these paths. Keep this configuration
and plugin cache outside contributor control. The copied in-repository TFLint
configuration is not used as trusted executable policy.

The Lefthook manifest also formats Markdown and JSON, including generated setup
files, even in Terraform-only repositories. Before the first commit, install
Prettier outside the consumer and supply an explicit external config. PowerShell:

```powershell
$FormatTools = Join-Path $HOME '.config/auto-code-scanning/formatters'
New-Item -ItemType Directory -Force $FormatTools | Out-Null
npm install --prefix $FormatTools prettier@3.6.2
'{}' | Set-Content -Encoding utf8 "$FormatTools/prettier.json"
'**/schemas/**' | Set-Content -Encoding utf8 "$FormatTools/.prettierignore"
$env:SCAN_PRETTIER_BIN = "$FormatTools/node_modules/.bin/prettier.cmd"
$env:SCAN_PRETTIER_CONFIG = "$FormatTools/prettier.json"
```

macOS/Linux:

```bash
FORMAT_TOOLS="$HOME/.config/auto-code-scanning/formatters"
mkdir -p "$FORMAT_TOOLS"
npm install --prefix "$FORMAT_TOOLS" prettier@3.6.2
printf '{}\n' > "$FORMAT_TOOLS/prettier.json"
printf '**/schemas/**\n' > "$FORMAT_TOOLS/.prettierignore"
export SCAN_PRETTIER_BIN="$FORMAT_TOOLS/node_modules/.bin/prettier"
export SCAN_PRETTIER_CONFIG="$FORMAT_TOOLS/prettier.json"
```

Skip that formatter provisioning only if choosing the Terraform pre-commit runner.
The external ignore file keeps vendored schemas byte-identical; merge its rule if
you already have an ignore file there. The trusted formatter runs from this external
directory, so a consumer's own `.prettierignore` does not supply this protection.
For TypeScript, also provision external ESLint 9+ with reviewed parsers/plugins and
set `SCAN_ESLINT_BIN` and `SCAN_ESLINT_CONFIG` to its absolute binary/config paths.
[Application-code scanning](APP-CODE-SCANNING.md) explains the external-tool boundary
and the explicit trusted-repository alternative. For C#, install Semgrep externally
and set `languages.csharp.build.working_dir` to the solution directory and `solution`
relative to that directory (for example `api` and `App.slnx`). Local .NET build and
format hooks execute project logic; enable them only for repositories you trust.

Now enter the consumer repository root (it must already be a Git repository).
Before running setup, save copies of any existing `lefthook.yml` and other files
setup can replace (see the list below): setup replaces them without a prompt on
every run, including the first, and including uncommitted edits.
Run **one** setup command. If selecting strict for scanning only, explicitly set
`fix_loop.enabled: false` afterwards: the strict template defaults it to true. These examples use Terraform on AWS and standard tier:

```powershell
python "$Platform/scripts/setup-scan-fix.py" --languages terraform --cloud-provider aws --tier standard --hooks-runner lefthook
```

macOS/Linux:

```bash
python "$PLATFORM/scripts/setup-scan-fix.py" --languages terraform --cloud-provider aws --tier standard --hooks-runner lefthook
```

For application code, replace the language/provider arguments with
`--languages csharp,typescript`. These arguments render a new config only. If
`scan-config.yaml` exists, edit the relevant `languages.<name>.enabled` and build/tool
settings explicitly, preserving reviewed settings; do not assume setup enabled them.
Use `--force` only after reviewing what replacing the entire config would change.
With hosted automatic language detection, merge reviewed language enablement into
the base before adding code in that language. A PR that enables a language and
adds its code still uses the base's earlier language selection. For the alternative runner use
`--hooks-runner pre-commit`; setup installs its push transaction adapter too.
Do not replace that adapter with a plain `pre-commit install --hook-type pre-push`.
The setup script copies hooks, schemas, shared scripts, provider policy, an optional
editor integration bundle under `.claude/`, and caller workflows. It overwrites
vendored hooks, schemas, shared scripts, provider policy, the Lefthook manifest,
caller workflows and the four shipped `.claude/hooks/` files, on every run including
the first. Save external copies of every file it can replace before running it,
including uncommitted edits. Compare the result and restore reviewed consumer settings afterwards; shared core
code must match the selected revision. Git cannot recover an uncommitted overwritten edit.
An existing `scan-config.yaml` is kept unless `--force` is supplied. Tool installation
is separate from setup. A nonzero setup result needs investigation before continuing.

Track policy before the first push. Ignore runtime reports while retaining policy:

```gitignore
.scan-results/
.scan-baseline/tmp/
__pycache__/
.scanning/*
!.scanning/configs/
```

Merge these rules into your `.gitignore`. If an older rule ignores `.scanning/`
entirely, remove that rule or explicitly force-add `.scanning/configs/.checkov.yaml`.
The push scanner requires that policy in the pushed tree. Also track `scan-config.yaml`,
`hooks/`, `schemas/`, `scripts/`, your runner file, caller workflows and any editor
integration you keep. Never put tokens in these files.

Keep vendored shell files at LF line endings. Merge the following into the consumer's
`.gitattributes` before staging files, especially on Windows:

```gitattributes
*.sh text eol=lf
*.py text eol=lf
*.json text eol=lf
*.yaml text eol=lf
*.yml text eol=lf
```

## 6. Configure CI callers

A **caller** is a small workflow that invokes a reusable workflow. Setup copies
release-tagged callers. Before committing, replace each platform `uses:` tag with
the full SHA from step 4, and set `scanning-repo-ref` to the **same SHA**.
Change the provider and scan directory in the Terraform caller as needed.
Before opening the first hosted adoption PR, ensure the target base already
contains reviewed `scan-config.yaml` and scanner policy. App language detection
reads the exact base commit; without that config it fails and the dependent secret
scan cannot run. Bootstrap with a separate reviewed configuration-only PR, validated
and scanned locally, without adding the new active caller workflows to it. Merge
that policy first, then rebase the adoption branch and add the callers and remaining
integration files. Enable the new required checks after their first successful run.
This keeps policy approval separate from the changes it authorizes.

These are the release-managed tag examples; use their resolved full SHA in consumers:

Use **two separate caller files** with distinct workflow names, as setup copies
them. Combining these jobs under one caller can make their reusable concurrency
groups cancel each other. Retain/adapt the copied triggers in each file.

```yaml
# .github/workflows/code-security-scan.yml
name: App Code Security Scan
on: [pull_request, push, workflow_dispatch]
permissions:
  contents: read
  actions: read
  security-events: write
  pull-requests: write
jobs:
  code-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v3.0.9 # x-release-please-version
    with:
      fail-on-findings: true
      # upload-sarif: false  # private repository without code scanning
```

```yaml
# .github/workflows/terraform-scan.yml
name: Terraform Security Scan
on: [pull_request, push, workflow_dispatch]
permissions:
  contents: read
  actions: read
  security-events: write
  pull-requests: write
jobs:
  terraform-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v3.0.9 # x-release-please-version
    with:
      terraform-directory: "."
      cloud-provider: "aws"          # aws | azure | gcp
      scanning-repo-ref: "v3.0.9" # x-release-please-version
      # upload-sarif: false  # private repository without code scanning
```

Keep the copied `pull_request`, `push` and `workflow_dispatch` triggers and adapt
branch names. IaC helpers default to the published platform repository; a reviewed
mirror requires explicit `scanning-repository`. There is no requirement to create
a same-owner platform copy. A Terraform-only consumer may keep the app-code caller
for its independent secret scan. Do not disable `run-secret-scan` to work around
an upload problem. For the pre-commit runner, replace the platform repository's
`rev:` tag with the same full SHA as well.

The optional fix-loop is a separate adoption step:
[FIX-LOOP.md](FIX-LOOP.md) covers its base policy, label, named secrets and caller
boundary. When enabling it, pin its `uses:` and `scanning_repo_ref` together too.

## 7. Verify setup

From the consumer root, run the verifier **from the external platform clone**;
setup does not vendor all of its dependencies. Choose your actual runner and tier:

```powershell
pwsh -NoProfile -File "$Platform/scripts/verify-scanning.ps1" -HooksRunner lefthook -Tier standard
$env:STRICT = '1'; python scripts/validate-scan-config.py
```

macOS/Linux:

```bash
pwsh -NoProfile -File "$PLATFORM/scripts/verify-scanning.ps1" -HooksRunner lefthook -Tier standard
STRICT=1 python scripts/validate-scan-config.py
```

Expect exit 0 and zero failed verifier checks. An optional missing `.trivyignore`
can produce a warning. Setup may display only a bounded prefix of verification
output, but must still drain the verifier to completion and preserve its exit
status. PowerShell setup uses `Select-Object -First 30 -Wait` and checks
`$LASTEXITCODE`; Python setup captures both streams and checks the completed
process status before displaying output. Any added output limit must retain
that contract. See [verification output troubleshooting](TROUBLESHOOTING.md#setup-verification-output).

This proves installation, not that every security rule was
exercised. The verifier checks the shipped runner template exactly, including pre-commit
revisions. With that alternative runner, verify the generated tag-based template
before replacing its platform `rev:` with the full SHA, then review that pin change
and exercise a real commit separately. Customized runner settings need separate review. See [consumer acceptance tests](TESTING-GUIDE-CONSUMING-REPO.md)
for Git transaction, application and hosted checks.

## 8. Make the first scan and commit

Use a real staged Terraform change so the commit scans more than setup files. For
a fresh local test repository, this minimal file needs no cloud credentials:

```hcl
terraform {
  required_version = ">= 1.0"
}
```

Save that as `main.tf`. Save the variable in `variables.tf`:

```hcl
variable "example" {
  type        = string
  description = "A non-secret onboarding value."
  default     = "hello"
}
```

Reference it in `outputs.tf` so the push linter sees a complete, used declaration:

```hcl
output "example" {
  description = "The non-secret onboarding value."
  value       = var.example
}
```

Run these commands from the consumer root on any OS:

```bash
git add .
git diff --cached --name-only
git commit -m "chore: adopt security scanning"
```

Inspect the hook output: secret checks should run, with exit 0 on this clean
example. Lefthook and standard/strict pre-commit also run Terraform security checks.
Starter pre-commit runs Terraform formatting without a Terraform security hook;
use the on-demand scan below for its Terraform security check. If a formatter edits files, inspect and stage those edits
and retry the commit. Do not confuse a skipped hook with a completed scan.
Applicable hooks write `.scanning/last-scan.json`; parallel reporters replace this
shared file, so the last report wins. A no-input hook may produce no report. The
writer retries transient sharing/access conflicts within a bounded loop and uses
atomic replacement; persistent errors block, and unsafe paths stop immediately.

For an on-demand Terraform scan (working tree rather than staged bytes):

```bash
python scripts/scan.py . --tools trivy --format json
```

Exit 0 means clean at the selected threshold, 1 means findings and 2 means a tool
error. Commit-stage security scanners read a captured index snapshot; unchanged
Terraform siblings and variable overrides provide context, but reports select
changed files. SQLFluff and formatters read the working tree. At push, scanners
read exact pushed objects and select changes for each ref and destination, not the
current index. See [hook semantics](HOOK-REFERENCE.md) for exclusions and failure rules.

For a real hosted repository, complete the base-policy bootstrap in step 6 before
opening the PR that enables the callers. Then confirm each
scan job and aggregate gate passes, and check SARIF delivery when enabled. Use the
full emitted check names in [branch protection](consumer-repo-setup-guide.md#branch-protection).
A local-only walkthrough stops before pushing and does not prove hosted upload.

## 9. Suppressions and baselines

Check `suppressions.file` in `scan-config.yaml` and use that registry path in
creation, validation and commits. Examples here use the default `.scan-suppressions.yaml`.

Fix new findings first. A **suppression** is an approved, expiring exception for an
exact finding. A **baseline** records reviewed existing debt so new occurrences
remain visible. Neither is a way to approve an incomplete scan.

Generate current fingerprints without hiding existing exceptions:

```bash
python scripts/scan.py . --skip-baseline --skip-suppressions --format json
```

Use schema `2.0` in `.scan-suppressions.yaml` and `.scan-baseline/baseline.json`.
A `v1:` fingerprint identifies tool, rule, repository path, resource, line range and
source-content hash; each entry approves one occurrence. Source edits invalidate it.
HIGH/CRITICAL suppression approval is mandatory and expiry is capped at 180 days.
Follow [suppression governance](SUPPRESSION-GOVERNANCE.md) for the complete entry format.

Create a baseline from the consumer root after reviewing all selected tools:

```bash
pwsh -NoProfile -File scripts/create-baseline.ps1 -Tool all -TerraformDir . -CloudProvider aws -Force
```

The creator uses explicit passive Checkov policy and verified external tools and
Python. Missing/invalid reports fail and preserve an existing baseline. Review which
tools actually ran, the occurrence entries and the resulting diff before committing.
`-MonorepoScope` can restrict modules; default output remains at the repository root
when invoked from a subdirectory. A separate `-PolicyRoot` checkout must be external.

Pull-request policy comes from the exact base commit; an exception added in the PR
becomes effective after merging into that base. Unchanged Checkov inline skips can
be honoured on the same base-approved resource or module with the same justification
and literal module source. New, changed, ambiguous or unsupported skips remain
findings. See [inline skip migration](CONSUMER-MIGRATION.md#trusted-base-inline-skip-migration).

## 10. Upgrade between releases

Read the release notes and [v3 behaviour audit](V3-BEHAVIOUR-AUDIT.md), especially
breaking changes. Resolve the new tag's full SHA into a clean external clone.
Re-vendor hooks, their complete library, scripts and schemas **byte for byte** from
that revision. For pre-commit, save the current runner config externally, then
prepare the new tier template with its tag-based `rev:` before setup: an existing
runner file is preserved, and the verifier requires exact template settings.
Run setup and template verification before restoring custom runner settings or
full-SHA hook pins. Setup also overwrites provider policy and caller templates;
save those files first and compare them afterwards.
Review and restore consumer-specific settings afterwards; do not silently preserve
modified shared code. Move every platform `uses:`, hook `rev:`, `scanning-repo-ref`
and optional `scanning_repo_ref` together to the new SHA. Review config/schema changes
and verify the generated template before applying full-SHA hook pins and reviewed
customizations. Validate and exercise the final configuration with a scanned
commit and hosted checks before merging; customized manifests need separate review.
[Migration](CONSUMER-MIGRATION.md), [version pinning](VERSION-PINNING.md) and
[BUMP-THE-SCAN.md](BUMP-THE-SCAN.md) cover older installations and rollback.

## 11. Troubleshooting

| Symptom | Next action |
|---|---|
| Bash version diagnostic | Install Bash 4.4+ and put it before the system Bash/WSL launcher on PATH |
| Python snapshot error | Use external Python 3.11+; check `python -E -P -c "import yaml, jsonschema"` |
| Tool rejected inside checkout | Move the executable/environment outside both consumer and snapshot; do not use the tool-error override |
| TFLint setup failure | Restore external `SCAN_TFLINT_CONFIG` and `SCAN_TFLINT_PLUGIN_DIR`; review plugin download diagnostics |
| Checkov policy rejected | Use the passive key allowlist in [the hook reference](HOOK-REFERENCE.md); executable extensions and module downloads are rejected |
| Push says policy missing | Track `.scanning/configs/.checkov.yaml` in the pushed commit; a worktree-only file is insufficient |
| Formatter fails in Terraform-only Lefthook setup | Provision external Prettier: the manifest also formats JSON and Markdown |
| SARIF permission error | Grant `actions: read` through every caller ceiling; if private code scanning is unavailable set `upload-sarif: false` |
| Commit fails without a finding | Read snapshot/report/tool diagnostics; incomplete security scans block by default |
| Setup rerun changed callers | Review generated files and restore your full SHA pins after setup |

More cases: [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Local errors never justify
assuming the scan was clean; CI scanner/report health remains mandatory.
