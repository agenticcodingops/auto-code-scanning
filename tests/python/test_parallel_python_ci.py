"""Keep the subprocess-heavy Python suite parallel in the self-test workflow."""
from importlib.util import cache_from_source
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


def test_shared_sources_are_compiled_before_workers_copy_them():
    # Setup tests copy the live hooks and scripts directories, some of them from
    # subprocesses. A worker publishing bytecode there mid-copy breaks the copy,
    # so the controller must leave nothing for a worker to publish.
    sources = [path for folder in ('hooks', 'scripts') for path in (ROOT / folder).rglob('*.py')
               if '__pycache__' not in path.parts]
    assert sources
    assert [str(path) for path in sources if not Path(cache_from_source(str(path))).is_file()] == []
