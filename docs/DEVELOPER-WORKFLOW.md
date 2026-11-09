# Developer Workflow Guide

Day-to-day guide for working with security scanning hooks in your Terraform repository.

## What Happens When You Commit

Install through [Getting started](SETUP-GUIDE.md). The runner manifest chooses
which hooks run. Security hooks read captured staged bytes; Terraform siblings
provide context, but findings are selected for changed files. Formatters and
SQLFluff read the working tree. Common security hooks include:

| Hook | What it checks | Blocks on |
| ---- | -------------- | --------- |
| **trivy-iac-critical** | Terraform misconfigurations | CRITICAL severity |
| **trivy-secrets** | Hardcoded secrets, API keys | Any secret found |
| **gitleaks** | Leaked credentials (patterns) | Any match found |

If all hooks pass, your commit goes through. If a finding is detected, the commit is blocked and you'll see details like:

```
[trivy-iac-critical] Scanning... (9 files in 1 directories)
[trivy-iac-critical]
[trivy-iac-critical]   CRITICAL  aws-vpc-no-public-egress-sgr  main.tf:68-68
[trivy-iac-critical]     A security group rule should not allow unrestricted egress to any IP address.
[trivy-iac-critical]     Resource: aws_security_group.example
[trivy-iac-critical]     Fix: Set a more restrictive cidr range
[trivy-iac-critical]
[trivy-iac-critical] FAIL: 1 findings (1 critical, 0 high, 0 medium, 0 low)
```

## What Happens When You Push (Standard/Strict tiers)

Pre-push hooks consume Git's complete ref transaction and read the exact pushed
objects, independently of the index and worktree. New branch selection is scoped
to the destination remote. Lefthook uses Checkov, TFLint and .NET build; the
standard/strict pre-commit manifests differ. These available hooks are not all
installed by every tier:

| Hook | What it checks | Blocks on |
| ---- | -------------- | --------- |
| **trivy-iac-full** | All misconfiguration severities (hardcoded, not config-driven) | CRITICAL, HIGH, MEDIUM, LOW |
| **checkov** | Policy-as-code checks | Per config |
| **checkov-strict** | Hard-fail CRITICAL+HIGH | CRITICAL, HIGH |
| **tflint** | Terraform linting rules | Errors |
| **validate-suppressions** | Suppression file format | Invalid entries |

## Reading the Output

Every finding shows:

```
[hook-name]   SEVERITY  RULE_ID  file.tf:start-end
[hook-name]     Description of the issue
[hook-name]     Resource: the_terraform_resource
[hook-name]     Fix: How to resolve it
```

- **SEVERITY**: CRITICAL, HIGH, MEDIUM, or LOW
- **RULE_ID**: The scanner rule (e.g., `AVD-AWS-0057`, `CKV_AWS_18`)
- **file:line**: Exact location in your code
- **Fix**: Remediation guidance

## Option 1: Fix the Finding

This is the preferred approach. Use the output to fix the issue directly:

```hcl
# BEFORE (CRITICAL: unrestricted egress)
resource "aws_security_group_rule" "egress" {
  type        = "egress"
  cidr_blocks = ["0.0.0.0/0"]    # <-- flagged
}

# AFTER (restricted to VPC CIDR)
resource "aws_security_group_rule" "egress" {
  type        = "egress"
  cidr_blocks = [var.vpc_cidr]    # <-- fixed
}
```

Then re-stage and commit:

```bash
git add main.tf
git commit -m "fix: restrict security group egress to VPC CIDR"
```

## Option 2: Suppress the Finding

First check `suppressions.file` in `scan-config.yaml`. The examples below use its
default, `.scan-suppressions.yaml`; if customized, create, validate and commit that
configured path instead. A registry at an unused default path has no scan effect.

For a reviewed false positive or accepted risk, create a schema-2.0 occurrence
entry in `.scan-suppressions.yaml`, using the fingerprint emitted by the current
scan. It binds the tool, rule, path, resource, lines and source-content hash.
Broad file globs do not approve new occurrences. HIGH/CRITICAL entries need
security approval, and expiry is capped at 180 days. Follow
[suppression governance](SUPPRESSION-GOVERNANCE.md) for the complete format.

Validate and commit the reviewed registry:

```bash
python scripts/validate-suppressions.py .scan-suppressions.yaml --ci
git add .scan-suppressions.yaml
git commit -m "chore: record reviewed occurrence exceptions"
```

## Option 3: Skip Specific Hooks (Temporary)

For the alternative pre-commit runner, `SKIP` bypasses named hooks for one command.
Use only under your team's reviewed exception process; CI still enforces scanning.
These commands use Bash syntax; Lefthook has separate runner settings.

```bash
# Skip one hook
SKIP=trivy-iac-critical git commit -m "wip: work in progress"

# Skip multiple hooks
SKIP=trivy-iac-critical,terraform_validate,terraform_tflint git commit -m "wip: terraform changes"

# Skip only our security hooks (keep formatting hooks)
SKIP=trivy-iac-critical,trivy-secrets,gitleaks git commit -m "wip: will fix findings later"
```

**Important:** `SKIP` only applies to the current command. The next commit will run all hooks normally.

## Option 4: Emergency Bypass (All Hooks)

For urgent production fixes, skip ALL hooks:

```bash
git commit --no-verify -m "hotfix: production issue BDCD-999"
```

**Use sparingly.** Bypasses are visible in CI and may be flagged by the bypass detection workflow.

## Handling Pre-Existing Findings

Terraform security scans include indexed sibling context and select changed files.
Hosted whole-tree scans can still reveal existing debt. Fix findings or record
reviewed exact occurrences in a schema-2.0 baseline; new or changed occurrences
remain visible. Pull-request policy comes from the exact base commit, so an
exception added in a pull request becomes effective after it merges into that base.
See [baselines](SETUP-GUIDE.md#9-suppressions-and-baselines).

## Quick Reference

| I want to... | Command |
| ------------ | ------- |
| See what hooks are installed | Inspect `lefthook.yml` or `.pre-commit-config.yaml` |
| Run hooks manually | `pre-commit run --all-files` |
| Run a specific hook | `pre-commit run trivy-iac-critical --all-files` |
| Run with verbose output | `SCAN_VERBOSE=1 pre-commit run --all-files` |
| Skip a specific hook | `SKIP=hook-id git commit -m "message"` |
| Skip all hooks | `git commit --no-verify -m "message"` |
| View last scan results | `cat .scanning/last-scan.json` |
| Validate suppressions | `python scripts/validate-suppressions.py .scan-suppressions.yaml --ci` |
| Clear pre-commit cache | `pre-commit clean` |
| Upgrade installed hooks | Follow [the coordinated upgrade](SETUP-GUIDE.md#10-upgrade-between-releases) |

## Common Hook IDs for SKIP

| Hook ID | Scanner | Stage |
| ------- | ------- | ----- |
| `trivy-iac-critical` | Trivy IaC (CRITICAL only) | pre-commit |
| `trivy-secrets` | Trivy secrets | pre-commit |
| `gitleaks` | Gitleaks secrets | pre-commit |
| `trivy-iac-full` | Trivy IaC (all severities) | pre-push |
| `checkov` | Checkov policies | pre-push |
| `checkov-strict` | Checkov CRITICAL+HIGH | pre-push |
| `tflint` | TFLint linting | pre-push |
| `snyk-iac` | Snyk IaC (optional) | pre-push |
| `validate-suppressions` | Suppression file | pre-commit |
| `trailing-whitespace` | Whitespace fixer | pre-commit |
| `terraform_fmt` | Terraform format | pre-commit |
| `terraform_validate` | Terraform validate | pre-commit |
| `terraform_tflint` | TFLint (pre-commit-terraform) | pre-commit |

## Understanding the Scan Scope

| File type staged | What gets scanned |
| ---------------- | ----------------- |
| Only non-Terraform files (.yaml, .md, etc.) | Secret hooks scan staged files only. IaC hooks skip entirely. |
| Terraform files (.tf) | IaC hooks include indexed module context and report selected changed files. Secret hooks scan staged files only. |
| Mix of both | Both IaC and secret hooks run on their respective scopes. |

**Why does trivy-iac scan the whole module directory?**

IaC security rules need full context. A `main.tf` resource might reference a variable in `variables.tf` or use a local from `locals.tf`. Scanning a single file in isolation would miss cross-file dependencies and produce false results.

## Enabling Snyk IaC (Optional)

Snyk IaC provides additional commercial security scanning on top of the open-source tools. Enable it only with a license and provisioned CLI. A selected missing CLI blocks by default; missing authentication warns and skips. CI enforces enabled scanner health independently.

### Prerequisites

1. A Snyk organisation licence and API token
2. Node.js/npm installed

### Setup

```bash
# Install the Snyk CLI
npm install -g snyk

# Authenticate (opens browser for login, or use SNYK_TOKEN)
snyk auth

# Verify it's working
snyk whoami
```

### Enable the hook

Edit `.pre-commit-config.yaml` and uncomment the `snyk-iac` block:

```yaml
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v3.0.9  # x-release-please-version
    hooks:
      # ... existing hooks ...
      # Uncomment below to enable Snyk IaC scanning
      - id: snyk-iac
        stages: [pre-push]
```

### How it works

| Behaviour | Detail |
| --------- | ------ |
| Stage | **pre-push** (runs on `git push`, not `git commit`) |
| Scope | Scans module directories containing staged `.tf` files |
| Auth check | If `SNYK_TOKEN` env var is not set, runs `snyk whoami` -- exits 0 if not authenticated |
| Policy file | Automatically uses `.snyk` in your repo root if present |
| Fail-open | Tool not installed or auth fails = allow push with a warning |

### Snyk-specific suppression

You can create a `.snyk` policy file in your repo root to ignore specific issues:

```yaml
# .snyk
version: v1.5.0
ignore:
  SNYK-CC-TF-63:
    - "*":
        reason: "Accepted risk: egress required for NAT gateway"
        expires: "2026-06-01T00:00:00.000Z"
```

### Enable Snyk in CI

Add `enable-snyk: true` to your workflow and ensure `SNYK_TOKEN` is in your repository secrets:

```yaml
jobs:
  security:
    permissions:
      contents: read
      actions: read
      security-events: write
      pull-requests: write
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v3.0.9 # x-release-please-version
    with:
      terraform-directory: "."
      cloud-provider: "aws"
      scanning-repo-ref: "v3.0.9" # x-release-please-version
      enable-snyk: true
    secrets:
      SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

In the release-managed caller example above, `OWNER` means the platform owner:
use `agenticcodingops` by default, or an explicitly reviewed mirror's owner with
`scanning-repository` set to that mirror. It does not mean the consumer owner.

`reusable-scan.yml` reads configuration from the reviewed platform repository,
`agenticcodingops/auto-code-scanning`, by default. No same-owner copy is required.
Set `scanning-repo-ref` to the same full commit SHA as the workflow pin. A reviewed
mirror needs an explicit `scanning-repository` input and must contain that commit.
Require setup and scanner jobs as well as aggregation; incomplete scans block.
See [workflow configuration sources](REUSABLE-WORKFLOWS.md#configs-come-from-the-reviewed-platform-revision).

The job installs an exact `snyk` CLI version from npm (`reusable-scan.yml:508`); bump it deliberately. Up to and including v2.3.2 it installed the latest on each run.
See [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md) for every input.

## Switching Cloud Providers

The scanning hooks work with **AWS**, **Azure**, and **GCP** Terraform code. The cloud provider setting controls which tool configurations (Checkov policies, tflint rulesets, policy overlays) are applied.

### Setting up for Azure

```bash
python scripts/setup-scan-fix.py --languages terraform --cloud-provider azure --tier standard
```

This copies Azure-specific configs to `.scanning/configs/`:

- `.checkov.yaml` -- Azure Checkov check exclusions (e.g., skips AWS/GCP-only checks)
- `.tflint.hcl` -- Azure tflint ruleset (`tflint-ruleset-azurerm`)
- `policy-overlay.yaml` -- Azure-specific organisational policies

### Setting up for GCP

```bash
python scripts/setup-scan-fix.py --languages terraform --cloud-provider gcp --tier standard
```

### Setting up for AWS

```bash
python scripts/setup-scan-fix.py --languages terraform --cloud-provider aws --tier standard
```

### Switching an existing repo

If your repo already has scanning installed and you need to switch cloud provider:

```bash
# Re-run setup with the new provider and --force to overwrite configs
python scripts/setup-scan-fix.py --languages terraform --cloud-provider azure --tier standard --force

# Verify the new configs
ls .scanning/configs/

# Stage and commit the config changes
git add .scanning/configs/ .pre-commit-config.yaml
git commit -m "chore: switch security scanning to Azure cloud provider"
```

### Multi-cloud repos

If your repository contains Terraform for multiple cloud providers, see [MULTI-CLOUD.md](MULTI-CLOUD.md) for configuration guidance.

### Cloud-specific template differences

The cloud-specific templates (`templates/aws/`, `templates/azure/`, `templates/gcp/`) are identical in hook configuration -- they differ only in the comments and the configs copied to `.scanning/configs/`. All hooks work the same regardless of cloud provider; the provider setting tunes which **policies and rules** are applied by Checkov and tflint.

## Choosing a Tier

| Tier | Hooks | Best for | Setup command |
| ---- | ----- | -------- | ------------- |
| **starter** | trivy-secrets, gitleaks, trivy-iac-critical | New adopters, minimal friction | `--tier starter` |
| **standard** | All starter + terraform_validate, terraform_tflint, snyk-iac (optional) | Most teams | `--tier standard` |
| **strict** | All standard + trivy-iac-full, checkov-strict, validate-suppressions, snyk-iac (optional) | Security-sensitive projects | `--tier strict` |

Do not upgrade tiers by just re-running setup with `--force`: `--hooks-runner` defaults
to `lefthook`, so omitting it silently switches an existing pre-commit consumer's runner.
Even passing `--hooks-runner pre-commit` explicitly does not add the new tier's hooks to
an existing `.pre-commit-config.yaml` — setup only writes that file when it is absent.
See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for the runner-preserving migration
that actually adds them.

## Getting Help

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) -- Common issues and fixes
- [HOOK-REFERENCE.md](HOOK-REFERENCE.md) -- Detailed hook documentation
- [SUPPRESSION-GOVERNANCE.md](SUPPRESSION-GOVERNANCE.md) -- Full suppression process
- [SEVERITY-MAPPING.md](SEVERITY-MAPPING.md) -- How severities map across tools
- [Getting started](SETUP-GUIDE.md) -- Canonical installation path
- [MULTI-CLOUD.md](MULTI-CLOUD.md) -- Multi-cloud repository configuration
- [Getting started](SETUP-GUIDE.md) -- Initial setup
