"""Executable scanner doubles for baseline integration tests."""
import json
import os
from pathlib import Path
import sys


def scanner_stub(folder, name, env, report=None, code=0, quiet_report=None):
    folder.mkdir(parents=True, exist_ok=True)
    prefix = 'BASELINE_STUB_' + name
    stub = folder / (name + '_stub.py')
    stub.write_text(
        'import json, os, sys\nfrom pathlib import Path\n'
        'args = sys.argv[1:]\n'
        'call = {"args": args, "executable": sys.argv[0]}\n'
        'if "--config-file" in args:\n'
        '    p = Path(args[args.index("--config-file") + 1])\n'
        '    call.update(policy_path=str(p), policy=p.read_text(encoding="utf-8"))\n'
        'with open(os.environ["BASELINE_TRACE"], "a", encoding="utf-8") as f:\n'
        '    f.write(json.dumps(call) + "\\n")\n'
        f'report = os.environ[{(prefix + "_REPORT")!r}]\n'
        f'if "--quiet" in args: report = os.environ.get({(prefix + "_QUIET_REPORT")!r}, report)\n'
        'print(report)\n'
        f'sys.exit(int(os.environ[{(prefix + "_CODE")!r}]))\n', encoding='utf-8')
    launcher = folder / (name + '.cmd' if os.name == 'nt' else name)
    launcher.write_text(
        f'@"{sys.executable}" "{stub}" %*\n@exit /b %errorlevel%\n' if os.name == 'nt' else
        f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    env['PATH'] = str(folder) + os.pathsep + env['PATH']
    env[prefix + '_CODE'] = str(code)
    env[prefix + '_REPORT'] = report if report is not None else json.dumps({
        'trivy': dict(Results=[]),
        'checkov': dict(results=dict(failed_checks=[], skipped_checks=[]), summary=dict(skipped=0)),
        'tflint': dict(issues=[]),
    }[name])
    if quiet_report is not None:
        env[prefix + '_QUIET_REPORT'] = quiet_report
    env.setdefault('BASELINE_TRACE', str(folder.parent / 'scanner-trace.jsonl'))
    return launcher
