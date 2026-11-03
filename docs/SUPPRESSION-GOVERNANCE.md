# Suppression Governance

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
baseline creation now uses the same identity as local scans and CI. The baseline
keeps a separate entry for each occurrence. Existing broad keys cannot be
automatically converted into an occurrence approval.

During a reviewed migration only, the reusable IaC workflow's
`allow-legacy-exceptions: true`, the local scanner's `--allow-legacy-exceptions`,
or the hook environment `SCAN_ALLOW_LEGACY_EXCEPTIONS=1` explicitly enables schema
`1.0` matching. These are off by default. Approval, date and expiry validation
still apply. HIGH and CRITICAL always require `approved_by`; registry settings
can add approval levels but cannot remove that floor. Severity is required and
approval must cover the actual finding severity. Expiry is capped at 180 days.

An inline Terraform `#checkov:skip=<ID>:<reason>` is honoured when the identical
check ID and justification already exist on the same resource in the same
repository-relative file at the trusted base commit. Reviewed base skips do not
need new schema-2.0 entries. Line shifts and unrelated edits do not revoke them.
Skips added or edited by a pull request (including a changed check ID, reason,
resource or file) remain findings until a schema-2.0 occurrence approval exists
in base policy. Removing a skip leaves the check active; a deleted base comment
cannot suppress a failed check. Missing or ambiguous base identity stays active.
App-code scans continue to disable inline suppression comments.

Local `scripts/scan.py` uses the same matcher. Supply `--policy-root` with a
separate checkout of the exact trusted base for PR parity. Without it, inline
approval is read from Git objects at the current `origin/HEAD` commit
(falling back to `origin/main`); fetch the remote default branch first. An older
merge base cannot restore a skip removed from the current base. If no
base can be resolved, inline skips stay active. Other policy files keep their
existing local defaults. Unsupported inline formats stay active.

Local module instances are matched to their source declarations only when the
same module call names and local source directories exist in base. New/renamed
calls or changed sources cannot borrow a declaration's approval. Remote or
dynamic module sources and ambiguous definitions remain active.

To retain all source inline policy during a reviewed migration, trusted
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


This document establishes the governance framework for managing security scan suppressions in the auto-code-scanning repository.


## Approval lifecycle

Record a specific justification, owner, dates and tracking ticket for each
occurrence. Security reviewers approve HIGH and CRITICAL exceptions before their
registry change enters the protected base. Review the registry quarterly, renew
only after reviewing current source, and remove entries when the finding is fixed.
Move retired entries to `suppression_history` for the audit trail.

The complete field contract and a schema 2.0 example are in
[suppression-format.md](../specs/001-security-scanning-spec/contracts/suppression-format.md).
Run `python scripts/validate-suppressions.py --ci` before committing a registry
change. Local hooks and CI use the same validator; neither can authenticate an
approver identity, so protected-base review remains the authorization boundary.
