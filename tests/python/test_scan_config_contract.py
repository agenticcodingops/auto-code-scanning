"""Shipped configs hold only keys with readers, and configs from earlier releases still validate."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import jsonschema
import pytest
import yaml

from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ['scan-config.yaml', *(f'templates/scan-config/{tier}.yaml' for tier in ('starter', 'standard', 'strict')),
           'examples/app-repo/scan-config.yaml', 'examples/terraform-repo/scan-config.yaml']
DETECT = '.github/workflows/code-security-scan.yml'
LOOP = '.github/workflows/autonomous-fix.yml'
VERIFY = 'scripts/verify-scanning.ps1'

# Each key a shipped config may contain, the file that reads it, and the text that does the reading.
READERS = {
    'global.local_hooks_enabled': ('hooks/pre-push.py', "get('local_hooks_enabled'"),
    'languages.terraform.enabled': (VERIFY, "languages['terraform']['enabled']"),
    'languages.csharp.enabled': ('scripts/scan-and-fix.ps1', "-Key 'languages.csharp.enabled'"),
    'languages.typescript.enabled': (DETECT, '(langs.get(l) or {}).get("enabled")'),
    'languages.sql.enabled': (VERIFY, "value.get('enabled') is True"),
    'languages.csharp.build.solution': ('hooks/dotnet-build.sh', 'languages.csharp.build.solution'),
    'languages.csharp.build.working_dir': ('hooks/dotnet-build.sh', 'languages.csharp.build.working_dir'),
    'languages.typescript.build.working_dir': ('hooks/eslint.sh', 'languages.typescript.build.working_dir'),
    'ci.sarif.category_prefix': (DETECT, '.get("category_prefix")'),
    'suppressions.file': ('scripts/scan_policy.py', 'section.get("file", name)'),
    'fix_loop.enabled': (LOOP, 'fl.get("enabled"'),
    'fix_loop.human_review_label': (LOOP, 'fl.get("human_review_label"'),
    'fix_loop.max_turns': (LOOP, 'fl.get("max_turns"'),
    'fix_loop.max_iterations': (LOOP, 'fl.get("max_iterations"'),
    'fix_loop.build_verify_cmd': (LOOP, 'fl.get("build_verify_cmd"'),
    'fix_loop.allowlist_paths': ('scripts/check-fix-allowlist.py', 'fix_loop.get("allowlist_paths")'),
    'fix_loop.gated_paths': ('scripts/check-fix-allowlist.py', 'fix_loop.get("gated_paths")'),
}
# Shape only: the schema requires the version and the action mirror; the check list is this repository's note.
INFORMATIONAL = {'schema_version', 'fix_loop.claude_code_action_ref', 'ci.required_checks'}

# Every kind of key that earlier releases generated and nothing reads.
OLD = {
    'schema_version': '1.0',
    'global': {'results_dir': '.scan-results', 'severity_levels': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
               'blocking_severities': ['CRITICAL'], 'exclude_paths': ['.git'],
               'performance': {'pre_commit_max_seconds': 10, 'pre_push_max_seconds': 60, 'per_hook_max_seconds': 5}},
    'languages': {'terraform': {
        'enabled': True, 'description': 'old', 'file_patterns': ['**/*.tf'], 'exclude_patterns': ['**/bin/**'],
        'tools': {'trivy': {'enabled': True, 'description': 'old', 'config_file': '.trivyignore', 'auto_fix': False,
                            'args': ['--quiet'], 'stage': 'pre-commit', 'full_scan_stage': 'pre-push',
                            'version': '0.69.2'}}},
        'kubernetes': {'enabled': False, 'tools': {'kube_linter': {'enabled': True}}}},
    'ci': {'workflow_file': '.github/workflows/scan.yml', 'sarif_upload': True, 'fail_on': ['CRITICAL']},
    'reporting': {'format': 'json', 'sarif': True, 'retention_days': 90,
                  'metrics': {'enabled': True, 'targets': {'bypass_rate_max': 5.0}}},
    'suppressions': {'file': '.scan-suppressions.yaml', 'max_duration_days': 180,
                     'require_approval': ['CRITICAL'], 'review_frequency_days': 90},
}
LANGUAGE = ('$defs', 'language', 'properties')
TOOL = ('$defs', 'tool', 'properties')
GLOBAL = ('properties', 'global', 'properties')
CI = ('properties', 'ci', 'properties')
IGNORED = [
    *(GLOBAL + (key,) for key in ('results_dir', 'severity_levels', 'blocking_severities', 'performance',
                                  'exclude_paths')),
    *(LANGUAGE + (key,) for key in ('description', 'file_patterns', 'exclude_patterns', 'tools')),
    *(TOOL + (key,) for key in ('enabled', 'version', 'description', 'config_file', 'auto_fix', 'args', 'stage',
                                'full_scan_stage')),
    *(CI + (key,) for key in ('workflow_file', 'sarif_upload', 'fail_on')),
    ('properties', 'reporting'),
    *(('properties', 'suppressions', 'properties', key)
      for key in ('max_duration_days', 'require_approval', 'review_frequency_days')),
]


def schema():
    return json.loads((ROOT / 'schemas/scan-config.schema.json').read_text(encoding='utf-8'))


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f'{prefix}.{key}' if prefix else key)
    else:
        yield prefix


@pytest.mark.parametrize('name', CONFIGS)
def test_shipped_configs_hold_only_keys_with_readers(name):
    config = yaml.safe_load((ROOT / name).read_text(encoding='utf-8'))
    assert set(leaves(config)) - set(READERS) - INFORMATIONAL == set()
    jsonschema.Draft202012Validator(schema()).validate(config)


@pytest.mark.parametrize('key', sorted(READERS))
def test_each_listed_key_is_still_read(key):
    path, literal = READERS[key]
    assert literal in (ROOT / path).read_text(encoding='utf-8')


def test_earlier_configs_still_validate():
    jsonschema.Draft202012Validator(schema()).validate(OLD)


@pytest.mark.parametrize('path', IGNORED, ids='.'.join)
def test_ignored_keys_are_marked_deprecated(path):
    node = schema()
    for part in path:
        node = node[part]
    assert node['deprecated'] is True
    assert node['description'].startswith('Ignored: nothing reads it')


@pytest.mark.parametrize('path,bad', [
    (('global', 'results_dir'), 5),
    (('global', 'blocking_severities'), ['SEVERE']),
    (('global', 'performance', 'per_hook_max_seconds'), 0),
    (('global', 'exclude_paths'), '.git'),
    (('languages', 'terraform', 'file_patterns'), '**/*.tf'),
    (('languages', 'terraform', 'tools', 'trivy', 'enabled'), 'yes'),
    (('languages', 'terraform', 'tools', 'trivy', 'stage'), 'nightly'),
    (('ci', 'sarif_upload'), 'yes'),
    (('ci', 'fail_on'), ['SEVERE']),
    (('reporting',), []),
])
def test_ignored_keys_keep_their_type_checks(path, bad):
    config = copy.deepcopy(OLD)
    node = config
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = bad
    assert list(jsonschema.Draft202012Validator(schema()).iter_errors(config))


@pytest.mark.parametrize('example,languages', [('app-repo', 'csharp,typescript'), ('terraform-repo', 'terraform')])
def test_examples_equal_renderer_output(tmp_path, example, languages):
    out = tmp_path / 'scan-config.yaml'
    subprocess.run([sys.executable, str(ROOT / 'scripts/render-scan-config.py'), '--tier', 'starter',
                    '--languages', languages, '--templates-dir', str(ROOT / 'templates/scan-config'),
                    '--out', str(out)], check=True, capture_output=True)
    shipped = (ROOT / 'examples' / example / 'scan-config.yaml').read_bytes()
    assert out.read_bytes().replace(b'\r\n', b'\n') == shipped.replace(b'\r\n', b'\n')


@pytest.mark.parametrize('hook,tool,filename', [
    ('semgrep-typescript', 'semgrep', 'app.ts'),
    ('sqlfluff', 'sqlfluff', 'query.sql'),
])
def test_disabled_language_does_not_switch_its_local_hook_off(tmp_path, hook, tool, filename):
    """Issue #157: `enabled` selects hosted languages; honouring it here would stop blocking."""
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash unavailable')
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    subprocess.run(['git', 'init', '-q', str(consumer)], check=True)
    (consumer / filename).write_text('x\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(consumer), 'add', filename], check=True)
    config = consumer / 'scan-config.yaml'
    config.write_text((ROOT / 'templates/scan-config/starter.yaml').read_text(encoding='utf-8'), encoding='utf-8')
    assert not any(value['enabled'] for value in yaml.safe_load(config.read_text(encoding='utf-8'))['languages'].values())
    application(tmp_path / 'tools', tool, 'import sys\nsys.exit(1)\n')
    env = dict(os.environ, SCAN_CONFIG_FILE=config.as_posix(),
               PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'])
    env.pop('SCAN_ALLOW_TOOL_ERRORS', None)
    result = subprocess.run([bash, (ROOT / 'hooks/dispatcher.sh').as_posix(), hook], cwd=consumer, env=env,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    assert result.returncode != 0, result.stdout + result.stderr
