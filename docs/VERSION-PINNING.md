# Version Pinning Guide

How to manage versions of auto-code-scanning in your repository.

## How Version Pinning Works

Consuming repos pin to a specific version via the `rev:` field in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v1.0.0    # Pinned to exact version
    hooks:
      - id: trivy-iac-critical
      - id: trivy-secrets
      - id: gitleaks
```

The `rev:` field accepts:
- **Git tags** (recommended): `v1.0.0`, `v1.2.3`
- **Branch names**: `main` (not recommended for production)
- **Commit SHAs**: `abc1234` (exact reproducibility but hard to update)

## SemVer Policy

This repository follows Semantic Versioning (SemVer):

| Change Type | Version Bump | Examples |
|-------------|-------------|---------|
| **Breaking** | Major (X.0.0) | Hook ID renamed, exit code semantics changed, removed hook |
| **Feature** | Minor (0.X.0) | New hook added, new script option, new config field |
| **Fix** | Patch (0.0.X) | Bug fix, config correction, documentation update |

### What Constitutes a Breaking Change

- Renaming or removing a hook ID (hook IDs are stable contracts)
- Changing exit code meanings (e.g., exit 1 no longer means "findings")
- Removing a script or changing its required arguments
- Changing the structure of `.scanning/last-scan.json` in backward-incompatible ways
- Removing fields from `schemas/unified-results.schema.json`

### What Is NOT a Breaking Change

- Adding new hooks (consumers must opt in)
- Adding optional parameters to scripts
- Adding fields to JSON schemas (additive)
- Changing tool version minimums (documented in release notes)
- Internal refactoring of hook implementations

## Upgrading Versions

### Automatic Update

```bash
# Update all pre-commit repos to latest tag
pre-commit autoupdate
```

This updates the `rev:` field in `.pre-commit-config.yaml` to the latest tagged release.

### Manual Update

Edit `.pre-commit-config.yaml` directly:

```yaml
repos:
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: v1.1.0    # Changed from v1.0.0
```

### Verify After Upgrade

```bash
# Run all hooks to verify compatibility
pre-commit run --all-files

# Clear cache if hooks behave unexpectedly
pre-commit clean
pre-commit install
```

## CI/CD Workflow Pinning

For the reusable GitHub Actions workflow, pin using `@` syntax:

```yaml
jobs:
  security:
    uses: agenticcodingops/auto-code-scanning/.github/workflows/reusable-scan.yml@v1.0.0
```

Update the `@` reference when upgrading. Unlike pre-commit, there is no automatic update mechanism for workflow references.

## Recommended Practices

1. **Pin to exact versions in production**: Use `v1.0.0`, not `main`
2. **Review release notes before upgrading**: Check for breaking changes
3. **Test after upgrading**: Run `pre-commit run --all-files` to verify
4. **Upgrade regularly**: Stay within 1-2 minor versions of latest for security patches
5. **Use the same version in pre-commit and CI**: Avoid drift between local and CI scanning

## Checking Current Version

```bash
# See what version is pinned
grep "rev:" .pre-commit-config.yaml

# See available versions
git ls-remote --tags https://github.com/agenticcodingops/auto-code-scanning
```

## Rollback

If an upgrade causes issues:

1. Edit `.pre-commit-config.yaml` and revert the `rev:` to the previous version
2. Clear the pre-commit cache:
   ```bash
   pre-commit clean
   pre-commit install
   ```
3. Verify hooks work:
   ```bash
   pre-commit run --all-files
   ```
