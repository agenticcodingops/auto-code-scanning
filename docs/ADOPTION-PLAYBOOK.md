# Adoption Playbook

A phased plan for rolling out the scan and fix platform across a team or organization.

## A Two-Layer Platform

The platform has two layers, and it scans application code as well as Terraform.
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

1. Pick a few developers to act as [scanning champions](#scanning-champions)
2. Deploy the starter tier to their repositories
3. Run for at least 2 weeks before measuring
4. Collect their feedback on speed, false positives and unclear messages

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
3. Expand to about half of the team's repositories
4. Track the metrics in [Collecting metrics](#collecting-metrics)
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
2. Expand to most of the team's repositories
3. Enable suppression validation in CI
4. Run quarterly suppression reviews
5. Ask developers for feedback again

### Success Criteria

- Bypass rate <5%
- Fewer security-related CI failures than before local scanning
- All suppressions have a valid business justification
- Developer feedback is neutral-to-positive

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
separate job without secrets, and gates fix paths and secret-scans changed files from the exact tree before pushing.
Read [FIX-LOOP.md](FIX-LOOP.md) and [SECURITY-MODEL.md](SECURITY-MODEL.md) before enabling it.

### Layer B Readiness Criteria

- Team is at **standard or strict** tier with a stable Layer A pass rate.
- `fix_loop.allowlist_paths` / `gated_paths` reviewed and signed off by a security owner.
- Required secrets provisioned as fine-grained, repo-scoped tokens.
- A human reviewer is assigned to `needs-human-review` PRs.
- The team has read [SECURITY-MODEL.md](SECURITY-MODEL.md).

## Metrics to Track

These are suggested starting targets, not industry benchmarks. Set your own from the
first weeks of data.

| Metric | Starter Target | Standard Target | Strict Target |
|--------|---------------|----------------|---------------|
| Hook pass rate | >95% | >80% | >80% |
| Bypass rate | N/A | <10% | <5% |
| Pre-commit time | <10s | <10s | <10s |
| Pre-push time | N/A | <60s | <60s |

### Collecting metrics

`scripts/collect-scan-metrics.ps1` (PowerShell 7) gathers rough adoption numbers for
one repository. Run it from the repository root:

```powershell
# Last 30 days (default), written to .scan-results/metrics/
./scripts/collect-scan-metrics.ps1

# Last 90 days, with more detail
./scripts/collect-scan-metrics.ps1 -Days 90 -Detailed

# Another output directory
./scripts/collect-scan-metrics.ps1 -OutputPath ./metrics
```

It writes `metrics-YYYY-MM-DD.json` and `metrics-latest.json`, and compares the result
with the previous snapshot in the same directory. In GitHub Actions, `-UploadArtifact`
writes the file path and an artifact name to the step outputs for an upload step.
Know what the numbers mean before you act on them:

- **Bypass rate** is a heuristic: the share of commits in the period whose subject is
  not a Conventional Commit. It does not detect `--no-verify` directly.
- **Hook pass rate** comes from the pre-commit log in the user profile when it exists.
  Otherwise the script estimates it from the bypass rate. Lefthook runs are not counted.
- **Finding counts** come from `.scan-results/unified-results-latest.json`, which
  `scripts/aggregate-scan-results.ps1` writes. Without it, finding counts are zero.

To find slow hooks, use `scripts/profile-hook-performance.ps1` and the
[performance guide](PERFORMANCE-OPTIMIZATION.md).

## Scanning champions

A scanning champion is a developer in each team who uses the tools daily, helps
teammates with setup, and passes feedback back to the platform owners.

**Choosing champions:** pick developers who are respected by their peers, work in the
scanned languages regularly, are comfortable with command-line tools, and can spend an
hour or two a week on it.

**First two weeks:** install scanning in their own repository, go through the full
workflow (commit, fix findings, push, read the CI result), and write down any friction.

**Ongoing:**

- Help teammates install and configure the hooks
- Triage false positives, and request a reviewed exception when one is justified
  (see [suppression governance](SUPPRESSION-GOVERNANCE.md))
- Meet the other champions regularly, for example monthly
- Suggest improvements to hooks and documentation

**Common issues they will see:**

1. **A hook is too slow:** move the check to pre-push; see the [performance guide](PERFORMANCE-OPTIMIZATION.md).
2. **A false positive:** request an exact-occurrence exception in `.scan-suppressions.yaml`.
3. **A tool is not installed:** rerun setup; see [troubleshooting](TROUBLESHOOTING.md).
4. **Someone wants to skip the hooks:** `git commit --no-verify` skips local hooks only.
   CI still scans the pull request. Record why it was needed.

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
