# Agent Team Implementation Guide

**Purpose**: Strategy and prompt for implementing the Terraform Security Scanning solution using Claude Code Agent Teams
**Created**: 2026-02-10
**Feature**: [spec.md](spec.md) | [tasks.md](tasks.md) | [plan.md](plan.md)

---

## Table of Contents

- [Why Agent Teams Work for This Project](#why-agent-teams-work-for-this-project)
- [Recommended Team Composition](#recommended-team-composition)
- [Execution Timeline](#execution-timeline)
- [Prerequisites](#prerequisites)
- [The Prompt](#the-prompt)
- [How to Use This Prompt](#how-to-use-this-prompt)
- [Cost Considerations](#cost-considerations)
- [Alternative: Sequential with Subagents](#alternative-sequential-with-subagents)

---

## Why Agent Teams Work for This Project

This project has several characteristics that make agent teams effective:

1. **Natural file boundaries** — hooks/, scripts/, configs/, workflows/, tests/, docs/ have zero overlap
2. **45+ parallel tasks** — after Phase 2, most work fans out independently
3. **Multi-language** — Bash, PowerShell, Python specialists can work simultaneously
4. **Clear dependencies** — Phase 1-2 block, then Phases 3-12 run in parallel

---

## Recommended Team Composition

### 4 Teammates + Lead

| Role | Specialization | Task Count | Owned Files |
|------|---------------|------------|-------------|
| **Lead** | Orchestrator (delegate mode) | 0 (coordinates) | None — uses delegate mode |
| **hooks-engineer** | Bash + PowerShell hooks | 16 tasks | `hooks/**`, `.pre-commit-hooks.yaml` |
| **python-engineer** | Python scripts + JSON schemas | 11 tasks | `scripts/*.py`, `scripts/setup-scanning*.ps1`, `hooks/validate-suppressions.py`, `schemas/**` |
| **infra-engineer** | Cloud configs + workflows + templates | 24 tasks | `configs/**`, `.github/workflows/**`, `templates/**` |
| **quality-engineer** | Fixtures, PS1 scripts, tests, docs, polish | 29 tasks | `tests/**`, `docs/**`, `scripts/*-scan-*.ps1`, `scripts/create-baseline.ps1`, `scripts/profile-*.ps1`, `scripts/generate-*.ps1`, `CHANGELOG.md` |

### Task Distribution Detail

**hooks-engineer (15 tasks)**
- Phase 1: T001 (directory structure), T002 (dispatcher.sh), T003 (common.sh), T004 (common.ps1)
- Phase 2: T007 (hook manifest)
- Phase 4: T014-T023 (5 hook pairs: trivy-iac-critical, trivy-iac-full, trivy-secrets, checkov, checkov-strict)
- Post-v1.0: snyk-iac .sh/.ps1 pair (optional hook, added after initial implementation)

**python-engineer (11 tasks)**
- Phase 1: T005 (unified-results schema), T006 (last-scan schema)
- Phase 3: T011 (setup-scanning.ps1 update), T012 (setup-scanning-no-admin.ps1 update), T013 (setup-scanning.py)
- Phase 4: T024 (validate-suppressions.py hook)
- Phase 7: T037 (validate-suppressions.py full script)
- Phase 9: T043 (scan.py), T044 (Checkov --fix integration)

**infra-engineer (24 tasks)**
- Phase 12: T047-T058 (12 cloud config tasks — all parallel)
- Phase 5: T025-T032 (8 workflow tasks)
- Phase 6: T033-T036 (4 template tasks)

**quality-engineer (29 tasks)**
- Phase 2: T008-T010 (test fixtures)
- Phase 7: T038 (suppression template), T039 (suppression report)
- Phase 8: T040-T042 (metrics scripts)
- Phase 10: T045 (baseline script)
- Phase 11: T046 (performance validation)
- Phase 13: T059-T066 (8 documentation tasks)
- Phase 14: T067-T074 (8 test tasks)
- Phase 15: T075-T079 (5 polish tasks)

---

## Execution Timeline

```
Phase 1-2 (blocking):
  hooks-engineer:   T001-T004, T007 (directory + dispatcher + libs + manifest)
  python-engineer:  T005-T006 (schemas)
  quality-engineer: T008-T010 (fixtures)
  infra-engineer:   [idle — joins at Phase 3]

Phase 3-12 (fan out):
  hooks-engineer:   T014-T023 (11 hook wrappers, all parallel)
  python-engineer:  T011-T013, T024, T037, T043-T044 (setup + validation + scan.py)
  infra-engineer:   T047-T058 (configs) ║ T025-T032 (workflows) ║ T033-T036 (templates)
  quality-engineer: T038-T042, T045, T046 (PS1 scripts + validation)

Phase 13-15 (convergence):
  quality-engineer: T059-T066 (docs) + T067-T079 (tests + polish)
  others:           Help or done
```

---

## Prerequisites

Before running the prompt, ensure:

1. **Enable Agent Teams** — Add to `~/.claude/settings.json`:
   ```json
   {
     "env": {
       "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
     }
   }
   ```

2. **Be on the correct branch**: `git checkout 001-security-scanning-spec`

3. **Spec artifacts exist** in `specs/001-security-scanning-spec/`:
   - spec.md, plan.md, tasks.md, research.md, data-model.md
   - contracts/hook-interface.md, workflow-interface.md, cli-interface.md, suppression-format.md
   - checklists/requirements.md, quality.md

---

## The Prompt

Copy everything between the `---START PROMPT---` and `---END PROMPT---` markers below and paste into a fresh Claude Code session.

---START PROMPT---

```
/speckit.implement

## Implementation Strategy: Agent Team

This project has 92 tasks across 15 phases with 45+ parallel opportunities.
Create an agent team to implement the tasks defined in
`specs/001-security-scanning-spec/tasks.md` using specialized teammates
that work on separate file domains to avoid conflicts.

### Team Structure

Create a team with 4 specialized teammates. Use delegate mode so you (the lead)
focus entirely on coordination — creating tasks, assigning work, monitoring
progress, and unblocking issues. Do NOT implement tasks yourself.

**Teammate 1: hooks-engineer**
- Role: Bash and PowerShell hook development specialist
- Model: Sonnet (cost-effective for scripting tasks)
- Exclusive file ownership: `hooks/**`, `.pre-commit-hooks.yaml`
- Spawn prompt context: "You are the hooks engineer for a Terraform security
  scanning solution. You write dual .sh/.ps1 hook wrappers that share a
  dispatcher architecture. Read `specs/001-security-scanning-spec/contracts/hook-interface.md`
  for the hook contract, and `specs/001-security-scanning-spec/plan.md` for
  project structure. Key patterns: fail-open error handling (exit 1 = findings
  block, all other non-zero = infrastructure warn + allow), JSON output to
  `.scanning/last-scan.json`, Trivy DB retry (capture stderr, grep for
  'database.*locked', wait 2s, retry once), monorepo incremental scanning via
  `detect_changed_dirs()`. ONLY modify files in hooks/ and .pre-commit-hooks.yaml."
- Task assignments (in order):
  - T001: Create hooks/ directory structure
  - T002: Create hooks/dispatcher.sh (OS-detecting dispatcher)
  - T003: Create hooks/lib/common.sh (shared bash functions)
  - T004: Create hooks/lib/common.ps1 (shared PowerShell functions)
  - T007: Update .pre-commit-hooks.yaml (all 9 hook entries, language: script)
  - T014-T015: trivy-iac-critical .sh/.ps1 pair
  - T016-T017: trivy-iac-full .sh/.ps1 pair
  - T018-T019: trivy-secrets .sh/.ps1 pair
  - T020-T021: checkov .sh/.ps1 pair
  - T022-T023: checkov-strict .sh/.ps1 pair

**Teammate 2: python-engineer**
- Role: Python scripting and JSON schema specialist
- Model: Sonnet
- Exclusive file ownership: `scripts/*.py`, `scripts/setup-scanning.ps1`,
  `scripts/setup-scanning-no-admin.ps1`, `hooks/validate-suppressions.py`,
  `schemas/**`
- Spawn prompt context: "You are the Python engineer for a Terraform security
  scanning solution. You build cross-platform Python scripts (3.8+) and JSON
  schemas. Read `specs/001-security-scanning-spec/contracts/cli-interface.md`
  for script contracts, `specs/001-security-scanning-spec/data-model.md` for
  entity schemas, and `specs/001-security-scanning-spec/contracts/suppression-format.md`
  for validation rules. Key patterns: PyYAML for YAML parsing, subprocess for
  tool invocation, exit codes (0=pass, 1=findings, 2=infrastructure error),
  JSON output conforming to schemas/. Python setup script detects OS via
  platform.system() and delegates to appropriate package manager. ONLY modify
  files in scripts/*.py, scripts/setup-scanning*.ps1,
  hooks/validate-suppressions.py, and schemas/."
- Task assignments (in order):
  - T005: Update schemas/unified-results.schema.json
  - T006: Create schemas/last-scan.schema.json
  - T011: Add -CloudProvider to scripts/setup-scanning.ps1
  - T012: Add -CloudProvider to scripts/setup-scanning-no-admin.ps1
  - T013: Create scripts/setup-scanning.py (cross-platform Python setup)
  - T024: Create hooks/validate-suppressions.py (Python validation hook)
  - T037: Create scripts/validate-suppressions.py (full Python rewrite)
  - T043: Create scripts/scan.py (AI agent scanning interface)
  - T044: Add Checkov --fix integration to scan.py

**Teammate 3: infra-engineer**
- Role: Cloud configurations, GitHub Actions workflows, and template specialist
- Model: Sonnet
- Exclusive file ownership: `configs/**`, `.github/workflows/**`, `templates/**`
- Spawn prompt context: "You are the infrastructure engineer for a Terraform
  security scanning solution. You manage cloud-specific configs (AWS/Azure/GCP),
  GitHub Actions reusable workflows, and adoption tier templates. Read
  `specs/001-security-scanning-spec/contracts/workflow-interface.md` for
  workflow contracts, `specs/001-security-scanning-spec/data-model.md` for
  config schemas, and `specs/001-security-scanning-spec/spec.md` sections on
  cloud configs and templates. Key patterns: Checkov BLOCKLIST approach (remove
  check: section, keep only skip-check:), policy-overlay.yaml for org-specific
  rules, SARIF truncation (25MB/5000 results, severity-descending), workflow_call
  trigger with typed inputs/outputs, template tiers (starter=6 hooks,
  standard=+security, strict=+governance). ONLY modify files in configs/,
  .github/workflows/, and templates/."
- Task assignments (in order):
  - T047-T049: Convert .checkov.yaml to blocklist (AWS, Azure, GCP — parallel)
  - T050-T052: Update .tflint.hcl files (AWS, Azure, GCP — parallel)
  - T053-T055: Create policy-overlay.yaml (AWS, Azure, GCP — parallel)
  - T056-T058: Create noisy-checks YAML (AWS, Azure, GCP — parallel)
  - T025: Convert terraform-security-scan.yml to reusable-scan.yml
  - T026: Add apply-suppressions job
  - T027: Add SARIF truncation logic
  - T028: Add Checkov remediation URL generation
  - T029: Add metrics artifact upload
  - T030: Add PR comment generation
  - T031: Create performance-check.yml
  - T032: Update ci.yml
  - T033: Update starter template
  - T034: Update standard template
  - T035: Update strict template
  - T036: Create TIER-UPGRADE-GUIDE.md

**Teammate 4: quality-engineer**
- Role: Test fixtures, PowerShell metrics scripts, testing, documentation, polish
- Model: Sonnet
- Exclusive file ownership: `tests/**`, `docs/**`,
  `scripts/aggregate-scan-results.ps1`, `scripts/collect-scan-metrics.ps1`,
  `scripts/profile-hook-performance.ps1`, `scripts/generate-suppression-report.ps1`,
  `scripts/create-baseline.ps1`, `configs/common/.scan-suppressions.yaml`,
  `CHANGELOG.md`
- Spawn prompt context: "You are the quality engineer for a Terraform security
  scanning solution. You manage test fixtures, PowerShell metrics/governance
  scripts, unit tests (Pester 5+ for PS1, pytest for Python), integration tests,
  documentation, and release polish. Read `specs/001-security-scanning-spec/spec.md`
  for requirements, `specs/001-security-scanning-spec/tasks.md` for task details,
  and `specs/001-security-scanning-spec/plan.md` for project structure. Key
  patterns: test fixtures with known-good and known-bad Terraform per cloud
  provider, Pester Describe/Context/It blocks, pytest with parametrize, 80%
  coverage target, performance thresholds (<5s/hook, <10s pre-commit, <60s
  pre-push). ONLY modify files in tests/, docs/, the specific scripts/*.ps1
  files listed above, configs/common/.scan-suppressions.yaml, and CHANGELOG.md."
- Task assignments (in order):
  - T008: Expand tests/fixtures/terraform-valid/ per provider
  - T009: Create tests/fixtures/terraform-critical/ per provider
  - T010: Verify tests/fixtures/terraform-secret/main.tf
  - T038: Update configs/common/.scan-suppressions.yaml
  - T039: Update scripts/generate-suppression-report.ps1
  - T040: Update scripts/aggregate-scan-results.ps1
  - T041: Update scripts/collect-scan-metrics.ps1
  - T042: Update scripts/profile-hook-performance.ps1
  - T045: Update scripts/create-baseline.ps1
  - T046: Performance validation
  - T059-T066: All documentation (8 tasks, parallel)
  - T067-T074: All tests (8 tasks, parallel)
  - T075-T079: Polish and final validation (5 tasks)

### Task Dependencies & Execution Rules

1. **Phase 1-2 must complete before fan-out**: hooks-engineer owns T001-T004, T007;
   python-engineer owns T005-T006; quality-engineer owns T008-T010. These are
   blocking — no Phase 3+ work starts until Phase 1-2 tasks are done.
2. **Set up task dependencies**: T007 blockedBy [T001]; all Phase 3+ tasks
   blockedBy [T007, T005, T006, T008, T009]; T025-T032 blockedBy [T007];
   docs (T059-T066) blockedBy all implementation tasks they document.
3. **Maximize parallelism**: Within each teammate's assignments, tasks marked [P]
   in tasks.md can execute concurrently. Especially Phase 4 (11 parallel hooks),
   Phase 12 (12 parallel configs), Phase 13 (8 parallel docs), Phase 14 (6
   parallel tests).
4. **MVP checkpoint**: After completing Phases 1-4 + Phase 12 (33 tasks), pause
   for validation. A developer should be able to install scanning and have
   working pre-commit hooks.

### Quality Gates

- After each teammate completes their phase assignments, they should verify:
  - Created files exist and are non-empty
  - Scripts are syntactically valid (bash -n, python -m py_compile, powershell -Command)
  - YAML/JSON files parse without errors
  - Each hook exits 0 against valid fixtures and exits 1 against failing fixtures
- Require plan approval for hooks-engineer and python-engineer (their work is
  foundational — review their approach before they implement)
- infra-engineer and quality-engineer can proceed without plan approval (their
  work is more self-contained)

### Key Design Decisions (from deep interview)

These decisions are already documented in the spec artifacts but are critical
for correct implementation:
- Hooks use `language: script` in .pre-commit-hooks.yaml, NOT `language: python`
- Trivy DB: --skip-db-update in hooks (offline), DB update in CI only
- Configs copied to `.scanning/configs/` in consuming repos via pre-commit cache
- Checkov uses BLOCKLIST approach: all checks run by default, config lists exclusions only
- Baseline matching: (rule_id, file_path) tuple ONLY, line numbers are informational
- Fail-open: exit 1 = security findings (block); all other non-zero = infrastructure error (warn + allow)
- scan.py writes JSON to .scanning/last-scan.json for AI agent consumption
- validate-suppressions is Python (PyYAML), NOT PowerShell
- no-commit-to-branch removed from standard tier
- commitizen is opt-in (commented out) in strict tier
- dispatcher.sh routes to .sh on Unix, .ps1 on Windows via $OSTYPE detection
- Snyk IaC is optional — hooks fail-open when Snyk CLI is not installed or not authenticated. Not included in default scan.py --tools.
```

---END PROMPT---

---

## How to Use This Prompt

### Step 1: Enable Agent Teams

Add to `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Or set the environment variable directly:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

### Step 2: Open a Fresh Session

Open a new Claude Code session in the repository directory:

```bash
cd "C:\Projects\azure-wordpress\auto-code-scanning"
claude
```

### Step 3: Switch to the Feature Branch

Ensure you're on the correct branch:

```bash
git checkout 001-security-scanning-spec
```

### Step 4: Paste the Prompt

Copy everything between `---START PROMPT---` and `---END PROMPT---` and paste it into Claude Code.

### Step 5: Enable Delegate Mode

After the team is created, press `Shift+Tab` to cycle into delegate mode. This ensures the lead focuses on orchestration and doesn't start implementing tasks itself.

### Step 6: Monitor Progress

- **In-process mode** (default on Windows): Use `Shift+Up/Down` to cycle through teammates
- **View a teammate's session**: Press `Enter` on a selected teammate
- **Toggle task list**: Press `Ctrl+T`
- **Message a teammate directly**: Select them with `Shift+Up/Down` and type

### Step 7: MVP Checkpoint

After Phases 1-4 + Phase 12 complete (33 tasks), the lead should pause and report status. At this point, validate that:

- [ ] hooks/ directory has all 12 hook scripts (.sh + .ps1 pairs)
- [ ] .pre-commit-hooks.yaml has all 9 hook entries
- [ ] schemas/ has both JSON schema files
- [ ] configs/ has blocklist .checkov.yaml for all 3 providers
- [ ] A developer can run `setup-scanning.py --cloud-provider aws` successfully

---

## Cost Considerations

Agent teams use significantly more tokens than a single session (4 teammates = ~5x a single session).

### Budget-Conscious Approach

For a phased rollout that minimizes cost:

1. **Phase A** — Start with 2 teammates (hooks-engineer + python-engineer) for Phases 1-4 (MVP core)
2. **Phase B** — Spawn infra-engineer for Phase 12 (configs) + Phase 5 (workflows) after MVP core is done
3. **Phase C** — Spawn quality-engineer for Phases 13-15 (docs, tests, polish) last

### Model Selection

The prompt specifies Sonnet for all teammates. This is the recommended balance of capability and cost. Opus would increase quality but at ~5x the token cost per teammate.

---

## Alternative: Sequential with Subagents

If agent teams feel too experimental or expensive, run `/speckit.implement` without the agent team section. The skill will process tasks sequentially from tasks.md, using subagents for parallelizable tasks within each phase.

**Pros of sequential approach:**
- Simpler coordination
- Lower token cost
- No file conflict risk
- Easier to debug issues

**Cons of sequential approach:**
- Slower (no true parallelism across phases)
- Single context window handles everything
- No specialized focus per domain

### Sequential Prompt (Alternative)

```
/speckit.implement

Start with the MVP scope: Phases 1-4 + Phase 12 (33 tasks).
Follow the dependency graph in tasks.md strictly.
After MVP checkpoint, proceed with remaining phases in order.
Validate each phase checkpoint before continuing.
```

---

## Reference Links

- [Claude Code Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams)
- [Feature Specification](spec.md)
- [Implementation Plan](plan.md)
- [Task List (92 tasks)](tasks.md)
- [Data Model](data-model.md)
- [Hook Interface Contract](contracts/hook-interface.md)
- [Workflow Interface Contract](contracts/workflow-interface.md)
- [CLI Interface Contract](contracts/cli-interface.md)
- [Suppression Format Contract](contracts/suppression-format.md)
- [Quality Checklist (80 items)](checklists/quality.md)
