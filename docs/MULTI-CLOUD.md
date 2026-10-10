# Multi-Cloud Configuration

This solution supports AWS, Azure, and GCP via cloud-specific configuration directories.

## Cloud-Specific Configs

Each cloud provider has its own configuration directory with tool-specific files:

| File | AWS | Azure | GCP |
|------|-----|-------|-----|
| `.checkov.yaml` | `configs/aws/.checkov.yaml` | `configs/azure/.checkov.yaml` | `configs/gcp/.checkov.yaml` |
| `.tflint.hcl` | `configs/aws/.tflint.hcl` | `configs/azure/.tflint.hcl` | `configs/gcp/.tflint.hcl` |
| `policy-overlay.yaml` | `configs/aws/policy-overlay.yaml` | `configs/azure/policy-overlay.yaml` | `configs/gcp/policy-overlay.yaml` |
| `noisy-checks-{cloud}.yaml` | `configs/common/noisy-checks-aws.yaml` | `configs/common/noisy-checks-azure.yaml` | `configs/common/noisy-checks-gcp.yaml` |
| tflint Ruleset | `tflint-ruleset-aws` | `tflint-ruleset-azurerm` | `tflint-ruleset-google` |

### What Each Config Controls

- **`.checkov.yaml`**: Blocklist of Checkov checks to skip for this cloud provider. All checks run by default; this file lists exclusions only.
- **`.tflint.hcl`**: Cloud-specific tflint ruleset plugin and rule configurations.
- **`policy-overlay.yaml`**: Organization-specific policy rules layered on top of universal security checks.
- **`noisy-checks.yaml`**: Known false-positive-prone checks that can be disabled during onboarding.

## Cloud-Agnostic Tools

These tools work across all clouds without provider-specific configuration:

- **Trivy IaC scanning** -- Automatically detects AWS, Azure, GCP resources
- **Trivy secret detection** -- Language and cloud agnostic
- **Gitleaks** -- Pattern-based secret detection, cloud agnostic
- **validate-suppressions** -- Validates `.scan-suppressions.yaml` regardless of cloud

## Single-Cloud Setup

For repositories targeting a single cloud provider:

```bash
# AWS
python scripts/setup-scanning.py --cloud-provider aws --tier standard

# Azure
python scripts/setup-scanning.py --cloud-provider azure --tier standard

# GCP
python scripts/setup-scanning.py --cloud-provider gcp --tier standard
```

This copies the provider-specific configs to `.scanning/configs/` in the consuming repository.

## Multi-Cloud Repositories

For repositories containing Terraform for multiple cloud providers (e.g., AWS + Azure), you need to configure per-directory scanning.

### Example: AWS + Azure Repository

Repository structure:
```
my-infra-repo/
  aws/
    main.tf          # AWS resources
    variables.tf
  azure/
    main.tf          # Azure resources
    variables.tf
  shared/
    modules/         # Cloud-agnostic modules
```

### Step 1: Set Up Primary Provider

Run setup for your primary cloud:
```bash
python scripts/setup-scanning.py --cloud-provider aws --tier standard
```

### Step 2: Add Secondary Provider Configs

Manually copy additional provider configs:
```bash
# Copy Azure configs alongside AWS configs
mkdir -p .scanning/configs/azure
cp configs/azure/.checkov.yaml .scanning/configs/azure/
cp configs/azure/.tflint.hcl .scanning/configs/azure/
cp configs/azure/policy-overlay.yaml .scanning/configs/azure/
```

### Step 3: Configure Per-Directory Scanning

Override hook file patterns in your `.pre-commit-config.yaml` to scope tools per directory:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v2.3.3  # x-release-please-version
    hooks:
      # AWS-scoped hooks
      - id: trivy-iac-critical
        name: "Trivy IaC CRITICAL (AWS)"
        files: '^aws/.*\.tf$'
      - id: checkov
        name: "Checkov (AWS)"
        files: '^aws/.*\.tf$'
        args: ["--config-file", ".scanning/configs/.checkov.yaml"]
      - id: tflint
        name: "tflint (AWS)"
        files: '^aws/.*\.tf$'
        args: ["--config-file", ".scanning/configs/.tflint.hcl"]

      # Azure-scoped hooks
      - id: trivy-iac-critical
        alias: trivy-iac-critical-azure
        name: "Trivy IaC CRITICAL (Azure)"
        files: '^azure/.*\.tf$'
      - id: checkov
        alias: checkov-azure
        name: "Checkov (Azure)"
        files: '^azure/.*\.tf$'
        args: ["--config-file", ".scanning/configs/azure/.checkov.yaml"]
      - id: tflint
        alias: tflint-azure
        name: "tflint (Azure)"
        files: '^azure/.*\.tf$'
        args: ["--config-file", ".scanning/configs/azure/.tflint.hcl"]

      # Cloud-agnostic hooks (run on all directories)
      - id: trivy-secrets
      - id: gitleaks
      - id: validate-suppressions
```

### Step 4: CI/CD for Multi-Cloud

Add one caller workflow file per cloud. Do not use a `strategy.matrix` over one call:
every call from the same caller workflow on the same ref computes the same concurrency
group, so one matrix leg can cancel the other (see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#concurrency)). Two SARIF uploads with the
same tool and category in one workflow run also fail that run
([GitHub Docs: Uploading a SARIF file to GitHub](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github)).

```yaml
# .github/workflows/terraform-scan-aws.yml
name: Terraform Security Scan (AWS)
on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  scan:
    permissions:
      contents: read
      security-events: write
      pull-requests: write
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v2.3.3 # x-release-please-version
    with:
      terraform-directory: aws
      cloud-provider: aws
      scanning-repo-ref: v2.3.3 # x-release-please-version
```

`OWNER` is the owner of your repository. `reusable-scan.yml` reads its configs from a
repository named `auto-code-scanning` under the owner of the calling repository, whatever
`uses:` names (`reusable-scan.yml:123-131`). That copy must be public (a private copy
cannot be read) and must hold the ref you pass as `scanning-repo-ref`. Without it, Setup
Scanning Tools fails, the scan jobs are skipped, Aggregate Results still passes, and the
pull request comment says "All security checks passed!". Create the copy as in
[step 2 of TERRAFORM-MODULE-ADOPTION.md](TERRAFORM-MODULE-ADOPTION.md#2-create-your-owners-copy-of-the-platform).
Require Setup Scanning Tools as well as Aggregate Results
([step 7](TERRAFORM-MODULE-ADOPTION.md#7-require-the-scan-before-merging)). See
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#configs-come-from-your-owners-copy).

Copy it to `.github/workflows/terraform-scan-azure.yml` with
`name: Terraform Security Scan (Azure)`, `terraform-directory: azure` and
`cloud-provider: azure`. Each file needs its own `name:`.

To bump these callers, follow [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md) with each file name in
place of `terraform-scan.yml`. Run steps 3 and 6 once per file, keeping separate before
and after files for each cloud, and move the pins in every file in the one pull request
of step 4.

Both calls upload SARIF to the same fixed categories: `trivy-iac`, `trivy-secrets`,
`checkov` and `snyk-iac` (`.github/workflows/reusable-scan.yml:881-908` at commit
`7cd34a5`). For one commit, a later upload with the same tool and category overwrites the
earlier results ([GitHub Docs: Uploading a SARIF file to GitHub](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github)), so
code scanning keeps only one cloud's results. Each call's gate and pull request comment
are not affected. Keep `upload-sarif: true` on the cloud whose alerts you want in code
scanning, and set `upload-sarif: false` on the others.

## Monorepo Support

For monorepos with Terraform in multiple subdirectories, hooks automatically detect changed directories using `detect_changed_dirs()`. Only directories with modified `.tf` files are scanned, improving performance.

This works automatically -- no additional configuration needed.

## Config Layering

Scanning configurations follow a two-layer model:

1. **Universal security checks**: Core checks that apply regardless of cloud (e.g., encryption required, no hardcoded secrets)
2. **Policy overlay**: Organization-specific rules per cloud provider (e.g., approved regions, naming conventions)

The `policy-overlay.yaml` file in each provider's config directory defines the org-specific rules.
