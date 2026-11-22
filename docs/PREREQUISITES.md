# Prerequisites

This page lists the tools to install before you run setup. What you need depends on
three choices:

- **Repository type:** Terraform only, application code only (C# or TypeScript), or both.
- **Hook manager:** Lefthook (the default) or pre-commit. A **hook** is a program Git
  runs before a commit or a push.
- **Operating system:** Windows, macOS or Linux.

Install every tool **outside** the repository you are protecting. The hooks refuse a
tool or Python environment that lives inside the checkout, even with
`SCAN_ALLOW_TOOL_ERRORS=1`.

The versions below are for release `v3.1.2`. [Getting started](SETUP-GUIDE.md#1-prerequisites)
is the source of truth for floors and exact pins; if the two pages disagree, follow
Getting started and report the difference.

## Tools every repository needs

| Tool | Version | Why |
|---|---|---|
| Git | 2.0 or later | Repository, index and hooks. |
| Bash | 4.4 or later | The hook dispatcher (`hooks/dispatcher.sh`) and shell hooks. On Windows use Git Bash, not the WSL `bash` launcher. On macOS the system `/bin/bash` is too old: install one with Homebrew. |
| Python | 3.11 or later, with PyYAML 6.0.3 and jsonschema 4.26.0 | Setup, config validation, and the snapshots the hooks scan. Keep it in a virtual environment outside the repository. |
| PowerShell (`pwsh`) | 7 or later | Setup runs `scripts/verify-scanning.ps1` on every OS. On Windows the dispatcher also runs the PowerShell version of each hook. |
| Trivy | 0.76.2 (installed by `scripts/install-scanner.py`; floor 0.48.0) | The `trivy-secrets` hook runs on every commit in every tier and runner. |
| Gitleaks | 8.30.1 (installed by `scripts/install-scanner.py`) | Lefthook runs `gitleaks` on every commit. With pre-commit, the standard and strict templates run it. |
| Lefthook **or** pre-commit | Lefthook 1.6.0 or later (`min_version` in `templates/lefthook/lefthook.yml`); pre-commit 4.7.0 (floor 3.2.0) | Runs the hooks. Install pre-commit in its own virtual environment, separate from the scanner environment: its `virtualenv` dependency can need a newer `packaging` than Checkov accepts. |

## Tools by repository type

| Tool | Version | Terraform only | App only | Both | Why |
|---|---|---|---|---|---|
| Terraform CLI | Your project's `required_version` | Yes | No, see note 1 | Yes | Formatting and validation hooks; the setup verifier checks it. |
| TFLint | 0.66.0 (installed by `scripts/install-scanner.py`; floor 0.50.0) | Yes | No, see note 1 | Yes | Push-time lint. Needs a trusted config outside the repository (`SCAN_TFLINT_CONFIG`, `SCAN_TFLINT_PLUGIN_DIR`). |
| Checkov | 3.4.5 (floor 3.0.0), in the scanner virtual environment | Yes | No, see note 1 | Yes | Push-time policy scan; the setup verifier checks it. |
| terraform-docs | 0.12.0 or later | pre-commit strict, aws, azure and gcp templates only | No | Same as Terraform only | The `terraform_docs` hook in those templates. Lefthook does not use it. |
| Semgrep | 1.60 or later (CI uses 1.184.0) | No | Yes | Yes | Lefthook runs `semgrep-csharp` on staged `.cs` files and `semgrep-typescript` on staged TS/JS files. |
| .NET SDK | 8 or later, or your project's SDK | No | C# only | C# only | Lefthook runs `dotnet-format` on staged `.cs`/`.csproj` files and `dotnet-build` at push. |
| Node.js and npm | A supported LTS release | Lefthook only, see note 2 | Lefthook | Lefthook | Installs Prettier and ESLint outside the repository. |
| Prettier | 3.6.2, outside the repository | Lefthook only, see note 2 | Lefthook | Lefthook | Lefthook formats staged TS/JS, JSON, CSS, SCSS and Markdown. Set `SCAN_PRETTIER_BIN` and `SCAN_PRETTIER_CONFIG`. |
| ESLint | 9 or later, outside the repository | No | TypeScript with Lefthook | TypeScript with Lefthook | Lefthook lints staged TS/JS. Set `SCAN_ESLINT_BIN` and `SCAN_ESLINT_CONFIG`. |
| SQLFluff | 3 or later | Only if you commit `.sql` files with Lefthook | Same | Same | Lefthook runs `sqlfluff` on staged `.sql` files. |
| GitHub CLI (`gh`) | A current release | Optional | Optional | Optional | Only for the optional fix loop: setup uses it to create labels and to check that secrets exist. |

**Note 1: what counts as app-only.** The setup verifier (`scripts/verify-scanning.ps1`)
always checks Trivy, the hook manager, Python and Git. It skips Terraform, TFLint,
Checkov and `SCAN_TFLINT_CONFIG` only when all three are true: `scan-config.yaml` sets
`languages.terraform.enabled: false`, it enables another language (choose one with
`--languages` at setup), and no `.tf` or `.tf.json` file exists in the working tree,
the index or a local branch tip. Otherwise it requires them. The commit and push hooks
need those tools when `.tf` or `.tf.json` files change.

**Note 2: Terraform-only repositories that use Lefthook need Prettier.** The Lefthook
manifest is the same for every tier and every language choice. Its `prettier` command
runs whenever you stage a `.json` or `.md` file, and setup itself adds JSON files
(`.claude/settings.json`). Without `SCAN_PRETTIER_BIN` and `SCAN_PRETTIER_CONFIG`, that
commit is blocked. The pre-commit runner does not run Prettier.

A missing tool **blocks** the hook that needs it. The hooks do not skip quietly: they
print `<tool> not found; scan incomplete` and exit 1. `SCAN_ALLOW_TOOL_ERRORS=1` turns
that into a warning for local experiments; never set it permanently.

## By operating system

### Windows

- Install Git for Windows (it includes Git Bash), Python 3.11 or later and PowerShell 7
  from your managed package source. Open a new PowerShell 7 terminal afterwards.
- Make sure `bash` resolves to Git Bash, not `C:\Windows\System32\bash.exe` (WSL).
- `scripts/install-scanner.py` supports Windows on x64 (AMD64) only. There are no
  `windows-arm64` entries in `scripts/scanner-downloads.json`.
- Windows builds each process's `PATH` from the system entries first, then the user
  entries. If a system-wide Python is installed, it can be found before your virtual
  environment. Check with `Get-Command python` in a new terminal: the interpreter
  found first must have PyYAML and jsonschema.

### macOS

```bash
brew install bash powershell python git lefthook terraform node
export PATH="$(brew --prefix bash)/bin:$PATH"
bash --version
```

`/bin/bash` on macOS is version 3.2, which the hooks reject.

### Linux

Install Bash, Git, Python with `venv` support, PowerShell 7, Terraform, Node.js and
your hook manager from your distribution's supported packages. Use `python3` where
these pages say `python` if that is your Python 3.11 command.

## Environment variables the hooks read

The hooks read trusted paths from environment variables. Each must be an absolute path
outside the repository.

| Variable | Needed when | Value set in Getting started |
|---|---|---|
| `PATH` | Always | Scanner virtual environment first, then `~/.local-scanning-tools/bin` (and the pre-commit environment if you use pre-commit). |
| `SCAN_TFLINT_CONFIG` | Terraform push hook, and the setup verifier for every repository | `~/.config/auto-code-scanning/<provider>/tflint.hcl` |
| `SCAN_TFLINT_PLUGIN_DIR` | Same as above | `~/.config/auto-code-scanning/<provider>/plugins` |
| `SCAN_PRETTIER_BIN`, `SCAN_PRETTIER_CONFIG` | Lefthook, whenever formatted files are staged | `~/.config/auto-code-scanning/formatters/...` |
| `SCAN_ESLINT_BIN`, `SCAN_ESLINT_CONFIG` | Lefthook with TypeScript or JavaScript | Your external ESLint install and config |

Variables set with `export` or `$env:` last only for the current terminal. A commit
from a new terminal, an IDE or a GUI Git client then fails. Make them permanent with
the commands in [Getting started: keep the settings for new terminals](SETUP-GUIDE.md#keep-the-settings-for-new-terminals-ides-and-git-clients).

## Cost and run time

- **CI minutes.** The scans run on GitHub-hosted runners in your repository, so they
  use your Actions minutes. How many depends on repository size, how many directories
  hold Terraform, which languages and optional jobs (such as Snyk) you enable, and how
  often you push. Measure your own first runs; this project publishes no estimate.
- **Local hook time.** `scan-config.yaml` declares time targets under
  `global.performance` (`pre_commit_max_seconds`, `pre_push_max_seconds`,
  `per_hook_max_seconds`), and [the hook reference](HOOK-REFERENCE.md#performance-targets)
  lists them per stage. The hooks do not enforce them: a slow hook is not stopped. This
  repository's own CI checks its hooks against the per-hook target on its test fixtures.
- **First runs download data.** Trivy downloads its checks bundle and TFLint downloads
  its rulesets on first use, so the first commit or push is slower than later ones.
- **The optional fix loop spends model tokens** on your Anthropic account (the
  `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` you supply). Each run is capped by
  `fix_loop.max_turns` and each pull request by `fix_loop.max_iterations`. See
  [the fix loop](FIX-LOOP.md).

Next: [Getting started](SETUP-GUIDE.md) or the shorter [Quickstart](QUICK-START-5MIN.md).
