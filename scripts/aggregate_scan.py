import json
import os
import hashlib
import sys
from datetime import datetime, timezone
from scan_policy import apply_exceptions, scanner_path
from scan_reports import load_report
from pathlib import Path

findings = []
health_errors = []
statuses = json.loads(os.environ.get("SCANNER_RESULTS", "{}"))
for job in ("setup", "scan-trivy", "scan-checkov", "scan-tflint"):
    if statuses.get(job, {}).get("result") != "success":
        health_errors.append(f"Required job {job} did not succeed")
enable_snyk = os.environ.get("ENABLE_SNYK") == "true"
if enable_snyk and statuses.get("scan-snyk", {}).get("result") != "success":
    health_errors.append("Required job scan-snyk did not succeed")

def report(path, tool):
    try:
        artifact_root = Path(os.environ.get("ARTIFACT_ROOT", "scan-artifacts"))
        return load_report(artifact_root / Path(path).relative_to("scan-artifacts"), tool)
    except (ValueError, OSError, TypeError) as exc:
        health_errors.append(f"{tool}: {exc}")
        return {"results": {}} if tool == "checkov" else {}

trivy_iac = report("scan-artifacts/trivy-results/trivy-iac-results.json", "trivy")
trivy_secrets = report("scan-artifacts/trivy-results/trivy-secrets-results.json", "trivy")
checkov_data = report("scan-artifacts/checkov-results/checkov-results.json", "checkov")
tflint_data = report("scan-artifacts/tflint-results/tflint-results.json", "tflint")
snyk_data = report("scan-artifacts/snyk-results/snyk-iac-results.json", "snyk") if enable_snyk else {}

# Parse Trivy IaC findings
trivy_results = trivy_iac.get("Results", [])
for result in trivy_results:
    for vuln in result.get("Misconfigurations", []):
        if vuln.get("Status") == "PASS":
            continue
        findings.append({
            "tool": "trivy",
            "rule_id": vuln.get("AVDID") or vuln.get("ID", ""),
            "severity": vuln.get("Severity", "UNKNOWN").upper(),
            "title": vuln.get("Title", ""),
            "message": vuln.get("Message", ""),
            "file": scanner_path(result.get("Target", ""), "trivy", ".", os.environ.get("TERRAFORM_DIRECTORY", ".")),
            "reported_file": result.get("Target", ""),
            "line": vuln.get("CauseMetadata", {}).get("StartLine", 0),
            "end_line": vuln.get("CauseMetadata", {}).get("EndLine", 0),
            "resource": vuln.get("CauseMetadata", {}).get("Resource", ""),
            "remediation": vuln.get("Resolution", ""),
            "remediation_url": vuln.get("PrimaryURL", ""),
            "detected_by": ["trivy"],
            "suppressed": False,
            "baseline": False
        })

# Parse Checkov findings
checkov_results = checkov_data if isinstance(checkov_data, list) else [checkov_data]
for result in checkov_results:
    # Checkov nests the check lists under "results".
    checks = result.get("results") or {}
    pending = checks.get("failed_checks", [])
    if os.environ.get("ALLOW_INLINE_CHECKOV_SKIPS") != "true":
        pending = pending + checks.get("skipped_checks", [])
    for check in pending:
        check_id = check.get("check_id", "")
        remediation_url = f"https://docs.checkov.io/docs/{check_id}" if check_id.startswith("CKV_") else None
        severity = check.get("severity", "HIGH")
        if severity:
            severity = severity.upper()
        else:
            severity = "HIGH"
        findings.append({
            "tool": "checkov",
            "rule_id": check_id,
            "severity": severity,
            "title": check.get("check_id", ""),
            "message": check.get("check_result", {}).get("message", check.get("name", "")),
            "file": scanner_path(check.get("file_path", ""), "checkov", ".", os.environ.get("TERRAFORM_DIRECTORY", ".")),
            "reported_file": check.get("file_path", ""),
            "line": check.get("file_line_range", [0])[0] if check.get("file_line_range") else 0,
            "end_line": (check.get("file_line_range") or [0])[-1],
            "resource": check.get("resource", ""),
            "remediation": check.get("guideline", ""),
            "remediation_url": remediation_url,
            "detected_by": ["checkov"],
            "suppressed": False,
            "baseline": False
        })

# Parse TFLint findings
tflint_severity_map = {"error": "HIGH", "warning": "MEDIUM", "notice": "LOW"}
for issue in tflint_data.get("issues", []):
    rule_name = issue.get("rule", {}).get("name", "")
    tflint_sev = issue.get("rule", {}).get("severity", "warning")
    findings.append({
        "tool": "tflint",
        "rule_id": rule_name,
        "severity": tflint_severity_map.get(tflint_sev, "MEDIUM"),
        "title": rule_name,
        "message": issue.get("message", ""),
        "file": issue.get("range", {}).get("filename", ""),
        "reported_file": issue.get("reported_file", issue.get("range", {}).get("filename", "")),
        "line": issue.get("range", {}).get("start", {}).get("line", 0),
        "end_line": issue.get("range", {}).get("end", {}).get("line", 0),
        "resource": "",
        "remediation": "",
        "remediation_url": f"https://github.com/terraform-linters/tflint/blob/master/docs/rules/{rule_name}.md" if rule_name.startswith("terraform_") else None,
        "detected_by": ["tflint"],
        "suppressed": False,
        "baseline": False
    })

# Parse Snyk IaC findings
snyk_severity_map = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
for issue in [dict(issue, targetFile=issue.get("targetFile") or doc.get("targetFile", ""))
              for doc in (snyk_data if isinstance(snyk_data, list) else [snyk_data])
              for issue in doc.get("infrastructureAsCodeIssues", [])]:
    snyk_sev = issue.get("severity", "medium").lower()
    target_file = scanner_path(issue.get("targetFile", ""), "snyk", ".", os.environ.get("TERRAFORM_DIRECTORY", "."))
    issue_id = issue.get("id") or issue.get("publicId", "")
    findings.append({
        "tool": "snyk",
        "rule_id": issue_id,
        "severity": snyk_severity_map.get(snyk_sev, "MEDIUM"),
        "title": issue.get("title", ""),
        "message": issue.get("iacDescription", {}).get("issue", issue.get("title", "")),
        "file": target_file,
        "line": issue.get("lineNumber", 0),
        "resource": issue.get("msg", ""),
        "reported_file": issue.get("targetFile", ""),
        "remediation": issue.get("iacDescription", {}).get("resolve", ""),
        "remediation_url": issue.get("documentation", None),
        "detected_by": ["snyk"],
        "suppressed": False,
        "baseline": False
    })

# Secret findings participate in the same gate as IaC results.
for result in trivy_secrets.get("Results", []):
    for secret in result.get("Secrets", []):
        findings.append(dict(tool="trivy", rule_id=secret["RuleID"],
                             severity=secret["Severity"].upper(), title=secret.get("Title", "Secret"),
                             message="Secret detected", file=result["Target"],
                             line=secret.get("StartLine", 0), end_line=secret.get("EndLine", 0),
                             resource="", detected_by=["trivy"]))

try:
    apply_exceptions(findings, ".", os.environ.get("POLICY_ROOT", ".scan-policy"),
                     suppressions=os.environ.get("APPLY_SUPPRESSIONS") == "true",
                     baseline=os.environ.get("APPLY_BASELINE") == "true",
                     allow_legacy=os.environ.get("ALLOW_LEGACY_EXCEPTIONS") == "true")
except (ValueError, OSError, TypeError) as exc:
    health_errors.append(str(exc))
    for finding in findings:
        finding["suppressed"] = finding["baseline"] = False
suppressions_applied = sum(bool(f.get("suppressed")) for f in findings)
baseline_filtered = sum(bool(f.get("baseline")) for f in findings)

# Filter active findings (not suppressed AND not baselined)
active = [f for f in findings if not f["suppressed"] and not f["baseline"]]

# Count by severity
severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
for f in active:
    sev = f["severity"]
    if sev in severity_counts:
        severity_counts[sev] += 1

total = len(active)
critical = severity_counts["CRITICAL"]
high = severity_counts["HIGH"]

fail_on = os.environ.get("FAIL_ON_FINDINGS", "") == "true"
# Gate on the BLOCKING severities (CRITICAL + HIGH) only — lint / medium / low
# findings are reported (SARIF + PR comment) but do NOT fail the check, matching
# the `severity: CRITICAL,HIGH` the scanners are configured with.
blocking = critical + high
passed = "true" if not health_errors and (blocking == 0 or not fail_on) else "false"

# Write aggregated results
output = {
    "scan_passed": passed == "true",
    "scan_complete": not health_errors,
    "health_errors": health_errors,
    "total_findings": total,
    "by_severity": severity_counts,
    "suppressions_applied": suppressions_applied,
    "baseline_filtered": baseline_filtered,
    "findings": findings
}
os.makedirs(".scan-results", exist_ok=True)
with open(".scan-results/aggregated.json", "w") as f:
    json.dump(output, f, indent=2)

# Write outputs
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"findings-count={total}\n")
    f.write(f"critical-count={critical}\n")
    f.write(f"high-count={high}\n")
    f.write(f"scan-passed={passed}\n")

print(f"Total active findings: {total}")
print(f"  CRITICAL: {critical}")
print(f"  HIGH: {high}")
print(f"  MEDIUM: {severity_counts['MEDIUM']}")
print(f"  LOW: {severity_counts['LOW']}")
print(f"  Suppressed: {suppressions_applied}")
print(f"  Baselined: {baseline_filtered}")

for error in health_errors:
    print("Scan incomplete: " + error, file=sys.stderr)

if passed == "false":
    sys.exit(1)
