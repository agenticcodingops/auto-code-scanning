"""Regenerate trimmed records with Checkov 3.3.19 in an isolated environment."""
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main():
    assert importlib.metadata.version('checkov') == '3.3.19'
    for case, directory, rule in [('module-calls', 'module-calls', 'CKV_TF_1'),
                                  ('nested', 'nested', 'CKV_AZURE_110'),
                                  ('nested-module-calls', 'nested', 'CKV_TF_1')]:
        result = subprocess.run([
            sys.executable, str(Path(sys.executable).with_name('checkov')),
            '-d', str(ROOT / directory), '--framework', 'terraform',
            '--download-external-modules', 'false', '--skip-download',
            '--check', rule, '-o', 'json',
        ], capture_output=True, text=True, encoding='utf-8', check=False)
        assert result.returncode in (0, 1), result.stderr
        report = json.loads(result.stdout)
        documents = report if isinstance(report, list) else [report]
        trimmed = []
        for document in documents:
            # Keep all scanner-relative identity and location fields unchanged;
            # discard machine-specific absolute paths, code and descriptive metadata.
            checks = {}
            for kind in ('failed_checks', 'skipped_checks'):
                checks[kind] = [{key: value for key, value in record.items()
                                if key in ('check_id', 'check_result', 'resource', 'file_path',
                                           'file_line_range', 'caller_file_path',
                                           'caller_file_line_range')}
                               for record in document['results'][kind]]
            trimmed.append(dict(check_type=document['check_type'], results=checks,
                                summary=document['summary']))
        (ROOT / f'{case}.json').write_text(json.dumps(trimmed, indent=2) + '\n', encoding='utf-8')
        print(f'{case}: scanner exit {result.returncode}; '
              f'{sum(len(d["results"]["skipped_checks"]) for d in trimmed)} skips')


if __name__ == '__main__':
    main()
