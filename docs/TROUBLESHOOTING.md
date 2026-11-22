# Troubleshooting

This page is organised by what you see. Each entry gives the likely cause and the fix.
It assumes you installed with [Getting started](SETUP-GUIDE.md) (release v3), which
also has a short troubleshooting table at the end.

Two facts explain most problems:

- **Setup runs from the platform clone, not from your repository.** The entry point is
  `python <platform-clone>/scripts/setup-scan-fix.py`, run from your repository's root.
  Setup copies hooks, schemas and a set of shared scripts into your repository, but not
  the setup or verification scripts. Run those from the platform clone you kept in
  [step 4](SETUP-GUIDE.md#4-obtain-and-pin-the-release).
- **Hooks fail closed.** A missing tool, a missing trusted config or a scanner error
  blocks the commit or push. It is never treated as a clean scan.
  `SCAN_ALLOW_TOOL_ERRORS=1` turns tool errors into warnings for a local experiment only.

In the commands below, `$Platform` (PowerShell) or `$PLATFORM` (Bash) is the path of
your platform clone.

## Commit blocked: tool not found

**You see:** `[<hook>] ERROR: trivy not found; scan incomplete` (or `gitleaks`,
`checkov`, `tflint`, `semgrep`, `dotnet`, `sqlfluff`), and the commit stops.

**Cause:** the hook needs that tool and cannot find it on `PATH`. Lefthook runs
`trivy-secrets` and `gitleaks` on every commit, and other hooks when matching files are
staged. See [prerequisites](PREREQUISITES.md) for which hook needs which tool.

**Fix:**

1. Install the locked scanners from the platform clone:

   ```bash
   python "$PLATFORM/scripts/install-scanner.py" trivy
   python "$PLATFORM/scripts/install-scanner.py" tflint
   python "$PLATFORM/scripts/install-scanner.py" gitleaks
   ```

   They go to `~/.local-scanning-tools/bin`. Install Checkov into the scanner virtual
   environment (`python -m pip install checkov==3.4.5`), and Semgrep, the .NET SDK or
   SQLFluff only if you commit those file types.
2. Put the scanner environment and `~/.local-scanning-tools/bin` on `PATH`
   permanently: see [keep the settings](SETUP-GUIDE.md#keep-the-settings-for-new-terminals-ides-and-git-clients).
3. Check the versions. The supported floors are trivy>=0.48.0, checkov>=3.0.0,
   tflint>=0.50.0 and pre-commit>=3.2.0; the release lock installs newer exact
   versions.

   ```bash
   trivy --version
   checkov --version
   tflint --version
   gitleaks version
   ```

**You see:** `... must resolve outside the destination repository`, or a tool is
"rejected inside checkout".

**Cause:** the tool, or the Python environment, is inside the repository you are
scanning. The hooks refuse it, because the repository's contents could replace it.

**Fix:** move the tool or virtual environment outside the repository and put that
location on `PATH`. Do not use `SCAN_ALLOW_TOOL_ERRORS` for this.

## Commit blocked: trusted config not set

**You see:** `Set SCAN_PRETTIER_BIN and SCAN_PRETTIER_CONFIG to external trusted paths`,
`Set SCAN_ESLINT_BIN and SCAN_ESLINT_CONFIG ...`, or `Trusted tool/config missing`.

**Cause:** Lefthook formats staged TS/JS, JSON, CSS, SCSS and Markdown with an external
Prettier, and lints TS/JS with an external ESLint. This happens in every repository,
including Terraform-only ones, because the Lefthook manifest is the same for all
tiers. Setup itself adds JSON files.

**Fix:** provision Prettier (and ESLint for TypeScript) outside the repository and set
the variables, as in [step 5 of Getting started](SETUP-GUIDE.md#5-install-local-hooks).
Then make them permanent. If you do not want local formatting, use the pre-commit
runner, which does not run Prettier.

## Commit works in one terminal but fails elsewhere

**You see:** commits pass in the terminal where you ran setup, but fail in a new
terminal, an IDE or a GUI Git client, with "not found" or "Set SCAN_..." errors.

**Cause:** `export` and `$env:` settings last only for that one terminal.

**Fix:** save `PATH` and the `SCAN_*` variables for your user account and restart the
program: [keep the settings](SETUP-GUIDE.md#keep-the-settings-for-new-terminals-ides-and-git-clients).
On macOS, apps started from the Dock or Finder do not read `~/.zprofile`; start them
from a terminal.

## Hooks fail in an IDE or GUI Git client

Besides the environment issue above:

- **`bash` is the wrong one (Windows).** The hooks need Git Bash 4.4 or later. If the
  client finds `C:\Windows\System32\bash.exe` (WSL) first, put Git for Windows'
  `usr\bin` or `bin` folder earlier on `PATH`, or configure the client to use the
  system Git rather than a bundled one.
- **The client uses its own Git.** Some clients ship a bundled Git with a minimal
  environment. Point the client at the system Git installation.
- **`python` is a different interpreter.** The hooks use the first `python`,
  `python3` or `py` on `PATH`, and it must be 3.11 or later with PyYAML and jsonschema.
  Check with `python -E -P -c "import yaml, jsonschema"` from the same environment the
  client uses.

## Commit blocked: Python errors

**You see:** `Python is required for index snapshots`, `Python is required to read
scan-config.yaml`, or `ModuleNotFoundError: No module named 'yaml'`.

**Cause:** the first Python on `PATH` is too old (the hooks need Python 3.11+) or lacks
PyYAML or jsonschema.

**Fix:** activate or put first on `PATH` the scanner environment from
[step 1](SETUP-GUIDE.md#1-prerequisites), which has `PyYAML==6.0.3` and
`jsonschema==4.26.0`. Keep pre-commit in its own environment: installing pre-commit,
Checkov and the other packages into one environment can fail on conflicting
`packaging` requirements. On Windows, if a system-wide Python comes first, install the
two packages into it as well.

## Push blocked

**You see:** `checkov requires tracked .scanning/configs/.checkov.yaml; no fallback
policy is allowed`.

**Fix:** commit the policy file. If your `.gitignore` ignores `.scanning/`, change it to
the rules in [step 5](SETUP-GUIDE.md#5-install-local-hooks) (ignore `.scanning/*` but
keep `!.scanning/configs/`), or force-add the file:
`git add -f .scanning/configs/.checkov.yaml`. The push scan reads the policy from the
commit being pushed, not from your working tree.

**You see:** `SCAN_TFLINT_CONFIG must name a trusted external config`, `Set
SCAN_TFLINT_PLUGIN_DIR to an external plugin cache`, or `Remove plugin_dir from the
trusted config`.

**Fix:** provision the trusted TFLint config outside the repository and set both
variables, as in [step 5](SETUP-GUIDE.md#5-install-local-hooks). The config must not
contain a `plugin_dir` setting.

**You see:** pushes are not scanned at all with the pre-commit runner, or the setup
verifier reports `pre-commit pre-push hook NOT installed`.

**Cause:** the push transaction adapter is missing. This is the `.git/hooks/pre-push`
script that setup writes. It scans every ref in the push, then hands the push to
pre-commit's own hook, saved as `.git/hooks/pre-push.pre-commit`. Running
`pre-commit install --hook-type pre-push` replaces the adapter with a plain pre-commit
hook that does not scan the pushed objects.

**Fix:** from your repository root, reinstall the adapter:

```bash
python hooks/pre-push.py --install-pre-commit
```

Do not run `pre-commit install --hook-type pre-push` afterwards. If the command says
`Original pre-push runner is missing`, restore `.git/hooks/pre-push.pre-commit` (for
example by running `pre-commit install --hook-type pre-push` once, **before** the command
above) and run it again.

A direct `pre-commit run --hook-stage pre-push --all-files` has no Git push
transaction and blocks by design. Test with a real push, or with the
[local transaction test](TESTING-GUIDE-CONSUMING-REPO.md#push-transaction-without-a-network-push).

**You see:** `Bash is required for the hook runner` or a Bash version message.

**Fix:** install Bash 4.4 or later. On Windows use Git Bash; on macOS run
`brew install bash` and put `$(brew --prefix bash)/bin` first on `PATH`.

## Commit or push blocked by a finding

**You see:** lines such as:

```text
[trivy-secrets] Scanning... (3 staged files)
[trivy-secrets]   CRITICAL  aws-access-key-id  config/settings.json:4-4
[trivy-secrets]     AWS Access Key ID
[trivy-secrets] FAIL: 1 findings (1 critical, 0 high, 0 medium, 0 low)
```

**Fix:** remove the secret or fix the misconfiguration, stage the change and commit
again. If the secret was real, rotate it: it may already exist in another commit or
on another machine. If a finding is a reviewed false positive, record an exception as
in [suppressions and baselines](SETUP-GUIDE.md#9-suppressions-and-baselines). Without
`jq` installed, the Bash hooks print the counts but not the finding lines.

## Suppression validation errors

**You see:** `validate-suppressions` or the CI aggregate fails with codes such as
`V-003`, `V-007` or `V-010`.

**Cause and fix:** the registry `.scan-suppressions.yaml` uses schema `2.0`
(`schema_version: '2.0'`; see `configs/common/.scan-suppressions.yaml`). Each entry
under `trivy_suppressions`, `checkov_suppressions` or `tflint_suppressions` needs:

- `rule_id`, `tool`, `reason`, `owner`, `severity`, `approved_date` and `expires_date`
  (dates as `YYYY-MM-DD`) (`V-003`);
- `fingerprint`: a `v1:` occurrence fingerprint copied from a current scan report, which
  identifies exactly one finding (`V-010`);
- `approved_by` for CRITICAL and HIGH, and any other level listed in
  `settings.require_security_approval` (`V-007`);
- an expiry no more than 180 days after approval (or the registry's shorter
  `max_expiry_days`).

Get current fingerprints with:

```bash
python scripts/scan.py . --skip-baseline --skip-suppressions --format json
```

Validate the registry from your repository root:

```bash
python scripts/validate-suppressions.py .scan-suppressions.yaml
python scripts/validate-suppressions.py --strict .scan-suppressions.yaml
```

Schema `1.0` entries (without `fingerprint`) are rejected unless you opt in during a
reviewed migration. See [suppression governance](SUPPRESSION-GOVERNANCE.md) for the
full format and the migration options.

## Setup verification output

Setup ends by running `scripts/verify-scanning.ps1` from the platform clone. Expect
exit 0 and no failed checks; a missing optional `.trivyignore` is only a warning. If
setup prints `SETUP COMPLETED WITH ERRORS`, run the verifier yourself from your
repository root to see every message:

```powershell
pwsh -NoProfile -File "$Platform/scripts/verify-scanning.ps1" -HooksRunner lefthook -Tier standard
```

Use your runner and tier. Common failures:

- **`Checkov NOT FOUND`, `tflint NOT FOUND`, `Terraform NOT FOUND`, or `Trusted external
  tflint configuration NOT FOUND` in an application-only repository.** The verifier
  skips them only when `scan-config.yaml` disables Terraform and enables another
  language, and neither the working tree, the index nor a local branch tip has a `.tf`
  or `.tf.json` file. Its `Terraform remains in scope` line says which condition
  failed. Fix that, or install the tools and provision the config as in
  [step 5](SETUP-GUIDE.md#5-install-local-hooks).
- **`Cannot verify template hooks`.** The verifier compares your `lefthook.yml` or
  `.pre-commit-config.yaml` with the shipped template exactly. Verify before you
  customise the file or replace the pre-commit `rev:` tag with a SHA, then review those
  changes separately.
- **`lefthook pre-commit hook NOT installed`.** Run `lefthook install` from the
  repository root.

If you write your own wrapper around the verifier, let it run to the end and keep its
exit status. In PowerShell, keep `-Wait` in `Select-Object -First 30 -Wait` and check
`$LASTEXITCODE` straight after. In Bash, enable `pipefail` and save the verifier's
`PIPESTATUS` entry before running another command. A reader that stops early can cut
the verifier off before it reports a failure.

## CI: SARIF upload fails

**You see:** an upload step fails with `Resource not accessible by integration`, or a
permission error.

**Cause:** the caller does not grant a permission the called workflow asks for. Every
caller (and every intermediate reusable workflow) needs `contents: read`,
`actions: read` and `security-events: write`. The Terraform caller also needs
`pull-requests: write` for its pull request comment. A called workflow cannot raise
its permissions above the caller's.

**Fix:** use the `permissions:` block from the shipped caller templates
(`templates/workflows/`), shown in [step 6](SETUP-GUIDE.md#6-configure-ci-callers).
Keep `actions: read` even if uploads are off: the jobs request it anyway.

**You see:** uploads fail in a private repository even with the right permissions.

**Cause:** code scanning is not available or not enabled for that repository on its
plan.

**Fix:** set `upload-sarif: false` on both callers. Scans and their gates still run.

```yaml
jobs:
  terraform-scan:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@<full-sha> # v3.1.2
    with:
      cloud-provider: aws
      scanning-repo-ref: <full-sha>
      upload-sarif: false
```

Large reports are truncated before upload: each run keeps its 5,000 most severe
results and gets one `scan-truncation-warning` result.

## CI: language detection or the secret scan fails on the first pull request

**Cause:** the app-code scan reads `scan-config.yaml` from the pull request's base
commit, not from the pull request. On the first adoption pull request, the base has no
config yet.

**Fix:** merge the reviewed `scan-config.yaml` and scanner policy first in a separate
pull request without the caller workflows, then add the callers. See
[step 6](SETUP-GUIDE.md#6-configure-ci-callers) and the
[example repositories](../examples/).

## Windows

- **Use PowerShell 7 (`pwsh`)**, not Windows PowerShell 5.1, for setup and
  verification. The dispatcher runs the PowerShell version of each hook with `pwsh` if
  it is installed.
- **Execution policy.** The dispatcher starts hooks with `-ExecutionPolicy Bypass`. If
  your own scripts are blocked, run
  `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`; this needs no
  administrator rights. A policy set by your organisation can override it.
- **Line endings.** Shell files must stay LF. Add the `.gitattributes` rules from
  [step 5](SETUP-GUIDE.md#5-install-local-hooks) before staging, and clone with
  `git -c core.autocrlf=false clone ...`. A CRLF shell script fails with errors such as
  `$'\r': command not found`.
- **ARM64.** `scripts/install-scanner.py` supports Windows on x64 only.
- **Trivy "database locked".** Two Trivy processes used the cache at the same time. The
  hooks retry once after two seconds. If it persists, make sure no other Trivy process
  is running, then run `trivy clean --all` and try again.

## Getting more detail

1. Run the hooks with verbose output: `SCAN_VERBOSE=1 git commit ...` (PowerShell:
   `$env:SCAN_VERBOSE = '1'`).
2. Run every pre-commit-stage hook without committing: `lefthook run pre-commit --all-files`
   or `pre-commit run --all-files`.
3. Read `.scanning/last-scan.json`, which the last hook that produced a report wrote.
4. With pre-commit, read its log: `~/.cache/pre-commit/pre-commit.log`.
5. See the [hook reference](HOOK-REFERENCE.md) for each hook's behaviour and exit codes.

If you think you found a security problem in the platform itself, do not open a public
issue; follow [SECURITY.md](../SECURITY.md).
