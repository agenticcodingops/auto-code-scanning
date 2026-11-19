# Performance Optimization Guide

Slow hooks get skipped. This guide shows how to measure hook times and keep local
scanning fast without weakening what CI enforces.

## Performance Targets

These are the platform's own targets. `scripts/profile-hook-performance.ps1` flags hooks
against them, and the `performance-check.yml` workflow enforces the same limits on this
repository's test fixtures.

| Metric | Target | Rationale |
|--------|--------|-----------|
| Individual hook | < 5 seconds | Keeps each commit responsive |
| Total pre-commit | < 10 seconds | Total time for all pre-commit stage hooks |
| Total pre-push | < 60 seconds | Acceptable for a less frequent operation |
| Full scan (--all-files) | < 3 minutes | For periodic complete scans |

## Profiling Hook Performance

Before optimizing, measure. The profiler (PowerShell 7) runs each security hook through
`pre-commit run <hook-id> --all-files` in the current directory, so run it from the
root of the repository you want to measure. It needs pre-commit and the scanners on
PATH. `-FixtureDir` is only recorded in the JSON output; it does not choose what is
scanned.

```powershell
# Profile the security hooks (3 iterations each)
./scripts/profile-hook-performance.ps1

# More iterations for accuracy, with per-iteration output
./scripts/profile-hook-performance.ps1 -Iterations 5 -ShowVerbose
```

It profiles these hooks: `trivy-iac-critical`, `trivy-secrets`,
`validate-suppressions` and `gitleaks` at pre-commit, and `trivy-iac-full`,
`checkov`, `checkov-strict` and `tflint` at pre-push. It prints the average time per
hook, marks each `[OK]` or `[SLOW]` against the 5-second target, and adds
recommendations. The labels reflect elapsed time only: the profiler does not check
whether a hook succeeded, so a hook that fails fast (a missing scanner, an unknown
hook ID) can still show `[OK]`. Run a hook on its own to confirm it works.

- `MIGRATE:` a pre-commit hook averaging over 10 seconds should move to pre-push.
- `OPTIMIZE:` a hook over the 5-second target needs attention.
- `TOTAL TIME:` a stage exceeds its total target.

Results are written to `.scan-results/performance/performance-YYYY-MM-DD.json` and
`performance-latest.json`, so you can compare runs.

## Optimization Strategies

### 1. Stage Migration

Run fast checks at commit time and slow, thorough checks at push time. The hooks
shipped by this repository already have default stages
(see [HOOK-REFERENCE](HOOK-REFERENCE.md)):

| Hook | Default stage | Notes |
|------|---------------|-------|
| `trivy-secrets` | pre-commit | Secret scan of staged content |
| `gitleaks` | pre-commit | Second secret scanner |
| `trivy-iac-critical` | pre-commit | Quick CRITICAL-only IaC scan |
| `validate-suppressions` | pre-commit | Validates the exception registry |
| `trivy-iac-full` | pre-push | Full-severity IaC scan |
| `checkov` / `checkov-strict` | pre-push | Policy scan |
| `tflint` | pre-push | Terraform linting |
| `snyk-iac` | pre-push | Optional |

The tier templates also use hooks from other repositories, such as `terraform_fmt` and
`terraform_validate` from pre-commit-terraform, at pre-commit.

With **pre-commit**, override a hook's stage in your `.pre-commit-config.yaml`:

```yaml
  - repo: https://github.com/agenticcodingops/auto-code-scanning
    rev: <release commit SHA>   # see VERSION-PINNING.md
    hooks:
      - id: trivy-iac-critical
        stages: [pre-commit]    # quick CRITICAL-only scan
      - id: trivy-iac-full
        stages: [pre-push]      # full severity scan at push time
      - id: checkov
        stages: [pre-push]
```

With **Lefthook** (the default runner), pre-commit commands sit under `pre-commit:`
in `lefthook.yml`, and push-time scanners are listed in the `--hooks` argument of the
`scan-push-objects` command under `pre-push:`. Move a check by editing those lists.
Lefthook already runs pre-commit commands in parallel (`parallel: true`).

Do not move `gitleaks` or `trivy-secrets` to pre-push. Both scan the staged index; after
a normal commit nothing is staged, so at push time they pass without scanning the
pushed commits. Keep secret scanning at commit time; CI scans the pull request again.

### 2. Caching

Enable caching for tools that support it.

#### Trivy

Trivy keeps its database and checks in a cache directory. Set a stable location so
it is reused between runs:

```powershell
# PowerShell (add to your profile)
$env:TRIVY_CACHE_DIR = "$HOME/.trivy-cache"
```

```bash
# Bash
export TRIVY_CACHE_DIR="$HOME/.trivy-cache"
```

The first run after clearing the cache downloads data and is slower.

#### pre-commit

pre-commit caches hook installations automatically. Clear the cache if hooks behave
unexpectedly:

```bash
pre-commit clean
pre-commit install
```

#### TFLint plugins

```bash
# Initialize plugins once; they are cached under ~/.tflint.d/plugins/
tflint --init
```

### 3. Parallel Execution

Lefthook runs pre-commit commands in parallel by default. pre-commit runs hooks one
after another. If you want to run several scanners concurrently in an ad hoc script,
PowerShell 7 can do it. This is an example to adapt; the repository does not ship such
a script:

```powershell
# Example only: your own script, for example parallel-scan.ps1
$jobs = @(
    { trivy config . --severity CRITICAL,HIGH },
    { tflint --config=.tflint.hcl }
)

$jobs | ForEach-Object -Parallel { & $_ } -ThrottleLimit 3
```

### 4. Scope Limiting

#### Scan only what changed

Commit hooks already scan staged content, and push hooks scan only the files changed by
each pushed ref. For a manual run on specific files with pre-commit:

```bash
pre-commit run --files terraform/modules/s3/main.tf
```

`gitleaks` and `trivy-secrets` ignore `--files`: they scan the staged index, and pass
without scanning when nothing is staged. Stage the file first to scan it for secrets.

#### Skip directories

Exclude generated or example code from pre-commit:

```yaml
# .pre-commit-config.yaml
exclude: |
  (?x)^(
    examples/.*|
    tests/.*|
    \.terraform/.*
  )$
```

Excluded paths are still scanned in CI unless CI is configured to skip them.

`gitleaks` does not apply these exclusions: it scans the whole staged index. When any
non-excluded file is staged, staged content under an excluded path is scanned too, and
a secret there can block the commit.

### 5. Skip Slow Hooks When Needed

For an urgent commit (use sparingly):

```bash
# pre-commit: skip specific hooks
SKIP=checkov,trivy-iac-full git commit -m "message"

# Lefthook: skip all local hooks for one command
LEFTHOOK=0 git commit -m "message"

# Skip all hooks (not recommended)
git commit --no-verify -m "urgent: message"
```

Skipping a local hook never skips CI: the pull request is still scanned. See
[LOCAL-HOOKS-TOGGLE](LOCAL-HOOKS-TOGGLE.md) for the supported switches.

## Measuring Improvement

After a change, profile again and compare with the earlier result in
`.scan-results/performance/`:

```powershell
./scripts/profile-hook-performance.ps1
```

You are done when every pre-commit hook is under 5 seconds, the pre-commit total is
under 10 seconds and the pre-push total is under 60 seconds.

## Troubleshooting Slow Hooks

### Common Causes

1. **Network calls**: database updates, external module downloads
2. **Large file scans**: generated files, binaries
3. **Deep analysis**: recursive scanning, cross-file analysis
4. **Missing cache**: cold start after a cache clear

### Diagnostics

```powershell
# Time one command
Measure-Command { trivy config . --severity CRITICAL }

# See Trivy's cache and download activity
$env:TRIVY_DEBUG = "true"
trivy config .
```

## Related Documentation

- [HOOK-REFERENCE.md](./HOOK-REFERENCE.md): hook IDs, stages and configuration
- [ADOPTION-PLAYBOOK.md](./ADOPTION-PLAYBOOK.md#collecting-metrics): adoption metrics
- [SETUP-GUIDE.md](./SETUP-GUIDE.md): initial setup
