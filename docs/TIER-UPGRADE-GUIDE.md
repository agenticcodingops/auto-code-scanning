# Tier Upgrade Guide

Install through [Getting started](SETUP-GUIDE.md) first. A **tier** (`starter`,
`standard` or `strict`) is a starting configuration. It selects two things:

- the `scan-config.yaml` template that setup writes (`templates/scan-config/<tier>.yaml`);
- with the pre-commit runner only, the `.pre-commit-config.yaml` template
  (`templates/<tier>/pre-commit-config.yaml`).

Lefthook uses **one manifest for every tier** (`templates/lefthook/lefthook.yml`).
Changing the tier does not rewrite it.

## What each tier blocks

The hooks that run, by runner and tier. "Runs when" says which staged or pushed files
start the hook; a hook with nothing to check passes. Every hook that runs blocks the
commit or push when it reports a finding at its own threshold, and when its tool or
trusted config is missing. See the [hook reference](HOOK-REFERENCE.md) for each hook.

| Hook | Stage | Runs when | Lefthook (all tiers) | pre-commit starter | pre-commit standard | pre-commit strict |
|---|---|---|---|---|---|---|
| `trivy-secrets` (Trivy secret scan) | commit | any staged file | yes | yes | yes | yes |
| `gitleaks` | commit | any staged file | yes | no | yes | yes |
| `detect-private-key` | commit | any staged file | no | yes | yes | yes |
| `trailing-whitespace`, `end-of-file-fixer`, `check-yaml` | commit | matching files | no | yes | yes | yes |
| `check-json` | commit | `.json` | no | no | yes | yes |
| `check-added-large-files` (over 500 KB), `check-merge-conflict` | commit | any staged file | no | no | no | yes |
| `validate-scan-config` | commit | `scan-config.yaml` | yes | no | no | no |
| `validate-suppressions` | commit | the suppression registry | no | no | no | yes |
| `terraform_fmt` | commit | `.tf` | no | yes | yes | yes |
| `terraform_validate` | commit | `.tf` | no | no | yes | yes |
| `terraform_docs` | commit | `.tf` | no | no | no | yes |
| `trivy-iac-critical` (CRITICAL only) | commit | `.tf` | yes | no | yes | yes |
| `trivy-iac-full` (CRITICAL to LOW) | push | changed `.tf` / `.tf.json` | no | no | no | yes |
| `checkov` | push | changed `.tf` / `.tf.json` | yes | no | no | no |
| `checkov-strict` | push | changed `.tf` / `.tf.json` | no | no | no | yes |
| `tflint` | push | changed `.tf` / `.tf.json` | yes | no | yes | yes |
| `semgrep-csharp` | commit | `.cs` | yes | no | no | no |
| `dotnet-format` | commit | `.cs`, `.csproj` | yes | no | no | no |
| `dotnet-build` | push | changed `.cs`, `.csproj` | yes | no | no | no |
| `semgrep-typescript`, `eslint` | commit | `.ts`, `.tsx`, `.js`, `.jsx` | yes | no | no | no |
| `prettier` | commit | TS/JS, `.json`, `.css`, `.scss`, `.md` | yes | no | no | no |
| `sqlfluff` | commit | `.sql` | yes | no | no | no |

The pre-commit templates are Terraform-focused. To run application hooks with
pre-commit, add them deliberately from [the hook reference](HOOK-REFERENCE.md).
`snyk-iac` is commented out in the standard and strict templates.

### What the `scan-config.yaml` tier settings change

The three `scan-config.yaml` templates differ in `global.blocking_severities`,
`ci.fail_on`, the per-tool `enabled` flags, `global.performance`, the suppression
settings and `fix_loop.enabled`. In release v3.1.2 the hooks and CI workflows **do not
read** the severity settings (`blocking_severities`, `severity_levels`, `ci.fail_on`),
the per-tool `enabled` flags or `global.performance`. Each hook has its own fixed threshold (for example
`trivy-iac-critical` blocks CRITICAL only), and the Terraform CI gate always counts
CRITICAL and HIGH. What the tier settings do change:

- `languages.<name>.enabled` decides which languages the **CI** app-code scan covers
  (`csharp`, `typescript`). It does not stop local Lefthook hooks from running on
  matching files.
- `suppressions.file` names the suppression registry that hooks and CI read. The
  other keys under `suppressions` are not read; approval levels and the expiry limit
  come from the `settings` block of the registry file itself.
- `fix_loop.enabled` turns the optional fix loop on. The **strict template sets it to
  `true`**. If you choose strict for scanning only, set `fix_loop.enabled: false`.
  The loop still needs its caller workflow, secrets and the `ai-autofix` label on a
  pull request before anything runs.

## Starter to Standard

**When to upgrade:** when the team commits through the starter hooks without
friction and is ready for IaC security checks at commit and push. The time frame is
yours; there is no deadline or automatic escalation.

### Hooks to add (pre-commit runner)

**pre-commit-hooks repo:**

```yaml
      - id: check-json
```

`check-yaml` keeps its existing arguments.

**pre-commit-terraform repo:**

```yaml
      - id: terraform_validate
```

**auto-code-scanning repo:**

```yaml
      - id: tflint
        stages: [pre-push]
      - id: gitleaks
        stages: [pre-commit]
      - id: trivy-iac-critical
        stages: [pre-commit]
```

Keep the starter hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`,
`detect-private-key`, `terraform_fmt` and `trivy-secrets`.

---

## Standard to Strict

**When to upgrade:** when standard runs cleanly and the team wants full IaC
severity at push, strict Checkov, suppression validation and generated Terraform
docs.

### Hooks to add (pre-commit runner)

**pre-commit-hooks repo:**

```yaml
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: check-merge-conflict
```

**pre-commit-terraform repo** (needs `terraform-docs` installed):

```yaml
      - id: terraform_docs
```

**auto-code-scanning repo:**

```yaml
      - id: trivy-iac-full
        stages: [pre-push]
      - id: checkov-strict
        stages: [pre-push]
      - id: validate-suppressions
        stages: [pre-commit]
```

Keep all standard hooks.

### Optional: Commitizen

Commitizen (conventional commit messages) is available, commented out, in the strict
template. It is pinned to a full commit SHA, like every other external hook:

```yaml
  # - repo: https://github.com/commitizen-tools/commitizen
  #   rev: a3498aba5e94c9f7c4acb529b5e7eb6df65fd053  # v3.29.1
  #   hooks:
  #     - id: commitizen
  #       stages: [commit-msg]
```

---

## Preserving customizations

When upgrading, do NOT replace your entire `.pre-commit-config.yaml`. Instead:

1. Save reviewed `.scanning/configs/`, `scan-config.yaml`, `hooks/`, `schemas/`, `scripts/`,
   caller workflows and runner configuration
   (`lefthook.yml` or `.pre-commit-config.yaml`) externally, including full-SHA pins
   and customized editor hooks, before making any of the changes below: this captures
   the pre-upgrade state, not a copy already modified by them.
2. Compare `scan-config.yaml` with the target tier's configuration defaults and
   merge reviewed settings deliberately. Setup preserves an existing config unless
   forced; `--enable-fix-loop` alone does not change an existing disabled setting.
3. Open your current runner config and the target tier template side by side.
4. Add only the new hooks listed above.
5. Keep any custom `args`, `exclude`, or `files` overrides you have added.
6. Keep any additional third-party hooks your team has added.
7. Review custom settings against the current security contract; the setup verifier
   checks exact shipped hook settings, so customized manifests need separate review.
8. Begin setup and verification with the required entries from the new tier
   template. With pre-commit, let setup reinstall the push transaction adapter (the
   `.git/hooks/pre-push` script that scans every pushed ref; see
   [Getting started](SETUP-GUIDE.md#5-install-local-hooks)).
9. Compare overwritten policy and workflows, restore approved customizations and full
   SHA pins after template verification, then stage a real change and make a scanned
   commit as in [consumer acceptance](TESTING-GUIDE-CONSUMING-REPO.md).

## Version pinning

Every external hook `rev:` is a full 40-character commit SHA with the version in a
comment, and [Getting started](SETUP-GUIDE.md#6-configure-ci-callers) asks you to pin
the auto-code-scanning entry to a full SHA too. Keep that form when you update.

- For the **auto-code-scanning** entry, do not use `pre-commit autoupdate`. Resolve the
  target release's commit, set `rev:` to it, and upgrade the vendored hooks, scripts,
  schemas and workflow pins together: [Getting started upgrades](SETUP-GUIDE.md#10-upgrade-between-releases).
- For **other** hook repositories, `pre-commit autoupdate --freeze --repo <url>` writes
  the newest tag's commit SHA with a `# frozen: vX.Y.Z` comment. Plain
  `pre-commit autoupdate` writes a tag name instead, which breaks the SHA rule. Read the
  upstream release notes and review the diff before committing.

The setup verifier compares the runner file with the shipped template, so run it
before you change pins and review the pin change separately.
