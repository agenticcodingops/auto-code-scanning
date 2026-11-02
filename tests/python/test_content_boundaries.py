"""Regression coverage for trusted inputs and output boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_templates_use_immutable_refs_and_safe_yaml():
    for path in (ROOT / 'templates').rglob('*.y*ml'):
        data = yaml.safe_load(path.read_text()) or {}
        for repo in data.get('repos', []):
            if repo['repo'] != 'local':
                assert re.fullmatch('[0-9a-f]{40}', repo['rev']), path
        for job in data.get('jobs', {}).values():
            if 'uses' in job and not job['uses'].startswith('./'):
                assert re.search('@[0-9a-f]{40}$', job['uses']), path


def test_templates_use_safe_yaml_validation():
    checked = 0
    for path in (ROOT / 'templates').rglob('pre-commit-config.yaml'):
        for repo in yaml.safe_load(path.read_text())['repos']:
            for hook in repo.get('hooks', []):
                if hook['id'] == 'check-yaml':
                    checked += 1
                    assert '--unsafe' not in hook.get('args', []), path
    assert checked >= 6


def test_installers_have_no_mutable_execution():
    for name in ('setup-scanning.py', 'setup-scanning.ps1', 'setup-scanning-no-admin.ps1'):
        source = (ROOT / 'scripts' / name).read_text()
        for pattern in ('Invoke-Expression', 'releases/latest/', '/master/install', 'scoop update'):
            assert pattern not in source, (name, pattern)


def link_or_skip(target, link, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        if directory and os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            if result.returncode == 0:
                return
        pytest.skip('link creation unavailable')


@pytest.mark.parametrize('parent_link', [False, True])
def test_onboarding_copy_refuses_link(tmp_path, parent_link):
    import setup_scan_fix
    source = tmp_path / 'source'; source.write_text('new')
    outside = tmp_path / 'outside'; outside.mkdir()
    target = outside / 'target'; target.write_text('original')
    destination = tmp_path / 'dest'
    link_or_skip(outside if parent_link else target, destination, parent_link)
    with pytest.raises((OSError, ValueError)):
        setup_scan_fix.copy(source, destination / 'target' if parent_link else destination)
    assert target.read_text() == 'original'


@pytest.mark.parametrize('shell', ['bash', 'pwsh'])
def test_hook_output_refuses_directory_link(tmp_path, shell):
    command = shutil.which(shell)
    if not command:
        pytest.skip(shell + ' unavailable')
    outside = tmp_path / 'outside'; outside.mkdir()
    sentinel = outside / 'last-scan.json'; sentinel.write_text('original')
    repo = tmp_path / 'repo'; repo.mkdir()
    link_or_skip(outside, repo / '.scanning', True)
    common = ROOT / ('hooks/lib/common.sh' if shell == 'bash' else 'hooks/lib/common.ps1')
    if shell == 'bash':
        local = tmp_path / 'common.sh'; local.write_text(common.read_text(), newline='\n')
        args = [command, '-c', f'source "{local.as_posix()}"; write_scan_json "new"']
    else:
        args = [command, '-NoProfile', '-Command', f"$ErrorActionPreference='Stop'; . '{common.as_posix()}'; Write-ScanJson 'new'"]
    result = subprocess.run(args, cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert sentinel.read_text() == 'original'


@pytest.mark.parametrize('tool', ['eslint', 'prettier'])
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_app_hooks_require_explicit_repository_trust(tool, shell):
    source = (ROOT / f'hooks/{tool}.{shell}').read_text()
    assert 'SCAN_TRUST_REPO_CODE' in source
    assert ('require_trusted_app_tool' if shell == 'sh' else 'Get-TrustedAppTool') in source


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_tflint_requires_trusted_config_before_init(shell):
    source = (ROOT / f'hooks/tflint.{shell}').read_text()
    assert 'SCAN_TFLINT_CONFIG' in source
    assert 'TFLINT_PLUGIN_DIR' in source
    assert source.index('SCAN_TFLINT_CONFIG') < source.index('--init')


def test_comment_escapes_all_scanner_text(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    workflow = yaml.safe_load((ROOT / '.github/workflows/reusable-scan.yml').read_text())
    script = next(s['with']['script'] for s in workflow['jobs']['pr-comment']['steps'] if s.get('name') == 'Post PR comment')
    folder = tmp_path / 'aggregated'; folder.mkdir()
    text = '<b>text</b>|[name](https://example.org)\n@someone `code`'
    data = {'scan_complete': True, 'scan_passed': False, 'total_findings': 1, 'by_severity': {'HIGH': '<b>count</b>'},
            'findings': [dict.fromkeys(['file','rule_id','severity','tool'], text) | {'remediation_url':'javascript:alert(1)'}]}
    (folder / 'aggregated.json').write_text(json.dumps(data))
    wrapper = "const context={issue:{number:1},repo:{owner:'test',repo:'test'}}; const github={rest:{issues:{createComment:async x=>console.log(JSON.stringify(x))}}};\n"
    result = subprocess.run([node, '-e', wrapper + '(async()=>{' + script + '})()'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)['body']
    assert text not in body
    assert 'javascript:' not in body
    assert '<b>' not in body
    assert '@someone' not in body
    assert '<b>count</b>' not in body

def test_archive_digest_is_checked_before_opening():
    spec = importlib.util.spec_from_file_location('install_scanner', ROOT / 'scripts/install-scanner.py')
    installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
    with pytest.raises(ValueError, match='checksum mismatch'):
        installer.verified_binary(b'not an archive', '0' * 64, 'scanner', True)


@pytest.mark.parametrize('operation', ['write', 'append'])
@pytest.mark.parametrize('parent_link', [False, True])
def test_output_helpers_reject_links(tmp_path, operation, parent_link):
    from safe_io import write_text, append_text
    outside = tmp_path / 'outside'; outside.mkdir()
    target = outside / 'report'; target.write_text('original')
    link = tmp_path / 'linked'
    link_or_skip(outside if parent_link else target, link, parent_link)
    with pytest.raises(OSError):
        (write_text if operation == 'write' else append_text)(link / 'report' if parent_link else link, 'changed')
    assert target.read_text() == 'original'


def prepare_hook_repo(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    subprocess.run(['git','init','-q'],cwd=repo,check=True)
    hooks = tmp_path / 'installed-hooks'
    shutil.copytree(ROOT / 'hooks', hooks)
    for script in hooks.rglob('*.sh'):
        script.write_text(script.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    return repo, hooks


@pytest.mark.parametrize('tool', ['eslint','prettier'])
@pytest.mark.parametrize('shell', ['bash','pwsh'])
def test_app_hook_does_not_run_checkout_binaries(tmp_path, tool, shell):
    if not shutil.which(shell): pytest.skip(shell + ' unavailable')
    repo, hooks = prepare_hook_repo(tmp_path)
    (repo / 'sample.ts').write_text('const x = 1;\n')
    local = repo / 'node_modules/.bin'; local.mkdir(parents=True)
    marker = tmp_path / 'executed'
    (local / tool).write_text(f'#!/usr/bin/env bash\ntouch "{marker.as_posix()}"\n')
    (local / tool).chmod(0o755)
    (local / (tool + '.cmd')).write_text(f'@echo off\necho ran > "{marker}"\n')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith('SCAN_')}
    suffix = 'sh' if shell == 'bash' else 'ps1'
    args = [shutil.which(shell)] + ([] if shell=='bash' else ['-NoProfile','-File']) + [str(hooks / f'{tool}.{suffix}')]
    result = subprocess.run(args,cwd=repo,env=env,capture_output=True)
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize('shell', ['bash','pwsh'])
@pytest.mark.parametrize('config', ['missing','repository','external'])
def test_tflint_init_requires_external_config(tmp_path,shell,config):
    if not shutil.which(shell): pytest.skip(shell + ' unavailable')
    repo,hooks = prepare_hook_repo(tmp_path)
    (repo / 'main.tf').write_text('# fixture\n')
    (repo / '.tflint.hcl').write_text('# repository config\n')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    tools = tmp_path / 'tools'; tools.mkdir()
    calls = tmp_path / 'calls'
    (tools / 'tflint').write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{calls.as_posix()}"\necho \'{{"issues":[]}}\'\n',newline='\n')
    (tools / 'tflint').chmod(0o755)
    (tools / 'tflint.cmd').write_text(f'@echo off\necho %* >> "{calls}"\necho {{"issues":[]}}\n')
    trusted = tmp_path / 'trusted.hcl'; trusted.write_text('# trusted config\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith('SCAN_')}
    env['PATH'] = str(tools) + os.pathsep + env['PATH']
    env['SCAN_TFLINT_PLUGIN_DIR'] = str(tmp_path / 'plugins')
    if config != 'missing': env['SCAN_TFLINT_CONFIG'] = str(trusted if config=='external' else repo / '.tflint.hcl')
    suffix='sh' if shell=='bash' else 'ps1'
    args=[shutil.which(shell)] + ([] if shell=='bash' else ['-NoProfile','-File']) + [str(hooks / f'tflint.{suffix}')]
    result=subprocess.run(args,cwd=repo,env=env,capture_output=True,text=True)
    if config=='external':
        assert result.returncode==0, result.stdout+result.stderr
        assert '--init' in calls.read_text()
        assert all('--config' in line and 'trusted.hcl' in line for line in calls.read_text().splitlines())
    else:
        assert result.returncode != 0
        assert not calls.exists()
