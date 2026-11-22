"""One input table exercised through the reporting entry points.

The checked-in fixture records exits from the unmodified implementation. Case
folding and non-string failures are deliberate compatibility exceptions.
"""
import copy
from datetime import date, timedelta
import itertools
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

import jsonschema
import pytest

import scan
from finalize_baseline import finalize
from scan_policy import occurrence_fingerprint, apply_exceptions
from .tool_helpers import application

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name('severity_parity.json')
TABLE = json.loads(FIXTURE.read_text(encoding='utf-8'))
LEVELS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
FILTERS = [list(items) for size in range(1, 5)
           for items in itertools.combinations(LEVELS, size)]
AGENT_SCHEMA = jsonschema.Draft202012Validator(json.loads(
    (ROOT / 'schemas/last-scan.schema.json').read_text(encoding='utf-8')))


def report(tool, rows):
    findings = []
    for index, row in enumerate(rows):
        severity = {} if row.get('missing') else {'severity': row['value']}
        if tool == 'checkov':
            finding = dict(check_id=f'CKV_TEST_{index}', file_path=f'f{index}-{tool}.tf',
                           check_name='fixture', file_line_range=[1, 1], **severity)
        elif tool == 'trivy':
            finding = dict(ID=f'AVD-TEST-{index}', Title='fixture',
                           CauseMetadata=dict(StartLine=1, EndLine=1))
            if severity:
                finding['Severity'] = row['value']
        elif tool == 'tflint':
            finding = dict(rule=dict(name=f'terraform_test_{index}', **severity),
                           message='fixture', range=dict(filename=f'f{index}-{tool}.tf',
                           start=dict(line=1), end=dict(line=1)))
        else:
            finding = dict(id=f'SNYK-{index}', title='fixture', targetFile=f'f{index}-{tool}.tf',
                           lineNumber=1, **severity)
        findings.append(finding)
    if tool == 'checkov':
        return dict(results=dict(failed_checks=findings, skipped_checks=[]), summary=dict(skipped=0))
    if tool == 'trivy':
        return dict(Results=[dict(Target=f'f{i}-{tool}.tf', Misconfigurations=[f])
                             for i, f in enumerate(findings)])
    return {'issues' if tool == 'tflint' else 'infrastructureAsCodeIssues': findings}


def exit_of(call):
    try:
        call()
    except SystemExit as exc:
        return exc.code or 0
    except (TypeError, AttributeError):
        return 'crash'
    return 0


def ci_run(folder, monkeypatch, tool, rows, fail=True, secrets=False):
    paths = {'trivy': 'trivy-results/trivy-iac-results.json',
             'checkov': 'checkov-results/checkov-results.json',
             'tflint': 'tflint-results/tflint-results.json',
             'snyk': 'snyk-results/snyk-iac-results.json'}
    for name, relative in paths.items():
        target = folder / 'artifacts' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report(name, rows if name == tool and not secrets else [])), encoding='utf-8')
    secret = folder / 'artifacts/trivy-results/trivy-secrets-results.json'
    payload = report('trivy', rows if secrets else [])
    for result in payload['Results']:
        result['Secrets'] = result.pop('Misconfigurations')
        for finding in result['Secrets']:
            finding['RuleID'] = finding.pop('ID')
    secret.write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.chdir(folder)
    monkeypatch.setenv('ARTIFACT_ROOT', str(folder / 'artifacts'))
    monkeypatch.setenv('GITHUB_OUTPUT', str(folder / 'github-output'))
    monkeypatch.setenv('SCANNER_RESULTS', json.dumps({name: {'result': 'success'} for name in
                       ('setup', 'scan-trivy', 'scan-checkov', 'scan-tflint', 'scan-snyk')}))
    monkeypatch.setenv('ENABLE_SNYK', 'true')
    monkeypatch.setenv('FAIL_ON_FINDINGS', str(fail).lower())
    output = folder / '.scan-results/aggregated.json'
    output.unlink(missing_ok=True)
    code = exit_of(lambda: runpy.run_path(str(ROOT / 'scripts/aggregate_scan.py')))
    return code, json.loads(output.read_text()) if output.exists() else None


def scan_run(folder, monkeypatch, tool, rows, levels):
    monkeypatch.setattr(scan, 'run_cmd', lambda *args, **kwargs: (0, json.dumps(report(tool, rows)), ''))
    monkeypatch.setenv('SNYK_TOKEN', 'fixture-token')
    monkeypatch.setattr(sys, 'argv', ['scan.py', str(folder), '--tools', tool, '--format', 'json',
                                     '--severity', ','.join(levels), '--output-file', str(folder / 'scan.json')])
    output = folder / 'scan.json'
    output.unlink(missing_ok=True)
    code = exit_of(scan.main)
    return code, json.loads(output.read_text()) if output.exists() else None


def assert_summary(data):
    summary = data.get('summary', data)
    assert sum(summary['by_severity'].values()) == summary['total_findings']


def test_python_paths(tmp_path, monkeypatch, capsys):
    # Only process execution is stubbed: validation, parsing, filtering, policy,
    # report generation and the main exit branches all execute normally.
    application(tmp_path / 'tools', 'snyk', 'pass\n')
    monkeypatch.setenv('PATH', str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'])
    for tool, rows in TABLE['cases'].items():
        for row in rows:
            actual = {'ci': [], 'scan': []}
            for fail in (False, True):
                code, data = ci_run(tmp_path, monkeypatch, tool, [row], fail)
                actual['ci'].append(code)
                if data and data['scan_complete']:
                    assert data['findings'][0]['severity'] == row['ci_bucket']
                    assert_summary(data)
                    gate = Path(os.environ['GITHUB_OUTPUT']).read_text().splitlines()[-4:]
                    assert gate == [f'findings-count=1',
                                    f'critical-count={int(row["ci_bucket"] == "CRITICAL")}',
                                    f'high-count={int(row["ci_bucket"] == "HIGH")}',
                                    f'scan-passed={str(code == 0).lower()}']
            if tool != 'tflint':
                for levels in FILTERS:
                    code, data = scan_run(tmp_path, monkeypatch, tool, [row], levels)
                    actual['scan'].append(code)
                    if data:
                        assert_summary(data)
                        AGENT_SCHEMA.validate(data)
                        if data['findings']:
                            assert data['findings'][0]['severity'] == row['scan_bucket']
            assert actual == row['exits'], (tool, row, actual)
            capsys.readouterr()


def ps_run(command, folder, env=None):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell unavailable')
    return subprocess.run([shell, '-NoProfile', '-Command', command], cwd=folder,
                          env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)


def test_python_zero_and_many_findings(tmp_path, monkeypatch, capsys):
    application(tmp_path / 'tools', 'snyk', 'pass\n')
    monkeypatch.setenv('PATH', str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'])
    for tool, rows in TABLE['cases'].items():
        valid = [row for row in rows if row['exits']['ci'][0] == 0]
        for selected in ([], valid):
            _, data = ci_run(tmp_path, monkeypatch, tool, selected)
            assert_summary(data)
            assert data['total_findings'] == len(selected)
            if tool != 'tflint':
                _, data = scan_run(tmp_path, monkeypatch, tool, selected, LEVELS)
                assert_summary(data)
                assert data['summary']['total_findings'] == len(selected)
                AGENT_SCHEMA.validate(data)
            capsys.readouterr()


def test_ci_secret_severity_and_pinned_exit(tmp_path, monkeypatch, capsys):
    for row in TABLE['cases']['trivy']:
        for index, fail in enumerate((False, True)):
            code, data = ci_run(tmp_path, monkeypatch, 'trivy', [row], fail, secrets=True)
            assert code == row['exits']['ci'][index]
            assert_summary(data)
            if data['scan_complete']:
                assert data['findings'][0]['severity'] == row['ci_bucket']
            capsys.readouterr()


@pytest.mark.parametrize('size', [0, 1, 'many'])
def test_powershell_aggregator(tmp_path, size):
    selected = {}
    for tool, rows in TABLE['cases'].items():
        selected[tool] = rows if size == 'many' else rows[:size] if tool == 'checkov' else []
        (tmp_path / f'{tool}-fixture.json').write_text(json.dumps(report(tool, selected[tool])), encoding='utf-8')
    result = ps_run(f"& '{ROOT.as_posix()}/scripts/aggregate-scan-results.ps1' -OutputPath '{tmp_path.as_posix()}' | Out-Null", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(next(tmp_path.glob('unified-results-*.json')).read_text(encoding='utf-8-sig'))
    assert isinstance(data['findings'], list)
    assert_summary(data)
    assert data['summary']['total_findings'] == sum(map(len, selected.values()))
    jsonschema.validate(data, json.loads((ROOT / 'schemas/unified-results.schema.json').read_text()))
    for finding in data['findings']:
        index = int(finding['file'].split('-')[0][1:])
        assert finding['severity'] == selected[finding['tool']][index]['ps_bucket']


def test_baseline_normalization_preserves_identity(tmp_path):
    entries = []
    for tool, rows in TABLE['cases'].items():
        for row in rows:
            file = f'f{len(entries)}.tf'
            (tmp_path / file).write_text('# fixture\n', encoding='utf-8')
            entry = dict(tool=tool, rule_id='TEST', file=file, line=1, end_line=1)
            if not row.get('missing'):
                entry['severity'] = row['value']
            entries.append(entry)
    before = [occurrence_fingerprint(e, tmp_path) for e in entries]
    data = finalize(dict(entries=copy.deepcopy(entries)), tmp_path)
    assert [e['fingerprint'] for e in data['entries']] == before
    index = 0
    for tool, rows in TABLE['cases'].items():
        for row in rows:
            assert data['entries'][index]['severity'] == row['baseline_bucket']
            index += 1


@pytest.mark.parametrize('backend', ['jq', 'python'])
def test_bash_count_backends_execute_the_shared_table(backend):
    # Exercise the actual embedded programs even on hosts that cannot start Bash.
    source = (ROOT / 'hooks/lib/common.sh').read_text(encoding='utf-8')
    definitions = source.split("SCAN_SEVERITY_JQ='\n", 1)[1].split("\n'\n", 1)[0]
    query = source.split('"$SCAN_SEVERITY_JQ"\'\n', 1)[1].split("\n        '", 1)[0]
    python = source.split('"$py" -I -c \'\nimport json, sys\n', 1)[1].split("\n' \"$tool\"", 1)[0]
    for tool, rows in TABLE['cases'].items():
        for size in (0, 1, len(rows)):
            selected = rows[:size]
            if backend == 'jq':
                executable = shutil.which('jq')
                if not executable:
                    pytest.skip('jq unavailable; Python fallback is tested separately')
                command = [executable, '-r', '--arg', 'tool', tool, '--arg', 'kind', 'Misconfigurations', definitions + query]
            else:
                command = [sys.executable, '-c', 'import json, sys\n' + python, tool, 'Misconfigurations']
            result = subprocess.run(command, input=json.dumps(report(tool, selected)), capture_output=True,
                                    text=True, encoding='utf-8', timeout=20)
            assert result.returncode == 0, result.stderr
            counts = list(map(int, result.stdout.split()))
            assert counts == [sum(row['sh_bucket'] == level for row in selected) for level in LEVELS]
            assert sum(counts) == size


def test_normalization_preserves_baseline_and_suppression_matches(tmp_path):
    import yaml
    (tmp_path / 'main.tf').write_text('# fixture\n', encoding='utf-8')
    baseline = tmp_path / '.scan-baseline'
    baseline.mkdir()
    for tool, rows in TABLE['cases'].items():
        for row in rows:
            raw = row['value']
            if not isinstance(raw, str) or row['exits']['ci'][0] != 0:
                continue
            rule = {'checkov': 'CKV_TEST_1', 'trivy': 'AVD-TEST-1',
                    'tflint': 'terraform_test', 'snyk': 'SNYK-TEST-1'}[tool]
            old_severity = raw
            if tool == 'checkov':
                old_severity = raw.upper() if raw else 'HIGH'
            elif tool == 'tflint':
                old_severity = {'error': 'HIGH', 'warning': 'MEDIUM', 'notice': 'LOW'}.get(raw, 'MEDIUM')
            elif tool == 'snyk':
                old_severity = raw.upper() if raw in ('critical', 'high', 'medium', 'low') else 'MEDIUM'
            finding = dict(tool=tool, rule_id=rule, file='main.tf', line=1,
                           end_line=1, severity=old_severity)
            normalized = dict(finding, severity=row['ci_bucket'])
            fingerprint = occurrence_fingerprint(finding, tmp_path)
            (baseline / 'baseline.json').write_text(json.dumps(dict(
                schema_version='2.0', entries=[dict(finding, fingerprint=fingerprint)])), encoding='utf-8')
            entry = dict(tool=tool, rule_id=rule, fingerprint=fingerprint,
                         severity='MEDIUM', reason='Reviewed fixture occurrence', owner='fixture',
                         approved_date=date.today().isoformat(),
                         expires_date=(date.today() + timedelta(days=60)).isoformat())
            (tmp_path / '.scan-suppressions.yaml').write_text(yaml.safe_dump(dict(
                schema_version='2.0', **{f'{tool}_suppressions': [entry]})), encoding='utf-8')
            # No approval for HIGH/CRITICAL: normalization must not alter whether
            # this deliberately lower-severity approval matches.
            old = copy.deepcopy(finding)
            apply_exceptions([old], tmp_path, tmp_path)
            apply_exceptions([normalized], tmp_path, tmp_path)
            for field in ('fingerprint', 'baseline', 'suppressed'):
                assert normalized[field] == old[field], (tool, raw, field)


@pytest.mark.parametrize('tool', ['checkov', 'trivy', 'tflint'])
def test_create_baseline_stores_and_counts_normalized_severity(tmp_path, tool):
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    subprocess.run(['git', 'init', '-q', str(consumer)], check=True)
    rows = [row for row in TABLE['cases'][tool]
            if not isinstance(row['value'], (int, list)) and
            (tool != 'tflint' or row['value'] is not None) and  # fails: see the next test
            (tool != 'trivy' or row['value'] in LEVELS + ['UNKNOWN'])]
    for index in range(len(rows)):
        (consumer / f'f{index}-{tool}.tf').write_text('# fixture\n', encoding='utf-8')
    payload = report(tool, rows)
    application(tmp_path / 'tools', tool,
                'import os\nprint(os.environ["PARITY_REPORT"])\n')
    config = tmp_path / 'trusted.hcl'
    config.write_text('# fixture\n', encoding='utf-8')
    env = dict(os.environ, PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'],
               PARITY_REPORT=json.dumps(payload), SCAN_TFLINT_CONFIG=str(config),
               SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'))
    result = ps_run(f"& '{ROOT.as_posix()}/scripts/create-baseline.ps1' -Tool {tool} -CloudProvider aws -Force", consumer, env)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((consumer / '.scan-baseline/baseline.json').read_text(encoding='utf-8-sig'))
    assert [entry['severity'] for entry in data['entries']] == [row['baseline_bucket'] for row in rows]
    counts = {level: int(re.search(rf'\b{level}:\s+(\d+)', result.stdout)[1]) for level in LEVELS}
    assert sum(counts.values()) == len(rows)


@pytest.mark.parametrize('row', [{'value': None, 'missing': True}, {'value': None}], ids=['absent', 'null'])
def test_create_baseline_still_fails_without_a_tflint_severity(tmp_path, row):
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    subprocess.run(['git', 'init', '-q', str(consumer)], check=True)
    (consumer / 'f0-tflint.tf').write_text('# fixture\n', encoding='utf-8')
    application(tmp_path / 'tools', 'tflint', 'import os\nprint(os.environ["PARITY_REPORT"])\n')
    config = tmp_path / 'trusted.hcl'
    config.write_text('# fixture\n', encoding='utf-8')
    env = dict(os.environ, PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'],
               PARITY_REPORT=json.dumps(report('tflint', [row])), SCAN_TFLINT_CONFIG=str(config),
               SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'))
    result = ps_run(f"& '{ROOT.as_posix()}/scripts/create-baseline.ps1' -Tool tflint -CloudProvider aws -Force",
                    consumer, env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'tflint reported a finding without a severity' in ' '.join((result.stdout + result.stderr).split())


@pytest.mark.parametrize('shell', ['sh', 'ps1'])
@pytest.mark.parametrize('hook,tool', [('checkov', 'checkov'), ('checkov-strict', 'checkov'),
    ('trivy-iac-full', 'trivy'), ('trivy-secrets', 'trivy'), ('tflint', 'tflint'), ('snyk-iac', 'snyk')])
def test_hook_summary_and_exit(tmp_path, shell, hook, tool):
    executable = shutil.which('bash' if shell == 'sh' else 'pwsh')
    if not executable:
        pytest.skip('Shell unavailable')
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    subprocess.run(['git', 'init', '-q', str(consumer)], check=True)
    (consumer / 'main.tf').write_text('# fixture\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(consumer), 'add', 'main.tf'], check=True)
    rows = TABLE['cases'][tool]
    payload = report(tool, rows)
    if hook == 'trivy-secrets':
        for result in payload['Results']:
            result['Secrets'] = result.pop('Misconfigurations')
            result['Secrets'][0]['RuleID'] = result['Secrets'][0].pop('ID')
    application(tmp_path / 'tools', tool,
        'import os,sys\nprint(os.environ["PARITY_REPORT"])\n'
        'sys.exit(0 if "--init" in sys.argv or "whoami" in sys.argv else int(os.environ["PARITY_EXIT"]))\n')
    config = tmp_path / 'trusted.hcl'
    config.write_text('# fixture\n', encoding='utf-8')
    env = dict(os.environ, PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'],
               SCAN_LEGACY_PUSH_STATE='1', SCAN_TFLINT_CONFIG=str(config),
               SCAN_TFLINT_PLUGIN_DIR=str(tmp_path / 'plugins'), SNYK_TOKEN='fixture-token',
               PARITY_REPORT=json.dumps(payload), SCAN_HOOK_ID='parity')
    path = ROOT / f'hooks/{hook}.{shell}'
    command = ([executable, str(path)] if shell == 'sh' else
               [executable, '-NoProfile', '-Command', f"& '{path.as_posix()}'; exit $LASTEXITCODE"])
    for status in (0, 1, 2, 3):
        output_file = consumer / '.scanning/last-scan.json'
        output_file.unlink(missing_ok=True)
        env['PARITY_EXIT'] = str(status)
        result = subprocess.run(command, cwd=consumer, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=120)
        # Captured before implementation: findings -> 1; operational errors -> 1;
        # success -> 0. TFLint alone uses status 2 for findings.
        expected = TABLE['hook_exits'][hook][str(status)]
        assert result.returncode == expected, result.stdout + result.stderr
        if status == (2 if tool == 'tflint' else 1):
            data = json.loads(output_file.read_text(encoding='utf-8-sig'))
            AGENT_SCHEMA.validate(data)
            assert_summary(data)
            buckets = {level: sum(row['ps_bucket' if shell == 'ps1' else 'sh_bucket'] == level for row in rows)
                       for level in LEVELS}
            summary = (f"{len(rows)} findings ({buckets['CRITICAL']} critical, {buckets['HIGH']} high, "
                       f"{buckets['MEDIUM']} medium, {buckets['LOW']} low)")
            assert summary in result.stdout, result.stdout + result.stderr
            assert data['summary']['total_findings'] == len(rows)
            for index, row in enumerate(rows):
                rule = {'checkov': f'CKV_TEST_{index}', 'trivy': f'AVD-TEST-{index}',
                        'tflint': f'terraform_test_{index}', 'snyk': f'SNYK-{index}'}[tool]
                bucket = row['ps_bucket' if shell == 'ps1' else 'sh_bucket']
                assert re.search(rf'\b{bucket}\s+{re.escape(rule)}\s', result.stdout), (tool, row, result.stdout)


@pytest.mark.parametrize('emitted,expected', [
    (b'1\t2\t3\t4\r\n', '1 2 3 4 10'),  # native Windows tools end lines with CRLF
    (b'1\t2\t3\t4\n', '1 2 3 4 10'),
    (b'', '0 0 0 0 0'),                  # jq prints nothing for empty scanner output
    (b'not counts\n', '0 0 0 0 0'),
    (b'1\t2\n', '0 0 0 0 0'),
])
def test_bash_counts_are_always_four_integers(tmp_path, emitted, expected):
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash unavailable')
    application(tmp_path / 'tools', 'jq',
                f'import sys\nsys.stdin.read()\nsys.stdout.buffer.write({emitted!r})\n')
    env = dict(os.environ, PATH=str(tmp_path / 'tools') + os.pathsep + os.environ['PATH'])
    # The hooks use exactly this form under set -e: a short read or a stray CR ends the hook.
    script = ('set -euo pipefail\nsource hooks/lib/common.sh\n'
              'read -r c h m l < <(scanner_severity_counts "{}" checkov)\n'
              'echo "counts=$c $h $m $l $((c + h + m + l))"\n')
    result = subprocess.run([bash, '-c', script], cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'counts={expected}' in result.stdout


def test_count_fallback_never_imports_from_the_scanned_checkout(tmp_path):
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash unavailable')
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
    marker = tmp_path / 'consumer-code-executed'
    (checkout / 'json.py').write_text(f'open({str(marker)!r}, "w").close()\n', encoding='utf-8')
    script = ('set -euo pipefail\n'
              f'source "{(ROOT / "hooks/lib/common.sh").as_posix()}"\n'
              # jq is optional: take the Python fallback whether or not this host has it.
              'command() { if [[ "${1:-}" == -v && "${2:-}" == jq ]]; then return 1; fi; builtin command "$@"; }\n'
              'scanner_severity_counts "$PARITY_REPORT" checkov\n')
    env = dict(os.environ, PARITY_REPORT=json.dumps(report('checkov', [{'value': None}])))
    result = subprocess.run([bash, '-c', script], cwd=checkout, env=env, capture_output=True,
                            text=True, encoding='utf-8', timeout=90)
    assert not marker.exists(), 'the hook imported json.py from the scanned repository'
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.split() == ['0', '1', '0', '0']


@pytest.mark.parametrize('script', ['aggregate-scan-results.ps1', 'create-baseline.ps1'])
def test_partly_vendored_library_fails_loudly(tmp_path, script):
    package = tmp_path / 'package'
    for folder in ('hooks', 'scripts'):
        shutil.copytree(ROOT / folder, package / folder, ignore=shutil.ignore_patterns('__pycache__'))
    library = package / 'hooks/lib/common.ps1'
    text = library.read_text(encoding='utf-8')
    library.write_text(text.replace('function Get-ScannerSeverity {', 'function Get-PreviousReleaseHelper {'),
                       encoding='utf-8')
    (tmp_path / 'checkov-fixture.json').write_text(
        json.dumps(report('checkov', [{'value': 'HIGH'}])), encoding='utf-8')
    arguments = (f"-OutputPath '{tmp_path.as_posix()}'" if script.startswith('aggregate')
                 else '-Tool trivy -CloudProvider aws -Force')
    result = ps_run(f"& '{(package / 'scripts' / script).as_posix()}' {arguments}", tmp_path)
    assert result.returncode != 0, 'a partly vendored install must not report a result'
    assert 're-vendor hooks/lib/common.ps1' in ' '.join((result.stdout + result.stderr).split())


def test_counts_run_no_text_utility_from_the_scanned_checkout(tmp_path):
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash unavailable')
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    marker = tmp_path / 'consumer-tool-executed'
    application(checkout / 'bin', 'tr', f'open({str(marker)!r}, "w").close()\n')
    script = ('set -euo pipefail\n'
              f'source "{(ROOT / "hooks/lib/common.sh").as_posix()}"\n'
              'PATH="$PWD/bin:$PATH"\n'
              'scanner_severity_counts "{}" checkov\n')
    result = subprocess.run([bash, '-c', script], cwd=checkout, capture_output=True,
                            text=True, encoding='utf-8', timeout=90)
    assert not marker.exists(), 'the hook ran a tr supplied by the scanned repository'
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.split() == ['0', '0', '0', '0']
