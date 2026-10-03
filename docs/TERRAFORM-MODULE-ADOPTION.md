# Runbook: Adopt the Scan in a Terraform Module Repository

A worked example: add the Terraform scan to a repository that publishes a Terraform
module.

The current release is `v2.2.0`. <!-- x-release-please-version -->

Line references such as `reusable-scan.yml:126` mean that line of
`.github/workflows/reusable-scan.yml` at commit
[`7cd34a5`](https://github.com/agenticcodingops/auto-code-scanning/tree/7cd34a52c823a725575ef3b59ab34e062d1d83dd)
on `main`.

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
- A public repository named `auto-code-scanning` under the module repository's owner,
  holding the release you will pin. The scan reads its configs from
  `<owner of the calling repository>/auto-code-scanning` (`reusable-scan.yml:126`), and
  cannot read a private copy (see
  [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#configs-come-from-your-owners-copy)).
  Step 2 creates it.
- Code scanning available on the module repository, if you want the SARIF results there.
  A failed upload does not fail the job; `sarif-uploaded` is `false` only when all four
  uploads fail (`reusable-scan.yml:875-922`).

This example uses the layout below. `OWNER` stands for your user or organisation.

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

With `terraform-directory: "."`, Trivy and Checkov scan the whole tree, and TFLint runs
once in each of `.`, `modules/network` and `examples/basic`
(`reusable-scan.yml:180`, `274`, `397-403`). Trivy skips `.terraform`, `node_modules` and
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

- **Who:** Operator (needs permission to create repositories under `OWNER`)
- **Operator STOP:** no

Skip this step if `OWNER/auto-code-scanning` already exists and holds the release you will
pin. Otherwise create an empty **public** repository `OWNER/auto-code-scanning`, then copy
every branch and tag into it:

```bash
git clone --mirror https://github.com/agenticcodingops/auto-code-scanning.git
cd auto-code-scanning.git
git push https://github.com/OWNER/auto-code-scanning.git --all
git push https://github.com/OWNER/auto-code-scanning.git --tags
```

Push `--all` and `--tags`, not `--mirror`: a mirror clone also holds the source's pull
request refs. To take a newer release later, run `git fetch --prune origin` in the same
directory, then the two `git push` commands again.

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
      security-events: write
      pull-requests: write
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v2.2.0 # x-release-please-version
    with:
      terraform-directory: "."
      cloud-provider: "azure"
      scanning-repo-ref: "v2.2.0" # x-release-please-version
```

- Replace `OWNER`, the branch name and `cloud-provider` with yours.
- Keep `uses:` and `scanning-repo-ref` on the same release. Never leave
  `scanning-repo-ref` unset; its default is `v1.0.0`, which is not a tag in this repository
  (`reusable-scan.yml:40-44`). To pin a commit instead of a tag, see
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
commands in [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md#3-record-the-failed-checks-before-the-bump),
using this pull request's run. The `aggregated-results` artifact is kept for one day
(`reusable-scan.yml:795`).

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
runs even when a scan job fails (`reusable-scan.yml:514`).

## Verify

- The pull request has a "Security Scan Results" comment (`reusable-scan.yml:987`).
- The repository's code scanning page lists the `trivy-iac`, `trivy-secrets` and
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
