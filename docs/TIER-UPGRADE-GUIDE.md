# Tier Upgrade Guide

Install through [Getting started](SETUP-GUIDE.md) first. The differences below are
for the Terraform pre-commit templates at the selected revision. Lefthook uses
the same manifest for every tier; changing tier configuration does not rewrite it.
Compare complete templates before changing an existing installation.

Phase timelines (30/60/90 days) are flexible guidelines. Teams that need more time extend the current phase until criteria are met. There is no mandatory rollback or escalation.

## Starter to Standard

**When to upgrade**: Team has been using starter hooks for ~30 days with >80% pass rate on first commit attempt.

### Hooks to Add

Add the following to your `.pre-commit-config.yaml`:

**pre-commit-hooks repo** -- add these hooks:

```yaml
      - id: check-json
```

`check-yaml` keeps its existing arguments.

**pre-commit-terraform repo** -- add these hooks:

```yaml
      - id: terraform_validate
```

**auto-code-scanning repo** -- add these hooks:

```yaml
      - id: tflint
        stages: [pre-push]
      - id: gitleaks
        stages: [pre-commit]
      - id: trivy-iac-critical
        stages: [pre-commit]
```

### Hooks NOT Changed

Keep all existing starter hooks as-is:
- trailing-whitespace
- end-of-file-fixer
- check-yaml
- detect-private-key
- terraform_fmt
- trivy-secrets

### Criteria for Moving to Strict

- >50% of team using standard hooks
- <5% bypass rate
- Team comfortable with hook workflow

---

## Standard to Strict

**When to upgrade**: Team has been using standard hooks for ~30 days with >80% pass rate and <5% bypass rate.

### Hooks to Add

**pre-commit-hooks repo** -- add these hooks:

```yaml
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: check-merge-conflict
```

**pre-commit-terraform repo** -- add this hook:

```yaml
      - id: terraform_docs
```

**auto-code-scanning repo** -- add these hooks:

```yaml
      - id: trivy-iac-full
        stages: [pre-push]
      - id: checkov-strict
        stages: [pre-push]
      - id: validate-suppressions
        stages: [pre-commit]
```

### Optional Hooks

Commitizen (conventional commit enforcement) is available but opt-in:

```yaml
  # Uncomment to enable conventional commit enforcement
  # - repo: https://github.com/commitizen-tools/commitizen
  #   rev: v3.29.1
  #   hooks:
  #     - id: commitizen
  #       stages: [commit-msg]
```

### Hooks NOT Changed

Keep all existing standard hooks as-is:
- All pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, detect-private-key)
- All pre-commit-terraform hooks (terraform_fmt, terraform_validate)
- trivy-secrets
- gitleaks
- tflint (pre-push)
- trivy-iac-critical

### What Changes at Strict

| Hook | Stage | Purpose |
|------|-------|---------|
| trivy-iac-full | pre-push | Full severity IaC scan (CRITICAL + HIGH + MEDIUM) |
| checkov-strict | pre-push | Hard-fail on CRITICAL + HIGH findings |
| validate-suppressions | pre-commit | Validates suppression file governance |
| terraform_docs | pre-commit | Auto-generate Terraform docs |

---

## Preserving Customizations

When upgrading, do NOT replace your entire `.pre-commit-config.yaml`. Instead:

1. Save reviewed `.scanning/configs/`, caller workflows and runner configuration
   (`lefthook.yml` or `.pre-commit-config.yaml`) externally, including full-SHA pins
   and customized editor hooks, before making any of the changes below: this captures
   the pre-upgrade state, not a copy already modified by them
2. Compare `scan-config.yaml` with the target tier's configuration defaults and
   merge reviewed settings deliberately. Setup preserves an existing config unless
   forced; `--enable-fix-loop` alone does not change an existing disabled setting
3. Open your current runner config and the target tier template side by side
4. Add only the new hooks listed above
5. Keep any custom `args`, `exclude`, or `files` overrides you have added
6. Keep any additional third-party hooks your team has added
7. Review custom settings against the current security contract; the setup verifier
   checks exact shipped hook settings, so customized manifests need separate review
8. Begin setup/verification with the required entries from the new tier template;
   reinstall the push transaction adapter through setup
9. Compare overwritten policy/workflows, restore approved customizations and full
   SHA pins after template verification, then stage a real change and make a scanned commit as in [consumer acceptance](TESTING-GUIDE-CONSUMING-REPO.md)

## Version Pinning

All templates pin `rev:` to the release they ship in (`v1.0.0` in releases up to and including v2.3.1). To update:

```bash
pre-commit autoupdate --repo https://github.com/agenticcodingops/auto-code-scanning
```

`autoupdate` alone changes only runner revisions. Resolve the target release's full
SHA, re-vendor complete hooks, shared scripts and schemas, and align every workflow
and helper pin using [Getting started upgrades](SETUP-GUIDE.md#10-upgrade-between-releases).
If strict is for scanning only, set `fix_loop.enabled: false`: its configuration
template enables that setting by default, independently of installing a fix caller.
