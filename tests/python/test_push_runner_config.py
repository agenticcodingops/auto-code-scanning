"""The push adapter must filter the saved runner's configuration."""
import json
import shutil
import subprocess
import sys

import pytest
import yaml

from tests.python.test_validation_targets import (
    ZERO, consumer, git, isolate_inherited_git_environment, load_push_runner, package, scanner,
)


@pytest.mark.parametrize('arguments,expected', [
    ('hook-impl --config=push.yaml --hook-type=pre-push', 'push.yaml'),
    ("hook-impl --config 'push configs/team.yaml'", 'push configs/team.yaml'),
    ('hook-impl -c push.yaml', 'push.yaml'),
    ('hook-impl --config=old.yaml --config=new.yaml', 'new.yaml'),
    ('hook-impl', '.pre-commit-config.yaml'),
])
def test_runner_configuration_reads_literal_arguments(package, arguments, expected):
    source = f'ARGS=({arguments})\n# end templated\nARGS+=(--config ignored.yaml)\n'
    assert load_push_runner(package).runner_configuration(source) == expected


@pytest.mark.parametrize('source', [
    'ARGS=(hook-impl)\n', '# end templated\n',
    'ARGS=(hook-impl --config)\n# end templated\n',
    'ARGS=(hook-impl --config=)\n# end templated\n',
])
def test_runner_configuration_rejects_incomplete_template(package, source):
    with pytest.raises(ValueError):
        load_push_runner(package).runner_configuration(source)


@pytest.mark.parametrize('default', ['empty', 'missing'])
@pytest.mark.parametrize('shell', ['sh', 'ps1'])
def test_saved_runner_alternate_config_runs_adapted_and_other_hooks(consumer, package, scanner, default, shell):
    if not shutil.which('pre-commit'):
        pytest.skip('pre-commit unavailable')
    shutil.copytree(package / 'hooks', consumer / 'hooks')
    if default == 'empty':
        (consumer / '.pre-commit-config.yaml').write_text('repos: []\n')
    other = {'id': 'other-push', 'name': 'other push', 'language': 'system',
             'entry': 'python -c "from pathlib import Path; Path(\'other-ran\').write_text(\'yes\')"',
             'always_run': True, 'stages': ['pre-push'], 'pass_filenames': False}
    config = {'repos': [
        {'repo': 'https://github.com/agenticcodingops/auto-code-scanning', 'rev': 'unused',
         'hooks': [{'id': 'dotnet-build'}]},
        {'repo': 'local', 'hooks': [other]},
    ]}
    alternate = consumer / "push configs/team's push.yaml"
    alternate.parent.mkdir()
    alternate.write_text(yaml.safe_dump(config))
    # Exercise both relative and absolute paths recorded by the real installer.
    config_arg = alternate.relative_to(consumer) if default == 'empty' else alternate
    installed = subprocess.run(['pre-commit', 'install', '--hook-type', 'pre-push', '--config', str(config_arg)],
                               cwd=consumer, text=True, capture_output=True)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    original = (consumer / '.git/hooks/pre-push').read_bytes()
    runner = consumer / 'hooks/pre-push.py'
    installed = subprocess.run([sys.executable, str(runner), '--install-pre-commit'],
                               cwd=consumer, text=True, capture_output=True)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    env, trace = scanner
    oid = git(consumer, 'rev-parse', 'HEAD')
    result = subprocess.run([sys.executable, str(runner), '--pre-commit-runner', '--shell', shell, 'origin', 'fixture'],
                            cwd=consumer, env=env, text=True, capture_output=True,
                            input=f'refs/heads/main {oid} refs/heads/main {ZERO}\n')
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    assert [json.loads(line) for line in trace.read_text().splitlines()] == [{'App.cs': 'pushed bytes\n'}]
    assert (consumer / 'other-ran').read_text() == 'yes'
    assert yaml.safe_load(alternate.read_text()) == config
    assert (consumer / '.git/hooks/pre-push.pre-commit').read_bytes() == original
    assert (consumer / '.pre-commit-config.yaml').exists() == (default == 'empty')
