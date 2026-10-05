#!/usr/bin/env python3
"""Validate reusable scan options and remove suppressed Checkov SARIF results."""

import argparse
import json
import os
from pathlib import Path
import re
import sys


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


def filter_sarif(sarif):
    """Checkov 3.3.19 labels skipped records with SARIF suppressions.

    Remove them rather than relying on code scanning to honour suppressions.
    Also recognise explicit skip/status properties from other report producers.
    Failed results at the same rule or location remain independent.
    """
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
                removed += 1
            else:
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
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        # A config selector must also be safe in a single-line workflow output.
        if "\n" in effective or "\r" in effective:
            raise ValueError("Config skip-check cannot contain newlines")
        stream.write(f"skip-checks={effective}\n")
        stream.write(f"render-env={json.dumps(render_env)}\n")
    render_label = render_count or "unset (Checkov default)"
    print(f"Effective Checkov skip list: {effective or '(none)'}")
    print(f"RENDER_EDGES_DUPLICATE_ITER_COUNT: {render_label}")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write("### Checkov consumer settings\n\n")
        stream.write(f"- Effective skip list: `{effective or '(none)'}`\n")
        stream.write(f"- Render setting: `{render_label}`\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("config", type=Path)
    commands.add_parser("filter-sarif").add_argument("sarif", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.config)
        else:
            with args.sarif.open(encoding="utf-8") as stream:
                sarif = json.load(stream)
            removed = filter_sarif(sarif)
            # Leave an unfiltered file untouched if parsing or filtering fails.
            temporary = args.sarif.with_suffix(".sarif.tmp")
            temporary.write_text(json.dumps(sarif, indent=2), encoding="utf-8")
            temporary.replace(args.sarif)
            print(f"Removed {removed} suppressed/skipped Checkov SARIF result(s)")
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        annotation("error", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
