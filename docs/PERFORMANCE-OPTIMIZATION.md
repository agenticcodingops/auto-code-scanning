# Performance Optimization Guide

This guide covers strategies for optimizing pre-commit hook performance to maintain developer experience while ensuring security scanning effectiveness.

## Performance Targets

Based on research and developer experience studies:

| Metric | Target | Rationale |
|--------|--------|-----------|
| Individual hook | < 5 seconds | Hooks over 5s see increased bypass rates |
| Total pre-commit | < 10 seconds | Total time for all pre-commit stage hooks |
| Total pre-push | < 60 seconds | Acceptable for less frequent operation |
| Full scan (--all-files) | < 3 minutes | For periodic complete scans |

## Profiling Hook Performance

Before optimizing, measure current performance:

```powershell
# Profile all hooks
.\scripts\profile-hook-performance.ps1

# With more iterations for accuracy
.\scripts\profile-hook-performance.ps1 -Iterations 5

# Verbose output
.\scripts\profile-hook-performance.ps1 -ShowVerbose
```

### Sample Output

```
Hook Times (averaged over 3 iterations):
-----------------------------------------
terraform_checkov              15.23s [SLOW] ====================================
terraform_trivy                 8.45s [SLOW] ===================
terraform_validate              4.12s [OK]   =========
terraform_tflint                3.87s [OK]   ========
terraform_fmt                   1.23s [OK]   ===
trivy-secrets                   2.45s [OK]   =====
trailing-whitespace             0.15s [OK]   =
-----------------------------------------
TOTAL                          35.50s

Recommendations:
  - MIGRATE: Move 'terraform_checkov' to pre-push stage (avg: 15.23s)
  - OPTIMIZE: Consider caching for 'terraform_trivy' (avg: 8.45s)
```

## Optimization Strategies

### 1. Stage Migration

Move slow hooks from pre-commit to pre-push:

```yaml
# .pre-commit-config.yaml

# FAST - Keep at pre-commit stage
- id: terraform_fmt
  stages: [pre-commit]

- id: trivy-terraform-critical
  stages: [pre-commit]  # Quick CRITICAL-only scan

# SLOW - Move to pre-push stage
- id: terraform_checkov
  stages: [pre-push]    # Full policy scan at push time

- id: terraform_trivy
  stages: [pre-push]    # Full severity scan at push time
```

**Recommended Staging:**

| Hook | Typical Time | Recommended Stage |
|------|--------------|-------------------|
| trailing-whitespace | < 1s | pre-commit |
| end-of-file-fixer | < 1s | pre-commit |
| check-yaml | < 1s | pre-commit |
| terraform_fmt | 1-2s | pre-commit |
| trivy-secrets | 2-3s | pre-commit |
| trivy-terraform-critical | 3-5s | pre-commit |
| terraform_tflint | 3-5s | pre-commit |
| terraform_validate | 3-5s | pre-commit |
| terraform_trivy (full) | 8-15s | pre-push |
| terraform_checkov | 15-30s | pre-push |
| validate-terraform-modules | 30-60s | pre-push |

### 2. Caching

Enable caching for tools that support it:

#### Trivy Database Caching

```powershell
# Set cache directory (add to profile)
$env:TRIVY_CACHE_DIR = "$env:USERPROFILE\.trivy-cache"

# Update database periodically (not on every run)
trivy image --download-db-only
```

#### Pre-commit Caching

Pre-commit caches hook installations automatically. Clear if needed:

```bash
# Clear cache
pre-commit clean

# Reinstall hooks
pre-commit install
```

#### tflint Plugin Caching

```bash
# Initialize plugins once
tflint --init

# Plugins cached at ~/.tflint.d/plugins/
```

### 3. Parallel Execution

Some hooks can run in parallel. Pre-commit runs hooks sequentially by default, but you can:

#### Run Independent Hooks in Parallel

Create a wrapper script that runs multiple tools concurrently:

```powershell
# scripts/parallel-scan.ps1
$jobs = @(
    { trivy config . --severity CRITICAL,HIGH },
    { tflint --config=.tflint.hcl }
)

$jobs | ForEach-Object -Parallel { & $_ } -ThrottleLimit 3
```

#### Use Trivy's Built-in Parallelism

```yaml
# In hook args
- id: terraform_trivy
  args:
    - --args=--parallel=4
```

### 4. Scope Limiting

Reduce what's scanned:

#### Scan Only Changed Files

Pre-commit does this by default for staged files. For manual runs:

```bash
# Run on specific files only
pre-commit run --files terraform/modules/s3/main.tf
```

#### Skip Directories

```yaml
# .pre-commit-config.yaml
exclude: |
  (?x)^(
    examples/.*|
    tests/.*|
    \.terraform/.*
  )$
```

#### Use Lightweight Checks for Pre-commit

```yaml
# Quick CRITICAL-only scan at pre-commit
- id: trivy-terraform-critical
  entry: trivy config . --severity CRITICAL --exit-code 1 --quiet
  stages: [pre-commit]

# Full scan at pre-push
- id: terraform_trivy
  args:
    - --args=--severity=CRITICAL,HIGH,MEDIUM
  stages: [pre-push]
```

### 5. Skip Slow Hooks When Needed

For urgent commits (use sparingly):

```bash
# Skip specific slow hooks
SKIP=terraform_checkov,terraform_trivy git commit -m "message"

# Skip all hooks (NOT recommended)
git commit --no-verify -m "urgent: message"
```

Track skip usage in metrics to identify friction points.

## Tool-Specific Optimizations

### Trivy

```yaml
args:
  - --args=--skip-dirs=.terraform,examples,tests  # Skip non-production code
  - --args=--cache-dir=$HOME/.trivy-cache         # Use cache
  - --args=--timeout=5m                            # Set reasonable timeout
  - --args=--quiet                                 # Reduce output
```

### Checkov

```yaml
# .checkov.yaml
quiet: true                    # Reduce output
compact: true                  # Compact output
download-external-modules: false  # Don't download modules
deep-analysis: false           # Disable for speed (enable in CI)

skip-path:
  - examples
  - tests
  - .terraform
```

### tflint

```hcl
# .tflint.hcl
config {
  # Disable slow rules if not needed
  disabled_by_default = false
}

# Focus on critical rules only
rule "terraform_deprecated_interpolation" {
  enabled = true
}
```

## Measuring Improvement

After optimization:

```powershell
# Re-profile
.\scripts\profile-hook-performance.ps1

# Compare with baseline
# Check .scan-results/performance/ for history
```

### Success Criteria

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Pre-commit total | 35s | 8s | < 10s |
| Slowest hook | 15s | 4s | < 5s |
| Hooks over target | 3 | 0 | 0 |

## Troubleshooting Slow Hooks

### Common Causes

1. **Network calls** - Database updates, external module downloads
2. **Large file scans** - Scanning generated files, binaries
3. **Deep analysis** - Recursive scanning, cross-file analysis
4. **Missing cache** - Cold start after cache clear

### Diagnostics

```powershell
# Time individual command
Measure-Command { trivy config . --severity CRITICAL }

# Check what's being scanned
trivy config . --list-all-pkgs --format json | Select-String "Target"

# Verify cache is being used
$env:TRIVY_DEBUG = "true"
trivy config .
```

## Related Documentation

- [HOOK-REFERENCE.md](./HOOK-REFERENCE.md) - Hook configuration
- [METRICS-DASHBOARD.md](./METRICS-DASHBOARD.md) - Performance metrics
- [SETUP-GUIDE.md](./SETUP-GUIDE.md) - Initial setup
