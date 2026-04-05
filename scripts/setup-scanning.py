#!/usr/bin/env python3
"""Cross-platform setup script for Terraform security scanning tools.

Detects the operating system and installs Trivy, Checkov, tflint, Gitleaks,
and pre-commit using the appropriate package manager. Copies cloud-specific
configs to .scanning/configs/ and installs pre-commit hooks.

Usage:
    python scripts/setup-scanning.py --cloud-provider aws
    python scripts/setup-scanning.py --cloud-provider azure --tier standard
    python scripts/setup-scanning.py --cloud-provider gcp --tier strict --verbose

Exit codes:
    0 - Setup completed successfully
    1 - Setup failed (missing dependency, permission error)
    2 - Partial setup (some tools installed, some failed)
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Minimum tool versions
MIN_VERSIONS = {
    "trivy": (0, 48, 0),
    "checkov": (3, 0, 0),
    "tflint": (0, 50, 0),
    "pre-commit": (3, 0, 0),
}

# Track installation results
tools_installed = 0
tools_failed = 0
total_tools = 5  # trivy, checkov, tflint, gitleaks, pre-commit
verbose = False


def log_ok(msg):
    print(f"  [OK] {msg}")


def log_warn(msg):
    print(f"  [WARN] {msg}")


def log_err(msg):
    print(f"  [ERROR] {msg}", file=sys.stderr)


def log_info(msg):
    if verbose:
        print(f"  [INFO] {msg}")


def log_step(msg):
    print(f"\n{'=' * 70}")
    print(f" {msg}")
    print(f"{'=' * 70}")


def run_cmd(cmd, capture=True, check=False):
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            timeout=300,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else ""


def command_exists(cmd):
    """Check if a command is available on PATH."""
    return shutil.which(cmd) is not None


def parse_version(version_str):
    """Extract version tuple from a version string."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if match:
        return tuple(int(x) for x in match.groups())
    return None


def get_tool_version(cmd):
    """Get the version of a tool as a tuple."""
    rc, stdout, stderr = run_cmd([cmd, "--version"])
    if rc == 0:
        output = stdout or stderr
        return parse_version(output)
    return None


def version_str(version_tuple):
    """Format a version tuple as a string."""
    if version_tuple:
        return ".".join(str(x) for x in version_tuple)
    return "unknown"


def meets_minimum(tool_name, actual_version):
    """Check if the actual version meets the minimum requirement."""
    if tool_name not in MIN_VERSIONS or actual_version is None:
        return True
    return actual_version >= MIN_VERSIONS[tool_name]


def detect_os():
    """Detect the operating system."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        return system


def install_tool_brew(package, display_name, cmd_name=None):
    """Install a tool via Homebrew (macOS)."""
    global tools_installed, tools_failed
    cmd_name = cmd_name or package

    if command_exists(cmd_name):
        ver = get_tool_version(cmd_name)
        if meets_minimum(cmd_name, ver):
            min_str = f" (>= {version_str(MIN_VERSIONS.get(cmd_name, ()))})" if cmd_name in MIN_VERSIONS else ""
            log_ok(f"{display_name} v{version_str(ver)}{min_str}")
            tools_installed += 1
            return True

    log_info(f"Installing {display_name} via Homebrew...")
    rc, _, stderr = run_cmd(["brew", "install", package])
    if rc == 0 and command_exists(cmd_name):
        ver = get_tool_version(cmd_name)
        log_ok(f"{display_name} installed (v{version_str(ver)})")
        tools_installed += 1
        return True
    else:
        log_warn(f"{display_name} installation failed: {stderr}")
        tools_failed += 1
        return False


def install_tool_apt(package, display_name, cmd_name=None):
    """Install a tool via apt (Linux). Falls back to snap/direct download."""
    global tools_installed, tools_failed
    cmd_name = cmd_name or package

    if command_exists(cmd_name):
        ver = get_tool_version(cmd_name)
        if meets_minimum(cmd_name, ver):
            min_str = f" (>= {version_str(MIN_VERSIONS.get(cmd_name, ()))})" if cmd_name in MIN_VERSIONS else ""
            log_ok(f"{display_name} v{version_str(ver)}{min_str}")
            tools_installed += 1
            return True

    log_info(f"Installing {display_name} via apt...")
    rc, _, stderr = run_cmd(["sudo", "apt-get", "install", "-y", package])
    if rc == 0 and command_exists(cmd_name):
        ver = get_tool_version(cmd_name)
        log_ok(f"{display_name} installed (v{version_str(ver)})")
        tools_installed += 1
        return True
    else:
        log_warn(f"{display_name} apt installation failed: {stderr}")
        tools_failed += 1
        return False


def install_trivy_linux():
    """Install Trivy on Linux via official repo."""
    global tools_installed, tools_failed

    if command_exists("trivy"):
        ver = get_tool_version("trivy")
        if meets_minimum("trivy", ver):
            log_ok(f"Trivy v{version_str(ver)} (>= {version_str(MIN_VERSIONS['trivy'])})")
            tools_installed += 1
            return True

    log_info("Installing Trivy via official repository...")
    commands = [
        ["sudo", "apt-get", "install", "-y", "wget", "apt-transport-https", "gnupg", "lsb-release"],
        ["bash", "-c", "wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor | sudo tee /usr/share/keyrings/trivy.gpg > /dev/null"],
        ["bash", "-c", 'echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list'],
        ["sudo", "apt-get", "update"],
        ["sudo", "apt-get", "install", "-y", "trivy"],
    ]
    for cmd in commands:
        rc, _, stderr = run_cmd(cmd)
        if rc != 0:
            log_warn(f"Trivy installation step failed: {stderr}")
            tools_failed += 1
            return False

    if command_exists("trivy"):
        ver = get_tool_version("trivy")
        log_ok(f"Trivy installed (v{version_str(ver)})")
        tools_installed += 1
        return True

    tools_failed += 1
    return False


def install_pip_tool(package, display_name, cmd_name=None):
    """Install a Python package via pip."""
    global tools_installed, tools_failed
    cmd_name = cmd_name or package

    if command_exists(cmd_name):
        ver = get_tool_version(cmd_name)
        if meets_minimum(cmd_name, ver):
            min_str = f" (>= {version_str(MIN_VERSIONS.get(cmd_name, ()))})" if cmd_name in MIN_VERSIONS else ""
            log_ok(f"{display_name} v{version_str(ver)}{min_str}")
            tools_installed += 1
            return True

    log_info(f"Installing {display_name} via pip...")
    rc, _, stderr = run_cmd([sys.executable, "-m", "pip", "install", package, "--quiet"])
    if rc == 0:
        # pip install may put the command somewhere not yet on PATH; recheck
        if command_exists(cmd_name):
            ver = get_tool_version(cmd_name)
            log_ok(f"{display_name} installed (v{version_str(ver)})")
            tools_installed += 1
            return True
        else:
            log_warn(f"{display_name} installed but not found on PATH")
            tools_installed += 1
            return True
    else:
        log_warn(f"{display_name} pip installation failed: {stderr}")
        tools_failed += 1
        return False


def install_snyk():
    """Install Snyk CLI via npm (optional - requires npm and Snyk license)."""
    if command_exists("snyk"):
        ver = get_tool_version("snyk")
        log_ok(f"Snyk CLI already installed (v{version_str(ver)}) [optional]")
        return True

    if not command_exists("npm"):
        log_info("Snyk CLI not installed (npm not found). This is optional - ignore if no Snyk license.")
        return False

    log_info("Installing Snyk CLI via npm (optional - requires Snyk license)...")
    rc, _, stderr = run_cmd(["npm", "install", "-g", "snyk"])
    if rc == 0 and command_exists("snyk"):
        ver = get_tool_version("snyk")
        log_ok(f"Snyk CLI installed (v{version_str(ver)}) [optional]")
        return True
    elif rc == 0:
        log_info("Snyk CLI installed but not on PATH. This is optional.")
        return False
    else:
        log_info(f"Snyk CLI installation skipped: {stderr}. This is optional.")
        return False


def install_tools(os_type, dry_run=False):
    """Install all required tools for the detected OS."""
    if dry_run:
        log_info("Dry run - would install: trivy, checkov, tflint, gitleaks, pre-commit")
        return

    if os_type == "windows":
        # On Windows, delegate to PowerShell script
        log_info("Windows detected - delegating to PowerShell setup script")
        ps_script = Path(__file__).parent / "setup-scanning.ps1"
        if ps_script.exists():
            log_info(f"Run: powershell -File {ps_script} -CloudProvider <provider>")
        else:
            log_warn("setup-scanning.ps1 not found")
        return

    if os_type == "macos":
        # Check Homebrew
        if not command_exists("brew"):
            log_err("Homebrew not found. Install from https://brew.sh")
            return

        install_tool_brew("trivy", "Trivy")
        install_tool_brew("tflint", "tflint")
        install_tool_brew("gitleaks", "Gitleaks")

    elif os_type == "linux":
        install_trivy_linux()

        # tflint on Linux - direct download
        if not command_exists("tflint"):
            log_info("Installing tflint via install script...")
            rc, _, _ = run_cmd(["bash", "-c", "curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash"])
            if rc == 0 and command_exists("tflint"):
                ver = get_tool_version("tflint")
                log_ok(f"tflint installed (v{version_str(ver)})")
                global tools_installed, tools_failed
                tools_installed += 1
            else:
                log_warn("tflint installation failed")
                tools_failed += 1
        else:
            ver = get_tool_version("tflint")
            if meets_minimum("tflint", ver):
                log_ok(f"tflint v{version_str(ver)} (>= {version_str(MIN_VERSIONS['tflint'])})")
                tools_installed += 1

        # Gitleaks on Linux
        if not command_exists("gitleaks"):
            log_info("Installing Gitleaks via go install or download...")
            install_tool_apt("gitleaks", "Gitleaks")
        else:
            log_ok("Gitleaks already installed")
            tools_installed += 1

    # Python-based tools (all platforms)
    install_pip_tool("pre-commit", "pre-commit")
    install_pip_tool("checkov", "Checkov")

    # Optional tools
    log_info("Optional tools:")
    install_snyk()


def copy_configs(cloud_provider, repo_path):
    """Copy cloud-specific configs to .scanning/configs/."""
    log_step(f"Copying {cloud_provider.upper()} Configs")

    scanning_config_dir = repo_path / ".scanning" / "configs"
    scanning_config_dir.mkdir(parents=True, exist_ok=True)

    # Look for configs in multiple locations (first match wins)
    cache_config_dir = None

    # 1. Relative to this script's location (scanning repo's configs/)
    script_config_dir = Path(__file__).resolve().parent.parent / "configs"
    if (script_config_dir / cloud_provider).is_dir():
        cache_config_dir = script_config_dir
        log_info(f"Using configs from scanning repo: {script_config_dir}")

    # 2. Pre-commit cache
    if cache_config_dir is None:
        home = Path.home()
        pre_commit_cache = home / ".cache" / "pre-commit"

        if pre_commit_cache.exists():
            for cache_dir in pre_commit_cache.rglob("configs"):
                provider_dir = cache_dir / cloud_provider
                if provider_dir.is_dir():
                    cache_config_dir = cache_dir
                    log_info(f"Using configs from pre-commit cache: {cache_dir}")
                    break

    # 3. Fallback: local configs directory (if running from the scanning repo itself)
    if cache_config_dir is None:
        local_config_dir = repo_path / "configs"
        if (local_config_dir / cloud_provider).is_dir():
            cache_config_dir = local_config_dir
            log_info(f"Using configs from local directory: {local_config_dir}")

    if cache_config_dir:
        provider_dir = cache_config_dir / cloud_provider
        if provider_dir.is_dir():
            count = 0
            for f in provider_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, scanning_config_dir / f.name)
                    log_info(f"Copied {f.name}")
                    count += 1
            log_ok(f"Copied {count} provider config(s) for {cloud_provider.upper()}")

        # Copy common configs
        common_dir = cache_config_dir / "common"
        if common_dir.is_dir():
            for f in common_dir.iterdir():
                if f.is_file():
                    dest = scanning_config_dir / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)

        # Copy suppression template to repo root
        suppression_src = scanning_config_dir / ".scan-suppressions.yaml"
        suppression_dest = repo_path / ".scan-suppressions.yaml"
        if suppression_src.exists() and not suppression_dest.exists():
            shutil.copy2(suppression_src, suppression_dest)
            log_ok("Copied suppression template to .scan-suppressions.yaml")
    else:
        log_warn(f"Could not find config source for {cloud_provider}")
        log_info("Configs will be available after first pre-commit run")

    return cache_config_dir


def copy_tier_template(tier, repo_path, config_source_dir, force=False):
    """Copy the tier template to .pre-commit-config.yaml."""
    log_step(f"Setting Up {tier} Tier Template")

    dest = repo_path / ".pre-commit-config.yaml"
    if dest.exists() and not force:
        log_info(".pre-commit-config.yaml already exists - skipping template copy")
        log_info("Use --force to overwrite existing config")
        return

    template_source = None

    # 1. Relative to this script's location (scanning repo's templates/)
    script_template = Path(__file__).resolve().parent.parent / "templates" / tier / "pre-commit-config.yaml"
    if script_template.exists():
        template_source = script_template
        log_info(f"Using template from scanning repo: {script_template}")

    # 2. Check pre-commit cache
    if template_source is None and config_source_dir:
        candidate = config_source_dir.parent / "templates" / tier / "pre-commit-config.yaml"
        if candidate.exists():
            template_source = candidate

    # 3. Fallback: local templates (if running from the scanning repo itself)
    if template_source is None:
        local_template = repo_path / "templates" / tier / "pre-commit-config.yaml"
        if local_template.exists():
            template_source = local_template

    if template_source:
        if dest.exists():
            log_info(f"Overwriting existing .pre-commit-config.yaml (--force)")
        shutil.copy2(template_source, dest)
        log_ok(f"Copied {tier} tier template to .pre-commit-config.yaml")
    else:
        log_warn(f"Could not find {tier} tier template")


def init_tflint(cloud_provider, repo_path):
    """Initialize tflint plugins."""
    log_step("Initializing tflint Plugins")

    if not command_exists("tflint"):
        log_warn("tflint not available - skipping plugin initialization")
        return

    tflint_config = repo_path / ".scanning" / "configs" / ".tflint.hcl"
    if tflint_config.exists():
        rc, _, stderr = run_cmd(["tflint", "--init", "--config", str(tflint_config)])
        if rc == 0:
            log_ok(f"tflint plugins initialized for {cloud_provider.upper()}")
        else:
            log_warn(f"tflint plugin initialization failed: {stderr}")
    else:
        log_info("No .tflint.hcl in .scanning/configs/ - plugins will initialize on first run")


def install_hooks(repo_path):
    """Install pre-commit and pre-push hooks."""
    log_step("Installing Pre-commit Hooks")

    git_dir = repo_path / ".git"
    if not git_dir.exists():
        log_warn("Not a Git repository - skipping hook installation")
        return

    config_file = repo_path / ".pre-commit-config.yaml"
    if not config_file.exists():
        log_warn(".pre-commit-config.yaml not found - hooks not installed")
        return

    if command_exists("pre-commit"):
        rc, _, stderr = run_cmd(["pre-commit", "install"], check=False)
        if rc == 0:
            log_ok("Pre-commit hooks installed")
        else:
            log_warn(f"Could not install pre-commit hooks: {stderr}")

        rc, _, stderr = run_cmd(["pre-commit", "install", "--hook-type", "pre-push"], check=False)
        if rc == 0:
            log_ok("Pre-push hooks installed")
        else:
            log_warn(f"Could not install pre-push hooks: {stderr}")
    else:
        log_warn("pre-commit not available - hooks need manual installation")
        log_info("Run: pip install pre-commit && pre-commit install")


def verify_installation():
    """Verify all tools are installed and meet version requirements."""
    log_step("Verifying Installation")

    tools = [
        ("Trivy", "trivy"),
        ("Checkov", "checkov"),
        ("tflint", "tflint"),
        ("Gitleaks", "gitleaks"),
        ("pre-commit", "pre-commit"),
    ]

    for display_name, cmd_name in tools:
        if command_exists(cmd_name):
            ver = get_tool_version(cmd_name)
            ver_str = f"v{version_str(ver)}" if ver else "(version unknown)"
            min_str = f" (>= {version_str(MIN_VERSIONS[cmd_name])})" if cmd_name in MIN_VERSIONS else ""
            log_ok(f"{display_name} {ver_str}{min_str}")
        else:
            log_warn(f"{display_name}: not found")

    # Optional tools
    if command_exists("snyk"):
        ver = get_tool_version("snyk")
        ver_str = f"v{version_str(ver)}" if ver else "(version unknown)"
        log_ok(f"Snyk CLI {ver_str} [optional]")
    else:
        log_info("Snyk CLI: not installed [optional - requires npm and Snyk license]")


def main():
    global verbose

    parser = argparse.ArgumentParser(
        description="Set up Terraform security scanning tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cloud-provider",
        required=True,
        choices=["aws", "azure", "gcp"],
        help="Cloud provider (aws, azure, or gcp)",
    )
    parser.add_argument(
        "--tier",
        default="starter",
        choices=["starter", "standard", "strict"],
        help="Adoption tier (default: starter)",
    )
    parser.add_argument(
        "--skip-tools",
        action="store_true",
        help="Skip tool installation (config only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .pre-commit-config.yaml with tier template",
    )

    args = parser.parse_args()
    verbose = args.verbose

    os_type = detect_os()
    repo_path = Path.cwd()

    print(f"\nSetting up security scanning for {args.cloud_provider.upper()} ({args.tier} tier)...")
    print(f"  Platform: {os_type} ({platform.platform()})")
    print()

    if args.dry_run:
        log_info("DRY RUN - no changes will be made")

    # Install tools
    if not args.skip_tools:
        log_step("Installing Security Scanning Tools")
        install_tools(os_type, dry_run=args.dry_run)
    else:
        log_info("Skipping tool installation (--skip-tools)")

    if not args.dry_run:
        # Copy configs
        config_source = copy_configs(args.cloud_provider, repo_path)

        # Copy tier template
        copy_tier_template(args.tier, repo_path, Path(config_source) if config_source else None, force=args.force)

        # Initialize tflint
        init_tflint(args.cloud_provider, repo_path)

        # Install hooks
        install_hooks(repo_path)

        # Verify
        verify_installation()

    # Summary
    print(f"\n{'=' * 70}")
    print(f" SETUP COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Cloud Provider: {args.cloud_provider.upper()}")
    print(f"  Adoption Tier:  {args.tier}")
    print(f"  Tools:          {tools_installed}/{total_tools} installed")
    print()

    if tools_failed == 0:
        log_ok("All tools installed and verified!")
    else:
        log_warn(f"{tools_failed} tool(s) need attention - check warnings above")

    print()
    print("Setup complete. Run 'git commit' to test hooks.")
    print()

    # Exit code
    if tools_failed == 0:
        sys.exit(0)
    elif tools_installed > 0:
        sys.exit(2)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
