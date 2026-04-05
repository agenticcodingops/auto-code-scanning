# auto-code-scanning

Reusable security scanning infrastructure for Terraform repositories. Supports AWS, Azure, and GCP.
## Overview

This repository provides two layers of security scanning:

1. **Shared pre-commit hooks** - Local developer experience via `.pre-commit-hooks.yaml`
2. **Reusable GitHub Actions workflows** - CI/CD enforcement via `workflow_call`

## Quick Start (5 minutes)

### Option A: Setup Script (Recommended)

```powershell
# Download and run the setup script
Invoke-WebRequest -Uri "https://github.com/agenticcodingops/auto-code-scanning/main/scripts/setup-scanning.ps1" -OutFile "setup-scanning.ps1"
.\setup-scanning.ps1 -CloudProvider aws
```

### Option B: Manual Setup

```powershell
# 1. Copy starter config for your cloud provider
Invoke-WebRequest -Uri "https://github.com/agenticcodingops/auto-code-scanning/main/templates/aws/pre-commit-config.yaml" -OutFile ".pre-commit-config.yaml"

# 2. Download cloud-specific configs
Invoke-WebRequest -Uri "https://github.com/agenticcodingops/auto-code-scanning/main/configs/aws/.tflint.hcl" -OutFile ".tflint.hcl"
Invoke-WebRequest -Uri "https://github.com/agenticcodingops/auto-code-scanning/main/configs/aws/.checkov.yaml" -OutFile ".checkov.yaml"
Invoke-WebRequest -Uri "https://github.com/agenticcodingops/auto-code-scanning/main/configs/common/.trivyignore" -OutFile ".trivyignore"

# 3. Install pre-commit hooks
pre-commit install
pre-commit install --hook-type pre-push
```

### Option C: CI/CD Only

Add to your `.github/workflows/security.yml`:

```yaml
name: Security Scan
on:
  pull_request:
    paths: ["**/*.tf"]
  push:
    branches: [main]

jobs:
  security:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/terraform-security-scan.yml@v1.0.0
    with:
      terraform-directory: "."
      cloud-provider: "aws"
    secrets: inherit
```

## Available Hooks

| Hook ID | Description | Default Stage |
|---------|-------------|---------------|
| `trivy-iac-critical` | Scan for CRITICAL misconfigurations | pre-commit |
| `trivy-iac-full` | Full scan (CRITICAL, HIGH, MEDIUM) | pre-push |
| `trivy-secrets` | Detect hardcoded secrets and API keys | pre-commit |
| `checkov-terraform` | CIS Benchmark policy validation | pre-push |
| `checkov-terraform-strict` | Strict mode - all checks | pre-push |
| `validate-suppressions` | Validate suppression file | pre-commit |

## Supported Cloud Providers

| Provider | tflint Config | Checkov Config | Template |
|----------|--------------|----------------|----------|
| AWS | `configs/aws/.tflint.hcl` | `configs/aws/.checkov.yaml` | `templates/aws/` |
| Azure | `configs/azure/.tflint.hcl` | `configs/azure/.checkov.yaml` | `templates/azure/` |
| GCP | `configs/gcp/.tflint.hcl` | `configs/gcp/.checkov.yaml` | `templates/gcp/` |

## Adoption Tiers

| Tier | Phase | Hooks | Time |
|------|-------|-------|------|
| **Starter** | Days 1-30 | Secrets + formatting | <5s |
| **Standard** | Days 31-60 | + linting + critical security | <10s |
| **Strict** | Days 61-90 | Full enforcement | <10s + pre-push |

See `templates/starter/`, `templates/standard/`, `templates/strict/` for pre-built configs.

## Updating

```bash
# Update to latest version
pre-commit autoupdate

# Or pin to specific version in .pre-commit-config.yaml:
#   rev: v1.2.0
```

## Documentation

- [Quick Start (5 min)](docs/QUICK-START-5MIN.md)
- [Setup Guide](docs/SETUP-GUIDE.md)
- [Hook Reference](docs/HOOK-REFERENCE.md)
- [Multi-Cloud Configuration](docs/MULTI-CLOUD.md)
- [Adoption Playbook](docs/ADOPTION-PLAYBOOK.md)
- [Metrics Dashboard](docs/METRICS-DASHBOARD.md)
- [Suppression Governance](docs/SUPPRESSION-GOVERNANCE.md)
- [Performance Optimization](docs/PERFORMANCE-OPTIMIZATION.md)

## Repository Structure

```
auto-code-scanning/
├── .pre-commit-hooks.yaml          # Hook manifest (consumed by other repos)
├── configs/                        # Cloud-specific tool configurations
│   ├── aws/                        # AWS CIS Benchmark configs
│   ├── azure/                      # Azure CIS Benchmark configs
│   ├── gcp/                        # GCP CIS Benchmark configs
│   └── common/                     # Cloud-agnostic configs
├── templates/                      # Pre-commit config templates
│   ├── starter/                    # Minimal (Phase 1)
│   ├── standard/                   # Recommended (Phase 2)
│   ├── strict/                     # Full enforcement (Phase 3)
│   ├── aws/                        # AWS-specific full config
│   ├── azure/                      # Azure-specific full config
│   └── gcp/                        # GCP-specific full config
├── scripts/                        # PowerShell setup & utility scripts
├── .github/workflows/              # Reusable CI/CD workflows
├── tests/                          # Test fixtures and integration tests
├── schemas/                        # JSON schemas for result formats
└── docs/                           # Documentation
```
