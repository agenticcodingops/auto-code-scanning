# Runbook: Migrate an Inline Scan or Fix Loop to the Platform

Some repositories copied the scan or fix-loop logic into their own workflow and hook
files. This runbook replaces those copies with pinned calls to this platform, and moves
the project-specific values into one file, `scan-config.yaml`.

The current release is `v2.2.0`. <!-- x-release-please-version -->

Line references such as `setup-scan-fix.py:85` mean that line of `scripts/setup-scan-fix.py`
at commit
[`7cd34a5`](https://github.com/agenticcodingops/auto-code-scanning/tree/7cd34a52c823a725575ef3b59ab34e062d1d83dd)
on `main`. Workflow files are under `.github/workflows/`.

## Purpose

After the migration the repository keeps `scan-config.yaml` and a few thin caller
workflows. The hardened logic (the two-job fix loop, the path gate, the secret re-scan,
the iteration cap) comes from the platform at a pinned release, so a fix to it reaches
the repository through one pin change.

## When to use

- The repository has its own copy of a fix-loop workflow, a scan workflow, or hooks with
  hard-coded paths, solution names or build commands.
- For a repository with no scan yet, use
  [consumer-repo-setup-guide.md](consumer-repo-setup-guide.md) or, for a Terraform
  module, [TERRAFORM-MODULE-ADOPTION.md](TERRAFORM-MODULE-ADOPTION.md).

## Prerequisites

- A clone of this platform, checked out at the release you will pin
  (`git checkout vX.Y.Z`). `setup-scan-fix.py` copies files from the clone it runs from
  (`setup-scan-fix.py:22`, `74-77`, `119-123`).
- Python 3 with PyYAML and `jsonschema`, and `gh` authenticated against the repository. `gh` creates the
  labels and checks the secrets (`setup-scan-fix.py:126-155`).
- Lefthook or pre-commit, for the local hooks.
- A clean working tree in the repository, so you can review every file the setup
  overwrites.
- A second maintainer to review the pull request.

Roles: the **Operator** is the maintainer doing the migration. The **Reviewer** approves
the pull request. **CI** is GitHub Actions.

## What moves where

| Inline today | After the migration | Source |
|---|---|---|
| A full fix-loop workflow in the repository | A thin caller that `uses:` `autonomous-fix.yml` at a pinned release | `templates/fix-loop/autonomous-fix.yml` |
| Fix-loop allowlist written into the workflow | `fix_loop.allowlist_paths` | `autonomous-fix.yml:23-25`, `302-320` |
| Sensitive-path denylist written into the workflow | `fix_loop.gated_paths` (case-insensitive substrings) | `scripts/check-fix-allowlist.py:4-7` |
| Solution path, working directory and build command in hooks or the workflow | `languages.<lang>.build.solution`, `languages.<lang>.build.working_dir` and `fix_loop.build_verify_cmd` | `templates/scan-config/standard.yaml:40`, `50`, `90` |
| A bespoke SARIF-uploading scan workflow | A caller of `code-security-scan.yml` and, for Terraform, of `reusable-scan.yml` | `templates/workflows/` |
| `lefthook.yml` calling each tool directly | `lefthook.yml` calling `hooks/dispatcher.sh` | `templates/lefthook/lefthook.yml:6-7` |
| An action pin maintained by hand in the fix loop | The pin inside the platform's `autonomous-fix.yml`, mirrored in `fix_loop.claude_code_action_ref` | `autonomous-fix.yml:27-29`, `242`; [VERSION-PINNING.md](VERSION-PINNING.md#the-centralized-claude-code-action-pin-layer-b) |

## Steps

### 1. List what the repository has copied

- **Who:** Operator
- **Operator STOP:** no

Find the inline workflows, hooks and their hard-coded values:

```bash
ls .github/workflows/
grep -rln "upload-sarif\|claude-code-action\|allowlist\|semgrep\|trivy" .github/workflows hooks scripts lefthook.yml 2>/dev/null
```

Write down, for each file: the paths the fix loop may edit, the paths it must never edit,
the build command, the solution file and its directory, the SARIF categories, and who is
allowed to trigger the fix loop. You will need each value in step 3.

### 2. Run the setup from the release you will pin

- **Who:** Operator
- **Operator STOP:** no

From the repository root, on a new branch:

```bash
python /path/to/auto-code-scanning/scripts/setup-scan-fix.py \
  --languages csharp,typescript --tier standard --hooks-runner lefthook --enable-fix-loop
```

Use your own languages and tier. Add `--cloud-provider aws|azure|gcp` for Terraform
(`setup-scan-fix.py:42-54`). The setup:

- writes `scan-config.yaml` from the tier template, but leaves an existing one unless you
  pass `--force` (`setup-scan-fix.py:59-68`; `render-scan-config.py:51-52`);
- copies `hooks/` and five shared scripts over any files with the same names
  (`setup-scan-fix.py:71-78`);
- overwrites `lefthook.yml` with the template, or writes `.pre-commit-config.yaml` only if
  it does not exist (`setup-scan-fix.py:82-100`);
- keeps an existing `.claude/settings.json`, and overwrites the four scan hooks in
  `.claude/hooks/` (`setup-scan-fix.py:103-114`);
- overwrites `code-security-scan.yml`, `terraform-scan.yml` (Terraform only) and
  `autonomous-fix.yml` (fix loop only) in `.github/workflows/` with the caller templates
  (`setup-scan-fix.py:117-124`).

Review `git status` and `git diff` before you go on.

### 3. Put the project values into `scan-config.yaml`

- **Who:** Operator
- **Operator STOP:** no

Set the values from step 1. An excerpt with example paths:

```yaml
languages:
  csharp:
    enabled: true
    build: { solution: "app/Example.slnx", working_dir: "app" }
  typescript:
    enabled: true
    build: { working_dir: "web" }
ci:
  sarif: { category_prefix: "scan-" }
fix_loop:
  enabled: true
  allowlist_paths: ["app/src/", "app/tests/", "web/"]
  gated_paths: ["auth", "payment", "crypto", "security", "identity", "secret", "credential",
                ".github/", ".claude/", "hooks", "lefthook.yml", "scan-and-fix.ps1", "scripts/", ".env", "LICENSE"]
  build_verify_cmd: "cd app && dotnet build Example.slnx --nologo"
```

Keep `fix_loop.claude_code_action_ref` as the template wrote it. The schema accepts only a
40-character commit SHA there (`schemas/scan-config.schema.json:157-161`). Then validate
with the platform clone's copy of the validator:

```bash
STRICT=1 python /path/to/auto-code-scanning/scripts/validate-scan-config.py scan-config.yaml
```

The copy the setup put in your `scripts/` cannot find the schema, because the setup does
not copy `schemas/`. Without `STRICT=1` it then prints a warning and exits 0 instead of
validating (`validate-scan-config.py:29`, `40-48`; `setup-scan-fix.py:71-78`).

The fix loop reads this file from the pull request's base commit, never from its head
(`autonomous-fix.yml:92-142`). Your changes take effect for the fix loop only after they
merge.

### 4. Pin the callers and grant their permissions

- **Who:** Operator
- **Operator STOP:** no

The caller templates pin `v2.0.0` (`templates/workflows/code-security-scan.yml:21`,
`templates/workflows/terraform-scan.yml:21` and `26`,
`templates/fix-loop/autonomous-fix.yml:55` and `59`). Move every pin to the release you
checked out in the prerequisites. For the fix-loop caller:

```yaml
jobs:
  fix:
    # Keep the template's `if:` here (see step 5).
    permissions:
      contents: read
      pull-requests: write
      issues: write
      actions: read
    uses: OWNER/auto-code-scanning/.github/workflows/autonomous-fix.yml@v2.2.0 # x-release-please-version
    with:
      pr_number: ${{ github.event.pull_request.number || github.event.inputs.pr_number }}
      config_path: scan-config.yaml
      scanning_repo: OWNER/auto-code-scanning
      scanning_repo_ref: v2.2.0 # x-release-please-version
    secrets: inherit
```

`OWNER` is the owner of the platform copy you call. The template grants only
`contents: read` (`templates/fix-loop/autonomous-fix.yml:32-33`), but the called workflow
needs the four permissions above; see
[REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#autonomous-fixyml). For the scan callers,
move `uses:` and `scanning-repo-ref` together as in [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md).

### 5. Check who can start the fix loop

- **Who:** Operator and Reviewer
- **Operator STOP:** yes. Do not merge until both agree the caller's `if:` admits only
  the people and bots you trust.

The caller's `if:` is the privilege boundary: it decides whose review or comment can make
the loop push with `AUTOFIX_TOKEN` (`templates/fix-loop/autonomous-fix.yml:37-53`). The
template admits a manual dispatch, or a non-fork pull request with the `ai-autofix`
label whose review or comment came from a listed bot or from an `OWNER`, `MEMBER` or
`COLLABORATOR`. Compare it with the rule your inline workflow enforced, and edit the bot
list to match yours. Read [SECURITY-MODEL.md](SECURITY-MODEL.md) before you widen it.

### 6. Remove the inline copies

- **Who:** Operator
- **Operator STOP:** no

- Delete any inline fix-loop or scan workflow that the callers replace. Keep each caller
  in its own workflow file: two calls from one caller workflow share a concurrency group
  (see [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md#concurrency)).
- Delete hard-coded paths and build commands from your own hooks and scripts; they are in
  `scan-config.yaml` now.
- Delete any local copy of the allowlist gate. The platform runs
  `scripts/check-fix-allowlist.py` from its own checkout (`autonomous-fix.yml:313`, `385`).

### 7. Create the secrets

- **Who:** Operator (needs permission to manage repository secrets)
- **Operator STOP:** yes. A person creates the secrets; no script does.

The setup creates the `ai-autofix` and `needs-human-review` labels, and only checks that
`AUTOFIX_TOKEN` and `ANTHROPIC_API_KEY` exist (`setup-scan-fix.py:126-155`). Create any
that are missing:

```bash
gh secret set AUTOFIX_TOKEN       # fine-grained token: Contents and Pull requests read/write, this repository only
gh secret set ANTHROPIC_API_KEY   # or CLAUDE_CODE_OAUTH_TOKEN
```

`AUTOFIX_TOKEN` is used only by the final push step (`autonomous-fix.yml:446-456`).

### 8. Review and merge

- **Who:** Operator, CI, then Reviewer
- **Operator STOP:** no

Open a pull request. CI runs the scan callers. The Reviewer checks the diff from step 2,
the pins from step 4 and the boundary from step 5, then approves. The Operator merges.

## Verify

- `STRICT=1 python /path/to/auto-code-scanning/scripts/validate-scan-config.py scan-config.yaml`
  prints `VALID`.
- A local commit runs the hooks through `hooks/dispatcher.sh`.
- Code scanning shows distinct categories: `<prefix>semgrep-csharp`,
  `<prefix>semgrep-typescript` and `<prefix>trivy-secrets` (`code-security-scan.yml:186`,
  `242`).
- On a test pull request labelled `ai-autofix`, a trusted review starts the fix loop. Its
  Analyze job runs with a read-only token (`autonomous-fix.yml:161-164`, `246`), and only
  the push step uses `AUTOFIX_TOKEN` (`autonomous-fix.yml:446-456`).
- A proposed fix that touches `.github/`, or a path containing a gated word such as
  `auth`, is not pushed. The pull request gets `needs-human-review` and a comment that
  names the reason (`autonomous-fix.yml:302-320`, `461-520`).

## Rollback

- **Who:** Operator, with Reviewer approval

1. Revert the migration pull request with `git revert`. The inline workflows and hooks
   come back from history.
2. Remove any required status checks you added for the new callers' jobs.
3. The labels and secrets can stay; nothing uses them without the caller.

## References

- [REUSABLE-WORKFLOWS.md](REUSABLE-WORKFLOWS.md): inputs, secrets and permissions.
- [FIX-LOOP.md](FIX-LOOP.md) and [SECURITY-MODEL.md](SECURITY-MODEL.md): how the fix loop
  works and what it trusts.
- [VERSION-PINNING.md](VERSION-PINNING.md): pinning rules.
- [BUMP-THE-SCAN.md](BUMP-THE-SCAN.md): later upgrades.
- [consumer-repo-setup-guide.md](consumer-repo-setup-guide.md): first-time setup.
