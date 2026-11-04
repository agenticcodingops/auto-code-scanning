"""User-installed parser compatibility and findings persistence failures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from .test_local_scanner_trust import passive_probe, wrapper_command
from .test_validation_targets import (
    ZERO, consumer, git, isolate_inherited_git_environment, package,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def user_site_python(tmp_path):
    """Use real PyYAML in a private user site, with global packages unavailable."""
    base = getattr(sys, '_base_executable', sys.executable)
    home = tmp_path / 'user-home'
    env = dict(os.environ, HOME=str(home), APPDATA=str(home / 'AppData'))
    environment = tmp_path / 'python-env'
    subprocess.run([base, '-m', 'venv', '--without-pip', '--system-site-packages', str(environment)],
                   check=True, env=env, capture_output=True)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    paths = json.loads(subprocess.check_output([
        str(python), '-E', '-P', '-c',
        'import json, site, sysconfig; print(json.dumps([site.getusersitepackages(), '
        'sysconfig.get_path("purelib"), site.getsitepackages()]))'], env=env, text=True))
    user_site, local_site, global_sites = paths
    parser = Path(user_site) / 'yaml'
    shutil.copytree(Path(yaml.__file__).parent, parser)
    # venv must enable the user site. Remove its inherited global package paths
    # after site initialization so a machine-wide PyYAML cannot mask the defect.
    excluded = [str(Path(path).resolve()) for path in global_sites
                if Path(path).resolve() != Path(local_site).resolve()]
    (Path(local_site) / 'sitecustomize.py').write_text(
        f'import os, sys\nexcluded = {excluded!r}\n'
        'sys.path[:] = [p for p in sys.path if os.path.realpath(p) not in excluded]\n',
        encoding='utf-8')
    probe = 'import yaml; print(yaml.__file__)'
    available = subprocess.run([str(python), '-E', '-P', '-c', probe], env=env,
                               capture_output=True, text=True)
    assert available.returncode == 0, available.stderr
    assert Path(available.stdout.strip()).resolve() == (parser / '__init__.py').resolve()
    isolated = subprocess.run([str(python), '-I', '-c', probe], env=env,
                              capture_output=True, text=True)
    assert isolated.returncode != 0 and 'No module named' in isolated.stderr
    return python, env


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('stage', ['push', 'staged'])
def test_snapshot_launchers_keep_user_site_and_reject_checkout_imports(
        consumer, package, passive_probe, user_site_python, shell, stage):
    python, user_env = user_site_python
    env, trace = passive_probe
    env.update({key: user_env[key] for key in ('HOME', 'APPDATA')})
    # Pin interpreter selection, while exercising the real shell launch flags,
    # Python snapshot runner, configuration loader and scanner re-entry.
    common = package / f'hooks/lib/common.{shell}'
    override = (f'\nfind_python() {{ printf "%s" "{python.as_posix()}"; }}\n' if shell == 'sh' else
                f"\nfunction Find-WorkingPython {{ '{python.as_posix()}' }}\n")
    common.write_text(common.read_text(encoding='utf-8') + override, encoding='utf-8', newline='\n')
    if stage == 'staged':
        # This runner currently uses only stdlib imports. Probe the same parser
        # availability contract at entry before continuing through its real scan.
        runner = package / 'hooks/pre-commit.py'
        runner.write_text('import yaml\n' + runner.read_text(encoding='utf-8'), encoding='utf-8')
    (consumer / 'main.tf').write_text('# selected source\n', encoding='utf-8')
    (consumer / 'scan-config.yaml').write_text('global:\n  local_hooks_enabled: true\n', encoding='utf-8')
    git(consumer, 'add', 'main.tf', 'scan-config.yaml')
    if stage == 'push':
        git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture policy')
    marker = consumer / 'import-marker'
    malicious = (f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported")\n'
                 'raise AssertionError("checkout import")\n')
    for folder in (consumer, package / 'hooks'):
        for module in ('yaml', 'argparse'):
            (folder / f'{module}.py').write_text(malicious, encoding='utf-8')
    env['PYTHONPATH'] = str(consumer)
    hook = 'trivy-iac-full' if stage == 'push' else 'trivy-iac-critical'
    transaction = (f'refs/heads/main {git(consumer, "rev-parse", "HEAD")} '
                   f'refs/heads/main {ZERO}\n') if stage == 'push' else ''
    result = subprocess.run(wrapper_command(package, shell, hook), cwd=consumer, env=env,
                            input=transaction, capture_output=True, text=True, encoding='utf-8')
    assert not marker.exists(), result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert any('main.tf' in json.loads(line)['files'] for line in trace.read_text().splitlines())


@pytest.mark.parametrize('operation', ['New-Item', 'Set-Content'])
def test_autofix_write_errors_terminate_before_reporting_results(tmp_path, operation):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell unavailable')
    # Advanced-function common parameters reproduce cmdlets' nonterminating
    # errors under Continue and their terminating errors with ErrorAction Stop.
    parameters = ('[string]$ItemType, [string]$Path, [switch]$Force' if operation == 'New-Item' else
                  '[Parameter(ValueFromPipeline)]$Value, [string]$Path, [string]$Encoding')
    script = (ROOT / 'scripts/scan-and-fix.ps1').as_posix()
    command = f"""
function trivy {{ $global:LASTEXITCODE=1 }}
function {operation} {{
    [CmdletBinding()] param({parameters})
    process {{ Write-Error 'injected findings write failure' }}
}}
try {{ & '{script}' -ScanType secrets -AutoFix }}
catch {{ Write-Output ('caught write failure: ' + $_.Exception.Message); exit 17 }}
"""
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command], cwd=tmp_path,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 17, result.stdout + result.stderr
    assert 'caught write failure: injected findings write failure' in result.stdout
    assert '[scan-and-fix] FAIL' not in result.stdout
    assert not (tmp_path / '.claude/scan-findings.json').exists()


@pytest.mark.parametrize('entrypoint', ['dispatcher', 'installed-adapter'])
def test_push_adapters_keep_user_site_and_reject_checkout_imports(
        consumer, package, passive_probe, user_site_python, tmp_path, entrypoint):
    python, user_env = user_site_python
    env, trace = passive_probe
    env.update({key: user_env[key] for key in ('HOME', 'APPDATA')})
    binary = tmp_path / 'python-bin'
    binary.mkdir()
    for name in ('python3', 'python', 'py'):
        wrapper = binary / name
        wrapper.write_text(f'#!/usr/bin/env bash\nexec "{python.as_posix()}" "$@"\n',
                           encoding='utf-8', newline='\n')
        wrapper.chmod(0o755)
    env['PATH'] = str(binary) + os.pathsep + env['PATH']
    common = package / 'hooks/lib/common.sh'
    common.write_text(common.read_text(encoding='utf-8') +
                      f'\nfind_python() {{ printf "%s" "{python.as_posix()}"; }}\n',
                      encoding='utf-8', newline='\n')
    (consumer / 'main.tf').write_text('# selected source\n', encoding='utf-8')
    (consumer / 'scan-config.yaml').write_text('local_hooks_enabled: true\n', encoding='utf-8')
    (consumer / '.pre-commit-config.yaml').write_text(yaml.safe_dump({'repos': [{
        'repo': 'local', 'hooks': [{'id': 'trivy-iac-full', 'language': 'system',
                                  'entry': 'bash hooks/dispatcher.sh trivy-iac-full',
                                  'stages': ['pre-push']}]}]}), encoding='utf-8')
    git(consumer, 'add', 'main.tf', 'scan-config.yaml', '.pre-commit-config.yaml')
    git(consumer, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture policy')
    command = wrapper_command(package, 'sh', 'dispatcher') + [
        'pre-push', '--hooks', 'trivy-iac-full', '--shell', 'sh']
    script_dir = package / 'hooks'
    if entrypoint == 'installed-adapter':
        script_dir = consumer / 'hooks'
        shutil.copytree(package / 'hooks', script_dir)
        adapter = consumer / '.git/hooks/pre-push'
        # A minimal recognized saved runner avoids depending on an installed
        # runner package, while exercising installation, filtering and chaining.
        adapter.write_text('#!/usr/bin/env bash\n# File generated by pre-commit\n'
                           'ARGS=(hook-impl --config=.pre-commit-config.yaml)\n'
                           '# end templated\nexit 0\n', encoding='utf-8', newline='\n')
        installed = subprocess.run([str(python), '-E', '-P', str(script_dir / 'pre-push.py'),
                                    '--install-pre-commit'], cwd=consumer, env=env,
                                   capture_output=True, text=True, encoding='utf-8')
        assert installed.returncode == 0, installed.stdout + installed.stderr
        command = [command[0], str(adapter), '--shell', 'sh']
    marker = consumer / 'import-marker'
    malicious = (f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported")\n'
                 'raise AssertionError("checkout import")\n')
    for folder in (consumer, script_dir):
        # sitecustomize also detects an unsafe interpreter-availability probe,
        # which executes before the generated adapter starts the actual runner.
        for module in ('sitecustomize', 'argparse', 'yaml'):
            (folder / f'{module}.py').write_text(malicious, encoding='utf-8')
    env['PYTHONPATH'] = str(consumer)
    transaction = f'refs/heads/main {git(consumer, "rev-parse", "HEAD")} refs/heads/main {ZERO}\n'
    result = subprocess.run(command, cwd=consumer, env=env, input=transaction,
                            capture_output=True, text=True, encoding='utf-8')
    assert not marker.exists(), result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert any('main.tf' in json.loads(line)['files'] for line in trace.read_text().splitlines())
