# Suppression Governance

## Scan policy and occurrence approval migration

Pull-request scans use policy from the exact base commit. Language selection,
scanner configuration and ignore files, the configured suppression registry, and
`.scan-baseline/baseline.json` become effective after their policy change reaches
the protected base. Push scans use the pushed commit. Pin reusable workflows and
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

Source inline skips are not independent approvals. Inline IaC skips remain in
the gate and report; app-code scans disable inline suppression comments. To
retain source inline policy for the policy scanner during migration, trusted
IaC callers can explicitly set `allow-inline-checkov-skips: true` (default
`false`). Explicit caller skip lists and the platform's reviewed cloud
configuration remain supported. IaC findings without severity are treated as
HIGH so missing metadata cannot weaken the gate.

Enabled scanner job failures, missing or invalid reports, parser errors and
report-write failures block completion independently of findings.
`fail-on-findings: false` only relaxes the findings threshold; it never permits
incomplete scans. Hooks also block tool errors by default; the local-only
`SCAN_ALLOW_TOOL_ERRORS=1` explicitly restores warning-only infrastructure errors.
This environment setting does not relax the CI aggregate.

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
