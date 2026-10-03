# Version Pinning Guide

How to manage versions of auto-code-scanning in your repository.

The current release is **`v2.1.0`**. <!-- x-release-please-version -->

Releases after `v2.1.0` are cut by release-please (see "Release Process" in
[CONTRIBUTING.md](CONTRIBUTING.md)). Each one has a GitHub Release with its notes, a
`CHANGELOG.md` entry, and a **Release Verification** run on its tag whose logs and job
summaries record the exact scanner and ruleset versions it installs. `version.txt` at the
root of each release holds its version.

## Pin to a Release Tag — Never `@main`

> **MANDATORY.** Consumers **MUST** pin every reference to this repo to a release
> tag (e.g. `@v2.0.0`) or a full 40-character commit SHA. **Never** reference
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
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@<commit-sha> # vX.Y.Z
    with:
      cloud-provider: aws
      scanning-repo-ref: <commit-sha>
```

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
    rev: v2.0.0    # Pinned to exact version — never @main
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
    rev: v2.1.0    # Changed from v2.0.0
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
full SHA) — **never `@main`**:

```yaml
jobs:
  # App-code + IaC scan (v2.0.0 generic reusable workflow)
  security:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/code-security-scan.yml@v2.0.0

  # Terraform-only scan (original reusable workflow)
  iac:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v2.0.0

  # Optional agentic fix loop (Layer B)
  autofix:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/autonomous-fix.yml@v2.0.0
```

The shipped caller templates (`templates/workflows/`, `templates/fix-loop/`)
already pin to `@v2.0.0`. Update the `@` reference when upgrading. Unlike
pre-commit, there is no automatic update mechanism for workflow references.

## Scanner Versions in the Terraform Scan

`reusable-scan.yml` installs exact scanner versions, so every consumer that pins a
release scans with the same tools and rules. Pass the same commit as
`scanning-repo-ref`, because the TFLint rulesets come from the configs checked out
at that ref.

| Scanner | Version | Where it is pinned |
|---|---|---|
| Checkov | 3.3.19 | the `bridgecrewio/checkov-action` SHA (v12.3125.0): the action's `action.yml` names the image `ghcr.io/bridgecrewio/checkov:3.3.19` |
| Trivy | 0.75.0 | `version:` on each of the four `aquasecurity/trivy-action` steps |
| TFLint | 0.64.0 | `tflint_version:` and `checksums:` on `terraform-linters/setup-tflint` |
| TFLint rulesets | terraform 0.15.0, azurerm 0.32.0, aws 0.49.0, google 0.40.0 | the `plugin` blocks in `configs/<cloud>/.tflint.hcl` |

Every run logs the versions it used: the Checkov step's image tag and banner, the
`Show Trivy version` step, and the `Show TFLint version` step, which lists each
ruleset. One input still moves without a pin: Trivy downloads its misconfiguration
checks bundle at run time, and `Show Trivy version` logs that bundle's digest.

To bump a scanner, change it in one release:

1. Checkov: choose the `checkov-action` tag whose `action.yml` names the Checkov
   image you want, and pin that tag's commit SHA.
2. Trivy: change all four `version:` values together.
3. TFLint: change `tflint_version:`, and replace `checksums:` with the SHA-256 of
   `tflint_linux_amd64.zip` and `tflint_linux_arm64.zip` from that release's
   `checksums.txt`.
4. Rulesets: change the `version` in every `configs/<cloud>/.tflint.hcl` that uses
   the plugin.

`.github/workflows/reusable-scan-self-test.yml` runs the scan on any change to it or
to `configs/`, and fails if a scanner wrote no report or TFLint reported an error.

`scan-config.yaml` carries no tool versions. The local hooks run whichever version
of each tool is on `PATH`.

## The Centralized `claude-code-action` Pin (Layer B)

The agentic fix loop calls Anthropic's `claude-code-action`. That action is
**SHA-pinned, centrally**, so all consumers inherit a single safe version:

- **Pin**: `anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102` (**v1.0.148**)
- **Why this version**: it is `>= 1.0.93`, which fixes
  **CVE-2025-66032 / GHSA-xq4m-mc3c-vvg3**.

This pin lives in two places that **must stay in sync**:

1. **Source of truth**: `.github/workflows/autonomous-fix.yml` (the reusable
   workflow that actually invokes the action).
2. **Mirror**: `fix_loop.claude_code_action_ref` in `scan-config.yaml`.

The config **schema enforces a SHA pin**: `schemas/scan-config.schema.json`
constrains `claude_code_action_ref` to the pattern
`^anthropics/claude-code-action@[0-9a-f]{40}$`, so a tag-only or `@main` ref is
**rejected** by `validate-scan-config`. Because the action is referenced only from
the reusable workflow, every consumer that `uses:` `autonomous-fix.yml@v2.0.0`
gets the safe pin automatically — there is nothing for the consumer to pin
themselves.

### Bumping the `claude-code-action` Pin Deliberately

To move to a newer (or different) `claude-code-action` release, change it in **both**
places together, in the same commit, then re-pin consumers to the new tag:

1. Update the `uses:` SHA (and the trailing `# vX.Y.Z` comment) in
   `.github/workflows/autonomous-fix.yml`.
2. Update `fix_loop.claude_code_action_ref` in `scan-config.yaml` to the **same**
   40-char SHA.
3. Run `validate-scan-config` (it will reject a non-SHA ref), merge the change under a
   `fix:` or `feat:` PR title, then merge the release PR that follows. Never tag by hand.
4. Consumers bump their workflow `uses:` pin to the commit of the new release tag.

Keep the new version `>= 1.0.93`. Never downgrade below the CVE-2025-66032 fix.

## Third-Party Action Pinning (This Repo)

Every third-party GitHub Action used by **this repo's own** workflows is SHA-pinned
(with a trailing `# vX.Y.Z` comment for readability) — for example
`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2` and
`anthropics/claude-code-action@d5726de... # v1.0.148`. SHA pins protect against a
tag being moved to malicious code. Apply the same discipline in your own
workflows when you copy the caller templates.

## Recommended Practices

1. **Pin to exact versions in production**: Use `v2.0.0` (or a full SHA), never `main`
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

If an upgrade causes issues:

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
