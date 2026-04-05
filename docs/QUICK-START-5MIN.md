# Quick Start (5 Minutes)

Get security scanning running in your Terraform repository in under 5 minutes.

## Prerequisites

- Git repository with Terraform files
- Python 3.8+ installed
- Internet access (first-time setup only)

## Step 1: Run Setup Script

### macOS / Linux (Recommended)

```bash
# Download and run the cross-platform Python setup script
python scripts/setup-scanning.py --cloud-provider aws --tier starter
```

Replace `aws` with `azure` or `gcp` as needed. Replace `starter` with `standard` or `strict` for more comprehensive scanning.

### Windows (PowerShell)

```powershell
# Admin install (uses Chocolatey)
.\scripts\setup-scanning.ps1 -CloudProvider aws -Tier starter

# Non-admin install (uses Scoop/pip)
.\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws -Tier starter
```

### What This Does

1. Installs security tools (Trivy, Checkov, tflint, Gitleaks, pre-commit)
2. Copies cloud-specific configs to `.scanning/configs/`
3. Creates `.pre-commit-config.yaml` from tier template
4. Runs `pre-commit install` to activate hooks

## Step 2: Make a Commit

```bash
git add .
git commit -m "feat: add new module"
# Hooks will scan for secrets and CRITICAL issues
```

Pre-commit hooks run automatically:
- **trivy-iac-critical**: Blocks CRITICAL Terraform misconfigurations
- **trivy-secrets**: Blocks committed secrets
- **gitleaks**: Blocks leaked credentials

If all checks pass, the commit succeeds. If a CRITICAL finding is detected, the commit is blocked with details about what to fix.

## Step 3: Review Results

After any hook run, check the scan report:

```bash
# Human-readable summary was printed to terminal
# Machine-readable JSON is at:
cat .scanning/last-scan.json
```

## Step 4: Push (Standard/Strict Tiers)

Standard and strict tiers add pre-push hooks:

```bash
git push
```

Pre-push runs additional checks:
- **trivy-iac-full**: All severity levels
- **checkov**: Policy-as-code checks
- **tflint**: Terraform linting
- **validate-suppressions**: Suppression file validation

## What Happens at Each Stage

| Stage | Hooks | Target Time |
|-------|-------|-------------|
| **pre-commit** | trivy-iac-critical, trivy-secrets, gitleaks, validate-suppressions | <10s total |
| **pre-push** | trivy-iac-full, checkov, checkov-strict, tflint | <60s total |

## What to Do When a Finding Blocks You

1. **Fix it**: Follow the remediation guidance in the terminal output
2. **Suppress it**: Add an entry to `.scan-suppressions.yaml` with business justification (see [Suppression Format](../specs/001-security-scanning-spec/contracts/suppression-format.md))
3. **Baseline it**: Run `.\scripts\create-baseline.ps1` to mark existing findings as known

## Emergency Bypass

```bash
git commit --no-verify -m "emergency: hotfix for production"
```

Bypasses are tracked and reported via metrics.

## Tier Comparison

| Capability | Starter | Standard | Strict |
|-----------|---------|----------|--------|
| CRITICAL IaC findings | Block | Block | Block |
| Secret detection | Block | Block | Block |
| Full IaC scan (all severities) | -- | Pre-push | Pre-push |
| Checkov policy scan | -- | Pre-push | Pre-push |
| Checkov strict (CRITICAL+HIGH fail) | -- | -- | Pre-push |
| tflint validation | -- | Pre-push | Pre-push |
| Suppression validation | -- | Pre-commit | Pre-commit |

## Next Steps

- **Upgrade tier**: See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for upgrade instructions
- **Customize**: Override hook args, stages, or file patterns in your `.pre-commit-config.yaml`
- **CI/CD**: Add the reusable workflow to your GitHub Actions (see [SETUP-GUIDE.md](SETUP-GUIDE.md#cicd-integration))
- **AI agents**: Use `python scripts/scan.py` for programmatic scanning (see [AI-AGENT-GUIDE.md](AI-AGENT-GUIDE.md))
- **All hooks**: See [HOOK-REFERENCE.md](HOOK-REFERENCE.md) for the complete hook reference
