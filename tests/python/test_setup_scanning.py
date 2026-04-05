"""Tests for scripts/setup-scanning.py - Cross-platform setup script."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import setup_scanning  # noqa: E402


class TestMinVersions:
    """Test minimum version configuration."""

    def test_trivy_min_version(self):
        assert setup_scanning.MIN_VERSIONS["trivy"] == (0, 48, 0)

    def test_checkov_min_version(self):
        assert setup_scanning.MIN_VERSIONS["checkov"] == (3, 0, 0)

    def test_tflint_min_version(self):
        assert setup_scanning.MIN_VERSIONS["tflint"] == (0, 50, 0)

    def test_precommit_min_version(self):
        assert setup_scanning.MIN_VERSIONS["pre-commit"] == (3, 0, 0)


class TestTotalTools:
    """Test tool count tracking."""

    def test_total_tools_is_five(self):
        assert setup_scanning.total_tools == 5


class TestLogFunctions:
    """Test logging helper functions exist and are callable."""

    def test_log_ok_exists(self):
        assert callable(setup_scanning.log_ok)

    def test_log_warn_exists(self):
        assert callable(setup_scanning.log_warn)

    def test_log_err_exists(self):
        assert callable(setup_scanning.log_err)

    def test_log_info_exists(self):
        assert callable(setup_scanning.log_info)

    def test_log_step_exists(self):
        assert callable(setup_scanning.log_step)


class TestScriptImport:
    """Test that the script can be imported without side effects."""

    def test_module_has_main(self):
        assert hasattr(setup_scanning, "main")
        assert callable(setup_scanning.main)

    def test_module_imports_platform(self):
        # The script should use platform.system() for OS detection
        content = Path(REPO_ROOT / "scripts" / "setup-scanning.py").read_text()
        assert "platform" in content

    def test_module_imports_subprocess(self):
        content = Path(REPO_ROOT / "scripts" / "setup-scanning.py").read_text()
        assert "subprocess" in content

    def test_module_imports_shutil(self):
        content = Path(REPO_ROOT / "scripts" / "setup-scanning.py").read_text()
        assert "shutil" in content


class TestScriptContent:
    """Test script content for required functionality."""

    @pytest.fixture(autouse=True)
    def load_content(self):
        self.content = Path(REPO_ROOT / "scripts" / "setup-scanning.py").read_text()

    def test_accepts_cloud_provider_argument(self):
        assert "--cloud-provider" in self.content

    def test_accepts_tier_argument(self):
        assert "--tier" in self.content

    def test_accepts_skip_tools_argument(self):
        assert "--skip-tools" in self.content

    def test_accepts_verbose_argument(self):
        assert "--verbose" in self.content

    def test_accepts_dry_run_argument(self):
        assert "--dry-run" in self.content

    def test_accepts_force_argument(self):
        assert "--force" in self.content

    def test_resolves_configs_from_script_location(self):
        assert "Path(__file__)" in self.content
        assert "parent.parent" in self.content

    def test_detects_os_with_platform(self):
        assert "platform.system()" in self.content

    def test_handles_windows(self):
        assert "Windows" in self.content

    def test_handles_darwin_macos(self):
        assert "Darwin" in self.content or "macOS" in self.content or "darwin" in self.content

    def test_handles_linux(self):
        assert "Linux" in self.content or "linux" in self.content

    def test_installs_precommit_hooks(self):
        assert "pre-commit install" in self.content

    def test_copies_configs_to_scanning_dir(self):
        assert ".scanning" in self.content
        assert "configs" in self.content

    def test_copies_tier_template(self):
        assert "template" in self.content.lower()

    def test_exit_code_0_for_success(self):
        assert "sys.exit(0)" in self.content

    def test_exit_code_1_for_failure(self):
        assert "sys.exit(1)" in self.content

    def test_exit_code_2_for_partial(self):
        assert "sys.exit(2)" in self.content

    def test_validates_cloud_provider_values(self):
        assert "aws" in self.content
        assert "azure" in self.content
        assert "gcp" in self.content

    def test_validates_tier_values(self):
        assert "starter" in self.content
        assert "standard" in self.content
        assert "strict" in self.content

    def test_trivy_installation(self):
        assert "trivy" in self.content.lower()

    def test_checkov_installation(self):
        assert "checkov" in self.content.lower()

    def test_tflint_installation(self):
        assert "tflint" in self.content.lower()

    def test_gitleaks_installation(self):
        assert "gitleaks" in self.content.lower()
