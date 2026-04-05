# Setup Guide

Detailed setup instructions for auto-code-scanning.

## Prerequisites

| Requirement | Minimum Version |
|------------|----------------|
| Python | 3.8+ |
| Git | 2.0+ |
| pre-commit | 3.0+ |
| Trivy | 0.48.0+ |
| Checkov | 3.0.0+ |
| tflint | 0.50.0+ |
| Gitleaks | 8.0+ |
| Snyk CLI (optional) | 1.0+ |

## Installation Methods

### Method 1: Cross-Platform Python Setup (Recommended)

The Python setup script works on macOS, Linux, and Windows.

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier starter
```

**What it does by OS**:

| OS | Package Manager | Tool Installation |
|----|----------------|-------------------|
| macOS | Homebrew | `brew install trivy tflint gitleaks` |
| Linux (Debian/Ubuntu) | apt | `apt-get install trivy` + pip for others |
| Linux (RHEL/Fedora) | yum/dnf | Similar to apt path |
| Windows | Delegates to PS1 | Calls `setup-scanning.ps1` automatically |

**Optional**: If you have a Snyk license, the setup script also installs Snyk CLI via npm (requires Node.js/npm).

**Options**:

```bash
# Dry run (show what would be done)
python scripts/setup-scanning.py --cloud-provider azure --dry-run

# Skip tool installation (config only)
python scripts/setup-scanning.py --cloud-provider gcp --skip-tools

# Force overwrite existing .pre-commit-config.yaml with tier template
python scripts/setup-scanning.py --cloud-provider aws --tier standard --force

# Verbose output
python scripts/setup-scanning.py --cloud-provider aws --tier standard --verbose
```

### Method 2: Windows PowerShell (Admin)

```powershell
.\scripts\setup-scanning.ps1 -CloudProvider aws -Tier starter
```

Uses Chocolatey for tool installation. Requires administrator privileges.

### Method 3: Windows PowerShell (Non-Admin)

```powershell
.\scripts\setup-scanning-no-admin.ps1 -CloudProvider aws -Tier starter
```

Uses Scoop and pip for tool installation. No administrator privileges required.

### Method 4: Manual Installation

1. Install required tools:

   **macOS**:
   ```bash
   brew install trivy tflint gitleaks
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk && snyk auth
   ```

   **Linux (Debian/Ubuntu)**:
   ```bash
   # Trivy
   sudo apt-get install wget apt-transport-https gnupg lsb-release
   wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
   echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
   sudo apt-get update && sudo apt-get install trivy

   # tflint
   curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

   # Gitleaks
   brew install gitleaks  # or download from GitHub releases

   # Checkov and pre-commit
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk && snyk auth
   ```

   **Windows (Chocolatey)**:
   ```powershell
   choco install trivy tflint gitleaks -y
   pip install pre-commit checkov

   # Optional: Snyk CLI (requires npm and Snyk license)
   npm install -g snyk
   snyk auth
   ```

2. Copy cloud-specific configs:
   ```bash
   mkdir -p .scanning/configs
   cp configs/aws/.checkov.yaml .scanning/configs/
   cp configs/aws/.tflint.hcl .scanning/configs/
   cp configs/aws/policy-overlay.yaml .scanning/configs/
   ```

3. Copy a tier template:
   ```bash
   cp templates/starter/pre-commit-config.yaml .pre-commit-config.yaml
   ```

4. Install hooks:
   ```bash
   pre-commit install
   pre-commit install --hook-type pre-push
   ```

## Cloud Provider Configuration

During setup, specify your cloud provider to get the correct tool configurations:

```bash
python scripts/setup-scanning.py --cloud-provider azure
```

This copies provider-specific files to `.scanning/configs/`:
- `.checkov.yaml` - Checkov check exclusions for your cloud
- `.tflint.hcl` - tflint ruleset and rules for your cloud
- `policy-overlay.yaml` - Organization-specific policy rules

See [Multi-Cloud Configuration](MULTI-CLOUD.md) for multi-cloud repositories.

## Tier Selection

| Tier | Hooks Installed | Best For |
|------|----------------|----------|
| **starter** | trivy-iac-critical, trivy-secrets, gitleaks | New adopters, minimal friction |
| **standard** | All starter + trivy-iac-full, checkov, tflint, validate-suppressions, snyk-iac (optional) | Most teams |
| **strict** | All standard + checkov-strict, snyk-iac (optional) | Security-sensitive projects |

See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for upgrade instructions.

## Partial Failure Recovery

If the setup script encounters errors installing some tools:

- **Exit code 0**: All tools installed successfully
- **Exit code 1**: Setup failed completely (missing dependency, permission error)
- **Exit code 2**: Partial setup (some tools installed, some failed)

On partial failure:
1. The script continues installing remaining tools
2. Warnings are printed for each failed tool with manual install instructions
3. Re-running the script is safe (idempotent) -- it skips already-installed tools
4. Fix the failed tools manually, then re-run to verify

Example partial failure output:
```
Setting up security scanning for AWS (starter tier)...
  [OK] Trivy v0.57.0 (>= 0.48.0)
  [OK] Checkov v3.2.1 (>= 3.0.0)
  [WARN] tflint installation failed - run manually: brew install tflint
  [OK] Gitleaks v8.18.0
  [OK] pre-commit v3.6.0 (>= 3.0.0)
  [OK] Configs copied to .scanning/configs/
  [OK] pre-commit hooks installed

Setup complete (4/5 tools). Run 'git commit' to test hooks.
```

## CI/CD Integration

Add a `.github/workflows/security.yml` to your repository:

```yaml
name: Security Scan
on:
  pull_request:
    paths: ["**/*.tf"]
  push:
    branches: [main]

jobs:
  security:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
    with:
      terraform-directory: "."
      cloud-provider: "aws"
      severity-threshold: "CRITICAL,HIGH"
      upload-sarif: true
    secrets: inherit
```

**Optional: Enable Snyk scanning in CI** (requires Snyk license and `SNYK_TOKEN` secret):

```yaml
jobs:
  security:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
    with:
      terraform-directory: "."
      cloud-provider: "aws"
      severity-threshold: "CRITICAL,HIGH"
      upload-sarif: true
      enable-snyk: true
    secrets: inherit  # Must include SNYK_TOKEN
```

See the [workflow interface contract](../specs/001-security-scanning-spec/contracts/workflow-interface.md) for all available inputs and outputs.

## Verification

After setup, verify everything is working:

```bash
# Run all hooks against current files
pre-commit run --all-files

# Test a specific hook
pre-commit run trivy-iac-critical --all-files

# Test the optional Snyk hook (requires Snyk CLI + authentication)
pre-commit run snyk-iac --all-files --hook-stage pre-push
```

## Updating

```bash
# Update hooks to latest version
pre-commit autoupdate

# Update to a specific version
# Edit .pre-commit-config.yaml and change rev: to desired tag
```

See [VERSION-PINNING.md](VERSION-PINNING.md) for version management guidance.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.
