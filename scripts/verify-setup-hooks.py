#!/usr/bin/env python3
"""Check installed hook identities against the shipped runner/tier template."""
import argparse
from pathlib import Path

import yaml


def hook_entries(config, runner):
    if runner == 'pre-commit':
        return {(repo['repo'], hook['id']): hook
                for repo in config['repos'] for hook in repo['hooks']}
    return {(stage, name): command
            for stage in ('pre-commit', 'pre-push')
            for name, command in config[stage]['commands'].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runner', choices=['lefthook', 'pre-commit'])
    parser.add_argument('tier', choices=['starter', 'standard', 'strict'])
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    templates = Path(__file__).resolve().parent.parent / 'templates'
    template = (templates / 'lefthook/lefthook.yml' if args.runner == 'lefthook'
                else templates / args.tier / 'pre-commit-config.yaml')
    try:
        expected = hook_entries(yaml.safe_load(template.read_text(encoding='utf-8')), args.runner)
        actual = hook_entries(yaml.safe_load(args.config.read_text(encoding='utf-8')), args.runner)
        if not expected:
            raise ValueError('Template contains no hooks')
        for key, hook in expected.items():
            if key not in actual:
                raise ValueError(f'Required hook missing: {key[1]}')
            if args.runner == 'lefthook' and actual[key].get('run') != hook['run']:
                raise ValueError(f'Required hook command changed: {key[1]}')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError) as exc:
        print(f'Hook configuration invalid: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
