#!/usr/bin/env python3
"""Scan immutable push tips, keeping the runner's complete Git transaction."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

HOOKS = ('trivy-iac-full', 'checkov', 'checkov-strict', 'tflint', 'snyk-iac', 'dotnet-build')
HERE = Path(__file__).resolve().parent


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)


def bash() -> str:
    if os.name == 'nt':
        # Native subprocess lookup can select the WSL launcher instead of Git Bash.
        candidate = Path(os.fsdecode(git('--exec-path')).strip()).parents[2] / 'usr/bin/bash.exe'
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which('bash')
    if not executable:
        raise ValueError('Bash is required for the hook runner')
    return executable


def tips(records: str) -> list[str]:
    result = []
    for line in records.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError('Malformed pre-push record')
        _, local, _, remote = fields
        if not all(re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', oid) for oid in (local, remote)):
            raise ValueError('Malformed pre-push object ID')
        if set(local) == {'0'}:  # deletion has no local tree to scan
            continue
        # Peel annotated tags. Reject blob tags and unavailable objects.
        git('rev-parse', '--verify', local + '^{tree}')
        if local not in result:
            result.append(local)
    return result


def materialize(oid: str, destination: Path) -> list[str]:
    """Copy blobs verbatim: no checkout filters, attributes, hooks or local index."""
    names = []
    entries = git('ls-tree', '-rz', '--full-tree', oid).split(b'\0')
    with subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as blobs:
        try:
            for entry in filter(None, entries):
                meta, raw_name = entry.split(b'\t', 1)
                mode, kind, blob = meta.split()
                name = os.fsdecode(raw_name)
                path = PurePosixPath(name)
                if (path.is_absolute() or any(p in ('..', '.git') or ':' in p or '\\' in p
                                              for p in path.parts)):
                    raise ValueError('Unsafe path in pushed tree')
                # Following a symlink or borrowing an unpinned submodule checkout
                # would read bytes outside this tree. Require explicit remediation.
                if kind != b'blob' or mode not in (b'100644', b'100755'):
                    raise ValueError('Push snapshot contains a symlink or submodule; scan incomplete')
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError('Pushed paths collide on this filesystem')
                blobs.stdin.write(blob + b'\n')
                blobs.stdin.flush()
                header = blobs.stdout.readline().split()
                if len(header) != 3 or header[1] != b'blob':
                    raise ValueError('Cannot read pushed blob')
                size = int(header[2])
                with target.open('wb') as output:
                    remaining = size
                    while remaining:
                        data = blobs.stdout.read(min(remaining, 1024 * 1024))
                        if not data:
                            raise ValueError('Truncated pushed blob')
                        output.write(data)
                        remaining -= len(data)
                if blobs.stdout.read(1) != b'\n':
                    raise ValueError('Invalid blob response')
                if mode == b'100755':
                    target.chmod(0o755)
                names.append(name)
        finally:
            blobs.stdin.close()
            blobs.wait()
    return names


def scan(records: str, hooks: list[tuple[str, list[str]]], shell: str, *, from_git: bool = False) -> int:
    objects = tips(records)
    if not records.strip() and not from_git:
        raise ValueError('Missing Git pre-push records; use the transaction-aware runner')
    status = 0
    for oid in objects:
        with tempfile.TemporaryDirectory(prefix='scan-push-') as temporary:
            snapshot = Path(temporary) / 'tree'
            snapshot.mkdir()
            names = materialize(oid, snapshot)
            config = {}
            if (snapshot / 'scan-config.yaml').is_file():
                import yaml
                config = yaml.safe_load((snapshot / 'scan-config.yaml').read_text(encoding='utf-8')) or {}
                enabled = config.get('global', {}).get('local_hooks_enabled', config.get('local_hooks_enabled', True))
                if enabled is False:
                    print(f'[pre-push] local scanning explicitly disabled in object {oid}', flush=True)
                    continue
            manifest = Path(temporary) / 'paths'
            manifest.write_bytes(b''.join(os.fsencode(p) + b'\0' for p in names))
            env = dict(os.environ, SCAN_PUSH_SNAPSHOT='1', SCAN_PUSH_FILES=str(manifest),
                       SCAN_CONFIG_FILE='scan-config.yaml', SCAN_CONFIG_DIR='.scanning/configs')
            for key in tuple(env):
                if key.startswith('GIT_'):
                    del env[key]
            for hook, extra in hooks:
                if hook not in HOOKS:
                    raise ValueError('Unknown pre-push scanner')
                extensions = ('.cs', '.csproj') if hook == 'dotnet-build' else ('.tf',)
                if not any(name.lower().endswith(extensions) for name in names):
                    continue
                if hook == 'dotnet-build':
                    build = config.get('languages', {}).get('csharp', {}).get('build', {})
                    for field in ('working_dir', 'solution'):
                        configured = build.get(field, '')
                        path = PurePosixPath(configured.replace('\\', '/'))
                        if path.is_absolute() or '..' in path.parts or ':' in configured:
                            raise ValueError('Build paths must remain inside the pushed snapshot')
                print(f'[pre-push] {hook}: scanning object {oid}', flush=True)
                script = str(HERE / f'{hook}.{shell}')
                command = (['pwsh', '-NoProfile', '-File', script] if shell == 'ps1'
                           else [bash(), script])
                result = subprocess.run(command + extra, cwd=snapshot, env=env)
                status = max(status, int(result.returncode != 0))
    return status


def configured_hooks() -> list[tuple[str, list[str]]]:
    import yaml
    config = yaml.safe_load(Path('.pre-commit-config.yaml').read_text(encoding='utf-8'))
    return [(h['id'], h.get('args', [])) for repo in config['repos'] for h in repo['hooks']
            if h['id'] in HOOKS and 'pre-push' in h.get('stages', config.get('default_stages', ['pre-push']))]


def install() -> int:
    path = Path(os.fsdecode(git('rev-parse', '--git-path', 'hooks/pre-push')).strip())
    original = path.with_name('pre-push.pre-commit')
    marker = '# scan push transaction adapter'
    if not path.exists():
        subprocess.run(['pre-commit', 'install', '--hook-type', 'pre-push'], check=True)
    content = path.read_text(encoding='utf-8')
    if marker in content:
        if not original.is_file():
            raise ValueError('Original pre-push runner is missing; restore it before reinstalling')
        return 0
    if 'File generated by pre-commit' not in content:
        raise ValueError('Refusing to replace an unrecognized pre-push hook')
    if original.exists():
        if 'File generated by pre-commit' not in original.read_text(encoding='utf-8'):
            raise ValueError('Unrecognized pre-push backup; review before reinstalling')
        # A normal runner reinstall may have saved our adapter as .legacy.
        # It must not be called recursively by the restored original runner.
        legacy = path.with_name('pre-push.legacy')
        if legacy.is_file() and marker in legacy.read_text(encoding='utf-8'):
            legacy.unlink()
    path.replace(original)
    # Relative, repo-owned entry point; no machine-specific paths in generated files.
    path.write_text('#!/usr/bin/env bash\n' + marker + '\n'
                    'for py in python3 python py; do\n'
                    '  if command -v "$py" >/dev/null && "$py" -c "" 2>/dev/null; then\n'
                    '    exec "$py" hooks/pre-push.py --pre-commit-runner "$@"\n'
                    '  fi\ndone\necho "Python is required for push snapshots" >&2\nexit 1\n',
                    encoding='utf-8', newline='\n')
    path.chmod(0o755)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-pre-commit', action='store_true')
    parser.add_argument('--pre-commit-runner', action='store_true')
    parser.add_argument('--stdin-from-git', action='store_true')
    parser.add_argument('--shell', choices=('sh', 'ps1'), default='ps1' if os.name == 'nt' else 'sh')
    parser.add_argument('--hooks', default='checkov,tflint,dotnet-build')
    args, extra = parser.parse_known_args()
    if args.install_pre_commit:
        return install()
    records = sys.stdin.read()
    if args.pre_commit_runner:
        hooks = configured_hooks()
        status = scan(records, hooks, args.shell, from_git=True)
        if status:
            return status
        original = os.fsdecode(git('rev-parse', '--git-path', 'hooks/pre-push.pre-commit')).strip()
        env = dict(os.environ, SKIP=','.join(filter(None, [os.environ.get('SKIP', ''), *HOOKS])))
        return subprocess.run([bash(), original, *extra], input=records, text=True, env=env).returncode
    return scan(records, [(h, extra) for h in args.hooks.split(',')], args.shell, from_git=args.stdin_from_git)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        print(f'[pre-push] ERROR: {exc}; scan incomplete', file=sys.stderr)
        raise SystemExit(1)
