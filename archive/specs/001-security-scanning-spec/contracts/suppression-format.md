# Contract: Suppression Format

## Schema 2.0

The active registry is `suppressions.file` in `scan-config.yaml`, or
`.scan-suppressions.yaml` at the repository root when unset. CI loads that path
from the trusted base commit on pull requests. Local hooks validate the same path.

```yaml
schema_version: "2.0"
settings:
  max_expiry_days: 180
  require_security_approval: [CRITICAL, HIGH]
  review_frequency_days: 90
checkov_suppressions:
  - rule_id: "CKV_AWS_19"
    tool: "checkov"
    fingerprint: "v1:<64 lowercase SHA-256 hex characters from the scan report>"
    severity: "HIGH"
    reason: "Reviewed business justification for this occurrence"
    owner: "team@example.com"
    approved_by: "security@example.com"
    approved_date: "2026-11-02"
    expires_date: "2026-12-02"
    ticket: "SEC-123"
    file_pattern: "terraform/*.tf"
trivy_suppressions: []
tflint_suppressions: []
gitleaks_suppressions: []
snyk_suppressions: []
suppression_history: []
```

Required entry fields: `rule_id`, `tool`, `fingerprint`, `severity`, `reason`
(at least 10 characters), `owner`, `approved_date`, and `expires_date`.
`approved_by` is required for HIGH and CRITICAL and any additional levels in
`settings.require_security_approval`. The registry cannot lower that approval
floor. A lower declared severity cannot approve a HIGH/CRITICAL occurrence
without an approver. `file_pattern` and `ticket` are optional.

Trivy entries accept IaC `AVD-*` rule IDs and built-in lowercase secret rule IDs
such as `aws-access-key-id`; both require the same exact fingerprint. Null tool
sections are empty registries. The standalone validator supports `--warning-days`
and the PowerShell wrapper preserves its `WarningDays` parameter.

Dates must be ISO dates. Approval cannot be in the future, expiry cannot precede
approval, and lifetime cannot exceed 180 days (or a stricter configured limit).
The expiry date itself remains valid through that UTC date. CI rejects expired
registries; the local validator warns when expiry checks are requested.

## Occurrence identity v1

`scripts/scan_policy.py` is the canonical implementation used by the workflow,
local scanner and baseline generator. Identity is `v1:` followed by SHA-256 of
UTF-8 canonical JSON (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`)
with these exact keys:

- `tool`, `rule_id`: scanner and rule identifiers.
- `file`: case-sensitive repository-relative path using `/`, with redundant
  segments resolved and the scanner's path convention normalized.
- `resource`: scanner resource address, or the empty string when unavailable.
- `line`, `end_line`: integer range (end defaults to start).
- `content_sha256`: lowercase SHA-256 of complete source file bytes after replacing
  CRLF with LF.

An unreadable/out-of-repository source or absent positive start line produces no
fingerprint and cannot match an exact exception. File edits intentionally require
renewed review. `file_pattern` further limits identity; it never broadens it.
Each suppression or baseline entry is consumed once. Duplicate exact suppression
entries are rejected; baseline records retain multiplicity. Different resources,
locations, files, contents or tools require their own approval.

## Validation

Both `hooks/validate-suppressions.py` and `scripts/validate-suppressions.py` use the
same validator. V-001 covers document/section structure, V-002 schema version,
V-003 required fields, V-004 tool/section agreement, V-005 dates, V-006 expiry,
V-007 mandatory approval, V-008 duplicate occurrence keys, V-009 rule syntax,
and V-010 the versioned fingerprint. CI rejects an invalid registry as a unit.
Warnings cover upcoming expiry, missing tickets and owner email formatting.

## Baseline 2.0

`.scan-baseline/baseline.json` has `schema_version: "2.0"` and an `entries` array.
Every entry contains the same `fingerprint`; descriptive scanner, rule, path,
range, resource and severity fields are retained by the generator. Each record
authorizes one occurrence. Baseline creation and consumption share the Python
identity implementation; consumers must not recompute a rule/path-only key.

## Migration

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
incomplete scans. Local compatibility settings do not relax the CI aggregate.

Hooks validate `suppressions.file` from `scan-config.yaml`, defaulting to the
repository-root `.scan-suppressions.yaml`, exactly as CI does. Downloaded setup
copies are templates rather than an active registry. Re-vendor both `hooks/` and
`scripts/` together; the hook and standalone validators share one implementation.
Python and PyYAML are required for registry validation.
