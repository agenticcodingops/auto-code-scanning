"""Shared pytest fixtures for security scanning tests."""
import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure scripts directory is importable
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _import_hyphenated(module_name, file_name):
    """Import a Python module with hyphens in the filename."""
    file_path = SCRIPTS_DIR / file_name
    if not file_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Pre-import hyphenated modules so tests can use standard import
_import_hyphenated("validate_suppressions", "validate-suppressions.py")
_import_hyphenated("setup_scanning", "setup-scanning.py")


@pytest.fixture
def repo_root():
    """Return the repository root path."""
    return REPO_ROOT


@pytest.fixture
def fixtures_dir():
    """Return the test fixtures directory path."""
    return REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def valid_aws_fixture(fixtures_dir):
    """Return path to valid AWS Terraform fixture."""
    return fixtures_dir / "terraform-valid" / "aws"


@pytest.fixture
def critical_aws_fixture(fixtures_dir):
    """Return path to critical AWS Terraform fixture."""
    return fixtures_dir / "terraform-critical" / "aws"


@pytest.fixture
def secret_fixture(fixtures_dir):
    """Return path to secret detection Terraform fixture."""
    return fixtures_dir / "terraform-secret"
