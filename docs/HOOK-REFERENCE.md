# Hook Reference

Pre-push hooks require the complete Git stdin transaction and scan isolated object
trees. Config validation reads the consumer's staged root config. Upgrade the
runner configuration and vendored files together; see
[validation target migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration)
for runner setup, manual invocations, prerequisites and explicit legacy opt-ins.

Local hooks require **Python 3.11 or newer**, with PyYAML and jsonschema available
to that interpreter. Both shells probe candidates with `-E -P` before selecting
one, so Python 3.8–3.10 and broken launchers are skipped. The shared configuration
reader (`scan_config.py`, called from `read_scan_config` and `Read-ScanConfigValue`) runs
with the same flags, which keep the working and helper directories and Python environment
overrides out of its imports while keeping the trusted user-site dependencies that the
no-admin setup installs. Other helper scripts, including `pre-push.py`, run without them. Upgrade older interpreters before re-vendoring these hooks.

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

Commit scanners select staged files from the index. Transaction-bound push
scanners select files from each isolated pushed tree. Hooks publish available
JSON reports to `.scanning/last-scan.json`; an incomplete scan can block without
producing a report.

## Exit Code Contract

Transaction-bound push validation is **fail-closed**:

| Exit Code | Meaning | Behavior |
|-----------|---------|----------|
| `0` | No findings (pass) | Allow commit/push |
| `1` | Findings, snapshot setup errors, malformed transactions/configuration, unsafe tree entries or missing policies | Block push |
| `2+` from a scanner | Infrastructure or parse error | Push runner converts a nonzero scanner result to `1` and blocks |

Shared wrappers also block incomplete scans by default. `SCAN_ALLOW_TOOL_ERRORS=1`
opts into local warning-only handling where supported by an individual wrapper;
it never bypasses transaction setup, configuration shape, tree safety or required
policy checks. Optional scanner-specific skips are documented below. Staged
configuration validation blocks invalid configuration and missing prerequisites
by default; see its entry for the explicit prerequisite opt-in.

## JSON Output

Applicable scans write a JSON report to `.scanning/last-scan.json` (overwritten
by each reporting hook; last report wins). The output conforms to
`schemas/last-scan.schema.json`. A hook with nothing to scan may return success
without writing a report, including `checkov`, `tflint` and `dotnet-build` when
no matching files exist.

Push scanners export their reports from the isolated snapshot to this location in
the consumer repository before snapshot cleanup, including on scan failure. Earlier
reports are cleared before a new transaction, object or scanner attempt; if that
attempt produces no report, the earlier report is absent.

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
- **Tool**: Gitleaks 8.19 or newer (`gitleaks git --staged`)
- **Target**: <5 seconds
- **Flags**: `--report-format json --report-path - --redact --no-banner --exit-code 1 --log-level error`
- **Note**: Prints each staged finding's rule, file, and line. It does not print the secret. A config Gitleaks cannot load warns and allows the commit (fail-open) and is not counted as a finding. If the report is a JSON array and the bash hook has neither Python nor jq, it blocks with one finding and does not print the report. On the inputs in [SECRET-SCANNER-EVALUATION.md](SECRET-SCANNER-EVALUATION.md), Trivy found AWS access-key ids that Gitleaks did not. Gitleaks' extra hit on that file was a Slack webhook, which Trivy rates MEDIUM and the CI HIGH,CRITICAL gate does not block. CI secret scans stay on Trivy.

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
- **Config**: Requires external trusted `SCAN_TFLINT_CONFIG` (an HCL file) and
  `SCAN_TFLINT_PLUGIN_DIR` (plugin cache); executable config is not loaded from the
  pushed tree. See [the migration guide](CONSUMER-MIGRATION.md#trusted-execution-and-output-migration).
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
| **Optional** | Enable only when provisioned; unavailable tool blocks by default; missing authentication warns and skips |

This hook is **optional**. It is included as a commented-out entry in standard and strict tier templates. Projects without a Snyk license can leave it disabled. Once selected, a missing CLI blocks by default; missing authentication exits 0 with a warning.

**Authentication check order**:
1. Check `SNYK_TOKEN` environment variable (zero subprocess overhead)
2. Fall back to `snyk whoami` (checks keychain/config)
3. If neither succeeds: warn and exit 0 (fail-open)

## App-Code Hooks (v2.0.0)

These hooks extend the platform from Terraform-only IaC scanning to application
code. They follow the **same** dispatcher pattern as the Trivy/Checkov hooks:
shared tool availability checks, staged-file selection for commit scanners,
`.scanning/last-scan.json` output, and the exit-code contract above. Each ships
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
- **Exit codes**: `0` -> pass; findings or incomplete reports -> exit 1.
  Tool errors block by default; the shared local opt-in applies.

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
- **Behavior**: Runs when the pushed tree contains `.cs`/`.csproj` files. Surfaces
  the first ~40 analyzer/build error/warning lines. Build or analyzer errors and
  a missing solution block by default (exit 1).

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
- **Behavior**: Lint issues -> exit 1; tool errors block by default (shared local opt-in applies).

### Config Validation

#### validate-scan-config

- **Purpose**: Validate `scan-config.yaml` against `schemas/scan-config.schema.json`
- **Stage**: pre-commit
- **Tool**: Python (`scripts/validate-scan-config.py`)
- **Trigger**: Runs **only when `scan-config.yaml` is staged** (checks the git index)
- **Behavior**: Invalid staged YAML/schema shape -> exit 1. Python, PyYAML,
  `jsonschema` and the schema are required; the hook sets strict validation and
  missing prerequisites block by default. `SCAN_ALLOW_TOOL_ERRORS=1` explicitly
  allows missing prerequisites locally; invalid YAML still blocks. Setup copies
  `schemas/`, so the copied validator finds the schema under the
  consumer's `schemas/`; if it is removed,
  restore it by re-running setup. The schema rejects an
  invalid `fix_loop.claude_code_action_ref` (it must be a 40-char SHA pin of
  `anthropics/claude-code-action`) when it does run

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
    rev: v2.3.6    # always pin to a release tag, never @main  x-release-please-version
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

**Infrastructure error (blocks by default)**:
```
[trivy-iac-critical] ERROR: Tool error (exit code 127); scan incomplete
```

## Shared hook scan integrity

Changed-file paths remain NUL-delimited from Git through enumeration, filtering
and deduplication. Scanner path operands follow `--`; fixed path-valued scanner
options remain bound to their option. Bash and PowerShell use equivalent path
selection, preserving spaces, Unicode, quotes and embedded newlines.

Tool failures handled by the shared hook library now block by default. Set
`SCAN_ALLOW_TOOL_ERRORS=1` only when explicitly choosing the previous local
warning-only infrastructure behavior. This setting does not affect CI. Re-vendor
the hook directory as a unit so callers and shared helpers upgrade together.
Trivy retry decisions use its stderr and operational exit status; findings output
does not control retries.
