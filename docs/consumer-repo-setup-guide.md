# Consumer operations reference

For installation, use [Getting started](SETUP-GUIDE.md). This page covers controls
and maintenance after adoption; it does not define a second setup path.

> **This guide uses the current release, `v3.1.0`.** <!-- x-release-please-version -->

## Branch protection

In **Settings → Branches → Branch protection rules** for `main`, require **every**
security job emitted by the scan callers. For the app-code caller, select:

- `Detect languages`;
- `Semgrep (csharp)` when C# is enabled;
- `Semgrep (typescript)` when TypeScript/JavaScript is enabled;
- `Secret scan` (keep `run-secret-scan: true`).

Copy each full context from the pull request's Checks tab after the first run:
caller workflow/job prefixes vary. A passing language job does not cover another
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

Scope the push token to this repository only, with Contents and Pull requests read/write,
and a short expiry under your rotation policy. Store it through `gh secret set
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
- To remove scanning, uninstall the runner hooks, remove its configuration and
  caller workflows, and remove the editor integration if unused. Adjust required
  checks deliberately so branch protection does not wait for removed jobs.

## Manual installation inventory

If you maintain setup by hand, reproduce the files selected by
`scripts/setup-scan-fix.py` at your chosen release, rather than an old partial list:
complete `hooks/` (including `hooks/lib/`), `schemas/`, every script in its vendoring
list, the provider policy, runner template and caller workflows. Include the
optional editor bundle only if used. Render and validate `scan-config.yaml`,
provision trusted external lint/formatter inputs, track push policy, and install
the push transaction adapter for the alternative runner. Then repeat the canonical
verification and first-commit steps. Keep shared files byte-identical to the release.

## Release-managed compatibility references

These retained lines are maintained by release automation for existing users of
this page. Resolve the named tag to a full SHA and follow Getting started for
executable installation commands; `<commit-sha>` and `/path/to` are placeholders.

```text
git clone --branch v3.1.0 https://github.com/agenticcodingops/auto-code-scanning.git /path/to/auto-code-scanning  # x-release-please-version
git commit -m "chore: adopt auto-code-scanning v3.1.0 (scan + fix-loop)"  # x-release-please-version
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v3.1.0 # x-release-please-version
    uses: agenticcodingops/auto-code-scanning/.github/workflows/autonomous-fix.yml@<commit-sha> # v3.1.0 x-release-please-version
      scanning_repo_ref: <commit-sha> # v3.1.0 x-release-please-version
   `uses:`, `scanning-repo-ref` and `scanning_repo_ref` to the current release, `v3.1.0`.** <!-- x-release-please-version -->
```

[Application configuration](APP-CODE-SCANNING.md), [workflow inputs](REUSABLE-WORKFLOWS.md),
[suppression governance](SUPPRESSION-GOVERNANCE.md) and [migration](CONSUMER-MIGRATION.md)
remain focused references. Report sensitive security concerns through the repository's
private advisory channel without including exploit details in public issues.
