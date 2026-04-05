# Adoption Playbook

Research-backed phased approach to rolling out security scanning across the organization.

## Rollout Philosophy

The three tiers (starter, standard, strict) provide a progressive path from minimal friction to full enforcement. The timelines below are **guidelines, not deadlines** -- teams should advance when they meet the criteria for each phase, regardless of calendar time.

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
