#!/usr/bin/env python3
"""Validate reusable scan options and remove suppressed Checkov SARIF results."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote
from safe_io import assert_safe_path, append_text, write_text


# Built-in Terraform policy IDs in https://www.checkov.io/5.Policy%20Index/terraform.html
# include CKV_AZURE_35, CKV2_AZURE_1 and CKV_TF_1. Accept IDs, not CLI selectors
# such as severity names, wildcards or platform IDs.
CHECK_ID = re.compile(r"CKV2?_[A-Z0-9]+_[0-9]+", re.ASCII)
POSITIVE_INTEGER = re.compile(r"[0-9]+", re.ASCII)


def validate_skip_checks(value):
    """An empty string means no consumer skips; empty comma elements are errors."""
    if value == "":
        return []
    checks = value.split(",")
    for check_id in checks:
        if not CHECK_ID.fullmatch(check_id):
            raise ValueError(
                f"Invalid checkov-skip-checks ID {check_id!r}; expected "
                "CKV_<PROVIDER>_<NUMBER> or CKV2_<PROVIDER>_<NUMBER>, with no spaces"
            )
    return checks


def merge_skip_checks(config_checks, consumer_checks):
    """Preserve configured selectors and order while deduplicating consumer IDs."""
    if config_checks is None:
        config_checks = []
    if isinstance(config_checks, str):
        config_checks = config_checks.split(",") if config_checks else []
    if not isinstance(config_checks, list) or any(
        not isinstance(check, str) or not check for check in config_checks
    ):
        raise ValueError("Config skip-check must be a list of strings or a comma-separated string")
    return list(dict.fromkeys([*config_checks, *consumer_checks]))


def validate_render_count(value):
    """Keep unset distinct from an override; reject signs, whitespace and zero."""
    if value and (not POSITIVE_INTEGER.fullmatch(value) or not value.strip("0")):
        raise ValueError(f"Invalid checkov-render-iter-count {value!r}; expected a positive integer")
    return value


def approved_inline_locations(report, source_root, scan_directory, base_commit):
    """Translate only base-approved JSON skips into exact SARIF locations."""
    from scan_policy import checkov_checks, scanner_path
    from scan_reports import validate_report
    if not re.fullmatch(r'[0-9a-fA-F]{40,64}', base_commit):
        raise ValueError('A full trusted base commit is required')
    validate_report(report, 'checkov')
    locations, blocked = set(), set()
    for document in report if isinstance(report, list) else [report]:
        checks = document['results']
        pending = checkov_checks(checks, source_root, scan_directory=scan_directory, base_commit=base_commit)
        retained = {id(check) for check in pending}
        for check in checks.get('skipped_checks', []):
            lines = check.get('file_line_range') or []
            if lines:
                key = (check['check_id'], scanner_path(check['file_path'], 'checkov',
                       source_root, scan_directory), lines[0], lines[-1])
                (blocked if id(check) in retained else locations).add(key)
    # SARIF locations omit module-instance identity. A pending instance must
    # keep a shared location active even when another instance is approved.
    return locations - blocked


def filter_sarif(sarif, allow_inline=None, approved_locations=(), source_root='.', scan_directory='.'):
    """Remove approved skipped records; keep failed records independent.

    Checkov 3.3.19 labels skips with SARIF suppressions. Recognise explicit
    skip/status properties too, and normalize paths against the scan directory.
    """
    if allow_inline is None:
        allow_inline = os.environ.get("ALLOW_INLINE_CHECKOV_SKIPS") == "true"
    removed = 0
    for run in sarif["runs"]:
        results = run.get("results", [])
        kept = []
        for result in results:
            properties = result.get("properties") or {}
            status = properties.get("check_result") or result.get("check_result") or {}
            if isinstance(status, dict):
                status = status.get("result", "")
            skipped = str(status).upper() in {"SKIPPED", "SUPPRESSED"}
            skipped = skipped or str(properties.get("status", "")).upper() in {"SKIPPED", "SUPPRESSED"}
            skipped = skipped or any(
                container.get(key) is True
                for container in (result, properties)
                for key in ("skipped", "suppressed")
            )
            if result.get("suppressions") or skipped:
                locations = result.get('locations') or []
                location = locations[0].get('physicalLocation', {}) if len(locations) == 1 else {}
                region = location.get('region') or {}
                uri = unquote((location.get('artifactLocation') or {}).get('uri', ''))
                if approved_locations:
                    from scan_policy import scanner_path
                    uri = scanner_path(uri, 'checkov', source_root, scan_directory)
                key = (result.get('ruleId'), uri,
                       region.get('startLine'), region.get('endLine'))
                if allow_inline or key in approved_locations:
                    removed += 1
                    continue
                result.pop("suppressions", None)
                result.pop("check_result", None)
                result["level"] = "error"
                for key in ("status", "skipped", "suppressed", "check_result"):
                    properties.pop(key, None)
                    result.pop(key, None)
            kept.append(result)
        run["results"] = kept
    return removed


def annotation(kind, message):
    # Untrusted option strings must not inject workflow commands or extra lines.
    escaped = str(message).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{kind}::{escaped}")


def prepare(config):
    import yaml

    consumer_checks = validate_skip_checks(os.environ.get("CHECKOV_SKIP_CHECKS", ""))
    render_count = validate_render_count(os.environ.get("CHECKOV_RENDER_ITER_COUNT", ""))
    with config.open(encoding="utf-8") as stream:
        settings = yaml.safe_load(stream) or {}
    if not isinstance(settings, dict):
        raise ValueError("Checkov config must be a YAML mapping")
    effective = ",".join(merge_skip_checks(settings.get("skip-check"), consumer_checks))
    render_env = {"RENDER_EDGES_DUPLICATE_ITER_COUNT": render_count} if render_count else {}
    if "\n" in effective or "\r" in effective:
        raise ValueError("Config skip-check cannot contain newlines")
    append_text(os.environ["GITHUB_OUTPUT"], f"skip-checks={effective}\nrender-env={json.dumps(render_env)}\n")
    render_label = render_count or "unset (Checkov default)"
    print(f"Effective Checkov skip list: {effective or '(none)'}")
    print(f"RENDER_EDGES_DUPLICATE_ITER_COUNT: {render_label}")
    append_text(os.environ["GITHUB_STEP_SUMMARY"],
                f"### Checkov consumer settings\n\n- Effective skip list: `{effective or '(none)'}`\n- Render setting: `{render_label}`\n")


def main():
    """Prepare caller options or filter scanner output before publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("config", type=Path)
    sarif_parser = commands.add_parser("filter-sarif")
    sarif_parser.add_argument("sarif", type=Path)
    sarif_parser.add_argument("--checkov-report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.config)
        else:
            with args.sarif.open(encoding="utf-8") as stream:
                sarif = json.load(stream)
            approved = set()
            if args.checkov_report:
                report = json.loads(args.checkov_report.read_text(encoding='utf-8'))
                approved = approved_inline_locations(report, Path.cwd(),
                    os.environ.get('TERRAFORM_DIRECTORY', '.'), os.environ.get('TRUSTED_POLICY_SHA', ''))
            removed = filter_sarif(sarif, approved_locations=approved, source_root=Path.cwd(),
                                   scan_directory=os.environ.get('TERRAFORM_DIRECTORY', '.'))
            # Leave an unfiltered file untouched if parsing or filtering fails.
            temporary = args.sarif.with_suffix(".sarif.tmp")
            assert_safe_path(args.sarif)
            write_text(temporary, json.dumps(sarif, indent=2))
            temporary.replace(args.sarif)
            print(f"Removed {removed} suppressed/skipped Checkov SARIF result(s)")
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        annotation("error", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
