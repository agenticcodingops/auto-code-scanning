# Quickstart

This is the shortest honest path to a first scanned commit and a first CI scan. It
takes a few minutes plus tool downloads. [Getting started](SETUP-GUIDE.md) explains
every step and option; use it when something here does not fit your case.

> **Pin consumers to a release tag or commit SHA, never `@main`.** The current release is `v3.1.3`. <!-- x-release-please-version -->

The commands use Bash (macOS, Linux or Git Bash). [Getting started](SETUP-GUIDE.md)
has the PowerShell version of each one.

## 1. Install the prerequisites

Install Git, Bash 4.4 or later, Python 3.11 or later, PowerShell 7, Terraform,
Lefthook, and Node.js with npm (step 3 installs Prettier with npm), as listed in [Prerequisites](PREREQUISITES.md). An application-only
repository needs Terraform, TFLint and Checkov too, because the setup verifier checks
them. Then create the scanner environment outside your repository:

```bash
python3 -m venv "$HOME/.venvs/auto-code-scanning"
. "$HOME/.venvs/auto-code-scanning/bin/activate"   # Windows Git Bash: .../Scripts/activate
python -m pip install PyYAML==6.0.3 jsonschema==4.26.0 checkov==3.4.5
```

On Windows, Python puts the environment's programs under `Scripts`, not `bin`. In Git
Bash, run `python -m venv` and then
`. "$HOME/.venvs/auto-code-scanning/Scripts/activate"`.

## 2. Clone the platform at the release and install the scanners

Keep this clone; you run the verifier and later upgrades from it.

```bash
PLATFORM="$HOME/tools/auto-code-scanning"
git -c core.autocrlf=false clone https://github.com/agenticcodingops/auto-code-scanning.git "$PLATFORM"
git -C "$PLATFORM" checkout --detach "v3.1.3^{commit}"  # x-release-please-version
SCAN_SHA="$(git -C "$PLATFORM" rev-parse HEAD)"; echo "$SCAN_SHA"
python "$PLATFORM/scripts/install-scanner.py" trivy
python "$PLATFORM/scripts/install-scanner.py" tflint
python "$PLATFORM/scripts/install-scanner.py" gitleaks
export PATH="$HOME/.local-scanning-tools/bin:$PATH"
```

## 3. Provide the trusted external configs

The hooks only use lint and format configs that live outside your repository.
Replace `aws` with `azure` or `gcp` if needed:

```bash
TRUSTED="$HOME/.config/auto-code-scanning/aws"
mkdir -p "$TRUSTED"
cp "$PLATFORM/configs/aws/.tflint.hcl" "$TRUSTED/tflint.hcl"
export SCAN_TFLINT_CONFIG="$TRUSTED/tflint.hcl"
export SCAN_TFLINT_PLUGIN_DIR="$TRUSTED/plugins"

FORMAT_TOOLS="$HOME/.config/auto-code-scanning/formatters"
mkdir -p "$FORMAT_TOOLS"
npm install --prefix "$FORMAT_TOOLS" prettier@3.6.2
printf '{}\n' > "$FORMAT_TOOLS/prettier.json"
printf '**/schemas/**\n' > "$FORMAT_TOOLS/.prettierignore"
export SCAN_PRETTIER_BIN="$FORMAT_TOOLS/node_modules/.bin/prettier"
export SCAN_PRETTIER_CONFIG="$FORMAT_TOOLS/prettier.json"
```

For TypeScript, also set `SCAN_ESLINT_BIN` and `SCAN_ESLINT_CONFIG` to an ESLint 9 or
later installed outside the repository.

These settings last only for this terminal. Before you commit from an IDE or a new
terminal, make them permanent:
[keep the settings](SETUP-GUIDE.md#keep-the-settings-for-new-terminals-ides-and-git-clients).

## 4. Run setup once

From the root of your repository (it must be a Git repository). Setup overwrites
`lefthook.yml`, vendored `hooks/`, `schemas/` and `scripts/` files, provider policy and
caller workflows without asking, so commit or save your changes first.

**(a) Application repository (C# and/or TypeScript):**

```bash
python "$PLATFORM/scripts/setup-scan-fix.py" --languages csharp,typescript --tier starter
```

**(b) Terraform repository:**

```bash
python "$PLATFORM/scripts/setup-scan-fix.py" --languages terraform --cloud-provider aws --tier starter
```

Expect `=== SETUP COMPLETE ===` at the end. If it says `SETUP COMPLETED WITH ERRORS`,
read the messages above it and [Troubleshooting](TROUBLESHOOTING.md#setup-verification-output).

Then add these lines to `.gitignore` and `.gitattributes` (the
[examples](../examples/) contain both files):

```gitignore
.scan-results/
.scan-baseline/tmp/
__pycache__/
.scanning/*
!.scanning/configs/
```

```gitattributes
*.sh text eol=lf
*.py text eol=lf
*.json text eol=lf
*.yaml text eol=lf
*.yml text eol=lf
```

## 5. Make the first scanned commit

Leave the caller workflows that setup copied into `.github/workflows/` out of this
commit; step 6 adds them in a second pull request:

```bash
git add -- . ':(exclude).github/workflows'
git commit -m "chore: adopt security scanning"
```

The hooks run before the commit is recorded. A clean result looks like:

```text
[trivy-secrets] Scanning... (12 staged files)
[trivy-secrets] PASS: No findings above threshold
```

A blocked commit names the hook, each finding and a summary, then Git stops:

```text
[trivy-secrets]   CRITICAL  aws-access-key-id  config/settings.json:4-4
[trivy-secrets]     AWS Access Key ID
[trivy-secrets] FAIL: 1 findings (1 critical, 0 high, 0 medium, 0 low)
```

Read it as: severity, rule, `file:first-line-last-line`, then the rule's title. Fix the
file, `git add` it and commit again. An error such as `trivy not found; scan
incomplete` is not a finding: a tool or setting is missing, and the commit is blocked
until you fix it. See [Troubleshooting](TROUBLESHOOTING.md).

## 6. Add the CI scan

Setup copied caller workflows into `.github/workflows/`: `code-security-scan.yml`
always, and `terraform-scan.yml` for Terraform. Replace the release tag on each `uses:`
line, and the `scanning-repo-ref` value in `terraform-scan.yml`, with the full SHA you
printed in step 2:

```yaml
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@<full-sha> # v3.1.2
    with:
      scanning-repo-ref: "<full-sha>"
```

In `terraform-scan.yml`, set `cloud-provider` to your provider.

The CI scan reads `scan-config.yaml` from the pull request's **base** branch. So use
two pull requests:

1. A first pull request with `scan-config.yaml`, `.scanning/configs/` and the hook
   files, **without** the files in `.github/workflows/`. Merge it.
2. A second pull request that adds the caller workflows. Its checks are your first CI
   scan.

The [example repositories](../examples/) show the finished files. Next steps: require
the checks in branch protection ([consumer operations](consumer-repo-setup-guide.md#branch-protection)),
raise the tier when you are ready ([tier upgrades](TIER-UPGRADE-GUIDE.md)), and only
then consider the optional [fix loop](FIX-LOOP.md).
