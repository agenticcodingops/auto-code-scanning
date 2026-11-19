Introduction

Welcome to the comprehensive presentation guide for the Reusable Terraform Security Scanning Solution. This audio guide will prepare you to present this project to a wider audience with confidence. You will learn why we are building this solution, what problem it solves, how it works, and what key design decisions shaped it.

This guide is organized into twelve chapters. Chapter One covers the problem statement and why this solution matters. Chapter Two explains the core design principles that govern every decision. Chapter Three walks through the solution architecture at a high level. Chapter Four through Chapter Nine cover each of the major feature areas in detail. Chapter Ten explains the key design decisions and the reasoning behind them. Chapter Eleven covers the implementation strategy, team structure, and project scope. Chapter Twelve wraps up with success criteria and key takeaways.

At a normal listening pace, this guide should take approximately two to three hours to listen through completely. Feel free to pause and replay any section that feels particularly relevant to your presentation audience.

Section Break

Chapter One: The Problem Statement and Why This Matters

Let us start with the fundamental question. Why are we building this?

Every organization writing Terraform infrastructure as code faces a common challenge. Security vulnerabilities in Terraform configurations, things like open security groups, publicly accessible storage buckets, hardcoded secrets, and missing encryption, are cheap to fix during development but incredibly expensive to fix after deployment. According to research by the National Institute of Standards and Technology, commonly known as NIST, fixing a security issue in production costs roughly thirty times more than fixing it during the coding phase. IBM's annual Cost of a Data Breach report puts the average cost of a data breach in the United States at ten point two two million dollars.

The industry term for addressing security issues earlier in the development lifecycle is called shift-left security. The idea is simple. Instead of discovering security problems during a production audit or, worse, after a breach, you catch them the moment a developer writes the code. The earlier you catch it, the cheaper and safer the fix.

Now here is the real-world problem. Most organizations have multiple teams writing Terraform code across multiple cloud providers, including Amazon Web Services, Microsoft Azure, and Google Cloud Platform. Each team might be using different scanning tools, different configurations, different severity thresholds, or no scanning at all. There is no consistency, no governance, and no way to measure whether security scanning is actually working across the organization.

Some teams might install a tool like Trivy or Checkov and configure it well. Other teams might skip it entirely because setup is too complicated or the tools produce too many false positives. Even teams that do adopt scanning often bypass it when they are under deadline pressure. A developer can simply type git commit with a no-verify flag and skip all the hooks entirely.

This is important. The solution we are building addresses all of these problems simultaneously. It provides a single, reusable, centrally maintained security scanning solution that any Terraform repository across the organization can adopt in under five minutes. It works across all three major cloud providers. It uses a two-layer defense model with local hooks and CI enforcement. It provides governance, metrics, and reporting. And it does all of this while respecting developer productivity by keeping scan times under ten seconds for typical commits.

Let me explain the two-layer defense model because it is central to everything. The first layer consists of pre-commit hooks that run locally on the developer's machine. These hooks catch the most critical issues, like hardcoded secrets and critical infrastructure misconfigurations, before the code even leaves the developer's laptop. The second layer is a reusable GitHub Actions workflow that runs in CI/CD, which stands for Continuous Integration and Continuous Deployment. This second layer performs a comprehensive scan on every pull request, uploads results to GitHub's Security tab, and posts summary comments on the pull request. Even if a developer bypasses the local hooks, the CI layer catches everything.

Think of it like airport security with two checkpoints. The first checkpoint is quick and catches the obvious problems. The second checkpoint is thorough and catches everything else. Together, they provide defense in depth.

Section Break

Chapter Two: The Core Design Principles

Before we dive into the features, let me walk you through the six core principles that govern every design decision in this project. These principles are documented in what we call the project constitution, and they serve as the authoritative guide for all development work.

The first principle is Cloud Agnostic. The solution must support Amazon Web Services, Azure, and Google Cloud Platform without any code changes to the shared hooks or workflow logic. Cloud-specific behavior is driven entirely by configuration files stored in separate directories, one for each provider. Adding a new cloud provider in the future should only require creating a new configuration directory and corresponding templates. No existing hooks or workflows should need modification. The rationale here is straightforward. Organizations use multiple cloud providers. A single scanning solution that adapts through configuration eliminates tool sprawl and ensures a consistent security posture across all clouds.

The second principle is Zero-Friction Installation. Developers must be able to install and activate scanning in under five minutes using a single setup script or at most three shell commands. No manual editing of configuration files should be required for the default installation path. The setup process validates all prerequisites and provides clear remediation guidance if anything is missing. The rationale is that developer adoption is inversely proportional to setup friction. A five-minute ceiling ensures teams can onboard during a single standup timebox.

The third principle is Version Controlled. All consuming repositories must pin to a specific version tag of the scanning repository. Updates are opt-in, never forced. Version tags follow semantic versioning, meaning major dot minor dot patch format. Breaking changes increment the major version. New hooks or optional parameters increment the minor version. Bug fixes increment the patch version. Consuming repos update by running the pre-commit autoupdate command or by changing the rev field in their pre-commit configuration file. A changelog documents every version with migration notes for major bumps. The rationale is that pinned versions prevent unexpected breakage. Opt-in updates give teams control over when they absorb changes.

The fourth principle is Override Friendly. Consuming repositories must be able to override any hook argument, stage, file pattern, or severity threshold without forking this repository. Every hook exposes configurable arguments. Consuming repos can override behavior by specifying custom arguments, stages, file patterns, or exclusions in their local configuration. Severity thresholds are also overridable through arguments or external config files. The rationale is that no two teams have identical risk profiles. Override without fork ensures teams can tailor scanning to their context while still benefiting from upstream improvements.

The fifth principle is Performance First. Pre-commit hooks must complete in under ten seconds total for a typical commit. Individual hooks must complete in under five seconds. Fast checks like secret scanning and critical-only scans run at the pre-commit stage to minimize developer wait time. Slower checks like full severity scans and CIS benchmark validation run at the pre-push stage or only in CI. Performance regressions are detected via CI benchmarks and treated as bugs. The rationale is powerful and simple. Developers bypass slow hooks. By tiering checks across commit, push, and CI stages, the solution maximizes coverage without degrading the inner development loop.

The sixth and final principle is Tested. Every hook must have integration tests with fixture files covering all supported cloud providers. Test fixtures must exist in a dedicated test fixtures directory organized by provider. Each fixture contains both passing and intentionally failing Terraform configurations. CI runs all hook integration tests on every pull request. New hooks cannot be merged without corresponding test fixtures and a passing CI run. The rationale is that a security tool that produces false positives or misses real findings erodes trust. Integration tests with real Terraform fixtures ensure hooks behave correctly before reaching consuming teams.

Beyond these six principles, the constitution also establishes security standards. Default severity thresholds must align with the organization's risk tolerance. Critical findings block commits. High and above block pushes. Suppression of findings requires justification and tracking. All scanning runs locally with no code uploaded to external services. Scanning tool versions enforce minimum ranges to ensure baseline capability.

Section Break

Chapter Three: The Solution Architecture

Now let me walk you through how the solution is actually structured. Understanding the architecture will help you explain it clearly during your presentation.

At its core, this is a shared library or framework project. It is not a standalone application. Other Terraform repositories across the organization consume it through the pre-commit framework. When a team adds a reference to this repository in their pre-commit configuration file, they get access to all the security scanning hooks we provide.

The repository is organized into several major directories. Let me walk through each one.

First, the hooks directory. This contains the actual hook entry scripts. There are eight hooks in total. Each hook has both a bash script for Unix systems and a PowerShell script for Windows. A thin dispatcher script detects the operating system and routes execution to the appropriate script. The hooks also have a shared library directory containing common functions used by all hooks, things like fail-open error handling, JSON output generation, monorepo directory detection, and verbose output toggling.

Second, the scripts directory. This contains utility scripts that serve various purposes. There is a setup scanning script in both PowerShell and Python for cross-platform installation. There is a scan dot py script for AI agent integration. There is a validate suppressions script rewritten in Python for cross-platform compatibility. And there are PowerShell scripts for creating baselines, aggregating scan results, collecting metrics, profiling hook performance, and generating suppression reports.

Third, the configs directory. This is organized by cloud provider, with subdirectories for Amazon Web Services, Azure, and Google Cloud Platform, plus a common directory for shared configurations. Each provider directory contains a Checkov configuration file, a tflint configuration file, and a policy overlay file. The common directory contains a Trivy ignore file and a suppression template.

Fourth, the templates directory. This contains pre-commit configuration templates organized by adoption tier. There are three tiers: starter, standard, and strict. Each tier template has progressively more hooks enabled. There are also cloud-specific templates for each provider.

Fifth, the GitHub workflows directory. This contains reusable GitHub Actions workflows, including the main reusable scan workflow, a performance check workflow, a bypass detection workflow, and a CI workflow for testing the scanning repository itself.

Sixth, the schemas directory. This contains JSON schema files that define the structure of scan output, including the unified results schema and the agent report schema.

Seventh, the tests directory. This contains test fixtures organized by provider and outcome, along with unit tests for PowerShell and Python scripts, and integration tests for end-to-end validation.

Finally, the docs directory. This contains all the user-facing documentation, including the quick start guide, setup guide, hook reference, multi-cloud guide, adoption playbook, and several other reference documents.

This is important. When a consuming repository installs this solution, the setup script copies the appropriate cloud-specific configurations to a dot scanning directory within their repository. The hooks then reference these local copies via explicit config file flags. This means the consuming repository's existing configuration files are never touched or overwritten.

Section Break

Chapter Four: The Hook System and How It Works

Let me now walk through the eight security scanning hooks in detail. This is the heart of the solution, so understanding each hook will be valuable for your presentation.

The first hook is trivy-iac-critical. This runs at the pre-commit stage, meaning it executes every time a developer makes a commit. It uses Trivy to scan for infrastructure as code misconfigurations, but only at the critical severity level. This is the fastest possible scan because it filters out everything below critical. It runs with the skip database update flag for speed, meaning it uses whatever Trivy vulnerability database is already downloaded locally. The database gets updated in CI instead.

The second hook is trivy-iac-full. This runs at the pre-push stage, meaning it only executes when a developer pushes their changes to the remote repository. It scans for all severity levels, not just critical. Because it is more thorough and therefore slower, it is placed at the push stage where a few extra seconds are more acceptable.

The third hook is trivy-secrets. This also runs at the pre-commit stage. It uses Trivy's secret detection mode to find hardcoded secrets, API keys, passwords, and other credentials in the code. Secret detection is binary. Either a secret is found or it is not. There are no severity levels.

The fourth hook is checkov. This runs at the pre-push stage. Checkov is a policy-as-code tool that validates Terraform configurations against CIS benchmarks and hundreds of other security best practices. It uses the cloud-specific Checkov configuration file to determine which checks to run.

The fifth hook is checkov-strict. This also runs at the pre-push stage. It is a stricter version of the checkov hook that hard-fails on both critical and high severity findings. Teams using the strict adoption tier would enable this hook.

The sixth hook is validate-suppressions. This runs at the pre-commit stage. It validates the suppressions file to ensure all entries have required governance fields, expiry dates are within limits, and high and critical suppressions have security team approval. It is written in Python using the PyYAML library for cross-platform compatibility.

The seventh hook is tflint. This runs at the pre-push stage. tflint is a Terraform linter that catches provider-specific issues that the other tools might miss, like invalid instance types or deprecated resource configurations.

The eighth and final hook is gitleaks. This runs at the pre-commit stage. Gitleaks is another secret detection tool that complements Trivy's secret scanning. Having two secret detection tools provides defense in depth for credential leakage.

Now let me explain two critical behaviors of the hook system that are very important for your presentation.

First, fail-open error handling. This is important. When a hook encounters an infrastructure error, such as a tool crash, a corrupted database, a network timeout, or any other non-finding error, the hook does not block the developer's commit. Instead, it prints a prominent warning and allows the commit to proceed. Only actual security findings, specifically when the scanning tool returns exit code one indicating it found vulnerabilities, will block the commit. Any other error code is treated as an infrastructure problem and fails open. The rationale is simple. We should never block a developer's work because of a tool malfunction. The CI layer provides the safety net to catch anything missed.

Second, the dual-wrapper dispatcher architecture. Every hook has two implementations. A bash script for Unix-based systems like macOS and Linux, and a PowerShell script for Windows. A central dispatcher script sits as the entry point. When the pre-commit framework calls a hook, it calls the dispatcher, which checks the operating system and routes to the appropriate implementation. This ensures the exact same security checks work identically regardless of the developer's operating system.

Section Break

Chapter Five: Multi-Cloud Configuration and Config Layering

Supporting multiple cloud providers is one of the most distinctive aspects of this solution. Let me explain how it works.

Each cloud provider has its own configuration directory. The Amazon Web Services directory contains a Checkov config, a tflint config, and a policy overlay. Azure and Google Cloud Platform have identical structures with provider-specific content. There is also a common directory for configurations that apply regardless of cloud provider.

Here is the key insight about the Checkov configuration. We use what we call a blocklist approach rather than an allowlist approach. Let me explain the difference because this was a significant design decision.

With an allowlist approach, the configuration file lists every specific check that should run. If a new check is added in a Checkov update, it will not run until someone explicitly adds it to the configuration. This means your security scanning can silently fall behind as new checks become available.

With a blocklist approach, all checks run by default. The configuration file only lists the checks that should be skipped, along with a justification for each exclusion. When Checkov releases a new check in an update, it automatically activates without any configuration changes. This keeps your scanning current and comprehensive. The tradeoff is that you need to maintain a list of known noisy or inapplicable checks, but we handle that centrally through shared exclusion lists maintained in this repository.

Now let me explain config layering, which is another important design decision. Each cloud provider's configuration is split into two layers. The first layer contains universal security checks. These are things like encryption requirements, public access prevention, and logging enforcement. These checks apply to every organization and are maintained centrally in this repository. The second layer is a policy overlay file. This contains organization-specific rules like tagging requirements, naming conventions, and custom policies. Consuming repositories are expected to replace this overlay file with their own organization's standards. This separation means organizations get strong security defaults out of the box while retaining the flexibility to enforce their own policies.

When a consuming repository runs the setup script, both layers are copied to a dot scanning configs directory within the repository. Hooks reference these local copies using explicit config file flags. This is important because it means the solution never touches or overwrites any existing configuration files in the consuming repository.

Section Break

Chapter Six: The CI/CD Layer and Reusable Workflows

The second defense layer is the reusable GitHub Actions workflow. Let me walk through how it works and what it provides.

The core workflow uses a workflow call trigger, which means other repositories can call it from their own workflow files. Think of it as a function that other repositories can invoke. The consuming repository passes in parameters like which Terraform directory to scan, which cloud provider to use, what severity levels to check, and whether to fail the pipeline on findings.

When the workflow runs on a pull request, it does several things. First, it runs Trivy for infrastructure as code scanning and secret detection. Second, it runs Checkov for policy validation. Third, it runs tflint for Terraform linting. Fourth, it uploads the scan results in SARIF format to GitHub's Security tab, which gives developers a centralized view of all security findings. Fifth, it posts a new comment on the pull request summarizing the scan results, including a severity breakdown, tool list, and the top findings in a collapsible section.

There are several important behaviors to understand about the workflow.

Suppression handling. The workflow includes a dedicated job that reads the suppressions file, filters out actively suppressed findings from the results, keeps expired suppression findings active, and produces the final pass or fail determination. In CI, expired suppressions are treated as active findings and will block the pipeline. This is different from the local hooks, which only warn about expired suppressions.

SARIF truncation. GitHub has limits on SARIF uploads. The file size limit is twenty-five megabytes and the result count limit is five thousand results. When scan results exceed either limit, the workflow sorts findings by severity with critical first, truncates to fit within the limits, and adds a warning annotation to the workflow summary noting how many findings were dropped.

Metrics collection. The workflow uploads a metrics JSON file as a GitHub Actions artifact. This enables cross-repository aggregation. A security manager can query these artifacts across all repositories using the GitHub API to get an organization-wide view of security scanning health.

Permission handling. Not all repositories have the same GitHub permissions. The workflow accepts boolean inputs for uploading SARIF and posting pull request comments, both defaulting to true. Repositories without the necessary permissions can explicitly set these to false.

Remediation links. For Checkov findings specifically, the workflow automatically generates documentation URLs pointing to Checkov's online documentation for each check ID. These links appear in both the SARIF output and the pull request comment, making it easy for developers to understand what the finding means and how to fix it.

Beyond the main scan workflow, there are two additional workflows. The performance check workflow runs timing tests for each hook against test fixtures on every pull request, enforcing the five-second-per-hook threshold. If any hook exceeds the threshold, the check fails, treating performance regressions as bugs. The bypass detection workflow uses heuristic analysis to detect when developers have bypassed pre-commit hooks and logs this to metrics.

Section Break

Chapter Seven: Installation Experience and Cross-Platform Support

One of our core principles is zero-friction installation. Let me walk through exactly how a developer gets started.

A developer opens their Terraform repository and runs a single command. On Windows, they would run the PowerShell setup script with a cloud provider parameter. On macOS or Linux, they would run the Python setup script with the same parameter. The Python script detects the operating system and uses the appropriate package manager. Homebrew for macOS, apt for Linux, and it delegates to the PowerShell script on Windows.

The setup script does several things automatically. It installs all required scanning tools, including Trivy, Checkov, tflint, Gitleaks, and the pre-commit framework. It verifies that installed versions meet the minimum requirements. For example, Trivy must be version zero point forty-eight or higher, Checkov must be version three point zero or higher, and tflint must be version zero point fifty or higher. It copies the appropriate cloud-specific configurations to the dot scanning configs directory. And it runs pre-commit install to activate the hooks for both the commit and push stages.

This is important. The setup script runs idempotently. This means if you run it again on a repository that already has scanning installed, it completes without errors. It does not reinstall tools that are already present and meets version requirements. It does not overwrite configurations that are already in place.

For Windows environments without administrator rights, there is a separate no-admin setup script that uses Scoop and pip for tool installation instead of Chocolatey.

Partial failure recovery is also handled. If some tools install successfully but one fails, perhaps tflint installation fails due to a network issue, the script reports what succeeded, what failed, and how to retry. It does not leave the system in an inconsistent state.

For multi-cloud repositories that contain Terraform for more than one cloud provider, the setup script configures a single primary provider. Additional providers must be configured manually by copying the relevant provider configs and setting up per-directory scanning. This is a documented manual process. The rationale for not automating multi-cloud setup is that the per-directory scanning configuration is highly specific to each repository's directory structure.

Section Break

Chapter Eight: Adoption Strategy and Tiered Templates

One of the biggest challenges in rolling out security scanning across an organization is developer resistance. If you turn on full security scanning overnight, developers will be overwhelmed by hundreds of findings and will simply bypass the tools. Our solution addresses this through a phased adoption approach using three tiers.

The first tier is called Starter. This is intended for the first thirty days of adoption, though these timelines are flexible guidelines, not mandatory deadlines. The starter tier includes six lightweight hooks. Trailing whitespace cleanup, end of file fixer, YAML syntax checking, private key detection, Terraform formatting, and secret scanning via Trivy secrets. These hooks are fast, non-disruptive, and address the most critical security concern, which is credential leakage, while also improving code quality. The goal of the starter tier is to get developers comfortable with the concept of pre-commit hooks running on every commit without overwhelming them with security findings.

The second tier is called Standard. This is intended for days thirty-one through sixty. The standard tier adds security scanning and linting hooks on top of everything in the starter tier. Specifically, it adds Terraform validation, tflint for provider-specific linting, and trivy-iac-critical for critical infrastructure misconfigurations. It also adds the suppression validation hook so teams can begin managing exceptions governance. These additional hooks run at the pre-push stage, meaning they only execute when developers push their changes, not on every commit.

The third tier is called Strict. This is intended for days sixty-one through ninety. The strict tier adds full enforcement. On top of everything in the standard tier, it adds trivy-iac-full for all severity levels, the checkov Terraform hook for comprehensive policy validation, and the checkov strict hook that hard-fails on critical and high findings. The commitizen hook for conventional commit messages is included as commented-out with instructions to opt in, because commit message conventions are a team workflow preference rather than a security concern.

Here is the key insight about the adoption tiers. Teams that miss a milestone do not get automatically escalated or rolled back. They simply extend their current phase until they meet the criteria. The timelines are guidelines designed to reduce pressure while maintaining forward momentum. Teams should feel empowered to move at their own pace.

Templates are designed as copy-once references. When a team wants to upgrade from starter to standard, they do not replace their entire configuration file. Instead, the tier upgrade guide lists the exact hooks to add. This lets teams preserve any customizations they have made while still upgrading their security posture.

For organizational adoption at scale, the solution includes an adoption playbook with documented phases, a champion network guide for identifying and supporting team champions, a troubleshooting guide covering the top ten common issues, and optionally, developer satisfaction survey templates. The business case documentation references only verified statistics, specifically the NIST thirty times cost multiplier and the IBM ten point two two million dollar average breach cost. We explicitly avoid unverified statistics like one hundred times or six hundred and forty times multipliers that circulate in some industry materials.

Section Break

Chapter Nine: Suppression Governance, Baselines, Metrics, and AI Agent Integration

This chapter covers four supporting capabilities that round out the solution. Each one addresses a specific real-world need.

Let us start with suppression governance. In any real codebase, there will be findings that cannot or should not be fixed immediately. Perhaps a finding is a false positive. Perhaps the risk is accepted at a governance level. Perhaps the fix requires a large refactoring effort that is planned for a future sprint. The suppression system provides a governed way to acknowledge and track these exceptions.

A suppression entry is added to a YAML file called scan suppressions. Each entry requires several governance fields. The rule ID identifies which specific check is being suppressed. The tool field identifies which scanning tool reported it. The reason field contains the business justification, which must be at least ten characters long. The owner field identifies who is responsible for the suppression, using an email address. The approved date and expiry date fields define when the suppression was approved and when it expires. Suppressions have a maximum lifetime of one hundred and eighty days.

For critical and high severity findings, an additional approved by field is required, indicating that the security team has reviewed and approved the suppression. This approval is based on an honor system with git blame providing the audit trail. There is no cryptographic verification.

The validation script enforces nine specific rules, checking things like required fields, valid dates, expiry limits, approval requirements, duplicate detection, rule ID format, and email format. When a suppression expires, CI workflows immediately treat the finding as active and block on it. Local hooks, however, only warn about expired suppressions without blocking, giving teams time to renew or remediate.

Now let us talk about baselines. When a team first adopts scanning on an existing codebase, they often have dozens or even hundreds of pre-existing findings. If every existing finding blocks commits, the tool becomes unusable. Baselines solve this problem.

A baseline is a snapshot of current scan findings stored as JSON. Once created, subsequent scans only report new findings that are not present in the baseline. This allows teams to adopt scanning without being overwhelmed by pre-existing technical debt. They can focus on preventing new issues while gradually addressing the baseline findings over time.

The baseline matching algorithm uses a tuple of rule ID and file path. Line numbers are intentionally excluded from the matching. This makes baselines resilient to code refactoring. If you move code around within a file, the baseline still recognizes the same finding. The lookup uses a hash-based algorithm for constant-time performance.

Baselines include a staleness warning. If a baseline is older than ninety days, scans will warn that the baseline may be outdated. Teams can refresh the baseline using a force parameter. For monorepo environments with multiple Terraform directories, baselines can be scoped to specific modules or directories.

Next, let us cover metrics. The solution provides three types of metrics that help security managers understand adoption health.

First, scan metrics. These include the bypass rate, which measures how often developers skip pre-commit hooks using the no-verify flag. The target is less than five percent. They also include the hook pass rate, which measures how often hooks pass on the first attempt. The target is greater than eighty percent.

Second, aggregated results. The aggregation script normalizes findings from all scanning tools into a unified JSON format. Each tool uses different severity naming, so the solution maps everything to a standard four-level scale: critical, high, medium, and low. For example, Trivy uses direct mapping. tflint maps error to high and warning to medium. Gitleaks maps all findings to high because any leaked secret is significant.

The aggregation script also handles cross-tool deduplication. When multiple tools detect the same underlying issue, for example when both Trivy and Checkov flag an unencrypted storage bucket, the findings are merged into a single result with a detected by array listing all reporting tools. The matching uses a tuple of file, resource, and category. The highest severity across tools is kept.

Third, performance metrics. The performance profiler measures per-hook execution time against the five-second threshold, reporting average, minimum, and maximum times. CI enforces these thresholds on every pull request.

All metrics are uploaded as GitHub Actions artifacts. Cross-repository aggregation is performed by querying artifacts across repos using the GitHub API. The CI workflow's pass and fail trend over ninety days provides the before and after measurement for tracking improvement over time.

Finally, let us discuss AI agent integration. This is a forward-looking capability that positions the solution for the growing trend of AI-assisted development.

AI coding agents, such as those that generate Terraform code autonomously, need a way to validate their output before committing. The solution provides two paths for AI agents.

The first path is through the standard pre-commit hooks. When an AI agent runs git commit, the hooks execute and write structured JSON findings to a file called last-scan dot json within the dot scanning directory. The agent can read this JSON file to understand what issues were found.

The second path is through a standalone Python script called scan dot py. This script runs all scans independently of the pre-commit framework and outputs unified JSON results. It accepts parameters for output format, severity filtering, cloud provider, and specific tools to run.

Here is the key capability for AI agents. The scan script supports an auto-fix flag. When enabled, it invokes Checkov with its built-in fix capability. For checks that Checkov can automatically remediate, the fix is applied directly to the Terraform files. The script then reports which findings were auto-fixed and which remain unfixable. This enables a scan, fix, rescan cycle that AI agents can perform autonomously.

The JSON output schema for agents includes additional fields beyond the standard unified result. These include whether auto-fix was applied, how many findings were auto-remediated, and per-finding flags indicating whether each issue was fixable and whether it was actually fixed.

Section Break

Chapter Ten: Key Design Decisions and Their Rationale

This chapter covers the twelve major design decisions that shaped the solution. Understanding the reasoning behind these decisions will help you answer questions during your presentation.

Decision one. Dual shell wrappers with OS-detecting dispatcher. We considered four options. Bash-only, which would fail on Windows without Git Bash. PowerShell-only, which is unavailable on default macOS and Linux installations. Python entry points, which would have slower startup times. And dual bash and PowerShell wrappers with a dispatcher. We chose the dual-wrapper approach because it provides full platform coverage with native performance. The tradeoff is maintaining more files, roughly twelve hook scripts, but the consistency across platforms is worth it. This decision is reversible. We could consolidate to a single approach later if the platform landscape changes.

Decision two. Blocklist Checkov configuration. We switched from an allowlist approach where the configuration explicitly lists every check to run, to a blocklist approach where all checks run by default and the configuration only lists exclusions. The key advantage is that new checks automatically activate when teams update Checkov. The tradeoff is needing to maintain shared exclusion lists for noisy checks. This is important. This decision is not easily reversible because it changes the behavior for consuming repositories.

Decision three. Skip Trivy database updates in hooks, update only in CI. Local hooks run with the skip database update flag for speed. The Trivy vulnerability database is only updated during CI workflow runs where network access is available and speed is less critical. This is how we achieve the five-second-per-hook performance target while still maintaining up-to-date vulnerability data in the authoritative CI scans.

Decision four. Baseline matching on rule ID and file path only, without line numbers. We considered three matching approaches. Matching on rule ID, file, and line number, which would be precise but would break on any refactoring that moves code to a different line. Matching on rule ID, file, and resource name, which would be resource-aware but does not work for all tools since tflint does not always report resource names. And matching on rule ID and file path only, which is resilient to refactoring. We chose the simpler approach for resilience. The tradeoff is that if the same rule triggers multiple times in the same file, all instances are considered baselined. This is an acceptable tradeoff for the benefit of not breaking baselines every time someone reformats their code.

Decision five. Python for cross-platform scripts. Python was chosen for the cross-platform setup script and the scan script because it is guaranteed to be available. Both the pre-commit framework and Checkov require Python, so any environment capable of running the hooks already has Python installed. PowerShell remains the primary scripting language for Windows-specific scripts. Python is used only for the cross-platform entry points.

Decision six. Suppression validation rewritten in Python. The original suppression validation was in PowerShell, which required the powershell-yaml module as an extra dependency. The rewrite uses Python's PyYAML library, which is already required by Checkov. This eliminates the extra dependency and ensures identical validation behavior across all operating systems.

Decision seven. Fail-open error handling for infrastructure errors. Only exit code one, which explicitly indicates security findings were detected, blocks a commit. Every other non-zero exit code is treated as an infrastructure error and fails open with a warning. The rationale is that we should never block developers because of a tool malfunction. The CI layer provides the safety net. This decision is reversible. A future strict mode could be added for teams that want fail-closed behavior for all errors.

Decision eight. Priority-based SARIF truncation. GitHub's limits on SARIF uploads are hard constraints. Twenty-five megabytes for file size and five thousand results for result count. When these limits are exceeded, we truncate by keeping the highest-severity findings first and dropping low-severity findings. A warning annotation notes the truncation. This is not reversible because it is driven by GitHub's requirements.

Decision nine. Dual paths for AI agent integration. Agents can consume scan results either through the pre-commit hooks, which write JSON alongside terminal output, or through the standalone scan dot py script, which runs independently of the pre-commit framework. Having both paths provides flexibility for different agent workflows. An agent integrated into the git workflow uses hooks. An agent that wants to scan before committing uses scan dot py directly.

Decision ten. Cross-tool deduplication matching on file, resource, and category. When Trivy and Checkov both detect an unencrypted S3 bucket, we merge them into a single finding with a detected by array listing both tools. The highest severity across tools is kept. This reduces noise in reports without losing information about which tools detected the issue.

Decision eleven. Two-file config layering with policy overlays. Universal security checks like encryption and public access prevention are maintained centrally. Organization-specific policies like tagging and naming conventions live in a separate overlay file that consuming repos replace. This separation means organizations get strong defaults while retaining flexibility.

Decision twelve. Minimum version ranges rather than exact pins. We enforce minimums like Trivy greater than or equal to version zero point forty-eight, not exact versions like Trivy equals version zero point forty-eight point three. This allows patch and minor upgrades while ensuring required features are available. The setup script validates versions at install time.

Section Break

Chapter Eleven: Implementation Strategy, Scope, and Team Structure

Let me now walk through how this project is being implemented. This context will help you discuss timelines and approach during your presentation.

The project is organized into seventy-nine tasks across fifteen phases. The tasks are grouped by user story, meaning each group represents a complete, independently testable capability.

There are nine user stories, each with a priority level. Priority one covers the most critical stories. Story one is about developers installing scanning. Story two is about developers committing secure code with hooks. Story three is about CI/CD enforcing security on pull requests. Priority two covers important but secondary stories. Story four is about teams adopting via the phased tier rollout. Story five is about security engineers managing suppressions. Story six is about security managers reviewing metrics. Story nine is about AI agents scanning and auto-fixing code. Priority three covers lower-priority stories. Story seven is about developers baselining existing technical debt. Story eight is about platform engineers validating performance.

The minimum viable product, or MVP, consists of thirty-three tasks spanning phases one through four plus phase twelve. These cover the setup infrastructure, the foundational prerequisites, developer installation, all eight hooks, and all cloud configurations. Completing the MVP means a developer can install scanning and have working pre-commit hooks that catch critical misconfigurations and secrets across all three cloud providers.

The implementation follows a strict dependency graph. Phases one and two are blocking prerequisites that must complete before any other work can begin. Phase one creates the directory structure, shared libraries, and schemas. Phase two creates the hook manifest and test fixtures. After these two phases are complete, phases three through twelve can fan out and execute in parallel, as each user story is independent.

Phases thirteen through fifteen are convergence phases that depend on all implementation work being complete. Phase thirteen covers documentation updates. Phase fourteen covers testing, including unit tests, integration tests, and coverage measurement. Phase fifteen covers polish and final validation.

For the implementation team, the project is designed for parallel execution by four specialized agents. The first agent focuses on hook development, creating all the bash and PowerShell hook scripts, the dispatcher, and shared libraries. The second agent focuses on Python scripting, creating the setup scripts, validation scripts, scan script, and JSON schemas. The third agent focuses on infrastructure, handling cloud configurations, GitHub Actions workflows, and adoption templates. The fourth agent focuses on quality, handling test fixtures, remaining PowerShell scripts, documentation, testing, and release polish.

Each agent owns a distinct set of files to avoid conflicts. The hooks engineer exclusively owns the hooks directory and the pre-commit hooks manifest. The Python engineer exclusively owns the Python scripts and schemas. The infrastructure engineer exclusively owns the configurations, workflows, and templates directories. The quality engineer exclusively owns the tests and docs directories.

Within each phase, many tasks are marked as parallelizable. Phase four alone has eleven parallel tasks for creating hook wrappers. Phase twelve has twelve parallel tasks for cloud configurations. Phase thirteen has eight parallel documentation tasks. Phase fourteen has six parallel testing tasks. In total, there are over forty-five parallel opportunities across six phases.

Section Break

Chapter Twelve: Success Criteria, Edge Cases, and Key Takeaways

Let us wrap up with the measurable success criteria, important edge cases, and the key takeaways for your presentation.

The solution defines nine measurable success criteria. First, consuming repos must complete setup in under five minutes using a single script on Windows, macOS, or Linux. Second, pre-commit hooks must complete in under ten seconds for typical Terraform commits. Third, the hook bypass rate must stay below five percent across consuming repositories. Fourth, the hook pass rate must exceed eighty percent on first attempt. Fifth, all three cloud providers must have complete configuration coverage. Sixth, test fixtures must achieve one hundred percent expected outcome accuracy. Seventh, consuming repos should achieve a forty percent reduction in CI security failures within ninety days of adoption. Eighth, hooks must produce identical pass and fail outcomes whether run locally or in CI. Ninth, AI agents must be able to parse scan output and auto-fix at least Checkov-fixable findings without human intervention.

Now let me cover the most important edge cases that your audience might ask about.

What happens when a developer has no internet connection? After initial setup, all scanning runs offline. Hooks use the skip database update flag. The Trivy vulnerability database is cached locally. No code is ever uploaded to external services.

What happens when a developer bypasses hooks with the no-verify flag? The bypass is detected by the bypass detection workflow in CI and logged to metrics. The CI layer then performs a comprehensive scan on the pull request regardless. Think of bypass detection as an audit trail, not a prevention mechanism. CI is the real enforcement gate.

What happens in a monorepo with multiple Terraform directories? The hooks detect which directories contain changed files and only scan those directories. This keeps scanning within the five-second budget even in large repositories.

What happens when a scan tool crashes? The hook wrapper catches the unexpected exit code and fails open. A prominent warning is displayed, but the commit proceeds. The CI layer catches anything missed.

What happens when Checkov releases new checks? Because we use the blocklist approach, new checks automatically activate on tool update. A shared exclusion list filters known noisy checks, but new genuine security checks start running immediately.

What happens when SARIF output is too large? The workflow truncates to the highest severity findings first and adds a warning annotation. Low-severity findings are dropped to fit within GitHub's limits.

What happens when a repo has both Amazon Web Services and Azure Terraform? The setup script configures one primary provider. Additional providers must be configured manually with per-directory scanning. This is documented but intentionally not automated because the directory structure varies too much between repositories.

What happens when a suppression expires? In CI, the finding immediately becomes active and blocks the pipeline. Locally, the hooks warn but do not block, giving teams time to renew or remediate.

Section Break

Now let me give you the key takeaways for your presentation.

First, this is a shift-left security solution. We catch vulnerabilities when they are cheapest to fix, during the coding phase, not in production.

Second, it uses a two-layer defense model. Local hooks provide fast feedback on every commit. CI provides comprehensive enforcement on every pull request. Together, they ensure nothing slips through.

Third, it is truly reusable and multi-cloud. One centrally maintained repository serves all teams across Amazon Web Services, Azure, and Google Cloud Platform. Cloud-specific behavior is driven entirely by configuration, not code changes.

Fourth, developer experience is paramount. Five-minute setup. Ten-second commits. Phased adoption. Override-friendly. Fail-open for infrastructure errors. Every design decision was made with developer productivity in mind.

Fifth, governance is built in. Suppressions require justification and expiry. Baselines track technical debt. Metrics measure adoption health. Everything is auditable through git history.

Sixth, it is future-ready. AI agent integration with structured JSON output and auto-fix capabilities positions the solution for the growing trend of autonomous coding workflows.

Seventh, the implementation is comprehensive. Seventy-nine tasks across fifteen phases, covering ninety-eight functional requirements, seventeen non-functional requirements, fifteen Kiro requirements with two hundred and forty-five acceptance criteria, and eighty quality checklist items.

And eighth, the architecture is designed for evolution. Version pinning gives consuming teams control. Semantic versioning communicates risk. The blocklist config approach automatically inherits new security checks. Config layering separates universal security from organizational policy. All of these patterns ensure the solution grows and improves without disrupting the teams that depend on it.

This concludes your comprehensive audio presentation guide for the Reusable Terraform Security Scanning Solution. Good luck with your presentation, and safe travels during your commute.
