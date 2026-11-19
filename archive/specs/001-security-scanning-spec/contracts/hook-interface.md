# Contract: Hook Interface

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)
**Date**: 2026-02-10

## Overview

Defines the interface contract between the pre-commit framework and this repo's hooks. All hooks are consumed via `.pre-commit-hooks.yaml` and invoked through `hooks/dispatcher.sh`.

## Hook Manifest Contract (.pre-commit-hooks.yaml)

### Entry Format

Each hook entry MUST conform to the pre-commit hook definition schema:

```yaml
- id: {hook-id}                    # REQUIRED: Unique kebab-case identifier
  name: {Human Readable Name}      # REQUIRED: Display name
  entry: hooks/dispatcher.sh {hook-id}  # REQUIRED: Dispatcher + hook ID
  language: script                  # REQUIRED: Always "script"
  files: ''                         # REQUIRED: Empty string (match all files)
  exclude: '(\.terraform/|node_modules/|\.git/)'  # REQUIRED: Directory exclusions
  types: [file]                     # REQUIRED: Match file type
  stages: [{stage}]                 # REQUIRED: pre-commit | pre-push
  pass_filenames: false             # REQUIRED: Hooks scan directories, not files
  verbose: true                     # REQUIRED: Show output even on success
```

### Hook IDs (Stable — Breaking Change if Renamed)

| ID | Tool | Stage | Severity Filter |
|----|------|-------|----------------|
| `trivy-iac-critical` | Trivy | pre-commit | CRITICAL only |
| `trivy-iac-full` | Trivy | pre-push | All severities |
| `trivy-secrets` | Trivy | pre-commit | N/A |
| `checkov` | Checkov | pre-push | Per config |
| `checkov-strict` | Checkov | pre-push | CRITICAL + HIGH |
| `validate-suppressions` | Python | pre-commit | N/A |
| `tflint` | tflint | pre-push | Per config |
| `gitleaks` | Gitleaks | pre-commit | N/A |

## Dispatcher Contract (hooks/dispatcher.sh)

### Invocation

```
hooks/dispatcher.sh <hook-id> [args...]
```

### Behavior

1. Detect OS (Windows/macOS/Linux)
2. If Windows + PowerShell available → invoke `hooks/{hook-id}.ps1`
3. Else → invoke `hooks/{hook-id}.sh`
4. Pass all `[args...]` through to the target script

### Environment Variables (Set by Dispatcher)

| Variable | Value | Purpose |
|----------|-------|---------|
| `SCAN_HOOK_ID` | Hook ID string | Identifies current hook |
| `SCAN_VERBOSE` | `0` or `1` | Verbosity flag |
| `SCAN_CONFIG_DIR` | Path to `.scanning/configs/` | Config directory location |

## Hook Script Contract (hooks/{hook-id}.sh / .ps1)

### Exit Codes

| Code | Meaning | pre-commit Behavior |
|------|---------|-------------------|
| `0` | No findings (pass) | Allow commit/push |
| `1` | Security findings detected | Block commit/push |
| `2+` | Infrastructure error | Treat as pass (fail-open) |

**Critical**: Exit code `1` MUST only be returned when actual security findings exceed the configured severity threshold. All other errors (tool not found, DB lock, network failure, parse error) MUST exit with code `2` or higher to trigger fail-open behavior.

**Note (KC-006)**: The `validate-suppressions` hook uses exit code 1 for validation errors (missing fields, expired suppressions, format violations). While the general hook contract defines exit code 1 as 'security findings', suppression validation errors ARE the security concern for this hook — invalid or expired suppressions represent governance failures that must block the commit. The exit code 1 semantic is thus consistent in intent: both represent 'conditions that should block the commit'.

### Output Contract

**stdout**: Human-readable summary (always)
```
[hook-id] Scanning... (X files in Y directories)
[hook-id] PASS: No findings above threshold
```
or
```
[hook-id] Scanning... (X files in Y directories)
[hook-id] FAIL: N findings (C critical, H high, M medium, L low)
```
or (infrastructure error)
```
[hook-id] WARNING: Tool error (exit code N) - allowing commit (fail-open)
```

**JSON output**: Written to `.scanning/last-scan.json` (overwritten by each hook, last hook wins)

### Config Resolution

Hooks resolve configuration files in this order:
1. `.scanning/configs/{file}` (consuming repo's downloaded configs)
2. Explicit `--config-file` argument (if provided via `args:` in consuming repo's config)
3. Tool defaults (fallback)

### Performance Contract

| Stage | Max Duration | Measured In |
|-------|-------------|-------------|
| pre-commit | <5 seconds per hook | CI (`ubuntu-latest`) |
| pre-push | <60 seconds total | CI (`ubuntu-latest`) |
| Total pre-commit | <10 seconds | CI (`ubuntu-latest`) |

### Trivy-Specific Retry

When Trivy returns a DB lock error (detected via stderr pattern `"database locked"`):
1. Wait 2 seconds
2. Retry once
3. If retry fails → exit code 2 (fail-open)

### Override Points (Consuming Repo)

Consuming repos can override via their `.pre-commit-config.yaml`:

```yaml
hooks:
  - id: trivy-iac-critical
    args: ["--severity", "CRITICAL,HIGH"]    # Override severity
    stages: [pre-push]                        # Override stage
    files: 'terraform/.*\.tf$'                # Override file pattern
    exclude: 'terraform/legacy/.*'            # Override exclusions
```

All fields in the consuming repo's config override the manifest defaults.
