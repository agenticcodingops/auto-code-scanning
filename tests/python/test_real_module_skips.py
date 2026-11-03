"""Use captured 3.3.19 records, including actual instance and caller formats."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scan_policy import checkov_checks


FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/checkov-module-records'


def records(case):
    report = json.loads((FIXTURES / f'{case}.json').read_text(encoding='utf-8'))[0]
    assert report['summary']['checkov_version'] == '3.3.19'
    # Captured on Windows. Only translate the platform's path separator, as the
    # same scanner does on Linux; keep all addresses and caller relationships.
    for check in report['results']['skipped_checks']:
        for key in ('file_path', 'caller_file_path'):
            if check.get(key):
                check[key] = check[key].replace('\\', '/')
    return report['results']


@pytest.mark.parametrize('case', ['module-calls', 'nested'])
@pytest.mark.parametrize('backend', ['checkout', 'objects'])
@pytest.mark.parametrize('change', ['unchanged', 'new-skip', 'edited-skip', 'moved-skip',
                                    'new-call', 'changed-source', 'unsupported'])
def test_real_records_require_trusted_approvals(tmp_path, case, backend, change):
    source, base = tmp_path / 'source', tmp_path / 'base'
    shutil.copytree(FIXTURES / case, source)
    shutil.copytree(source, base)
    skip_path = 'main.tf' if case == 'module-calls' else 'modules/b/main.tf'
    trusted = base / skip_path
    original = trusted.read_text(encoding='utf-8')
    if change == 'new-skip':
        trusted.write_text('\n'.join(line for line in original.splitlines()
                                     if '#checkov:skip=' not in line), encoding='utf-8')
    elif change == 'edited-skip':
        trusted.write_text(original.replace('Reviewed', 'Previously reviewed'), encoding='utf-8')
    elif change == 'moved-skip':
        trusted.rename(trusted.with_name('previous.tf'))
    elif change in ('new-call', 'changed-source'):
        # A nested declaration cannot lend approval to a new or repointed call.
        if case == 'module-calls':
            trusted.write_text('', encoding='utf-8')
        else:
            path = base / 'entry/main.tf'
            path.write_text('' if change == 'new-call' else
                            path.read_text().replace('../modules/a', '../modules/previous'), encoding='utf-8')
    elif change == 'unsupported':
        trusted.write_text(original + '\nlocals { value = "${<<EOT\ntext\nEOT\n}" }\n', encoding='utf-8')

    if backend == 'objects':
        def git(*args):
            return subprocess.check_output(['git', '-C', str(base), *args], text=True).strip()
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.test')
        git('add', '.')
        git('commit', '-qm', 'trusted fixture')
        # The Git-object backend reads from the source repository.
        subprocess.run(['git', 'clone', '-q', str(base), str(tmp_path / 'objects')], check=True)
        shutil.copytree(tmp_path / 'objects/.git', source / '.git')
        options = {'base_commit': git('rev-parse', 'HEAD')}
    else:
        options = {'policy_root': base}
    report = records(case)
    expected = [] if change == 'unchanged' else report['skipped_checks']
    assert checkov_checks(report, source, **options) == expected


@pytest.mark.parametrize('change', ['renamed-inner', 'duplicate-inner', 'changed-inner-source',
                                    'unsupported-caller', 'wrong-caller', 'wrong-file-in-caller-directory'])
def test_nested_records_cannot_borrow_a_different_chain(tmp_path, change):
    source, base = tmp_path / 'source', tmp_path / 'base'
    shutil.copytree(FIXTURES / 'nested', source)
    shutil.copytree(source, base)
    caller = base / 'modules/a/main.tf'
    text = caller.read_text()
    if change == 'renamed-inner':
        text = text.replace('"inner"', '"previous"')
    elif change == 'duplicate-inner':
        text += text
    elif change == 'changed-inner-source':
        text = text.replace('../b', '../previous')
    elif change == 'unsupported-caller':
        text += '\nlocals { value = "${<<EOT\ntext\nEOT\n}" }\n'
    caller.write_text(text, encoding='utf-8')
    report = records('nested')
    if change == 'wrong-caller':
        for check in report['skipped_checks']:
            check['caller_file_path'] = '/entry/main.tf'
    elif change == 'wrong-file-in-caller-directory':
        (source / 'modules/a/other.tf').write_text('locals { value = 1 }\n', encoding='utf-8')
        for check in report['skipped_checks']:
            check['caller_file_path'] = '/modules/a/other.tf'
    assert checkov_checks(report, source, base) == report['skipped_checks']


@pytest.mark.parametrize('changed_parent', [False, True])
def test_real_nested_module_call_records(tmp_path, changed_parent):
    source, base = tmp_path / 'source', tmp_path / 'base'
    shutil.copytree(FIXTURES / 'nested', source)
    shutil.copytree(source, base)
    report = records('nested-module-calls')
    assert any('.inner' in check['resource'] for check in report['skipped_checks'])
    if changed_parent:
        (base / 'entry/main.tf').write_text('', encoding='utf-8')
    assert checkov_checks(report, source, base) == (report['skipped_checks'] if changed_parent else [])
