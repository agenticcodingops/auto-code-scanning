"""Tests for scripts/scan.py - AI agent scanning interface."""
import hashlib
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan  # noqa: E402


class TestSeverityMapping:
    """Test severity normalization mappings."""

    def test_trivy_critical_maps_to_critical(self):
        assert scan.map_trivy_severity("CRITICAL") == "CRITICAL"

    def test_trivy_high_maps_to_high(self):
        assert scan.map_trivy_severity("HIGH") == "HIGH"

    def test_trivy_medium_maps_to_medium(self):
        assert scan.map_trivy_severity("MEDIUM") == "MEDIUM"

    def test_trivy_low_maps_to_low(self):
        assert scan.map_trivy_severity("LOW") == "LOW"

    def test_trivy_unknown_maps_to_low(self):
        assert scan.map_trivy_severity("UNKNOWN") == "LOW"

    def test_trivy_unrecognized_maps_to_low(self):
        assert scan.map_trivy_severity("FOOBAR") == "LOW"

    def test_checkov_critical_maps_to_critical(self):
        assert scan.map_checkov_severity("CRITICAL") == "CRITICAL"

    def test_checkov_high_maps_to_high(self):
        assert scan.map_checkov_severity("HIGH") == "HIGH"

    def test_checkov_none_maps_to_medium(self):
        assert scan.map_checkov_severity(None) == "MEDIUM"


class TestRemediationUrls:
    """Test remediation URL generation."""

    def test_checkov_url(self):
        url = scan.generate_remediation_url("checkov", "CKV_AWS_19")
        assert url == "https://docs.checkov.io/docs/CKV_AWS_19"

    def test_trivy_url(self):
        url = scan.generate_remediation_url("trivy", "AVD-AWS-0107")
        assert url == "https://avd.aquasec.com/misconfig/avd-aws-0107"

    def test_unknown_tool_returns_empty(self):
        url = scan.generate_remediation_url("unknown", "SOME_RULE")
        assert url == ""

    def test_none_rule_id_returns_empty(self):
        url = scan.generate_remediation_url("checkov", None)
        assert url == ""


class TestCountBySeverity:
    """Test severity counting."""

    def test_empty_findings(self):
        result = scan.count_by_severity([])
        assert result == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    def test_mixed_severities(self):
        findings = [
            {"severity": "CRITICAL"},
            {"severity": "HIGH"},
            {"severity": "HIGH"},
            {"severity": "LOW"},
        ]
        result = scan.count_by_severity(findings)
        assert result["CRITICAL"] == 1
        assert result["HIGH"] == 2
        assert result["MEDIUM"] == 0
        assert result["LOW"] == 1


class TestCountByTool:
    """Test tool counting."""

    def test_empty_findings(self):
        result = scan.count_by_tool([])
        assert result == {}

    def test_mixed_tools(self):
        findings = [
            {"tool": "trivy"},
            {"tool": "checkov"},
            {"tool": "trivy"},
        ]
        result = scan.count_by_tool(findings)
        assert result["trivy"] == 2
        assert result["checkov"] == 1


class TestBaselineHash:
    """Test baseline hash computation."""

    def test_hash_format(self):
        h = scan.compute_baseline_hash("AVD-AWS-0107", "main.tf")
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_deterministic(self):
        h1 = scan.compute_baseline_hash("CKV_AWS_19", "terraform/main.tf")
        h2 = scan.compute_baseline_hash("CKV_AWS_19", "terraform/main.tf")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        h1 = scan.compute_baseline_hash("CKV_AWS_19", "main.tf")
        h2 = scan.compute_baseline_hash("CKV_AWS_20", "main.tf")
        assert h1 != h2

    def test_hash_uses_pipe_separator(self):
        key = "AVD-AWS-0107|main.tf"
        expected = hashlib.sha256(key.encode("utf-8")).hexdigest()
        assert scan.compute_baseline_hash("AVD-AWS-0107", "main.tf") == expected


class TestFilterBySeverity:
    """Test severity filtering."""

    def test_filter_critical_only(self):
        findings = [
            {"severity": "CRITICAL", "rule_id": "1"},
            {"severity": "HIGH", "rule_id": "2"},
            {"severity": "LOW", "rule_id": "3"},
        ]
        result = scan.filter_by_severity(findings, ["CRITICAL"])
        assert len(result) == 1
        assert result[0]["rule_id"] == "1"

    def test_filter_multiple_severities(self):
        findings = [
            {"severity": "CRITICAL", "rule_id": "1"},
            {"severity": "HIGH", "rule_id": "2"},
            {"severity": "LOW", "rule_id": "3"},
        ]
        result = scan.filter_by_severity(findings, ["CRITICAL", "HIGH"])
        assert len(result) == 2

    def test_filter_empty_list(self):
        result = scan.filter_by_severity([], ["CRITICAL"])
        assert result == []


class TestCloudProviderDetection:
    """Test auto-detection of cloud provider."""

    def test_detect_aws_from_terraform(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text('provider "aws" {\n  region = "us-east-1"\n}\n')
            result = scan.detect_cloud_provider(tmpdir)
            assert result == "aws"

    def test_detect_azure_from_terraform(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text('provider "azurerm" {\n  features {}\n}\n')
            result = scan.detect_cloud_provider(tmpdir)
            assert result == "azure"

    def test_detect_gcp_from_terraform(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tf_file = Path(tmpdir) / "main.tf"
            tf_file.write_text('provider "google" {\n  project = "my-project"\n}\n')
            result = scan.detect_cloud_provider(tmpdir)
            assert result == "gcp"

    def test_no_provider_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scan.detect_cloud_provider(tmpdir)
            assert result is None


class TestBuildReport:
    """Test report building."""

    def test_report_structure(self):
        findings = [
            {
                "rule_id": "CKV_AWS_19",
                "tool": "checkov",
                "severity": "CRITICAL",
                "file": "main.tf",
                "line": 10,
                "message": "S3 missing encryption",
                "fixable": True,
                "fixed": False,
            }
        ]
        report = scan.build_report(
            findings,
            scan_dir=".",
            tools_executed=["checkov"],
            duration_ms=1234,
            auto_fix=False,
            fix_count=0,
        )

        assert report["schema_version"] == "1.0"
        assert "scan_id" in report
        assert "scan_timestamp" in report
        assert report["duration_ms"] == 1234
        assert report["tools_executed"] == ["checkov"]
        assert report["auto_fix_applied"] is False
        assert report["auto_fix_count"] == 0
        assert report["summary"]["total_findings"] == 1
        assert report["summary"]["by_severity"]["CRITICAL"] == 1
        assert report["summary"]["fixable"] == 1
        assert report["summary"]["unfixable"] == 0
        assert len(report["findings"]) == 1

    def test_empty_report(self):
        report = scan.build_report(
            findings=[],
            scan_dir=".",
            tools_executed=["trivy", "checkov"],
            duration_ms=500,
            auto_fix=False,
            fix_count=0,
        )
        assert report["summary"]["total_findings"] == 0
        assert report["findings"] == []


class TestRunCmd:
    """Test command execution wrapper."""

    @patch("scan.subprocess.run")
    def test_successful_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        rc, stdout, stderr = scan.run_cmd(["echo", "test"])
        assert rc == 0
        assert stdout == "output"

    @patch("scan.subprocess.run")
    def test_timeout_returns_exit_2(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd="test", timeout=300)
        rc, stdout, stderr = scan.run_cmd(["test"])
        assert rc == 2
        assert "timed out" in stderr.lower()

    @patch("scan.subprocess.run")
    def test_command_not_found_returns_exit_2(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        rc, stdout, stderr = scan.run_cmd(["nonexistent"])
        assert rc == 2
        assert "not found" in stderr.lower()


class TestLoadBaseline:
    """Test baseline loading."""

    def test_no_baseline_returns_empty_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scan.load_baseline(tmpdir)
            assert result == set()

    def test_load_valid_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_dir = Path(tmpdir) / ".scan-baseline"
            baseline_dir.mkdir()
            baseline_file = baseline_dir / "baseline.json"
            baseline_data = {
                "entries": [
                    {"hash": "abc123", "rule_id": "CKV_AWS_19", "file_path": "main.tf"},
                    {"hash": "def456", "rule_id": "AVD-AWS-0107", "file_path": "vpc.tf"},
                ]
            }
            baseline_file.write_text(json.dumps(baseline_data))
            result = scan.load_baseline(tmpdir)
            assert "abc123" in result
            assert "def456" in result
            assert len(result) == 2


class TestLoadSuppressions:
    """Test suppression loading."""

    def test_no_suppression_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scan.load_suppressions(tmpdir)
            assert result == {}

    def test_load_valid_suppressions_with_tool_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text(textwrap.dedent("""\
                trivy_suppressions:
                  - rule_id: AVD-AWS-0107
                    tool: trivy
                    reason: accepted risk
                checkov_suppressions:
                  - rule_id: CKV_AWS_19
                    tool: checkov
                    reason: not applicable
            """))
            result = scan.load_suppressions(tmpdir)
            assert ("AVD-AWS-0107", "trivy") in result
            assert result[("AVD-AWS-0107", "trivy")] == "accepted risk"
            assert ("CKV_AWS_19", "checkov") in result
            assert result[("CKV_AWS_19", "checkov")] == "not applicable"

    def test_load_suppressions_fallback_tool_from_section_key(self):
        """When tool field is omitted, tool should be derived from section key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text(textwrap.dedent("""\
                trivy_suppressions:
                  - rule_id: AVD-AWS-0107
                    reason: accepted risk
                checkov_suppressions:
                  - rule_id: CKV_AWS_19
                    reason: not applicable
                tflint_suppressions:
                  - rule_id: some_rule
                    reason: tflint suppressed
            """))
            result = scan.load_suppressions(tmpdir)
            # Tool derived from section key when tool field is absent
            assert ("AVD-AWS-0107", "trivy") in result
            assert ("CKV_AWS_19", "checkov") in result
            assert ("some_rule", "tflint") in result

    def test_load_suppressions_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scan.load_suppressions(tmpdir)
            assert result == {}

    def test_load_suppressions_import_error(self):
        """ImportError when yaml is missing should warn and return empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text("trivy_suppressions: []")
            with patch.dict(sys.modules, {"yaml": None}):
                # Force re-import to trigger ImportError
                import importlib
                with patch("builtins.__import__", side_effect=ImportError("No module named 'yaml'")):
                    result = scan.load_suppressions(tmpdir)
                    assert result == {}

    def test_load_suppressions_malformed_yaml(self):
        """Malformed YAML should warn and return empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text("!!invalid:\n  - [broken yaml\n")
            result = scan.load_suppressions(tmpdir)
            # Malformed YAML triggers an exception, should return {}
            assert result == {}

    def test_load_suppressions_non_dict_data(self):
        """YAML file containing a list instead of a dict should return empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text("- item1\n- item2\n")
            result = scan.load_suppressions(tmpdir)
            assert result == {}

    def test_load_suppressions_default_reason(self):
        """Entries without a reason field should default to 'suppressed'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text(textwrap.dedent("""\
                trivy_suppressions:
                  - rule_id: AVD-AWS-0107
                    tool: trivy
            """))
            result = scan.load_suppressions(tmpdir)
            assert result[("AVD-AWS-0107", "trivy")] == "suppressed"

    def test_load_suppressions_gitleaks_section(self):
        """Gitleaks suppressions section should be loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            supp_file = Path(tmpdir) / ".scan-suppressions.yaml"
            supp_file.write_text(textwrap.dedent("""\
                gitleaks_suppressions:
                  - rule_id: generic-api-key
                    reason: test key only
            """))
            result = scan.load_suppressions(tmpdir)
            assert ("generic-api-key", "gitleaks") in result


class TestFindingLineField:
    """Test that findings with line=0 do not include the 'line' key."""

    @patch("scan.run_cmd")
    def test_trivy_finding_line_zero_omitted(self, mock_run_cmd):
        """Trivy findings with StartLine=0 should not have a 'line' key."""
        trivy_output = json.dumps({
            "Results": [{
                "Target": "main.tf",
                "Misconfigurations": [{
                    "AVDID": "AVD-AWS-0107",
                    "Severity": "HIGH",
                    "Title": "Test finding",
                    "CauseMetadata": {"StartLine": 0},
                }],
            }]
        })
        mock_run_cmd.return_value = (0, trivy_output, "")
        findings, error = scan.run_trivy("/tmp/test")
        assert not error
        assert len(findings) == 1
        assert "line" not in findings[0]

    @patch("scan.run_cmd")
    def test_trivy_finding_line_positive_included(self, mock_run_cmd):
        """Trivy findings with a positive StartLine should include the 'line' key."""
        trivy_output = json.dumps({
            "Results": [{
                "Target": "main.tf",
                "Misconfigurations": [{
                    "AVDID": "AVD-AWS-0107",
                    "Severity": "HIGH",
                    "Title": "Test finding",
                    "CauseMetadata": {"StartLine": 42},
                }],
            }]
        })
        mock_run_cmd.return_value = (0, trivy_output, "")
        findings, error = scan.run_trivy("/tmp/test")
        assert not error
        assert len(findings) == 1
        assert findings[0]["line"] == 42

    @patch("scan.run_cmd")
    def test_checkov_finding_line_zero_omitted(self, mock_run_cmd):
        """Checkov findings with file_line_range=[0] should not have a 'line' key."""
        checkov_output = json.dumps({
            "results": {
                "failed_checks": [{
                    "check_id": "CKV_AWS_19",
                    "severity": "HIGH",
                    "check_name": "Test check",
                    "file_path": "main.tf",
                    "file_line_range": [0, 10],
                }]
            }
        })
        mock_run_cmd.return_value = (0, checkov_output, "")
        findings, error, fix_count = scan.run_checkov("/tmp/test")
        assert not error
        assert len(findings) == 1
        assert "line" not in findings[0]

    @patch("scan.run_cmd")
    def test_checkov_finding_line_positive_included(self, mock_run_cmd):
        """Checkov findings with a positive line should include the 'line' key."""
        checkov_output = json.dumps({
            "results": {
                "failed_checks": [{
                    "check_id": "CKV_AWS_19",
                    "severity": "HIGH",
                    "check_name": "Test check",
                    "file_path": "main.tf",
                    "file_line_range": [15, 20],
                }]
            }
        })
        mock_run_cmd.return_value = (0, checkov_output, "")
        findings, error, fix_count = scan.run_checkov("/tmp/test")
        assert not error
        assert len(findings) == 1
        assert findings[0]["line"] == 15


class TestBuildReportPathNormalization:
    """Test that build_report normalizes Windows paths to forward slashes."""

    def test_scan_directory_uses_forward_slashes(self):
        report = scan.build_report(
            findings=[],
            scan_dir="C:\\Users\\test\\terraform",
            tools_executed=["trivy"],
            duration_ms=100,
            auto_fix=False,
            fix_count=0,
        )
        assert "\\" not in report["scan_directory"]
        assert "C:/Users/test/terraform" == report["scan_directory"]
