# Archive

This folder keeps historical material: early specifications, research notes, audits
and test evidence. It is **not maintained** and is **not adopter guidance**. Much of it
describes older behaviour, older versions or plans that changed.

For current behaviour, start at the [documentation index](../docs/README.md) and the
[changelog](../CHANGELOG.md).

| Item | What it was |
|---|---|
| [specs/001-security-scanning-spec/](specs/001-security-scanning-spec/) | The original specification, plan, task list and interface contracts for the Terraform-only scanner (v1). |
| [specs/002-scan-fix-platform/](specs/002-scan-fix-platform/) | The specification and plan that extended the scanner to application code and added the fix loop (v2). |
| [ai-research/](ai-research/) | Early research notes and a framework design draft written before the platform was built. |
| [presentation-slides.md](presentation-slides.md) | Slides that presented the first design. |
| [agent-team-implementation-guide.md](agent-team-implementation-guide.md) | Notes on how the v1 specification was implemented with a team of AI coding agents. |
| [CLAUDE-CODE-TEST-PROMPT.md](CLAUDE-CODE-TEST-PROMPT.md) | A prompt once used to test an install in a consuming repository with an AI agent. |
| [MIGRATION-ANALYSIS.md](MIGRATION-ANALYSIS.md) | The analysis that planned the move from a Terraform-only scanner to the scan and fix platform. |
| [V3-BEHAVIOUR-AUDIT.md](V3-BEHAVIOUR-AUDIT.md) | An audit of the user-visible changes in v3.0.0 to v3.0.6. |
| [V3-WALKTHROUGH-RESULTS.md](V3-WALKTHROUGH-RESULTS.md) | Evidence from one local walkthrough of the setup guide during v3. |
| [SECRET-SCANNER-EVALUATION.md](SECRET-SCANNER-EVALUATION.md) | A comparison of secret scanners that informed the choice to keep Gitleaks as the local hook. |
