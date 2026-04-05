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
    rev: v1.0.0
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

Use a matrix strategy in your GitHub Actions workflow:

```yaml
jobs:
  security:
    strategy:
      matrix:
        include:
          - directory: aws
            provider: aws
          - directory: azure
            provider: azure
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
    with:
      terraform-directory: ${{ matrix.directory }}
      cloud-provider: ${{ matrix.provider }}
    secrets: inherit
```

## Monorepo Support

For monorepos with Terraform in multiple subdirectories, hooks automatically detect changed directories using `detect_changed_dirs()`. Only directories with modified `.tf` files are scanned, improving performance.

This works automatically -- no additional configuration needed.

## Config Layering

Scanning configurations follow a two-layer model:

1. **Universal security checks**: Core checks that apply regardless of cloud (e.g., encryption required, no hardcoded secrets)
2. **Policy overlay**: Organization-specific rules per cloud provider (e.g., approved regions, naming conventions)

The `policy-overlay.yaml` file in each provider's config directory defines the org-specific rules.
