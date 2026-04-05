# Feature Specification: Reusable Terraform Security Scanning Solution

**Feature Branch**: `001-security-scanning-spec`
**Created**: 2026-02-10
**Status**: Draft
**Input**: User description: "Reusable Terraform Security Scanning Solution - 12 features covering hooks, multi-cloud config, workflows, setup, templates, suppression, metrics, baselines, playbooks, severity normalization, performance CI, and testing infrastructure"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Installs Scanning in Consuming Repo (Priority: P1)

A developer in a consuming Terraform repository wants to add security scanning to their workflow. They run a single setup script, select their cloud provider (AWS, Azure, or GCP), and within 5 minutes have pre-commit hooks catching CRITICAL misconfigurations and secrets on every commit.

**Why this priority**: Without installation, no other feature delivers value. This is the entry point for all adoption.

**Independent Test**: Run `setup-scanning.ps1 -CloudProvider aws` in a fresh repo clone and verify `pre-commit run --all-files` executes Trivy and Checkov hooks.

**Acceptance Scenarios**:

1. **Given** a fresh Terraform repository with no scanning, **When** developer runs `setup-scanning.ps1 -CloudProvider aws`, **Then** pre-commit hooks are installed and `pre-commit run --all-files` executes within 10 seconds
2. **Given** a repository with scanning already installed, **When** developer runs setup again, **Then** the script completes idempotently without errors
3. **Given** a Windows machine without admin rights, **When** developer runs `setup-scanning-no-admin.ps1`, **Then** tools install via Scoop and pip without requiring elevation
4. **Given** a macOS or Linux machine, **When** developer runs `python setup-scanning.py -CloudProvider aws`, **Then** tools install via Homebrew (macOS) or apt (Linux) and hooks activate

---

### User Story 2 - Developer Commits Secure Terraform Code (Priority: P1)

A developer writes Terraform code and commits it. Pre-commit hooks automatically scan for CRITICAL IaC misconfigurations and hardcoded secrets. If issues are found, the commit is blocked with clear remediation guidance. Clean code commits instantly.

**Why this priority**: This is the core value proposition - catching security issues before they reach the shared repository.

**Independent Test**: Commit a Terraform file with a hardcoded AWS secret and verify `trivy-secrets` blocks the commit.

**Acceptance Scenarios**:

1. **Given** a Terraform file with no security issues, **When** developer commits, **Then** all pre-commit hooks pass in under 10 seconds total
2. **Given** a Terraform file with a hardcoded AWS access key, **When** developer commits, **Then** `trivy-secrets` blocks the commit with exit code 1
3. **Given** a Terraform file with a CRITICAL misconfiguration (e.g., open security group), **When** developer commits, **Then** `trivy-iac-critical` blocks the commit
4. **Given** a Terraform file with a HIGH-severity finding only, **When** developer commits, **Then** pre-commit hooks pass (HIGH is caught at pre-push)
5. **Given** a hook infrastructure failure (tool crash, corrupted DB), **When** the hook wrapper detects a non-finding exit code, **Then** the hook exits 0 with a prominent warning (fail-open) instead of blocking the commit

---

### User Story 3 - CI/CD Enforces Security on Pull Requests (Priority: P1)

A DevOps engineer configures their consuming repo to call the reusable GitHub Actions workflow. On every pull request, Trivy and Checkov run automatically, SARIF results upload to the GitHub Security tab, and a summary comment posts on the PR.

**Why this priority**: CI/CD provides the defense-in-depth safety net, catching anything bypassed locally.

**Independent Test**: Open a PR with a Terraform file containing a CRITICAL finding and verify the workflow fails and posts a comment.

**Acceptance Scenarios**:

1. **Given** a consuming repo referencing the reusable workflow, **When** a PR is opened with clean Terraform, **Then** all scan jobs pass and a success comment posts
2. **Given** a PR with CRITICAL/HIGH findings, **When** the workflow runs, **Then** the job fails and SARIF results appear in the Security tab
3. **Given** a consuming repo specifying `cloud-provider: azure`, **When** the workflow runs, **Then** Azure-specific Checkov checks execute
4. **Given** a consuming repo without `security-events: write` permission, **When** the workflow runs with `upload-sarif: false`, **Then** scans execute and PR comment posts without SARIF upload

---

### User Story 4 - Team Adopts Scanning via 90-Day Phased Rollout (Priority: P2)

A team lead follows the adoption playbook to roll out scanning across their team. They start with the starter template (secrets + formatting only) for days 1-30, upgrade to standard (+ linting + CRITICAL checks) for days 31-60, and reach strict (full enforcement) by day 90. Phase timelines are flexible guidelines - teams that miss milestones extend the current phase until criteria are met.

**Why this priority**: Phased adoption reduces developer friction and prevents scanning fatigue. Without it, teams often reject scanning entirely.

**Independent Test**: Install the starter template and verify only secrets + formatting hooks run. Then upgrade to standard and verify additional hooks activate.

**Acceptance Scenarios**:

1. **Given** the starter template installed, **When** developer commits, **Then** only `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `detect-private-key`, `terraform_fmt`, and `trivy-secrets` run
2. **Given** the standard template installed, **When** developer commits, **Then** starter hooks plus `terraform_validate`, `terraform_tflint`, and `trivy-iac-critical` run
3. **Given** the strict template installed, **When** developer pushes, **Then** `trivy-iac-full`, `checkov-strict`, and `validate-suppressions` also run at pre-push

---

### User Story 5 - Security Engineer Manages Suppressions (Priority: P2)

A security engineer needs to suppress a known false positive. They add an entry to `.scan-suppressions.yaml` with required governance fields (rule_id, reason, owner, expiry date). The validation hook enforces that HIGH/CRITICAL suppressions have security team approval and all suppressions expire within 180 days. Approval trust is based on the honor system with git blame providing the audit trail.

**Why this priority**: Without a suppression mechanism, teams either ignore all findings or fork the solution.

**Independent Test**: Add a suppression entry missing the `approved_by` field for a CRITICAL finding and verify the validation script fails.

**Acceptance Scenarios**:

1. **Given** a valid suppression entry with all required fields, **When** `validate-suppressions.ps1` runs, **Then** validation passes
2. **Given** a CRITICAL suppression without `approved_by`, **When** `validate-suppressions.ps1` runs, **Then** validation fails with "requires security team approval"
3. **Given** a suppression with `expires_date` more than 180 days from `approved_date`, **When** validation runs, **Then** a warning is emitted about exceeding maximum duration

---

### User Story 6 - Security Manager Reviews Metrics and Adoption (Priority: P2)

A security manager runs the metrics collection script to check adoption health. They see bypass rate (<5% target), hook pass rate (>80% target), and aggregated findings by severity across tools. Results are normalized to a unified JSON schema. CI workflow run history provides the natural before/after measurement for tracking improvement over time.

**Why this priority**: Metrics demonstrate ROI and identify teams needing support.

**Independent Test**: Run `collect-scan-metrics.ps1` in a repo with commit history and verify JSON output contains bypass_rate and pass_rate fields.

**Acceptance Scenarios**:

1. **Given** a repository with 100 commits, **When** `collect-scan-metrics.ps1` runs, **Then** output includes bypass_rate, hook_pass_rate, and finding counts
2. **Given** scan results from Trivy and Checkov, **When** `aggregate-scan-results.ps1 -RunScans` runs, **Then** findings are normalized to CRITICAL/HIGH/MEDIUM/LOW and output validates against `unified-results.schema.json`

---

### User Story 7 - Developer Baselines Existing Technical Debt (Priority: P3)

A developer adopting scanning on an existing codebase with many pre-existing findings creates a baseline. Subsequent scans only report NEW findings, allowing the team to focus on preventing new issues while gradually addressing debt.

**Why this priority**: Existing codebases often have hundreds of findings. Without baselines, scanning is overwhelming and gets abandoned.

**Independent Test**: Create a baseline, add a new finding, and verify only the new finding is reported.

**Acceptance Scenarios**:

1. **Given** a codebase with existing findings, **When** `create-baseline.ps1 -Tool all` runs, **Then** baseline JSON files are created for Trivy, Checkov, and tflint
2. **Given** a baseline exists, **When** a new misconfiguration is added and scans run, **Then** only findings not in the baseline are reported
3. **Given** a baseline older than 90 days, **When** scans run, **Then** a warning is emitted that the baseline may be stale

---

### User Story 8 - Platform Engineer Validates Hook Performance (Priority: P3)

A platform engineer runs the performance profiler to ensure hooks meet the 5-second-per-hook target. CI also validates performance on every pull request, catching regressions before they reach developers.

**Why this priority**: Slow hooks get bypassed. Performance validation prevents silent degradation.

**Independent Test**: Run `profile-hook-performance.ps1` and verify each hook is measured against the 5-second threshold.

**Acceptance Scenarios**:

1. **Given** hooks installed in a repository, **When** `profile-hook-performance.ps1 -Iterations 3` runs, **Then** output includes average/min/max times per hook and flags any exceeding 5 seconds
2. **Given** CI runs on a PR to this repository, **When** the performance-check job executes, **Then** `trivy-iac-critical` against test fixtures completes in under 5 seconds

---

### User Story 9 - AI Agent Scans and Auto-Fixes Before Committing (Priority: P2)

An AI coding agent (e.g., Claude Code) generates Terraform code and needs to validate it before committing. The agent runs `scan.py --format json` to get structured findings, parses the JSON output to understand issues, invokes Checkov auto-fix for fixable checks, and re-scans to verify fixes before committing autonomously.

**Why this priority**: AI agent workflows are a growing development pattern. Agent-readable output is a differentiator that enables autonomous secure coding workflows.

**Independent Test**: Run `scan.py --format json` on a Terraform file with a fixable Checkov finding and verify the JSON output is machine-parseable with file, line, rule, and severity fields.

**Acceptance Scenarios**:

1. **Given** Terraform code with a fixable Checkov finding, **When** an agent runs `scan.py --format json`, **Then** output is written to `.scanning/last-scan.json` with structured findings array
2. **Given** structured findings from scan.py, **When** an agent invokes `scan.py --auto-fix`, **Then** Checkov `--fix` is applied to fixable checks and remaining unfixable findings are reported
3. **Given** an agent running `git commit`, **When** pre-commit hooks block with findings, **Then** the hook writes structured JSON to `.scanning/last-scan.json` alongside the human-readable terminal summary

---

### Edge Cases

- What happens when Trivy database is not yet downloaded? Setup script initializes it; first scan takes longer.
- What happens when consuming repo has both AWS and Azure Terraform? Setup script configures a single primary provider. Multi-cloud repos MUST manually copy additional provider configs from `configs/{provider}/` and configure per-directory scanning in their `.pre-commit-config.yaml`. This is a documented manual process, not automated.
- What happens when a developer uses `git commit --no-verify`? Bypass is detected by the `bypass-detection.yml` workflow in CI and logged to metrics. Heuristic detection via commit format analysis is sufficient; CI re-scanning is the real enforcement gate.
- What happens when scan tools are not installed? Hook wrapper detects the error (infrastructure failure) and exits 0 with a prominent warning (fail-open). Setup script provides remediation guidance.
- What happens when consuming repo pins to an old version? Solution works but misses new checks. `pre-commit autoupdate` provides opt-in upgrade path.
- What happens when a team upgrades tiers with custom hooks? Templates are copy-once references. Teams manually add the new hooks listed in tier upgrade docs while keeping their customizations intact.
- What happens when Trivy or Checkov crashes (segfault, Python traceback)? Hook wrapper catches infrastructure errors and exits 0 with a warning (fail-open). Only actual security findings (exit code 1 from the scanning tool) block the commit.
- What happens when two Trivy hooks run simultaneously? Hooks run in parallel by default. If a DB lock contention is detected (identifiable via exit code/stderr), the hook automatically retries once before reporting.
- What happens when SARIF output exceeds GitHub's 25MB/5000 result limit? Workflow truncates to highest-severity findings first and adds a warning annotation to the workflow summary.
- What happens when Checkov releases new checks? Blocklist config approach means new checks auto-activate on tool update. A shared exclusion list in this repo filters known-noisy checks.
- What happens when Trivy reclassifies a finding from HIGH to CRITICAL? This is accepted behavior - severity reclassification reflects real-world risk evolution and the system working as intended.
- What happens when a repo has Terraform mixed with application code? Consuming repos configure scan scope via `.scan-config.yaml` to specify which directories to scan and which to exclude.
- What happens in a monorepo with multiple Terraform roots? Hooks detect which Terraform directories contain changed files and only scan those directories, staying within the 5-second budget.
- What happens when a suppression expires? CI workflows immediately treat the finding as active and block. Local hooks warn about the expired suppression but do not block, giving teams time to renew or remediate.

## Requirements *(mandatory)*

### Functional Requirements

#### FEATURE 1: Pre-commit Hook Manifest

- **FR-001**: System MUST define hooks in `.pre-commit-hooks.yaml` consumable by any repo via `repo:` URL reference
- **FR-002**: System MUST provide `trivy-iac-critical` hook scanning for CRITICAL-only IaC misconfigurations at pre-commit stage
- **FR-003**: System MUST provide `trivy-iac-full` hook scanning for CRITICAL, HIGH, MEDIUM findings at pre-push stage
- **FR-004**: System MUST provide `trivy-secrets` hook detecting hardcoded secrets and API keys at pre-commit stage
- **FR-005**: System MUST provide `checkov` hook for CIS Benchmark policy validation at pre-push stage
- **FR-006**: System MUST provide `checkov-strict` hook with hard-fail on CRITICAL/HIGH at pre-push stage
- **FR-007**: System MUST provide `validate-suppressions` hook validating `.scan-suppressions.yaml` at pre-commit stage
- **FR-008**: Each hook MUST specify `id`, `name`, `description`, `entry`, `language`, `files`, and `stages` fields
- **FR-009**: All hooks MUST use `language: script` with pre-installed tools, invoked through `hooks/dispatcher.sh`
- **FR-010**: Hooks MUST set `pass_filenames: false` and use directory-level scanning
- **FR-011**: Consuming repos MUST be able to override any hook `args`, `stages`, `files`, or `exclude` fields in their local `.pre-commit-config.yaml`
- **FR-011a**: Each hook MUST provide both a `.sh` (bash) and `.ps1` (PowerShell) entry script; a thin dispatcher detects the OS and routes to the appropriate script
- **FR-011b**: All Trivy hooks MUST run with `--skip-db-update` flag to ensure speed and offline operation; Trivy DB updates happen only in CI workflows
- **FR-011c**: Hooks MUST run in parallel by default (`require_serial: false`); if a Trivy DB lock contention is detected, the hook MUST automatically retry once before failing
- **FR-011d**: Hook file pattern MUST match all files (not just `\.tf$`) with directory exclusions (`.terraform/`, `node_modules/`, `.git/`); scanning tools determine file relevance
- **FR-011e**: Hooks MUST write structured JSON findings to `.scanning/last-scan.json` in addition to human-readable terminal output, enabling AI agent consumption
- **FR-011f**: Hook output verbosity MUST be configurable via `SCAN_VERBOSE` environment variable; default is summarized output, `SCAN_VERBOSE=1` shows full raw tool output
- **FR-011g**: Hook wrappers MUST implement fail-open for infrastructure errors (tool crash, DB corruption, timeout); only security findings (tool exit code 1) block commits. Infrastructure errors exit 0 with a prominent warning

**Kiro cross-reference**: Req 1, AC 1-28. Fully aligned.

**Gap identified**: Original Kiro Req 1 (AC 1-11) did not specify cross-platform hook wrappers, Trivy DB management, parallel execution, monorepo support, AI agent output, or fail-open error handling. Updated Kiro (AC 12-28) now aligns with FR-011a through FR-011g. Also cross-referenced: Req 15 (Error Recovery) AC 1-5 for fail-open behavior.

#### FEATURE 2: Multi-Cloud Configuration

- **FR-012**: System MUST provide AWS-specific tflint config (`configs/aws/.tflint.hcl`) with `tflint-ruleset-aws` plugin
- **FR-013**: System MUST provide Azure-specific tflint config (`configs/azure/.tflint.hcl`) with `tflint-ruleset-azurerm` plugin
- **FR-014**: System MUST provide GCP-specific tflint config (`configs/gcp/.tflint.hcl`) with `tflint-ruleset-google` plugin
- **FR-015**: System MUST provide AWS Checkov config (`configs/aws/.checkov.yaml`) using a blocklist approach (all checks enabled, config lists exclusions only)
- **FR-016**: System MUST provide Azure Checkov config (`configs/azure/.checkov.yaml`) using a blocklist approach
- **FR-017**: System MUST provide GCP Checkov config (`configs/gcp/.checkov.yaml`) using a blocklist approach
- **FR-018**: System MUST provide cloud-agnostic common configs in `configs/common/` (`.trivyignore`, `.scan-suppressions.yaml`)
- **FR-019**: Cloud-specific configs MUST NOT trigger checks for other cloud providers
- **FR-020**: Trivy IaC scanning and secret detection MUST be cloud-agnostic (no provider-specific config required)
- **FR-021**: All tflint configs MUST include the shared `tflint-ruleset-terraform` plugin for common Terraform rules
- **FR-021a**: Configs MUST be downloaded to `.scanning/configs/` in consuming repos; hooks reference configs via explicit `--config-file` flags, leaving any existing repo-root configs untouched
- **FR-021b**: Config download MUST leverage pre-commit's existing repository clone (from hook installation) by copying configs from the pre-commit cache directory; no separate download mechanism required
- **FR-021c**: The `.scanning/` directory's VCS status (committed vs git-ignored) is a consuming team's choice; documentation MUST describe both approaches
- **FR-021d**: Configs MUST be split into two layers: universal security checks (encryption, public access, logging) and organization-specific policy (tagging, naming conventions). Policy rules reside in a separate overlay file that consuming repos can replace
- **FR-021e**: System MUST maintain a shared known-noisy-checks exclusion list per provider, curated in this repo, that filters checks known to produce excessive false positives
- **FR-021f**: System MUST document the manual process for configuring per-directory scanning in consuming repos with multiple cloud providers

**Kiro cross-reference**: Req 2, AC 1-21. Fully aligned.

**Gap identified**: Kiro does not specify config download mechanism, .scanning/ directory strategy, config layering, or blocklist approach. FR-021a through FR-021e address these based on interview clarifications. FR-021f adds multi-cloud documentation per Kiro AC 21.

#### FEATURE 3: Reusable GitHub Actions Workflows

- **FR-022**: Reusable workflow MUST use `workflow_call` trigger
- **FR-023**: Workflow MUST accept `terraform-directory` input parameter (default: `.`)
- **FR-024**: Workflow MUST accept `severity` input parameter (default: `CRITICAL,HIGH`)
- **FR-025**: Workflow MUST accept `cloud-provider` input parameter
- **FR-026**: Workflow MUST accept `fail-on-findings` boolean input parameter
- **FR-027**: Workflow MUST run Trivy IaC scan and upload SARIF results
- **FR-028**: Workflow MUST run Trivy secret scan and upload SARIF results
- **FR-029**: Workflow MUST run Checkov policy scan and upload SARIF results
- **FR-030**: Workflow MUST run tflint scan
- **FR-031**: Workflow MUST fail on CRITICAL/HIGH findings by default
- **FR-032**: Workflow MUST post a new PR comment summarizing scan results (pass/fail per tool) on each run; previous comments are not updated or collapsed
- **FR-033**: Workflow MUST upload SARIF to GitHub Security tab via `github/codeql-action/upload-sarif`
- **FR-033a**: Workflow MUST accept `upload-sarif` boolean input (default: true); consuming repos without `security-events: write` permission set this to false
- **FR-033b**: Workflow MUST accept `post-pr-comment` boolean input (default: true); consuming repos without `pull-requests: write` permission set this to false
- **FR-033c**: When SARIF output exceeds GitHub's 25MB/5000 result limits, the workflow MUST truncate to highest-severity findings first and add a warning annotation to the workflow summary
- **FR-033d**: Workflow MUST include a dedicated `apply-suppressions` job that reads `.scan-suppressions.yaml`, filters results (removing actively suppressed findings, keeping expired-suppression findings), and produces the final pass/fail determination
- **FR-033e**: Workflow MUST upload metrics JSON as a GitHub Actions artifact for cross-repo aggregation via GitHub API
- **FR-033f**: For Checkov findings, the workflow MUST generate documentation URLs (e.g., `https://docs.checkov.io/docs/{CHECK_ID}`) as remediation links in SARIF and PR comments
- **FR-033g**: For non-Checkov findings, the workflow MUST generate remediation URLs by linking to the tool's documentation index (e.g., `https://avd.aquasec.com/{RULE_ID}` for Trivy, `https://github.com/terraform-linters/tflint/blob/master/docs/rules/` for tflint). When a URL cannot be generated, the `remediation_url` field MUST be set to null

**Kiro cross-reference**: Req 3, AC 1-25. Fully aligned.

**Gap identified**: Kiro does not specify permission-handling inputs, SARIF size limits, CI suppression integration, cross-repo metrics, or remediation links. FR-033a through FR-033f address these.

#### FEATURE 4: Installation & Setup Experience

- **FR-034**: Setup script MUST accept `-CloudProvider` parameter accepting a single value (aws, azure, or gcp); multi-cloud repos configure additional providers manually
- **FR-035**: Setup script MUST install Trivy, Checkov, tflint, pre-commit, and Terraform if not present
- **FR-036**: Setup script MUST copy cloud-specific configs from the pre-commit cache directory (post-hook-install) to `.scanning/configs/` in the consuming repo
- **FR-037**: Setup script MUST install pre-commit hooks (`pre-commit install` and `pre-commit install --hook-type pre-push`)
- **FR-038**: Setup script MUST verify all tool installations and report status
- **FR-039**: Setup script MUST run idempotently without errors on re-execution
- **FR-040**: System MUST provide `setup-scanning.ps1` for Windows with admin rights (Chocolatey)
- **FR-041**: System MUST provide `setup-scanning-no-admin.ps1` for Windows without admin rights (Scoop)
- **FR-042**: Setup MUST validate prerequisites and provide clear remediation guidance for missing dependencies
- **FR-043**: System MUST provide `setup-scanning.py` as a cross-platform Python setup script that detects OS and uses Homebrew (macOS), apt/yum (Linux), or delegates to the PowerShell scripts (Windows)
- **FR-043a**: Setup scripts MUST enforce minimum tool versions (version range, not exact pins): e.g., `trivy>=0.48.0`, `checkov>=3.0.0`, `tflint>=0.50.0`. Newer versions within the range are accepted
- **FR-043b**: PowerShell remains the primary scripting language for Windows-specific scripts. Python is used only for cross-platform entry points (`setup-scanning.py`, `scan.py`)
- **FR-043c**: When a partial tool installation fails (e.g., Trivy installs but tflint fails), the setup script MUST provide error recovery guidance listing what succeeded, what failed, and how to retry

**Kiro cross-reference**: Req 4, AC 1-29. Fully aligned.

**Gap identified**: Kiro specifies Linux (AC 4) and macOS (AC 5) support. FR-043 now provides cross-platform Python setup. FR-043a adds version range enforcement. FR-043b clarifies scripting language strategy. FR-043c adds partial installation failure recovery per Kiro AC 29.

#### FEATURE 5: Tiered Adoption Templates

- **FR-044**: System MUST provide `templates/starter/pre-commit-config.yaml` for days 1-30 (secrets + formatting)
- **FR-045**: System MUST provide `templates/standard/pre-commit-config.yaml` for days 31-60 (+ linting + CRITICAL checks)
- **FR-046**: System MUST provide `templates/strict/pre-commit-config.yaml` for days 61-90 (full enforcement)
- **FR-047**: Starter template MUST include: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `detect-private-key`, `terraform_fmt`, `trivy-secrets`
- **FR-048**: Standard template MUST include all starter hooks plus: `terraform_validate`, `terraform_tflint`, `trivy-iac-critical`
- **FR-049**: Strict template MUST include all standard hooks plus: `terraform_docs`, `trivy-iac-full` (pre-push), `checkov-strict` (pre-push), `validate-suppressions`
- **FR-049a**: The `commitizen` hook MUST be included in the strict template as commented-out with instructions to uncomment; it is opt-in because commit message conventions are a team workflow preference, not a security concern
- **FR-050**: System MUST provide cloud-specific templates in `templates/{aws,azure,gcp}/pre-commit-config.yaml`
- **FR-051**: All templates MUST pin to a specific release tag (e.g., `rev: v1.0.0`)
- **FR-051a**: Templates are copy-once references; tier upgrade documentation MUST list the exact hooks to add for each transition (starter->standard, standard->strict) so teams can merge without losing customizations
- **FR-051b**: Adoption phase timelines (30/60/90 days) are flexible guidelines; teams that miss milestones extend the current phase until criteria are met. There is no mandatory rollback or escalation

**Kiro cross-reference**: Req 5, AC 1-27. Fully aligned.

**Gap identified**: `no-commit-to-branch` removed from standard tier (branch protection is a workflow preference, not security). `commitizen` made opt-in in strict tier. Phase timelines clarified as flexible.

#### FEATURE 6: Suppression Governance

- **FR-052**: System MUST provide `.scan-suppressions.yaml` template with governance fields
- **FR-053**: System MUST require `rule_id`, `tool`, `reason`, `owner`, `approved_date`, `expires_date` fields for each suppression
- **FR-054**: System MUST enforce 180-day maximum expiry from `approved_date`
- **FR-055**: System MUST require `approved_by` field for CRITICAL and HIGH severity suppressions; approval trust is honor-system-based with git blame providing the audit trail
- **FR-056**: System MUST provide `validate-suppressions.ps1` script that checks compliance; suppression validation checks syntax and governance fields only - it does NOT verify that suppressed rule_ids correspond to actual findings in the codebase
- **FR-056a**: Validation script MUST be rewritten in Python (using PyYAML) for cross-platform compatibility; Python is guaranteed available as a dependency of pre-commit and Checkov
- **FR-057**: System MUST provide `generate-suppression-report.ps1` for quarterly audit reporting
- **FR-058**: Validation script MUST detect expired suppressions and duplicate entries
- **FR-058a**: When a suppression has expired, CI workflows MUST treat the finding as active and block on it according to severity thresholds
- **FR-058b**: When a suppression has expired, local pre-commit/pre-push hooks MUST warn about the expired suppression but MUST NOT block the commit/push
- **FR-059**: Validation script MUST validate owner email format
- **FR-060**: Scripts MUST work without modification in consuming repositories

**Kiro cross-reference**: Req 6, AC 1-27. Fully aligned.

**Gap identified**: Kiro specifies pattern matching for cloud-specific rule IDs (AC 13-15). FR-056a adds Python rewrite for cross-platform. Approval trust model and syntax-only validation scope clarified. Expired suppression behavior (AC 24-26) and baseline interaction documentation (AC 27) covered by FR-058a/b and FR-074a.

#### FEATURE 7: Metrics, Performance & Results Aggregation

- **FR-061**: System MUST provide `collect-scan-metrics.ps1` tracking bypass rate, hook pass rate, and finding counts
- **FR-062**: Bypass rate MUST target less than 5% of commits; bypass detection uses heuristic commit format analysis which is sufficient since CI re-scanning is the real enforcement gate
- **FR-063**: Hook pass rate MUST target greater than 80% on first attempt
- **FR-064**: System MUST provide `aggregate-scan-results.ps1` normalizing Trivy, Checkov, and tflint results
- **FR-065**: System MUST provide `profile-hook-performance.ps1` measuring per-hook execution time
- **FR-066**: Aggregated results MUST normalize tool-specific severities to unified CRITICAL/HIGH/MEDIUM/LOW levels
- **FR-067**: Aggregated results MUST output JSON conforming to `schemas/unified-results.schema.json`
- **FR-068**: Metrics script MUST calculate trend data when previous metrics exist
- **FR-068a**: When multiple tools report the same underlying issue (e.g., Trivy and Checkov both flag an unencrypted S3 bucket), the aggregation script MUST deduplicate cross-tool findings by matching on (file, resource, category) and merge into a single finding with a `detected_by` array listing all reporting tools
- **FR-068b**: CI workflows MUST upload metrics JSON as a GitHub Actions artifact; cross-repo aggregation is performed by querying artifacts across repos via GitHub API
- **FR-068c**: The 40% CI security failure reduction target (SC-007) is measured from CI workflow run history; the workflow's pass/fail trend over 90 days provides the before/after measurement without requiring a separate baseline capture

**Kiro cross-reference**: Req 7, AC 1-25. Fully aligned.

**Gap identified**: Kiro does not specify deduplication, cross-repo metrics, or CI-based trend measurement. FR-068a through FR-068c address these.

#### FEATURE 8: Baseline Management

- **FR-069**: System MUST provide `create-baseline.ps1` capturing current scan state
- **FR-070**: Baselines MUST support per-tool creation (Trivy, Checkov, tflint, or all)
- **FR-071**: Baseline metadata MUST include creation timestamp and tools captured
- **FR-072**: System MUST warn when a baseline is older than 90 days
- **FR-073**: System MUST support baseline refresh via `-Force` parameter
- **FR-074**: Subsequent scans SHOULD report only findings not present in the baseline
- **FR-074a**: When a finding matches both a baseline entry and an active suppression, the unified result MUST include both filter reasons (`baseline: true`, `suppressed: true`) independently; neither mechanism overrides the other
- **FR-074b**: Baseline matching MUST use (rule_id, file_path) tuple; line numbers are ignored to be resilient to code refactoring. A finding with the same rule_id in the same file is considered baselined regardless of line number changes
- **FR-074c**: External Terraform modules referenced via remote sources are NOT scanned (Checkov runs with `download-external-modules: false`). This is an accepted tradeoff for speed and offline operation. Modules are assumed to be scanned in their own source repositories
- **FR-074d**: When a baseline is created in a monorepo, the baseline MUST be scoped to specific Terraform modules/directories, not the entire repository

**Kiro cross-reference**: Req 8, AC 1-10. Fully aligned.

**Gap identified**: Kiro does not specify baseline matching algorithm or module scanning scope. FR-074b and FR-074c address these. FR-074d adds monorepo-scoped baselines per Kiro AC 10.

#### FEATURE 9: Adoption Playbook & Champion Guide

- **FR-075**: System MUST provide documentation for 30-day, 60-day, and 90-day adoption phases with milestones
- **FR-076**: System MUST provide champion network guidance documentation
- **FR-077**: System MUST provide troubleshooting guidance for top 10 common issues
- **FR-078**: System MUST reference only verified statistics (NIST 30x, not 100x; IBM $10.22M US average)
- **FR-079**: System MUST NOT reference unverified 100x or 640x cost multipliers
- **FR-080**: System SHOULD provide developer satisfaction survey templates

**Kiro cross-reference**: Req 9, AC 1-10. Fully aligned. No gaps.

#### FEATURE 10: Severity Normalization Reference

- **FR-081**: System MUST define normalized severity mapping for Trivy (CRITICAL/HIGH/MEDIUM/LOW direct mapping)
- **FR-082**: System MUST define normalized severity mapping for Checkov severities
- **FR-083**: System MUST define normalized severity mapping for tflint (ERROR->HIGH, WARNING->MEDIUM)
- **FR-084**: System MUST define normalized severity mapping for PSScriptAnalyzer, ShellCheck, hadolint, and Gitleaks
- **FR-085**: Aggregation scripts MUST apply severity normalization to all findings
- **FR-085a**: Severity reclassification by tool updates (e.g., a finding moving from HIGH to CRITICAL in a newer Trivy version) is accepted behavior reflecting real-world risk evolution; no mitigation or pinning required

**Kiro cross-reference**: Req 11, AC 1-9. Fully aligned.

#### FEATURE 11: Performance Validation in CI

- **FR-086**: CI MUST run timing tests for each hook on every pull request to this repository
- **FR-087**: CI MUST enforce the same 5-second threshold per hook as local; CI (`ubuntu-latest`) is the authoritative measurement environment
- **FR-088**: CI MUST display timing information in CI output
- **FR-089**: Performance regression (hook exceeding threshold) MUST fail the CI check

**Kiro cross-reference**: Req 12, AC 1-4. Fully aligned.

#### FEATURE 12: Testing Infrastructure

- **FR-090**: System MUST provide test fixture at `tests/fixtures/terraform-valid/` that passes all security hooks
- **FR-091**: System MUST provide test fixture at `tests/fixtures/terraform-secret/` containing a hardcoded AWS key
- **FR-092**: System MUST provide test fixtures at `tests/fixtures/terraform-{aws,azure,gcp}-fail/` with provider-specific misconfigurations
- **FR-093**: CI MUST run integration tests using fixtures for all three cloud providers
- **FR-094**: Clean fixtures MUST produce exit code 0 from all scanning tools
- **FR-095**: Fail fixtures MUST produce exit code 1 from Trivy and Checkov
- **FR-096**: Secret fixture MUST trigger `trivy-secrets` detection
- **FR-097**: System SHOULD provide Pester unit tests for PowerShell scripts
- **FR-098**: CI SHOULD target 80% code coverage measured via Pester's `-CodeCoverage` for PowerShell scripts (setup-scanning.ps1, aggregate-scan-results.ps1, collect-scan-metrics.ps1, create-baseline.ps1, generate-suppression-report.ps1, profile-hook-performance.ps1) and `pytest-cov` for Python scripts (scan.py, validate-suppressions.py, setup-scanning.py)

### Test Fixture Expected Outcomes

The following matrix defines the expected exit codes for each fixture-hook combination:

| Fixture | trivy-iac-critical | trivy-iac-full | trivy-secrets | checkov | checkov-strict | validate-suppressions | tflint | gitleaks |
|---------|-------------------|----------------|---------------|---------|----------------|----------------------|--------|----------|
| terraform-valid/aws | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 |
| terraform-valid/azure | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 |
| terraform-valid/gcp | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 0 |
| terraform-critical/aws | Exit 1 | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |
| terraform-critical/azure | Exit 1 | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |
| terraform-critical/gcp | Exit 1 | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |
| terraform-secret/ | Exit 0 | Exit 0 | Exit 1 | Exit 0 | Exit 0 | Exit 0 | Exit 0 | Exit 1 |
| terraform-aws-fail/ | Exit 0* | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |
| terraform-azure-fail/ | Exit 0* | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |
| terraform-gcp-fail/ | Exit 0* | Exit 1 | Exit 0 | Exit 1 | Exit 1 | Exit 0 | Exit 0 | Exit 0 |

*Exit 0 from trivy-iac-critical depends on whether CRITICAL findings are present; if only HIGH/MEDIUM findings exist, exit code is 0.

**Kiro cross-reference**: Req 13, AC 1-11. Fully aligned.

### Non-Functional Requirements

#### Performance

- **NFR-001**: Individual pre-commit hook MUST complete in under 5 seconds
- **NFR-002**: Total pre-commit stage MUST complete in under 10 seconds
- **NFR-003**: Total pre-push stage MUST complete in under 60 seconds
- **NFR-004**: Setup script MUST complete in under 5 minutes (excluding initial Trivy database download)
- **NFR-004a**: Hooks MUST support incremental scanning: detect which Terraform directories contain changed files and only scan those directories, rather than scanning the entire repository

#### Security

- **NFR-005**: All scanning MUST run locally - no code uploaded to external services. Trivy hooks run with `--skip-db-update`; DB updates happen only in CI
- **NFR-006**: Checkov MUST run with `no-guide: true` and `download-external-modules: false` (accepted tradeoff: remote modules not scanned)
- **NFR-007**: Scanning tool versions MUST enforce minimum version ranges (e.g., `trivy>=0.48.0`) to ensure baseline capability while accepting newer versions

#### Usability

- **NFR-008**: Setup MUST require no manual configuration beyond cloud provider selection
- **NFR-009**: Hook failure output MUST provide clear remediation guidance; default is summarized output, configurable to full verbosity via `SCAN_VERBOSE=1` environment variable
- **NFR-010**: All scripts MUST support `-Help` or comment-based help documentation

#### Compatibility

- **NFR-011**: Hooks MUST work with pre-commit framework version 3.0+
- **NFR-012**: Setup scripts MUST support PowerShell 7+ (Windows) and Python 3.8+ (all platforms)
- **NFR-013**: CI workflows MUST run on `ubuntu-latest` runners
- **NFR-013a**: Hook entry scripts MUST work on Windows (PowerShell/Git Bash), macOS (bash/zsh), and Linux (bash) via dual-wrapper architecture

#### AI Agent Compatibility

- **NFR-014**: All hooks MUST write machine-readable JSON findings to `.scanning/last-scan.json` alongside human-readable terminal output
- **NFR-015**: System MUST provide a `scan.py` command that runs all scans and outputs unified JSON results for direct agent consumption, independent of the pre-commit framework
- **NFR-016**: `scan.py` MUST support a `--auto-fix` flag that invokes Checkov's `--fix` for fixable checks, applying remediations automatically and reporting remaining unfixable findings

**Kiro cross-reference**: Req 10 (AI Agent Integration), AC 1-11. Fully aligned. NFR-014 covers AC 8-11 (hook JSON output). NFR-015 covers AC 1-4 (scan.py command). NFR-016 covers AC 5-7 (auto-fix). FR-011e covers AC 8-10 (hook writes JSON on findings). User Story 9 provides full acceptance scenarios.

#### Version Pinning

**Kiro cross-reference**: Req 14 (Version Pinning and Auto-Update), AC 1-4. Fully aligned. FR-051 covers AC 1-2 (pin to release tag). Edge case #5 covers AC 2-3 (old version works, pre-commit autoupdate). See also FR-051a for upgrade documentation.

- **NFR-017**: System MUST document the version pinning mechanism (git tags + `rev:` field) and the upgrade process (`pre-commit autoupdate`) in user-facing documentation

#### Error Recovery

**Kiro cross-reference**: Req 15 (Error Recovery and Resilience), AC 1-9. Fully aligned. FR-011g covers AC 1-5 (infrastructure error handling, fail-open). FR-042 covers AC 3 (remediation guidance). Edge cases #1 and #10 cover AC 6-8 (Trivy DB init, new check auto-activation). FR-085a covers AC 9 (severity reclassification).

### Key Entities

- **Hook**: A pre-commit or pre-push hook entry in `.pre-commit-hooks.yaml` with id, name, entry command (dual .sh/.ps1 wrappers), language, file pattern, and stage. Hooks write JSON to `.scanning/last-scan.json` and support configurable verbosity
- **Cloud Config**: A set of tool-specific configuration files (`.tflint.hcl`, `.checkov.yaml`) in `configs/{provider}/` directories, split into universal security checks and organization-specific policy overlays
- **Adoption Tier**: A `.pre-commit-config.yaml` template in `templates/{starter,standard,strict}/` with progressively more hooks enabled. Phase timelines are flexible guidelines
- **Suppression**: An entry in `.scan-suppressions.yaml` with governance fields (rule_id, tool, reason, owner, dates, approval). Trust is honor-system with git blame audit trail. Syntax-validated only (no cross-reference to actual findings)
- **Baseline**: A snapshot of current scan findings stored in `.scan-baseline/` used to filter known issues. Matching uses (rule_id, file_path) tuple - line numbers are ignored for refactoring resilience
- **Unified Result**: A normalized JSON finding conforming to `schemas/unified-results.schema.json` with tool, severity, file, line, and `detected_by` array for cross-tool deduplication. Includes `baseline` and `suppressed` boolean flags
- **Metric**: A JSON measurement of adoption health (bypass rate, pass rate, finding counts) stored in `.scan-results/metrics/` and uploaded as GitHub Actions artifacts for cross-repo aggregation
- **Scan Config**: A `.scan-config.yaml` file in consuming repos that specifies scan scope (directories to include/exclude), enabling repos with mixed Terraform and application code to control what gets scanned
- **Agent Report**: Structured JSON output at `.scanning/last-scan.json` produced by both hooks and `scan.py`, designed for machine consumption by AI coding agents. Includes file, line, rule_id, severity, and remediation URL
- **Policy Overlay**: Organization-specific policy rules (tagging, naming) separated from universal security checks in config files. Consuming repos replace the policy overlay to match their organization's standards
- **Scanning Directory**: The `.scanning/` directory in consuming repos containing downloaded configs (`configs/`), scan results (`last-scan.json`), and baseline data. VCS status (committed vs git-ignored) is a team choice

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Consuming repos complete setup in under 5 minutes using a single script on Windows, macOS, or Linux
- **SC-002**: Pre-commit hooks complete in under 10 seconds for typical Terraform commits
- **SC-003**: Hook bypass rate stays below 5% across consuming repositories (measured via CI artifact aggregation)
- **SC-004**: Hook pass rate exceeds 80% on first attempt across consuming repositories
- **SC-005**: All three cloud providers (AWS, Azure, GCP) have complete configuration coverage
- **SC-006**: Test fixtures achieve 100% expected-outcome accuracy (clean passes, fail fixtures fail, secrets detected)
- **SC-007**: Consuming repos achieve 40% reduction in CI security failures within 90 days of adoption (measured from CI workflow run history trend)
- **SC-008**: All hooks produce identical pass/fail outcomes whether run locally or in CI (defense-in-depth parity); performance thresholds are measured authoritatively in CI
- **SC-009**: AI agents can parse scan output from `.scanning/last-scan.json` and auto-fix at least Checkov-fixable findings without human intervention

## Clarifications

### Session 2026-02-10 (speckit.clarify)

- Q: How should a consuming repository with multiple cloud providers (e.g., AWS + Azure in the same repo) be handled? → A: Single primary provider selected at setup; multi-cloud repos must manually copy additional provider configs and configure per-directory scanning. This is documented but not automated.
- Q: When a finding exists in both the baseline AND has an active suppression, which mechanism takes precedence? → A: Both evaluated independently; finding marked with all applicable filter reasons (`baseline`, `suppressed`, or both) in unified results JSON. Neither mechanism overrides the other.
- Q: Should the 5-second performance threshold apply identically to both local developer machines and CI runners? → A: Same 5-second threshold for both; CI (`ubuntu-latest`) is the authoritative measurement environment. No separate CI threshold.
- Q: When a team upgrades from one adoption tier to the next, how should custom hook configurations be preserved? → A: Templates are copy-once references; teams manually merge new hooks from the next tier template into their existing config. Upgrade documentation lists exactly which hooks to add per tier transition.
- Q: When a suppression expires, should the previously-suppressed finding immediately block commits/CI, or is there a grace period? → A: Immediate block in CI only; expired suppressions fail CI workflows but local hooks warn without blocking, giving teams time to renew or remediate.

### Session 2026-02-10 (deep interview - 30 decisions)

- Q: What shell should hook entry scripts target? → A: Dual wrapper - each hook has both .sh and .ps1 entry scripts with an OS-detecting dispatcher
- Q: How should Trivy DB freshness be managed? → A: Hooks run with --skip-db-update for speed; CI workflows always pull the latest DB
- Q: How should configs be stored in consuming repos? → A: Downloaded to `.scanning/configs/`; hooks reference via explicit --config-file flags; existing repo-root configs untouched
- Q: Should the spec address monorepo scanning? → A: Yes - hooks detect which Terraform directories have changed files and scan only those (incremental scanning with dependency awareness)
- Q: Should Checkov download external modules? → A: No - accepted tradeoff for speed/offline operation. Modules assumed scanned in their source repos
- Q: Should hooks run in parallel or serial? → A: Parallel + retry. Default parallel execution; auto-retry once on Trivy DB lock contention
- Q: How should suppression approval be verified? → A: Honor system. Git blame provides audit trail. No cryptographic verification
- Q: How should baseline findings be matched? → A: Match on (rule_id, file_path) only. Line numbers ignored for refactoring resilience
- Q: How strict should tool version pinning be? → A: Version ranges with minimums (e.g., trivy>=0.48.0). Not exact pins
- Q: What happens when SARIF exceeds GitHub limits? → A: Truncate to highest-severity findings + warning annotation
- Q: How reliable does bypass detection need to be? → A: Heuristic is sufficient. CI re-scanning is the real enforcement
- Q: What happens if a team fails adoption milestones? → A: Flexible timeline. Phases are guidelines, not deadlines
- Q: Should Checkov use allowlist or blocklist? → A: Blocklist - all checks run by default, config lists exclusions only. New checks auto-activate on update
- Q: How should PR comment management work? → A: New comment always. No update/collapse of previous comments
- Q: Should validate-suppressions require powershell-yaml? → A: Rewrite in Python (PyYAML) for cross-platform support. Python is guaranteed by pre-commit/Checkov dependency
- Q: How should severity classification drift be handled? → A: Accept as feature. Reclassification reflects real-world risk evolution
- Q: How should permission-dependent workflow features be handled? → A: Boolean inputs (upload-sarif, post-pr-comment) defaulting to true. Consuming repos explicitly opt out
- Q: How should remediation be provided for Checkov findings? → A: Auto-generate Checkov docs URLs (e.g., docs.checkov.io/docs/CHECK_ID) as remediation links
- Q: Should file patterns be expanded beyond .tf? → A: Match all files; exclude directories (.terraform/, node_modules/). Let scanning tools decide relevance
- Q: Should no-commit-to-branch be in standard tier? → A: Remove. Branch protection is workflow preference, not security scanning
- Q: Should tools be isolated per-repo? → A: Global install is fine. Version conflicts rare with range enforcement
- Q: How should pre-adoption metrics baseline be captured? → A: CI workflow run history provides natural before/after. No separate capture needed
- Q: Should there be a shared noisy-checks exclusion list? → A: Yes. Maintained in this repo per provider. Teams inherit curation
- Q: How should cross-platform setup work? → A: Python setup script (setup-scanning.py) detecting OS. Homebrew for macOS, apt for Linux, delegates to PS on Windows
- Q: What output format for AI agent consumption? → A: JSON to .scanning/last-scan.json + human summary to terminal. Agents read the JSON file
- Q: Should there be an explicit agent mode? → A: Both paths. Pre-commit hooks for git operations + scan.py for direct agent invocation
- Q: Should scan.py provide fix suggestions? → A: Leverage Checkov's --fix flag for auto-remediation of fixable checks. Report remaining unfixable findings
- Q: Should new concepts be formalized as entities? → A: Formalize all: Scan Config, Agent Report, Policy Overlay, Scanning Directory
- Q: Should AI agent integration be a new feature? → A: Fold into existing features as enhancements. No separate Feature 13
- Q: Should all scripts migrate to Python? → A: Keep PowerShell primary for Windows. Python only for cross-platform entry points (scan.py, setup-scanning.py)

## Current Implementation Status

| Feature | Status | Key Gaps |
|---------|--------|----------|
| Pre-commit Hook Manifest | Migrated, functional | Missing dual .sh/.ps1 wrappers, no JSON output, no fail-open, no parallel retry |
| Multi-Cloud Configuration | Complete for all 3 providers | Allowlist approach (needs blocklist conversion), no config layering, no .scanning/ dir strategy, no multi-cloud docs |
| Reusable GitHub Workflows | Migrated, NOT converted to `workflow_call` | Hardcoded `terraform/` path, no input parameters, no permission inputs, no suppression step |
| Installation & Setup | Admin script complete, no-admin complete | No `-CloudProvider` parameter, no Python cross-platform script, no version range enforcement, no partial failure recovery |
| Tiered Adoption Templates | Complete (starter, standard, strict) | `no-commit-to-branch` needs removal from standard, `commitizen` needs comment-out in strict |
| Suppression Governance | Scripts complete | No Python rewrite for cross-platform, no rule_id pattern validation |
| Metrics & Performance | Scripts complete | No cross-tool deduplication, no CI artifact upload, no trend calculation from CI history |
| Baseline Management | Script creates baselines | Baseline comparison not implemented, matching algorithm not coded, no monorepo scoping |
| Adoption Playbook | Docs exist (ADOPTION-PLAYBOOK.md, CHAMPION-GUIDE.md) | Survey templates not provided |
| Severity Normalization | Doc exists, basic mapping in scripts | Full mapping for all 7 tools not codified |
| Performance CI Validation | Basic timing for trivy-iac-critical only | Missing timing for all other hooks |
| Testing Infrastructure | Fixtures exist for all providers + clean + secret | No Pester tests, no coverage measurement |
| AI Agent Integration | Not started | scan.py, JSON output, auto-fix mode all new |
| Cross-Platform Support | PowerShell only | setup-scanning.py, dual hook wrappers, Python validation all new |
| Version Pinning | Partial (templates pin tags) | No version pinning/upgrade documentation |
| Error Recovery | Partial (setup validates prereqs) | No fail-open hook wrappers, no partial install recovery |

## Kiro Requirements Gap Analysis

### Kiro Requirements Summary (15 Total)

| Kiro Req | Name | ACs | Spec Coverage |
|----------|------|-----|---------------|
| Req 1 | Pre-commit Hook Manifest | 28 | FR-001–FR-011g, NFR-004a |
| Req 2 | Multi-Cloud Configuration | 21 | FR-012–FR-021f |
| Req 3 | Reusable GitHub Actions Workflows | 25 | FR-022–FR-033f |
| Req 4 | Installation & Setup Experience | 29 | FR-034–FR-043c |
| Req 5 | Tiered Adoption Templates | 27 | FR-044–FR-051b |
| Req 6 | Suppression Governance | 27 | FR-052–FR-060 |
| Req 7 | Metrics, Performance & Results Aggregation | 25 | FR-061–FR-068c |
| Req 8 | Baseline Management | 10 | FR-069–FR-074d |
| Req 9 | Adoption Playbook & Champion Guide | 10 | FR-075–FR-080 |
| Req 10 | AI Agent Integration | 11 | NFR-014–NFR-016, FR-011e |
| Req 11 | Severity Normalization | 9 | FR-081–FR-085a |
| Req 12 | Performance Validation in CI | 4 | FR-086–FR-089 |
| Req 13 | Testing Infrastructure | 11 | FR-090–FR-098 |
| Req 14 | Version Pinning and Auto-Update | 4 | FR-051, NFR-017, Edge cases |
| Req 15 | Error Recovery and Resilience | 9 | FR-011g, FR-042, FR-085a |

### Requirements Fully Covered by Kiro (No Gaps)

- Requirement 1: Pre-commit Hook Manifest (28 ACs → all covered)
- Requirement 2: Multi-Cloud Configuration (21 ACs → all covered)
- Requirement 3: Reusable GitHub Actions Workflows (25 ACs → all covered)
- Requirement 4: Installation & Setup Experience (29 ACs → all covered)
- Requirement 5: Tiered Adoption Templates (27 ACs → all covered)
- Requirement 6: Suppression Governance (27 ACs → all covered)
- Requirement 7: Metrics, Performance & Results Aggregation (25 ACs → all covered)
- Requirement 8: Baseline Management (10 ACs → all covered)
- Requirement 9: Adoption Playbook & Champion Guide (10 ACs → all covered)
- Requirement 10: AI Agent Integration (11 ACs → all covered)
- Requirement 11: Severity Normalization (9 ACs → all covered)
- Requirement 12: Performance Validation in CI (4 ACs → all covered)
- Requirement 13: Testing Infrastructure (11 ACs → all covered)
- Requirement 14: Version Pinning and Auto-Update (4 ACs → all covered)
- Requirement 15: Error Recovery and Resilience (9 ACs → all covered)

### Implementation Gaps (Spec vs Current State)

| Gap | Feature | Description | Spec Requirement |
|-----|---------|-------------|------------------|
| G-001 | F1: Hooks | `pass_filenames: false` is critical for directory-scanning tools | FR-010 |
| G-002 | F2: Multi-Cloud | Common Terraform rules shared across all provider configs | FR-021 |
| G-003 | F3: Workflows | SARIF upload for secret scanning (only IaC/Checkov mentioned) | FR-028 |
| G-004 | F3: Workflows | Current workflow NOT converted to `workflow_call` trigger | FR-022 |
| G-005 | F4: Setup | No `-CloudProvider` parameter in setup scripts | FR-034 |
| G-006 | F4: Setup | No Linux/macOS support (PowerShell-only) | FR-043 |
| G-007 | F6: Suppression | No rule_id pattern validation (CKV_AWS_*, etc.) | Noted in Kiro AC 13-15 |
| G-008 | F7: Metrics | Schema validation not enforced at runtime | Noted in Kiro AC 18 |
| G-009 | F8: Baseline | Baseline comparison not implemented in aggregation | FR-074 |
| G-010 | F11: Perf CI | Only `trivy-iac-critical` timed; other hooks not timed | FR-086 |
| G-011 | F12: Testing | No Pester tests or coverage measurement | FR-097, FR-098 |
| G-012 | F1: Hooks | No cross-platform hook wrappers (.sh/.ps1 dual entry) | FR-011a |
| G-013 | F1: Hooks | No AI agent JSON output from hooks | FR-011e |
| G-014 | F1: Hooks | No fail-open error handling for infrastructure failures | FR-011g |
| G-015 | F2: Config | No config layering (security vs org policy) | FR-021d |
| G-016 | F3: Workflows | No CI suppression integration step | FR-033d |
| G-017 | F4: Setup | No cross-platform Python setup script | FR-043 |
| G-018 | F7: Metrics | No cross-tool finding deduplication | FR-068a |
| G-019 | F8: Baseline | No baseline matching algorithm specified | FR-074b |
| G-020 | All | No AI agent scan command (scan.py) | NFR-015, NFR-016 |
| G-021 | F2: Config | No documentation for multi-cloud manual scanning process | FR-021f |
| G-022 | F4: Setup | No partial installation failure recovery guidance | FR-043c |
| G-023 | F8: Baseline | No monorepo-scoped baseline support | FR-074d |
| G-024 | F14: Version | No version pinning/upgrade documentation | NFR-017 |

## Assumptions

- Consuming repos use the pre-commit framework (Python-based) for hook management
- Developers have Python 3.8+ available (required for pre-commit and Checkov)
- GitHub is the CI/CD platform (GitHub Actions workflows)
- Windows is the primary developer OS; macOS and Linux are supported via Python cross-platform scripts
- Scanning tools (Trivy, Checkov, tflint) are free, open-source, and run locally without requiring paid licenses
- The NIST 30x cost multiplier is the authoritative statistic for shift-left business cases (per research validation)
- Consuming repos have internet access during initial setup (for tool installation and Trivy DB download)
- Pre-commit stage runs on every `git commit`; pre-push stage runs on every `git push`
- AI coding agents (e.g., Claude Code) can read JSON files and execute Python/shell commands
- Global tool installation is acceptable; per-repo tool isolation (Docker, venv) is not required
- Checkov's built-in `--fix` flag provides reliable auto-remediation for a subset of checks
- Remote Terraform modules are scanned in their own source repositories; this repo does not scan remote module code

## Dependencies

| Feature | Depends On | Reason |
|---------|-----------|--------|
| F3: Workflows | F1: Hooks | Workflows mirror local hook capabilities |
| F3: Workflows | F2: Multi-Cloud | Workflows need cloud-specific Checkov configs |
| F4: Setup | F1: Hooks, F2: Multi-Cloud | Setup downloads hooks and configs |
| F5: Templates | F1: Hooks | Templates reference hook IDs |
| F5: Templates | F2: Multi-Cloud | Cloud-specific templates need configs |
| F6: Suppression | F1: Hooks | `validate-suppressions` is a hook |
| F7: Metrics | F1: Hooks | Metrics track hook execution data |
| F7: Metrics | F10: Severity | Aggregation uses severity normalization |
| F8: Baseline | F7: Metrics | Baselines compare against aggregated results |
| F11: Perf CI | F1: Hooks, F12: Testing | Perf CI uses test fixtures to time hooks |
| F12: Testing | F1: Hooks, F2: Multi-Cloud | Tests validate hooks against cloud-specific fixtures |
| AI Agent (scan.py) | F1: Hooks, F7: Metrics | scan.py reuses hook scanning logic and aggregation |
| Cross-Platform (setup.py) | F4: Setup | Python setup wraps existing PowerShell setup logic |
