# Build vs. Buy Analysis: Terraform Security Scanning

**Date**: 2026-02-11
**Feature**: [spec.md](spec.md) | [plan.md](plan.md) | [tasks.md](tasks.md)
**Status**: Complete
**Audience**: Engineering leadership, security team, stakeholders

---

## Part 1: Executive Summary

### Verdict: BUILD — with a hybrid complement path

After comprehensive market research covering 11 open-source tools, 12 commercial platforms, and the 3,648-star antonbabenko/pre-commit-terraform repository (our closest open-source competitor), we conclude that **no existing solution provides what we are building**. The specific combination of multi-tool orchestration with cloud-specific configurations, tiered adoption templates, suppression governance, baseline management, reusable CI workflows, cross-platform support, and AI agent integration does not exist in any open-source project or commercial product today.

**Justification in three sentences.** Open-source scanning tools (Trivy, Checkov, tflint) are excellent at detection but provide no orchestration framework for organizational adoption. The closest open-source framework, antonbabenko/pre-commit-terraform, wraps these tools but provides zero cloud-specific configs, zero suppression governance, zero baseline management, zero reusable CI workflows, zero setup automation, and has broken Windows support. Commercial CNAPP platforms (Prisma Cloud, Snyk, Wiz) operate at a different layer — they provide SaaS dashboards and runtime correlation but do not offer a redistributable pre-commit hook framework that organizations can self-host and customize.

### Cost Summary

| Approach | Year 1 Cost (100 developers) | Year 2+ Annual Cost | Pre-commit Hooks | CI/CD Workflows | Governance |
| --- | --- | --- | --- | --- | --- |
| **Build (our project)** | Engineering time + $0 licensing | $0 maintenance | Yes | Yes | Yes |
| **Buy mid-tier commercial (Snyk)** | $30,000-$68,000 | $30,000-$68,000 | Community only | Platform-managed | Platform-managed |
| **Buy enterprise CNAPP (Wiz)** | $24,000-$354,000 | $24,000-$354,000 | CLI only | Platform-managed | Platform-managed |
| **Hybrid (Build + commercial)** | Engineering time + $50,000-$150,000 | $50,000-$150,000 | Yes (ours) | Yes (ours + theirs) | Both layers |

Our solution fills a specific gap: the space between raw open-source tools (free but require manual orchestration) and expensive CNAPP platforms (comprehensive but costly and not pre-commit-focused). We provide the organizational framework layer that neither category addresses.

---

## Part 2: The Problem Space

### What Problem Are We Solving?

Organizations writing Terraform infrastructure as code across multiple cloud providers face a systemic problem: **there is no standardized, reusable framework for enforcing security scanning at the developer workstation level with organizational governance.**

Individual teams can install Trivy or Checkov manually, but this creates fragmentation. Each team writes their own configurations, chooses their own severity thresholds, manages their own suppression mechanisms (if any), and has no visibility into whether scanning is actually happening. Some teams scan diligently. Others skip it entirely because setup is too complex or findings are overwhelming. Security teams have no metrics to measure adoption health.

The consequences are real. According to NIST research, fixing a security issue in production costs roughly 30 times more than fixing it during development. IBM's 2025 Cost of a Data Breach report puts the average US breach cost at $10.22 million. The business case for shift-left security is well established — the question is how to implement it at organizational scale.

### Why Existing Tools Alone Don't Solve It

The Terraform security scanning ecosystem has excellent individual tools. Trivy (31,855 GitHub stars) is a world-class vulnerability scanner. Checkov (8,461 stars) provides over 1,000 policy checks with graph-based analysis. tflint (5,000+ stars) catches provider-specific issues that other tools miss. These tools are mature, well-maintained, and free.

However, these tools are scanners, not frameworks. They answer the question "does this code have security issues?" but they do not answer the organizational questions:

- How do we install scanning consistently across 50 teams in under 5 minutes per team?
- How do we provide AWS-specific, Azure-specific, and GCP-specific configurations out of the box?
- How do we phase adoption so teams are not overwhelmed on day one?
- How do we govern suppression of findings with expiry dates and approval workflows?
- How do we baseline existing technical debt so teams can focus on new issues?
- How do we measure bypass rates, pass rates, and adoption health across the organization?
- How do we provide the same scanning in CI/CD as a reusable workflow?
- How do we support developers on Windows, macOS, and Linux equally?
- How do we integrate with AI coding agents that are becoming standard development tools?

This is the orchestration gap that our solution fills.

### The Orchestration Gap Illustrated

Think of the current landscape as three layers:

**Layer 1 — Individual scanning tools** (Trivy, Checkov, tflint): Excellent at detection. Zero opinion on organizational adoption, governance, or workflow integration.

**Layer 2 — Hook execution frameworks** (antonbabenko/pre-commit-terraform): Wraps Layer 1 tools into pre-commit hooks. Provides execution infrastructure but zero cloud-specific configs, zero governance, zero CI workflows, zero adoption strategy.

**Layer 3 — Commercial CNAPP platforms** (Prisma Cloud, Snyk, Wiz): Provide SaaS dashboards, runtime correlation, compliance reporting. Operate at the CI/CD and cloud runtime layer, not at the developer pre-commit layer. Expensive ($24K-$354K/year).

**Our solution occupies the missing space between Layer 2 and Layer 3.** We build on the same open-source tools as Layer 1, provide the same hook execution as Layer 2, and add the governance, adoption, and organizational features that only Layer 3 provides — but we do it as a self-hosted, free, redistributable framework rather than a paid SaaS platform.

---

## Part 3: Open-Source Landscape

### 3.1 antonbabenko/pre-commit-terraform — Our Closest Competitor

This is the single most important comparison because it is the de facto standard for Terraform pre-commit hooks in the open-source community.

**Repository profile:**

- GitHub stars: 3,648
- Forks: 582
- License: MIT
- Latest release: v1.105.0 (January 6, 2026)
- Release cadence: Monthly
- Language: Shell (Bash)
- Maintenance: Very active, consistent monthly releases over 10 years

**What it provides:** 19 hooks total, including wrappers for terraform_fmt, terraform_validate, terraform_docs, terraform_tflint, terraform_trivy, terraform_checkov, terrascan, infracost_breakdown, and several Terragrunt-specific hooks. It provides a mature per-directory execution framework with parallelism support, Docker image delivery, and OpenTofu compatibility.

**What it does NOT provide — the 11 strategic gaps that justify building our own:**

**Gap 1: No cloud-specific configurations.** pre-commit-terraform provides generic tool wrappers that invoke Trivy as `trivy conf "$(pwd)" --exit-code=1` and Checkov as `checkov -d .` with no configuration. Every consuming team must create their own Checkov YAML, tflint HCL, and Trivy configuration from scratch for their specific cloud provider. Our solution ships pre-built, curated configs for AWS, Azure, and GCP with known-noisy-check exclusions and policy overlay separation.

**Gap 2: No severity-based hook staging.** All hooks in pre-commit-terraform run at the same stage (typically pre-commit). There is no concept of running fast critical-only scans at commit time and comprehensive full-severity scans at push time. Our solution explicitly separates trivy-iac-critical (pre-commit, fast) from trivy-iac-full (pre-push, thorough) and places Checkov at the pre-push stage.

**Gap 3: No reusable CI/CD workflows.** pre-commit-terraform's GitHub workflows directory contains 12 workflows, but they are all internal CI for testing the pre-commit-terraform repository itself. There is no `workflow_call` reusable workflow that consuming repositories can call. Our solution provides a reusable scan workflow with typed inputs for cloud provider, severity, SARIF upload, PR comments, and suppression handling.

**Gap 4: No suppression governance.** There is no suppression mechanism, no `.scan-suppressions.yaml`, no expiry enforcement, no approval workflow, no validation script. Teams using pre-commit-terraform must manage finding suppression entirely on their own through each tool's native (and inconsistent) suppression mechanisms.

**Gap 5: No baseline management.** There is no concept of capturing current scan state and filtering known findings. Existing codebases with hundreds of pre-existing issues have no path to gradual adoption.

**Gap 6: No tiered adoption templates.** There are no starter, standard, or strict templates. There is no phased rollout guidance. Teams face all-or-nothing adoption, which frequently results in choosing nothing.

**Gap 7: No setup automation.** Installation requires multiple manual steps: install pre-commit separately, install each tool individually (Trivy, Checkov, tflint, terraform-docs), create a `.pre-commit-config.yaml` file manually, then run `pre-commit install`. On Ubuntu, this involves 10+ manual curl commands for each binary. Our solution provides a single-script setup with one parameter.

**Gap 8: No metrics or adoption tracking.** There is no bypass detection, no pass rate measurement, no finding trend analysis, no organizational visibility into scanning health.

**Gap 9: No AI agent integration.** No JSON output mode, no machine-readable report file, no auto-fix orchestration, no scan.py standalone script.

**Gap 10: Broken Windows support.** All hooks are Bash scripts. Windows requires WSL or Git Bash — native PowerShell and cmd.exe do not work. Issue #648 "Windows Support / Rewrite hooks to Python" has been open since March 2024 with no resolution. A proof-of-concept Python-based hook was started in PR #652 but the effort has stalled. Our solution provides dual .sh/.ps1 wrappers from day one.

**Gap 11: No fail-open error handling.** When a scanning tool crashes in pre-commit-terraform, the hook blocks the commit. There is no distinction between "the tool found security issues" and "the tool itself failed." Our solution classifies exit codes: only exit code 1 (security findings) blocks; all other non-zero codes are infrastructure errors that fail open with a warning.

**What pre-commit-terraform does well that we should learn from:**

- Mature per-directory scanning framework (`_common.sh`, 641 lines) with battle-tested parallelism (CPU-1 default, configurable limits, CI-aware core detection)
- Flexible argument passing convention (`--args`, `--hook-config`, `--env-vars`)
- Docker image delivery as a fallback for complex installation scenarios
- OpenTofu binary discovery chain

### 3.2 Individual Scanning Tools

**Trivy** (Aqua Security) — 31,855 stars, latest v0.67.2 (October 2025)

The most popular open-source scanner by a wide margin. Trivy is an all-in-one tool covering container vulnerabilities, IaC misconfigurations, secret detection, SBOM generation, and license scanning. It absorbed tfsec (deprecated February 2023) and became the recommended successor. Trivy provides 322+ Terraform-specific checks, supports all major clouds, and runs as a single binary with an auto-updating vulnerability database. It does not provide pre-commit hooks natively — these come through antonbabenko's wrapper. Trivy has no auto-fix capability.

Our solution uses Trivy as a core tool for three dedicated hooks: trivy-iac-critical (CRITICAL-only at pre-commit), trivy-iac-full (all severities at pre-push), and trivy-secrets (secret detection at pre-commit). We add `--skip-db-update` for offline operation, fail-open error handling, JSON output to `.scanning/last-scan.json`, and DB lock retry logic.

**Checkov** (Bridgecrew / Palo Alto Networks) — 8,461 stars, latest 3.2.437+ (weekly releases)

The most comprehensive IaC policy scanner with 1,000+ built-in checks covering CIS, PCI-DSS, HIPAA, and SOC2 frameworks. Checkov is unique in its graph-based analysis that evaluates resource relationships, not just individual attributes. It supports the broadest range of IaC formats (Terraform, CloudFormation, Kubernetes, Helm, Dockerfile, Bicep, ARM, OpenTofu). Checkov provides 6 pre-commit hook variants, including a diff-only hook for scanning only changed files.

Checkov's `--fix` flag offers fix suggestions, but these are AI-powered via OpenAI integration (requires an API key) and generate suggestions rather than deterministic fixes. The open-source Checkov is fully free under Apache 2.0 — the commercial Prisma Cloud platform adds a SaaS dashboard layer.

Our solution uses Checkov for two dedicated hooks: checkov (pre-push with cloud-specific config) and checkov-strict (pre-push, hard-fail on CRITICAL+HIGH). We provide pre-built blocklist configs per cloud provider and leverage `--fix` for AI agent auto-remediation.

**tflint** — 5,000+ stars, latest v0.59.1 (August 2025)

The only scanning tool with native, deterministic auto-fix via `tflint --fix` (available since v0.47.0). tflint is a pluggable Go-based linter with provider-specific plugins for AWS, Azure, and GCP. It catches issues that security scanners miss, such as invalid instance types, deprecated resource configurations, and naming convention violations. It uses keyless plugin verification via Sigstore.

Our solution uses tflint at the pre-push stage with cloud-specific `.tflint.hcl` configs that include both the provider-specific ruleset plugin and the shared `tflint-ruleset-terraform` plugin.

**KICS** (Checkmarx) — 2,300 stars, active through 2025

The broadest IaC platform support (Terraform, CloudFormation, Kubernetes, Docker, Ansible, Bicep, OpenAPI) with 1,900-2,400 queries. KICS provides limited auto-fix capability for simple single-line replacements and additions. It has a VS Code extension with Quick Fix integration and the richest output format support (SARIF, CycloneDX, GitLab SAST, SonarQube, and more). Backed by Checkmarx.

We chose not to include KICS because Trivy + Checkov already cover Terraform comprehensively, and adding a fourth tool would increase complexity and scan times without proportional benefit.

**Terrascan** (Tenable) — 4,800 stars, latest v1.19.9 (September 2024)

OPA/Rego-based policy engine with 500+ policies. Terrascan was a CNCF member project, but its development velocity has declined significantly. The last release was September 2024 — nearly a year and a half without an update. This raises concerns about long-term maintenance and is a reason we excluded it from our tool stack.

**Gitleaks** — Secret detection tool focused specifically on git history scanning. Complements Trivy's secret scanning by checking the full git commit history, not just the current working tree. Included in our solution as the eighth hook.

### 3.3 Auto-Fix Landscape

Auto-remediation for Terraform security findings is an emerging capability with significant limitations.

**tflint --fix** is the most reliable option. It provides deterministic, pattern-based fixes for linting violations. Available since v0.47.0, it modifies Terraform files in-place for well-defined rules. However, it only covers linting issues (formatting, naming, type validation), not security misconfigurations.

**Checkov --fix** provides AI-powered fix suggestions. In the open-source version, this requires an OpenAI API key and generates suggestions rather than automatically applying fixes. The commercial Prisma Cloud platform adds "Smart Fixes" with broader coverage and one-click PR generation.

**KICS auto-fix** handles simple single-line replacements and additions. It is conservative and limited to deterministic pattern replacements where the fix is unambiguous.

**Semgrep fix directives** allow rule authors to define automatic fixes within rule definitions. This works well for pattern-based substitutions but requires custom rules for each fix scenario.

Emerging research (LLMSecConfig, 2025) achieved a 94% success rate on Kubernetes security config repair using large language models with Checkov for policy evaluation. This suggests that AI-powered auto-remediation will improve significantly in the coming years, but current capabilities remain limited to a subset of findings.

Our solution leverages Checkov's `--fix` for AI agent auto-remediation via the `scan.py --auto-fix` flag, and reports which findings were auto-fixed versus which remain unfixable.

### 3.4 Feature Comparison: pre-commit-terraform vs. Our Solution

| Feature | pre-commit-terraform | Our Solution | Gap? |
| --- | --- | --- | --- |
| Pre-commit hooks for Terraform | 19 hooks (general-purpose wrappers) | 8 hooks (security-focused, purpose-built) | Parity |
| Trivy integration | Generic `trivy conf` wrapper | 3 dedicated hooks with severity splitting | Our advantage |
| Checkov integration | Generic `checkov -d .` wrapper | 2 dedicated hooks with cloud configs | Our advantage |
| tflint integration | Generic wrapper with --init | Cloud-specific configs provided | Our advantage |
| Severity-based hook staging | No differentiation | CRITICAL at pre-commit, FULL at pre-push | Our advantage |
| Pre-commit vs pre-push staging | No | Explicit per-hook stage assignment | Our advantage |
| Cloud-specific configurations | None | AWS, Azure, GCP configs for Checkov + tflint | Our advantage |
| Config layering (security vs policy) | N/A | Universal security + org policy overlay | Our advantage |
| Suppression governance | None | YAML-based with validation, expiry, approval | Our advantage |
| Baseline management | None | (rule_id, file_path) matching with hash lookup | Our advantage |
| Reusable GitHub Actions workflow | None (internal CI only) | workflow_call with cloud-provider, SARIF, PR comments | Our advantage |
| SARIF upload to GitHub Security tab | N/A | Yes, with truncation handling | Our advantage |
| PR comment summaries | N/A | Pass/fail per tool with severity breakdown | Our advantage |
| Setup automation | Manual multi-step (10+ commands) | Single script with -CloudProvider param | Our advantage |
| Tiered adoption templates | None | Starter, standard, strict with rollout guide | Our advantage |
| Metrics collection | None | Bypass rate, pass rate, trends, CI artifacts | Our advantage |
| Cross-tool deduplication | None | (file, resource, category) matching | Our advantage |
| AI agent integration | None | scan.py, JSON output, --auto-fix | Our advantage |
| Fail-open error handling | No (crashes block commits) | Exit code classification, infrastructure errors pass | Our advantage |
| Cross-platform Windows support | Broken (requires WSL) | Native .ps1 wrappers via dispatcher | Our advantage |
| Hook parallelism | Yes (CPU-1 default) | Yes (parallel + Trivy DB lock retry) | Parity |
| Performance profiling | Manual benchmarks | CI-enforced 5s per hook threshold | Our advantage |
| Docker image delivery | Yes (full image) | Not in scope (setup scripts instead) | Their advantage |
| Terragrunt support | Yes (4 hooks) | Not in scope | Their advantage |
| Infracost integration | Yes | Not in scope | Their advantage |
| OpenTofu support | Yes | Not yet specified | Their advantage |
| terraform-docs support | Yes (3 variants) | In strict tier template | Parity |
| Community adoption | 3,648 stars, 10 years | New (internal) | Their advantage |

**Score: 19 features where we have an advantage, 3 where they have an advantage, 3 at parity.**

---

## Part 4: Commercial Landscape

### 4.1 Platform Profiles

**Prisma Cloud** (Palo Alto Networks / Bridgecrew)

The most comprehensive CNAPP platform, built on the open-source Checkov engine that Palo Alto acquired with Bridgecrew in 2021. Prisma Cloud's Code Security module adds a SaaS dashboard, Smart Fixes, one-click PR generation, graph-based analysis, drift detection, and compliance framework mapping on top of Checkov's open-source scanning.

Pricing is credit-based. Business Edition runs approximately $9,000/year per 100 credits. Enterprise Edition runs approximately $18,000/year per 100 credits. The Code Security module is metered per active developer (git committer in the last 90 days). No free tier for the commercial platform, but Checkov remains fully free.

Key differentiator: Owns the most popular IaC policy scanner. Deepest Terraform policy coverage with 2,000+ policies via Checkov. Graph-based analysis evaluates resource dependencies, not just individual attributes.

**Snyk Infrastructure as Code**

Developer-first security platform with IaC scanning as one of four product modules. Snyk offers Terraform plan file scanning, which analyzes the fully-resolved configuration rather than just the HCL source code, producing fewer false positives.

Pricing is per developer per month. Free tier available with limited monthly tests. Team plans range from $25-$57 per developer per month. Business and Enterprise tiers have custom pricing. For 100 developers, annual costs range from $30,000 to $68,000.

Pre-commit support exists through community-maintained hooks (not officially supported by Snyk). Auto-remediation is basic — recommendations rather than automatic fixes. Snyk's strongest value proposition is the developer experience with IDE plugins for VS Code and JetBrains.

**Wiz** (acquired by Google for $32 billion in 2025)

Cloud security platform with IaC scanning as part of Wiz Code. Wiz's differentiator is agentless, graph-based security that maps IaC code directly to deployed cloud resources via Terraform state files. This code-to-cloud traceability is the strongest in the market.

Pricing is per workload. Wiz Essential starts at $24,000/year for 100 workloads. Wiz Advanced is $38,000/year. Wiz Code add-on is $58,500/year for 100 code licenses. Median enterprise contracts run approximately $111,500/year. No free tier.

Local scanning is supported via the Wiz CLI (wizcli) for shift-left integration. Pre-commit hooks are supported through the CLI. Wiz uses a unified policy engine where rules can be written once and enforced across code, pipeline, and runtime.

**Aqua Security** (Trivy maker)

Aqua maintains the open-source Trivy scanner and offers Trivy Premium as part of their CNAPP platform. Trivy open-source is unlimited and free under Apache 2.0. Trivy Premium adds customer support, premium threat intelligence, malware scanning, and centralized management. Enterprise pricing is not publicly disclosed.

Aqua's position is unique: they maintain the most popular open-source scanner while also selling a commercial layer on top. This validates our approach of building on Trivy as a core tool — the tool itself is well-maintained with corporate backing.

**HCP Terraform / Terraform Enterprise** (HashiCorp / IBM)

HashiCorp's own platform with policy enforcement via Sentinel (proprietary) or OPA/Rego. Pricing is based on Resources Under Management (RUM). Essentials runs $0.10 per resource per month. Standard runs $0.47 per resource per month. Free tier includes 500 managed resources. The legacy free plan ends March 31, 2026.

HCP Terraform does not operate at the pre-commit layer. Policy enforcement happens at plan/apply time. It provides gating (blocking non-compliant plans from applying) but not auto-remediation. It is complementary to pre-commit scanning, not a replacement for it.

**Other notable platforms:** Orca Security (AI-driven cloud-to-code remediation, custom expensive pricing), Spacelift (IaC orchestration platform starting at $399/month, not a scanner), env0 (governance-first IaC automation, Pro at $349/month), Datadog Cloud Security (uses 800+ KICS rules, one-click remediations for 180+ findings), Lacework/Fortinet (CNAPP add-on, auto-remediation via PR), Aikido Security (all-in-one ASPM, free for 2 users, AI-powered autofix).

### 4.2 What Commercial Platforms Offer That Open-Source Cannot

There are eight differentiators that justify commercial platform spending for organizations that need them:

**1. Runtime context and code-to-cloud correlation.** Open-source tools perform static analysis in isolation. Commercial platforms correlate IaC findings with actual runtime behavior. A permission flagged as overly broad in static analysis may be actively exploited in production or may be safely unused. This context-aware prioritization is the single most valuable commercial differentiator.

**2. Centralized dashboards and cross-repo reporting.** Open-source tools produce CLI output, SARIF files, or JSON. Commercial platforms offer unified dashboards aggregating findings across all repositories, teams, and cloud accounts. This is critical for security teams managing hundreds of repos.

**3. Compliance framework mapping.** While Checkov and Trivy include CIS benchmark mappings, commercial platforms provide audit-ready compliance reports mapped to SOC2, HIPAA, PCI-DSS, NIST, and ISO 27001 with evidence collection and attestation workflows.

**4. Policy management at scale.** Open-source requires manual distribution of custom policies across repositories. Commercial platforms offer centralized policy definition, versioning, exception management, and enforcement across all repos simultaneously.

**5. Drift detection.** Open-source IaC scanners only analyze code at rest. Commercial platforms detect when deployed infrastructure has drifted from its IaC definition and can automatically remediate.

**6. Supply chain security for Terraform modules.** Commercial platforms scan module registries, validate module integrity, and generate SBOMs. Open-source tools do not address this.

**7. Enterprise identity and access management.** SSO/SAML, RBAC with fine-grained permissions, and audit logging are standard in commercial platforms and absent in open-source tools.

**8. AI-powered remediation at scale.** Commercial platforms generate fix PRs automatically with AI-driven code suggestions across entire repositories. Open-source auto-fix is limited to individual tool capabilities.

### 4.3 Market Trends (2025-2026)

The global IaC Security market reached $1.35 billion in 2024 and is growing at 25.6% CAGR, projected to reach $10.85 billion by 2033 (DataIntelo).

CNAPP consolidation is accelerating. Gartner forecasts that by 2029, 60% of enterprises that do not deploy unified CNAPP solutions will lack extensive cloud attack surface visibility. IaC scanning is being absorbed into broader cloud security platforms rather than existing as standalone products.

Shift-left security has become table stakes. Every vendor now supports some form of pre-commit or CI-level scanning. The competitive differentiator has moved from "can you scan IaC?" to "can you correlate code findings with runtime context?"

Detection-only tooling is fading. Industry analysts predict that by 2026, platforms will be expected to automatically correct drift, reverse unauthorized console changes, and maintain desired state continuously.

Terraform remains the dominant IaC tool despite the BSL license change and OpenTofu fork. Per Firefly's State of IaC 2025 report, Terraform maintains the largest market share, especially among enterprises.

---

## Part 5: Gap Analysis

### 5.1 Strategic Gaps in pre-commit-terraform That Justify Our Build

| Gap | What's Missing | Impact on Organizations | Our Solution |
| --- | --- | --- | --- |
| Cloud configs | Every team writes configs from scratch | Inconsistent scanning across teams, missed checks | Pre-built AWS/Azure/GCP configs with noisy-check curation |
| Severity staging | All checks at one stage | Slow commits or incomplete scanning | CRITICAL at commit (fast), full at push (thorough) |
| CI workflows | Teams build their own pipelines | Duplicated effort, inconsistent CI scanning | Reusable workflow_call with SARIF + PR comments |
| Suppressions | No governance mechanism | Teams ignore all findings or fork the solution | YAML-based with validation, expiry, approval workflow |
| Baselines | No debt management | Existing codebases overwhelmed, scanning abandoned | (rule_id, file_path) matching with O(1) lookup |
| Tiered adoption | All-or-nothing | Teams reject scanning entirely | Starter/standard/strict with 90-day rollout |
| Setup automation | 10+ manual steps | High onboarding friction, inconsistent installations | Single script, one parameter |
| Metrics | No organizational visibility | Cannot measure ROI or identify struggling teams | Bypass rate, pass rate, trends, CI artifact upload |
| AI integration | No machine output | Growing AI dev workflows have no scanning integration | scan.py + JSON + auto-fix |
| Windows support | Broken (requires WSL) | Excludes Windows-primary development teams | Native .ps1 wrappers via dispatcher |
| Fail-open | Tool crashes block developers | Developer frustration, increased hook bypassing | Exit code classification, infrastructure errors pass |

### 5.2 Features They Have That We Match

- Trivy, Checkov, tflint integration (we both wrap the same tools, but with different levels of configuration)
- Hook parallelism (both support concurrent execution)
- terraform-docs support (included in our strict tier template)
- terraform_fmt, terraform_validate (included in our tier templates via pre-commit/pre-commit-hooks)

### 5.3 Features They Have That We Intentionally Skip

| Feature | Their Solution | Why We Skip It | Future Option |
| --- | --- | --- | --- |
| Terragrunt support | 4 dedicated hooks | Our target repos use Terraform, not Terragrunt | Could add later if demand exists |
| Infracost integration | Cost estimation hook | Not security scanning; orthogonal concern | Teams add independently if wanted |
| Terrascan integration | Scanner wrapper | Redundant with Trivy + Checkov; declining maintenance | Not recommended |
| Docker image delivery | Full bundled image | Our setup scripts eliminate installation complexity | Could add as alternative delivery |
| OpenTofu support | Binary discovery chain | Not yet a priority; Terraform dominant | Add when demand justifies |
| tfupdate hook | Version constraint management | Not security scanning | Out of scope |

---

## Part 6: Build vs. Buy Decision Matrix

### 6.1 Scoring Matrix (1 = Poor, 5 = Excellent)

This matrix evaluates five options against our 15 Kiro requirements:

| Requirement | Build (Ours) | pre-commit-terraform | Prisma Cloud | Snyk IaC | Wiz |
| --- | --- | --- | --- | --- | --- |
| Req 1: Pre-commit hooks | 5 | 4 | 3 | 2 | 2 |
| Req 2: Multi-cloud config | 5 | 1 | 4 | 3 | 4 |
| Req 3: Reusable CI workflows | 5 | 1 | 3 | 3 | 3 |
| Req 4: Setup experience | 5 | 2 | 3 | 3 | 2 |
| Req 5: Tiered adoption | 5 | 1 | 1 | 1 | 1 |
| Req 6: Suppression governance | 5 | 1 | 4 | 3 | 3 |
| Req 7: Metrics and aggregation | 5 | 1 | 5 | 4 | 5 |
| Req 8: Baseline management | 5 | 1 | 3 | 2 | 3 |
| Req 9: Adoption playbook | 5 | 1 | 2 | 2 | 2 |
| Req 10: AI agent integration | 5 | 1 | 2 | 1 | 1 |
| Req 11: Severity normalization | 5 | 1 | 5 | 4 | 4 |
| Req 12: Performance CI validation | 5 | 1 | 1 | 1 | 1 |
| Req 13: Testing infrastructure | 5 | 2 | 3 | 2 | 2 |
| Req 14: Version pinning | 5 | 4 | N/A | N/A | N/A |
| Req 15: Error recovery (fail-open) | 5 | 1 | 3 | 2 | 2 |
| **Total Score** | **75/75** | **23/75** | **42/70** | **33/70** | **35/70** |

Note: Commercial platforms score N/A on Req 14 (version pinning) because they manage versions through their platform rather than git tags.

**Interpretation:** Our solution scores 75/75 by design — it was built to address all 15 requirements. pre-commit-terraform covers only basic hook execution (23/75). Commercial platforms score higher than pre-commit-terraform (33-42/70) due to their governance, metrics, and multi-cloud capabilities, but they do not address our specific requirements around pre-commit hooks, tiered adoption, setup automation, AI agent integration, or performance validation.

### 6.2 When to BUILD (Our Scenario)

Building is the right choice when:

- Pre-commit scanning at the developer workstation is the primary use case
- You need offline/local scanning without SaaS dependency or data leaving the organization
- You want to avoid vendor lock-in with open-source tools
- You need cloud-specific configurations curated for your organization
- You need tiered adoption to roll out scanning across teams with varying maturity
- You want to keep licensing costs at zero (open-source tools only)
- You need cross-platform support including native Windows
- You are building organizational standards, not purchasing a product
- You want to integrate with AI coding agents

All of these conditions apply to our scenario.

### 6.3 When to BUY (Not Our Scenario, But Worth Documenting)

Buying a commercial platform is the right choice when:

- Runtime correlation between IaC code and deployed cloud resources is a primary need
- Compliance attestation for external auditors (SOC2, HIPAA, PCI-DSS) is required
- Drift detection and automated remediation at scale is critical
- You have 100+ developers and need centralized dashboards with cross-repo visibility
- You are already invested in a CNAPP vendor's ecosystem
- Your security budget supports $50,000-$350,000+ per year for tooling
- You prioritize breadth of scanning (containers, secrets, SBOM, licenses) over depth of Terraform adoption workflow

### 6.4 The Hybrid Recommendation

The strongest long-term position is to build our pre-commit framework AND complement it with a commercial CNAPP platform when the organization is ready. These are complementary, not competing solutions.

Our framework catches issues at the earliest possible moment (before commit) with organizational governance (suppressions, baselines, tiers). A commercial platform provides runtime correlation, compliance reporting, centralized dashboards, and drift detection. Together, they cover the full development lifecycle: code (our framework) to cloud (commercial platform).

The hybrid approach works because our framework operates at the pre-commit and CI layer with no dependency on any commercial platform. If the organization adds a CNAPP platform later, our framework continues operating independently. If the organization decides not to add a commercial platform, our framework still delivers complete shift-left security coverage.

---

## Part 7: Cost Analysis

### 7.1 Build Cost

Our solution requires implementing 79 tasks across 15 phases (see [tasks.md](tasks.md)). The MVP scope is 33 tasks covering Phases 1-4 plus Phase 12 (setup, foundational, install, hooks, cloud configs).

The direct licensing cost is $0. All underlying tools (Trivy, Checkov, tflint, Gitleaks, pre-commit) are open-source with permissive licenses (Apache 2.0 or MIT).

Engineering investment is a one-time build cost. Once built, the framework requires only maintenance effort (responding to tool updates, curating noisy-check lists, updating documentation). This maintenance is estimated at low ongoing effort given the solution's reliance on stable, well-maintained open-source tools.

### 7.2 Buy Cost (For Comparison)

Annual licensing costs for commercial platforms at the scale of 100 developers:

| Platform | Annual Cost | What You Get | What You Miss |
| --- | --- | --- | --- |
| Snyk IaC (Team) | $30,000-$68,000 | CLI scanning, IDE plugins, TF plan scanning | No pre-commit hooks, no tiered adoption, no governance |
| Prisma Cloud (Business) | ~$90,000+ | Full CNAPP, Checkov integration, Smart Fixes | No redistributable hook framework, no tiered adoption |
| Wiz (Advanced + Code) | $96,500-$354,000 | Full CNAPP, code-to-cloud, unified policies | No pre-commit framework, no adoption playbook |
| HCP Terraform (Standard) | ~$28,000 (500 RUM) | Policy gating, Sentinel, state management | No pre-commit hooks, no scanning (gating only) |

### 7.3 Hybrid Cost

Build our framework ($0 licensing) plus add a mid-tier commercial platform for runtime correlation when the organization is ready:

- Year 1: Engineering investment + $0 licensing (framework only)
- Year 2+: $0 framework maintenance + $50,000-$150,000 commercial platform (optional)

### 7.4 ROI Argument

The framework is a one-time build investment that delivers:

- Zero per-developer licensing fees at any scale (100 developers or 1,000 developers — same cost: $0)
- Organizational control over configurations, policies, and adoption pace
- No vendor lock-in — all underlying tools are open-source with large communities
- Customization freedom — every aspect can be tailored to organizational needs
- AI agent integration that no commercial platform currently provides at the pre-commit layer

For a 100-developer organization, avoiding even the cheapest commercial platform ($30,000/year) pays for the engineering investment within the first year. At 500+ developers, the cost avoidance is $150,000+ per year, every year.

---

## Part 8: Recommendation

### Primary Recommendation: BUILD

Build the Reusable Terraform Security Scanning Solution as specified in [spec.md](spec.md) and [tasks.md](tasks.md). The market research validates this decision:

1. **No existing solution provides what we need.** The combination of multi-tool orchestration, cloud-specific configs, tiered adoption, suppression governance, baseline management, reusable CI workflows, cross-platform support, and AI agent integration is novel. We are not reinventing the wheel — we are building the car.

2. **We build on proven foundations.** Our tool stack (Trivy 31,855 stars, Checkov 8,461 stars, tflint 5,000+ stars) represents the most mature and actively maintained scanning tools in the ecosystem. We orchestrate these tools — we do not compete with them.

3. **The orchestration gap is real and unaddressed.** pre-commit-terraform (our closest competitor) has 11 strategic gaps including no cloud configs, no governance, no CI workflows, no setup automation, and broken Windows support. These are not minor missing features — they are the entire organizational adoption layer.

4. **Commercial platforms solve a different problem.** CNAPP platforms provide runtime correlation and compliance dashboards at $30,000-$354,000/year. They do not provide a redistributable pre-commit hook framework. They are complementary to our solution, not alternatives.

### Secondary Recommendation: LEARN from pre-commit-terraform

Despite the 11 gaps, pre-commit-terraform has valuable patterns refined over 10 years with 3,648 stars:

- Their per-directory execution framework and parallelism implementation are battle-tested
- Their argument passing conventions are well-understood by the community
- Their Docker image approach is a viable alternative delivery mechanism for the future

### Tertiary Recommendation: COMPLEMENT with commercial CNAPP (optional, later)

When the organization is ready, adding a commercial platform for runtime correlation, compliance reporting, and drift detection would strengthen the overall security posture. This is complementary to our framework and can be adopted independently on its own timeline.

### Positioning Statement

Our solution fills the gap between raw open-source scanning tools and expensive commercial CNAPP platforms. We provide the organizational framework layer — setup automation, cloud configs, tiered adoption, governance, metrics, and CI integration — that makes open-source tools usable at enterprise scale. This is not a product that exists today. We are building it.

---

## Sources

### Open-Source Tools
- [antonbabenko/pre-commit-terraform](https://github.com/antonbabenko/pre-commit-terraform) — 3,648 stars, MIT, v1.105.0
- [bridgecrewio/checkov](https://github.com/bridgecrewio/checkov) — 8,461 stars, Apache 2.0
- [aquasecurity/trivy](https://github.com/aquasecurity/trivy) — 31,855 stars, Apache 2.0
- [terraform-linters/tflint](https://github.com/terraform-linters/tflint) — 5,000+ stars
- [Checkmarx/kics](https://github.com/Checkmarx/kics) — 2,300 stars, Apache 2.0
- [tenable/terrascan](https://github.com/tenable/terrascan) — 4,800 stars, Apache 2.0
- [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) — Secret detection
- [gruntwork-io/pre-commit](https://github.com/gruntwork-io/pre-commit) — 541 stars, Apache 2.0
- [pre-commit-terraform issue #648](https://github.com/antonbabenko/pre-commit-terraform/issues/648) — Windows support

### Commercial Platforms
- [Prisma Cloud Licensing](https://www.paloaltonetworks.com/resources/guides/prisma-cloud-enterprise-edition-licensing-guide)
- [Snyk IaC](https://snyk.io/product/infrastructure-as-code-security/)
- [Wiz Pricing (Vendr)](https://www.vendr.com/marketplace/wiz)
- [Orca Security](https://orca.security/platform/application-security/)
- [Aqua Trivy Premium](https://trivy.dev/docs/latest/commercial/compare/)
- [HCP Terraform Pricing](https://www.hashicorp.com/en/pricing)
- [Spacelift Pricing](https://spacelift.io/pricing)
- [env0 Pricing](https://www.env0.com/pricing)
- [Datadog IaC Security](https://www.datadoghq.com/blog/datadog-iac-security/)
- [Lacework IaC](https://docs.lacework.com/iac/)

### Market Research
- [IaC Security Market Size (DataIntelo)](https://dataintelo.com/report/infrastructure-as-code-security-market) — $1.35B in 2024, 25.6% CAGR
- [Firefly State of IaC 2025](https://www.firefly.ai/state-of-iac-2025)
- [Gartner CNAPP Market Guide](https://www.gartner.com/reviews/market/cloud-native-application-protection-platforms)
- [2026 IaC Predictions (ControlMonkey)](https://controlmonkey.io/blog/2026-iac-predictions/)
- [Terraform Scanning Tools Comparison (Spacelift)](https://spacelift.io/blog/terraform-scanning-tools)
- [IBM Cost of a Data Breach Report 2025](https://www.ibm.com/reports/data-breach)
- [NIST Relative Cost of Fixing Defects](https://www.nist.gov/publications)
