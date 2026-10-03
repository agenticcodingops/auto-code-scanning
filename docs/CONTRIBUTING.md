# Contributing

## How to Contribute

1. Fork this repository
2. Create a feature branch
3. Make your changes, with [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) messages
4. Ensure all tests pass
5. Submit a pull request whose title is a conventional commit: it becomes the
   squash commit on `main` and the changelog entry (see [Release Process](#release-process))

## Adding a New Hook

1. Add the hook definition to `.pre-commit-hooks.yaml`
2. Add test fixtures in `tests/fixtures/`
3. Update `tests/` with integration tests
4. Update `docs/HOOK-REFERENCE.md`
5. Update relevant templates

## Adding a New Cloud Provider

1. Create `configs/{provider}/.checkov.yaml` with CIS Benchmark checks
2. Create `configs/{provider}/.tflint.hcl` with provider plugin
3. Create `templates/{provider}/pre-commit-config.yaml`
4. Add test fixture `tests/fixtures/terraform-{provider}-fail/`
5. Update `docs/MULTI-CLOUD.md`

## Release Process

Releases are cut by [release-please](https://github.com/googleapis/release-please)
from `.github/workflows/release.yml`. **Never create a release tag or a GitHub Release
by hand.** `v2.1.0` was the last release cut by hand.

### How a release happens

1. Every push to `main` runs release-please. It reads the conventional commits merged
   since the last release and keeps one release PR open, titled
   `chore(main): release X.Y.Z`. That PR adds the `CHANGELOG.md` entry and sets the new
   version in `.release-please-manifest.json`, `version.txt`, `README.md` and
   `docs/VERSION-PINNING.md` (on the lines marked `x-release-please-version`).
2. CI runs on the release PR like on any other. Review it, and squash-merge it when you
   want to release.
3. The run on that merge creates the tag `vX.Y.Z` on the merge commit and a GitHub
   Release with the same notes.
4. Publishing the release starts the **Release Verification** workflow
   (`release-verify.yml`) on the tag. Its logs and job summaries record what the release
   installs: the exact Checkov, Trivy and TFLint versions, the TFLint ruleset versions and
   the digest of the Trivy checks bundle. It fails if a scanner wrote no report.
5. Consumers move their pins: see [VERSION-PINNING.md](VERSION-PINNING.md).

To regenerate the release PR without a new commit, for example after a change to
`release-please-config.json`, run **Actions → Release → Run workflow** on `main`.

The configuration is `release-please-config.json` (release type `simple`, tags
`vX.Y.Z`) and the last released version is in `.release-please-manifest.json`. The
`simple` release type also keeps the version in `version.txt`, so a checkout of any
release can tell its version.

### Commit types decide the version

| Commit | Changelog section | Version bump |
|---|---|---|
| `feat: …` | Features | minor |
| `fix: …` | Bug Fixes | patch |
| `perf: …` | Performance Improvements | patch |
| `revert: …` | Reverts | patch |
| any type with `!` (`feat!: …`, `ci!: …`) or a `BREAKING CHANGE:` footer | ⚠ BREAKING CHANGES | major |
| `docs`, `chore`, `ci`, `test`, `style`, `refactor`, `build` | hidden | none |

- The largest bump among the commits since the last release wins.
- Hidden types never open a release PR on their own and never appear in the changelog.
  They ship in the next release that has a visible commit.
- Write a revert as `revert: <subject of the reverted commit>`. Git's default
  `Revert "…"` message is not a conventional commit, and release-please ignores it.
- release-please splits a commit message at every blank line that is followed by a
  conventional header, and reads each part as its own entry. Keep such lines out of
  commit bodies and PR titles unless you mean them as entries.

### Forcing a version

The next release PR proposes exactly the version named by a `Release-As:` footer in a
commit that lands on `main`. A squash merge keeps only the PR title, so put the footer in
the PR description, as a commit override that repeats the title:

```text
BEGIN_COMMIT_OVERRIDE
feat(scan): <the PR title>

Release-As: 3.0.0
END_COMMIT_OVERRIDE
```

A footer typed into the squash commit message when merging works too.

### Merging pull requests

**Squash-merge every PR, release PRs included**, with the repository's default squash
commit message set to the pull request title:

- The PR title is the commit release-please reads. It must be a conventional commit; it
  decides the bump and becomes the changelog entry.
- When a PR carries several changes that each deserve an entry, list them in the PR
  description between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE`, one
  conventional commit per paragraph. release-please reads those instead of the title.
- A merge commit would put every commit on the branch into the changelog, and the PR
  title a second time: GitHub writes the title into the merge commit's body, where
  release-please reads it as one more entry. Its `Merge pull request …` subject also
  makes `bypass-detection.yml` warn.
- A squash-merged release PR leaves `chore(main): release X.Y.Z (#N)` as the head of
  `main`, and the release tag points to that commit.

### The release token

`release.yml` writes with the `RELEASE_PLEASE_TOKEN` repository secret, not with
`GITHUB_TOKEN`. GitHub starts no workflow for a PR, tag or release created with
`GITHUB_TOKEN`: the release PR would get no CI, and publishing the release would not
start its verification run. The workflow's `permissions:` block governs only
`GITHUB_TOKEN`; the token's own permissions are what apply.

- **Owner:** a maintainer with admin access to this repository creates the token, under
  their own account or a dedicated machine account, and owns its rotation. Release PRs,
  tags and releases show that account as their author.
- **Scope:** a fine-grained personal access token, resource owner `agenticcodingops`,
  repository access to this repository only, with these repository permissions:
  - Contents: read and write (release branch, commits, tags, releases)
  - Pull requests: read and write (the release PR, its labels and its comments)
  - Metadata: read (always included)

  Nothing else. GitHub accepts Pull requests write for the labels and comments
  release-please puts on its PRs, so Issues is not needed. Workflows is not needed
  either, because the release PR never changes a file under `.github/workflows/`; keep
  workflow files out of `extra-files`.
- **Rotation:** give the token an expiry within the organization's limit, and replace it
  before it expires: create a new token with the same settings, update the secret, then
  delete the old token. Replace it at once if it may have leaked, or when its owner
  leaves the project. If the secret is missing, the Release workflow stops at
  *Require RELEASE_PLEASE_TOKEN*; if the token has expired or been revoked, it fails at
  *Run release-please*. Nothing is released until the secret is fixed.

### Recovering from a bad release

Never move, delete or re-create a published tag: consumers pin the commit it points to.

- **The release PR proposes the wrong version:** land a `Release-As:` footer on `main`,
  as in [Forcing a version](#forcing-a-version).
- **The release PR's notes are wrong:** edit the description of the merged PR that
  produced the entry, add a `BEGIN_COMMIT_OVERRIDE` … `END_COMMIT_OVERRIDE` block with the
  corrected message, then run **Actions → Release → Run workflow** on `main`. Do not edit
  the release PR itself: release-please rewrites it on every run.
- **A released version is broken:** fix forward. Merge a `fix:` or `revert:` commit,
  release the next patch, and edit the broken release's notes on GitHub to name the
  version that replaces it.
- **Release Verification failed on a tag:** read the failing job. A scanner that wrote
  no report means the release is broken: fix forward as above. If the run died before
  any scan ran (checkout, runner loss), re-run its failed jobs.
- **The release PR was merged but no release was created** (the Release run failed or
  was skipped): run **Actions → Release → Run workflow** on `main`. release-please finds
  the merged PR, still labelled `autorelease: pending`, and creates the tag and the
  release. Until then it opens no new release PR.
- **Back to manual releases (rollback):** delete `release.yml`, `release-verify.yml`,
  `release-please-config.json`, `.release-please-manifest.json` and
  `tests/python/test_release_config.py` (it reads those files), and remove the
  `workflow_call` trigger from `reusable-scan-self-test.yml`. Then cut releases by hand
  again, as up to `v2.1.0`: add the `CHANGELOG.md` entry, set the new version in
  `version.txt` and on the `x-release-please-version` lines of `README.md` and
  `docs/VERSION-PINNING.md`, create an annotated tag on the release commit with
  `git tag -a vX.Y.Z -m "<summary>"`, and push it. Tags and releases created in the
  meantime stay valid.

## Code Standards

- PowerShell scripts follow PSScriptAnalyzer rules
- YAML files must be valid
- All hooks must complete in <5 seconds
- Documentation required for all features
