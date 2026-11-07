# Hook Reference

Pre-push hooks require the complete Git stdin transaction and scan isolated object
snapshots of changed files. Existing refs compare the remote object with the pushed
object. New branches compare with the merge base of the destination remote's tracked
default branch. Without a usable merge base, only commits absent from direct
tracking refs unambiguously owned by that destination contribute paths. Unknown
destinations or unsafe/ambiguous mappings conservatively scan reachable ancestry.
Other remotes never exclude destination-bound changes. Deleted refs and deleted files scan nothing. File bytes and policy
come from the pushed objects, regardless of the index or working tree.
Config validation reads the consumer's staged root config. Upgrade the
runner configuration and vendored files together; see
[validation target migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration)
for runner setup, manual invocations, prerequisites and explicit legacy opt-ins.

Shell hooks require **Bash 4.4 or later**. On macOS, run `brew install bash`
and make sure the installed Bash is first on PATH; the system `/bin/bash` is
too old. The shared Bash library rejects older versions with an installation hint.

Local hooks require **Python 3.11 or newer**, with PyYAML and jsonschema available
to that interpreter. Both shells probe candidates with `-E -P` before selecting
one, so Python 3.8–3.10 and broken launchers are skipped. The shared configuration
reader (`scan_config.py`, called from `read_scan_config` and `Read-ScanConfigValue`) runs
with the same flags, which keep the working and helper directories and Python environment
overrides out of its imports while keeping the trusted user-site dependencies that the
no-admin setup installs. Staged and push snapshot launchers, the transaction
dispatcher, and the installed push adapter use the same `-E -P` policy. Install
PyYAML in the selected interpreter's site-packages, an active virtual environment,
or its trusted user site. Check that environment with
`python -E -P -c "import yaml"` before running the hooks. Upgrade older
interpreters before re-vendoring these hooks.

Both shells verify executable paths before probing Python or launching a scanner.
The invoked path and its canonical target must be outside the scanned checkout
and, during snapshots, the original consumer checkout. Functions and aliases
cannot override the verified application. External virtual environments keep
their invoked interpreter path so their installed packages remain available.
Opaque external execution aliases are skipped without probing; a checkout-boundary
rejection still stops interpreter discovery.
Re-vendor the complete `hooks/lib` directory when upgrading. Checkout-owned or
unverified executables are refused even with `SCAN_ALLOW_TOOL_ERRORS=1`.

On Windows, the `py` fallback selects an active `VIRTUAL_ENV`'s `Scripts/python.exe`,
or the single default marked by the launcher's `-0p` inventory. That inventory
does not run Python. The hooks and baseline creator verify the selected interpreter
and run its path directly. An interpreter inside a protected checkout, or an
ambiguous launcher selection, is rejected before any Python probe.

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

Semgrep and Trivy's pre-commit IaC scanner run in temporary trees exported
from the index, including their tracked policy inputs. Unstaged edits do not change
the bytes they inspect. Export errors block; temporary trees are removed after
reports are published. Formatters retain their existing worktree behavior.
SQLFluff lints the staged file names in the working tree because it is a style
linter, not a security gate; project configuration, macros and templates remain
available in their original locations.
When upgrading, provision Python 3.11+ for `semgrep-csharp`, `semgrep-typescript`
and `trivy-iac-critical` before re-vendoring: their staged snapshot adapter needs
it even when the scanner executable is installed. An unavailable, older or broken
interpreter blocks before scanner launch with `Python is required for index
snapshots`. `SCAN_ALLOW_TOOL_ERRORS=1` does not bypass this prerequisite.
Parallel scanners capture private index copies. Repository-local Semgrep rule
overrides (files or directories) are exported from that same index version.
External rule aliases are resolved before checking the repository boundary, so
a link into the checkout uses staged rules or fails if they are not staged.
Checkout-local rule settings keep their captured names even when an unstaged
link redirects the worktree path elsewhere; captured symlinks still block.
The pre-commit Terraform snapshot includes `.tf`, `.tf.json` and `.tfvars`
siblings from the captured index in each selected directory. Trivy can resolve
module variables and locals. Indexed `terraform.tfvars` and `*.auto.tfvars` files
are passed as variable overrides, with automatic files in ordinal filename order;
other variable files require an explicit `--tf-vars` argument. Findings are
filtered to the selected changed files, accepting bare or directory-prefixed
scanner targets. Ambiguous targets and invalid reports block even with tool-error
opt-in. Nested directories and unrelated files remain excluded. A required
context file that is a symlink blocks snapshot creation. Index-capture errors include
Git's diagnostic so conflicts or other rejected index entries can be corrected.
Transaction-bound push
scanners select changed files from each isolated pushed tree, alongside required
tracked policy. Terraform directory scans exclude unchanged source files, including
siblings and nested files of other IaC types. Both `.tf` and `.tf.json` changes
trigger IaC scanning. TFLint reads the complete pushed tree for module context and
uses per-directory file filters to report findings only in changed sources. A changed
`.cs`/`.csproj` input triggers a build with the complete pushed solution for context.
Hooks publish available
JSON reports to `.scanning/last-scan.json`; an incomplete scan can block without
producing a report.

Checkov, Trivy IaC and Snyk IaC copy only selected changed files and required
tracked policy. An unchanged, unrelated symlink or submodule is outside that
snapshot and does not block these file-only scanners. A selected symlink or
submodule blocks. TFLint and dotnet build copy the complete pushed tree for
context, so any symlink or submodule in that tree blocks them, even if unchanged.

Local Checkov entrypoints accept only passive configuration: `framework`,
`skip-framework`, `skip-check`, `skip-path`, `deep-analysis`, `evaluate-variables`,
`quiet`, `compact`, `skip-download`, `download-external-modules` (false only), and
standard `output` formats. Output format selection is owned by the wrapper. A
string `output-file-path`, which earlier setup releases wrote into consumer configs,
is accepted and dropped, because the wrapper also owns the output location.
Unknown keys, extension loading, module downloads, and extra hook arguments are
rejected before launch. The scanner always receives an explicit
temporary config so automatic configuration discovery cannot change the policy.
`scripts/scan.py --policy-root` reads Checkov policy from that checkout's
`.scanning/configs/.checkov.yaml`, ignoring consumer policy; a missing policy uses
the same safe defaults.

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

Shared writers use atomic replacement and bounded retries for concurrent sharing
and access-denied conflicts. Persistent publication failures block and preserve an
existing report; staging files are cleaned. Fresh path-safety failures stop immediately
and are never retried. This is a shared last-writer-wins report, not an aggregate.

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
- **Prerequisite when upgrading**: Python 3.11+ is required for the staged snapshot
  adapter, including installations that previously ran this hook with only Bash,
  Git and the standalone Trivy binary. Missing or unusable Python blocks before
  Trivy starts, even with `SCAN_ALLOW_TOOL_ERRORS=1`.
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
- **Note**: Prints each staged finding's rule, file, and line, without the secret. A configuration error is an incomplete scan and blocks by default. Invalid findings reports block even with tool-error opt-in; known leaks remain findings. On the inputs in [SECRET-SCANNER-EVALUATION.md](SECRET-SCANNER-EVALUATION.md), the tools detect different patterns. CI secret scans stay on Trivy at HIGH/CRITICAL severity.

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
them per repo (e.g. `setup-scan-fix.py --languages csharp`).

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
- **Behavior**: Runs when the push changes `.cs`/`.csproj` files. Builds the complete pushed solution and surfaces
  the first ~40 analyzer/build error/warning lines. Build or analyzer errors and
  a missing solution block by default (exit 1).
- **Trust**: Runs the project's own build logic with the developer's permissions
  and environment. Use local build hooks only in repositories the developer
  already trusts. The source snapshot provides version fidelity, not host
  isolation; CI is the authoritative security boundary. See
  [the security model](SECURITY-MODEL.md#local-build-hooks-require-a-trusted-repository).

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
- **Runner resolution**: trusted external `SCAN_ESLINT_BIN` and `SCAN_ESLINT_CONFIG`
  by default (ESLint 9+). Missing trusted inputs block. Repository-local/npx
  resolution requires explicit `SCAN_TRUST_REPO_CODE=1` in a trusted repository.
- **Behavior**: Auto-fixes in place. Remaining errors -> exit 1 (re-stage and
  re-commit). Under Lefthook, `stage_fixed: true` re-stages auto-fixed files

#### prettier

- **Purpose**: Prettier auto-format of staged files
- **Stage**: pre-commit
- **Tool**: `prettier --write --ignore-unknown`
- **Files**: `.ts/.tsx/.js/.jsx/.json/.css/.scss/.md`
- **Working dir**: Reads `languages.typescript.build.working_dir`; trusted external
  `SCAN_PRETTIER_BIN` and `SCAN_PRETTIER_CONFIG` are required by default. The explicit
  trusted-repository opt-in permits local package resolution.
- **Behavior**: Reformats in place. Under Lefthook, `stage_fixed: true` re-stages;
  under pre-commit a modified file fails the hook so you re-stage and re-commit.
  A non-zero `prettier` exit (e.g. syntax error) -> exit 1

### SQL

#### sqlfluff

- **Purpose**: SQL linting (staged `.sql` files)
- **Stage**: pre-commit
- **Tool**: `sqlfluff lint`
- **Dialect**: Project configuration when a root `.sqlfluff` exists; otherwise
  the hook supplies `--dialect ansi`, as in v3.0.2.
- **Configuration**: SQLFluff reads the working tree with the project's own
  configuration, ignore files, macro paths and template paths. The hook runs once
  for all staged SQL file names. The scan-config `args` field is ignored; direct
  hook arguments are forwarded.
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
    rev: v3.0.6    # always pin to a release tag, never @main  x-release-please-version
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
