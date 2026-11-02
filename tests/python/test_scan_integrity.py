"""Gate, exception and hook contracts exercised against the shipped entry points."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import date, timedelta

import pytest
import yaml
import scan
import validate_suppressions as validator

ROOT = Path(__file__).resolve().parents[2]


def registry(**changes):
    entry = dict(rule_id="CKV_AWS_19", tool="checkov", reason="Reviewed test fixture",
                 owner="security@example.com", approved_by="security@example.com",
                 severity="HIGH", approved_date=str(date.today()),
                 expires_date=str(date.today() + timedelta(days=30)),
                 fingerprint="v1:" + "a" * 64)
    entry.update(changes.pop("entry", {}))
    return dict(schema_version="2.0", checkov_suppressions=[entry], **changes)


def write_registry(tmp_path, data):
    path = tmp_path / ".scan-suppressions.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_approval_floor_is_independent_of_registry_settings(tmp_path):
    data = registry(settings={"require_security_approval": []}, entry={"approved_by": ""})
    result = validator.validate_file(write_registry(tmp_path, data))
    assert any(e["rule"] == "V-007" for e in result.errors)


def test_legacy_registry_is_rejected_by_default(tmp_path):
    data = registry()
    data["schema_version"] = "1.0"
    del data["checkov_suppressions"][0]["fingerprint"]
    assert validator.validate_file(write_registry(tmp_path, data)).has_errors


def test_distinct_occurrences_have_distinct_keys():
    assert hasattr(scan, "occurrence_fingerprint")


def test_exact_exception_consumes_one_occurrence(tmp_path):
    from scan_policy import apply_exceptions, occurrence_fingerprint
    (tmp_path / 'main.tf').write_text('resource "sample" "one" {}\nresource "sample" "two" {}\n')
    first = dict(tool="checkov", rule_id="CKV_AWS_19", severity="HIGH", file="main.tf", line=1, resource="sample.one")
    second = dict(first, line=2, resource="sample.two")
    fp = occurrence_fingerprint(first, tmp_path)
    assert fp != occurrence_fingerprint(second, tmp_path)
    write_registry(tmp_path, registry(entry={"fingerprint": fp}))
    findings = [dict(first), dict(first), second]
    apply_exceptions(findings, tmp_path, tmp_path, baseline=False)
    assert [f["suppressed"] for f in findings] == [True, False, False]
    (tmp_path / 'main.tf').write_text('resource "sample" "changed" {}\n')
    assert fp != occurrence_fingerprint(first, tmp_path)


def test_baseline_consumes_only_one_exact_occurrence(tmp_path):
    from scan_policy import apply_exceptions, occurrence_fingerprint
    (tmp_path / 'main.tf').write_text('# fixture\n')
    finding = dict(tool="trivy", rule_id="AVD-AWS-0001", severity="HIGH", file="main.tf", line=1)
    directory = tmp_path / '.scan-baseline'
    directory.mkdir()
    (directory / 'baseline.json').write_text(json.dumps(dict(schema_version="2.0", entries=[dict(fingerprint=occurrence_fingerprint(finding, tmp_path))])))
    findings = [dict(finding), dict(finding), dict(finding, tool="checkov")]
    apply_exceptions(findings, tmp_path, tmp_path, suppressions=False)
    assert [f["baseline"] for f in findings] == [True, False, False]


@pytest.mark.parametrize('changes', [dict(expires_date=str(date.today()-timedelta(days=1))),
                                    dict(approved_by=''), dict(severity=None), dict(fingerprint='invalid')])
def test_registry_rejects_incomplete_or_inactive_approval(tmp_path, changes):
    from scan_policy import load_suppression_entries
    with pytest.raises(ValueError):
        load_suppression_entries(write_registry(tmp_path, registry(entry=changes)))


def test_legacy_registry_requires_explicit_opt_in(tmp_path):
    from scan_policy import load_suppression_entries
    data = registry()
    data['schema_version'] = '1.0'
    del data['checkov_suppressions'][0]['fingerprint']
    path = write_registry(tmp_path, data)
    with pytest.raises(ValueError):
        load_suppression_entries(path)
    assert len(load_suppression_entries(path, allow_legacy=True)) == 1


@pytest.mark.parametrize('tool,document', [('trivy', {}), ('trivy', {'Results': 'invalid'}),
    ('checkov', {}), ('checkov', {'results': {'failed_checks': [], 'parsing_errors': ['error']}}),
    ('tflint', {'issues': [], 'errors': [{'message': 'error'}]}), ('tflint', {'issues': None}),
    ('snyk', {'error': 'error'}), ('snyk', {})])
def test_report_health_is_required(tool, document):
    from scan_reports import validate_report
    with pytest.raises((ValueError, TypeError)):
        validate_report(document, tool)


def test_inline_skips_remain_visible_by_default():
    import checkov_consumer_options as options
    data = {'runs': [{'results': [{'ruleId': 'CKV_AWS_19', 'suppressions': [{'kind': 'inSource'}]}]}]}
    assert options.filter_sarif(data) == 0
    assert data['runs'][0]['results'][0]['level'] == 'error'
    assert 'suppressions' not in data['runs'][0]['results'][0]


def test_source_policy_is_materialized_from_base(tmp_path, monkeypatch):
    import prepare_scan_policy
    monkeypatch.chdir(tmp_path)
    subprocess.run(['git', 'init', '-q'], check=True)
    (tmp_path / '.semgrepignore').write_text('approved/\n')
    subprocess.run(['git', 'add', '--', '.semgrepignore'], check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'test: policy fixture'], check=True)
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    (tmp_path / '.semgrepignore').write_text('other/\n')
    (tmp_path / 'trivy.yaml').write_text('severity: []\n')
    subprocess.run(['git', 'add', '--', '.semgrepignore', 'trivy.yaml'], check=True)
    prepare_scan_policy.prepare(base)
    assert (tmp_path / '.semgrepignore').read_text() == 'approved/\n'
    assert not (tmp_path / 'trivy.yaml').exists()


def test_aggregate_requires_healthy_reports(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-scan.yml").read_text())
    step = next(s for s in workflow["jobs"]["aggregate"]["steps"] if s.get("id") == "aggregate")
    script = step["run"]
    if "PYTHON_SCRIPT" in script:
        script = script.split("'PYTHON_SCRIPT'", 1)[1].rsplit("PYTHON_SCRIPT", 1)[0]
        command = [sys.executable, "-c", script]
    else:
        command = [sys.executable, str(ROOT / "scripts/aggregate_scan.py")]
    env = dict(os.environ, GITHUB_OUTPUT=str(tmp_path / "out"), FAIL_ON_FINDINGS="false")
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode != 0


@pytest.fixture
def aggregate_run(tmp_path):
    documents = {
        'trivy-results/trivy-iac-results.json': {'SchemaVersion': 2, 'Results': []},
        'trivy-results/trivy-secrets-results.json': {'SchemaVersion': 2, 'Results': []},
        'checkov-results/checkov-results.json': {'results': {'failed_checks': [], 'skipped_checks': []}},
        'tflint-results/tflint-results.json': {'issues': [], 'errors': []},
    }
    for name, data in documents.items():
        path = tmp_path / 'scan-artifacts' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    (tmp_path / '.scan-policy').mkdir()
    statuses = {name: {'result': 'success'} for name in ('setup', 'scan-trivy', 'scan-checkov', 'scan-tflint')}
    def run(**overrides):
        env = dict(os.environ, SCANNER_RESULTS=json.dumps(statuses), GITHUB_OUTPUT=str(tmp_path / 'out'),
                   FAIL_ON_FINDINGS='false', APPLY_SUPPRESSIONS='true', APPLY_BASELINE='true')
        env.update(overrides)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/aggregate_scan.py')], cwd=tmp_path,
                                env=env, capture_output=True, text=True)
        report = json.loads((tmp_path / '.scan-results/aggregated.json').read_text())
        return result, report
    return run, statuses


def test_healthy_clean_aggregate_passes(aggregate_run):
    result, report = aggregate_run[0]()
    assert result.returncode == 0, result.stderr
    assert report['health_errors'] == []


@pytest.mark.parametrize('job', ['setup', 'scan-trivy', 'scan-checkov', 'scan-tflint'])
def test_failed_job_cannot_pass_report_only_gate(aggregate_run, job):
    run, statuses = aggregate_run
    statuses[job]['result'] = 'failure'
    result, report = run()
    assert result.returncode == 1
    assert report['health_errors']


@pytest.mark.parametrize('contents', ['{', '{}', 'null', '{"issues":[],"errors":[{}]}'])
def test_invalid_report_cannot_pass_report_only_gate(tmp_path, aggregate_run, contents):
    (tmp_path / 'scan-artifacts/tflint-results/tflint-results.json').write_text(contents)
    result, report = aggregate_run[0]()
    assert result.returncode == 1
    assert report['health_errors']


def test_source_registry_does_not_override_base_registry(tmp_path, aggregate_run):
    (tmp_path / 'main.tf').write_text('# fixture\n')
    report_path = tmp_path / 'scan-artifacts/checkov-results/checkov-results.json'
    report_path.write_text(json.dumps({'results': {'failed_checks': [dict(check_id='CKV_AWS_19', severity='HIGH',
        file_path='/main.tf', file_line_range=[1,1], resource='sample.one')]}}))
    from scan_policy import occurrence_fingerprint
    fp = occurrence_fingerprint(dict(tool='checkov', rule_id='CKV_AWS_19', file='main.tf', line=1, resource='sample.one'), tmp_path)
    write_registry(tmp_path, registry(entry={'fingerprint': fp}))
    result, report = aggregate_run[0](FAIL_ON_FINDINGS='true')
    assert result.returncode == 1
    assert report['suppressions_applied'] == 0
    write_registry(tmp_path / '.scan-policy', registry(entry={'fingerprint': fp}))
    result, report = aggregate_run[0](FAIL_ON_FINDINGS='true')
    assert result.returncode == 0, result.stderr
    assert report['suppressions_applied'] == 1


def test_secret_findings_are_included_in_aggregate_gate(tmp_path, aggregate_run):
    path = tmp_path / 'scan-artifacts/trivy-results/trivy-secrets-results.json'
    path.write_text(json.dumps({'Results': [{'Target':'sample.txt', 'Secrets': [
        {'RuleID':'sample-key', 'Severity':'HIGH', 'StartLine':1}]}]}))
    result, report = aggregate_run[0](FAIL_ON_FINDINGS='true')
    assert result.returncode == 1
    assert report['by_severity']['HIGH'] == 1


def test_language_policy_checkout_uses_base():
    wf = yaml.safe_load((ROOT / ".github/workflows/code-security-scan.yml").read_text())
    checkout = wf["jobs"]["detect"]["steps"][0]
    assert "github.event.pull_request.base.sha" in checkout.get("with", {}).get("ref", "")












def test_hook_selects_authoritative_registry():
    for suffix in ("sh", "ps1"):
        text = (ROOT / f"hooks/validate-suppressions.{suffix}").read_text()
        assert "suppressions.file" in text
        assert "SCAN_CONFIG_DIR" not in text


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_hook_validates_configured_registry_even_with_setup_copy(tmp_path, shell):
    bundle = tmp_path / 'bundle'
    for name in ['hooks/validate-suppressions.sh', 'hooks/validate-suppressions.ps1',
                 'hooks/validate-suppressions.py', 'hooks/lib/common.sh', 'hooks/lib/common.ps1',
                 'scripts/scan_policy.py', 'scripts/validate-suppressions.py']:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / name).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    folder = tmp_path / 'policy'
    folder.mkdir()
    active = folder / 'registry.yaml'
    active.write_text(yaml.safe_dump(registry(entry={'approved_by': ''})))
    (tmp_path / 'scan-config.yaml').write_text(yaml.safe_dump({'suppressions': {'file': 'policy/registry.yaml'}}))
    stale = tmp_path / '.scanning/configs'
    stale.mkdir(parents=True)
    write_registry(stale, {'schema_version': '2.0', 'checkov_suppressions': []})
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    args = [executable] + (['-NoProfile', '-File'] if shell == 'ps1' else [])
    args += [(bundle / f'hooks/validate-suppressions.{shell}').as_posix()]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'V-007' in result.stdout + result.stderr




