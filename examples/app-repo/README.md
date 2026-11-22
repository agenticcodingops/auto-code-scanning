# Example: application repository

The files in this folder show what a C# and TypeScript application repository adds to
adopt the auto-code-scanning release named on the callers' `uses:` lines, with the
**starter** tier and the
**Lefthook** runner. They are reference copies to compare against, not a project to
run. Follow the [Quickstart](../../docs/QUICK-START-5MIN.md) or
[Getting started](../../docs/SETUP-GUIDE.md) to install; setup writes these files for you.

## Files

| File | What it is | Where it comes from |
|---|---|---|
| `scan-config.yaml` | Project settings. Here `languages.csharp` and `languages.typescript` are enabled, which tells the CI app-code scan to run Semgrep for both. Set `languages.csharp.build.solution` (relative to `working_dir`) if you use the .NET hooks. | Written by `scripts/render-scan-config.py --tier starter --languages csharp,typescript`, which setup runs. Generated with this repository's renderer, not edited by hand. |
| `.github/workflows/code-security-scan.yml` | Caller of the app-code scan (`code-security-scan.yml`): Semgrep per enabled language and a Trivy secret scan, each with its own SARIF category. | Copy of `templates/workflows/code-security-scan.yml` at that release, with a header comment on pinning the SHA. |
| `.gitignore` | Keeps run-time reports out of Git while keeping the scanner policy under `.scanning/configs/`. | The lines [Getting started step 5](../../docs/SETUP-GUIDE.md#5-install-local-hooks) asks you to merge in. Setup does not edit `.gitignore` itself. |
| `.gitattributes` | Keeps the vendored shell, Python, JSON and YAML files at LF line endings, which the hooks need on Windows. | Same as above. |

Setup also writes files that are not copied here, because they are large and must
match the release byte for byte: `lefthook.yml`, `hooks/`, `schemas/`, the shared
scripts under `scripts/`, the default (AWS) policy under `.scanning/configs/`, and the
editor bundle under `.claude/`. Commit them too.

Locally, Lefthook runs Semgrep, `dotnet format`, ESLint and Prettier on matching
staged files, so install those tools outside the repository and set
`SCAN_ESLINT_BIN`, `SCAN_ESLINT_CONFIG`, `SCAN_PRETTIER_BIN` and
`SCAN_PRETTIER_CONFIG`. The setup verifier skips the Terraform tools for this repository
while it has no Terraform files; see [Prerequisites](../../docs/PREREQUISITES.md).

Before you commit the caller:

- Replace the release tag on the `uses:` line with the full commit SHA it points to,
  keeping the tag as a comment. Resolve the SHA as in [version pinning](../../docs/VERSION-PINNING.md#pin-the-commit-a-release-tag-points-to).
- Adapt the branch names in the `on:` triggers.
- For a private repository without code scanning, add `upload-sarif: false` under
  `with:`.

## Two pull requests: config first, callers second

The app-code scan decides which languages to scan by reading `scan-config.yaml` from
the pull request's **base** commit, not from the pull request itself. On the first
adoption pull request the base has no config, so language detection fails and the
secret scan, which depends on it, cannot run. So adopt in two steps:

1. **Policy pull request.** Add `scan-config.yaml`, `.scanning/configs/`, the runner
   file, `hooks/`, `schemas/`, `scripts/`, `.gitignore` and `.gitattributes`, **without**
   the files under `.github/workflows/`. Validate and scan it locally (a commit through
   the hooks is enough), get it reviewed, and merge it.
2. **Caller pull request.** Rebase on the merged base and add the caller workflow. Its
   checks are your first CI scan: `code-scan / Detect languages`,
   `code-scan / Semgrep (csharp)`, `code-scan / Semgrep (typescript)` and
   `code-scan / Secret scan`. After they pass once, require all of them in branch
   protection: see [consumer operations](../../docs/consumer-repo-setup-guide.md#branch-protection).

A language enabled in the same pull request that adds its code is not scanned until
the config change reaches the base.
