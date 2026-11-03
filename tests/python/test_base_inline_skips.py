"""Exercise trusted inline skips through both shipped scan entry points."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import scan

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '''resource "azurerm_mysql_server" "example" {
  #checkov:skip=CKV_AZURE_53:Reviewed exception
  name = "storage"
}
'''


@pytest.mark.parametrize('case,expected', [
    ('unchanged', 0), ('added', 1), ('changed-id', 1), ('changed-resource', 1),
    ('changed-reason', 1), ('deleted', 1), ('unrelated-edit', 0),
    ('moved-file', 1), ('string-in-base', 1), ('other-resource', 1), ('extra-reason', 1),
])
@pytest.mark.parametrize('entrypoint', ['local', 'aggregate'])
def test_inline_skip_requires_same_base_approval(tmp_path, monkeypatch, case, expected, entrypoint):
    base = tmp_path / '.scan-policy'
    base.mkdir()
    source, trusted = SOURCE, SOURCE
    filename = 'infra/main.tf'
    skipped = True
    if case == 'added':
        trusted = SOURCE.replace('  #checkov:skip=CKV_AZURE_53:Reviewed exception\n', '')
    elif case == 'changed-id':
        trusted = SOURCE.replace('CKV_AZURE_53', 'CKV_AZURE_110')
    elif case == 'changed-resource':
        trusted = SOURCE.replace('"example"', '"previous"')
    elif case == 'changed-reason':
        source = SOURCE.replace('Reviewed exception', 'New justification')
    elif case == 'deleted':
        source = SOURCE.replace('  #checkov:skip=CKV_AZURE_53:Reviewed exception\n', '')
        skipped = False
    elif case == 'unrelated-edit':
        source = '# New heading\n' + SOURCE.replace('"storage"', '"renamed"')
    elif case == 'moved-file':
        filename = 'infra/moved.tf'
    elif case == 'string-in-base':
        trusted = SOURCE.replace('  #checkov:', '  description = "#checkov:').replace('Reviewed exception\n', 'Reviewed exception"\n')
    elif case == 'other-resource':
        trusted = SOURCE.replace('"example"', '"other"') + 'resource "azurerm_mysql_server" "example" {}\n'
    elif case == 'extra-reason':
        source = SOURCE.replace('  name =', '  #checkov:skip=CKV_AZURE_53:New justification\n  name =')
    (base / 'infra').mkdir()
    (base / 'infra/main.tf').write_text(trusted, encoding='utf-8')
    (tmp_path / 'infra').mkdir()
    (tmp_path / filename).write_text(source, encoding='utf-8')
    check = dict(check_id='CKV_AZURE_53', severity='HIGH', file_path='/' + Path(filename).name,
                 file_line_range=[2 if case == 'unrelated-edit' else 1, len(source.splitlines())],
                 resource='azurerm_mysql_server.example')
    document = {'results': {'failed_checks': [] if skipped else [check],
                            'skipped_checks': [check] if skipped else []}}
    monkeypatch.chdir(tmp_path)
    if entrypoint == 'local':
        monkeypatch.setattr(scan, 'run_cmd', lambda *a, **kw: (0, json.dumps(document), ''))
        monkeypatch.setattr(scan.shutil, 'which', lambda name: name)
        monkeypatch.setattr(sys, 'argv', ['scan.py', 'infra', '--tools', 'checkov',
            '--policy-root', str(base), '--format', 'json', '--output-file', 'result.json'])
        (tmp_path / 'scan-config.yaml').write_text('{}')
        with pytest.raises(SystemExit) as exited:
            scan.main()
        code = exited.value.code
        report = json.loads((tmp_path / 'result.json').read_text())
        assert report['summary']['total_findings'] == expected
    else:
        documents = {
            'checkov-results/checkov-results.json': document,
            'trivy-results/trivy-iac-results.json': {'SchemaVersion': 2, 'Results': []},
            'trivy-results/trivy-secrets-results.json': {'SchemaVersion': 2, 'Results': []},
            'tflint-results/tflint-results.json': {'issues': [], 'errors': []},
        }
        for name, data in documents.items():
            target = tmp_path / 'scan-artifacts' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data))
        statuses = {name: {'result': 'success'} for name in ('setup', 'scan-checkov', 'scan-trivy', 'scan-tflint')}
        env = dict(os.environ, SCANNER_RESULTS=json.dumps(statuses), POLICY_ROOT=str(base),
                   TERRAFORM_DIRECTORY='infra', FAIL_ON_FINDINGS='true', GITHUB_OUTPUT=str(tmp_path / 'out'),
                   ALLOW_INLINE_CHECKOV_SKIPS='false', APPLY_SUPPRESSIONS='true', APPLY_BASELINE='true')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/aggregate_scan.py')],
                                env=env, capture_output=True, text=True)
        code = result.returncode
        report = json.loads((tmp_path / '.scan-results/aggregated.json').read_text())
        assert report['scan_complete'], result.stderr
        assert report['total_findings'] == expected
    assert code == expected


def test_local_default_reads_merge_base_not_pr_tip(tmp_path):
    from scan_policy import checkov_checks
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    path = tmp_path / 'main.tf'
    path.write_text(SOURCE)
    git('add', '.')
    git('commit', '-m', 'base')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    path.write_text(SOURCE.replace('Reviewed exception', 'New justification'))
    git('add', '.')
    git('commit', '-m', 'changed skip')
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', resource='azurerm_mysql_server.example')
    results = dict(failed_checks=[], skipped_checks=[check])
    assert checkov_checks(results, tmp_path) == [check]
    path.write_text('# line shift\n' + SOURCE)
    assert checkov_checks(results, tmp_path) == []


def test_local_requests_skipped_records_and_keeps_unrated_skips_blocking(tmp_path, monkeypatch):
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', resource='azurerm_mysql_server.example')
    def run(command, **kwargs):
        # Quiet JSON omits skipped_checks, defeating the base comparison entirely.
        assert '--quiet' not in command
        return 0, json.dumps(dict(results=dict(failed_checks=[], skipped_checks=[check]))), ''
    monkeypatch.setattr(scan, 'run_cmd', run)
    findings, error, _ = scan.run_checkov(tmp_path)
    assert not error
    assert len(findings) == 1
    assert findings[0]['severity'] == 'HIGH'


@pytest.mark.parametrize('contents', [
    'description = "#checkov:skip=CKV_AZURE_53:Reviewed exception"',
    'description = <<EOT\n#checkov:skip=CKV_AZURE_53:Reviewed exception\nEOT',
    'description = <<-EOT\n  #checkov:skip=CKV_AZURE_53:Reviewed exception\n  EOT',
])
def test_comment_text_inside_strings_cannot_approve(tmp_path, contents):
    from scan_policy import terraform_inline_skips
    fake = 'resource "azurerm_mysql_server" "example" {\n' + contents + '\n}\n'
    assert not terraform_inline_skips(fake).get('azurerm_mysql_server.example')


def test_nested_blocks_templates_and_crlf_do_not_change_resource_identity():
    from scan_policy import terraform_inline_skips
    source = SOURCE.replace('  name = "storage"', '''  name = "${format("%s", "{storage}")}"
  nested {
    value = "}"
  }''')
    assert terraform_inline_skips(source.replace('\n', '\r\n')) == {
        'azurerm_mysql_server.example': {('CKV_AZURE_53', 'Reviewed exception')}}


def test_sarif_honours_only_approved_skips_and_keeps_failed_twin(tmp_path, monkeypatch):
    import checkov_consumer_options as options
    from scan_policy import checkov_checks
    # Bind the SARIF filter to the same JSON matcher, then prove that a failed
    # record at an approved location remains independent.
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'main.tf').write_text(SOURCE)
    (tmp_path / 'main.tf').write_text(SOURCE)
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', file_line_range=[1, 4],
                 resource='azurerm_mysql_server.example')
    monkeypatch.setattr('scan_policy.local_inline_base', lambda root: 'a' * 40)
    original = checkov_checks
    monkeypatch.setattr('scan_policy.checkov_checks', lambda results, root, **kw:
                        original(results, root, base, kw['scan_directory']))
    report = dict(results=dict(failed_checks=[], skipped_checks=[check]))
    approved = options.approved_inline_locations(report, tmp_path, '.', 'a' * 40)
    location = dict(physicalLocation=dict(artifactLocation=dict(uri='main.tf'),
                                          region=dict(startLine=1, endLine=4)))
    failed = dict(ruleId='CKV_AZURE_53', locations=[location], level='error')
    skipped = dict(failed, suppressions=[dict(kind='inSource')])
    added = dict(skipped, ruleId='CKV_AZURE_110')
    sarif = dict(runs=[dict(results=[skipped, failed, added])])
    assert options.filter_sarif(sarif, allow_inline=False, approved_locations=approved) == 1
    assert sarif['runs'][0]['results'] == [failed, added]
    assert 'suppressions' not in added
