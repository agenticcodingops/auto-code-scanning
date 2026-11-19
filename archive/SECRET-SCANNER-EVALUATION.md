# Secret scanner evaluation

Checked 2026-10-31 on this worktree (`feat/secret-scanner-evaluation`, base `origin/main` at `2b78f59`).

## Recommendation

Keep Gitleaks as the local pre-commit hook and fix that hook. Do not adopt Betterleaks, do not add Gitleaks to CI or the fix loop, and do not remove Gitleaks from templates that already list it.

The measured defects are in the hook, not in Gitleaks' staged scan. On the same planted file, `gitleaks protect --staged` and `gitleaks git --staged` returned the same two findings once the report was actually written. Betterleaks v1.9.0 matched those two findings and added none. Betterleaks v2.0.0-rc.6 also matched those two, and its CLI changes break the config, ignore file, and SARIF behaviour this repo already documents. Trivy already reports the AWS access-key id that Gitleaks and Betterleaks missed, at CRITICAL, which is what CI gates on.

## Options

| Option | Decision | Why |
|---|---|---|
| A. Keep Gitleaks and fix the hook | Chosen | The hook drops the JSON report, so a real staged scan becomes one undetailed finding. `git --staged` with `--report-path -` returns the same staged rows as `protect`. Fixing that does not add a scanner and does not change a template default. |
| B. Also run Gitleaks in CI or the fix loop | Not chosen | CI and the fix loop already fail closed on Trivy HIGH and CRITICAL secrets. On the planted file, Trivy's only extra finding was an AWS access-key id at CRITICAL. Gitleaks' only extra finding was a Slack webhook that Trivy rates MEDIUM, below that gate. Running Gitleaks in CI would block that MEDIUM webhook as HIGH (`docs/SEVERITY-MAPPING.md`). That changes what adopters' CI blocks. |
| C. Replace Gitleaks with Betterleaks | Not chosen | v1.9.0 found the same rows as Gitleaks and nothing more. v2.0.0-rc.6 is a release candidate. Its `-v` flag sends a found credential to the provider. It rejects a Gitleaks `allowlists` config, does not read `.gitleaksignore`, and has no SARIF reporter. No detection gain on the inputs below. |
| D. Choose the scanner in scan-config | Not chosen | The local hook is already selected by the pre-commit template. The starter template does not include Gitleaks. A scan-config tool enum would be a new adopter surface for a scanner that did not find anything Trivy or Gitleaks missed. |
| E. Trivy only | Not chosen as a default change | Removing `gitleaks` from the aws, azure, gcp, standard, and strict templates would change what those adopters run. Left as an open question. |

## Evidence

### How these runs were made

Host: Windows 10.0.26300.0, PowerShell 7.6.9. One run each, unless a row says otherwise. Counts are `rule|file|line` (Trivy rows also include Trivy severity). `leaked=False` means none of the planted secret strings appeared in that command's stdout, stderr, or report file. Reports were deleted after the safe rows were recorded.

Binaries, each checked with `Get-FileHash -Algorithm SHA256` against the checksum file in that GitHub release:

| Tool | Version | Archive SHA-256 | Match |
|---|---|---|---|
| Gitleaks official `gitleaks_8.30.1_windows_x64.zip` | `8.30.1` | `d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e` | yes |
| Betterleaks `betterleaks_1.9.0_windows_x64.zip` | `1.9.0` | `b765daec9fda475b031b5a5159798cbe4294a3f2a50683cbc0471226e376d3da` | yes |
| Betterleaks `betterleaks_2.0.0-rc.6_windows_x64.zip` | `2.0.0-rc.6` | `43814f2e76203cd81040ef3598ad691cf503de547d6d12c52dd9ba1db9643322` | yes |
| Trivy `trivy_0.75.0_windows-64bit.zip` | `0.75.0` | `4e43bd71a30f51aee39525f60f2b47043af77eb8df8fe082aae4372b69c6660f` | yes |

The Scoop app binary `scoop\apps\gitleaks\current\gitleaks.exe` on this machine had the same SHA-256 as the official zip's `gitleaks.exe` (`17157e2ee8b76fc8b1d8bee607a250e34b8a8023c8bc81822d4b5ee4d78fcb7c`). Scans below used the official zip binary.

Gitleaks 8.30.1 publishes `gitleaks_8.30.1_checksums.txt` and no sigstore bundle (release asset list, 2026-10-31). Betterleaks 1.9.0 and 2.0.0-rc.6 publish `checksums.txt.sigstore.json`; those files were downloaded and not verified. Signature verification was not run for any scanner.

Linux and macOS binaries were not executed. Install commands below are quoted from upstream docs and marked not run. Building Betterleaks `main` was not run: Go is not installed here. `main` was 1 commit ahead of tag `v2.0.0-rc.6` (`gh api repos/betterleaks/betterleaks/compare/v2.0.0-rc.6...main`). The v2 numbers are the rc.6 binary.

Not valid, and not used below: an earlier history scan of this repo whose stderr was `cannot spawn astextplain` (Git for Windows `diff.astextplain.textconv` with `C:\Program Files\Git\usr\bin` absent from the scanner's PATH). A PowerShell `@($null).Count` of an empty Trivy 0.69.3 fixture report printed `secret_objects=1` while the process exited 0. Hook invocations that ran after the scratch index was empty (`PASS: No files staged`) and a bash invocation that executed `bash.exe` as its own script (exit 126).

### Hook on base `2b78f59`, confirmed on Gitleaks 8.30.1

These lines are the hook before this branch. `git show 2b78f59:hooks/gitleaks.sh` and `git show 2b78f59:hooks/gitleaks.ps1` still match them. They are not the line numbers in the files after the fix, so they are quoted as text rather than as links to the branch tip.

The hook command was `gitleaks protect --staged` with no `--report-path`. Base `hooks/gitleaks.sh` line 25:

    gitleaks_cmd=(gitleaks protect --staged --report-format json --exit-code 1)

Base line 40:

    output="$("${gitleaks_cmd[@]}" 2>&1)"

Base line 49:

        total_high="$(echo "${output}" | jq 'length' 2>/dev/null || echo 1)"

Base line 77:

    write_scan_json "$(build_findings_json "gitleaks" "." "${duration_ms}" "[]" 0 "${total_high}" 0 0)"

The PowerShell hook was the same command and the same empty findings array. On a parse failure it set the count to 1. Base `hooks/gitleaks.ps1` line 25:

    $gitleaksArgs = @('protect', '--staged', '--report-format', 'json', '--exit-code', '1')

Base line 62:

        $totalHigh = 1

Base line 77:

    Write-ScanJson (Build-FindingsJson -Tool 'gitleaks' -DurationMs $durationMs -High $totalHigh)

`gitleaks protect --help` still documents `--staged` (exit 0). Top-level `gitleaks --help` does not list `protect` (exit 0, `mentions_protect_command=False`). The v8.30.1 README says: "v8.19.0 introduced a change that deprecated `detect` and `protect`. Those commands are still available but are hidden in the `--help` menu."

Direct command, official `gitleaks.exe` 8.30.1, scratch repo, three planted lines staged (AWS access-key id shape, GitHub PAT shape, Slack webhook URL). Values are not recorded here.

| Name | Command | Exit | ms | Findings | Notes |
|---|---|---|---|---|---|
| gl-protect-staged-nopath | `protect --staged --report-format json --exit-code 1 --no-banner --log-level error` | 1 | 2028 | 0 | stdout 0 bytes. This is the hook's command shape. |
| gl-protect-staged-path | same, plus `--report-path <file> --redact` | 1 | 1874 | 2 | `slack-webhook-url\|secrets.txt\|3`, `github-pat\|secrets.txt\|2`. leaked=False. |
| gl-git-staged | `git --staged` with the same report file flags | 1 | 1443 | 2 | Same two rows. `PROTECT vs GIT STAGED same set: True`. |
| gl-git-staged-stdout | `git --staged --report-format json --report-path - --redact --no-banner --exit-code 1 --log-level error` | 1 | 1401 | 2 | stdout 1057 bytes, valid JSON, same two rows. leaked=False. |

The AWS access-key id was not in either Gitleaks row.

The PowerShell hook was then run on a fresh temp git repo with a real staged file (`pwsh -NoProfile -File hooks/gitleaks.ps1`, official 8.30.1 first on PATH). Exit 1. Output included `FAIL: 1 findings (0 critical, 1 high, 0 medium, 0 low)`. `.scanning/last-scan.json` had `summary.by_severity.HIGH=1` and a `findings` array of length 0. leaked=False. Gitleaks itself would have reported the GitHub and Slack rows; the hook reported one undetailed finding because stdout was empty. The bash hook was not run: the invocation used in that session did not execute the script.

A config file whose contents were `this is not toml [[[[`:

| Name | Exit | ms | Findings | stderr (trimmed) |
|---|---|---|---|---|
| gl-broken-config (`git --staged --config broken.toml --report-path -`) | 1 | 1216 | 0 | `unable to load gitleaks config, err: While parsing config: toml: expected character =` |
| bl1-broken-config | 1 | 160 | 0 | `unable to load config, err: toml: expected character =` |
| bl2-broken-config | 1 | 104 | 0 | `unable to load config ... toml: expected character =` |

Gitleaks' own README lists exit codes `0` no leaks, `1` leaks or error, `126` unknown flag. Exit 1 for a bad config never reaches the hook's `exit >= 2` branch. The same PowerShell hook, with that broken file at `.scanning/configs/.gitleaks.toml` (the path `resolve_config` reads), exited 1 and printed `FAIL: 1 findings`. It counted the config error as a finding.

`resolve_config` looks at `$SCAN_CONFIG_DIR` (dispatcher default `.scanning/configs`) and an optional fallback. It does not read a repo-root `.gitleaks.toml`:

```407:409:hooks/lib/common.sh
    if [[ -f "${SCAN_CONFIG_DIR}/${filename}" ]]; then
        echo "${SCAN_CONFIG_DIR}/${filename}"
        return 0
```

### Same inputs, four scanners

Scratch file `secrets.txt` before any commit. Staged paths: `clean.txt`, `fixture-copy.tf`, `secrets.txt`. Filesystem scans below are `dir` / `fs` of that worktree, so they also see the copy of `tests/fixtures/terraform-secret`. That copy added no rows.

| Name | Tool | Command | Exit | ms | Findings |
|---|---|---|---|---|---|
| bl1-dir-scratch | Betterleaks 1.9.0 | `dir . --report-format json --report-path <file> --redact --no-banner --exit-code 1 --log-level error` | 1 | 1411 | 2: `github-pat\|secrets.txt\|2`, `slack-webhook-url\|secrets.txt\|3` |
| bl1-git-staged | Betterleaks 1.9.0 | `git --staged` with the same report flags | 1 | 827 | same 2 |
| bl2-fs-scratch | Betterleaks 2.0.0-rc.6 | `fs . --redact --no-banner --log-level=error --exit-code=1 -o <file>` | 1 | 1187 | 2: `github-pat\|./secrets.txt\|2`, `slack-webhook-url\|./secrets.txt\|3` |
| bl2-stdin-gitdiff | Betterleaks 2.0.0-rc.6 | `git diff --cached` piped to `stdin --git-diff --redact --no-banner --log-level=error --exit-code=1 -o -` | 1 | 905 | same 2 rules and lines. stdout was JSON. leaked=False. |
| trivy075-scratch | Trivy 0.75.0 | `fs . --scanners secret --format json --output <file> --quiet --exit-code 1 --skip-db-update` | 1 | 584 | 3: `aws-access-key-id\|secrets.txt\|1\|CRITICAL`, `github-pat\|secrets.txt\|2\|CRITICAL`, `slack-web-hook\|secrets.txt\|3\|MEDIUM` |
| trivy-local-scratch | Trivy 0.69.3 (Chocolatey) | `fs . --scanners secret --format json --output <file> --quiet --exit-code 1` | 1 | 558 | same 3 rows and severities |

A second planted file, high-entropy AWS access-key id with no adjacent secret access key, next to a GitHub PAT. `dir` / `fs` of that file only. leaked=False.

| Name | Exit | Rules |
|---|---|---|
| entropy-gl (Gitleaks 8.30.1 `dir`) | 1 | `github-pat` only (1) |
| entropy-bl2 (Betterleaks 2.0.0-rc.6 `fs`) | 1 | `github-pat` only (1) |
| entropy-trivy (Trivy 0.75.0 `fs --scanners secret`) | 1 | `aws-access-key-id`, `github-pat` (2) |

On these two planted AWS access-key ids, with no adjacent secret access key, Gitleaks 8.30.1 and Betterleaks 2.0.0-rc.6 reported neither id. Trivy 0.75.0 reported both. This does not say Gitleaks can never report an AWS key. It says a second scanner did not cover the id-only case Trivy already flags, and the id Trivy flags is CRITICAL.

Rule-selection probe for the regression test, official Gitleaks 8.30.1, one temp file with three runtime-generated values, deleted afterwards. Command: `dir <file> --report-format json --report-path <file> --redact --no-banner --exit-code 1 --log-level error`. Exit 1, count 3: `stripe-access-token` line 1, `github-pat` line 2, `slack-webhook-url` line 3. The strings were not written to the log.

`tests/fixtures/terraform-secret` (filesystem scan of that directory, not the hook):

| Name | Tool | Exit | ms | Findings |
|---|---|---|---|---|
| gl-dir-fixture | Gitleaks 8.30.1 `dir` | 0 | 1359 | 0 |
| bl1-dir-fixture | Betterleaks 1.9.0 `dir` | 0 | 580 | 0 |
| bl2-fs-fixture | Betterleaks 2.0.0-rc.6 `fs` | 0 | 456 | 0 |
| trivy075-fixture | Trivy 0.75.0 `fs --scanners secret --skip-db-update` | 0 | 482 | 0 |
| trivy069-fixture | Trivy 0.69.3 `fs --scanners secret` | 0 | not recorded | 0 |

The fixture comment still says otherwise:

```1:2:tests/fixtures/terraform-secret/main.tf
# WARNING: This file intentionally contains hardcoded secrets for testing
# Expected: trivy-secrets=Exit1, gitleaks=Exit1
```

Those values were not copied into this document. The fixture was not edited.

`tests/fixtures/terraform-valid/aws`: Gitleaks 8.30.1 `dir` exit 0 (1470 ms), Trivy 0.75.0 exit 0 (399 ms), Betterleaks 2.0.0-rc.6 `fs` exit 0 (348 ms). All 0 findings.

This repo's working tree (`dir` / `fs .`, scanners' default skips). All leaked=False, 0 findings:

| Name | Exit | ms |
|---|---|---|
| gl-dir-repo (Gitleaks 8.30.1) | 0 | 1937 |
| bl1-dir-repo (Betterleaks 1.9.0) | 0 | 774 |
| bl2-fs-repo (Betterleaks 2.0.0-rc.6) | 0 | 961 |
| trivy075-repo (Trivy 0.75.0) | 0 | 485 |

This repo's git history, after prepending `C:\Program Files\Git\usr\bin` to PATH so `astextplain` can start. Gitleaks and Betterleaks 1.9.0: `git . --report-format json --report-path <file> --redact --no-banner --exit-code 1 --log-level error`. Betterleaks 2.0.0-rc.6 does not spawn `git`: `git . --redact --no-banner --log-level=error --exit-code=1 -o <file>`.

| Name | Exit | ms | Findings | stderr |
|---|---|---|---|---|
| gl-hist-path | 0 | 7211 | 0 | empty |
| bl1-hist-path | 0 | 6176 | 0 | empty |
| bl2-hist | 0 | 12215 | 0 | empty. Report `scan.state=complete`. |

A zero is not a proof that the repo contains no secret. No scanner raised a finding outside the planted scratch files, so there is no rule, file, and line to report.

After one commit in the scratch repo, history scans of that repo (the planted file only): Gitleaks 8.30.1 `git` exit 1, 1718 ms, 2 findings; Betterleaks 1.9.0 exit 1, 863 ms, 2; Betterleaks 2.0.0-rc.6 exit 1, 696 ms, 2. `git --staged` on the clean index: Gitleaks exit 0, stdout `[]`, 0 findings.

### Config, ignore files, SARIF, redaction, exit codes

| Check | Result |
|---|---|
| `.gitleaksignore` with one Gitleaks fingerprint of a detected row | Gitleaks 8.30.1: 2 findings became 1 (exit 1, 2490 ms). Fingerprint present, `fingerprint_contains_secret=False`. Betterleaks 1.9.0: 2 became 1 (exit 1, 856 ms). |
| Betterleaks 2.0.0-rc.6 with that `.gitleaksignore` present and no `--ignore-file` | still 2 (838 ms). Autodiscovery did not apply. |
| Betterleaks 2.0.0-rc.6 `--ignore-file` whose line was the SHA-256 of the detected GitHub PAT | exit 1, leaked=False, remaining row `slack-webhook-url\|3` only. |
| `gitleaks:allow` on the only secret line | Gitleaks 8.30.1 `dir` exit 0, 0 findings, 2032 ms. Betterleaks 2.0.0-rc.6 exit 0, 0 findings, 404 ms. |
| Gitleaks `--config` of a TOML allowlist that named only `clean.txt` | exit 1, 2 findings, 1451 ms. The allowlisted path had no secret, so this shows the file loaded, not that the allowlist matched a secret. |
| Betterleaks 1.9.0 with and without `.gitleaks.toml` present | both exit 1, 2 findings, no config error (505 ms each). |
| Betterleaks 2.0.0-rc.6 with `.gitleaks.toml` present and no `--config` | exit 1, 2 findings, 503 ms, no config error. The file was not auto-loaded. |
| Betterleaks 2.0.0-rc.6 `--config .gitleaks.toml` | exit 1, 0 findings, 135 ms. stderr: `unknown configuration fields: allowlists (line 4, column 3): strict mode`. |
| SARIF | Gitleaks `dir secrets.txt --report-format sarif`: exit 1, 1455 ms, 50347 bytes, schema string present, leaked=False. Betterleaks 1.9.0: exit 1, 96445 bytes, schema present, leaked=False. Betterleaks 2.0.0-rc.6 `--report-format sarif`: exit 126, `unknown flag`. |

v2 migration doc (`docs/v2_migration.md` at tag `v2.0.0-rc.6`): default scans "do not validate or analyze credentials"; `-v` / `--validate` and `-a` / `--analyze` do; `revoke` is a separate command and "Scans never revoke credentials." The same page says `-v` used to mean verbose. SARIF, CSV, and JUnit reporters are removed. `.gitleaksignore` discovery is not supported; ignore entries are SHA-256 of the secret bytes. Neither `.betterleaks.toml` nor `.gitleaks.toml` is auto-loaded. Staged scan is `git diff --cached` piped to `stdin --git-diff`. There is no `--staged` flag (`bl2-git-help` exit 0, `mentions_staged=False`).

No hook, workflow, or fix-loop path in this change may pass `-v`, `--validate`, `--analyze`, `--validation`, or `revoke`.

### Overlap with the CI secret scan

CI secret scans are Trivy only, severity HIGH,CRITICAL:

```241:248:.github/workflows/reusable-scan.yml
      - name: Run Trivy secret scanner
        uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25  # v0.36.0
        with:
          version: "v0.75.0"  # exact Trivy pin; bump deliberately (docs/VERSION-PINNING.md)
          scan-type: fs
          scanners: secret
          severity: "HIGH,CRITICAL"
          exit-code: "1"
```

```398:409:.github/workflows/autonomous-fix.yml
      - name: Authoritative secret scan (SHA-pinned action, pinned Trivy version)
        # Supply-chain hygiene: keep the SHA-pinned Trivy action (no curl|sh) in this
        # write-capable job. Pin the Trivy binary version so setup-trivy does not default
        # to v0.65.0, which fails to install on the runner.
        uses: aquasecurity/trivy-action@b6643a29fecd7f34b3597bc6acb0a98b03d33ff8  # v0.33.1
        with:
          version: "v0.71.0"
          scan-type: fs
          scan-ref: ${{ env.SCAN_TMP }}
          scanners: secret
          severity: CRITICAL,HIGH
          exit-code: "1"
```

The supported CI paths are `code-security-scan.yml` for app code and `reusable-scan.yml` for Terraform/IaC, exercised in this repository by `reusable-scan-self-test.yml`. They use Trivy for CI secret scanning. None of these workflows run Gitleaks.

Gitleaks maps every secret to HIGH:

```44:50:docs/SEVERITY-MAPPING.md
### Gitleaks

| Source Value | Normalized |
|-------------|------------|
| (all secrets) | HIGH |

Gitleaks does not provide severity levels. All detected secrets are normalized to HIGH because leaked credentials represent a significant security risk.
```

On the scratch file, the CI gate would block Trivy's two CRITICAL rows and drop the MEDIUM Slack webhook. A Gitleaks CI job would block the Slack webhook as HIGH and would still miss the AWS access-key id. That is a change to what CI blocks, with no gain on the finding CI already blocks. Option B stays out.

### `gitleaks_suppressions` is validated and not applied

`scripts/validate-suppressions.py` and `hooks/validate-suppressions.py` accept a `gitleaks_suppressions` section (`hooks/validate-suppressions.py` line 73, `"gitleaks": "gitleaks_suppressions"`). `scripts/scan.py` loads that section:

```403:403:scripts/scan.py
                for section_key in ["trivy_suppressions", "checkov_suppressions", "tflint_suppressions", "gitleaks_suppressions", "snyk_suppressions"]:
```

`scan.py` then runs Trivy, Checkov, and optional Snyk only (lines 584-612). It never produces a Gitleaks finding, so the filter at lines 627-635 has nothing Gitleaks-shaped to drop. `scripts/aggregate-scan-results.ps1` maps tool `gitleaks` to HIGH (lines 112-114) and collects `trivy-*.json`, `checkov-*.json`, `tflint-*.json`, and `snyk-*.json` only (lines 498-539). The aggregate step in `reusable-scan.yml` applies four sections and not `gitleaks_suppressions`:

```746:746:.github/workflows/reusable-scan.yml
              for section in ["trivy_suppressions", "checkov_suppressions", "tflint_suppressions", "snyk_suppressions"]:
```

`hooks/gitleaks.sh` does not read `.scan-suppressions.yaml`. The section is validated, and loaded into a map that no Gitleaks run consults. Applying it is out of scope for this change.

### Where Gitleaks is already wired

`.pre-commit-hooks.yaml` lines 122-124 define id `gitleaks`, entry `hooks/dispatcher.sh gitleaks`, stage `pre-commit`. The aws, azure, gcp, standard, and strict pre-commit templates, `templates/lefthook/lefthook.yml`, and `scripts/.pre-commit-config.yaml` include that id. The starter template does not:

```24:26:templates/starter/pre-commit-config.yaml
    hooks:
      - id: trivy-secrets
        stages: [pre-commit]
```

`docs/SETUP-GUIDE.md` line 275 describes the starter tier as "Secret gate (trivy-secrets, gitleaks)". That sentence does not match `templates/starter/pre-commit-config.yaml`. It was not changed here.

`ci.yml` job `test-hooks` (line 109) installs Trivy from apt, Checkov from pip, and TFLint `latest`. It does not install Gitleaks. `tests/integration/test-hooks.sh` is not what that job runs. The script's `run_hook_test` cds into the fixture and expects the secret fixture to exit 1 (lines 65-78 and 180-182). The hook scans `git diff --cached` of that process, not the fixture tree. The fixture is also a false negative for Gitleaks 8.30.1, as measured above.

### Maintenance and install paths

| Project | Licence | Release checked | Repo activity |
|---|---|---|---|
| github.com/gitleaks/gitleaks | MIT (`gh api repos/gitleaks/gitleaks/license`) | latest `v8.30.1`, published 2026-03-21 | `pushed_at` 2026-10-28. `v8.30.1...master` was diverged, ahead 26, behind 1. |
| github.com/betterleaks/betterleaks | MIT | latest non-prerelease `v1.9.0`, published 2026-09-29. Prerelease `v2.0.0-rc.6`, published 2026-10-30. | Created 2026-02-03. `pushed_at` 2026-10-31. |

The Betterleaks README (repo root, fetched with the v1.9.0 tag page during investigation) says the Gitleaks maintainers, including the original author, maintain Betterleaks, with development supported by Aikido. Re-check that sentence on the tag before treating it as a pin decision. It does not change the measurement: v2 is still a candidate, and v1 did not find more than Gitleaks.

Gitleaks README install lines, not executed here: `brew install gitleaks` on macOS; Docker tags `zricethezav/gitleaks:latest` and `ghcr.io/gitleaks/gitleaks:latest` (moving tags; do not pin adopters to them); GitHub release archives. Linux x64 archive checksum from `gitleaks_8.30.1_checksums.txt` line 7: `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  gitleaks_8.30.1_linux_x64.tar.gz`. Darwin archive checksums are lines 1-2 of that file. Windows zip checksum is line 10, verified above.

Betterleaks v2 migration doc: the rc does not move Docker `latest`, the Homebrew cask, or GitHub's "latest" release. v1 maintenance stays on Docker `:v1` and cask `betterleaks/tap/betterleaks@1`. Not executed here.

The official Gitleaks Action README example sets `GITLEAKS_LICENSE` and says it is only required for organizations, not personal accounts. This change does not use that action.

### Tool failures block by default

The v3 hook contract blocks incomplete scans. Both hook implementations normalize
missing, malformed or non-array JSON, inconsistent exit statuses, and tool exits
above 1 to a tool error. They use the shared exit-code handler: the commit blocks
unless the adopter explicitly sets `SCAN_ALLOW_TOOL_ERRORS=1`. That local override
warns and never writes a clean pass report. Raw reports and stderr are not printed,
so configuration errors cannot expose staged credentials.

Known findings and array-shaped corruption always block, including with the
tool-error override enabled. The override applies only to infrastructure errors
without a usable or potentially corrupted findings array.

An empty JSON array passes only with exit 0. Parsed findings block. A nonempty
array that cannot be parsed also blocks without printing credential fields.
The integration test covers broken configuration with and without a parser,
the explicit local override, real findings, and a clean staged file.

## Plan

### Files to change

- `hooks/gitleaks.sh` and `hooks/gitleaks.ps1`. Command becomes `gitleaks git --staged --report-format json --report-path - --redact --no-banner --exit-code 1 --log-level error`, plus `--config` when `resolve_config` / `Resolve-ScanConfig` finds `.gitleaks.toml`. Stdout is parsed alone. Stderr is not merged into the report.
- `tests/integration/test-gitleaks-hook.sh`. Own temporary repository; verifies findings contain only safe fields, tool/configuration errors block without a pass report, the explicit local tool-error override warns, and clean staged files pass. Both shell implementations are exercised locally; CI exercises Bash.
- `.github/workflows/ci.yml`. One job, not multiplied by the aws/azure/gcp matrix. Download `gitleaks_8.30.1_linux_x64.tar.gz`, require SHA-256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`, then run the new test. Checkout stays on the existing SHA pin `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`.
- `docs/HOOK-REFERENCE.md`. The gitleaks note currently says it complements trivy-secrets with different detection patterns (`docs/HOOK-REFERENCE.md` line 85). Replace that with the measured direction and the new command.
- `docs/TESTING-GUIDE-CONSUMING-REPO.md` line 215, which tells an adopter that the AWS example key blocks the Gitleaks hook. That expectation is false for 8.30.1.

No new scanner. No template edit. No scan-config default. No change to the supported scan or fix-loop workflows. No schema or severity-map edit. No suppression-application change. `CHANGELOG.md`, `version.txt`, and `x-release-please-version` lines stay untouched.

### Tests

The new script runs the bash hook and, when asked, the PowerShell hook. CI runs the bash hook only. Local verification runs both. The existing `tests/integration/test-hooks.sh` gitleaks case stays as it is: it does not stage a secret, and the fixture is a false negative, so it is not this fix's proof.

### Adopter impact

Adopters running the `gitleaks` hook must repair broken scanner configuration
before committing. Missing or invalid reports block by default, including when
staged files contain secrets. The existing explicit local tool-error override
remains available. Re-vendor both hooks and their shared libraries together.
CI and the fix loop continue to scan secrets with their existing scanner.

### Rollback

Revert the hook pair. The test and the CI job can revert with them. Templates and workflows are unchanged, so there is no scanner pin to roll back.

### Left out on purpose

- Betterleaks, in any hook, template, or workflow.
- Gitleaks in CI scans or the fix loop.
- Removing Gitleaks from templates that already include it.
- Network validation, analysis, or revocation.
- Teaching the hook to read `.scan-suppressions.yaml`.
- Replacing the committed `terraform-secret` fixture with a higher-entropy value.
- Editing `docs/SETUP-GUIDE.md` line 275 (starter tier names Gitleaks; the starter template does not include it).

### Open questions

- Revisit a CI Gitleaks job only if a later comparison shows HIGH or CRITICAL findings Trivy misses on inputs this repo cares about. The runs above did not show that.
- Whether to drop the `gitleaks` hook from the aws, azure, gcp, standard, and strict templates. That would change a default, so it is not in this change.
- Whether the hook should apply `gitleaks_suppressions`. Today the section is validated and not applied.
- Whether to correct `docs/SETUP-GUIDE.md` line 275, and whether to replace `tests/fixtures/terraform-secret` so the comment's expected exit codes are true again. Both are pre-existing and were left in place.
