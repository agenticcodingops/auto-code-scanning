# Hook Reference

Complete reference for the hooks provided by auto-code-scanning. As of v2.0.0
this covers both the original Terraform/IaC hooks and the new app-code hooks
(C#/.NET, TypeScript/JavaScript, SQL) plus config validation.

## Architecture

All hooks use a dual-wrapper architecture:
1. A local runner manifest defines hook entries:
   - **Lefthook** (`templates/lefthook/lefthook.yml`) — the **default** runner. A
     single Go binary, native on Windows, runs hooks in parallel, friction-free
     for autonomous Claude Code loops.
   - **pre-commit** (`.pre-commit-hooks.yaml`) — the alternative runner, with
     `language: script` entries.
2. Each hook entry (in either runner) calls the same `hooks/dispatcher.sh <hook-id>`.
   There is **no logic duplication** between the two runners — they share the
   dispatcher and the hook scripts.
3. The dispatcher detects the OS and routes to the appropriate implementation:
   - Unix/macOS: `hooks/<hook-id>.sh`
   - Windows (PowerShell available): `hooks/<hook-id>.ps1`
4. Shared functions are loaded from `hooks/lib/common.sh` (Bash) or `hooks/lib/common.ps1` (PowerShell)

Every hook scans **only the staged files** (discovered from the git index, not
the doublestar globs — globs only decide *whether* a command runs), writes a JSON
report to `.scanning/last-scan.json`, and is **fail-open**: a missing tool or an
infrastructure error never blocks the commit/push.

## Exit Code Contract

All hooks follow the fail-open error handling model:

| Exit Code | Meaning | Behavior |
|-----------|---------|----------|
| `0` | No findings (pass) | Allow commit/push |
| `1` | Security findings detected | Block commit/push |
| `2+` | Infrastructure error (tool crash, DB lock, network issue) | Allow commit/push (fail-open) |

**Exit code 1** is reserved exclusively for actual security findings exceeding the configured severity threshold. Tool errors, network failures, and parse errors use exit code 2+ to avoid blocking developers on infrastructure issues.

## JSON Output

Every hook writes a JSON report to `.scanning/last-scan.json` (overwritten by each hook; last hook wins). The output conforms to `schemas/last-scan.schema.json`.

## Environment Variables

The dispatcher sets these environment variables for hook scripts:

| Variable | Value | Purpose |
|----------|-------|---------|
| `SCAN_HOOK_ID` | Hook ID string | Identifies current hook |
| `SCAN_VERBOSE` | `0` or `1` | Verbosity flag |
| `SCAN_CONFIG_DIR` | Path to `.scanning/configs/` | Config directory location |

## Available Hooks

### Pre-Commit Hooks

#### trivy-iac-critical

- **Purpose**: Quick scan for CRITICAL Terraform misconfigurations only
- **Stage**: pre-commit
- **Tool**: Trivy (IaC scanner mode)
- **Target**: <5 seconds
- **Severity filter**: CRITICAL only
- **Flags**: `--skip-check-update`, `--severity CRITICAL`, `--exit-code 1`, `--quiet`
- **Retry**: On Trivy DB lock error, waits 2 seconds and retries once
- **Monorepo**: Detects changed Terraform directories via `detect_changed_dirs()`

#### trivy-secrets

- **Purpose**: Detects hardcoded secrets, API keys, and credentials in files
- **Stage**: pre-commit
- **Tool**: Trivy (secret scanner mode)
- **Target**: <5 seconds
- **Flags**: `--scanners secret`, `--severity HIGH,CRITICAL`, `--exit-code 1`, `--quiet`
- **Retry**: Same DB lock retry as trivy-iac-critical

#### gitleaks

- **Purpose**: Detects leaked credentials and secrets using pattern matching
- **Stage**: pre-commit
- **Tool**: Gitleaks
- **Target**: <5 seconds
- **Note**: Complements trivy-secrets with different detection patterns

#### validate-suppressions

- **Purpose**: Validates `.scan-suppressions.yaml` format, fields, and expiration dates
- **Stage**: pre-commit
- **Tool**: Python (PyYAML)
- **Target**: <3 seconds
- **Implementation**: `hooks/validate-suppressions.py`
- **Validation rules**:
  - YAML syntax valid
  - All required fields present per entry
  - `expires_date` is valid ISO date and within 180-day maximum
  - `approved_by` present when severity is HIGH or CRITICAL
  - `rule_id` format matches expected pattern for declared tool (AVD-* for Trivy, CKV_* for Checkov)
  - No duplicate `(rule_id, tool)` pairs
- **Expiry behavior**: Expired suppressions produce warnings locally (allow commit); errors in CI (fail workflow)

### Pre-Push Hooks

#### trivy-iac-full

- **Purpose**: Full IaC scan across all severity levels
- **Stage**: pre-push
- **Tool**: Trivy (IaC scanner mode)
- **Target**: <30 seconds
- **Severity filter**: All (CRITICAL, HIGH, MEDIUM, LOW)
- **Flags**: `--skip-check-update`, `--exit-code 1`, `--quiet`
- **Retry**: Same DB lock retry as trivy-iac-critical
- **Monorepo**: Same `detect_changed_dirs()` support

#### checkov

- **Purpose**: Policy-as-code checks against CIS Benchmarks and best practices
- **Stage**: pre-push
- **Tool**: Checkov
- **Target**: <30 seconds
- **Config**: Uses `.scanning/configs/.checkov.yaml` (blocklist approach -- all checks enabled, config lists exclusions)
- **Flags**: `--config-file .scanning/configs/.checkov.yaml`, `--framework terraform`, `--quiet`, `--compact`

#### checkov-strict

- **Purpose**: Strict mode Checkov -- hard-fails on CRITICAL and HIGH findings
- **Stage**: pre-push
- **Tool**: Checkov
- **Target**: <30 seconds
- **Config**: Same as `checkov` plus `--hard-fail-on CRITICAL,HIGH`
- **Used in**: Strict tier only

#### tflint

- **Purpose**: Terraform-specific linting (provider-aware rules, deprecated syntax, naming)
- **Stage**: pre-push
- **Tool**: tflint
- **Target**: <15 seconds
- **Config**: Uses `.scanning/configs/.tflint.hcl` (cloud-specific ruleset and rules)
- **Monorepo**: Runs per detected Terraform directory

#### snyk-iac (Optional)

| Property | Value |
|----------|-------|
| **Purpose** | Snyk IaC scan for Terraform misconfigurations |
| **Stage** | `pre-push` |
| **Tool** | Snyk CLI (`snyk iac test`) |
| **Severity** | All (CRITICAL, HIGH, MEDIUM, LOW) |
| **Prerequisites** | Snyk CLI (`npm install -g snyk`), authenticated (`snyk auth` or `SNYK_TOKEN`) |
| **Policy file** | `.snyk` in repo root (Snyk convention) |
| **Optional** | Yes — fail-open if not installed or not authenticated |

This hook is **optional**. It is included as a commented-out entry in standard and strict tier templates. Projects without a Snyk license can safely ignore it. When Snyk CLI is not installed or not authenticated, the hook exits 0 with a warning message and does not block the push.

**Authentication check order**:
1. Check `SNYK_TOKEN` environment variable (zero subprocess overhead)
2. Fall back to `snyk whoami` (checks keychain/config)
3. If neither succeeds: warn and exit 0 (fail-open)

## App-Code Hooks (v2.0.0)

These hooks extend the platform from Terraform-only IaC scanning to application
code. They follow the **same** dispatcher pattern as the Trivy/Checkov hooks:
`require_tool` fail-open, staged-files-only, `.scanning/last-scan.json` output,
and the exit-code contract (`0`=pass, `1`=findings, `2+`=fail-open). Each ships
as both `.sh` and `.ps1` and is registered in `.pre-commit-hooks.yaml` and the
default Lefthook manifest.

The corresponding language plugins in `scan-config.yaml` (`languages.csharp`,
`languages.typescript`, `languages.sql`) ship **disabled by default** — enable
them per repo (e.g. `setup-scanning --languages csharp`).

### C# / .NET

#### semgrep-csharp

- **Purpose**: Semgrep SAST for C# (staged `.cs` files)
- **Stage**: pre-commit
- **Tool**: Semgrep (`semgrep scan`)
- **Ruleset**: `p/csharp` (registry pack). Override via `SEMGREP_RULESET_CSHARP`
- **Flags**: `--config <ruleset>`, `--error`, `--metrics off`, `--quiet`
- **Windows**: runs natively (no WSL) with `PYTHONUTF8=1` and `SEMGREP_SEND_METRICS=off`
- **Exit codes**: Semgrep `0` -> pass, `1` -> findings (exit 1), `2+` -> fail-open

#### dotnet-format

- **Purpose**: Verify C# formatting (`dotnet format --verify-no-changes`)
- **Stage**: pre-commit
- **Tool**: `dotnet format`
- **Build config**: Reads `languages.csharp.build.{solution,working_dir}` from
  `scan-config.yaml` — the solution path is **never hardcoded**. Empty `solution`
  -> auto-detect the nearest `.sln`/`.slnx` under `working_dir`
- **Flags**: `--verify-no-changes`, `--no-restore`, with `--include` per staged file
- **Behavior**: Staged `.cs` files are filtered to those under `working_dir` and
  made relative to it; runs `dotnet format` from `working_dir`. Formatting needed
  -> exit 1. No solution found -> warn and exit 0 (fail-open)

#### dotnet-build

- **Purpose**: Roslyn analyzers via build
- **Stage**: pre-push
- **Tool**: `dotnet build`
- **Build config**: Same `languages.csharp.build.{solution,working_dir}` resolution
  (and auto-detect) as `dotnet-format`
- **Flags**: `/p:AnalysisMode=AllEnabledByDefault`, `--nologo`
- **Behavior**: Only runs when `.cs`/`.csproj` files are staged. Surfaces the first
  ~40 analyzer/build error/warning lines. Build or analyzer errors -> exit 1

### TypeScript / JavaScript

#### semgrep-typescript

- **Purpose**: Semgrep SAST for TypeScript/JavaScript (staged `.ts/.tsx/.js/.jsx`)
- **Stage**: pre-commit
- **Tool**: Semgrep (`semgrep scan`)
- **Ruleset**: `p/typescript`. Override via `SEMGREP_RULESET_TYPESCRIPT`
- **Flags**: `--config <ruleset>`, `--error`, `--metrics off`, `--quiet`
- **Windows**: native, `PYTHONUTF8=1`, metrics off (same as `semgrep-csharp`)

#### eslint

- **Purpose**: ESLint auto-fix + gate on remaining errors
- **Stage**: pre-commit
- **Tool**: `eslint --fix`
- **Working dir**: Reads `languages.typescript.build.working_dir` from
  `scan-config.yaml` (monorepo-aware); staged paths are relativized to it
- **Runner resolution**: `<working_dir>/node_modules/.bin/eslint` -> `eslint` on PATH
  -> `npx --no-install eslint`; none found -> warn and exit 0 (fail-open)
- **Behavior**: Auto-fixes in place. Remaining errors -> exit 1 (re-stage and
  re-commit). Under Lefthook, `stage_fixed: true` re-stages auto-fixed files

#### prettier

- **Purpose**: Prettier auto-format of staged files
- **Stage**: pre-commit
- **Tool**: `prettier --write --ignore-unknown`
- **Files**: `.ts/.tsx/.js/.jsx/.json/.css/.scss/.md`
- **Working dir**: Reads `languages.typescript.build.working_dir`; same runner
  resolution (`node_modules/.bin/prettier` -> `prettier` -> `npx --no-install prettier`)
- **Behavior**: Reformats in place. Under Lefthook, `stage_fixed: true` re-stages;
  under pre-commit a modified file fails the hook so you re-stage and re-commit.
  A non-zero `prettier` exit (e.g. syntax error) -> exit 1

### SQL

#### sqlfluff

- **Purpose**: SQL linting (staged `.sql` files)
- **Stage**: pre-commit
- **Tool**: `sqlfluff lint`
- **Dialect**: `ansi` (default)
- **Behavior**: Lint issues -> exit 1; tool error -> fail-open

### Config Validation

#### validate-scan-config

- **Purpose**: Validate `scan-config.yaml` against `schemas/scan-config.schema.json`
- **Stage**: pre-commit
- **Tool**: Python (`scripts/validate-scan-config.py`)
- **Trigger**: Runs **only when `scan-config.yaml` is staged** (checks the git index)
- **Behavior**: Schema violation -> exit 1; Python not found -> warn and exit 0
  (fail-open). The schema rejects an invalid `fix_loop.claude_code_action_ref`
  (it must be a 40-char SHA pin of `anthropics/claude-code-action`)

## Override Environment Variables

In addition to the dispatcher variables above, the following env vars tune hook
behavior:

| Variable | Scope | Purpose |
|----------|-------|---------|
| `SEMGREP_RULESET_CSHARP` | `semgrep-csharp` | Override the C# ruleset (default `p/csharp`) |
| `SEMGREP_RULESET_TYPESCRIPT` | `semgrep-typescript` | Override the TS/JS ruleset (default `p/typescript`) |

The in-session Claude Code bundle (`templates/claude/`) also honors escape-hatch
variables for its own hooks: `CC_SKIP_SEMGREP_HOOK=1` (skip the per-file Semgrep
scan), `CC_SKIP_SECRET_HOOK=1` (skip the per-file secret scan), and
`CC_STOP_SCAN_TYPE=secrets|semgrep|all` (choose the Stop-gate scan; default
`secrets`). These are convenience escape hatches for the agentic loop, not for the
commit/push gate.

## Performance Targets

| Stage | Max Per Hook | Max Total |
|-------|-------------|-----------|
| pre-commit | 5 seconds | 10 seconds |
| pre-push | 30 seconds | 60 seconds |
| pre-push (snyk-iac) | 30 seconds | (included in pre-push total) |

Measured on CI runner (`ubuntu-latest`). Local times may vary. App-code hooks that
shell out to `dotnet` (`dotnet-format`, and especially `dotnet-build`, which runs
full Roslyn analysis) are scheduled at the stage shown above and can exceed these
targets on a cold restore; `dotnet-build` runs at pre-push for that reason. Lefthook
runs commands in parallel, which helps keep wall-clock time within budget.

## Overriding Hook Configuration

Consuming repos using the **pre-commit** runner can override any hook's args,
stages, or files in their `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v2.0.0    # always pin to a release tag, never @main
    hooks:
      - id: trivy-iac-critical
        stages: [pre-push]          # Override: move to pre-push
        args: ["--severity", "HIGH"] # Override: change severity
      - id: checkov
        exclude: 'legacy/.*'        # Override: skip legacy directory
```

All fields in the consuming repo's config override the manifest defaults. See
[VERSION-PINNING.md](VERSION-PINNING.md) for the pinning policy.

Consumers using the **default Lefthook** runner override behavior in their copy of
`lefthook.yml` (glob, stage, `stage_fixed`, etc.). Both runners ultimately call
the same `hooks/dispatcher.sh <hook-id>`, and most app-code hooks self-discover
their settings from `scan-config.yaml` (`languages.*.build.*`) rather than from
command-line args.

## Config Resolution Order

Hooks resolve configuration files in this priority:

1. `.scanning/configs/{file}` (consuming repo's downloaded configs)
2. Explicit `--config-file` argument (if provided via `args:` override)
3. Tool defaults (fallback)

## Stdout Output Format

All hooks produce human-readable output:

**Pass**:
```
[trivy-iac-critical] Scanning... (12 files in 3 directories)
[trivy-iac-critical] PASS: No findings above threshold
```

**Fail**:
```
[trivy-iac-critical] Scanning... (12 files in 3 directories)
[trivy-iac-critical] FAIL: 2 findings (2 critical, 0 high, 0 medium, 0 low)
```

**Infrastructure error (fail-open)**:
```
[trivy-iac-critical] WARNING: Tool error (exit code 127) - allowing commit (fail-open)
```
