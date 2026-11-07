# Runbook: Adopt the Scan in a Terraform Module Repository

For installation, follow [Getting started](SETUP-GUIDE.md). This reference covers
hosted acceptance for a repository that publishes a Terraform module. Its source
line references describe the historical revision named below; current configuration
sources and security contracts are in [the workflow reference](REUSABLE-WORKFLOWS.md).

The current release is `v3.0.6`. <!-- x-release-please-version -->

Every `file:line` reference on this page, such as `reusable-scan.yml:126`, means that line
at commit
[`7cd34a5`](https://github.com/agenticcodingops/auto-code-scanning/tree/7cd34a52c823a725575ef3b59ab34e062d1d83dd)
on `main`. Workflow file names such as `reusable-scan.yml` are under `.github/workflows/`;
other paths are relative to the repository root.

## Purpose

Scan every pull request and every push to the default branch of a Terraform module
repository with Trivy, Checkov and TFLint. Block merges that add a CRITICAL or HIGH
finding.

## When to use

- The repository holds a Terraform module: a root module, and optionally `modules/` and
  `examples/` directories.
- It has no scan yet. To replace an existing inline scan, use
  [CONSUMER-MIGRATION.md](CONSUMER-MIGRATION.md) instead.
- For application code in the same repository, add `code-security-scan.yml` as well; see
  [APP-CODE-SCANNING.md](APP-CODE-SCANNING.md).

## Prerequisites

- Admin access to the module repository, to set branch protection.
- Access to the reviewed platform revision used by the caller and its
  `scanning-repo-ref`; the default is the published platform, not a same-owner copy.
- Code scanning available on the module repository, if you want the SARIF results there.
  Upload failures fail the separate Upload SARIF job by default. Require that
  check when enabled and leave `allow-sarif-upload-errors: false` if delivery must
  block merging; the five scan checks alone
  do not guarantee delivery. Even a successful upload check can skip missing SARIF
  files; inspect every expected category and artifact. If private code scanning is unavailable, set
  `upload-sarif: false`; scanning and finding gates still run. By default three uploads run: the Snyk upload is
  skipped unless the Snyk job, which needs `enable-snyk: true`, wrote a SARIF file
  (`reusable-scan.yml:70-74`, `904`).

This example uses the layout below. `OWNER` means the reviewed platform owner,
`agenticcodingops` by default, rather than the consumer owner.

```text
.
├── main.tf
├── variables.tf
├── outputs.tf
├── versions.tf
├── modules/
│   └── network/
│       └── main.tf
└── examples/
    └── basic/
        └── main.tf
```

With `terraform-directory: "."`, Trivy scans the whole tree. Checkov scans it too, except
any path that contains `examples` or `tests`: the platform's `configs/<cloud>/.checkov.yaml`
lists both under `skip-path`, and Checkov reads each entry as a regular expression
(`configs/azure/.checkov.yaml:52-58`). So `examples/basic` gets Trivy and TFLint but no
Checkov. TFLint runs once in each of `.`, `modules/network` and `examples/basic`
(`reusable-scan.yml:180`, `274-275`, `397-403`). Trivy skips `.terraform`, `node_modules` and
`.git` (`reusable-scan.yml:186`). Checkov does not download external modules
(`reusable-scan.yml:280`).

## Steps

### 1. Choose the cloud provider

- **Who:** Operator
- **Operator STOP:** no

Set `cloud-provider` to the provider the module targets: `aws`, `azure` or `gcp`. It picks
the Checkov and TFLint configs (`reusable-scan.yml:31-34`, `130`, `141-143`). For a module
that targets more than one provider, add one caller workflow file per provider. Two calls
from one caller workflow share a concurrency group and can cancel each other (see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#concurrency)). Only one of those calls
should upload SARIF; see [MULTI-CLOUD.md](MULTI-CLOUD.md#step-4-cicd-for-multi-cloud).

### 2. Create your owner's copy of the platform

This historical step is no longer required. Use the full platform commit SHA
selected in Getting started for the local installation, workflow and helper pins,
including its explicit Windows setup-fix exception when applicable.
If your organization requires a reviewed mirror, set `scanning-repository` to it
explicitly and ensure it contains that same commit. `OWNER` in the retained
release-tagged example below means the platform owner, `agenticcodingops`, unless
you have deliberately chosen a mirror. Replace the example tags with the full SHA.

### 3. Add the caller workflow

- **Who:** Operator
- **Operator STOP:** no

On a new branch, add `.github/workflows/terraform-scan.yml`:

```yaml
name: Terraform Security Scan

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  terraform-scan:
    # The called workflow cannot raise these; it needs all three.
    permissions:
      contents: read
      actions: read
      security-events: write
      pull-requests: write
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v3.0.6 # x-release-please-version
    with:
      terraform-directory: "."
      cloud-provider: "azure"
      scanning-repo-ref: "v3.0.6" # x-release-please-version
```

- Set `OWNER` to the reviewed platform owner (`agenticcodingops` by default), and
  choose your own branch name and `cloud-provider`.
- Keep `uses:` and `scanning-repo-ref` on the same release. The default lives inside the
  workflow revision that `uses:` pins (`reusable-scan.yml:40-44`): from the release that
  carries this change on, release-please sets it to that release's tag, so an unset input
  reads the same release's configs. Earlier releases default to `v1.0.0`, which is not a tag,
  so a caller pinned to one of them must set it. To pin a commit instead of a tag, see
  [VERSION-PINNING.md](VERSION-PINNING.md#pin-the-commit-a-release-tag-points-to).
- The permissions follow [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#permissions-to-grant-on-the-calling-job).
- Do not add a workflow-level `concurrency` group of `${{ github.workflow }}-${{ github.ref }}`.
  It equals the called workflow's group (`reusable-scan.yml:104-106`).
- The release-please marker comments keep this page current. You can drop them in
  your copy.
- For Snyk IaC, add `enable-snyk: true` under `with:`, and pass `SNYK_TOKEN` under a
  `secrets:` key on the same job (`reusable-scan.yml:70-74`, `96-99`).

### 4. Open a pull request and read the first results

- **Who:** Operator, then CI
- **Operator STOP:** no

Push the branch and open a pull request. CI runs the scan. Save the findings with the
commands in
[BUMP-THE-SCAN.md step 6](BUMP-THE-SCAN.md#6-record-the-failed-checks-after-the-bump):
`gh run list --event pull_request ...` for this pull request's run, then `gh run download`
and `jq`. Write to `first/` and `first.tsv` instead of `after/` and `after.tsv`, and skip
the two `comm` lines, since there is no earlier run to compare. The `aggregated-results`
artifact is kept for one day (`reusable-scan.yml:795`).

### 5. Decide how each finding is handled

- **Who:** Operator and Reviewer
- **Operator STOP:** yes. Do not merge until every CRITICAL and HIGH finding has a
  decision.

With `fail-on-findings` left at its default, `true`, the Aggregate Results job fails
while a CRITICAL or HIGH finding remains (`reusable-scan.yml:45-49`, `752-756`,
`785-786`). Fix, baseline or suppress each one, as in
[BUMP-THE-SCAN.md](BUMP-THE-SCAN.md#7-decide-how-each-newly-failing-check-is-handled).
Record the decisions in the pull request.

### 6. Merge

- **Who:** Reviewer, then Operator
- **Operator STOP:** no

The Reviewer approves; the Operator merges. CI runs the scan on the default branch.

### 7. Require the scan before merging

- **Who:** Operator (repository admin)
- **Operator STOP:** no

In the branch protection rule or ruleset for the default branch, add these jobs as
required status checks: Setup Scanning Tools, Trivy IaC Scan, Checkov Policy Scan, TFLint
Scan and Aggregate Results (`reusable-scan.yml:114`, `161`, `257`, `328`, `510`). Use the
names shown on the pull request's Checks tab. Require all five, because Aggregate Results
runs even when a scan job fails. The current aggregate rejects missing or malformed
required reports; report-only mode still enforces scan completion. See
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#scanner-health-and-secret-findings).

## Verify

- The pull request has a "Security Scan Results" comment (`reusable-scan.yml:987`).
- If SARIF uploads are enabled, the repository's code scanning page lists the `trivy-iac`, `trivy-secrets` and
  `checkov` categories (`reusable-scan.yml:881`, `890`, `899`).
- The run's `checkov-results` artifact contains `checkov-results.json`, and the TFLint Scan
  job summary lists each ruleset (`reusable-scan.yml:314-322`, `371-383`).
- A pull request that fails one of the five required jobs cannot merge.

## Rollback

- **Who:** Operator (repository admin)

1. Remove the five jobs from the required status checks first. Otherwise open pull
   requests wait for checks that will never run.
2. Delete `.github/workflows/terraform-scan.yml` in a pull request and merge it.
3. Optionally dismiss or delete the scan's code scanning alerts.

## References

- [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md): every input and output of
  `reusable-scan.yml`.
- [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md): move to a newer release later.
- [VERSION-PINNING.md](VERSION-PINNING.md): tags, commits and scanner versions.
- [SUPPRESSION-GOVERNANCE.md](SUPPRESSION-GOVERNANCE.md): approval rules for
  suppressions.
- `templates/workflows/terraform-scan.yml`: the shipped caller template.
