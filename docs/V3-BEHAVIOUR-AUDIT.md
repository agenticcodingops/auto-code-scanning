# v3.0.0–v3.0.6 behaviour audit

This inventory covers every user-visible change in [CHANGELOG.md](../CHANGELOG.md)
from v3.0.0 through v3.0.6, checked against merged pull requests and implementation
at release commit `45a4248ad8d7522e6462255c94b3d228f43e1fb2`. Release PRs
[58](https://github.com/agenticcodingops/auto-code-scanning/pull/58),
[74](https://github.com/agenticcodingops/auto-code-scanning/pull/74),
[80](https://github.com/agenticcodingops/auto-code-scanning/pull/80),
[88](https://github.com/agenticcodingops/auto-code-scanning/pull/88),
[96](https://github.com/agenticcodingops/auto-code-scanning/pull/96),
[101](https://github.com/agenticcodingops/auto-code-scanning/pull/101) and
[103](https://github.com/agenticcodingops/auto-code-scanning/pull/103) package the
changes below; their version/changelog edits introduce no additional scan behaviour.
The audit used `gh pr list -R agenticcodingops/auto-code-scanning --state merged --limit 60`
and the release Git history. It describes current contracts without reproducing
past security findings.

The follow-up check at commit `8321adf7020025a5a7a6c7cd8d1780015b18a07a`
found one change after that release: [PR 104](https://github.com/agenticcodingops/auto-code-scanning/pull/104)
makes Python setup decode captured tool output as UTF-8 with replacement and
forward it safely to narrower console encodings. It changes setup reliability,
not scan policy. The [Windows setup note](SETUP-GUIDE.md#windows-setup-fix-after-the-current-release)
provides its exact pin until a release contains the fix.

Start adoption with [Getting started](SETUP-GUIDE.md). The README summarizes the
contracts; the references below carry details and migration requirements.

| Release / merged PR | Current user-visible behaviour | Documentation checked or corrected |
|---|---|---|
| 3.0.0 / [55](https://github.com/agenticcodingops/auto-code-scanning/pull/55) | Changed paths retain spaces/newlines through NUL-delimited discovery; scanner operands are separated from options. Incomplete tool runs block by default; local tool-error compatibility is explicit and limited. | README, [hook exit contract](HOOK-REFERENCE.md#exit-code-contract), [architecture](ARCHITECTURE.md) |
| 3.0.0 / [56](https://github.com/agenticcodingops/auto-code-scanning/pull/56) | PR scans use exact base-commit policy; pushes use pushed policy. Schema-2.0 suppressions/baselines approve exact occurrences, including source hash and location; source edits invalidate approval. Secret findings and missing-severity IaC findings participate in the gate. Scanner/report health is mandatory even in report-only mode. SARIF delivery fails by default, with explicit delivery-only tolerance. App-code helper artifacts are unique per call; reviewed IaC mirrors use `scanning-repository`. | README, [migration](CONSUMER-MIGRATION.md#scan-policy-and-occurrence-approval-migration), [suppression governance](SUPPRESSION-GOVERNANCE.md), [workflow reference](REUSABLE-WORKFLOWS.md) |
| 3.0.0 / [59](https://github.com/agenticcodingops/auto-code-scanning/pull/59) | Commit config validation reads the root index blob. Push adapters retain the whole stdin transaction, scan exact object trees without worktree/filter substitution and export reports before cleanup. Unsafe objects, missing tracked policy and invalid config block. The local switch cannot suppress staged config validation. Required checks cover detection, every enabled language and the independent secret scan. | README, [Getting started](SETUP-GUIDE.md), [push migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration), [branch protection](consumer-repo-setup-guide.md#branch-protection) |
| 3.0.0 / [60](https://github.com/agenticcodingops/auto-code-scanning/pull/60) | Downloads verify committed SHA-256 values. Output writes reject linked/reparse paths. Executable formatter/linter inputs are external by default. Report comments render scanner text inertly. Shipped platform references are release-managed tags; consumers resolve full release SHAs and align helpers. | [Getting started](SETUP-GUIDE.md), [trusted-input migration](CONSUMER-MIGRATION.md#trusted-execution-and-output-migration), [version pinning](VERSION-PINNING.md) |
| 3.0.0 / [61](https://github.com/agenticcodingops/auto-code-scanning/pull/61) | Optional fix callers grant the reusable jobs' union: contents/actions read and pull-requests/issues write; individual jobs remain scoped. | [workflow reference](REUSABLE-WORKFLOWS.md), [migration caller](CONSUMER-MIGRATION.md#4-pin-the-callers-and-grant-their-permissions) |
| 3.0.0 / [65](https://github.com/agenticcodingops/auto-code-scanning/pull/65) | The root-level local-hooks boolean is accepted; the global setting takes precedence in push scanning. Applicable hooks write reports, while no-input hooks may pass without a report. | [hook reference](HOOK-REFERENCE.md#json-output), [local toggle](LOCAL-HOOKS-TOGGLE.md) |
| 3.0.0 / [66](https://github.com/agenticcodingops/auto-code-scanning/pull/66) | The installed push adapter respects the alternate configuration recorded by the saved pre-commit runner, preserving unrelated hooks and configuration. | [push migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration) |
| 3.0.0 / [67](https://github.com/agenticcodingops/auto-code-scanning/pull/67) | Executables and trusted inputs stay outside both the temporary snapshot and original consumer. Python 3.11+ is required; isolated search flags retain trusted user-site dependencies. | README, [Getting started prerequisites](SETUP-GUIDE.md#1-prerequisites), [hook reference](HOOK-REFERENCE.md) |
| 3.0.1 / [72](https://github.com/agenticcodingops/auto-code-scanning/pull/72) | Each pushed ref selects changed paths; deleted refs/files do not scan. Both `.tf` and `.tf.json` trigger IaC. TFLint keeps complete context and filters reports to changed paths; C# changes build the complete pushed solution. Unrelated unchanged links do not block file-only scanners, but complete-tree scanners reject links/submodules anywhere in their context. | README, [hook reference](HOOK-REFERENCE.md), [push migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration) |
| 3.0.1 / [71](https://github.com/agenticcodingops/auto-code-scanning/pull/71) | Inline skips require the same file/resource, ID and justification in trusted base policy. Unrelated edits and line shifts preserve supported skips; deleted/new/changed or unsupported-template skips remain findings. Nested local module identity is checked. | [inline migration](CONSUMER-MIGRATION.md#trusted-base-inline-skip-migration), [governance](SUPPRESSION-GOVERNANCE.md#scan-policy-and-occurrence-approval-migration) |
| 3.0.1 / [75](https://github.com/agenticcodingops/auto-code-scanning/pull/75) | Secret-report corruption cannot become a clean result; linked tool boundaries are resolved. Reports include `scan_timestamp`. Baselines handle subdirectory scope and default root output; unconfigured optional lint can be skipped in `all`, but invalid explicit selection blocks. JSON mode emits one stdout document, with progress on stderr; malformed exceptions report incomplete scans. Atomic writes retain permissions and validate output paths at write time. Trusted module-call file renames retain approval where supported. | [hook reports](HOOK-REFERENCE.md#json-output), [baseline migration](CONSUMER-MIGRATION.md#scan-policy-and-occurrence-approval-migration), [consumer tests](TESTING-GUIDE-CONSUMING-REPO.md) |
| 3.0.2 / [78](https://github.com/agenticcodingops/auto-code-scanning/pull/78) | Module-block skips support plain, `count`, `for_each` and nested calls with unchanged literal source and trusted chains. Remote module blocks may be approved, but remote traversal is refused. Ambiguity retains findings. Every explicit SARIF caller ceiling needs `actions: read`, even public/intermediate callers and disabled uploads; private uploads also read run metadata. | [inline migration](CONSUMER-MIGRATION.md#trusted-base-inline-skip-migration), [Getting started CI](SETUP-GUIDE.md#6-configure-ci-callers), [workflow permissions](REUSABLE-WORKFLOWS.md) |
| 3.0.2 / [79](https://github.com/agenticcodingops/auto-code-scanning/pull/79) | New-ref ancestry selection is scoped to direct tracking refs unambiguously owned by the destination's fetch mappings, including negative refspecs. Unknown/ambiguous/unsafe mappings scan reachable ancestry conservatively. Existing refs retain old-to-new selection. On-demand C# builds use configured paths or deep discovery, skip disabled/absent C#, and fail on missing or invalid build inputs. | [hook selection](HOOK-REFERENCE.md), [push migration](CONSUMER-MIGRATION.md#push-object-and-staged-config-validation-migration), [fix-loop on-demand build](FIX-LOOP.md) |
| 3.0.3 / [84](https://github.com/agenticcodingops/auto-code-scanning/pull/84) | Security commit scanners use private captured index snapshots and staged local rules. Python 3.11+ is mandatory before snapshot setup even with tool-error opt-in. Checkov permits passive keys only and receives explicit generated policy. SQLFluff retains a single worktree lint invocation, project macros/templates and ANSI fallback when root config is absent. Reports publish safely. | [Getting started](SETUP-GUIDE.md), [hook reference](HOOK-REFERENCE.md), [application code](APP-CODE-SCANNING.md) |
| 3.0.3 / [85](https://github.com/agenticcodingops/auto-code-scanning/pull/85) | Setup verifies external tools and installs provider policy in `.scanning/configs`; verifier uses the selected runner/tier and exact shipped hook settings. Missing required policy fails. Edit-time secret feedback exposes metadata only. Baseline creation shares occurrence gating and requires complete reports, preserving an existing baseline on failure; explicit policy roots stay external. Allowlist path validation is strict. | README, [Getting started](SETUP-GUIDE.md), [baseline migration](CONSUMER-MIGRATION.md#scan-policy-and-occurrence-approval-migration), [security model](SECURITY-MODEL.md) |
| 3.0.3 / [86](https://github.com/agenticcodingops/auto-code-scanning/pull/86) | Fix tools are confined to the source checkout; trusted helpers/settings/runtime stay outside it. Patch capture accepts supported regular text only and uses no external diff/text conversion. A healthy isolated secret scan is required before patch publication; vetted blobs retain original and neutral filenames for scanning. Verification builds run without secrets; final publication gates/scans the exact tree. The obsolete standalone infrastructure workflow is removed in favour of the reusable path. | README, [fix loop](FIX-LOOP.md), [security model](SECURITY-MODEL.md), [workflow reference](REUSABLE-WORKFLOWS.md) |
| 3.0.3 / [87](https://github.com/agenticcodingops/auto-code-scanning/pull/87) | Hosted Trivy installs download release 0.75.0 from the release assets and verify a pinned SHA-256 before extraction. Scan actions reuse the verified binary; the final fix secret scan also uses this version. | README Local CI parity, [version pinning](VERSION-PINNING.md#release-managed-references-and-verified-downloads) |
| 3.0.4 / [93](https://github.com/agenticcodingops/auto-code-scanning/pull/93) | Staged Terraform scans include indexed sibling context and automatic variable overrides, reporting selected files only. Local rule aliases stay bound to captured policy. Ambiguous paths or malformed reports block even with tool-error opt-in. Index errors include Git diagnostics; allowlist whitespace is preserved exactly. | [hook reference](HOOK-REFERENCE.md), [Getting started first scan](SETUP-GUIDE.md#8-make-the-first-scan-and-commit), [fix gate](SECURITY-MODEL.md#4-the-path-gate-is-an-allowlist-not-a-denylist) |
| 3.0.4 / [94](https://github.com/agenticcodingops/auto-code-scanning/pull/94) | Snapshot launchers/adapters use `-E -P` to retain trusted user packages while excluding checkout/environment imports. Findings-directory and JSON write failures terminate. | [hook prerequisites](HOOK-REFERENCE.md), [Getting started troubleshooting](SETUP-GUIDE.md#11-troubleshooting) |
| 3.0.4 / [95](https://github.com/agenticcodingops/auto-code-scanning/pull/95) | Baseline creation uses shared passive Checkov policy with explicit config and verified absolute scanner/Python paths. Both invoked and canonical identities must stay outside scanned/consumer trees, including environment startup locations. Temporary policy is cleaned on success/failure. | [Getting started baselines](SETUP-GUIDE.md#9-suppressions-and-baselines), [baseline migration](CONSUMER-MIGRATION.md#scan-policy-and-occurrence-approval-migration) |
| 3.0.5 / [100](https://github.com/agenticcodingops/auto-code-scanning/pull/100) | Shared verified resolution runs applications by frozen absolute paths and verifies Python before probes. Checkout-owned tools are refused regardless of tool-error compatibility; external environments retain package identity. Windows launcher selection is verified without executing its candidates; ambiguous selection fails. | [hook reference](HOOK-REFERENCE.md), [Getting started prerequisites](SETUP-GUIDE.md#1-prerequisites) |
| 3.0.5 / [99](https://github.com/agenticcodingops/auto-code-scanning/pull/99) | Shared report writers atomically replace the report with bounded retry for concurrent access; incomplete writes/directories are rejected, temporary files cleaned and old reports preserved on failure. The shared location remains last-writer-wins. | [hook JSON output](HOOK-REFERENCE.md#json-output), [Getting started reports](SETUP-GUIDE.md#8-make-the-first-scan-and-commit) |
| 3.0.6 / [102](https://github.com/agenticcodingops/auto-code-scanning/pull/102) | Bash 4.4+ is checked with an actionable diagnostic; older shell parsing remains compatible enough to reach it. Windows interpreter selection is portable. Report publication also retries transient access-denied errors; fresh path-safety rejection stays terminal. | README prerequisites, [Getting started](SETUP-GUIDE.md), [hook reports](HOOK-REFERENCE.md#json-output) |

## Consolidation decisions

`SETUP-GUIDE.md` is the canonical ordered onboarding path. `QUICK-START-5MIN.md`
points there. `consumer-repo-setup-guide.md` retains branch protection, credentials,
manual inventory and ongoing operations. `ADOPTION-PLAYBOOK.md` retains organizational
rollout criteria and metrics. `TESTING-GUIDE-CONSUMING-REPO.md` is an acceptance-test
reference. Unique operational content is retained in these focused pages or linked
from the canonical guide; no guide file was deleted. Historical specifications and
presentation materials are labelled as historical where their old fail-open model
could otherwise be mistaken for current instructions. Binary presentation documents
are outside this audit's edits.

The module-adoption, multi-cloud, tier-upgrade and scan-bump references also now
point to the canonical path. Their older same-owner policy source, local hook
selection and broad exception examples have been updated to the current contracts.

## Local walkthrough evidence

On 7 November 2026, the Windows path was repeated in a fresh temporary Terraform
consumer with no remote. It used the exact post-release setup-fix pin above,
the standard tier and Lefthook. All 29 recorded command steps exited 0. Setup and
the separate verifier each reported zero failed checks; the optional missing
`.trivyignore` produced a warning. The commit ran configuration validation,
Gitleaks, Trivy secrets, Trivy IaC and Prettier successfully. The on-demand Trivy
scan returned zero findings and `scan_complete: true`.

After the commit, all 61 vendored hook, schema and script files matched the
external platform clone byte for byte, and the consumer working tree was clean.
The guide includes the external formatter ignore rule and LF line-ending rules
needed to retain those bytes. This local proof does not exercise hosted uploads,
branch protection or application-language scanners.
