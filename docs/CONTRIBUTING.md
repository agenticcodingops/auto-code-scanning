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
   version in `.release-please-manifest.json`, `version.txt`, and every file listed under
   `extra-files` in `release-please-config.json` (on the lines marked
   `x-release-please-version`). Those are `README.md` and the adopter docs that show a pin.
   On a marked line, release-please replaces only the first `X.Y.Z`, so a marked line holds
   one version: the current one. When you add a pin to a doc, mark its line and list the
   doc under `extra-files`. `tests/python/test_release_config.py` checks that every listed
   file has at least one marked line, and that each marked line holds the current version.
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

### The release GitHub App

`release.yml` writes with an installation token of the organization's release GitHub
App, not with `GITHUB_TOKEN`. GitHub starts no workflow for a PR, tag or release created
with `GITHUB_TOKEN`, but it does for one created with an App's token: CI runs on the
release PR, and publishing the release starts its verification run. The workflow's
`permissions:` block governs only `GITHUB_TOKEN`.

- **Owner:** the App belongs to the `agenticcodingops` organization, not to a person.
  Organization owners and the App's managers administer the App's settings and private
  keys. Only organization owners can change its installation, including which
  repositories it covers: the App manager role cannot install or uninstall an App.
  Release PRs, release commits, tags and releases show the App's bot account as their
  author.
- **Where its credentials live:** the App's client ID is the organization variable
  `RELEASE_APP_CLIENT_ID`, and its private key the organization secret
  `RELEASE_APP_PRIVATE_KEY` (Organization settings → Secrets and variables → Actions).
  Both are shared with selected repositories, and this repository must be one of them.
  The App's installation (Organization settings → GitHub Apps → the App → Configure)
  must include this repository too.
- **What each run gets:** the *Mint the release token* step runs
  `actions/create-github-app-token` with that client ID and key. It sets no `owner` or
  `repositories`, so the token covers this repository only, and it asks for these
  permissions and nothing else:
  - Contents: write (release branch, commits, tags, releases)
  - Pull requests: write (the release PR)
  - Issues: write (the labels and comments release-please puts on the release PR)

  Metadata read comes with every token. The App's installation must grant at least these
  permissions, or minting fails. The token expires within an hour and is revoked when the
  job ends. Workflows permission is not needed, because the release PR never changes a
  file under `.github/workflows/`; keep workflow files out of `extra-files`.
- **Rotating the private key:** an App's private key has no expiry date, so rotate it on
  the organization's schedule, and at once if it may have leaked or when someone who held
  a copy leaves.
  1. In the App's settings (Organization settings → Developer settings → GitHub Apps →
     the App), generate a new private key.
  2. Replace the value of the `RELEASE_APP_PRIVATE_KEY` organization secret with the new
     key.
  3. Run **Actions → Release → Run workflow** on `main` and check that *Mint the release
     token* passes.
  4. Delete the old key in the App's settings, and any downloaded copy of either key.
- **When it fails:** if the variable or the secret is not shared with this repository,
  the Release workflow stops at *Require the release App's client ID and private key*. If
  the key was deleted or is wrong, the App is not installed on this repository, or the
  installation lacks one of the permissions, it fails at *Mint the release token*.
  Nothing is released until it is fixed.

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
  `version.txt` and on the `x-release-please-version` lines of every file listed under
  `extra-files` in `release-please-config.json`, create an annotated tag on the release commit with
  `git tag -a vX.Y.Z -m "<summary>"`, and push it. Tags and releases created in the
  meantime stay valid.

## Code Standards

- PowerShell scripts follow PSScriptAnalyzer rules
- YAML files must be valid
- All hooks must complete in <5 seconds
- Documentation required for all features
