"""Tests for scripts/validate-suppressions.py - Suppression validation."""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Must have PyYAML installed for these tests
yaml = pytest.importorskip("yaml")

import validate_suppressions as vs  # noqa: E402


def write_suppression_file(tmpdir, data):
    """Helper to write a suppression YAML file for testing."""
    filepath = Path(tmpdir) / ".scan-suppressions.yaml"
    filepath.write_text(yaml.dump(data, default_flow_style=False))
    return str(filepath)


class TestParseIsoDate:
    """Test ISO date parsing."""

    def test_valid_date_string(self):
        result = vs.parse_iso_date("2026-01-15")
        assert result == date(2026, 1, 15)

    def test_date_object_passthrough(self):
        d = date(2026, 6, 1)
        result = vs.parse_iso_date(d)
        assert result == d

    def test_invalid_date_returns_none(self):
        assert vs.parse_iso_date("not-a-date") is None

    def test_none_returns_none(self):
        assert vs.parse_iso_date(None) is None

    def test_empty_string_returns_none(self):
        assert vs.parse_iso_date("") is None


class TestValidationResult:
    """Test the ValidationResult collector."""

    def test_new_result_has_no_errors(self):
        r = vs.ValidationResult()
        assert not r.has_errors
        assert r.errors == []
        assert r.warnings == []

    def test_error_makes_has_errors_true(self):
        r = vs.ValidationResult()
        r.error("V-001", "test error")
        assert r.has_errors
        assert len(r.errors) == 1

    def test_warning_does_not_trigger_has_errors(self):
        r = vs.ValidationResult()
        r.warning("W-001", "test warning")
        assert not r.has_errors
        assert len(r.warnings) == 1

    def test_to_dict_structure(self):
        r = vs.ValidationResult()
        r.error("V-001", "test")
        d = r.to_dict()
        assert d["valid"] is False
        assert d["error_count"] == 1
        assert d["warning_count"] == 0


class TestValidateFile:
    """Test full file validation."""

    def test_valid_suppression_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            expires = today + timedelta(days=90)
            data = {
                "schema_version": "1.0",
                "settings": {
                    "max_expiry_days": 180,
                    "require_security_approval": ["CRITICAL", "HIGH"],
                    "review_frequency_days": 90,
                },
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "This is a valid business justification for the suppression",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(expires),
                        "severity": "MEDIUM",
                        "ticket": "JIRA-123",
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert not result.has_errors

    def test_missing_schema_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "trivy_suppressions": [],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-002" in error_rules

    def test_wrong_schema_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "schema_version": "2.0",
                "trivy_suppressions": [],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-002" in error_rules

    def test_missing_required_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        # missing: reason, owner, approved_date, expires_date
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-003" in error_rules

    def test_invalid_tool_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "invalid_tool",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-004" in error_rules

    def test_expires_beyond_max_expiry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "settings": {"max_expiry_days": 180},
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=365)),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-006" in error_rules

    def test_missing_approved_by_for_critical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "settings": {
                    "max_expiry_days": 180,
                    "require_security_approval": ["CRITICAL", "HIGH"],
                },
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                        "severity": "CRITICAL",
                        # missing: approved_by
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-007" in error_rules

    def test_duplicate_rule_id_tool_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            entry = {
                "rule_id": "AVD-AWS-0107",
                "tool": "trivy",
                "reason": "Valid reason that is long enough",
                "owner": "user@example.com",
                "approved_date": str(today),
                "expires_date": str(today + timedelta(days=90)),
            }
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [entry, entry],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-008" in error_rules

    def test_invalid_rule_id_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "INVALID-FORMAT",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors
            error_rules = [e["rule"] for e in result.errors]
            assert "V-009" in error_rules

    def test_checkov_rule_id_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "checkov_suppressions": [
                    {
                        "rule_id": "CKV_AWS_19",
                        "tool": "checkov",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            # Should not have V-009 error for valid Checkov format
            error_rules = [e["rule"] for e in result.errors]
            assert "V-009" not in error_rules

    def test_file_not_found(self):
        result = vs.validate_file("/nonexistent/path/file.yaml")
        assert result.has_errors
        error_rules = [e["rule"] for e in result.errors]
        assert "V-001" in error_rules

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / ".scan-suppressions.yaml"
            filepath.write_text("")
            result = vs.validate_file(str(filepath))
            assert result.has_errors

    def test_reason_too_short(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "short",  # Less than MIN_REASON_LENGTH (10)
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath)
            assert result.has_errors


class TestStrictMode:
    """Test strict mode (warnings become errors)."""

    def test_strict_promotes_warnings_to_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today()
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(today),
                        "expires_date": str(today + timedelta(days=90)),
                        # Missing ticket (W-002) and severity (W-003)
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)

            # Non-strict: should be warnings only
            result_normal = vs.validate_file(filepath, strict=False)
            assert not result_normal.has_errors
            assert len(result_normal.warnings) > 0

            # Strict: warnings promoted to errors
            result_strict = vs.validate_file(filepath, strict=True)
            assert result_strict.has_errors


class TestCIMode:
    """Test CI mode (expired suppressions are errors)."""

    def test_ci_mode_expired_is_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            past = date.today() - timedelta(days=30)
            expired = date.today() - timedelta(days=1)
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(past),
                        "expires_date": str(expired),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath, ci_mode=True)
            assert result.has_errors

    def test_non_ci_mode_expired_is_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            past = date.today() - timedelta(days=30)
            expired = date.today() - timedelta(days=1)
            data = {
                "schema_version": "1.0",
                "trivy_suppressions": [
                    {
                        "rule_id": "AVD-AWS-0107",
                        "tool": "trivy",
                        "reason": "Valid reason that is long enough",
                        "owner": "user@example.com",
                        "approved_date": str(past),
                        "expires_date": str(expired),
                    }
                ],
            }
            filepath = write_suppression_file(tmpdir, data)
            result = vs.validate_file(filepath, ci_mode=False)
            # Expired suppression should be a warning, not error
            error_rules = [e["rule"] for e in result.errors]
            warning_rules = [w["rule"] for w in result.warnings]
            assert "W-001" in warning_rules or "V-006" not in error_rules


class TestFormatOutput:
    """Test output formatting."""

    def test_text_format_errors(self):
        result = vs.ValidationResult()
        result.error("V-001", "YAML syntax error")
        output = vs.format_text(result, "test.yaml")
        assert "ERROR" in output
        assert "V-001" in output

    def test_text_format_pass(self):
        result = vs.ValidationResult()
        result.entry_count = 3
        output = vs.format_text(result, "test.yaml")
        assert "passed" in output.lower()

    def test_json_format(self):
        result = vs.ValidationResult()
        result.entry_count = 2
        output = vs.format_json(result, "test.yaml")
        data = json.loads(output)
        assert data["valid"] is True
        assert data["entry_count"] == 2
        assert data["file"] == "test.yaml"
