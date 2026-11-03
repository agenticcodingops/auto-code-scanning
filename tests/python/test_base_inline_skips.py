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
        (tmp_path / 'scan-config.yaml').write_text('{}', encoding='utf-8')
        with pytest.raises(SystemExit) as exited:
            scan.main()
        code = exited.value.code
        report = json.loads((tmp_path / 'result.json').read_text(encoding='utf-8'))
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
            target.write_text(json.dumps(data), encoding='utf-8')
        statuses = {name: {'result': 'success'} for name in ('setup', 'scan-checkov', 'scan-trivy', 'scan-tflint')}
        env = dict(os.environ, SCANNER_RESULTS=json.dumps(statuses), POLICY_ROOT=str(base),
                   TERRAFORM_DIRECTORY='infra', FAIL_ON_FINDINGS='true', GITHUB_OUTPUT=str(tmp_path / 'out'),
                   ALLOW_INLINE_CHECKOV_SKIPS='false', APPLY_SUPPRESSIONS='true', APPLY_BASELINE='true')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/aggregate_scan.py')],
                                env=env, capture_output=True, text=True)
        code = result.returncode
        report = json.loads((tmp_path / '.scan-results/aggregated.json').read_text(encoding='utf-8'))
        assert report['scan_complete'], result.stderr
        assert report['total_findings'] == expected
    assert code == expected


def test_local_default_reads_remote_base_not_pr_tip(tmp_path):
    from scan_policy import checkov_checks
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    path = tmp_path / 'main.tf'
    path.write_text(SOURCE, encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'base')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    path.write_text(SOURCE.replace('Reviewed exception', 'New justification'), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'changed skip')
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', resource='azurerm_mysql_server.example')
    results = dict(failed_checks=[], skipped_checks=[check])
    assert checkov_checks(results, tmp_path) == [check]
    path.write_text('# line shift\n' + SOURCE, encoding='utf-8')
    assert checkov_checks(results, tmp_path) == []


@pytest.mark.parametrize('backend,unrelated', [('checkout', b''), ('objects', b''),
    ('objects', b'notes-\xff.txt'), ('objects', b'nested/notes-\xff.tf')])
@pytest.mark.parametrize('nested', [False, True])
def test_renamed_module_call_file_keeps_trusted_approval(tmp_path, backend, unrelated, nested):
    from scan_policy import checkov_checks
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    root = tmp_path / 'infra' if nested else tmp_path
    module = root / 'modules/database'
    module.mkdir(parents=True)
    (module / 'main.tf').write_text(SOURCE, encoding='utf-8')
    (root / 'main.tf').write_text('module "database" { source = "./modules/database" }\n', encoding='utf-8')
    git('add', '.')
    if unrelated:
        blob = subprocess.check_output(['git', '-C', str(tmp_path), 'hash-object', '-w', '--stdin'], input=b'notes')
        record = b'100644 ' + blob.strip() + b'\t' + unrelated + b'\0'
        subprocess.run(['git', '-C', str(tmp_path), 'update-index', '-z', '--index-info'], input=record, check=True)
    git('commit', '-qm', 'trusted base')
    base = git('rev-parse', 'HEAD')
    checkout = tmp_path / 'trusted'
    if backend == 'checkout':
        subprocess.run(['git', 'clone', '-q', str(tmp_path), str(checkout)], check=True)
    (root / 'main.tf').rename(root / 'calls.tf')
    check = dict(check_id='CKV_AZURE_53', file_path='/modules/database/main.tf',
                 resource='module.database.azurerm_mysql_server.example')
    options = {'policy_root': checkout} if backend == 'checkout' else {'base_commit': base}
    assert checkov_checks(dict(failed_checks=[], skipped_checks=[check]), root, **options) == []


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


def test_local_does_not_restore_a_skip_removed_on_the_advanced_base(tmp_path):
    from scan_policy import checkov_checks
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    path = tmp_path / 'main.tf'
    path.write_text(SOURCE, encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'original base')
    git('branch', 'feature')
    path.write_text(SOURCE.replace('  #checkov:skip=CKV_AZURE_53:Reviewed exception\n', ''), encoding='utf-8')
    git('commit', '-am', 'remove reviewed skip')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    git('checkout', 'feature')
    (tmp_path / 'note.txt').write_text('unrelated feature change', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'feature')
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', resource='azurerm_mysql_server.example')
    results = dict(failed_checks=[], skipped_checks=[check])
    assert checkov_checks(results, tmp_path) == [check]


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


@pytest.mark.parametrize('approved', [False, True])
@pytest.mark.parametrize('explicit_base', [False, True])
def test_nested_policy_root_cannot_borrow_root_file_approval(tmp_path, approved, explicit_base):
    from scan_policy import checkov_checks
    repo, base = tmp_path / 'repo', tmp_path / 'base'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    without_skip = SOURCE.replace('  #checkov:skip=CKV_AZURE_53:Reviewed exception\n', '')
    for directory in (repo, base):
        (directory / 'infra').mkdir(parents=True)
        (directory / 'main.tf').write_text(without_skip if approved else SOURCE, encoding='utf-8')
        (directory / 'infra/main.tf').write_text(SOURCE if approved else without_skip, encoding='utf-8')
        (directory / 'infra/scan-config.yaml').write_text('{}', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'base')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    (repo / 'infra/main.tf').write_text(SOURCE, encoding='utf-8')
    check = dict(check_id='CKV_AZURE_53', file_path='/main.tf', resource='azurerm_mysql_server.example')
    pending = checkov_checks(dict(failed_checks=[], skipped_checks=[check]), repo / 'infra',
                             base if explicit_base else None)
    assert pending == ([] if approved else [check])


def test_heredoc_inside_template_cannot_authorize_a_real_skip(tmp_path):
    from scan_policy import checkov_checks
    base = tmp_path / 'base'
    base.mkdir()
    text = '''resource "aws_instance" "example" {
  user_data = "${<<EOT
}"
#checkov:skip=CKV_AWS_79:Reviewed exception
EOT
}"
}
'''
    (base / 'main.tf').write_text(text, encoding='utf-8')
    (tmp_path / 'main.tf').write_text(text.replace('  user_data',
        '  #checkov:skip=CKV_AWS_79:Reviewed exception\n  user_data'), encoding='utf-8')
    check = dict(check_id='CKV_AWS_79', file_path='/main.tf', resource='aws_instance.example')
    results = dict(failed_checks=[], skipped_checks=[check])
    assert checkov_checks(results, tmp_path, base) == [check]


NESTED_HEREDOCS = [
    '''resource "aws_instance" "example" {
  user_data = "${<<EOT
}"
#checkov:skip=CKV_AWS_79:Reviewed exception
EOT
}"
}
''',
    '''resource "aws_instance" "example" {
  user_data = <<OUTER
${<<INNER
OUTER
{
#checkov:skip=CKV_AWS_79:Reviewed exception
INNER
}
OUTER
}
''',
]


@pytest.mark.parametrize('text', NESTED_HEREDOCS, ids=['quoted', 'heredoc'])
def test_nested_heredoc_data_cannot_approve_an_added_skip(tmp_path, text):
    from scan_policy import checkov_checks
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'main.tf').write_text(text, encoding='utf-8')
    (tmp_path / 'main.tf').write_text(text.replace('  user_data',
        '  #checkov:skip=CKV_AWS_79:Reviewed exception\n  user_data'), encoding='utf-8')
    check = dict(check_id='CKV_AWS_79', file_path='/main.tf', resource='aws_instance.example')
    assert checkov_checks(dict(failed_checks=[], skipped_checks=[check]), tmp_path, base) == [check]


@pytest.mark.parametrize('text', NESTED_HEREDOCS, ids=['quoted', 'heredoc'])
@pytest.mark.parametrize('unsupported_in', ['base', 'current', 'both'])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_unsupported_templates_reject_whole_file_only(tmp_path, text, unsupported_in, position):
    from scan_policy import checkov_checks, terraform_inline_skips
    base = tmp_path / 'base'
    base.mkdir()
    unsupported = text + SOURCE if position == 'before' else SOURCE + text
    # A real approval anywhere in the unsupported file must also be discarded.
    assert terraform_inline_skips(unsupported) == {}
    modules = {'previous': './previous'}
    assert terraform_inline_skips(unsupported, module_sources=modules) == {}
    assert modules == {}
    for root, version in ((tmp_path, 'current'), (base, 'base')):
        (root / 'main.tf').write_text(
            unsupported if unsupported_in in (version, 'both') else SOURCE, encoding='utf-8')
        (root / 'ordinary.tf').write_text(SOURCE, encoding='utf-8')
    rejected = dict(check_id='CKV_AZURE_53', file_path='/main.tf',
                    resource='azurerm_mysql_server.example')
    ordinary = dict(rejected, file_path='/ordinary.tf')
    results = dict(failed_checks=[], skipped_checks=[rejected, ordinary])
    assert checkov_checks(results, tmp_path, base) == [rejected]


def test_excessive_template_nesting_rejects_whole_file():
    from scan_policy import terraform_inline_skips
    template = '"value"'
    for _ in range(sys.getrecursionlimit() + 10):
        template = '"${' + template + '}"'
    text = SOURCE + 'locals { deep = ' + template + ' }\n'
    modules = {'previous': './previous'}
    assert terraform_inline_skips(text, module_sources=modules) == {}
    assert modules == {}


@pytest.mark.parametrize('split_documents', [False, True])
def test_sarif_keeps_module_location_shared_with_unapproved_instance(tmp_path, split_documents):
    import checkov_consumer_options as options
    from scan_policy import checkov_checks
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    (tmp_path / 'modules/database').mkdir(parents=True)
    (tmp_path / 'modules/database/main.tf').write_text(SOURCE, encoding='utf-8')
    call = 'module "database" { source = "./modules/database" }\n'
    (tmp_path / 'main.tf').write_text(call, encoding='utf-8')
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.com')
    git('add', '.')
    git('commit', '-m', 'fixture base')
    base = git('rev-parse', 'HEAD')
    (tmp_path / 'main.tf').write_text(call + call.replace('"database"', '"new"'), encoding='utf-8')
    approved = dict(check_id='CKV_AZURE_53', file_path='/modules/database/main.tf',
                    file_line_range=[1, 4], resource='module.database.azurerm_mysql_server.example')
    pending = dict(approved, resource='module.new.azurerm_mysql_server.example')
    checks = dict(failed_checks=[], skipped_checks=[approved, pending])
    assert checkov_checks(checks, tmp_path, base_commit=base) == [pending]
    report = ([dict(results=dict(failed_checks=[], skipped_checks=[check]))
               for check in (approved, pending)] if split_documents else dict(results=checks))
    locations = options.approved_inline_locations(report, tmp_path, '.', base)
    assert locations == set()
    results = [dict(ruleId='CKV_AZURE_53', suppressions=[dict(kind='inSource')],
                    properties=dict(resource=check['resource']),
                    locations=[dict(physicalLocation=dict(
                        artifactLocation=dict(uri='modules/database/main.tf'),
                        region=dict(startLine=1, endLine=4)))]) for check in (approved, pending)]
    sarif = dict(runs=[dict(results=results)])
    assert options.filter_sarif(sarif, False, locations, tmp_path) == 0
    assert sarif['runs'][0]['results'] == results
    assert all(result['level'] == 'error' and 'suppressions' not in result for result in results)


@pytest.mark.parametrize('opener', ['$${', '%%{'])
def test_escaped_template_openers_keep_real_skips_visible(opener):
    from scan_policy import terraform_inline_skips
    text = SOURCE.replace('name = "storage"', f'name = "{opener}"')
    assert terraform_inline_skips(text)['azurerm_mysql_server.example'] == {
        ('CKV_AZURE_53', 'Reviewed exception')}


def test_interpolation_comments_cannot_expose_string_contents():
    from scan_policy import terraform_inline_skips
    text = '''resource "aws_s3_bucket" "example" {
  bucket = "${join("", [/* } */ "#checkov:skip=CKV_AWS_20:Reviewed"])}"
}
'''
    assert not terraform_inline_skips(text).get('aws_s3_bucket.example')


@pytest.mark.parametrize('tag', ['EOT', 'ÉOT'])
def test_plain_heredoc_does_not_end_at_an_indented_marker(tag):
    from scan_policy import terraform_inline_skips
    text = f'''resource "aws_s3_bucket" "example" {{
  value = <<{tag}
  {tag}
  #checkov:skip=CKV_AWS_20:Reviewed
{tag}
}}
'''
    assert not terraform_inline_skips(text).get('aws_s3_bucket.example')


def test_unrecognized_heredoc_fails_closed():
    from scan_policy import terraform_inline_skips
    text = SOURCE.replace('  name = "storage"', '  value = <<EOT\nunterminated')
    assert terraform_inline_skips(text) == {}


@pytest.mark.parametrize('case,expected', [
    ('unchanged', 0), ('added-call', 1), ('renamed-call', 1), ('changed-source', 1),
    ('unrelated-caller-edit', 0), ('nested', 0), ('indexed', 0), ('remote-source', 1),
])
def test_module_skips_require_the_same_trusted_source_chain(tmp_path, case, expected):
    from scan_policy import checkov_checks
    source, base = tmp_path / 'source', tmp_path / 'base'
    call = 'module "database" { source = "./modules/database" }\n'
    for root in (source, base):
        (root / 'modules/database').mkdir(parents=True)
        (root / 'modules/database/main.tf').write_text(SOURCE, encoding='utf-8')
        (root / 'main.tf').write_text(call, encoding='utf-8')
    resource = 'module.database.azurerm_mysql_server.example'
    if case == 'added-call':
        (base / 'main.tf').write_text('', encoding='utf-8')
    elif case == 'renamed-call':
        (source / 'main.tf').write_text(call.replace('"database"', '"new"'), encoding='utf-8')
        resource = resource.replace('module.database.', 'module.new.')
    elif case == 'changed-source':
        (base / 'main.tf').write_text(call.replace('./modules/database', './modules/previous'), encoding='utf-8')
    elif case == 'unrelated-caller-edit':
        (source / 'main.tf').write_text('# unrelated edit\n' + call, encoding='utf-8')
    elif case == 'nested':
        for root in (source, base):
            (root / 'modules/outer').mkdir()
            (root / 'main.tf').write_text('module "outer" { source = "./modules/outer" }\n', encoding='utf-8')
            (root / 'modules/outer/main.tf').write_text(call.replace('./modules/database', '../database'), encoding='utf-8')
        resource = 'module.outer.' + resource
    elif case == 'indexed':
        resource = 'module.database[0].azurerm_mysql_server.example[0]'
    elif case == 'remote-source':
        for root in (source, base):
            (root / 'main.tf').write_text(call.replace('./modules/database', 'registry/database/cloud'), encoding='utf-8')
    check = dict(check_id='CKV_AZURE_53', file_path='/modules/database/main.tf', resource=resource)
    results = dict(failed_checks=[], skipped_checks=[check])
    assert len(checkov_checks(results, source, base)) == expected


@pytest.mark.parametrize('uri', ['main.tf', 'infra%20space/main.tf'])
def test_sarif_paths_use_the_selected_scan_directory(tmp_path, uri):
    import checkov_consumer_options as options
    result = dict(ruleId='CKV_AZURE_53', suppressions=[dict(kind='inSource')],
                  locations=[dict(physicalLocation=dict(artifactLocation=dict(uri=uri),
                                                        region=dict(startLine=1, endLine=4)))])
    sarif = dict(runs=[dict(results=[result])])
    approved = {('CKV_AZURE_53', 'infra space/main.tf', 1, 4)}
    assert options.filter_sarif(sarif, False, approved, tmp_path, 'infra space') == 1
    assert not sarif['runs'][0]['results']


def test_sarif_honours_only_approved_skips_and_keeps_failed_twin(tmp_path, monkeypatch):
    import checkov_consumer_options as options
    from scan_policy import checkov_checks
    # Bind the SARIF filter to the same JSON matcher, then prove that a failed
    # record at an approved location remains independent.
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'main.tf').write_text(SOURCE, encoding='utf-8')
    (tmp_path / 'main.tf').write_text(SOURCE, encoding='utf-8')
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
