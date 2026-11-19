# Example: Terraform repository

The files in this folder show what a Terraform repository adds to adopt
the auto-code-scanning release named on the callers' `uses:` lines, with the **starter** tier and the **Lefthook**
runner. They are reference copies to compare against, not a project to run. Follow
the [Quickstart](../../docs/QUICK-START-5MIN.md) or [Getting started](../../docs/SETUP-GUIDE.md)
to install; setup writes these files for you.

## Files

| File | What it is | Where it comes from |
|---|---|---|
| `scan-config.yaml` | Project settings: which languages CI scans, the suppression registry path, the optional fix loop. Here only `languages.terraform` is enabled. | Written by `scripts/render-scan-config.py --tier starter --languages terraform`, which setup runs. Generated with this repository's renderer, not edited by hand. |
| `.github/workflows/terraform-scan.yml` | Caller of the Terraform scan (`reusable-scan.yml`): Trivy, Checkov and TFLint, gate on CRITICAL and HIGH, SARIF upload, pull request comment. | Copy of `templates/workflows/terraform-scan.yml` at that release, with a header comment on pinning the SHA. |
| `.github/workflows/code-security-scan.yml` | Caller of the app-code scan. In a Terraform-only repository it still runs its independent **secret scan** over the whole checkout; no language is enabled, so the Semgrep jobs are skipped. | Copy of `templates/workflows/code-security-scan.yml` at that release. |
| `.gitignore` | Keeps run-time reports out of Git while keeping the scanner policy under `.scanning/configs/`. | The lines [Getting started step 5](../../docs/SETUP-GUIDE.md#5-install-local-hooks) asks you to merge in. Setup does not edit `.gitignore` itself. |
| `.gitattributes` | Keeps the vendored shell, Python, JSON and YAML files at LF line endings, which the hooks need on Windows. | Same as above. |

Setup also writes files that are not copied here, because they are large and must
match the release byte for byte: `lefthook.yml`, `hooks/`, `schemas/`, the shared
scripts under `scripts/`, the provider policy under `.scanning/configs/`, and the
editor bundle under `.claude/`. Commit them too.

Before you commit the callers:

- Replace the release tag on each `uses:` line and in `scanning-repo-ref` with the full
  commit SHA it points to, keeping the tag as a comment. Resolve the SHA as in
  [version pinning](../../docs/VERSION-PINNING.md#pin-the-commit-a-release-tag-points-to).
- Set `cloud-provider` to `aws`, `azure` or `gcp`, and `terraform-directory` if your
  Terraform is not at the root.
- Adapt the branch names in the `on:` triggers.
- For a private repository without code scanning, add `upload-sarif: false` under
  `with:` in both callers.

## Two pull requests: config first, callers second

The CI scans read policy from the pull request's **base** commit, not from the pull
request itself. On the first adoption pull request the base has no
`scan-config.yaml`, so the app-code language detection fails and its secret scan
cannot run. So adopt in two steps:

1. **Policy pull request.** Add `scan-config.yaml`, `.scanning/configs/`, the runner
   file, `hooks/`, `schemas/`, `scripts/`, `.gitignore` and `.gitattributes`, **without**
   the files under `.github/workflows/`. Validate and scan it locally (a commit through
   the hooks is enough), get it reviewed, and merge it.
2. **Caller pull request.** Rebase on the merged base and add the two caller workflows.
   Its checks are your first CI scan. After they pass once, require them in branch
   protection: see [consumer operations](../../docs/consumer-repo-setup-guide.md#branch-protection).

This keeps approving the policy separate from the changes it authorises.
