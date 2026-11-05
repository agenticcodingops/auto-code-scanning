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


def test_legacy_baseline_can_match_the_original_scanner_path(tmp_path):
    from scan_policy import apply_exceptions
    import hashlib
    folder = tmp_path / '.scan-baseline'
    folder.mkdir()
    old_hash = hashlib.sha256(b'CKV_AWS_19|/main.tf').hexdigest()
    (folder / 'baseline.json').write_text(json.dumps(dict(schema_version='1.0', entries=[dict(hash=old_hash)])))
    finding = dict(tool='checkov', rule_id='CKV_AWS_19', file='module/main.tf', reported_file='/main.tf', line=1, severity='HIGH')
    apply_exceptions([finding], tmp_path, tmp_path, suppressions=False, allow_legacy=True)
    assert finding['baseline']


def test_scoped_baseline_uses_each_scanner_directory(tmp_path):
    from finalize_baseline import finalize
    (tmp_path / 'main.tf').write_text('# root\n')
    entries = []
    for name in ['network', 'storage']:
        directory = tmp_path / 'terraform' / name
        directory.mkdir(parents=True)
        (directory / 'main.tf').write_text('# module\n')
        entries.append(dict(file='/main.tf', tool='checkov', rule_id='CKV_AWS_19',
                            line=1, resource='sample.one', scan_directory=f'terraform/{name}'))
    data = finalize(dict(scan_directory='.', entries=entries), tmp_path)
    assert [e['file'] for e in data['entries']] == ['terraform/network/main.tf', 'terraform/storage/main.tf']
    assert len({e['fingerprint'] for e in data['entries']}) == 2


def test_relative_scanner_paths_use_selected_module(tmp_path):
    from scan_policy import scanner_path
    (tmp_path / 'main.tf').write_text('# root\n')
    folder = tmp_path / 'module'
    folder.mkdir()
    (folder / 'main.tf').write_text('# module\n')
    assert scanner_path('main.tf', 'trivy', tmp_path, 'module') == 'module/main.tf'
    assert scanner_path('module/main.tf', 'trivy', tmp_path, 'module') == 'module/main.tf'


@pytest.mark.parametrize('filename', ['main.tf', 'module/main.tf'])
def test_tflint_merge_preserves_repository_paths(tmp_path, monkeypatch, filename):
    workflow = yaml.safe_load((ROOT / '.github/workflows/reusable-scan.yml').read_text())
    step = next(s for s in workflow['jobs']['scan-tflint']['steps'] if s.get('id') == 'tflint')
    program = step['run'].split('python3 -c "\n', 1)[1].split('\n"', 1)[0]
    folder = tmp_path / 'module'
    folder.mkdir()
    (folder / 'main.tf').write_text('# fixture\n')
    report = tmp_path / 'tflint-dir-test.json'
    report.write_text(json.dumps({'issues': [dict(rule=dict(name='sample', severity='warning'),
        range=dict(filename=filename, start=dict(line=1), end=dict(line=1)))], 'errors': []}))
    (tmp_path / 'tflint-dir-test.json.directory').write_text(str(folder))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_WORKSPACE', str(tmp_path))
    exec(program, {})  # shipped workflow code, exercised against report fixtures
    result = json.loads((tmp_path / 'tflint-results.json').read_text())
    assert result['issues'][0]['range']['filename'] == 'module/main.tf'


@pytest.mark.skipif(os.name == 'nt', reason='Windows does not permit literal backslashes in filenames')
def test_literal_backslash_is_a_distinct_posix_occurrence(tmp_path):
    from scan_policy import occurrence_fingerprint
    (tmp_path / 'module').mkdir()
    (tmp_path / 'module/main.tf').write_text('# fixture\n')
    (tmp_path / 'module\\main.tf').write_text('# fixture\n')
    finding = dict(tool='trivy', rule_id='AVD-AWS-0001', line=1, file='module/main.tf')
    assert occurrence_fingerprint(finding, tmp_path) != occurrence_fingerprint(dict(finding, file='module\\main.tf'), tmp_path)


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


@pytest.mark.parametrize('tool,document', [
    ('checkov', {'results': {'failed_checks': [{'check_id': 1, 'file_path': 'main.tf'}]}}),
    ('checkov', {'results': {'failed_checks': [{'check_id': 'CKV_AWS_19', 'file_path': 'main.tf', 'file_line_range': '12'}]}}),
    ('trivy', {'Results': [{'Target': 'main.tf', 'Misconfigurations': [{'ID': 1, 'Severity': 'HIGH'}]}]}),
    ('tflint', {'issues': [{'rule': {'name': 'sample'}, 'range': {'filename': 1}}]})])
def test_invalid_finding_identity_is_a_report_error(tool, document):
    from scan_reports import validate_report
    with pytest.raises(ValueError):
        validate_report(document, tool)


def test_checkov_empty_input_summary_is_a_valid_report():
    from scan_reports import validate_report
    data = dict(passed=0, failed=0, skipped=0, parsing_errors=0, resource_count=0, checkov_version='3.3.19')
    assert validate_report(data, 'checkov')['results']['failed_checks'] == []


def test_checkov_nonempty_summary_without_findings_is_incomplete():
    from scan_reports import validate_report
    data = dict(passed=0, failed=1, skipped=0, parsing_errors=0, resource_count=1, checkov_version='3.3.19')
    with pytest.raises(ValueError):
        validate_report(data, 'checkov')


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


def test_secret_configuration_is_trusted_policy():
    from prepare_scan_policy import POLICY_NAMES
    assert 'trivy-secret.yaml' in POLICY_NAMES


def test_actual_severity_rejects_blank_approver(tmp_path):
    from scan_policy import apply_exceptions, occurrence_fingerprint
    (tmp_path / 'main.tf').write_text('# fixture\n')
    finding = dict(tool='checkov', rule_id='CKV_AWS_19', file='main.tf', line=1, severity='HIGH')
    write_registry(tmp_path, registry(entry=dict(severity='MEDIUM', approved_by=' ', fingerprint=occurrence_fingerprint(finding, tmp_path))))
    apply_exceptions([finding], tmp_path, tmp_path, baseline=False)
    assert not finding['suppressed']


def test_null_registry_section_is_empty(tmp_path):
    from scan_policy import load_suppression_entries
    path = write_registry(tmp_path, dict(schema_version='2.0', trivy_suppressions=None))
    assert load_suppression_entries(path) == []


def test_completed_optional_scanner_report_can_have_findings_status():
    from scan_reports import validate_report
    data = {'ok': False, 'targetFile': 'main.tf', 'infrastructureAsCodeIssues': []}
    assert validate_report(data, 'snyk') is data


def test_optional_scanner_document_path_survives_normalization(tmp_path, monkeypatch):
    folder = tmp_path / 'module'
    folder.mkdir()
    (folder / 'main.tf').write_text('# fixture\n')
    (tmp_path / 'scan-config.yaml').write_text('{}')
    monkeypatch.setenv('SNYK_TOKEN', 'fixture')
    monkeypatch.setattr(scan.shutil, 'which', lambda name: name)
    document = dict(ok=False, targetFile='main.tf', infrastructureAsCodeIssues=[
        dict(id='SNYK-CC-0001', publicId='SNYK-CC-ALIAS', severity='high', lineNumber=1,
             msg='sample.one', resolve='Remediation guidance')])
    monkeypatch.setattr(scan, 'run_cmd', lambda *args, **kwargs: (1, json.dumps(document), ''))
    findings, error = scan.run_snyk(folder)
    assert not error
    assert findings[0]['file'] == 'module/main.tf'
    assert findings[0]['resource'] == 'sample.one'
    assert findings[0]['rule_id'] == 'SNYK-CC-0001'


def test_secret_rule_can_receive_exact_approval(tmp_path):
    data = registry()
    entry = data.pop('checkov_suppressions')[0]
    entry.update(tool='trivy', rule_id='aws-access-key-id')
    data['trivy_suppressions'] = [entry]
    assert not validator.validate_file(write_registry(tmp_path, data)).has_errors


def test_custom_expiry_warning_window_is_preserved(tmp_path):
    data = registry(entry=dict(ticket='SEC-123', expires_date=str(date.today()+timedelta(days=45))),
                    settings=dict(max_expiry_days=180, require_security_approval=['CRITICAL','HIGH'], review_frequency_days=90))
    path = write_registry(tmp_path, data)
    assert not validator.validate_file(path, strict=True, ci_mode=True, warning_days=30).has_errors
    assert validator.validate_file(path, strict=True, ci_mode=True, warning_days=60).has_errors


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


def test_app_policy_helper_is_packaged_from_the_shared_contract():
    wf = yaml.safe_load((ROOT / '.github/workflows/code-security-scan.yml').read_text())
    step = next(s for s in wf['jobs']['detect']['steps'] if s.get('name') == 'Package workflow policy helper')
    embedded = step['run'].split("<<'POLICY_HELPER'\n", 1)[1].rsplit('POLICY_HELPER', 1)[0]
    assert embedded == (ROOT / 'scripts/prepare_scan_policy.py').read_text()


def test_app_helper_artifacts_are_unique_per_call(tmp_path):
    wf = yaml.safe_load((ROOT / '.github/workflows/code-security-scan.yml').read_text())
    detect = wf['jobs']['detect']
    step = next(s for s in detect['steps'] if s.get('id') == 'helper-name')
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash unavailable')
    output = tmp_path / 'output'
    for _ in range(2):
        result = subprocess.run([bash, '-c', step['run']], env=dict(os.environ, GITHUB_OUTPUT=str(output)), capture_output=True)
        assert result.returncode == 0, result.stderr
    names = output.read_text().splitlines()
    assert len(set(names)) == 2
    for job in ('semgrep', 'secrets'):
        download = next(s for s in wf['jobs'][job]['steps'] if s.get('name') == 'Download workflow policy helper')
        assert download['with']['name'] == '${{ needs.detect.outputs.policy-helper-artifact }}'


def test_upload_delivery_tolerance_is_an_explicit_opt_in():
    wf = yaml.safe_load((ROOT / '.github/workflows/reusable-scan.yml').read_text())
    inputs = (wf.get('on') or wf[True])['workflow_call']['inputs']
    assert inputs['allow-sarif-upload-errors']['default'] is False
    uploads = [s for s in wf['jobs']['sarif-upload']['steps'] if s.get('id', '').startswith('upload-')]
    assert len(uploads) == 4
    assert all(s['continue-on-error'] == '${{ inputs.allow-sarif-upload-errors }}' for s in uploads)


@pytest.mark.parametrize('complete,passed,expected', [(False,False,'Scan incomplete'), (True,False,'security findings detected'), (True,True,'Scan gate passed')])
def test_comment_reports_the_aggregate_verdict(tmp_path, complete, passed, expected):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    wf = yaml.safe_load((ROOT / '.github/workflows/reusable-scan.yml').read_text())
    script = next(s['with']['script'] for s in wf['jobs']['pr-comment']['steps'] if 'github-script' in s.get('uses',''))
    folder = tmp_path / 'aggregated'
    folder.mkdir()
    (folder / 'aggregated.json').write_text(json.dumps(dict(scan_complete=complete, scan_passed=passed,
        total_findings=0, by_severity={}, findings=[])))
    harness = "const github={rest:{issues:{createComment:async x=>console.log(x.body)}}}; const context={issue:{number:1},repo:{owner:'test',repo:'test'}}; (async()=>{" + script + "})();"
    result = subprocess.run([node, '-e', harness], cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    if not complete:
        assert 'Scan gate passed' not in result.stdout












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
                 'hooks/lib/tool-paths.sh', 'hooks/lib/tool-paths.ps1',
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




