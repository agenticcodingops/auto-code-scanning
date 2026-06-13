# Adoption Playbook

Research-backed phased approach to rolling out the security scan→fix platform across the organization.

## A Two-Layer Platform

As of v2.0.0 this is a reusable **two-layer platform**, not just a Terraform scanner.
Roll the layers out **independently** — Layer A first, Layer B only when a team is
ready for autonomous code changes.

| Layer | What it is | Rollout |
|-------|------------|---------|
| **Layer A — Scanning** | Detects issues across **Terraform *and* app-code** (C#/.NET, TypeScript/JS, SQL). Runs locally (Lefthook by default, or pre-commit) and in CI (SARIF to the Security tab). Read-only — never changes code. | The tiered path below (starter → standard → strict) governs **Layer A** adoption. |
| **Layer B — Agentic fix-loop** | **Optional, opt-in, off by default.** An agent proposes a minimal fix: *in-session* via the Claude Code bundle (`templates/claude/`), and *in CI* via the hardened `autonomous-fix.yml` (opt-in per PR with the `ai-autofix` label). | Layered **on top of** a mature Layer A — see [Layer B: Enabling the Fix-Loop](#layer-b-enabling-the-fix-loop). |

Everything for both layers is configured in **one file, `scan-config.yaml`**
(`languages.*` for Layer A, the `fix_loop.*` block for Layer B). One-command
onboarding handles install:

```bash
# Layer A only (app-code scanning, Lefthook default runner)
python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard
# Layer A + Layer B (adds the fix-loop)
python scripts/setup-scan-fix.py --languages csharp,typescript --tier standard --enable-fix-loop
```

> **Pin consumers to `@v2.0.0` (or a SHA) — never `@main`.**

## Rollout Philosophy

The three tiers (starter, standard, strict) provide a progressive path from minimal friction to full enforcement of **Layer A scanning**. The timelines below are **guidelines, not deadlines** -- teams should advance when they meet the criteria for each phase, regardless of calendar time. **Layer B (the fix-loop) is a separate, opt-in decision** layered on a mature Layer A, covered after the tiers.

## Phase 1: Starter Tier

**Goal**: Build developer confidence with minimal friction

### Setup

```bash
python scripts/setup-scanning.py --cloud-provider aws --tier starter
```

### What Runs

| Hook | Stage | What It Does |
|------|-------|-------------|
| trivy-iac-critical | pre-commit | Blocks CRITICAL IaC misconfigurations |
| trivy-secrets | pre-commit | Blocks committed secrets |
| gitleaks | pre-commit | Blocks leaked credentials |

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

### What's Added

| Hook | Stage | What It Does |
|------|-------|-------------|
| trivy-iac-full | pre-push | Full IaC scan (all severities) |
| checkov | pre-push | Policy-as-code checks |
| tflint | pre-push | Terraform linting |
| validate-suppressions | pre-commit | Suppression file validation |

### Rollout Steps

1. Create a baseline of existing findings: `.\scripts\create-baseline.ps1`
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
`stop_hook_active`, so it blocks at most once). No PR, no push credentials, no
privilege boundary to reason about — start here.

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

The CI loop is engineered to break the "lethal trifecta": a read-only **analyze**
job (no push creds, no egress, untrusted PR text treated as data) emits a patch
artifact, and a separate **apply-and-push** job re-enforces the allowlist gate and
re-verifies (secret scan + `build_verify_cmd`) before pushing with `AUTOFIX_TOKEN`.
`claude-code-action` is SHA-pinned to v1.0.148 (CVE-2025-66032). Do not adopt the CI
loop without reading [SECURITY-MODEL.md](SECURITY-MODEL.md).

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
| "Too many false positives" | Use `noisy-checks.yaml` to disable known noisy checks during onboarding. Review quarterly |
| "I need to commit quickly" | `git commit --no-verify` bypasses hooks in emergencies. Bypasses are tracked in metrics |
| "Suppressions are too bureaucratic" | Suppressions protect the team from audit findings. Start with LOW/MEDIUM self-service |

## Rollback Plan

If a tier upgrade causes excessive friction:

1. Revert `.pre-commit-config.yaml` to the previous tier template
2. Run `pre-commit install` to apply changes
3. Investigate root cause (false positives, performance, missing baselines)
4. Address issues before re-attempting upgrade
