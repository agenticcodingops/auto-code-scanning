# Adoption Playbook

Research-backed phased approach to rolling out the security scan→fix platform across the organization.

## A Two-Layer Platform

As of v2.0.0 this is a reusable **two-layer platform**, not just a Terraform scanner.
Roll the layers out **independently** — Layer A first, Layer B only when a team is
ready for autonomous code changes.

| Layer | What it is | Rollout |
|-------|------------|---------|
| **Layer A — Scanning** | Detects issues across **Terraform *and* app-code** (C#/.NET, TypeScript/JS, SQL). Runs locally (Lefthook by default, or pre-commit) and in CI (SARIF to the Security tab). Security scanners report findings; formatters may edit code and build hooks execute project logic. | The tiered path below (starter → standard → strict) governs **Layer A** adoption. |
| **Layer B — Agentic fix-loop** | **Optional, opt-in, off by default.** An agent proposes a minimal fix: *in-session* via the Claude Code bundle (`templates/claude/`), and *in CI* via the hardened `autonomous-fix.yml` (opt-in per PR with the `ai-autofix` label). | Layered **on top of** a mature Layer A — see [Layer B: Enabling the Fix-Loop](#layer-b-enabling-the-fix-loop). |

Install through [Getting started](SETUP-GUIDE.md), then use this page to plan
team rollout. Tier defaults and actual runner manifests differ; use the canonical
guide and [tier reference](TIER-UPGRADE-GUIDE.md) when deciding what to enable.

## Rollout Philosophy

The three tiers (starter, standard, strict) provide a progressive path from minimal friction to full enforcement of **Layer A scanning**. The timelines below are **guidelines, not deadlines** -- teams should advance when they meet the criteria for each phase, regardless of calendar time. **Layer B (the fix-loop) is a separate, opt-in decision** layered on a mature Layer A, covered after the tiers.

## Phase 1: Starter Tier

**Goal**: Build developer confidence with minimal friction

### Scope

Start with the runner and starter configuration from Getting started. The Terraform
pre-commit starter contains the Trivy secret gate, private-key detection and
formatting; Lefthook has a broader fixed manifest. Do not promise identical hook
sets merely because both installations are called starter.

### Rollout Steps

1. Identify 3-5 advocate developers who will champion the tool
2. Deploy starter tier to their repositories
3. Run for at least 2 weeks before measuring
4. Collect feedback via [developer survey](DEVELOPER-SURVEY.md)

### Transition Criteria (Move to Standard)

- Hook pass rate >95% (most commits pass without changes)
- Zero complaints about hook speed (<10s pre-commit total)
- Developer feedback is neutral-to-positive
- At least 3 successful weeks of usage

## Phase 2: Standard Tier

**Goal**: Add meaningful security value with broader coverage

### Upgrade

See [TIER-UPGRADE-GUIDE.md](TIER-UPGRADE-GUIDE.md) for step-by-step upgrade instructions.

### Scope

Review the standard manifest changes in [tier upgrades](TIER-UPGRADE-GUIDE.md).
Enable each new scanner only after prerequisites and trusted policy are provisioned.

### Rollout Steps

1. Create a reviewed schema-2.0 baseline using [Getting started](SETUP-GUIDE.md#9-suppressions-and-baselines).
2. Upgrade advocate repos to standard tier
3. Expand to 50%+ of Terraform developers
4. Monitor metrics via `.\scripts\collect-scan-metrics.ps1`
5. Set up CI/CD integration with the reusable workflow

### Transition Criteria (Move to Strict)

- Bypass rate <10% (developers rarely skip hooks)
- Hook pass rate >80%
- CI failure rate reduced vs. pre-scanning baseline
- Suppression governance process established
- At least 4 weeks of standard tier usage

## Phase 3: Strict Tier

**Goal**: Full security enforcement for mature teams

### What's Added

| Hook | Stage | What It Does |
|------|-------|-------------|
| checkov-strict | pre-push | Hard-fail on CRITICAL + HIGH findings |

### Rollout Steps

1. Upgrade to strict tier in advocate repos first
2. Expand to 90%+ developer adoption
3. Enable suppression validation in CI
4. Run quarterly suppression reviews
5. Conduct developer satisfaction survey

### Success Criteria

- Bypass rate <5%
- CI failures reduced 40% vs. pre-scanning baseline
- All suppressions have valid business justification
- Developer satisfaction >3.5/5.0

## Layer B: Enabling the Fix-Loop

Layer B is **optional and opt-in**. Treat it as a deliberate, separate rollout on
top of a team that already trusts Layer A scanning — not a tier upgrade. There are
two independently adoptable surfaces:

### Surface 1: In-session self-correction (lowest risk)

The Claude Code bundle (`templates/claude/`, installed as `.claude/`) scans an
agent's edits **inside the session** and lets Claude self-correct before anything is
committed. **PostToolUse** scans each edited file by language (Semgrep `p/csharp` /
`p/typescript`) plus a secret check and exits `2` to feed findings back; **Stop**
runs the shared `scan-and-fix` secret gate as a final check (guarded by
`stop_hook_active`, so it blocks at most once). No PR or push credential is needed; the session still runs with the developer's local permissions and needs trusted tools and configuration.

### Surface 2: CI fix-loop (`autonomous-fix.yml`)

Off by default. Enable it deliberately, per repo, once Layer A is mature:

1. Set `fix_loop.enabled: true` in `scan-config.yaml`.
2. Tune `fix_loop.allowlist_paths` (only these dirs are ever auto-fixed) and confirm
   `fix_loop.gated_paths` covers your security-sensitive areas (`auth`, `payment`,
   `crypto`, `.github/`, `.claude/`, `scripts/`, …). The gate fails **closed**.
3. Provision the required secrets (`AUTOFIX_TOKEN`, `ANTHROPIC_API_KEY` or
   `CLAUDE_CODE_OAUTH_TOKEN`); setup **verifies, never creates** them.
4. **Opt in per PR** with the `ai-autofix` label. There is a hard `max_iterations`
   cap; on cap (or any gate/failure) the PR is flagged `needs-human-review`.

The CI loop confines file tools to the source checkout, keeps trusted helpers and
settings outside it, scans a text-only patch before publication, runs builds in a
separate job without secrets, and gates/scans the exact tree before pushing.
Read [FIX-LOOP.md](FIX-LOOP.md) and [SECURITY-MODEL.md](SECURITY-MODEL.md) before enabling it.

### Layer B Readiness Criteria

- Team is at **standard or strict** tier with a stable Layer A pass rate.
- `fix_loop.allowlist_paths` / `gated_paths` reviewed and signed off by a security owner.
- Required secrets provisioned as fine-grained, repo-scoped tokens.
- A human reviewer is assigned to `needs-human-review` PRs.
- The team has read [SECURITY-MODEL.md](SECURITY-MODEL.md).

## Metrics to Track

| Metric | Starter Target | Standard Target | Strict Target |
|--------|---------------|----------------|---------------|
| Hook pass rate | >95% | >80% | >80% |
| Bypass rate | N/A | <10% | <5% |
| Pre-commit time | <10s | <10s | <10s |
| Pre-push time | N/A | <60s | <60s |
| Developer satisfaction | >3.0/5 | >3.5/5 | >3.5/5 |

Collect metrics using:
```powershell
.\scripts\collect-scan-metrics.ps1 -OutputDir .scan-results/metrics/
```

## Key Statistics (Industry Research)

- **30x** cost multiplier for fixing bugs in production vs. development (NIST)
- **$10.22M** average data breach cost in the US (IBM 2025)
- **40%** reduction in CI failures with shift-left scanning (Forrester TEI)

## Champion Network

Identify scanning champions in each team:
- Champions receive early access to new features
- Champions provide feedback on false positives and friction points
- Champions help onboard teammates
- Schedule monthly champion sync meetings

See [DEVELOPER-SURVEY.md](DEVELOPER-SURVEY.md) for feedback collection templates.

## Handling Resistance

Common objections and responses:

| Objection | Response |
|-----------|----------|
| "Hooks are too slow" | Pre-commit hooks target <10s. Profile with `scripts/profile-hook-performance.ps1` |
| "Too many false positives" | Review exact occurrence exceptions under [suppression governance](SUPPRESSION-GOVERNANCE.md) |
| "I need to commit quickly" | Fix the finding or failed prerequisite; follow the team's reviewed exception process |
| "Suppressions are too bureaucratic" | Suppressions protect the team from audit findings. Start with LOW/MEDIUM self-service |

## Rollback Plan

If a tier upgrade causes excessive friction:

1. Restore the previously reviewed runner configuration and matching platform revision
2. Reinstall its hooks and push transaction adapter if applicable, then verify
3. Investigate root cause (false positives, performance, missing baselines)
4. Address issues before re-attempting upgrade
