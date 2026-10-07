# Version Pinning Guide

How to manage versions of auto-code-scanning in your repository.

The current release is **`v2.3.2`**. <!-- x-release-please-version -->

> **On a release before `v2.1.0`?** Your Terraform scan (`reusable-scan.yml`) did not run Checkov, and TFLint
> linted at most one directory. Read
> [Upgrading from a Release Before 2.1.0](#upgrading-from-a-release-before-210) before you
> bump.

Releases after `v2.1.0` are cut by release-please (see "Release Process" in
[CONTRIBUTING.md](CONTRIBUTING.md)). Each one has a GitHub Release with its notes, a
`CHANGELOG.md` entry, and a **Release Verification** run on its tag whose logs and job
summaries record the exact scanner and ruleset versions it installs. `version.txt` at the
root of each release holds its version.

## Pin to a Release Tag — Never `@main`

> **MANDATORY.** Consumers **MUST** pin every reference to this repo to a release
> tag (e.g. `@v2.3.2`) or a full 40-character commit SHA. **Never** reference <!-- x-release-please-version -->
> `@main`. This applies to **both**:
>
> - pre-commit `rev:` in `.pre-commit-config.yaml`, and
> - the reusable workflow `uses:` references in `.github/workflows/`
>   (`code-security-scan.yml`, `autonomous-fix.yml`, `reusable-scan.yml`).
>
> `@main` is a moving target: it can change hook behavior, exit-code semantics, or
> the fix-loop privilege boundary under you without warning. A pinned tag/SHA is
> the only reproducible, reviewable reference.

## Pin the Commit a Release Tag Points To

Pin the commit a release tag points to, and name the version in a comment. Pass the same
commit as `scanning-repo-ref`, so the configs match the workflow:

```yaml
jobs:
  iac:
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@<commit-sha> # vX.Y.Z
    with:
      cloud-provider: aws
      scanning-repo-ref: <commit-sha>
```

`OWNER` is the owner of your repository. `reusable-scan.yml` reads its configs from a
repository named `auto-code-scanning` under the owner of the calling repository, whatever
`uses:` names (`reusable-scan.yml:123-131`). That copy must be public (a private copy
cannot be read) and must hold the ref you pass as `scanning-repo-ref`. Without it, Setup
Scanning Tools fails, the scan jobs are skipped, Aggregate Results still passes, and the
pull request comment says "All security checks passed!". Create the copy as in
[step 2 of TERRAFORM-MODULE-ADOPTION.md](TERRAFORM-MODULE-ADOPTION.md#2-create-your-owners-copy-of-the-platform).
Require Setup Scanning Tools as well as Aggregate Results
([step 7](TERRAFORM-MODULE-ADOPTION.md#7-require-the-scan-before-merging)). See
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#configs-come-from-your-owners-copy).

Find the commit with `^{commit}`, which peels a tag to the commit it points to:

```bash
# In a clone of this repository
git fetch --tags origin
git rev-parse 'vX.Y.Z^{commit}'

# Without a clone: an annotated tag lists two lines; use the one ending in ^{}
git ls-remote https://github.com/agenticcodingops/auto-code-scanning 'refs/tags/vX.Y.Z*'
```

This works for both kinds of tag here. The tags up to `v2.1.0` were made by hand and are
**annotated**: for them, `git rev-parse vX.Y.Z` without `^{commit}` returns the SHA of the
tag object, which is not a commit and not a valid pin. The tags release-please creates
are **lightweight**, and point straight at the commit.

## How Version Pinning Works

Consuming repos pin to a specific version via the `rev:` field in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v2.3.2    # Pinned to exact version — never @main  x-release-please-version
    hooks:
      - id: trivy-iac-critical
      - id: trivy-secrets
      - id: gitleaks
      # v2.0.0 app-code hooks (enable the matching languages.* in scan-config.yaml):
      - id: semgrep-csharp
      - id: semgrep-typescript
      - id: eslint
      - id: prettier
      - id: sqlfluff
      - id: validate-scan-config
```

The `rev:` field accepts:
- **Git tags** (recommended): `v2.0.0`, `v2.1.0`
- **Commit SHAs** (also acceptable): full 40-char SHA for exact reproducibility
- **Branch names** (`main`): **not allowed** — see the rule above

## SemVer Policy

This repository follows Semantic Versioning (SemVer):

| Change Type | Version Bump | Examples |
|-------------|-------------|---------|
| **Breaking** | Major (X.0.0) | Hook ID renamed, exit code semantics changed, removed hook |
| **Feature** | Minor (0.X.0) | New hook added, new script option, new config field |
| **Fix** | Patch (0.0.X) | Bug fix, config correction, documentation update |

> **Note on v2.0.0.** The 2.0.0 release adds the app-code hooks
> (`semgrep-csharp`, `semgrep-typescript`, `dotnet-format`, `dotnet-build`,
> `eslint`, `prettier`, `sqlfluff`, `validate-scan-config`), a second local runner
> (Lefthook, now the default), and the optional Layer-B agentic fix loop. These are
> additive — the existing Terraform hooks and their contracts are unchanged. The
> major bump reflects the platform's evolution from a Terraform-only scan POC into
> a reusable scan→fix platform (and the new `scan-config.yaml` /
> `scan-config.schema.json` becoming the configuration surface).

### What Constitutes a Breaking Change

- Renaming or removing a hook ID (hook IDs are stable contracts)
- Changing exit code meanings (e.g., exit 1 no longer means "findings")
- Removing a script or changing its required arguments
- Changing the structure of `.scanning/last-scan.json` in backward-incompatible ways
- Removing fields from `schemas/unified-results.schema.json`
- Backward-incompatible changes to `scan-config.yaml` / `scan-config.schema.json`
  (e.g. renaming `languages.*.build`, or `fix_loop` required fields)

### What Is NOT a Breaking Change

- Adding new hooks (consumers must opt in by enabling the matching `languages.*`)
- Adding optional parameters to scripts
- Adding fields to JSON schemas (additive)
- Changing tool version minimums (documented in release notes)
- Internal refactoring of hook implementations
- Bumping the centralized `claude-code-action` SHA pin to a newer compatible
  version (documented in release notes)

## Upgrading Versions

To move a workflow caller to a new release, follow [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md).
It moves `uses:` and `scanning-repo-ref` together and records the failed checks before
and after.

### Upgrading from a Release Before 2.1.0

If you pin any release before `v2.1.0` (`v2.0.9` or earlier), `reusable-scan.yml` did not
scan the way its name suggests. The 2.1.0 entry of [CHANGELOG.md](../CHANGELOG.md)
records it (`CHANGELOG.md:18-31` at commit `7cd34a5`):

- **Checkov never ran.** It rejected the output list it was given, wrote no report, and
  `continue-on-error` kept the job green.
- **TFLint linted at most the scan root.** Every other directory failed to load its
  config, and those errors were dropped.
- **No Checkov finding could reach the pull request comment or the metrics.** The
  Aggregate step read Checkov's JSON at the wrong level.
- Every release before `v2.1.0` used Checkov 2.0.930 and the latest TFLint on each run.
  `v2.0.5` to `v2.0.9` installed Trivy 0.71.0. `v2.0.0` to `v2.0.4` set no Trivy version,
  so `trivy-action` fell back to its default, Trivy 0.65.0, which fails to install on the
  runner, and their TFLint job got no config (the 2.0.5 entry of
  [CHANGELOG.md](../CHANGELOG.md)).

So a passing scan on `v2.0.5` to `v2.0.9` shows only that Trivy found nothing at the
gated severities. On `v2.0.0` to `v2.0.4`, Trivy did not scan at all, so a passing scan
shows nothing. When you move to `v2.1.0` or later:

- Expect findings the scan never showed: TFLint warnings and Checkov failed checks in the
  pull request comment, and Checkov alerts in code scanning (`CHANGELOG.md:57-59`).
- Checkov findings normally count as MEDIUM and do not block (`CHANGELOG.md:46-47`). A
  TFLint rule at `error` level counts as HIGH and does block
  (`.github/workflows/reusable-scan.yml:646`).
- Checkov uses this repository's `configs/<cloud>/.checkov.yaml`, not your own Checkov
  config (`CHANGELOG.md:59-60`).
- Set `scanning-repo-ref` to the same commit as `uses:` (`CHANGELOG.md:60-61`). If it is
  unset, it defaults to `v1.0.0` (`.github/workflows/reusable-scan.yml:40-44`), which is
  not a tag in this repository.

Line references are at commit `7cd34a5`. Follow [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md) for
the upgrade.

### Automatic Update

```bash
# Update all pre-commit repos to latest tag
pre-commit autoupdate
```

This updates the `rev:` field in `.pre-commit-config.yaml` to the latest tagged release.

### Manual Update

Edit `.pre-commit-config.yaml` directly:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: vX.Y.Z    # The release you are moving to
```

### Verify After Upgrade

```bash
# Run all hooks to verify compatibility
pre-commit run --all-files

# Clear cache if hooks behave unexpectedly
pre-commit clean
pre-commit install
```

## CI/CD Workflow Pinning

The reusable GitHub Actions workflows are pinned the same way, with `@<tag>` (or a
full SHA) — **never `@main`**. Put each call in its own caller workflow file; two calls
from one caller workflow share a concurrency group (see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#concurrency)). `OWNER` is the owner of
your repository, and needs its own public copy of `auto-code-scanning`; see
[Pin the Commit a Release Tag Points To](#pin-the-commit-a-release-tag-points-to).

```yaml
# .github/workflows/code-security-scan.yml: application code
jobs:
  code-scan:
    uses: OWNER/auto-code-scanning/.github/workflows/code-security-scan.yml@v2.3.2 # x-release-please-version
```

```yaml
# .github/workflows/terraform-scan.yml: Terraform
jobs:
  terraform-scan:
    uses: OWNER/auto-code-scanning/.github/workflows/reusable-scan.yml@v2.3.2 # x-release-please-version
    with:
      cloud-provider: aws
      scanning-repo-ref: v2.3.2 # x-release-please-version
```

```yaml
# .github/workflows/autonomous-fix.yml: optional fix loop (Layer B)
jobs:
  fix:
    uses: OWNER/auto-code-scanning/.github/workflows/autonomous-fix.yml@<commit-sha> # v2.3.2 x-release-please-version
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      scanning_repo: OWNER/auto-code-scanning   # defaults to the upstream repository
      scanning_repo_ref: <commit-sha> # v2.3.2 x-release-please-version
    secrets:
      AUTOFIX_TOKEN: ${{ secrets.AUTOFIX_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
```

Each excerpt leaves out the triggers and permissions; see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md) for every input and the permissions each
call needs.

The fix loop is the one call that pushes to your repository, so pin the commit and pass
only the three secrets `autonomous-fix.yml` declares (`autonomous-fix.yml:56-65`). The
shipped `templates/fix-loop/autonomous-fix.yml` says `secrets: inherit`; replace it. Never
use `secrets: inherit` there: it hands the called workflow every secret of your repository
and organisation. See [step 4 of CONSUMER-MIGRATION.md](CONSUMER-MIGRATION.md#4-pin-the-callers-and-grant-their-permissions).

The shipped caller templates (`templates/workflows/`, `templates/fix-loop/`) pin the release
they ship in, and release-please moves those pins at each release, as it does the pins in
these docs. `setup-scan-fix` copies them unchanged. Releases up to and including v2.3.1
shipped `@v2.0.0` in all of them: if you copied one of those, move the pins to the current
release.

The pre-commit templates follow the same rule. All six,
`templates/{starter,standard,strict,aws,azure,gcp}/pre-commit-config.yaml`, pin this
repository at the release they ship in. Releases up to and including v2.3.1 pinned
`rev: v1.0.0`, a tag that does not exist. With `--hooks-runner pre-commit`,
`setup-scan-fix` copies `templates/<tier>/pre-commit-config.yaml` to
`.pre-commit-config.yaml` when that file does not exist yet
(`scripts/setup-scan-fix.py:91-95`, `scripts/setup-scan-fix.ps1:100-102`), and
[SETUP-GUIDE.md](SETUP-GUIDE.md) has you copy the starter template by hand. If you copied
a template from one of those releases, change `rev:` to the current release before your
first commit or `pre-commit run`, because until then pre-commit cannot fetch the hooks.

Dependabot can update the `uses:` line of a reusable workflow
([GitHub Docs](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot)),
but `scanning-repo-ref` and `scanning_repo_ref` are ordinary inputs: move them yourself,
as in [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md).

## Scanner Versions in the Terraform Scan

`reusable-scan.yml` installs exact versions of Checkov, Trivy and TFLint, so every
consumer that pins a release scans with the same tools and rules. The optional Snyk job
installs an exact CLI version too (up to and including v2.3.2 it installed the latest).
Pass the same commit as
`scanning-repo-ref`, because the TFLint rulesets come from the configs checked out
at that ref.

| Scanner | Version | Where it is pinned |
|---|---|---|
| Checkov | 3.3.19 | the `bridgecrewio/checkov-action` SHA (v12.3125.0): the action's `action.yml` names the image `ghcr.io/bridgecrewio/checkov:3.3.19` |
| Trivy | 0.75.0 | `version:` on each of the four `aquasecurity/trivy-action` steps |
| TFLint | 0.64.0 | `tflint_version:` and `checksums:` on `terraform-linters/setup-tflint` |
| TFLint rulesets | terraform 0.15.0, azurerm 0.32.0, aws 0.49.0, google 0.40.0 | the `plugin` blocks in `configs/<cloud>/.tflint.hcl` |
| Snyk CLI (optional job) | 1.1307.4 | `npm install -g snyk@1.1307.4` in the `scan-snyk` job (`reusable-scan.yml:507-508`) |

Every run logs the Checkov, Trivy and TFLint versions it used: the Checkov step's image
tag and banner, the `Show Trivy version` step, and the `Show TFLint version` step, which
lists each ruleset. Some inputs still move without a pin. Trivy downloads its
misconfiguration checks bundle at run time, and `Show Trivy version` logs that bundle's
digest. When `enable-snyk` is `true`, the Snyk job installs the `snyk` package at the
exact version above (`reusable-scan.yml:507-508`), but npm still resolves that package's
own dependencies at run time, and no step logs the version it installed.

To bump a scanner, change it in one release:

1. Checkov: choose the `checkov-action` tag whose `action.yml` names the Checkov
   image you want, and pin that tag's commit SHA.
2. Trivy: change all four `version:` values together.
3. TFLint: change `tflint_version:`, and replace `checksums:` with the SHA-256 of
   `tflint_linux_amd64.zip` and `tflint_linux_arm64.zip` from that release's
   `checksums.txt`.
4. Rulesets: change the `version` in every `configs/<cloud>/.tflint.hcl` that uses
   the plugin.
5. Snyk: change the version in `npm install -g snyk@<version>` (`reusable-scan.yml:508`,
   the job is optional) to the one `npm view snyk dist-tags.latest` reports, and update the
   table. `tests/python/test_workflow_pins.py` fails if the version is not exact.

`.github/workflows/reusable-scan-self-test.yml` runs the scan on any change to it or
to `configs/`, and fails if a scanner wrote no report or TFLint reported an error.

`scan-config.yaml` carries no tool versions. The local hooks run whichever version
of each tool is on `PATH`.

## The Centralized `claude-code-action` Pin (Layer B)

The agentic fix loop calls Anthropic's `claude-code-action`. That action is
**SHA-pinned, centrally**, so all consumers inherit a single safe version:

- **Pin**: `anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102` (**v1.0.148**)
- **Why this version is safe**: CVE-2025-66032 / GHSA-xq4m-mc3c-vvg3 is a flaw in the
  Claude Code CLI (npm `@anthropic-ai/claude-code`, fixed in 1.0.93), not in
  `claude-code-action`. The two version numbers are unrelated. The pinned action,
  v1.0.148, locks `@anthropic-ai/claude-agent-sdk` 0.3.177 in its `bun.lock`, and that
  SDK release matches Claude Code 2.1.177, well past the fix.

The SHA is set in `.github/workflows/autonomous-fix.yml`, the source of truth (line 242;
the header comment at line 27 names the version). It is mirrored as
`fix_loop.claude_code_action_ref` in `scan-config.yaml` and in
`templates/scan-config/starter.yaml`, `standard.yaml` and `strict.yaml`, which
`setup-scan-fix` copies into a new adopter's `scan-config.yaml`. Nothing checks that
these agree, and nothing reads the mirror at run time; the schema checks only its format.

The config **schema enforces a SHA pin**: `schemas/scan-config.schema.json`
constrains `claude_code_action_ref` to the pattern
`^anthropics/claude-code-action@[0-9a-f]{40}$`, so `validate-scan-config` rejects a
tag-only or `@main` ref when it can run the check. PyYAML and `jsonschema` must be
installed, and the validator must find `schemas/scan-config.schema.json`. The copy that
setup puts in an adopter's `scripts/` cannot find it, because setup does not copy
`schemas/`. Otherwise it prints a warning and exits 0, unless `STRICT=1` is set, which
turns the skip into a failure (`scripts/validate-scan-config.py:40-60`). No CI workflow
runs it.

Because the action is referenced only from the reusable workflow, every consumer that
`uses:` `autonomous-fix.yml@v2.0.0` gets the safe pin automatically — there is nothing
for the consumer to pin themselves.

### Bumping the `claude-code-action` Pin Deliberately

To move to a newer (or different) `claude-code-action` release, change it in every
place listed above together, in the same commit, then re-pin consumers to the new tag:

1. Update the `uses:` SHA, the trailing `# vX.Y.Z` comment and the header comment in
   `.github/workflows/autonomous-fix.yml`.
2. Update `fix_loop.claude_code_action_ref` to the **same** 40-char SHA in
   `scan-config.yaml` and in the three files under `templates/scan-config/`.
3. Run `git grep -n -e <old-sha> -e <old-version>` and update every hit except history
   (`CHANGELOG.md`, `MIGRATION-ANALYSIS.md`, `ROADMAP.md`). Today that also covers this
   page, `FIX-LOOP.md`, `consumer-repo-setup-guide.md`, `ADOPTION-PLAYBOOK.md`,
   `AI-AGENT-GUIDE.md`, `SECURITY-MODEL.md` and `TESTING-GUIDE-CONSUMING-REPO.md`.
4. With `pyyaml` and `jsonschema` installed, run
   `STRICT=1 python scripts/validate-scan-config.py <file>` on `scan-config.yaml` and on
   each file in `templates/scan-config/`. Each must print `VALID`. This rejects a non-SHA
   ref. The pre-commit hook checks only the root `scan-config.yaml`.
5. Merge the change under a `fix:` or `feat:` PR title, then merge the release PR that
   follows. Never tag by hand.
6. Consumers bump their workflow `uses:` pin to the commit of the new release tag.

When you bump, check the `@anthropic-ai/claude-agent-sdk` version locked in that action
release's `bun.lock`, and the Claude Code version that SDK release matches (the
`claudeCodeVersion` field in its package metadata on npm). It must be 1.0.93 or later.
The action's own version number does not tell you this.

## Third-Party Action Pinning (This Repo)

Every workflow in `.github/workflows/` SHA-pins the third-party actions it uses, with a
trailing `# vX.Y.Z` comment for readability, and `semgrep.yml` runs its container image by
digest (`semgrep/semgrep@sha256:...`, with the version and the date it was resolved in a
comment; Dependabot does not update a workflow's container image, so renew it
deliberately). For example, the reusable workflows use
`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2`, and
`autonomous-fix.yml` uses `anthropics/claude-code-action@d5726de... # v1.0.148`. SHA pins
protect against a tag being moved to malicious code. `claude.yml` and `semgrep.yml` were
the two exceptions through v2.3.2. A test (`tests/python/test_workflow_pins.py`) refuses
an unpinned action, an image without a digest and an unpinned Snyk install. Apply the same
discipline in your own workflows when you copy the caller templates.

## Recommended Practices

1. **Pin to exact versions in production**: Use `v2.3.2` (or a full SHA), never `main` <!-- x-release-please-version -->
2. **Pin pre-commit `rev:` AND workflow `uses:` together**: keep both at the same tag
3. **Review release notes before upgrading**: Check for breaking changes
4. **Test after upgrading**: Run `pre-commit run --all-files` to verify
5. **Upgrade regularly**: Stay within 1-2 minor versions of latest for security patches
6. **Use the same version in pre-commit and CI**: Avoid drift between local and CI scanning
7. **Keep the `claude-code-action` pin and `fix_loop.claude_code_action_ref` in sync**: see above

## Checking Current Version

```bash
# See what version is pinned
grep "rev:" .pre-commit-config.yaml

# See available versions
git ls-remote --tags https://github.com/agenticcodingops/auto-code-scanning

# See which release a checkout of this repository is
cat version.txt
```

## Rollback

To roll back a workflow caller, move every pin you changed back to the previous commit, as
in the Rollback section of [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md#rollback). Revert the bump
commit only if it changed nothing but pins: after a squash merge it also undoes the
Terraform fixes made in the same pull request.

If a pre-commit upgrade causes issues:

1. Edit `.pre-commit-config.yaml` and revert the `rev:` to the previous version
2. Clear the pre-commit cache:
   ```bash
   pre-commit clean
   pre-commit install
   ```
3. Verify hooks work:
   ```bash
   pre-commit run --all-files
   ```
