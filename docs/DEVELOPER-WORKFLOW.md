# Developer Workflow Guide

Day-to-day guide for working with security scanning hooks in your Terraform repository.

## What Happens When You Commit

When you run `git commit`, pre-commit hooks scan **only your staged changes**:

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

Pre-push hooks run additional checks on `git push`:

| Hook | What it checks | Blocks on |
| ---- | -------------- | --------- |
| **trivy-iac-full** | All severity misconfigurations | Any severity |
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

If the finding is a false positive or an accepted risk, add it to `.scan-suppressions.yaml`:

```yaml
# .scan-suppressions.yaml
trivy_suppressions:
  - rule_id: AVD-AWS-0057
    tool: trivy
    severity: CRITICAL
    reason: "Egress to 0.0.0.0/0 is required for NAT gateway connectivity in this module"
    file_pattern: "terraform/modules/aws/networking/nat/*.tf"
    owner: your-team@company.com
    approved_date: "2026-02-25"
    expires_date: "2026-05-25"
    approved_by: security-team@company.com
    ticket: "BDCD-999"
```

**Rules for suppressions:**
- LOW/MEDIUM: Module owner can approve, max 6 months
- HIGH/CRITICAL: Requires `approved_by` from security team, max 1-3 months
- All suppressions require a Jira ticket for HIGH/CRITICAL
- See [SUPPRESSION-GOVERNANCE.md](SUPPRESSION-GOVERNANCE.md) for full details

Then commit the suppression file:

```bash
git add .scan-suppressions.yaml
git commit -m "chore: suppress AVD-AWS-0057 for NAT gateway module (BDCD-999)"
```

## Option 3: Skip Specific Hooks (Temporary)

Use the `SKIP` environment variable to bypass specific hooks for one commit:

```bash
# Skip one hook
SKIP=trivy-iac-critical git commit -m "wip: work in progress"

# Skip multiple hooks
SKIP=trivy-iac-critical,terraform_validate,terraform_tflint git commit -m "wip: terraform changes"

# Skip only our security hooks (keep formatting hooks)
SKIP=trivy-iac-critical,trivy-secrets,gitleaks git commit -m "wip: will fix findings later"
```

**When to use this:**
- Pre-existing findings in a module you're modifying (not caused by your changes)
- Tool infrastructure issues (crashes, timeouts)
- Work-in-progress commits on a feature branch

**Important:** `SKIP` only applies to the current command. The next commit will run all hooks normally.

## Option 4: Emergency Bypass (All Hooks)

For urgent production fixes, skip ALL hooks:

```bash
git commit --no-verify -m "hotfix: production issue BDCD-999"
```

**Use sparingly.** Bypasses are visible in CI and may be flagged by the bypass detection workflow.

## Handling Pre-Existing Findings

When you modify a file in a module that has pre-existing security issues, the IaC hooks scan the entire module directory (not just your file). This is by design -- IaC scanners need full module context.

**You are NOT expected to fix all pre-existing issues.** Options:

1. **Fix if quick** -- If the finding is in code you're already changing, fix it
2. **Suppress it** -- Add to `.scan-suppressions.yaml` with a ticket to fix later
3. **Skip the hook** -- Use `SKIP=trivy-iac-critical` for this commit
4. **Create a tech debt ticket** -- Log the finding in Jira for planned remediation

## Quick Reference

| I want to... | Command |
| ------------ | ------- |
| See what hooks will run | `pre-commit run --all-files --dry-run` |
| Run hooks manually | `pre-commit run --all-files` |
| Run a specific hook | `pre-commit run trivy-iac-critical --all-files` |
| Run with verbose output | `SCAN_VERBOSE=1 pre-commit run --all-files` |
| Skip a specific hook | `SKIP=hook-id git commit -m "message"` |
| Skip all hooks | `git commit --no-verify -m "message"` |
| View last scan results | `cat .scanning/last-scan.json` |
| Validate suppressions | `python scripts/validate-suppressions.py .scan-suppressions.yaml` |
| Clear pre-commit cache | `pre-commit clean` |
| Update hooks to latest | `pre-commit autoupdate` |

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
| Terraform files (.tf) | IaC hooks scan the **module directory** containing the changed file. Secret hooks scan staged files only. |
| Mix of both | Both IaC and secret hooks run on their respective scopes. |

**Why does trivy-iac scan the whole module directory?**

IaC security rules need full context. A `main.tf` resource might reference a variable in `variables.tf` or use a local from `locals.tf`. Scanning a single file in isolation would miss cross-file dependencies and produce false results.

## Enabling Snyk IaC (Optional)

Snyk IaC provides additional commercial security scanning on top of the open-source tools. It requires a Snyk license and is **fail-open** -- if Snyk is not installed or not authenticated, the hook exits cleanly and does not block your commit or push.

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
    rev: v1.0.0
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
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
    with:
      terraform-directory: "."
      cloud-provider: "aws"
      enable-snyk: true
    secrets: inherit  # Must include SNYK_TOKEN
```

## Switching Cloud Providers

The scanning hooks work with **AWS**, **Azure**, and **GCP** Terraform code. The cloud provider setting controls which tool configurations (Checkov policies, tflint rulesets, policy overlays) are applied.

### Setting up for Azure

```bash
python scripts/setup-scanning.py --cloud-provider azure --tier standard
```

This copies Azure-specific configs to `.scanning/configs/`:

- `.checkov.yaml` -- Azure Checkov check exclusions (e.g., skips AWS/GCP-only checks)
- `.tflint.hcl` -- Azure tflint ruleset (`tflint-ruleset-azurerm`)
- `policy-overlay.yaml` -- Azure-specific organisational policies

### Setting up for GCP

```bash
python scripts/setup-scanning.py --cloud-provider gcp --tier standard
```

### Setting up for AWS

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier standard
```

### Switching an existing repo

If your repo already has scanning installed and you need to switch cloud provider:

```bash
# Re-run setup with the new provider and --force to overwrite configs
python scripts/setup-scanning.py --cloud-provider azure --tier standard --force

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

Upgrade tiers by re-running setup with `--force`:

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier strict --force
```

See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for detailed upgrade instructions.

## Getting Help

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) -- Common issues and fixes
- [HOOK-REFERENCE.md](HOOK-REFERENCE.md) -- Detailed hook documentation
- [SUPPRESSION-GOVERNANCE.md](SUPPRESSION-GOVERNANCE.md) -- Full suppression process
- [SEVERITY-MAPPING.md](SEVERITY-MAPPING.md) -- How severities map across tools
- [SETUP-GUIDE.md](SETUP-GUIDE.md) -- Full installation reference
- [MULTI-CLOUD.md](MULTI-CLOUD.md) -- Multi-cloud repository configuration
- [QUICK-START-5MIN.md](QUICK-START-5MIN.md) -- Initial setup
