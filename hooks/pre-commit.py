#!/usr/bin/env python3
"""Run passive commit scanners against selected, immutable index blobs."""
import argparse
import importlib.util
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('push_snapshot', HERE / 'pre-push.py')
push = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push)

EXTENSIONS = {
    'semgrep-csharp': ('.cs',),
    'semgrep-typescript': ('.ts', '.tsx', '.js', '.jsx'),
    'trivy-iac-critical': ('.tf', '.tf.json'),
    'sqlfluff': ('.sql',),
}


def scan(hook, arguments, shell):
    root = Path(os.fsdecode(push.git('rev-parse', '--show-toplevel')).strip()).resolve()
    os.chdir(root)
    report = root / '.scanning/last-scan.json'
    push.clear_report(report)
    # write-tree captures one index version; both selection and byte export use it.
    # Unmerged entries fail here rather than being silently omitted.
    tree = os.fsdecode(push.git('write-tree')).strip()
    try:
        base = os.fsdecode(push.git('rev-parse', '--verify', '-q', 'HEAD^{tree}')).strip()
    except subprocess.CalledProcessError:
        base = subprocess.check_output(['git', 'mktree'], input=b'').decode().strip()
    selected = {name for name in push.diff_paths(base, tree)
                if name.lower().endswith(EXTENSIONS[hook])}
    if not selected:
        return 0
    policy_dir = push.policy_directory(root)
    policy = {'scan-config.yaml', '.sqlfluff', '.semgrepignore', '.gitignore',
              str(PurePosixPath(policy_dir) / '.trivyignore')}
    implementation, executable = push.select_shell(shell)
    with tempfile.TemporaryDirectory(prefix='scan-index-') as directory:
        temporary = Path(directory).resolve(strict=True)
        snapshot = temporary / 'tree'
        snapshot.mkdir()
        available = push.materialize(tree, snapshot, selected | policy)
        manifest = temporary / 'paths'
        manifest.write_bytes(b''.join(os.fsencode(p) + b'\0' for p in available if p in selected))
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(SCAN_INDEX_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest),
                   SCAN_CONFIG_FILE='scan-config.yaml', SCAN_CONFIG_DIR=policy_dir,
                   SCAN_CONSUMER_ROOT=str(root))
        script = str(HERE / f'{hook}.{implementation}')
        command = ([executable, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script]
                   if implementation == 'ps1' else [executable, script])
        try:
            return subprocess.run(command + arguments, cwd=snapshot, env=env).returncode
        finally:
            push.export_report(snapshot / '.scanning/last-scan.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell', choices=('auto', 'sh', 'ps1'), default='auto')
    parser.add_argument('hook', choices=EXTENSIONS)
    args, extra = parser.parse_known_args()
    try:
        raise SystemExit(scan(args.hook, extra, args.shell))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'[pre-commit] ERROR: {exc}; scan incomplete', file=sys.stderr)
        raise SystemExit(1)
