# Running Codex tasks in GitHub Actions

`.github/workflows/codex-task.yml` runs one coding task with OpenAI Codex on a GitHub-hosted runner and uploads
the result as a patch. It is for maintainers and their orchestration agents. It doesn't push a branch or open a
pull request: whoever dispatched it applies the patch and opens the PR under their own account, so the normal CI
and reviews run on it. A PR opened with the workflow's `GITHUB_TOKEN` would start no workflows.

## One-time setup (repository owner)

1. Create an OpenAI API key in a project with a monthly budget limit set on the OpenAI platform. Usage is billed
   to the API account. The workflow can't cap spend itself; its 30-minute timeout only bounds a single run.
2. Store it as a repository secret named `OPENAI_API_KEY`:
   `gh secret set OPENAI_API_KEY --repo agenticcodingops/auto-code-scanning`
3. Only the accounts named in the workflow's `if:` condition can run it. Edit that list to add another
   maintainer.

## Running a task

```bash
id="$(date -u +%Y%m%d%H%M%S)-issue-155"
gh workflow run codex-task.yml --ref main \
  -f base=main -f request_id="$id" -f task="Fix #155: <what to change and how to check it>"
# The new run can take a few seconds to appear in the list.
run=""
for _ in $(seq 1 30); do
  run=$(gh run list --workflow codex-task.yml --limit 20 --json databaseId,displayTitle \
    -q ".[] | select(.displayTitle == \"codex-$id\") | .databaseId" | head -1)
  [ -n "$run" ] && break
  sleep 5
done
[ -n "$run" ] || { echo "No run named codex-$id appeared within 150 seconds" >&2; exit 1; }
gh run watch "$run" --exit-status
gh run download "$run" -n "codex-result-$id" -D "<a folder outside the checkout>"
```

The artifact holds `codex.patch`, `stat.txt`, `final-message.md` (Codex's summary and test results) and
`base-sha.txt`. Before upload, the workflow leaves agent configuration (`CLAUDE.md`, `.claude/`, `.mcp.json` and
similar) out of the patch, refuses binary changes, and secret-scans the result with Trivy; if the scan fails or
finds a secret, nothing is uploaded and the job log doesn't show the match. If the artifact also holds
`TOUCHES-WORKFLOWS`, the patch edits `.github/workflows/`: read it closely before applying.

To land it, in a clean checkout of the base commit: create a branch, `git apply --check codex.patch`,
`git apply codex.patch`, read the diff, stage files by name, commit with a Conventional Commit title, push and open
the PR. Then review it like any other change.

## What Codex can do in the run

- It runs with the `:workspace` permission profile: it can edit the checkout but has no network access, so the
  workflow installs the Python test dependencies, and Checkov in its own virtual environment, before it starts. PowerShell and Pester come with
  the runner. Trivy, TFLint and Gitleaks aren't installed; tests that need them are skipped or fail, and Codex
  is told to report what it couldn't run.
- The action's default `drop-sudo` safety strategy removes `sudo` before Codex starts. The API key stays behind
  the action's proxy.
- The job's token can only read the repository, and the checkout keeps no credentials.
