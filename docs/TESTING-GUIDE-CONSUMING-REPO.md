# Consumer acceptance tests

Complete [Getting started](SETUP-GUIDE.md) first. This reference tests the installed
system; it replaces the historical setup walkthrough and its old result counts.

> **Pin the
> consuming repo to `@v3.0.9` (or a SHA) — never `@main`.** <!-- x-release-please-version -->

## Local acceptance

Run in a disposable consumer with the external trusted inputs from Getting started.
Record each command, exit code, selected files and scanner output. Use no real
credentials in test data. A skipped hook does not prove a scanner ran.

| Test | Command or action | Expected result |
|---|---|---|
| Installation | Run the external clone's `scripts/verify-scanning.ps1` with the actual runner and tier | Exit 0; no failed checks |
| Configuration | `python scripts/validate-scan-config.py` | Exit 0 for valid config |
| Commit | Make and stage a new clean change to the Terraform example, then `git commit` | Secret hooks run; IaC security also runs with Lefthook or standard/strict pre-commit; a clean commit succeeds |
| Staged security input | Stage a known scanner fixture, then change only its worktree contents and run the security hook | Security decision follows staged content; SQLFluff/formatters follow worktree content |
| Terraform on demand | `python scripts/scan.py . --tools trivy --format json` | One JSON document on stdout; diagnostics on stderr; 0 clean, 1 findings, 2 tool error |
| Suppression | `python scripts/validate-suppressions.py .scan-suppressions.yaml --ci` after creating a schema-2.0 registry | Valid entries pass; invalid metadata/expiry blocks |
| Report | Inspect `.scanning/last-scan.json` after a reporting hook | Valid JSON; rule/location metadata, no raw secret values |

For deliberate finding tests, use the platform's maintained integration fixtures
and assert the selected scanner actually detects them. A familiar example access
key is not guaranteed to match every detector: see [the secret scanner evaluation](SECRET-SCANNER-EVALUATION.md).
Missing tools and incomplete security reports block by default. The local
`SCAN_ALLOW_TOOL_ERRORS=1` compatibility setting has limited scope and cannot bypass
unsafe paths, required snapshots, invalid policy or malformed selected reports.

### Push transaction without a network push

From the consumer root after committing, feed a real four-field Git transaction
to the batch runner. First commit a new Terraform change in the range selected
against the destination's tracked default branch. Confirm the selected files and
scanner output: a transaction with no selected Terraform can pass by skipping both
scanners. This validates a new branch's exact committed tree locally:

```powershell
$Tip = (git rev-parse HEAD).Trim()
$Transaction = "refs/heads/main $Tip refs/heads/main " + ('0' * 40)
$Transaction | python hooks/pre-push.py --remote origin --hooks checkov,tflint
```

macOS/Linux:

```bash
tip="$(git rev-parse HEAD)"
printf 'refs/heads/main %s refs/heads/main %040d\n' "$tip" 0 |
  python hooks/pre-push.py --remote origin --hooks checkov,tflint
```

The explicit batch command tests those two scanners, independently of runner
configuration. Also feed the same transaction to the **installed** push hook,
checking the scanners configured for that runner and tier. Adjust the hook path
if `core.hooksPath` points elsewhere. PowerShell with the verified Git Bash on PATH:

```powershell
$PushHook = (git rev-parse --git-path hooks/pre-push).Trim()
$Transaction | bash $PushHook origin local-test
```

macOS/Linux:

```bash
push_hook="$(git rev-parse --git-path hooks/pre-push)"
printf 'refs/heads/main %s refs/heads/main %040d\n' "$tip" 0 |
  bash "$push_hook" origin local-test
```

This invokes the local hook without a network push. Starter pre-commit has no
IaC security hook to expect here. For other tiers/runners, inspect selected files,
scanner output and raw exits; a successful skipped hook is not scan evidence.
A lint/security-clean tree with tracked Checkov policy and trusted external TFLint inputs passes.
With no known destination tracking refs this conservatively scans reachable ancestry.
A direct `pre-commit run --hook-stage pre-push --all-files` has no transaction and
is not a valid substitute. For existing refs, use the real advertised old SHA,
not the zero value. See [push selection](HOOK-REFERENCE.md) for multi-ref cases.

## Application checks

For C# and TypeScript, stage one relevant file and invoke the corresponding
registered Semgrep hook through your runner. Confirm the hook reads index bytes,
uses the expected ruleset and rejects a maintained finding fixture. Check C#
`build.working_dir` and its relative `solution` with the format/build hooks.
For TypeScript confirm external lint/formatter configuration is used. SQLFluff
must retain access to worktree dialect configuration, macros and templates.

The platform's own regressions are contributor tests, run from the platform clone:

```bash
python -m pytest tests/python/test_hook_integrity.py -q
bash tests/integration/test-app-code-hooks.sh
```

These complement the full [contributor suite](CONTRIBUTING.md); they do not replace it.

## Hosted acceptance

1. Open a test pull request. Confirm language detection, each enabled language's
   scan, the independent secret scan and Terraform jobs actually run.
2. If code scanning is enabled, inspect distinct SARIF categories and upload logs.
   In a private repository without that feature, explicitly disable upload in both
   callers and confirm scanning/gates still run.
3. Make a maintained test finding fail a check and verify branch protection prevents
   merge. Restore the clean state through normal reviewed changes.
4. If adopting the optional fix workflow, confirm `analyze` emits only a text patch
   after its isolated secret scan; `verify` runs builds without secrets; the final
   job gates fix paths and secret-scans added/modified files from the candidate
   tree before adding the counter. A gated path or invalid patch
   must route to `needs-human-review`. Use [FIX-LOOP.md](FIX-LOOP.md) for details.

## Performance and cleanup

Measure representative changed-file commits and push transactions after caches
are warm. Targets are 5 seconds per hook, 10 seconds per commit stage and 60 seconds
per push stage; first-run downloads and large builds can take longer. Time the
installed runner with representative committed/staged inputs and record scanner
output, exit codes, selected files and tool versions alongside timings. The old
profiler does not prove a Lefthook or transaction-bound push scan ran. Historical full-repository timings do not establish
changed-file hook performance.

Keep the disposable repository and logs until results are reviewed. Delete only
the specifically created temporary directory when finished; do not reset or
remove policy files in a real consumer as test cleanup.
