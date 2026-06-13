# Quickstart 002 — scan→fix platform

The shortest path from zero to a working scan (+ optional fix) in a consumer repo. Full guide:
[`docs/QUICK-START-5MIN.md`](../../docs/QUICK-START-5MIN.md).

## Prerequisites

- git; PowerShell 7 **or** bash; Python 3.8+ (for config validation/rendering).
- Tools for the languages you enable: `semgrep`, `.NET SDK` (C#), Node/`npm` (TS), `trivy`,
  `lefthook` (default runner). `gh` CLI for labels/secret verification.

## 1. Onboard (one idempotent command)

```powershell
# scan C#/TS, standard tier, default Lefthook runner, enable the fix-loop
path/to/auto-code-scanning/scripts/setup-scan-fix.ps1 `
  -Languages csharp,typescript -Tier standard -EnableFixLoop
```
```bash
python path/to/auto-code-scanning/scripts/setup-scan-fix.py \
  --languages csharp,typescript --tier standard --enable-fix-loop
# pre-commit instead of Lefthook:  --hooks-runner pre-commit
# Terraform only:                  --languages terraform --cloud-provider aws
```

This writes `scan-config.yaml`, vendors `hooks/` + scripts, installs the runner + the `.claude/`
in-session bundle + thin caller workflows, creates the `ai-autofix` / `needs-human-review`
labels, **verifies** `AUTOFIX_TOKEN` / `ANTHROPIC_API_KEY`, and runs verify-scanning.

## 2. Test Layer A locally

```bash
# stage a C# change and commit — semgrep-csharp + dotnet-format run in < 15s
git add src/Foo.cs && git commit -m "test"
# or run the runner directly:
lefthook run pre-commit         # (or: pre-commit run --all-files)
```

## 3. Wire CI (pin the tag!)

The setup copied `.github/workflows/code-security-scan.yml` (app-code, distinct SARIF) and, if
chosen, `terraform-scan.yml` + `autonomous-fix.yml`. Confirm each `uses:` is pinned to `@v2.0.0`.

## 4. Turn on the fix-loop (optional)

1. Create the two secrets (the platform only **verifies** them):
   - `AUTOFIX_TOKEN` — fine-grained PAT: *Contents RW + Pull-requests RW, this repo only*.
   - `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`).
2. `fix_loop.enabled: true` in `scan-config.yaml`; tune `allowlist_paths` + `build_verify_cmd`.
3. Add the **`ai-autofix`** label to a PR; a trusted review triggers the two-job loop.

See [`docs/FIX-LOOP.md`](../../docs/FIX-LOOP.md) and [`docs/SECURITY-MODEL.md`](../../docs/SECURITY-MODEL.md).

## 5. Verify the platform itself

```bash
python -m pytest tests/python -q                      # 127 passing
bash tests/integration/test-app-code-hooks.sh         # app-code hooks vs planted fixtures
python scripts/validate-scan-config.py                # config conforms to schema
```
