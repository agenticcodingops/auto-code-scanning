# Tier Upgrade Guide

This guide lists the exact changes needed when upgrading between adoption tiers. Templates are copy-once references -- teams manually merge new hooks into their existing `.pre-commit-config.yaml` to preserve any customizations.

Phase timelines (30/60/90 days) are flexible guidelines. Teams that need more time extend the current phase until criteria are met. There is no mandatory rollback or escalation.

## Starter to Standard

**When to upgrade**: Team has been using starter hooks for ~30 days with >80% pass rate on first commit attempt.

### Hooks to Add

Add the following to your `.pre-commit-config.yaml`:

**pre-commit-hooks repo** -- add these hooks:

```yaml
      - id: check-json
```

Update `check-yaml` to add unsafe flag:

```yaml
      - id: check-yaml
        args: ["--unsafe"]
```

**pre-commit-terraform repo** -- add these hooks:

```yaml
      - id: terraform_validate
      - id: terraform_tflint
        args:
          - "--args=--config=__GIT_WORKING_DIR__/.scanning/configs/.tflint.hcl"
```

**auto-code-scanning repo** -- add this hook:

```yaml
      - id: trivy-iac-critical
        stages: [pre-commit]
```

### Hooks NOT Changed

Keep all existing starter hooks as-is:
- trailing-whitespace
- end-of-file-fixer
- check-yaml (update args as shown above)
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
      - id: checkov
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
- All pre-commit-terraform hooks (terraform_fmt, terraform_validate, terraform_tflint)
- trivy-secrets
- trivy-iac-critical

### What Changes at Strict

| Hook | Stage | Purpose |
|------|-------|---------|
| trivy-iac-full | pre-push | Full severity IaC scan (CRITICAL + HIGH + MEDIUM) |
| checkov | pre-push | CIS Benchmark policy validation |
| checkov-strict | pre-push | Hard-fail on CRITICAL + HIGH findings |
| validate-suppressions | pre-commit | Validates suppression file governance |
| terraform_docs | pre-commit | Auto-generate Terraform docs |

---

## Preserving Customizations

When upgrading, do NOT replace your entire `.pre-commit-config.yaml`. Instead:

1. Open your current config and the target tier template side by side
2. Add only the new hooks listed above
3. Keep any custom `args`, `exclude`, or `files` overrides you have added
4. Keep any additional third-party hooks your team has added
5. Run `pre-commit run --all-files` to verify everything works

## Version Pinning

All templates pin to `rev: v1.0.0`. To update:

```bash
pre-commit autoupdate --repo https://github.com/agenticcodingops/auto-code-scanning
```
