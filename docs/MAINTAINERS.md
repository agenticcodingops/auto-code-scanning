# Maintainer guide

This page is for maintainers with write access to the repository. It covers how
releases are cut, how the release automation is set up, and how to recover when a
release goes wrong. Contributors start at [Contributing](../CONTRIBUTING.md).

## Release process

Releases are cut by [release-please](https://github.com/googleapis/release-please)
from `.github/workflows/release.yml`. **Never create a release tag or a GitHub Release
by hand.** `v2.1.0` was the last release cut by hand.

### How a release happens

1. Every push to `main` runs release-please. It reads the Conventional Commits merged
   since the last release and keeps one release PR open, titled
   `chore(main): release X.Y.Z`. That PR adds the `CHANGELOG.md` entry and sets the new
   version in `.release-please-manifest.json`, `version.txt`, and every file listed under
   `extra-files` in `release-please-config.json` (on the lines marked
   `x-release-please-version`). Those include `README.md`, adopter docs that show a pin,
   and the current release tag used as `reusable-scan.yml`'s `scanning-repo-ref` default.
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
release can tell its version. No floating major tag (such as `v3`) is published.

The commit types that decide the version are listed in
[Contributing](../CONTRIBUTING.md#commit-types-decide-the-version). release-please splits
a commit message at every blank line that is followed by a Conventional Commit header,
and reads each part as its own entry. Keep such lines out of commit bodies and PR
titles unless you mean them as entries.

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

- The PR title is the commit release-please reads. It must be a Conventional Commit; it
  decides the bump and becomes the changelog entry.
- When a PR carries several changes that each deserve an entry, list them in the PR
  description between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE`, one
  Conventional Commit per paragraph. release-please reads those instead of the title.
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
  - Workflows: write (the release-managed default tag in `reusable-scan.yml`)
  - Pull requests: write (the release PR)
  - Issues: write (the labels and comments release-please puts on the release PR)

  Metadata read comes with every token. The App's installation must grant at least these
  permissions, or minting fails. The token expires within an hour and is revoked when the
  job ends. Workflows permission lets release-please update the marked default in
  `reusable-scan.yml`; without it, GitHub rejects the release PR's workflow-file change.
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

## How consumers pick up a release

The platform does not update installed consumers automatically. A consumer resolves
the new release tag's full commit SHA, re-vendors complete `hooks/` (including its
library), shared `scripts/` and `schemas/` byte for byte from that revision, then
updates workflow `uses:`, pre-commit `rev:`, IaC `scanning-repo-ref` and optional
fix-workflow `scanning_repo_ref` to that same SHA. Setup refreshes caller templates,
so it runs **before** the consumer restores SHA pins and project-specific settings.
For pre-commit, save the existing runner configuration outside the repository and begin
setup and verification with the new tier template and its tag-based revision. Setup
keeps an existing runner file, and verification requires exact template settings.
After template verification, restore reviewed customizations and set the full SHA;
validate and test the final configuration separately. Review policy and schema
migration, make a scanned commit, then check hosted checks on an adoption pull
request. See [Getting started upgrades](SETUP-GUIDE.md#10-upgrade-between-releases) and
[consumer migration](CONSUMER-MIGRATION.md).

Keep this in mind when a change alters vendored files, schemas or workflow inputs:
call out the consumer action in the PR description so it reaches the release notes.

## Pin inventory

Every version pin in the repository, and how pin updates arrive, is listed in
[the pin inventory](maintainers/PIN-INVENTORY.md) and
[pin freshness](PIN-FRESHNESS.md).
