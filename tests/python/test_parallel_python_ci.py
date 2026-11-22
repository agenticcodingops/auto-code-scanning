"""Keep the subprocess-heavy Python suite parallel in the self-test workflow."""
from pathlib import Path
import re
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_python_ci_uses_pinned_xdist_and_work_stealing():
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))
    job = workflow['jobs']['test-scripts']
    steps = {step.get('name'): step for step in job['steps']}
    install = shlex.split(steps['Install Python test dependencies']['run'])
    plugins = [arg for arg in install if arg.startswith('pytest-xdist')]
    assert len(plugins) == 1 and re.fullmatch(r'pytest-xdist==\d+\.\d+\.\d+', plugins[0])
    commands = [shlex.split(line.strip())
                for line in steps['Run Python tests']['run'].splitlines()
                if line.strip().startswith('pytest ')]
    assert len(commands) == 1
    command = commands[0]
    assert 'tests/python/' in command
    assert command[command.index('-n') + 1] == 'auto'
    assert command[command.index('--dist') + 1] == 'worksteal'
    assert job['timeout-minutes'] == 25
