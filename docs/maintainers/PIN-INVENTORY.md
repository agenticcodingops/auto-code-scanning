# Pin inventory (maintainers)

This page is for maintainers of this repository. Adopters only need
[version pinning](../VERSION-PINNING.md). It moved here from `VERSION-PINNING.md`.

The inventory below is a **dated snapshot**. Versions have moved since it was taken
(for example, release v3.1.2 installs Trivy 0.76.2 and TFLint 0.66.0). The current
values live in the workflows, `scripts/scanner-downloads.json` and the configs; the
weekly [pin freshness](../PIN-FRESHNESS.md) report lists what is outdated.

## How pin updates arrive

[`.github/dependabot.yml`](../../.github/dependabot.yml) schedules version checks
every Monday at 06:00 UTC (`Etc/UTC`). Each configured ecosystem gets one group
for patch and minor updates; majors remain individual PRs. Up to five version
update PRs per ecosystem can be open. PRs carry the `dependencies` label, which
a maintainer must create if absent.

Updates start with `chore(deps)`, hidden from release-please, and ship with the
next release. Before merging a bump that moves a scanner engine or changes scan
behaviour for callers, retitle it `fix(deps)` and add a one-line release note.
For example, a deliberate `bridgecrewio/checkov-action` bump that installs a
newer Checkov becomes `fix(deps): update the Checkov scanner engine`, with a note
such as "Terraform scans now use the newer Checkov engine and its updated rules."
That visible commit triggers a release through the normal release PR process.

Bot-opened update PRs receive no automatic review: the review workflows skip
bot PRs, so a maintainer requests a review of each update PR. Patch and minor
Actions bumps are **Routine**: they can merge after a clean review of the current
head and green checks. Majors, Terraform CLI/providers, language runtimes, anything
touching a production-facing workflow, any pin that requires re-measurement, and
general hook and package updates are **Maintainer** decisions. A group containing
any Maintainer change waits as a whole.

### Coverage and exclusions

- `github-actions` at `/` covers external `uses:` refs in `.github/workflows/`
  and root `action.yml`/`action.yaml`, per the
  [directory reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#directories-or-directory).
  The documented Actions configuration uses `/`; no extra template directories
  are configured. Shipped workflow callers under `templates/workflows/` and
  `templates/fix-loop/` remain release-managed. There are no composite action
  manifests under `.github/` today; a future nested composite needs a coverage
  check rather than an assumption that `/` recurses.
- `pre-commit` at `/scripts` covers its `.pre-commit-config.yaml`. The
  [supported ecosystems reference](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories#pre-commit)
  now lists it without beta enablement. Its dependency name is the hook repository
  URL, so the ignore for this repository protects its marked hook revision;
  release-please owns that revision.
  The six `templates/{starter,standard,strict,aws,azure,gcp}/pre-commit-config.yaml`
  files lack the leading dot required by the
  [updater's file matcher](https://github.com/dependabot/dependabot-core/blob/main/pre_commit/lib/dependabot/pre_commit/file_fetcher.rb).
  Their external revs need freshness reporting and coordinated manual changes;
  their own-platform revs remain release-managed. The optional Commitizen hook
  is commented out. Current SHA comments are ordinary version comments, not
  `frozen:` selectors; the support reference says such hook updates can target
  default-branch HEAD, so the maintainer must verify a released tag and coordinate
  all copies before merging a hook update.
- `anthropics/claude-code-action` is ignored for **every** update type and every
  occurrence: a bump requires manual re-measurement because a
  bump moves the bundled CLI, plus coordinated config mirrors (P1/P2 below).
- `bridgecrewio/checkov-action` is ignored for every update type: P3 requires
  choosing the embedded Checkov engine deliberately, reviewing its behaviour
  and releasing it with the matching install strings.
- `aquasecurity/trivy-action` is ignored for every update type: its inventory
  rows carry P4, requiring preservation of verified engine downloads and their
  coordinated version/checksum lock. The action version and engine version are
  separate selections; a manual bump must preserve `skip-setup-trivy`.

A separate weekly freshness job compares hand-kept pins (workflow env vars
and inputs, script constants, download locks, unsupported templates and docs)
with upstream releases and reports drift for review, preserving the inventory's
preconditions and excluding release-managed references and historical evidence.
[PIN-FRESHNESS.md](../PIN-FRESHNESS.md) describes the job, its rolling issue and
how to add a pin to its manifest.

To add a pin, record its location, update mechanism, merge lane and any existing
precondition in the inventory; confirm the updater supports its filename and
directory, then add it to the existing ecosystem entry or add an entry with the
same schedule, grouping, labels and commit prefix. Protect release-managed and
conditional pins with a documented ignore, or put unreadable pins in the
freshness inventory. Extend [the policy test](../../tests/python/test_dependabot_config.py)
and run the contributor checks before opening the PR.

## Repository pin inventory

Snapshot of commit `c09ec31`, checked 2026-11-09. This section records
values at that revision; it is not a second set of release defaults. The tables
include exact pins, ranges and floating selections. A repeated file is listed once
per row, even if it contains several occurrences. **Repeated pins must move together**;
workflow action pins and scanner engines are separate dependencies. Callers inherit
the reusable workflows' actions and scanners from the revision they select.

Updates arrive grouped, weekly, on Mondays. The last column of each table names
the merge lane:

- **Routine** means patch/minor Actions or scanner bumps that may merge after a clean
  review of the current head and green checks.
- **Maintainer** means majors, Terraform CLI/providers, language runtimes, a
  re-measure instruction, or anything touching a production-facing workflow. These
  need an explicit maintainer decision.
- **Release** means this repository's own release automation; these are not
  freshness targets. **Hand** means there is no readable dependency manifest for
  Dependabot here. Other packages and hook runners are Maintainer decisions.

A Routine entry is conditional: the maintainer exception above still applies to a
production-facing workflow. Preconditions below are quotations from existing files;
“none stated” means no extra bump condition was found beside that pin.

### Actions and reusable workflows

All 16 distinct active external action refs are full commit SHAs, with the tag in a
comment. There are no floating external `uses:` refs in `.github/workflows/`.
Dependabot ecosystem `github-actions`, directory `/`, can read these action refs;
it cannot coordinate their config mirrors or the engines selected in `with:`.

| Action / SHA | Version comment | Every workflow file | Merge lane / precondition |
|---|---|---|---|
| `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` | `v7.0.1` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/bypass-detection.yml`](../../.github/workflows/bypass-detection.yml), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/claude-code-review.yml`](../../.github/workflows/claude-code-review.yml), [`.github/workflows/claude.yml`](../../.github/workflows/claude.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/gemini-code-review.yml`](../../.github/workflows/gemini-code-review.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/pin-freshness.yml`](../../.github/workflows/pin-freshness.yml), [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`.github/workflows/semgrep.yml`](../../.github/workflows/semgrep.yml) | Routine; majors Maintainer; None stated. |
| `actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510` | `v3.3.0` | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) | Routine; majors Maintainer; None stated. |
| `actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333` | `v8.0.2` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3` | `v9.0.0` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1` | `v7.1.0` | [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` | `v7.1.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/pin-freshness.yml`](../../.github/workflows/pin-freshness.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9` | `v7.0.2` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `anthropics/claude-code-action@8cf3482550831fb35a4fc3fbf7ca139cf8028b4c` | `v1.0.233` | [`.github/workflows/claude-code-review.yml`](../../.github/workflows/claude-code-review.yml), [`.github/workflows/claude.yml`](../../.github/workflows/claude.yml) | Maintainer for review workflow; Routine patch/minor for mention workflow; P1 (review workflow). |
| `anthropics/claude-code-action@d5726de019ec4498aa667642bc3a80fca83aa102` | `v1.0.148` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml) | Routine; majors Maintainer; P2; mirrored in root/tier configs (see below). |
| `aquasecurity/trivy-action@b6643a29fecd7f34b3597bc6acb0a98b03d33ff8` | `v0.33.1` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml) | Routine; majors Maintainer; P4; action version differs from engine. |
| `aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25` | `v0.36.0` | [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; P4; action version differs from engine. |
| `bridgecrewio/checkov-action@45edc9d8856b664db2ec251f5f8632361f0a67aa` | `v12.3139.0 = Checkov 3.4.3` | [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; P3 (engine selected inside action). |
| `github/codeql-action/upload-sarif@33d7b85da1a04171e211befe2c739303b9a4c066` | `v4.39.3` | [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |
| `googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7` | `v5.0.0` | [`.github/workflows/release.yml`](../../.github/workflows/release.yml) | Routine; majors Maintainer; None stated. |
| `terraform-linters/setup-tflint@6ffdbaa3be476b3431f7275c26966ef32ff60337` | `v6.3.2` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml) | Routine; majors Maintainer; None stated. |

The following local calls use the same commit as their caller, with no independent
version to refresh:

| Local workflow reference | Caller | Update / lane |
|---|---|---|
| `./.github/workflows/reusable-scan-self-test.yml` | [`.github/workflows/release-verify.yml`](../../.github/workflows/release-verify.yml) | Hand: change repository code; Maintainer for workflow changes. |
| `./.github/workflows/reusable-scan.yml` | [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml) | Hand: change repository code; Maintainer for workflow changes. |

The commented, inactive `azure/login` example in
[the setup workflow](../../.github/workflows/copilot-setup-steps.yml) records
`a641126d1b8aa4d1fa005f4f92df94a3a4c4c906` (`v3.1.0`). It is Hand, not an active
Dependabot target; review it with the maintainer before enabling it.

### Scanner engines and rulesets

These 11 rows are separate selections, including both Semgrep installation paths.
All are Hand. Scanner patch/minor updates use the Routine lane (majors Maintainer),
subject to the applicable preconditions and the production-facing exception. TFLint rulesets are scanner
plugins, not Terraform providers.

| Scanner / plugin | Snapshot value | Every installing/config file | Hand update / existing precondition |
|---|---|---|---|
| Trivy | `0.75.0` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`scripts/scanner-downloads.json`](../../scripts/scanner-downloads.json) | Workflow env/version+SHA pair; release download lock; P4. |
| Checkov | `3.4.3` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`scripts/setup-scanning-no-admin.ps1`](../../scripts/setup-scanning-no-admin.ps1), [`scripts/setup-scanning.ps1`](../../scripts/setup-scanning.ps1), [`scripts/setup-scanning.py`](../../scripts/setup-scanning.py), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) | pip install strings plus the Checkov action above; `copilot-setup-steps.yml` installs it into its own virtual environment under `$RUNNER_TEMP` and puts a launcher symlink on `PATH`; P3, P7. |
| TFLint | `0.64.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`scripts/scanner-downloads.json`](../../scripts/scanner-downloads.json) | Workflow with/input plus release download lock; P5. |
| Gitleaks | `8.30.1` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`scripts/scanner-downloads.json`](../../scripts/scanner-downloads.json) | Release download lock and ci.yml shell version/expected checksum; P4. Local hooks execute the trusted installed binary. |
| Semgrep reusable app scan | `1.100.0` | [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml) | workflow_call semgrep-version default, installed through SEMGREP_VERSION; no checksum stated. |
| Semgrep container scan | `1.178.0` | [`.github/workflows/semgrep.yml`](../../.github/workflows/semgrep.yml) | Container digest and version/date comment; P6. `sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b`. |
| Snyk CLI | `1.1307.4` | [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`scripts/setup-scanning-no-admin.ps1`](../../scripts/setup-scanning-no-admin.ps1), [`scripts/setup-scanning.ps1`](../../scripts/setup-scanning.ps1), [`scripts/setup-scanning.py`](../../scripts/setup-scanning.py) | npm install strings; optional job/setup; no npm lockfile; P8. |
| TFLint terraform ruleset | `0.15.0` | [`configs/aws/.tflint.hcl`](../../configs/aws/.tflint.hcl), [`configs/azure/.tflint.hcl`](../../configs/azure/.tflint.hcl), [`configs/gcp/.tflint.hcl`](../../configs/gcp/.tflint.hcl) | HCL plugin version in all three cloud configs; P5. |
| TFLint azurerm ruleset | `0.32.0` | [`configs/azure/.tflint.hcl`](../../configs/azure/.tflint.hcl) | HCL plugin version; P5. |
| TFLint aws ruleset | `0.49.0` | [`configs/aws/.tflint.hcl`](../../configs/aws/.tflint.hcl) | HCL plugin version; P5. |
| TFLint google ruleset | `0.40.0` | [`configs/gcp/.tflint.hcl`](../../configs/gcp/.tflint.hcl) | HCL plugin version; P5. |

The three binary entries in [scanner-downloads.json](../../scripts/scanner-downloads.json)
each repeat the version in `version`, `checksum_source` and five release URLs
(`linux-amd64`, `windows-amd64`, `darwin-arm64`, `darwin-amd64`, `linux-arm64`).
Each platform has its own committed SHA-256. These are 15 archive records, not 15
independent tool versions. The workflows repeat Trivy's Linux amd64 SHA-256
`c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f`.
The TFLint checksum blocks in `ci.yml`, `performance-check.yml` and
`reusable-scan.yml` repeat Linux amd64
`cca9d13e2e1d7a2c627af60ff899a3c9b74212899416aeb96ec764d2ef954537`
and arm64 `560da89aacf59389d4eb029730dd5b109b7288096c32f2726a0d9e783a5ea8eb`;
the setup workflow selects the same engine without an explicit checksum block.
[scripts/install-scanner.py](../../scripts/install-scanner.py) consumes the lock rather
than carrying another version. The full platform hashes/URLs remain in that lock. CI also repeats Gitleaks'
Linux amd64 archive URL construction and SHA-256
`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`;
move its shell version, digest and version assertion with the lock.
The tests [test_autofix_file_guard.py](../../tests/python/test_autofix_file_guard.py)
and [test_workflow_pins.py](../../tests/python/test_workflow_pins.py) compare Trivy's
workflow version/checksum dynamically against the lock; they do not repeat the
literal engine version.

The fix action's `d5726de019ec4498aa667642bc3a80fca83aa102` SHA also appears in
[root scan-config](../../scan-config.yaml) and all three
[tier configs](../../templates/scan-config/starter.yaml),
[standard](../../templates/scan-config/standard.yaml) and
[strict](../../templates/scan-config/strict.yaml). These Hand mirrors are **not read at
run time**; move them with the action under P2. Documentation describes its bundled
SDK `0.3.177` and CLI `2.1.177`, with security floor `1.0.93`; those are upstream
transitive versions, not local lockfiles. The review workflow's comments record
measurements on CLI `2.1.281`, `2.1.302`, `2.1.310`, `2.1.314`, `2.1.316`;
[test_review_comment_guard.py](../../tests/python/test_review_comment_guard.py) repeats
the last measurement. Preserve them as evidence, not an installed CLI selection.

### Installed packages and hook revisions

The seven package selections below are Hand install strings or docs commands;
there is no `requirements.txt`, Python project manifest, npm manifest or package
lockfile in the tracked tree. Thus `pip` or `npm` ecosystem entries alone would
find none of these pins. Maintainer owns package/runner changes; Snyk, Semgrep and
Checkov remain scanner entries above.

| Package | Snapshot value | Every exact install string file | Lane / precondition |
|---|---|---|---|
| pytest | `9.2.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md) | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| pytest-cov | `7.1.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md) | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| PyYAML | `6.0.3` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md`, [`tests/python/test_autonomous_fix_trust_boundary.py`](../../tests/python/test_autonomous_fix_trust_boundary.py) | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| jsonschema | `4.26.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md` | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| pre-commit | `4.7.0` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`scripts/setup-scanning-no-admin.ps1`](../../scripts/setup-scanning-no-admin.ps1), [`scripts/setup-scanning.ps1`](../../scripts/setup-scanning.ps1), [`scripts/setup-scanning.py`](../../scripts/setup-scanning.py) | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| pip | `26.3` | [`scripts/setup-scanning-no-admin.ps1`](../../scripts/setup-scanning-no-admin.ps1), [`scripts/setup-scanning.ps1`](../../scripts/setup-scanning.ps1) | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |
| Prettier | `3.6.2` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md` | Maintainer; P7 for pre-commit/Checkov environments, otherwise none stated. |

The hook rows retain their snapshot classification below. Current `pre-commit`
support covers the external revs in `scripts/.pre-commit-config.yaml`; template
filenames are outside its matcher (see [coverage](#coverage-and-exclusions)).
Maintainer owns these general hook updates, including the optional Commitizen hook.
`pre-commit autoupdate` can rewrite revs, but the coordinated platform upgrade still applies.

| Hook repository | SHA / comment | Every repeating file | Update / precondition |
|---|---|---|---|
| pre-commit/pre-commit-hooks | `3e8a8703264a2f4a69428a0aa4dcb512790b2c8c` / `v6.0.0` | [`scripts/.pre-commit-config.yaml`](../../scripts/.pre-commit-config.yaml), [`templates/aws/pre-commit-config.yaml`](../../templates/aws/pre-commit-config.yaml), [`templates/azure/pre-commit-config.yaml`](../../templates/azure/pre-commit-config.yaml), [`templates/gcp/pre-commit-config.yaml`](../../templates/gcp/pre-commit-config.yaml), [`templates/standard/pre-commit-config.yaml`](../../templates/standard/pre-commit-config.yaml), [`templates/starter/pre-commit-config.yaml`](../../templates/starter/pre-commit-config.yaml), [`templates/strict/pre-commit-config.yaml`](../../templates/strict/pre-commit-config.yaml) | Hand rev/comment; none stated. |
| antonbabenko/pre-commit-terraform | `b9e409b0fee34ee0eee7e6f6a407061f15032926` / `v1.109.5` | [`scripts/.pre-commit-config.yaml`](../../scripts/.pre-commit-config.yaml), [`templates/aws/pre-commit-config.yaml`](../../templates/aws/pre-commit-config.yaml), [`templates/azure/pre-commit-config.yaml`](../../templates/azure/pre-commit-config.yaml), [`templates/gcp/pre-commit-config.yaml`](../../templates/gcp/pre-commit-config.yaml), [`templates/standard/pre-commit-config.yaml`](../../templates/standard/pre-commit-config.yaml), [`templates/starter/pre-commit-config.yaml`](../../templates/starter/pre-commit-config.yaml), [`templates/strict/pre-commit-config.yaml`](../../templates/strict/pre-commit-config.yaml) | Hand rev/comment; none stated. |
| commitizen-tools/commitizen (commented opt-in) | `a3498aba5e94c9f7c4acb529b5e7eb6df65fd053` / `v3.29.1` | [`templates/strict/pre-commit-config.yaml`](../../templates/strict/pre-commit-config.yaml) | Hand rev/comment; none stated. |

Lefthook invokes vendored hooks; its template has no remote hook `rev:`. Its
`min_version` is recorded below. The optional Commitizen revision is commented out and is not an installed tool.
The checkout `v7.0.1` SHA also repeats as an example in
[the review styleguide](../../.gemini/styleguide.md). The secret-scanner evaluation
quotes both Trivy action SHAs and checkout `v4.2.2`; the fix-action SHA repeats in
[Fix loop](../FIX-LOOP.md) and historical Migration analysis (archived).

### Runtimes, runners and minimum versions

These ten rows are Hand selections or compatibility floors, with Maintainer merge
ownership. A minimum is not the installed version. Python/Node inputs and runner
labels are not `github-actions` dependency refs.

| Runtime / runner | Snapshot value | Repeating selection / floor files | Hand update / precondition |
|---|---|---|---|
| Bun | `1.3.14` | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml) | BUN_VERSION and BUN_SHA256 env pair; Maintainer; P10. SHA-256 `951ee2aee855f08595aeec6225226a298d3fea83a3dcd6465c09cbccdf7e848f` for `bun-linux-x64.zip`. |
| Hosted runner image | `ubuntu-latest` (floating) | [`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/bypass-detection.yml`](../../.github/workflows/bypass-detection.yml), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/claude-code-review.yml`](../../.github/workflows/claude-code-review.yml), [`.github/workflows/claude.yml`](../../.github/workflows/claude.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/gemini-code-review.yml`](../../.github/workflows/gemini-code-review.yml), [`.github/workflows/performance-check.yml`](../../.github/workflows/performance-check.yml), [`.github/workflows/release.yml`](../../.github/workflows/release.yml), [`.github/workflows/reusable-scan-self-test.yml`](../../.github/workflows/reusable-scan-self-test.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`.github/workflows/semgrep.yml`](../../.github/workflows/semgrep.yml) | Workflow runs-on labels; Maintainer; image supplies unpinned tools; none stated. |
| Python | `3.11` CI; `3.11+` local | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/code-security-scan.yml`](../../.github/workflows/code-security-scan.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`README.md`](../../README.md), [`docs/CONSUMER-MIGRATION.md`](../CONSUMER-MIGRATION.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/HOOK-REFERENCE.md`](../HOOK-REFERENCE.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md), `docs/V3-BEHAVIOUR-AUDIT.md`, `docs/agent-team-implementation-guide.md`, [`hooks/lib/common.ps1`](../../hooks/lib/common.ps1), [`hooks/lib/common.sh`](../../hooks/lib/common.sh), [`scripts/create-baseline.ps1`](../../scripts/create-baseline.ps1), `specs/001-security-scanning-spec/tasks.md` (archived) | Workflow inputs; interpreter probes and docs; P9. |
| Bash | `4.4+` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/HOOK-REFERENCE.md`](../HOOK-REFERENCE.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`hooks/lib/common.sh`](../../hooks/lib/common.sh) | Shared library floor and docs; P9. |
| PowerShell | `7+`; hosted `pwsh` is image supplied | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`scripts/setup-scanning-no-admin.ps1`](../../scripts/setup-scanning-no-admin.ps1), [`scripts/setup-scanning.ps1`](../../scripts/setup-scanning.ps1) | Script prerequisite and docs; not an exact runtime pin. |
| Pester | CI `-MinimumVersion 5.0`; setup install `5.0.0`–`5.99.99` | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/copilot-setup-steps.yml`](../../.github/workflows/copilot-setup-steps.yml), [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), `docs/agent-team-implementation-guide.md`, `specs/001-security-scanning-spec/plan.md` (archived) | Import/install command; setup skips installation if any installed major is >=5; none stated. |
| Node.js | CI `20`; docs supported LTS | [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) | setup-node input / docs sentence; none stated. |
| .NET SDK | `8+` or project SDK | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) | Docs floor; no global.json or SDK setup pin here; none stated. |
| Git | `2.0+` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) | Docs floor; none stated. |
| Lefthook | `min_version: 1.6.0`; docs `1.6+` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`templates/lefthook/lefthook.yml`](../../templates/lefthook/lefthook.yml) | Template floor/docs; no exact runner install pin; none stated. |

Four scanner/runner minimums are repeated in
[scripts/setup-scanning.py](../../scripts/setup-scanning.py),
[setup-scanning.ps1](../../scripts/setup-scanning.ps1),
[setup-scanning-no-admin.ps1](../../scripts/setup-scanning-no-admin.ps1),
[Getting started](../SETUP-GUIDE.md) and [Troubleshooting](../TROUBLESHOOTING.md):
Trivy `0.48.0`, Checkov `3.0.0`, TFLint `0.50.0`, pre-commit `3.2.0`.
They are Hand constants/docs, not alternative exact installed pins; scanner
patch/minor floors use Routine, pre-commit Maintainer. Getting started additionally
names Gitleaks `8+` and Semgrep `1.60+`. The older spec floors and Python `3.8+`
are indexed below. All hosted jobs that declare `runs-on` use the floating
`ubuntu-latest` image; no OS image digest or exact PowerShell version is pinned.

### Terraform constraints and other versioned references

These six Terraform constraint rows are Dependabot `terraform` candidates in
each listed directory (the directory containing `main.tf`); they are fixture
requirements, not production deployments. Maintainer owns every CLI/provider move.
No `.terraform.lock.hcl`, external module version pin or exact Terraform installer
was found. Provider constraints can still resolve newer compatible releases.

| Terraform component | Constraint | Every repeating file | Update / precondition |
|---|---|---|---|
| CLI | `>= 1.0` | [`tests/integration/test-consuming-repo.sh`](../../tests/integration/test-consuming-repo.sh) | Maintainer; Hand: shell generates a temporary manifest. None stated. |
| CLI | `>= 1.0.0` | [`tests/fixtures/terraform-critical/aws/main.tf`](../../tests/fixtures/terraform-critical/aws/main.tf), [`tests/fixtures/terraform-critical/azure/main.tf`](../../tests/fixtures/terraform-critical/azure/main.tf), [`tests/fixtures/terraform-critical/gcp/main.tf`](../../tests/fixtures/terraform-critical/gcp/main.tf), [`tests/fixtures/terraform-secret/main.tf`](../../tests/fixtures/terraform-secret/main.tf), [`tests/fixtures/terraform-valid/aws/main.tf`](../../tests/fixtures/terraform-valid/aws/main.tf), [`tests/fixtures/terraform-valid/azure/main.tf`](../../tests/fixtures/terraform-valid/azure/main.tf), [`tests/fixtures/terraform-valid/gcp/main.tf`](../../tests/fixtures/terraform-valid/gcp/main.tf) | Maintainer; terraform: each containing fixture directory. None stated. |
| aws | `>= 5.0.0` | [`tests/fixtures/terraform-critical/aws/main.tf`](../../tests/fixtures/terraform-critical/aws/main.tf), [`tests/fixtures/terraform-secret/main.tf`](../../tests/fixtures/terraform-secret/main.tf), [`tests/fixtures/terraform-valid/aws/main.tf`](../../tests/fixtures/terraform-valid/aws/main.tf) | Maintainer; terraform: each containing fixture directory. None stated. |
| aws | `~> 5.0` | [`tests/integration/test-consuming-repo.sh`](../../tests/integration/test-consuming-repo.sh) | Maintainer; Hand: shell generates a temporary manifest. None stated. |
| azurerm | `>= 3.0.0` | [`tests/fixtures/terraform-critical/azure/main.tf`](../../tests/fixtures/terraform-critical/azure/main.tf), [`tests/fixtures/terraform-valid/azure/main.tf`](../../tests/fixtures/terraform-valid/azure/main.tf) | Maintainer; terraform: each containing fixture directory. None stated. |
| google | `>= 5.0.0` | [`tests/fixtures/terraform-critical/gcp/main.tf`](../../tests/fixtures/terraform-critical/gcp/main.tf), [`tests/fixtures/terraform-valid/gcp/main.tf`](../../tests/fixtures/terraform-valid/gcp/main.tf) | Maintainer; terraform: each containing fixture directory. None stated. |

The generated integration consumer's CLI `>= 1.0` and AWS `~> 5.0` constraints
are two additional Hand selections in the shell file above, not manifests
Dependabot can read. The table counts the two CLI spellings and the two AWS ranges separately:
six selections in total.

| Other reference | Snapshot value | Every file | Update / lane |
|---|---|---|---|
| release-please config schema | `v17.6.0` URL | [`release-please-config.json`](../../release-please-config.json) | Hand $schema URL; Maintainer; none stated. |
| Review model selection | `gemini-3.8-flash` fallback; otherwise discovered models | [`.github/scripts/gemini_review.py`](../../.github/scripts/gemini_review.py) | Hand DEFAULT_MODEL constant; Maintainer; none stated. |
| Review API version | `v1beta` in list/generate URLs | [`.github/scripts/gemini_review.py`](../../.github/scripts/gemini_review.py) | Hand URL strings; Maintainer; none stated. |

### Release-managed platform references

Counted as selection families rather than occurrences, this inventory has **61**:
19 action refs (18 active, one commented example), 11 scanner/plugin selections,
seven installed packages, three hook revs (two active, one commented opt-in),
ten runtime/runner selections, six Terraform constraints, three other references
one release family and one documented workaround commit. The two same-commit workflow calls, 15 archive records,
repeated compatibility floors and historical evidence are not additional families.

One release family, snapshot `v3.0.8` / `3.0.8`, is intentionally repeated in
`version.txt`, `.release-please-manifest.json`, workflow defaults, six pre-commit
templates, the scripts pre-commit example, three caller templates and adopter docs.
The precise file set is:
[`.github/workflows/autonomous-fix.yml`](../../.github/workflows/autonomous-fix.yml), [`.github/workflows/reusable-scan.yml`](../../.github/workflows/reusable-scan.yml), [`.release-please-manifest.json`](../../.release-please-manifest.json), [`README.md`](../../README.md), [`docs/APP-CODE-SCANNING.md`](../APP-CODE-SCANNING.md), [`docs/BUMP-THE-SCAN.md`](../BUMP-THE-SCAN.md), [`docs/CONSUMER-MIGRATION.md`](../CONSUMER-MIGRATION.md), [`docs/DEVELOPER-WORKFLOW.md`](../DEVELOPER-WORKFLOW.md), [`docs/HOOK-REFERENCE.md`](../HOOK-REFERENCE.md), [`docs/MULTI-CLOUD.md`](../MULTI-CLOUD.md), [`docs/QUICK-START-5MIN.md`](../QUICK-START-5MIN.md), [`docs/REUSABLE-WORKFLOWS.md`](../REUSABLE-WORKFLOWS.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/TERRAFORM-MODULE-ADOPTION.md`](../TERRAFORM-MODULE-ADOPTION.md), [`docs/TESTING-GUIDE-CONSUMING-REPO.md`](../TESTING-GUIDE-CONSUMING-REPO.md), [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md), [`docs/consumer-repo-setup-guide.md`](../consumer-repo-setup-guide.md), [`scripts/.pre-commit-config.yaml`](../../scripts/.pre-commit-config.yaml), [`templates/aws/pre-commit-config.yaml`](../../templates/aws/pre-commit-config.yaml), [`templates/azure/pre-commit-config.yaml`](../../templates/azure/pre-commit-config.yaml), [`templates/fix-loop/autonomous-fix.yml`](../../templates/fix-loop/autonomous-fix.yml), [`templates/gcp/pre-commit-config.yaml`](../../templates/gcp/pre-commit-config.yaml), [`templates/standard/pre-commit-config.yaml`](../../templates/standard/pre-commit-config.yaml), [`templates/starter/pre-commit-config.yaml`](../../templates/starter/pre-commit-config.yaml), [`templates/strict/pre-commit-config.yaml`](../../templates/strict/pre-commit-config.yaml), [`templates/workflows/code-security-scan.yml`](../../templates/workflows/code-security-scan.yml), [`templates/workflows/terraform-scan.yml`](../../templates/workflows/terraform-scan.yml), [`version.txt`](../../version.txt).
Update: **Release**, using `release-please-config.json`'s `extra-files` and the
existing marked lines; not a freshness target. Historical examples are not active
release pins. Preconditions from [Contributing](../../CONTRIBUTING.md): “Never create a
release tag or a GitHub Release by hand.” From this page: “Review and update these
pins together when upgrading.” `scanning-repo-ref` and `scanning_repo_ref` are Hand
inputs even when Dependabot can read a workflow `uses:` beside them.

The setup guide also offers the fixed post-release workaround commit
`8321adf7020025a5a7a6c7cd8d1780015b18a07a`; it is repeated as historical evidence
in the walkthrough (archived) and
behaviour audit (archived). This Hand docs example is an Maintainer
platform-upgrade decision, counted separately from the release family.
The audit also records `45a4248ad8d7522e6462255c94b3d228f43e1fb2`, while
[Bump the scan](../BUMP-THE-SCAN.md), [Consumer migration](../CONSUMER-MIGRATION.md) and
[Terraform module adoption](../TERRAFORM-MODULE-ADOPTION.md) use
`7cd34a52c823a725575ef3b59ab34e062d1d83dd` solely to anchor historical line numbers.

### Existing bump preconditions

These are existing instructions, quoted without adding a new bump requirement.

- **P1 — review action**, [.github/workflows/claude-code-review.yml](../../.github/workflows/claude-code-review.yml):
  “Re-measure before bumping this pin, and before loosening the guard step above: the
  plugin's `gh pr comment` grant is honoured on every CLI version measured, so the
  PR boundary rests on that guard, not on --allowedTools.” Maintainer lane.
- **P2 — fix action**, [the deliberate bump procedure](../VERSION-PINNING.md#bumping-the-claude-code-action-pin-deliberately):
  “change it in every place listed above together, in the same commit”; “When you
  bump, check the `@anthropic-ai/claude-agent-sdk` version locked in that action
  release's `bun.lock`”; “It must be 1.0.93 or later.” That last floor refers to the
  bundled CLI. The procedure also requires strict validation of all four configs.
- **P3 — Checkov**, [scanner procedure](../VERSION-PINNING.md#scanner-versions-in-the-terraform-scan):
  “choose the `checkov-action` tag whose `action.yml` names the Checkov image you
  want, and pin that tag's commit SHA.” The image
  `ghcr.io/bridgecrewio/checkov:3.4.3` is transitive through the action; it is not
  a container image literal in this repository's workflows.
- **P4 — verified scanner downloads**, [download policy](../VERSION-PINNING.md#release-managed-references-and-verified-downloads):
  “Verify new hashes against the publisher's checksum source before updating this
  lock.” The [Trivy procedure](../VERSION-PINNING.md#scanner-versions-in-the-terraform-scan) says
  “change `TRIVY_VERSION` and `TRIVY_SHA256` together on every `Install Trivy` step”
  and “the `trivy` entry in `scripts/scanner-downloads.json` in the same change”.
- **P5 — TFLint and rulesets**, [scanner procedure](../VERSION-PINNING.md#scanner-versions-in-the-terraform-scan):
  “change `tflint_version:`, and replace `checksums:` with the SHA-256 of
  `tflint_linux_amd64.zip` and `tflint_linux_arm64.zip` from that release's
  `checksums.txt`”; “change the `version` in every `configs/<cloud>/.tflint.hcl`
  that uses the plugin.” The workflow also says “exact pin; bump deliberately”.
- **P6 — Semgrep image**, [.github/workflows/semgrep.yml](../../.github/workflows/semgrep.yml):
  “Dependabot does not update a workflow's container image, so renew the digest
  deliberately.” The comment records “semgrep 1.178.0, resolved 2026-10-07.”
- **P7 — Python environments**, [Getting started](../SETUP-GUIDE.md):
  “If choosing pre-commit instead, keep it in a separate external environment: its
  virtualenv dependency can require a newer `packaging` package than Checkov accepts.”
- **P8 — Snyk**, [scanner procedure](../VERSION-PINNING.md#scanner-versions-in-the-terraform-scan):
  “change the version in `npm install -g snyk@<version>`”; “update the table.”
  The same section notes “npm still resolves that package's own dependencies at run time”.
- **P9 — hook runtime floors**, [Hook reference](../HOOK-REFERENCE.md):
  “Shell hooks require **Bash 4.4 or later**”; “Local hooks require **Python 3.11 or
  newer**, with PyYAML and jsonschema available”. These describe compatibility,
  rather than an exact installed runtime.

- **P10 — Bun**, [.github/workflows/autonomous-fix.yml](../../.github/workflows/autonomous-fix.yml):
  “The agent action would otherwise restore its Bun binary from the Actions cache,
  which a job running the PR's code can write to. Download the release the action
  pins and check it against a recorded SHA-256 instead.” Maintainer runtime lane.

### Versions quoted in docs and captured evidence

Current install strings and runtime floors are listed above, including their docs.
The index below lists every Markdown file repeating another version selection or
historical tool version. It excludes platform release history (the release family
above), network addresses, TLS/data/schema formats and arbitrary fake test versions.
Hand docs sentences follow the same lane as their tool; archived research and
captured evidence stay historical rather than being automatically bumped.

| Quoted version (with or without v prefix) | Every Markdown file at the snapshot |
|---|---|
| `0.15.0` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.26.0` | `docs/ai-research/2-Generic-Scanning-Framework-Design.md` |
| `0.3.177` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.31.0` | `docs/ai-research/2-Generic-Scanning-Framework-Design.md` |
| `0.32.0` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.40.0` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.47.0` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `0.48.0` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md), `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived), `specs/001-security-scanning-spec/plan.md` (archived), `specs/001-security-scanning-spec/research.md` (archived), `specs/001-security-scanning-spec/spec.md` (archived), `specs/001-security-scanning-spec/tasks.md` (archived) |
| `0.49.0` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.50.0` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md), `specs/001-security-scanning-spec/plan.md` (archived), `specs/001-security-scanning-spec/research.md` (archived), `specs/001-security-scanning-spec/spec.md` (archived), `specs/001-security-scanning-spec/tasks.md` (archived) |
| `0.57.0` | `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived) |
| `0.59.1` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `0.64.0` | [`README.md`](../../README.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.65.0` | `docs/SECRET-SCANNER-EVALUATION.md`, [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `0.67.2` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `0.69.3` | `docs/SECRET-SCANNER-EVALUATION.md` |
| `0.71.0` | [`docs/REUSABLE-WORKFLOWS.md`](../REUSABLE-WORKFLOWS.md), `docs/SECRET-SCANNER-EVALUATION.md` |
| `0.75.0` | [`README.md`](../../README.md), `docs/SECRET-SCANNER-EVALUATION.md`, [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-BEHAVIOUR-AUDIT.md`, [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `1.0.93` | [`README.md`](../../README.md), [`docs/AI-AGENT-GUIDE.md`](../AI-AGENT-GUIDE.md), [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), [`docs/FIX-LOOP.md`](../FIX-LOOP.md), `docs/MIGRATION-ANALYSIS.md`, [`docs/ROADMAP.md`](../ROADMAP.md), [`docs/SECURITY-MODEL.md`](../SECURITY-MODEL.md), [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md), `specs/002-scan-fix-platform/spec.md` (archived) |
| `1.0.148` | [`docs/AI-AGENT-GUIDE.md`](../AI-AGENT-GUIDE.md), [`docs/FIX-LOOP.md`](../FIX-LOOP.md), `docs/MIGRATION-ANALYSIS.md`, [`docs/ROADMAP.md`](../ROADMAP.md), [`docs/SECURITY-MODEL.md`](../SECURITY-MODEL.md), [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `1.100.0` | [`docs/REUSABLE-WORKFLOWS.md`](../REUSABLE-WORKFLOWS.md) |
| `1.105.0` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `1.1307.4` | [`docs/REUSABLE-WORKFLOWS.md`](../REUSABLE-WORKFLOWS.md), [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `1.178.0` | [`README.md`](../../README.md) |
| `1.19.9` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `1.28.0` | `docs/ai-research/2-Generic-Scanning-Framework-Design.md` |
| `1.9.0` | `docs/SECRET-SCANNER-EVALUATION.md` |
| `2.0.0-rc.6` | `docs/SECRET-SCANNER-EVALUATION.md` |
| `2.0.930` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `2.1.177` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `3.0.0` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), [`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md), `docs/V3-BEHAVIOUR-AUDIT.md`, `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived), `specs/001-security-scanning-spec/plan.md` (archived), `specs/001-security-scanning-spec/research.md` (archived), `specs/001-security-scanning-spec/spec.md` (archived), `specs/001-security-scanning-spec/tasks.md` (archived) |
| `3.2.1` | `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived) |
| `3.2.437` | `specs/001-security-scanning-spec/build-vs-buy-analysis.md` (archived) |
| `3.3.19` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md`, [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md), [`tests/fixtures/checkov-module-records/README.md`](../../tests/fixtures/checkov-module-records/README.md) |
| `3.6.0` | `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived) |
| `3.6.2` | [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md` |
| `3.29.1` | [`docs/TIER-UPGRADE-GUIDE.md`](../TIER-UPGRADE-GUIDE.md) |
| `4.25.1` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md` |
| `4.3.0` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) |
| `4.1.1` | [`README.md`](../../README.md) |
| `4.2.2` | [`docs/VERSION-PINNING.md`](../VERSION-PINNING.md) |
| `5.6.0` | [`README.md`](../../README.md) |
| `6.0.3` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md), [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md), `docs/V3-WALKTHROUGH-RESULTS.md` |
| `7.6.9` | `docs/SECRET-SCANNER-EVALUATION.md` |
| `7.0.0` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md) |
| `8.18.0` | `specs/001-security-scanning-spec/contracts/cli-interface.md` (archived) |
| `8.19.0` | `docs/SECRET-SCANNER-EVALUATION.md` |
| `8.30.1` | `docs/SECRET-SCANNER-EVALUATION.md`, [`docs/SETUP-GUIDE.md`](../SETUP-GUIDE.md) |
| `8.4.2` | [`README.md`](../../README.md), [`docs/CONTRIBUTING.md`](../../CONTRIBUTING.md) |

Additional evidence-only repeats outside Markdown: Checkov `3.3.19` appears in
[scripts/checkov-consumer-options.py](../../scripts/checkov-consumer-options.py),
[the duplicate-edge fixture](../../tests/fixtures/checkov-consumer-inputs/main.tf),
[fixture capture script](../../tests/fixtures/checkov-module-records/capture.py), its
[`module-calls.json`](../../tests/fixtures/checkov-module-records/module-calls.json),
[`nested-module-calls.json`](../../tests/fixtures/checkov-module-records/nested-module-calls.json),
[`nested.json`](../../tests/fixtures/checkov-module-records/nested.json),
[test_real_module_skips.py](../../tests/python/test_real_module_skips.py) and
[test_scan_integrity.py](../../tests/python/test_scan_integrity.py). Checkov `3.3.8` is
captured in [checkov-baseline-reports.json](../../tests/fixtures/checkov-baseline-reports.json)
and asserted by [test_setup_review_regressions.py](../../tests/python/test_setup_review_regressions.py).
Gitleaks' deprecated-command boundary `8.19.0` is repeated in
[the Bash hook](../../hooks/gitleaks.sh) and [PowerShell hook](../../hooks/gitleaks.ps1).
These are report/behaviour evidence, not installer drift.

The two `.doc` files under `docs/` are archived MIME/HTML documents, not dependency
manifests. `CHANGELOG.md`, `MIGRATION-ANALYSIS.md`, `ROADMAP.md`, the two `specs/`
projects and `docs/ai-research/` retain historical or proposed versions. In particular,
the research design's Kubernetes `v1.28.0` and TFLint plugin examples `0.31.0` /
`0.26.0` are not active configuration. Old Python `3.8+` in both spec quickstarts
and the first spec's plan is historical; the review styleguide still says Python
`3.10+`. Data formats (SARIF `2.1.0`, suppression schema `2.0`, JSON Schema drafts),
CIS benchmark labels and TLS minima are not software freshness pins.

### Drift found (left unchanged)

- `actions/checkout` has three versions: `v4.2.2`, `v6.1.0`, `v7.0.1`; all files
  are listed in the action table. `trivy-action` has `v0.33.1` in the
  fix loop and `v0.36.0` in the reusable scan; the Trivy engine agrees at `0.75.0`.
- The fix action/config mirrors use `v1.0.148`; review/mention workflows use
  `v1.0.233`. These are distinct roles, not proof of a defect; P1 prevents an
  automatic blanket bump of the review workflow.
- Semgrep's reusable app scan defaults to `1.100.0`, while the standalone CI image
  records `1.178.0`. Local hooks have no exact Semgrep install selection.
- [Reusable workflows](../REUSABLE-WORKFLOWS.md) describes the app secret scan as
  Trivy `0.71.0`; its workflow installs `0.75.0`. Its `scanning_repo_ref` table also
  says default `v2.0.0`, while the actual default is release-managed.
- Presentation slides (archived) still show platform `v1.0.0` pins;
  the platform spec quickstart (archived)
  tells readers to confirm `v2.0.0`, while shipped callers are release-managed.
- This page's existing fix-action bump instructions name three tier mirrors but
  also describe docs hits that no longer contain that SHA/version. The file list
  above records actual matches. The unmarked examples are not a new release source.
- Old spec Python `3.8+` and review-styleguide `3.10+` differ from the active local
  hook requirement `3.11+`. These are guidance floors, not CI interpreter pins.

### Dependabot configured here

The inventory remains a snapshot; the active configuration is
[`.github/dependabot.yml`](../../.github/dependabot.yml). See
[How pin updates arrive](#how-pin-updates-arrive) for the schedule and merge rules.

- `github-actions`, directory `/`: covers the external refs under
  `.github/workflows/`, including external reusable workflow refs if added there.
  The two existing local reusable calls need no independent dependency update.
- `pre-commit`, directory `/scripts`: covers the two external hook repositories;
  this repository's own marked hook revision is ignored for release automation.
- `terraform` is not configured here. Candidates are one directory per
  real fixture manifest, because Dependabot does
  not recurse: `/tests/fixtures/terraform-valid`, `/tests/fixtures/terraform-valid/aws`,
  `/tests/fixtures/terraform-valid/azure`, `/tests/fixtures/terraform-valid/gcp`,
  `/tests/fixtures/terraform-critical/aws`, `/tests/fixtures/terraform-critical/azure`,
  `/tests/fixtures/terraform-critical/gcp`, `/tests/fixtures/terraform-secret`.
  The top-level valid fixture has no provider constraint but contains a Terraform
  configuration. Review whether fixture dependency PRs are useful before enabling
  these entries. Generated integration manifests are invisible to it.
- No present `pip`, `npm` or `docker` manifest directories were found. Do not add
  empty ecosystem entries for script install strings or a workflow image literal.
  Hook configs under `templates/{starter,standard,strict,aws,azure,gcp}/` lack the
  supported leading-dot filename and stay hand-kept. The `templates/workflows/`
  and `templates/fix-loop/` caller files are release-managed shipped examples,
  outside the active workflow directory; keep them under release automation.
- The weekly freshness job must cover workflow env/input engine pins, checksum
  pairs and download lock URLs, container digest/version comments, HCL TFLint
  plugins, script `pip`/`npm` constants, runtime inputs/floors, unreadable hook revisions,
  schema URL, model/API constants and docs sentences. It must preserve P1–P10 and
  the release-family exclusion. Conditional action ignores are listed in
  [coverage and exclusions](#coverage-and-exclusions).

Unpinned surfaces also need a deliberate freshness policy: the hosted
`ubuntu-latest` toolchain, local tools already on PATH, the Trivy checks bundle
(downloaded at run time and logged by digest), Semgrep's language registry
rules (`p/csharp`, `p/typescript`), package transitive dependencies, the review plugin marketplace and the
model helper's discovered-model fallback. ESLint, SQLFluff, terraform-docs,
PSScriptAnalyzer, ShellCheck and hadolint have no exact installer pin in this tree;
local hooks or research descriptions naming a tool do not lock its installed version.
The setup warning's
`go install github.com/evilmartians/lefthook@latest` and unversioned package-manager
install advice are floating recommendations, not exact pins.
