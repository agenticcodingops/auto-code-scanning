# Runbook: Migrate an Inline Scan or Fix Loop to the Platform

## Trusted base inline skip migration

Re-vendor `scripts/scan.py` and `scripts/scan_policy.py` together and upgrade the
reusable scan to a release containing the trusted-base inline skip fix. Existing
Terraform `#checkov:skip=<ID>:<reason>` comments are honoured when the same ID and
justification remain on the same resource in the same file as at the trusted
base commit. They do not need schema-2.0 registry entries. Line shifts or unrelated
resource edits do not invalidate these reviewed skips.

Files containing syntax the inline matcher cannot fully model fail closed: if
either the trusted base or current version contains a heredoc inside a quoted
template's interpolation, no inline skip from that file is honoured. Heredocs
containing template openers (`${` or `%{`, even escaped openers) are also rejected
conservatively, covering heredocs nested inside another heredoc's interpolation.
All skipped checks in these files remain unapproved findings and need schema-2.0
registry approvals in base policy, even when their comments are unchanged.
Unchanged skips in ordinary files continue to be honoured.

A PR adding or changing a skip, its reason, check ID, resource or file still
reports a finding and needs a schema-2.0 occurrence approval in base policy.
Deleting a skip restores the active check; an old base skip cannot hide a failure.
Keep `allow-inline-checkov-skips` at its default `false` to enforce this boundary.

For identical local and CI decisions, pass `python scripts/scan.py <directory>
--policy-root <separate-base-checkout>` using the exact PR base commit. With no
explicit policy checkout, the local inline matcher reads the current
`origin/HEAD` (or `origin/main`) commit from Git objects. Fetch that remote branch
first; an older fork point cannot restore a skip removed on the current base.
If no base is available, skips remain active. See
[suppression governance](SUPPRESSION-GOVERNANCE.md#scan-policy-and-occurrence-approval-migration)
for the complete rule and the separate registry migration.

## Push-object and staged-config validation migration

Re-vendor `hooks/`, `scripts/validate-scan-config.py` and `schemas/` together.
Pre-push scanners now scan a private copy of **each local object named by Git's
stdin transaction**, including new branches, annotated tags, alternate destinations
and non-HEAD/multiple refs. Each ref selects files changed between its remote
object and pushed object; deleted refs and deleted files scan nothing. New branches
compare against the merge base with the destination remote's tracked default branch
(`refs/remotes/<remote>/HEAD`). Without a usable default/merge base, paths come from
commits absent from every remote-tracking ref (`--not --remotes`); an empty remote
therefore scans all new files. Keep remote-tracking refs current before pushing.
Uncommitted files, checkout filters and archive attributes cannot replace the
scanned bytes. Terraform scans exclude unchanged source files even in selected
directories, so pre-existing findings elsewhere do not block a clean change.
Required tracked policy files still come from the pushed tip, even when unchanged.
Both `.tf` and `.tf.json` changes trigger IaC scanners. TFLint retains the complete
pushed tree as analysis context and filters reported findings to changed files,
so unchanged variable consumers are available without gating unrelated findings.
A changed `.cs`/`.csproj` file triggers a build of the complete pushed solution.
The temporary copy is deleted after scanning; source files and the index are
untouched. Reports are exported to the consumer's `.scanning/last-scan.json` before
cleanup, and earlier reports are cleared when the next attempt produces no report.
Checkov, Trivy IaC and Snyk IaC use file-only snapshots: unchanged, unrelated
symlinks and submodules are excluded and do not block those scanners. Changed
links and submodules still block. TFLint and dotnet build require the complete
pushed tree for context; any link or submodule anywhere in that tree blocks them.
Unavailable/non-tree objects, selected symlinks, submodules and filesystem path collisions
block the push because a complete isolated scan cannot be guaranteed.
Transaction-bound validation is fail-closed: setup errors, malformed transactions
or configuration, unsafe tree entries and missing required policies return `1`.
Configuration shape errors name the invalid key on one line; they never fall
back to defaults. This includes errors in the adapter's runner configuration.

**Track scanner policy before upgrading.** Push scans require the policy scanner's
`.checkov.yaml` in the pushed tree under
`.scanning/configs`, or under a tracked repository-relative `SCAN_CONFIG_DIR`.
The setup guide ignores `.scanning/`, so either force-add the required policy files
or commit them under another directory and configure `SCAN_CONFIG_DIR` accordingly.
An absolute override must resolve inside the consumer repository. Missing required
policies or an external policy directory blocks the push; the runner never silently
falls back to different rules. Config files and source bytes come from the same tip.
The linter instead requires an external trusted `SCAN_TFLINT_CONFIG` and
`SCAN_TFLINT_PLUGIN_DIR`, as described in the
[trusted-input migration](#trusted-execution-and-output-migration).
Individual legacy wrappers remain available only through the opt-in below.

- **Lefthook:** replace the `pre-push` block with the current
  `templates/lefthook/lefthook.yml` block. It has one command with `use_stdin: true`
  and no file glob, which fans out the complete transaction to all selected tools.
  Its `--remote '{1}'` passes Git's destination remote to new-branch selection,
  including destination paths containing spaces.
  Adjust its `--hooks` list to the push scanners you enable.
- **pre-commit:** after installing its push hook, run
  `python hooks/pre-push.py --install-pre-commit` from the consumer root. The
  current setup-scan-fix scripts do this automatically. The adapter preserves the
  original hook, runs every configured platform push scanner against all refs,
  then forwards the complete input to the original runner for other hooks. Python
  and PyYAML are required. Reinstall the adapter if you replace the push hook.
  Older setup-scanning installers need this manual step after vendoring `hooks/`.
  The runner's ref environment variables alone do not preserve a multi-ref push.
  The adapter recognizes platform repository entries and local entries that
  explicitly call the vendored dispatcher. It removes only those handled entries
  from a temporary config for the saved runner; unrelated IDs/aliases and user
  skip settings stay intact. Explicit per-hook stage overrides (including legacy
  `push`) take precedence; otherwise platform manifest
  stages apply before configuration-wide defaults. Windows runners prefer PowerShell
  7, then Windows PowerShell, then Git Bash, as the dispatcher does.

For manual validation, feed a real four-field transaction to a push wrapper or
`python hooks/pre-push.py --remote origin --hooks checkov,tflint,dotnet-build` on stdin.
Direct Bash/PowerShell wrappers also accept `--remote origin`. Without a remote
option, directly installed Git hooks consume Git's positional remote name and URL.
For manual invocations without either form of remote argument,
the runner uses a single tracked remote default, or the all-remotes
fallback when that default is absent or ambiguous. A direct
`pre-commit run --hook-stage pre-push --all-files` has no transaction and blocks.
During a reviewed migration only, `SCAN_LEGACY_PUSH_STATE=1` explicitly restores
the old index/tracking-ref/worktree behavior for individual push wrappers. It is
off by default and provides no assurance about the pushed objects. The adapter
and batch runner always use snapshots.

The local hook off-switch cannot suppress push-object scans through an unstaged
config edit: push scans read an explicit `local_hooks_enabled: false` from the
pushed tree itself. Config validation rejects staged symlinks/type changes to
unsupported objects and always checks the exact
root `scan-config.yaml` blob in the consumer's index, even when hook code is in
a separate package or the worktree file differs. Python, PyYAML, the vendored
schema and jsonschema are required; missing validation infrastructure blocks by
default. A configured build path must remain inside the snapshot, and a missing
build solution blocks. `SCAN_ALLOW_TOOL_ERRORS=1` explicitly retains the former local validation
fail-open behavior for missing prerequisites. Invalid staged YAML still blocks.
CI remains the authoritative backstop.

## Scan policy and occurrence approval migration

Pull-request scans use policy from the exact base commit. Language selection,
scanner configuration and ignore files, the configured suppression registry, and
`.scan-baseline/baseline.json` become effective after their policy change reaches
the protected base. Push scans use the pushed commit. Scanner helpers default to
the published platform repository. Set `scanning-repository` explicitly only for
a reviewed mirror, and align `scanning-repo-ref` with the workflow revision. Pin reusable workflows and
`scanning-repo-ref` to the same reviewed release or commit, and protect caller
workflows and their inputs through repository review rules.

**Adopter action required:** migrate suppression registries and baselines to
schema `2.0`. Each entry requires a `fingerprint` copied from a current scan report.
The `v1:` fingerprint binds the scanner, rule, repository-relative path, resource,
line range and SHA-256 of the source file (CRLF normalized to LF). A source edit
invalidates approval. Each entry applies to one occurrence; additional copies
remain active. A missing source file or location cannot match an exact exception.
`file_pattern`, when supplied, further restricts the match.

Generate current fingerprints with
`python scripts/scan.py --skip-baseline --skip-suppressions --format json`, review
the occurrences and their justification, and copy the approved fingerprints into
the registry. Regenerate baselines with `scripts/create-baseline.ps1 -Force`;
baseline creation now uses the same identity as local scans and CI. Invocations
from a subdirectory scan relative to that directory, while the default output
goes to the repository's `.scan-baseline` so the policy loader can find it.
Explicit output paths retain their invocation-relative meaning. The baseline
keeps a separate entry for each occurrence. Existing broad keys cannot be
automatically converted into an occurrence approval.

During a reviewed migration only, the reusable IaC workflow's
`allow-legacy-exceptions: true`, the local scanner's `--allow-legacy-exceptions`,
or the hook environment `SCAN_ALLOW_LEGACY_EXCEPTIONS=1` explicitly enables schema
`1.0` matching. These are off by default. Approval, date and expiry validation
still apply. HIGH and CRITICAL always require `approved_by`; registry settings
can add approval levels but cannot remove that floor. Severity is required and
approval must cover the actual finding severity. Expiry is capped at 180 days.

Source inline skips require the trusted-base comparison described above:
unchanged base-approved skips are honoured in supported files; all others
remain in the gate and report. App-code scans disable inline suppression comments. To
retain source inline policy for the policy scanner during migration, trusted
IaC callers can explicitly set `allow-inline-checkov-skips: true` (default
`false`). Explicit caller skip lists and the platform's reviewed cloud
configuration remain supported. IaC findings without severity are treated as
HIGH so missing metadata cannot weaken the gate.

Enabled scanner job failures, missing or invalid reports, parser errors and
report-write failures block completion independently of findings.
`fail-on-findings: false` only relaxes the findings threshold; it never permits
incomplete scans. Local compatibility settings do not relax the CI aggregate.

Hooks validate `suppressions.file` from `scan-config.yaml`, defaulting to the
repository-root `.scan-suppressions.yaml`, exactly as CI does. Downloaded setup
copies are templates rather than an active registry. Re-vendor both `hooks/` and
`scripts/` together; the hook and standalone validators share one implementation.
Python and PyYAML are required for registry validation.


Some repositories copied the scan or fix-loop logic into their own workflow and hook
files. This runbook replaces those copies with pinned calls to this platform, and moves
the project-specific values into one file, `scan-config.yaml`.

The current release is `v3.0.0`. <!-- x-release-please-version -->

Line references such as `setup-scan-fix.py:85` mean that line of `scripts/setup-scan-fix.py`
at commit
[`7cd34a5`](https://github.com/agenticcodingops/auto-code-scanning/tree/7cd34a52c823a725575ef3b59ab34e062d1d83dd)
on `main`. Workflow files are under `.github/workflows/`.

## Purpose

After the migration the repository keeps `scan-config.yaml` and a few thin caller
workflows. The hardened logic (the two-job fix loop, the path gate, the secret re-scan,
the iteration cap) comes from the platform at a pinned release, so a fix to it reaches
the repository through one pin change.

## When to use

- The repository has its own copy of a fix-loop workflow, a scan workflow, or hooks with
  hard-coded paths, solution names or build commands.
- For a repository with no scan yet, use
  [consumer-repo-setup-guide.md](consumer-repo-setup-guide.md) or, for a Terraform
  module, [TERRAFORM-MODULE-ADOPTION.md](TERRAFORM-MODULE-ADOPTION.md).

## Prerequisites

- A clone of this platform, checked out at the release you will pin
  (`git checkout vX.Y.Z`). `setup-scan-fix.py` copies files from the clone it runs from
  (`setup-scan-fix.py:22`, `74-77`, `119-123`).
- Python 3 with PyYAML and `jsonschema`, and `gh` authenticated against the repository. `gh` creates the
  labels and checks the secrets (`setup-scan-fix.py:126-155`).
- Lefthook or pre-commit, for the local hooks.
- A clean working tree in the repository, so you can review every file the setup
  overwrites.
- A second maintainer to review the pull request.

Roles: the **Operator** is the maintainer doing the migration. The **Reviewer** approves
the pull request. **CI** is GitHub Actions.

## What moves where

| Inline today | After the migration | Source |
|---|---|---|
| A full fix-loop workflow in the repository | A thin caller that `uses:` `autonomous-fix.yml` at a pinned release | `templates/fix-loop/autonomous-fix.yml` |
| Fix-loop allowlist written into the workflow | `fix_loop.allowlist_paths` | `autonomous-fix.yml:30-33`, `403-421` |
| Sensitive-path denylist written into the workflow | `fix_loop.gated_paths` (case-insensitive substrings) | `scripts/check-fix-allowlist.py:4-7` |
| Solution path, working directory and build command in hooks or the workflow | `languages.<lang>.build.solution`, `languages.<lang>.build.working_dir` and `fix_loop.build_verify_cmd` | `templates/scan-config/standard.yaml:40`, `50`, `90` |
| A bespoke SARIF-uploading scan workflow | A caller of `code-security-scan.yml` and, for Terraform, of `reusable-scan.yml` | `templates/workflows/` |
| `lefthook.yml` calling each tool directly | `lefthook.yml` calling `hooks/dispatcher.sh` | `templates/lefthook/lefthook.yml:6-7` |
| An action pin maintained by hand in the fix loop | The pin inside the platform's `autonomous-fix.yml`, mirrored in `fix_loop.claude_code_action_ref` | `autonomous-fix.yml:35-37`, `333`; [VERSION-PINNING.md](VERSION-PINNING.md#the-centralized-claude-code-action-pin-layer-b) |

## Steps

### 1. List what the repository has copied

- **Who:** Operator
- **Operator STOP:** no

Find the inline workflows, hooks and their hard-coded values:

```bash
ls .github/workflows/
grep -rln "upload-sarif\|claude-code-action\|allowlist\|semgrep\|trivy" .github/workflows hooks scripts lefthook.yml 2>/dev/null
```

Write down, for each file: the paths the fix loop may edit, the paths it must never edit,
the build command, the solution file and its directory, the SARIF categories, and who is
allowed to trigger the fix loop. You will need each value in step 3.

### 2. Run the setup from the release you will pin

- **Who:** Operator
- **Operator STOP:** no

From the repository root, on a new branch:

```bash
python /path/to/auto-code-scanning/scripts/setup-scan-fix.py \
  --languages csharp,typescript --tier standard --hooks-runner lefthook --enable-fix-loop
```

Use your own languages and tier. Add `--cloud-provider aws|azure|gcp` for Terraform. The
flag only adds `terraform` to the languages (`setup-scan-fix.py:46`, `53-54`). It does not
set the provider: the copied `terraform-scan.yml` always says `cloud-provider: "aws"`
(`templates/workflows/terraform-scan.yml:24`), which loads the AWS TFLint ruleset. Step 4
tells you to change it. The setup:

- writes `scan-config.yaml` from the tier template, but leaves an existing one unless you
  pass `--force` (`setup-scan-fix.py:59-68`; `render-scan-config.py:51-52`);
- copies `hooks/` and five shared scripts over any files with the same names
  (`setup-scan-fix.py:71-78`);
- overwrites `lefthook.yml` with the template, or writes `.pre-commit-config.yaml` only if
  it does not exist (`setup-scan-fix.py:82-100`);
- keeps an existing `.claude/settings.json`, and overwrites the four scan hooks in
  `.claude/hooks/` (`setup-scan-fix.py:103-114`);
- overwrites `code-security-scan.yml`, `terraform-scan.yml` (Terraform only) and
  `autonomous-fix.yml` (fix loop only) in `.github/workflows/` with the caller templates
  (`setup-scan-fix.py:117-124`).

Review `git status` and `git diff` before you go on.

### 3. Put the project values into `scan-config.yaml`

- **Who:** Operator
- **Operator STOP:** no

Set the values from step 1. An excerpt with example paths:

```yaml
languages:
  csharp:
    enabled: true
    build: { solution: "app/Example.slnx", working_dir: "app" }
  typescript:
    enabled: true
    build: { working_dir: "web" }
ci:
  sarif: { category_prefix: "scan-" }
fix_loop:
  enabled: true
  allowlist_paths: ["app/src/", "app/tests/", "web/"]
  gated_paths: ["auth", "payment", "crypto", "security", "identity", "secret", "credential",
                ".github/", ".claude/", "hooks", "lefthook.yml", "scan-and-fix.ps1", "scripts/", ".env", "LICENSE"]
  build_verify_cmd: "cd app && dotnet build Example.slnx --nologo"
```

Keep `fix_loop.claude_code_action_ref` as the template wrote it. The schema accepts only
`anthropics/claude-code-action@` followed by a 40-character lowercase commit SHA
(`schemas/scan-config.schema.json:157-161`). A bare SHA or a tag is rejected. Then
validate with the copy setup installed in the consumer:

```bash
STRICT=1 python scripts/validate-scan-config.py scan-config.yaml
```

Setup copies `schemas/` alongside the validator, so it finds the schema in your repository.
If the schema is later removed, without `STRICT=1` the validator prints a warning and exits
0 instead of validating (`validate-scan-config.py:29`, `40-48`).

The fix loop reads this file from the pull request's base commit, or from the default
branch on a manual dispatch. It never reads it from the pull request head
(`autonomous-fix.yml:120-179`). Your changes take effect for the fix loop only after they
merge.

### 4. Pin the callers and grant their permissions

- **Who:** Operator
- **Operator STOP:** no

The caller templates pin the release they ship in, and release-please moves those pins at
each release (`templates/workflows/code-security-scan.yml:21`,
`templates/workflows/terraform-scan.yml:21` and `26`,
`templates/fix-loop/autonomous-fix.yml:70` and `74`). Releases up to and including v2.3.1
pinned `v2.0.0` there. Check that every pin is the release you checked out in the
prerequisites, and pin the commit its tag points to, as in
[VERSION-PINNING.md](VERSION-PINNING.md#pin-the-commit-a-release-tag-points-to). For the
fix-loop caller:

```yaml
jobs:
  fix:
    # Keep the template's `if:` here (see step 5).
    permissions:
      contents: read
      pull-requests: write
      issues: write
      actions: read
    uses: OWNER/auto-code-scanning/.github/workflows/autonomous-fix.yml@<commit-sha> # v3.0.0 x-release-please-version
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      config_path: scan-config.yaml
      scanning_repo: OWNER/auto-code-scanning
      scanning_repo_ref: <commit-sha> # v3.0.0 x-release-please-version
    secrets:
      AUTOFIX_TOKEN: ${{ secrets.AUTOFIX_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
```

Find `<commit-sha>` as in
[BUMP-THE-SCAN.md](BUMP-THE-SCAN.md#2-find-the-commit-of-the-target-release). Pass only
the secrets the workflow declares (`autonomous-fix.yml:64-73`); never `secrets: inherit`,
which hands the called workflow every secret of your repository and organisation.

`OWNER` is the owner of the platform copy you call. The current template grants the
four permissions above on its `fix` job (`templates/fix-loop/autonomous-fix.yml:37-41`).
Callers copied from v2.3.6 or earlier grant only `contents: read` by default; add all
four grants under `jobs.fix.permissions` when migrating those callers. These grants
are the called workflow's permission ceiling; see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#autonomous-fixyml). For the scan callers,
move `uses:` and `scanning-repo-ref` together as in [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md).
In `terraform-scan.yml`, also set `cloud-provider` to your provider (`aws`, `azure` or
`gcp`).

With `--hooks-runner pre-commit`, the setup writes `.pre-commit-config.yaml` from
`templates/<tier>/pre-commit-config.yaml` when the file does not exist yet
(`setup-scan-fix.py:92-95`). Those templates pin the `auto-code-scanning` hooks at the
release they ship in (for example `templates/standard/pre-commit-config.yaml:30`).
Releases up to and including v2.3.1 pinned `rev: v1.0.0`, which is no tag or branch, so
pre-commit could not fetch the hooks and every commit through it failed, this migration's
included. In the same commit as the workflow pins, check that `rev:` is the release you
checked out, or set it to that release's commit SHA. If you call your owner's copy, point
that entry's `repo:` at it too. If an existing `.pre-commit-config.yaml` already lists
`auto-code-scanning`, move its `rev:` the same way.

### 5. Check who can start the fix loop

- **Who:** Operator and Reviewer
- **Operator STOP:** yes. Do not merge until both agree the caller's `if:` admits only
  the people and bots you trust.

The caller's `if:` is the privilege boundary: it decides whose review or comment can make
the loop push with `AUTOFIX_TOKEN` (`templates/fix-loop/autonomous-fix.yml:53-68`). The
template admits a manual dispatch, or a non-fork pull request with the `ai-autofix`
label whose review or comment came from a listed bot or from an `OWNER`, `MEMBER` or
`COLLABORATOR`. Compare it with the rule your inline workflow enforced, and edit the bot
list to match yours. List GitHub Apps by their `<app>[bot]` login, which belongs to one
App. Never list `github-actions[bot]`: every workflow's `GITHUB_TOKEN` acts as it, so it
names no particular workflow, and the reusable workflow refuses it
(`autonomous-fix.yml:101-118`). Read [SECURITY-MODEL.md](SECURITY-MODEL.md) before you widen it.

### 6. Remove the inline copies

- **Who:** Operator
- **Operator STOP:** no

- Delete any inline fix-loop or scan workflow that the callers replace. Keep each caller
  in its own workflow file: two calls from one caller workflow share a concurrency group
  (see [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#concurrency)).
- Delete hard-coded paths and build commands from your own hooks and scripts; they are in
  `scan-config.yaml` now.
- Delete any local copy of the allowlist gate. The platform runs
  `scripts/check-fix-allowlist.py` from its own checkout (`autonomous-fix.yml:414`, `599`).

### 7. Create the secrets

- **Who:** Operator (needs permission to manage repository secrets)
- **Operator STOP:** yes. A person creates the secrets; no script does.

The setup creates the `ai-autofix` and `needs-human-review` labels, and only checks that
`AUTOFIX_TOKEN` and `ANTHROPIC_API_KEY` exist (`setup-scan-fix.py:126-155`). Create any
that are missing:

```bash
gh secret set AUTOFIX_TOKEN       # fine-grained token: Contents and Pull requests read/write, this repository only
gh secret set ANTHROPIC_API_KEY   # or CLAUDE_CODE_OAUTH_TOKEN
```

`AUTOFIX_TOKEN` is used only by the final push step (`autonomous-fix.yml:675-692`).

### 8. Swap the required status checks

- **Who:** Operator (repository admin)
- **Operator STOP:** no

Swap the requirements together, before you merge, once the scan callers' jobs have run on
this pull request. In one change, remove every job of an inline workflow you delete (or the
pull request waits for a check that never runs) and require the scan callers' jobs, as in
[TERRAFORM-MODULE-ADOPTION.md](TERRAFORM-MODULE-ADOPTION.md#7-require-the-scan-before-merging).
Requiring the new jobs only after the merge would leave this and any concurrent pull request
mergeable with no scan gate. The jobs to require:

- for the Terraform scan: Setup Scanning Tools, Trivy IaC Scan, Checkov Policy Scan,
  TFLint Scan and Aggregate Results, plus Snyk IaC Scan (Optional) if enabled;
- for the code scan: `Detect languages`, `Semgrep (csharp)` for enabled C#,
  `Semgrep (typescript)` for enabled TypeScript/JavaScript, and `Secret scan`.
  Keep `run-secret-scan: true` and `fail-on-findings: true`. Add every newly enabled
  language's matrix context to branch protection. One passing language check does
  not cover the other language or secrets. Enable callers on every pull request
  without path filters. See [the setup guide](consumer-repo-setup-guide.md#branch-protection).

Use the names on the pull request's Checks tab. Never require the fix loop's jobs: they
run only on a trusted review or a dispatch.

### 9. Review and merge

- **Who:** Operator, CI, then Reviewer
- **Operator STOP:** no

Open a pull request. CI runs the scan callers. The Reviewer checks the diff from step 2,
the pins from step 4 and the boundary from step 5, then approves. The Operator merges.

## Verify

- `STRICT=1 python /path/to/auto-code-scanning/scripts/validate-scan-config.py scan-config.yaml`
  prints `VALID`.
- A local commit runs the hooks through `hooks/dispatcher.sh`.
- For Terraform, the TFLint Scan job summary lists your cloud's ruleset (`azurerm`, `aws`
  or `google`), not another cloud's (`reusable-scan.yml:371-383`).
- Code scanning shows distinct categories: `<prefix>semgrep-csharp`,
  `<prefix>semgrep-typescript` and `<prefix>trivy-secrets` (`code-security-scan.yml:186`,
  `242`).
- On a test pull request labelled `ai-autofix`, a trusted review starts the fix loop. Its
  Analyze job runs with a read-only token (`autonomous-fix.yml:198-201`, `337`), and only
  the push step uses `AUTOFIX_TOKEN` (`autonomous-fix.yml:675-692`).
- A proposed fix that touches `.github/`, or a path containing a gated word such as
  `auth`, is not pushed. The pull request gets `needs-human-review` and a comment that
  names the reason (`autonomous-fix.yml:403-421`, `697-760`).

## Rollback

- **Who:** Operator (a repository admin), with Reviewer approval

1. Remove the new callers' jobs from the required status checks first. Otherwise the
   revert pull request waits for checks that never run.
2. Decide whether the restored inline fix loop may run. The revert also restores it, and
   if it reads the same `ai-autofix` label and secrets (`AUTOFIX_TOKEN` and the agent key,
   which step 7 had you create or check), it can push again as soon as the revert merges.
   If it may not, do one of these before the merge:
   - delete the token (`gh secret delete AUTOFIX_TOKEN`), then revoke the token itself;
   - leave the inline fix-loop file out of the revert.

   `gh workflow disable` finds only active workflows, so use it on the restored file
   after the merge, not before.
3. In a new pull request, revert the migration: `git revert <squash-commit>`, or
   `git revert -m 1 <merge-commit>` for a merge commit. The inline workflows and hooks
   come back from history. Get Reviewer approval and merge.
4. If the restored inline workflows had required status checks, add them back. The labels
   can stay.

## Trusted execution and output migration

Re-vendor hooks and scripts together. Output paths now reject symbolic links and
Windows reparse points, including links in parent directories. Replace linked
report/configuration destinations with real directories before running setup or
scans. This also applies to explicit output paths and workflow output files. PowerShell
resolves destinations from the session location, including after `Set-Location`.

ESLint and Prettier default to externally provisioned tooling. Set
`SCAN_ESLINT_BIN` / `SCAN_ESLINT_CONFIG` and
`SCAN_PRETTIER_BIN` / `SCAN_PRETTIER_CONFIG` to absolute, trusted files outside the
scanned checkout. Use ESLint 9 or newer: its config lookup is disabled and the
explicit external config determines parsers and plugins. Prettier also receives
only the explicit external config and runs from its directory with absolute input
paths. Plugin-name resolution and the default ignore file are therefore relative
to that trusted directory. Install the tools and their plugins outside
the scanned repository; review the configuration as executable code. Missing
trusted inputs block the hook. Extra hook arguments are rejected in this mode.
For developer-owned repositories only, `SCAN_TRUST_REPO_CODE=1` explicitly restores
repository-local binaries, package resolution and executable configuration. Do not
set this option when reviewing an untrusted checkout.

TFLint requires `SCAN_TFLINT_CONFIG` to name an absolute, reviewed configuration
outside the checkout (with a `.hcl` extension), and `SCAN_TFLINT_PLUGIN_DIR` to
name an external plugin cache. Remove all `plugin_dir` settings from the config
so they cannot override that cache. Review plugin sources and exact versions.
Both initialization and scanning use that exact config; a missing config or failed
initialization blocks the hook, and extra hook arguments cannot override it.
The pre-commit templates use the platform's TFLint hook instead of a separate
wrapper. Copy the selected cloud config to the trusted location as an operator
provisioning step. Keep that location and its cache outside contributor control.

Setup requires Python 3.11 or newer and Git from your managed package source.
Windows Bash hook path checks also require Python; native POSIX link checks
remain available without a JSON parser. Setup validates its destination paths
and trees, so unrelated source/dependency symlinks can remain in the checkout.
It no longer bootstraps a package manager from downloaded script text.
Scanner binaries are selected from `scripts/scanner-downloads.json`, verified
against its committed SHA-256 values before archive parsing, and installed under
`~/.local-scanning-tools/bin`. Add that directory to PATH for later sessions.
Direct Python and optional package installs use exact versions. YAML validation
uses the default safe loader; custom YAML tags may now need a dedicated validator.

Executable template references and the default helper checkout use release-managed
tags. Adopters should replace each tag with the full commit SHA that the release
tag points to, and set `scanning-repo-ref` / `scanning_repo_ref` to that same SHA.
See [VERSION-PINNING.md](VERSION-PINNING.md#pin-the-commit-a-release-tag-points-to).
Review and bump those release commit pins and re-vendor together when upgrading.
Scheduled dependency refreshes remain tracked in issue #38. The review workflow
uses its own review instructions without dynamically
installing a plugin marketplace. Report comments allow links only to expected HTTPS
documentation hosts and omit complete rows if the encoded table reaches its size
budget. Configuration readers exclude checkout imports while retaining trusted
user-level packages installed by no-admin setup.

## References

- [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md): inputs, secrets and permissions.
- [FIX-LOOP.md](FIX-LOOP.md) and [SECURITY-MODEL.md](SECURITY-MODEL.md): how the fix loop
  works and what it trusts.
- [VERSION-PINNING.md](VERSION-PINNING.md): pinning rules.
- [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md): later upgrades.
- [consumer-repo-setup-guide.md](consumer-repo-setup-guide.md): first-time setup.
