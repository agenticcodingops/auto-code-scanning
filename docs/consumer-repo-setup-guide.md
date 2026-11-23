# Consumer operations reference

For installation, use [Getting started](SETUP-GUIDE.md). This page covers controls
and maintenance after adoption; it does not define a second setup path.

> **This guide uses the current release, `v3.1.5`.** <!-- x-release-please-version -->

## Branch protection

In **Settings → Branches → Branch protection rules** for `main`, require **every**
security job emitted by the scan callers. For the app-code caller, select:

- `Detect languages`;
- `Semgrep (csharp)` when C# is enabled;
- `Semgrep (typescript)` when TypeScript/JavaScript is enabled;
- `Secret scan` (keep `run-secret-scan: true`).

On the pull request each check is shown after the caller job's name, for example
`code-scan / Detect languages` or `code-scan / Secret scan` with the shipped caller
(its job is called `code-scan`). Copy each full name from the pull request's Checks
tab after the first run. A passing language job does not cover another
language or the independent secret scan. Add a required matrix context whenever
you enable another language. Keep `fail-on-findings: true`; requiring a report-only
job does not block findings. Require these callers on every pull request to `main`,
without path filters that could prevent a required check from running.

If Terraform scanning is enabled, also require `Setup Scanning Tools`, `Trivy IaC Scan`,
`Checkov Policy Scan`, `TFLint Scan` and `Aggregate Results`, plus `Snyk IaC Scan (Optional)` if enabled.
When Terraform SARIF delivery must block merging, also require `Upload SARIF`
when uploads are enabled, and leave `allow-sarif-upload-errors: false`. Missing
SARIF files can still skip individual uploads, so a successful check does not
prove every expected category was delivered; inspect artifacts/categories too.
App-code upload steps tolerate delivery failures, so
their passing jobs do not guarantee delivered alerts; inspect upload logs separately.
For first adoption, bootstrap base-approved configuration as described in
[Getting started CI callers](SETUP-GUIDE.md#6-configure-ci-callers).
Do not require optional fix-loop jobs: they do not run on every pull request.

## Optional fix workflow credentials

Scanning alone needs no secrets. The optional fix workflow needs `AUTOFIX_TOKEN`
and one model credential (`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`), passed
by name as declared by the reusable workflow. See [the migration caller example](CONSUMER-MIGRATION.md#4-pin-the-callers-and-grant-their-permissions).

Scope the push token to this repository only, with Contents read/write (see
[FIX-LOOP.md](FIX-LOOP.md#secrets) for what the workflow uses it for), and a short
expiry under your rotation policy. Store it through `gh secret set
AUTOFIX_TOKEN`; enter its value at the hidden prompt. A push using the built-in
workflow token does not start another scan workflow, which is why the fix loop uses
a separate token. A suitably scoped installation token is another option; arrange
its lifecycle separately rather than storing a long-lived installation token.

Setup creates `ai-autofix` and `needs-human-review` labels only when requested.
Who can apply the opt-in label is part of your trust boundary. Read
[the security model](SECURITY-MODEL.md) before enabling the caller.

## Acceptance and maintenance

Use [consumer acceptance tests](TESTING-GUIDE-CONSUMING-REPO.md) after installation
and every upgrade. A clean install verifier does not replace a scanned commit,
per-language hosted checks and merge protection.

When maintaining C# settings, keep `solution` relative to working_dir: for example,
`working_dir: "api"` with `solution: "App.slnx"`. Do not repeat `api/` in the
solution value. Review these paths after moving projects or upgrading the platform.

- Rotate the push credential before expiry.
- Keep the base-approved build command in a checked-in script under a gated path.
- Assign an owner to `needs-human-review`. Read its comment, fix the problem and
  review `.fix-attempts` before deliberately resetting the counter.
- Upgrade vendored code and all workflow/helper pins together using
  [Getting started](SETUP-GUIDE.md#10-upgrade-between-releases).
- To remove scanning, follow [Uninstall](#uninstall).

## Manual installation inventory

If you maintain setup by hand, reproduce the files selected by
`scripts/setup-scan-fix.py` at your chosen release, rather than an old partial list:
complete `hooks/` (including `hooks/lib/`), `schemas/`, every script in its vendoring
list, the provider policy, runner template and caller workflows. Include the
optional editor bundle only if used. Render and validate `scan-config.yaml`,
provision trusted external lint/formatter inputs, track push policy, and install
the push transaction adapter for the alternative runner. Then repeat the canonical
verification and first-commit steps. Keep shared files byte-identical to the release.

## Uninstall

To pause local hooks without removing anything, set `global.local_hooks_enabled: false`
in `scan-config.yaml`. CI is not affected. Commit hooks read the setting from the working
tree, but push hooks read it from each pushed commit: to pause push scans, commit the
change in the commits you push. To remove scanning completely, work through
the steps below in order. They undo what `scripts/setup-scan-fix.py` installs.

1. **Branch protection first.** Remove the scan checks from the required status checks
   of your protected branches (or rulesets). Otherwise open pull requests wait for
   checks that will never run again.

2. **Remove the local Git hooks.** Run from the repository root.

   Lefthook:

   ```bash
   lefthook uninstall
   ```

   pre-commit: remove the commit hook, then the push transaction adapter (the
   `.git/hooks/pre-push` script setup wrote) and the pre-commit push hook it saved.
   `pre-commit uninstall` does not remove the adapter, because pre-commit did not
   write it.

   ```bash
   pre-commit uninstall
   hooks_dir="$(git rev-parse --git-path hooks)"
   rm -f "$hooks_dir/pre-push" "$hooks_dir/pre-push.pre-commit" "$hooks_dir/pre-push.legacy"
   ```

   Check that `.git/hooks/` no longer contains `pre-commit` or `pre-push` files you do
   not recognise. If you had your own `pre-push` hook before setup, restore it from your
   backup.

3. **Remove the files setup added**, in a pull request so the change is reviewed:

   ```bash
   git rm -r --ignore-unmatch hooks schemas .scanning/configs scan-config.yaml \
     lefthook.yml .pre-commit-config.yaml \
     .github/workflows/code-security-scan.yml .github/workflows/terraform-scan.yml \
     .github/workflows/autonomous-fix.yml \
     .claude/hooks/posttooluse-scan.ps1 .claude/hooks/posttooluse-scan.sh \
     .claude/hooks/stop-scan.ps1 .claude/hooks/stop-scan.sh
   git rm --ignore-unmatch scripts/scan-and-fix.ps1 scripts/scan-and-fix.sh \
     scripts/check-fix-allowlist.py scripts/validate-scan-config.py \
     scripts/render-scan-config.py scripts/scan.py scripts/safe_io.py \
     scripts/scan_policy.py scripts/scan_reports.py scripts/validate-suppressions.py \
     scripts/create-baseline.ps1 scripts/finalize_baseline.py
   ```

   Check the list before running it: keep any file with the same name that your
   project owns (for example your own `lefthook.yml` entries or `hooks/` scripts).
   Setup wrote `.claude/settings.json` only if it did not exist; remove it only if you
   did not customise it. Remove `.scan-suppressions.yaml` and `.scan-baseline/` if you
   created them, and the `.gitignore` and `.gitattributes` lines you added in
   [step 5](SETUP-GUIDE.md#5-install-local-hooks). Delete the untracked `.scanning/`
   and `.scan-results/` folders.

4. **Fix loop only.** Delete the secrets and labels, and revoke the token itself in
   your GitHub settings:

   ```bash
   gh secret delete AUTOFIX_TOKEN
   gh secret delete ANTHROPIC_API_KEY        # or CLAUDE_CODE_OAUTH_TOKEN
   gh label delete ai-autofix --yes
   gh label delete needs-human-review --yes
   ```

5. **Environment variables.** Remove the `PATH` entries and `SCAN_*` variables you
   saved. On Windows (user scope):

   ```powershell
   foreach ($Name in 'SCAN_TFLINT_CONFIG', 'SCAN_TFLINT_PLUGIN_DIR', 'SCAN_PRETTIER_BIN',
                     'SCAN_PRETTIER_CONFIG', 'SCAN_ESLINT_BIN', 'SCAN_ESLINT_CONFIG') {
       [Environment]::SetEnvironmentVariable($Name, $null, 'User')
   }
   ```

   Then edit the user `Path` (System Properties > Environment Variables) to remove
   the scanner entries. On macOS and Linux, delete the lines you added to
   `~/.zprofile` or `~/.profile`.

6. **External tools.** If no other repository uses them, delete the platform clone,
   `~/.local-scanning-tools`, `~/.config/auto-code-scanning` and the virtual
   environments under `~/.venvs/` (`auto-code-scanning`, `acs-pre-commit`).

7. **Code scanning alerts.** Optionally dismiss or delete the alerts the scans
   uploaded, under Security > Code scanning.

## Further reading

[Application configuration](APP-CODE-SCANNING.md), [workflow inputs](REUSABLE-WORKFLOWS.md),
[suppression governance](SUPPRESSION-GOVERNANCE.md) and [migration](CONSUMER-MIGRATION.md)
remain focused references. Report security problems in the platform privately, as
described in [SECURITY.md](../SECURITY.md); do not put exploit details in public issues.
