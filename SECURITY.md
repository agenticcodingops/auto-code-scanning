# Security policy

auto-code-scanning runs scanners and, if you enable it, an AI fix loop with write access
to your repository. We take reports about its own weaknesses seriously.

## Supported versions

Security fixes are released for the latest minor release line only.

| Version | Supported |
| --- | --- |
| 3.1.x | Yes |
| 3.0.x and older | No |

Fixes ship as a new patch release. Upgrade to it as described in
[VERSION-PINNING](docs/VERSION-PINNING.md).

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a vulnerability.**

Report it privately through GitHub private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Fill in the form and submit it.

The direct link is
<https://github.com/agenticcodingops/auto-code-scanning/security/advisories/new>.
Only the maintainers can see the report.

## What to include

- The version (release tag or commit SHA) you tested.
- The affected part: a hook, a reusable workflow, a script, a template or the fix loop.
- Step-by-step instructions to reproduce, with a minimal repository or configuration if you can.
- What an attacker can do, and what they need first (for example, the ability to open a
  pull request from a fork).
- Any logs or output, with secrets removed.

## What to expect

This project is maintained on a best-effort basis. There is no guaranteed response
time. We will acknowledge the report, investigate it, and keep you updated in the
advisory. When a fix is released, we publish the advisory and credit you unless you
ask us not to.

## Scope

In scope: weaknesses in this repository's hooks, scripts, reusable workflows,
templates and the fix loop. For example, a way to make a scan pass when it should
block, to bypass the fix loop's path or label gates, or to leak a secret from a workflow.

Out of scope: vulnerabilities in the third-party scanners themselves (Trivy, Checkov,
TFLint, Gitleaks, Semgrep and others). Report those to their own projects.

The threat model and trust boundaries are described in the
[security model](docs/SECURITY-MODEL.md).
