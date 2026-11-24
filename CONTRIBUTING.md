# Contributing

Thank you for helping. This guide is for people who change auto-code-scanning itself.
If you want to **use** it in your own repository, start with the
[documentation index](docs/README.md) and the [5-minute quick start](docs/QUICK-START-5MIN.md)
instead.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Do not report security vulnerabilities in public issues or pull requests: see the
[security policy](SECURITY.md).

## Before you start

- For a bug, open an issue with the bug report form first, unless the fix is small and obvious.
- For a new feature or a behaviour change, open a feature request first so the design can be
  agreed before you write code.
- Read the reference for the part you change: [hooks](docs/HOOK-REFERENCE.md),
  [reusable workflows](docs/REUSABLE-WORKFLOWS.md) or the
  [security model](docs/SECURITY-MODEL.md).

## Set up a contributor checkout

Install Git, Python 3.11+, Bash 4.4+, PowerShell 7 and the scanners listed in
[Getting started prerequisites](docs/SETUP-GUIDE.md#1-prerequisites). On Windows use Git
for Windows and Git Bash, not the WSL launcher named `bash`. On macOS run
`brew install bash` and put `$(brew --prefix bash)/bin` first on PATH. On Linux use
the supported packages for your distribution, including Python venv support and
PowerShell 7. Keep Python environments and scanner installations outside the checkout.

Fork the repository on GitHub, then clone your fork with LF line endings on every
platform (the commands work in PowerShell or Bash). Replace `YOUR-USER` with your
GitHub user name:

```bash
git -c core.autocrlf=false clone https://github.com/YOUR-USER/auto-code-scanning.git auto-code-scanning
cd auto-code-scanning
git switch -c docs/my-change
```

Name the branch after the kind of change (`fix/…`, `feat/…`, `docs/…`). Create an
external Python environment. Windows, from PowerShell 7:

```powershell
python -m venv "$HOME/.venvs/acs-contribute"
& "$HOME/.venvs/acs-contribute/Scripts/Activate.ps1"
python -m pip install pytest==9.2.0 pytest-cov==7.1.0 pytest-xdist==3.8.0 PyYAML==6.0.3 jsonschema==4.26.0 pre-commit==4.7.0
pwsh -NoProfile -Command 'Install-Module Pester -Scope CurrentUser -MinimumVersion 5.0 -Force'
```

macOS/Linux:

```bash
python3 -m venv "$HOME/.venvs/acs-contribute"
. "$HOME/.venvs/acs-contribute/bin/activate"
python -m pip install pytest==9.2.0 pytest-cov==7.1.0 pytest-xdist==3.8.0 PyYAML==6.0.3 jsonschema==4.26.0 pre-commit==4.7.0
pwsh -NoProfile -Command 'Install-Module Pester -Scope CurrentUser -MinimumVersion 5.0 -Force'
```

For scanner checks, install the release-locked binaries with
`scripts/install-scanner.py`. From the checkout root, install all three:

```bash
python scripts/install-scanner.py trivy
python scripts/install-scanner.py tflint
python scripts/install-scanner.py gitleaks
```

In PowerShell, add their directory with
`$env:PATH = "$HOME/.local-scanning-tools/bin;$env:PATH"`. In the Git Bash,
macOS or Linux session used for the CI parity checks, run
`export PATH="$HOME/.local-scanning-tools/bin:$PATH"` too.

Keep Checkov in a separate external environment from the test packages: the runner
dependencies and Checkov have incompatible `packaging` requirements. Keep the
contributor environment active. In PowerShell:

```powershell
python -m venv "$HOME/.venvs/acs-checkov"
& "$HOME/.venvs/acs-checkov/Scripts/python.exe" -m pip install checkov==3.4.5
$env:CHECKOV_PYTHON = "$HOME/.venvs/acs-checkov/Scripts/python.exe".Replace('\', '/')
& $env:CHECKOV_PYTHON -m checkov.main --version
```

macOS/Linux:

```bash
python -m venv "$HOME/.venvs/acs-checkov"
"$HOME/.venvs/acs-checkov/bin/python" -m pip install checkov==3.4.5
export CHECKOV_PYTHON="$HOME/.venvs/acs-checkov/bin/python"
"$CHECKOV_PYTHON" -m checkov.main --version
```

The CI parity loop below uses this explicit interpreter. On Windows, Checkov's
`.cmd` launcher selects Python from PATH, so adding its directory after the test
environment is not enough. Use the module command above for contributor checks;
consumer hooks use the active scanner environment from Getting started. Install
Semgrep, .NET and Node tooling when you exercise their integration suites. The exact
hosted dependency versions live in `.github/workflows/ci.yml`.

## Run checks before opening a pull request

From the checkout root, run the complete Python suite:

```bash
python -m pytest tests/python/ -n auto --dist worksteal -v --tb=short
```

`-n auto` uses the available CPUs; `--dist worksteal` balances individual tests
across workers, including the slow integration files. To debug serially, replace
`-n auto` with `-n 0`. Tests must use unique temporary directories and restore
process state; real pre-commit tests use the `isolated_pre_commit_home` fixture.

Run the PowerShell suite with Pester 5 (a PowerShell test framework):

```bash
pwsh -NoProfile -Command 'Get-Module Pester | Remove-Module -Force; Import-Module Pester -MinimumVersion 5.0 -Force; $c = New-PesterConfiguration; $c.Run.Path = "tests/unit/"; $c.Run.Exit = $true; $c.Output.Verbosity = "Detailed"; Invoke-Pester -Configuration $c'
```

Then run every applicable command in [Local CI parity](#local-ci-parity) from Bash.
Leave `set -euo pipefail` enabled, record raw scanner exits as well as deliberately
tolerated policy findings, and keep the logs. A local pass is not evidence of a hosted
upload or permission check; the jobs that run only in CI are listed after the block.

On Windows, open Git Bash or launch it explicitly from PowerShell:

```powershell
& 'C:/Program Files/Git/bin/bash.exe' --noprofile --norc
```

Verify `command -v bash` and `bash --version` inside the selected shell. If you open
Git Bash on its own rather than from the configured PowerShell session, prepare the
new shell first:

```bash
source "$HOME/.venvs/acs-contribute/Scripts/activate"
export PATH="$HOME/.local-scanning-tools/bin:$PATH"
export CHECKOV_PYTHON="$HOME/.venvs/acs-checkov/Scripts/python.exe"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
python --version
"$CHECKOV_PYTHON" -m checkov.main --version
```

Use the paths you actually created if they differ. Environment changes made in
one terminal do not configure a terminal opened separately.

Keep terminal and child-process output at UTF-8. In PowerShell set
`$env:PYTHONUTF8 = '1'` and `$env:PYTHONIOENCODING = 'utf-8'` before the test
commands; in Git Bash use `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`. Two tests in
`tests/python/test_hook_integrity.py` have failed on Windows when console encoding
changed non-ASCII output:
`test_powershell_reads_nul_paths_without_native_line_splitting` and
`test_distinct_git_directory_names_survive_ordinal_deduplication`. They are not
expected failures. If they recur, record the interpreter, shell and traceback, and
rerun the failed case on its own to tell an encoding problem from a real regression.
Do not change scanner behaviour to hide an encoding failure.

### Local CI parity

These commands mirror what CI runs on a pull request. Prerequisites: Bash 4.4 or later,
Python 3.11+ with the test packages above, Trivy, Checkov, TFLint and PowerShell 7
with Pester 5 on PATH. On macOS the system `/bin/bash` is too old; use the Homebrew
Bash. CI downloads Trivy 0.76.2 with a pinned SHA-256 and pins Checkov 3.4.5,
TFLint 0.66.0 and PyYAML 6.0.3. The release lock (`scripts/scanner-downloads.json`)
and the workflow files hold the exact pins; locally installed versions can differ.

```bash
set -euo pipefail   # a failed check stays a failure, loops included
# ci.yml "Lint & Validate": Python 3, pre-commit 4.7.0 and PyYAML 6.0.3
python -c "import yaml; yaml.safe_load(open('.pre-commit-hooks.yaml'))"
python -c "import yaml; yaml.safe_load(open('configs/common/.scan-suppressions.yaml'))"
for f in templates/*/pre-commit-config.yaml configs/*/.checkov.yaml configs/*/policy-overlay.yaml configs/common/noisy-checks-*.yaml; do python -c "import yaml; yaml.safe_load(open('$f'))"; done
for f in schemas/*.json; do python -c "import json; json.load(open('$f'))"; done
for f in configs/*/.checkov.yaml; do python -c "import yaml,sys; d=yaml.safe_load(open('$f')); sys.exit(1 if d and 'check' in d else 0)"; done

# ci.yml "Run Python tests": Python 3.11 (setup-python v7.1.0), pytest + xdist
python -m pip install pytest==9.2.0 pytest-cov==7.1.0 pytest-xdist==3.8.0 PyYAML==6.0.3 jsonschema==4.26.0 pre-commit==4.7.0
pytest tests/python/ -n auto --dist worksteal -v --tb=short

# ci.yml "Run Pester tests": Pester 5, shell pwsh
pwsh -NoProfile -Command 'if (Test-Path "tests/unit/*.Tests.ps1") { Get-Module Pester | Remove-Module -Force; Import-Module Pester -MinimumVersion 5.0 -Force; $c = New-PesterConfiguration; $c.Run.Path = "tests/unit/"; $c.Run.Exit = $true; $c.Output.Verbosity = "Detailed"; Invoke-Pester -Configuration $c } else { Write-Host "No Pester tests found" }'

# ci.yml "test-hooks": same verified Trivy 0.76.2, Checkov 3.4.5, TFLint 0.66.0 (setup-tflint v6.3.2) versions and
# aws/azure/gcp matrix, but stricter: a dedicated CHECKOV_PYTHON interpreter (see above) and a
# nonzero-exit check CI's own job does not have (it runs plain `checkov` and ignores its exit code with `|| true`).
: "${CHECKOV_PYTHON:?Set CHECKOV_PYTHON to the external scanner Python - see Contributing}"
"$CHECKOV_PYTHON" -m checkov.main --version   # missing interpreter/module must stop the loop
for cloud in aws azure gcp; do
  FIXTURE="tests/fixtures/terraform-valid/"; [ -d "${FIXTURE}${cloud}" ] && FIXTURE="${FIXTURE}${cloud}"   # the cloud's own fixture, as CI selects it
  trivy config "$FIXTURE" --severity CRITICAL --exit-code 1 --quiet --skip-check-update
  trivy fs "$FIXTURE" --scanners secret --severity HIGH,CRITICAL --exit-code 1 --quiet
  checkov_status=0
  "$CHECKOV_PYTHON" -m checkov.main -d "$FIXTURE" --config-file "configs/${cloud}/.checkov.yaml" --quiet || checkov_status=$?
  printf 'Checkov (%s) raw exit: %s\n' "$cloud" "$checkov_status"
  # Exit 1 may be a finding or an error: inspect the scanner output before accepting it.
  if [ "$checkov_status" -gt 1 ]; then exit "$checkov_status"; fi
  tflint --init --config="configs/${cloud}/.tflint.hcl"
done

# reusable-scan-self-test.yml "Prepare both consumer inputs": PyYAML 6.0.3
python -m pip install --disable-pip-version-check PyYAML==6.0.3
GITHUB_OUTPUT=$(mktemp) GITHUB_STEP_SUMMARY=$(mktemp) CHECKOV_SKIP_CHECKS=CKV_AZURE_33,CKV_AZURE_33 CHECKOV_RENDER_ITER_COUNT=20 python scripts/checkov-consumer-options.py prepare configs/azure/.checkov.yaml   # the script appends to GITHUB_OUTPUT and GITHUB_STEP_SUMMARY, so give it files

# Repository-wide secret scan (also used by the app-code scan workflow)
trivy fs . --scanners secret --severity HIGH,CRITICAL --exit-code 1
```

If a Windows checkout has CRLF shell files, run shell checks on an LF copy:
`tmp=$(mktemp -d) && git -c core.autocrlf=false archive HEAD | tar -x -C "$tmp" && cd "$tmp"`.
`git archive` copies the last commit only, so commit what you want checked first. A
command that needs the Git index (`git ls-files`, `git diff`) runs in the checkout
itself, not in the copy. Where a tool reads a single file, strip `\r` with
`sed 's/\r$//'`.

These checks run only in CI:

- `semgrep.yml`: `semgrep ci` needs `SEMGREP_APP_TOKEN` (semgrep 1.184.0).
- `ci.yml` integration: it installs Trivy with apt on the runner and builds a throwaway Git repository.
- `reusable-scan-self-test.yml` scan and verify: the reusable workflow uploads SARIF, and verify reads those artifacts.
- `performance-check.yml` times Trivy, Checkov and TFLint against the fixtures, and fails above 5000 ms per
  hook, 10000 ms for the pre-commit total or 60000 ms for the pre-push total. The local loop above covers less.
- `bypass-detection.yml`: it reads the push event and only warns.
- `copilot-setup-steps.yml`: it runs only when its own workflow file changes.
- The automated review workflows: they post a review and need a token.

### Documentation changes

The repository has no Markdown lint or link-check job. For documentation changes, run
`git diff --check`, check that every relative link and anchor resolves, and run any
command you changed. A changed setup path must install real hooks and make a scanned
commit in a throwaway local consumer repository; do not push test data.

## Forks and CI

Some of this repository's own workflows need secrets that only maintainers hold: the
Claude and Gemini review workflows, the Semgrep app token and the release GitHub App.
On a pull request from a fork those workflows skip or fail. That is expected and does
not block review. The test, lint and self-test jobs run without secrets.

## Open the pull request

1. Keep the change focused. Review `git diff`, and make sure shared consumer files still
   work from both hook shells (Bash and PowerShell).
2. Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
   (`fix: …`, `feat: …`, `docs: …`).
3. Give the pull request a Conventional Commit title. Maintainers squash-merge, so the
   title becomes the commit on `main` and decides the next version (see below).
4. Fill in [the pull request template](.github/pull_request_template.md): what changed,
   how you tested it, and any check you skipped and why.
5. Leave generated release files alone: `CHANGELOG.md`, `version.txt` and the lines marked
   `x-release-please-version` are updated by the release process.

### Commit types decide the version

| Commit | Changelog section | Version bump |
| --- | --- | --- |
| `feat: …` | Features | minor |
| `fix: …` | Bug Fixes | patch |
| `perf: …` | Performance Improvements | patch |
| `revert: …` | Reverts | patch |
| any type with `!` (`feat!: …`, `ci!: …`) or a `BREAKING CHANGE:` footer | ⚠ BREAKING CHANGES | major |
| `docs`, `chore`, `ci`, `test`, `style`, `refactor`, `build` | hidden | none |

- The largest bump among the commits since the last release wins.
- Hidden types never start a release on their own and never appear in the changelog.
  They ship in the next release that has a visible commit.
- Write a revert as `revert: <subject of the reverted commit>`. Git's default
  `Revert "…"` message is not a Conventional Commit, and the release tooling ignores it.

### Commit identities

GitHub lists every author and every co-author (`Co-authored-by` line) of a commit on
`main` as a contributor. An AI assistant must never appear there (maintainer's
policy, 2026-11-23).

- An AI assistant such as Claude or Codex, or a model such as Opus or GPT-5, must not
  be a commit's author or committer, and no `Co-authored-by` line may name one.
  Agents may push commits made under a human or orchestrator identity.
- Every other identity passes: people, code-quality bots (CodeRabbit, Semgrep,
  SonarCloud), Dependabot, the release bot and this repository's workflow bots.
- Commit subjects and bodies, branch names and PR titles are not checked, so they may
  name a tool. A `Signed-off-by` line is not contributor credit and is not checked.
- PR and issue descriptions must not carry AI attribution wording: no
  `Co-authored-by` line naming an AI assistant and no "Generated with" byline naming
  one. Other text may name any tool.
- The Contributor Identities workflow reports any author, committer or co-author that
  matches a pattern in `.github/contributor-identities/ai-assistants.txt`, by name
  or by address. The `main` ruleset requires this check, so a red result blocks the
  merge. Re-commit the change under a permitted identity and drop the trailer.
- Add a pattern to the list when a new AI assistant can author commits.

How releases are cut, and what consumers must do to pick one up, is in
[the maintainer guide](docs/MAINTAINERS.md).

## Adding a new hook

1. Add the hook definition to `.pre-commit-hooks.yaml`.
2. Add test fixtures in `tests/fixtures/`.
3. Add integration tests under `tests/`.
4. Update `docs/HOOK-REFERENCE.md`.
5. Update the relevant templates.

## Adding a new cloud provider

1. Create `configs/{provider}/.checkov.yaml` with CIS Benchmark checks.
2. Create `configs/{provider}/.tflint.hcl` with the provider plugin.
3. Create `templates/{provider}/pre-commit-config.yaml`.
4. Add the test fixture `tests/fixtures/terraform-{provider}-fail/`.
5. Update `docs/MULTI-CLOUD.md`.

## Code standards

- PowerShell scripts follow PSScriptAnalyzer rules.
- YAML files must be valid.
- Keep hooks within the documented per-tier time budgets; first-run downloads are measured
  separately. CI fails when a timed fixture scan exceeds 5000 ms.
- Every feature needs documentation.
