"""Summarize every SQL lint batch without treating tool errors as findings."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid


def report(directory, duration):
    batches = []
    for name in ('configured', 'default'):
        status = directory / f'{name}.exit'
        if status.exists():
            batches.append({'name': name, 'exit_code': int(status.read_text(encoding='utf-8')),
                            'output': (directory / f'{name}.output').read_text(encoding='utf-8', errors='replace')})
    findings = sum(batch['exit_code'] == 1 for batch in batches)
    return {
        'schema_version': '1.0', 'scan_id': str(uuid.uuid4()),
        'scan_timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'duration_ms': int(duration), 'scan_directory': '.', 'tools_executed': ['sqlfluff'],
        'auto_fix_applied': False, 'auto_fix_count': 0,
        'summary': {'total_findings': findings,
                    'by_severity': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': findings, 'LOW': 0},
                    'by_tool': {'sqlfluff': findings}, 'fixable': 0, 'unfixable': findings},
        'findings': [], 'scan_complete': all(batch['exit_code'] in (0, 1) for batch in batches),
        'batches': batches,
    }


if __name__ == '__main__':
    print(json.dumps(report(Path(sys.argv[1]), sys.argv[2])))
