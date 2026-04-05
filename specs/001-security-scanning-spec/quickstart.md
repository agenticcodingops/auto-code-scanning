# Quickstart: Reusable Terraform Security Scanning

**Feature**: [spec.md](spec.md) | **Time**: ~5 minutes

## Prerequisites

- Git repository with Terraform files
- Python 3.8+ installed
- Internet access (first-time setup only)

## Step 1: Run Setup Script

```bash
# Clone or download the setup script, then run:
python setup-scanning.py --cloud-provider aws --tier starter
```

Replace `aws` with `azure` or `gcp` as needed. Replace `starter` with `standard` or `strict` for more comprehensive scanning.

**What this does**:
1. Installs security tools (Trivy, Checkov, tflint, Gitleaks, pre-commit)
2. Copies cloud-specific configs to `.scanning/configs/`
3. Creates `.pre-commit-config.yaml` from tier template
4. Runs `pre-commit install` to activate hooks

**Windows users**: Can also use PowerShell directly:
```powershell
.\scripts\setup-scanning.ps1 -CloudProvider aws -Tier starter
```

## Step 2: Make a Commit

```bash
git add .
git commit -m "Add security scanning"
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

## What to Do When a Finding Blocks You

1. **Fix it**: Follow the remediation guidance in the terminal output
2. **Suppress it**: Add an entry to `.scan-suppressions.yaml` with business justification (see [suppression-format.md](contracts/suppression-format.md))
3. **Baseline it**: Run `.\scripts\create-baseline.ps1` to mark existing findings as known

## Tier Comparison

| Capability | Starter | Standard | Strict |
|-----------|---------|----------|--------|
| CRITICAL IaC findings | Block | Block | Block |
| Secret detection | Block | Block | Block |
| Full IaC scan (all severities) | — | Pre-push | Pre-push |
| Checkov policy scan | — | Pre-push | Pre-push |
| Checkov strict (CRITICAL+HIGH fail) | — | — | Pre-push |
| tflint validation | — | Pre-push | Pre-push |
| Suppression validation | — | Pre-commit | Pre-commit |

## Next Steps

- **Upgrade tier**: See docs/TIER-UPGRADE-GUIDE.md for exact hooks to add
- **Customize**: Override hook args, stages, or file patterns in your `.pre-commit-config.yaml`
- **CI/CD**: Add the reusable workflow to your GitHub Actions (see [workflow-interface.md](contracts/workflow-interface.md))
- **AI agents**: Use `python scripts/scan.py` for programmatic scanning (see [cli-interface.md](contracts/cli-interface.md))
- **Suppress findings**: Follow the governance process in [suppression-format.md](contracts/suppression-format.md)
