# App-Code Scanning (LAYER A)

The platform scans **application code** — C#/.NET, TypeScript/JavaScript, and SQL — alongside
the original Terraform/IaC scanning, using the **same** OS-detecting dispatcher, the **same**
`scan-config.yaml` seam, and the **same** reusable-workflow pattern. Nothing about Terraform
scanning changed.

---

## 1. Enable a language

In `scan-config.yaml`, flip `enabled` and (for C#) point at your solution:

```yaml
languages:
  csharp:
    enabled: true
    file_patterns: ["**/*.cs", "**/*.csproj", "**/*.slnx"]
    build:
      solution: "api/App.slnx"   # empty "" => auto-detect nearest .sln/.slnx
      working_dir: "api"         # run dotnet from here
    tools:
      semgrep_csharp: { enabled: true, args: ["--config=p/csharp", "--error", "--metrics=off"], stage: pre-commit }
      dotnet_format:  { enabled: true, args: ["--verify-no-changes", "--no-restore"], stage: pre-commit }
      dotnet_build:   { enabled: true, args: ["/p:AnalysisMode=AllEnabledByDefault"], stage: pre-push }
  typescript:
    enabled: true
    build: { working_dir: "mobile" }      # monorepo subdir with package.json
    tools:
      eslint:   { enabled: true, args: ["--fix"], stage: pre-commit }
      prettier: { enabled: true, args: ["--write"], stage: pre-commit }
      semgrep_typescript: { enabled: true, args: ["--config=p/typescript", "--error", "--metrics=off"], stage: pre-commit }
  sql:
    enabled: true
    tools:
      sqlfluff: { enabled: true, args: ["lint", "--dialect=ansi"], stage: pre-commit }
```

`setup-scan-fix --languages csharp,typescript,sql` writes this for you from a tier template.

---

## 2. The build path is **config**, never hardcoded

The single most important design point: `dotnet-format` and `dotnet-build` read the solution
and working directory from `languages.csharp.build.{solution,working_dir}`. They never hardcode
a path. This is the generic fix for the old `api/`-path bug, and it is enforced by a test
(`tests/python/test_dotnet_format_path.py`) that fails if any hook hardcodes a solution.

- `solution: ""` → the hook auto-detects the nearest `.slnx`/`.sln` under `working_dir`.
- `working_dir` also scopes which staged files are passed to `--include` (monorepo-friendly).

---

## 3. The hooks (same pattern as Terraform)

Each app-code hook ships as a `.sh` + `.ps1` pair under `hooks/`, dispatched by
`hooks/dispatcher.sh` (Windows → `.ps1`, else `.sh`), sharing `hooks/lib/common.{sh,ps1}`. They
all: check the tool with **fail-open** (`require_tool` → exit 0 if absent), scan **only staged
files** (via the git index), write `.scanning/last-scan.json`, and classify exit codes
(`0` pass / `1` findings / `2+` infra error → fail-open).

| Hook | What it runs | Stage | Notes |
|---|---|---|---|
| `semgrep-csharp` | `semgrep --config p/csharp --error` | pre-commit | native Windows (`PYTHONUTF8=1`); override via `SEMGREP_RULESET_CSHARP` |
| `semgrep-typescript` | `semgrep --config p/typescript --error` | pre-commit | override via `SEMGREP_RULESET_TYPESCRIPT` |
| `dotnet-format` | `dotnet format <sln> --verify-no-changes` | pre-commit | solution/working_dir from config |
| `dotnet-build` | `dotnet build <sln> /p:AnalysisMode=AllEnabledByDefault` | pre-push | Roslyn analyzers; heavier |
| `eslint` | `eslint --fix` (local/npx) | pre-commit | gates on remaining errors; `stage_fixed` under Lefthook |
| `prettier` | `prettier --write` | pre-commit | auto-format; `stage_fixed` under Lefthook |
| `sqlfluff` | `sqlfluff lint --dialect ansi` | pre-commit | |
| `validate-scan-config` | validate `scan-config.yaml` vs schema | pre-commit | runs only when the config is staged |

Both **Lefthook** (default) and **pre-commit** invoke these same scripts, so behaviour is
identical across runners. Hooks stay **< 15s** by scanning staged files only (Semgrep startup
dominates; the registry pack is cached after first run).

### Windows + agentic friction

Semgrep runs the **Fall-2025 native-Windows path — no WSL** — and the hooks export
`PYTHONUTF8=1` belt-and-braces so a cp1252 console never breaks a scan. Staged-only +
parallel keeps hooks fast enough that an autonomous agent never has a reason to bypass them.

---

## 4. CI — distinct SARIF categories

`.github/workflows/code-security-scan.yml` (reusable `workflow_call`) auto-detects the enabled
app-code languages from `scan-config.yaml`, runs Semgrep **per language**, and uploads SARIF
under **distinct categories** — `"<ci.sarif.category_prefix>semgrep-<lang>"` (e.g.
`scan-semgrep-csharp`, `scan-semgrep-typescript`) plus `scan-trivy-secrets`. Distinct categories
are required since GitHub's 2025-07-22 change rejects same tool+category SARIF collisions.

Drop in the thin caller `templates/workflows/code-security-scan.yml` (pinned `@v2.0.0`):

```yaml
jobs:
  code-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v2.0.0
    with: { category-prefix: "scan-", fail-on-findings: true }   # languages auto-detected
    permissions: { contents: read, security-events: write, pull-requests: write }
```

---

## 5. Custom rules

Point the Semgrep hooks at your own ruleset (a file or registry pack) via
`SEMGREP_RULESET_CSHARP` / `SEMGREP_RULESET_TYPESCRIPT`. The test suite uses this to run a
deterministic local rule (`tests/fixtures/semgrep-rules/planted.yaml`) so CI doesn't depend on
volatile remote-pack contents — and you can do the same for org-specific rules.

## 6. Verify

```bash
# app-code hooks against planted fixtures (deterministic local rule)
bash tests/integration/test-app-code-hooks.sh
# config-driven dotnet path + the gate
python -m pytest tests/python/test_dotnet_format_path.py tests/python/test_check_fix_allowlist.py -q
```
