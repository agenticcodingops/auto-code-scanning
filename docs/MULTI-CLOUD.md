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

Use [Getting started](SETUP-GUIDE.md), selecting `aws`, `azure` or `gcp` consistently
for provider policy and external TFLint configuration. Keep scanner installations
and plugin caches outside the consumer.

## Multi-Cloud Repositories

Separate cloud roots, for example `aws/` and `azure/`, so each hosted caller can
select its own directory and reviewed provider policy.

### Step 1: Set Up Primary Provider

Install through Getting started with the primary provider. Its setup selects one
provider policy; it does not automatically choose policy per changed directory.

### Step 2: Add Secondary Provider Configs

Provision a separate reviewed external TFLint config and plugin cache for each
provider. Keep the pushed Checkov policy tracked. Copying extra configuration
files into the consumer alone does not change the policy selected by local hooks.

### Step 3: Configure Per-Directory Scanning

The current shared hooks select their own index or push-object inputs. A runner's
`files:` expression controls whether it starts a hook; it does not redefine that
hook's scan selection or trusted policy. Do not pass in-repository executable
TFLint config or arbitrary Checkov arguments to create separate provider profiles.
Use the separate hosted callers below for per-directory provider policy. Any
custom local multi-cloud runner needs independent transaction and policy tests;
the shipped setup verifier validates the exact single-provider runner template.

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
      actions: read
      security-events: write
      pull-requests: write
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v3.0.8 # x-release-please-version
    with:
      terraform-directory: aws
      cloud-provider: aws
      scanning-repo-ref: v3.0.8 # x-release-please-version
```

In the retained release-managed caller example, set `OWNER` to `agenticcodingops`
for the published platform. For a reviewed mirror, use its owner and set
`scanning-repository` explicitly. Do not substitute the consumer owner unless
that reviewed platform copy exists there.

`reusable-scan.yml` reads configuration from the reviewed platform repository,
`agenticcodingops/auto-code-scanning`, by default. No same-owner copy is required.
Set `scanning-repo-ref` to the same full commit SHA as the workflow pin. A reviewed
mirror needs an explicit `scanning-repository` input and must contain that commit.
Require setup and scanner jobs as well as aggregation; incomplete scans block.
See [workflow configuration sources](REUSABLE-WORKFLOWS.md#configs-come-from-the-reviewed-platform-revision).

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
