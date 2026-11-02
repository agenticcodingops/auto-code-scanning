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


def test_templates_pin_third_party_hooks_to_immutable_refs():
    for path in (ROOT / 'templates').rglob('*.y*ml'):
        data = yaml.safe_load(path.read_text()) or {}
        for repo in data.get('repos', []):
            if repo['repo'] not in ('local', 'https://github.com/agenticcodingops/auto-code-scanning'):
                assert re.fullmatch('[0-9a-f]{40}', repo['rev']), path


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
    assert '&#64;&#8203;someone' in body
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
@pytest.mark.parametrize('config', ['missing','repository','override','external'])
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
    trusted = tmp_path / 'trusted.hcl'; trusted.write_text('config { plugin_dir = \"./plugins\" }\n' if config == 'override' else '# trusted config\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith('SCAN_')}
    env['PATH'] = str(tools) + os.pathsep + env['PATH']
    # This fixture tests the wrapper's input boundary, without a push transaction.
    env['SCAN_LEGACY_PUSH_STATE'] = '1'
    env['SCAN_TFLINT_PLUGIN_DIR'] = str(tmp_path / 'plugins')
    if config != 'missing': env['SCAN_TFLINT_CONFIG'] = str(trusted if config in ('external','override') else repo / '.tflint.hcl')
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


def test_installer_handles_empty_windows_machine(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('install_scanner', ROOT / 'scripts/install-scanner.py')
    installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(installer.platform, 'machine', lambda: '')
    monkeypatch.setattr(installer.sysconfig, 'get_platform', lambda: 'win-amd64')
    class Download:
        def read(self): return b'archive'
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **kw: Download())
    monkeypatch.setattr(installer, 'verified_binary', lambda *a: b'binary')
    result = installer.install('tflint', tmp_path)
    assert result.name == 'tflint.exe'
    assert result.read_bytes() == b'binary'


@pytest.mark.parametrize('shell', ['bash','pwsh'])
def test_prettier_resolves_plugins_from_trusted_directory(tmp_path, shell):
    if not shutil.which(shell): pytest.skip(shell + ' unavailable')
    repo, hooks = prepare_hook_repo(tmp_path)
    (repo / 'sample.ts').write_text('const x = 1;\n')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    trusted = tmp_path / 'trusted'; trusted.mkdir()
    config = trusted / 'prettier.json'; config.write_text('{}')
    trace = tmp_path / 'cwd'
    arguments = tmp_path / 'arguments'
    tool = trusted / 'prettier'
    tool.write_text(f'#!/usr/bin/env bash\npwd > "{trace.as_posix()}"\nprintf "%s\\n" "$@" > "{arguments.as_posix()}"\n',newline='\n')
    tool.chmod(0o755)
    if shell == 'pwsh' and os.name == 'nt':
        tool = trusted / 'prettier.cmd'
        tool.write_text(f'@echo off\ncd > "{trace}"\necho %* > "{arguments}"\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith('SCAN_')}
    env.update(SCAN_PRETTIER_BIN=str(tool),SCAN_PRETTIER_CONFIG=str(config))
    suffix = 'sh' if shell == 'bash' else 'ps1'
    args=[shutil.which(shell)] + ([] if shell=='bash' else ['-NoProfile','-File']) + [str(hooks / f'prettier.{suffix}')]
    result=subprocess.run(args,cwd=repo,env=env,capture_output=True,text=True)
    assert result.returncode==0, result.stdout+result.stderr
    actual=trace.read_text().strip().replace('\\','/').lower()
    expected=trusted.as_posix().lower()
    expected_repo=repo.as_posix().lower()
    if shell == 'bash' and os.name == 'nt':
        expected=subprocess.check_output([shutil.which('bash'),'-c','cd \"$1\" && pwd -P','_',str(trusted)],text=True).strip().lower()
        expected_repo=subprocess.check_output([shutil.which('bash'),'-c','cd \"$1\" && pwd -P','_',str(repo)],text=True).strip().lower()
    assert actual==expected
    actual_args=arguments.read_text().replace('\\','/').lower()
    assert expected_repo + '/sample.ts' in actual_args


def test_posix_link_checks_work_without_python(tmp_path):
    if os.name == 'nt': pytest.skip('POSIX fallback; Windows requires Python')
    bash=shutil.which('bash')
    if not bash: pytest.skip('bash unavailable')
    outside=tmp_path/'outside'; outside.mkdir()
    (outside/'last-scan.json').write_text('original')
    repo=tmp_path/'repo'; repo.mkdir()
    link_or_skip(outside,repo/'.scanning',True)
    common=(ROOT/'hooks/lib/common.sh').as_posix()
    result=subprocess.run([bash,'-c',f'source "{common}"; find_python() {{ return 1; }}; write_scan_json new'],cwd=repo,capture_output=True)
    assert result.returncode != 0
    assert (outside/'last-scan.json').read_text()=='original'


def test_onboarding_allows_unrelated_dependency_symlink(tmp_path, monkeypatch):
    import setup_scan_fix
    target=tmp_path/'dependency.js'; target.write_text('// installed dependency\n')
    folder=tmp_path/'node_modules/.bin'; folder.mkdir(parents=True)
    link_or_skip(target,folder/'tool')
    monkeypatch.setattr(setup_scan_fix,'have',lambda _command: False)
    monkeypatch.setattr(setup_scan_fix.subprocess,'run',lambda *a, **kw: None)
    assert setup_scan_fix.main(['setup-scan-fix.py','--repo-path',str(tmp_path)])==0
    assert (tmp_path/'hooks/lib/common.sh').is_file()
    assert (folder/'tool').is_symlink()


@pytest.mark.parametrize('tool', ['trivy','tflint','gitleaks'])
def test_linux_arm64_installer_is_supported(tmp_path,monkeypatch,tool):
    spec=importlib.util.spec_from_file_location('install_scanner',ROOT/'scripts/install-scanner.py')
    installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
    monkeypatch.setattr(installer.platform,'system',lambda:'Linux')
    monkeypatch.setattr(installer.platform,'machine',lambda:'aarch64')
    class Download:
        def read(self): return b'archive'
    monkeypatch.setattr(installer.urllib.request,'urlopen',lambda *a,**kw:Download())
    monkeypatch.setattr(installer,'verified_binary',lambda *a:b'binary')
    assert installer.install(tool,tmp_path).read_bytes()==b'binary'


def comment_body(tmp_path, findings):
    workflow=yaml.safe_load((ROOT/'.github/workflows/reusable-scan.yml').read_text())
    script=next(s['with']['script'] for s in workflow['jobs']['pr-comment']['steps'] if s.get('name')=='Post PR comment')
    directory=tmp_path/'aggregated'; directory.mkdir(exist_ok=True)
    (directory/'aggregated.json').write_text(json.dumps({'total_findings':len(findings),'findings':findings}))
    prefix="const context={issue:{number:1},repo:{owner:'test',repo:'test'}}; const github={rest:{issues:{createComment:async x=>console.log(JSON.stringify(x))}}};"
    result=subprocess.run([shutil.which('node'),'-e',prefix+'(async()=>{'+script+'})()'],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)['body']


@pytest.mark.parametrize('url,allowed', [
    ('https://avd.aquasec.com/misconfig/test',True),
    ('http://avd.aquasec.com/misconfig/test',False),
    ('https://untrusted.example/documentation',False),
    ('https://github.com/unrelated/project',False),
])
def test_comment_links_use_documentation_hosts(tmp_path,url,allowed):
    if not shutil.which('node'): pytest.skip('node unavailable')
    body=comment_body(tmp_path,[{'file':'example.tf','remediation_url':url}])
    assert ('[Link]' in body)==allowed


def test_comment_stays_within_size_limit_after_encoding(tmp_path):
    if not shutil.which('node'): pytest.skip('node unavailable')
    record={key:'_'*1000 for key in ('file','rule_id','severity','tool')}
    body=comment_body(tmp_path,[record]*20)
    assert len(body)<65536


def test_linux_setup_with_existing_secret_scanner(monkeypatch):
    import setup_scanning
    monkeypatch.setattr(setup_scanning,'command_exists',lambda name:name=='gitleaks')
    for name in ('install_trivy_linux','install_pinned_binary','install_pip_tool','install_snyk'):
        monkeypatch.setattr(setup_scanning,name,lambda *a,**kw:True)
    monkeypatch.setattr(setup_scanning,'tools_installed',0)
    setup_scanning.install_tools('linux')
    assert setup_scanning.tools_installed==1


def test_powershell_guard_uses_session_location(tmp_path):
    pwsh=shutil.which('pwsh')
    if not pwsh: pytest.skip('PowerShell unavailable')
    outside=tmp_path/'outside'; outside.mkdir()
    (outside/'report').write_text('original')
    repo=tmp_path/'repo'; repo.mkdir()
    link_or_skip(outside,repo/'linked',True)
    common=(ROOT/'hooks/lib/common.ps1').as_posix()
    result=subprocess.run([pwsh,'-NoProfile','-Command',f"$ErrorActionPreference='Stop'; . '{common}'; Set-Location -LiteralPath '{repo.as_posix()}'; Assert-SafeWritePath 'linked/report'"],cwd=tmp_path,capture_output=True)
    assert result.returncode!=0


@pytest.mark.parametrize('shell',['pwsh','powershell'])
def test_powershell_report_write_after_set_location(tmp_path,shell):
    command=shutil.which(shell)
    if not command: pytest.skip(shell+' unavailable')
    repo=tmp_path/'repo'; repo.mkdir()
    common=(ROOT/'hooks/lib/common.ps1').as_posix()
    result=subprocess.run([command,'-NoProfile','-Command',f"$ErrorActionPreference='Stop'; . '{common}'; Set-Location -LiteralPath '{repo.as_posix()}'; Write-ScanJson '{{\"pass\":true}}'; Write-ScanJson '{{\"pass\":false}}'"],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads((repo/'.scanning/last-scan.json').read_text())=={'pass':False}
    assert not (tmp_path/'.scanning').exists()


def test_powershell_repository_script_is_not_a_trusted_tool(tmp_path):
    pwsh=shutil.which('pwsh')
    if not pwsh: pytest.skip('PowerShell unavailable')
    subprocess.run(['git','init','-q'],cwd=tmp_path,check=True)
    tools=tmp_path/'tools'; tools.mkdir()
    script=tools/'scanner.ps1'; script.write_text('exit 0\n'); script.chmod(0o755)
    common=(ROOT/'hooks/lib/common.ps1').as_posix()
    env=dict(os.environ,PATH=str(tools)+os.pathsep+os.environ['PATH'])
    result=subprocess.run([pwsh,'-NoProfile','-Command',f"$ErrorActionPreference='Stop'; . '{common}'; Test-ToolAvailable 'scanner.ps1'"],cwd=tmp_path,env=env,capture_output=True)
    assert result.returncode!=0


def test_windows_yaml_reader_keeps_trusted_user_packages(tmp_path):
    if os.name!='nt': pytest.skip('Windows user-level setup regression')
    bash=shutil.which('bash')
    if not bash: pytest.skip('bash unavailable')
    base_python=getattr(sys,'_base_executable',sys.executable)
    env=dict(os.environ,APPDATA=str(tmp_path/'user-data'))
    user_site=subprocess.check_output([base_python,'-E','-P','-c','import site; print(site.getusersitepackages())'],env=env,text=True).strip()
    package=Path(user_site)/'yaml'; package.mkdir(parents=True)
    (package/'__init__.py').write_text("def safe_load(stream): return {'setting':'trusted-user-setting'}\n")
    repo=tmp_path/'repo'; repo.mkdir()
    (repo/'yaml.py').write_text("raise AssertionError('repository module must not be imported')\n")
    config=repo/'scan-config.yaml'; config.write_text('setting: from-config-file\n')
    tools=tmp_path/'tools'; tools.mkdir()
    wrapper=tools/'python'; wrapper.write_text(f'#!/usr/bin/env bash\nexec "{Path(base_python).as_posix()}" "$@"\n',newline='\n'); wrapper.chmod(0o755)
    common=tmp_path/'common.sh'; common.write_text((ROOT/'hooks/lib/common.sh').read_text(encoding='utf-8'),newline='\n')
    env.update(PATH=str(tools)+os.pathsep+env['PATH'],SCAN_CONFIG_FILE=str(config))
    result=subprocess.run([bash,'-c',f'source "{common.as_posix()}"; read_scan_config setting missing'],cwd=repo,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='trusted-user-setting'


def test_setup_path_refresh_preserves_verified_tools(tmp_path):
    pwsh=shutil.which('pwsh')
    if not pwsh: pytest.skip('PowerShell unavailable')
    script=(ROOT/'scripts/setup-scanning.ps1').as_posix()
    code=f"$ast=[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$null,[ref]$null); $f=$ast.Find({{param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Refresh-EnvironmentPath'}},$true); . ([scriptblock]::Create($f.Extent.Text)); $env:Path='trusted-process-entry'; Refresh-EnvironmentPath; $env:Path"
    result=subprocess.run([pwsh,'-NoProfile','-Command',code],env=dict(os.environ,USERPROFILE=str(tmp_path)),capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert '.local-scanning-tools' in result.stdout.split(';')[0]
    assert 'trusted-process-entry' in result.stdout
