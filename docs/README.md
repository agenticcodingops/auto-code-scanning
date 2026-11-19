# Documentation

The guides are listed in the order you are likely to need them, from "what is this?"
to day-to-day operation and reference. Each part builds on the one before it.

## 1. What it is and how it works

- [Project overview](../README.md): what the platform does, its two layers and four
  enforcement points, and where to start.
- [Architecture](ARCHITECTURE.md): how the hooks, reusable workflows, templates and
  configuration fit together, with diagrams.
- [Security model](SECURITY-MODEL.md): the threats the platform defends against,
  especially for the AI fix loop, and the controls that enforce each boundary.

## 2. Quick start and setup

- [Quick start (5 minutes)](QUICK-START-5MIN.md): the shortest path to a first
  scanned commit.
- [Prerequisites](PREREQUISITES.md): the tools and versions to install on Windows,
  macOS or Linux before setup.
- [Getting started](SETUP-GUIDE.md): the complete setup guide, from choosing a tier
  to hooks, CI, first scans, exceptions and upgrades.
- [Tier upgrade guide](TIER-UPGRADE-GUIDE.md): what changes when you move from
  starter to standard to strict, and how to do it.
- [Consumer acceptance tests](TESTING-GUIDE-CONSUMING-REPO.md): checks that prove an
  installed repository blocks and reports what it should.
- [Terraform module adoption](TERRAFORM-MODULE-ADOPTION.md): extra steps for a
  repository that publishes a Terraform module.
- [Examples](../examples/): small working repositories to copy from.

## 3. Scanning application code and other clouds

- [Application code scanning](APP-CODE-SCANNING.md): how C#/.NET, TypeScript/JavaScript
  and SQL are scanned locally and in CI.
- [Multi-cloud configuration](MULTI-CLOUD.md): the per-cloud scanner settings for
  AWS, Azure and GCP.
- [Turning local scanning on and off](LOCAL-HOOKS-TOGGLE.md): how to pause local hooks
  without uninstalling them or affecting CI.
- [Suppression governance](SUPPRESSION-GOVERNANCE.md): how to approve, record and
  review an exception for a finding, and the registry format.
- [Severity mapping](SEVERITY-MAPPING.md): how each scanner's severity becomes
  CRITICAL, HIGH, MEDIUM or LOW, and what blocks.

## 4. The AI fix loop

- [Fix loop](FIX-LOOP.md): how the opt-in loop proposes, verifies and pushes a minimal
  fix on a labelled pull request, and how to enable it.
- [AI agent guide](AI-AGENT-GUIDE.md): how AI coding agents call the scanner, read its
  JSON report and work with the hooks.
- [Claude Code in-session bundle](../templates/claude/README.md): the hooks that scan an
  agent's edits inside the session so it can correct them before committing.

## 5. Running it day to day

- [Developer workflow](DEVELOPER-WORKFLOW.md): what happens when you commit and push,
  and how to deal with a blocked commit.
- [Consumer operations](consumer-repo-setup-guide.md): controls and maintenance after
  adoption, including how to uninstall.
- [Version pinning](VERSION-PINNING.md): how to pin a release by commit SHA and how to
  upgrade safely.
- [Bump the scan](BUMP-THE-SCAN.md): a runbook for moving a repository's scan to a new
  release and recording what changed.
- [Pin freshness](PIN-FRESHNESS.md): the weekly report of version pins with newer
  upstream releases.
- [Consumer migration](CONSUMER-MIGRATION.md): how to move an existing inline scan or
  fix loop onto the platform, and the migrations that v3 releases require.
- [Troubleshooting](TROUBLESHOOTING.md): fixes for common install, hook and CI
  problems.
- [Performance optimization](PERFORMANCE-OPTIMIZATION.md): how to measure hook times
  and keep local scanning fast.

## 6. Rolling it out to a team

- [Adoption playbook](ADOPTION-PLAYBOOK.md): a phased rollout plan, champions,
  metrics and how to handle pushback.
- [Roadmap](ROADMAP.md): what each major version delivered and possible future work.

## 7. Reference

- [Hook reference](HOOK-REFERENCE.md): every hook ID, its stage, what it checks and its
  exit codes.
- [Reusable workflows](REUSABLE-WORKFLOWS.md): every input, output and permission of
  the reusable workflows. This is the single source of truth for workflow inputs.

### Maintainers and contributors

- [Contributing](../CONTRIBUTING.md): how to set up a checkout, run the tests and open a
  pull request.
- [Maintainer guide](MAINTAINERS.md): how releases are cut and how to recover from a
  bad release.
- [Pin inventory](maintainers/PIN-INVENTORY.md): every version pin in this repository
  and where it lives.

## Historical material

The [archive](../archive/README.md) keeps early specifications, research and audits.
It is not maintained and may describe old behaviour.
