"""Trust boundary of the Gemini review (gemini-code-review.yml and .github/scripts/gemini_review.py).

The review step holds the model key and a token that can write to pull requests. Nothing from the pull request may
run in it, or be read as its configuration: the job checks out the base commit, so the helper, the styleguide and the
ignore list are the base branch's, and the helper diffs the pull request's commits as git objects without checking
them out.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WF = REPO_ROOT / ".github" / "workflows" / "gemini-code-review.yml"
HELPER = REPO_ROOT / ".github" / "scripts" / "gemini_review.py"
BASE_SHA = "${{ github.event.pull_request.base.sha }}"


def _workflow():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _steps():
    return [step for job in _workflow()["jobs"].values() for step in job.get("steps") or []]


def _load_helper():
    spec = importlib.util.spec_from_file_location("gemini_review_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _holds_a_credential(step):
    text = yaml.safe_dump({k: step.get(k) for k in ("env", "with", "run")})
    return "secrets." in text or "github.token" in text


class WorkflowTrustTests(unittest.TestCase):
    def test_every_checkout_is_the_base_commit(self):
        # Without a ref, a pull_request run checks out the pull request's merge commit, and the helper would come
        # from the pull request.
        checkouts = [s for s in _steps() if str(s.get("uses", "")).startswith("actions/checkout@")]
        self.assertTrue(checkouts, "the workflow has no checkout")
        for step in checkouts:
            options = step.get("with") or {}
            self.assertEqual(options.get("ref"), BASE_SHA, "check out the base commit: " + str(step.get("name")))
            self.assertNotIn("repository", options, "a checkout of another repository can be the pull request's fork")
            self.assertIs(options.get("persist-credentials"), False)

    def test_no_step_refers_to_the_head_except_as_a_commit_to_diff(self):
        # The head commit may reach the helper only as the HEAD_SHA value it diffs.
        for step in _steps():
            for key, value in (step.get("with") or {}).items():
                self.assertNotIn("head", str(value), "a step input names the pull request's head: " + key)
            for key, value in (step.get("env") or {}).items():
                if "head" in str(value) or "head_ref" in str(value):
                    self.assertEqual((key, value), ("HEAD_SHA", "${{ github.event.pull_request.head.sha }}"))

    def test_the_credential_step_runs_only_the_base_helper(self):
        holders = [s for s in _steps() if _holds_a_credential(s)]
        self.assertEqual(len(holders), 1, "expected one step with the key and the token")
        step = holders[0]
        self.assertNotIn("uses", step, "an action in the credential step would run with the key")
        self.assertEqual(step["run"].strip(), "python3 -I .github/scripts/gemini_review.py")
        self.assertEqual(step["env"]["BASE_SHA"], BASE_SHA)
        # the checkout comes before it, so the helper it runs is the base commit's
        steps = _steps()
        last_checkout = max(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/checkout@"))
        self.assertLess(last_checkout, steps.index(step))


@unittest.skipIf(shutil.which("git") is None, "needs git")
class HelperDiffTests(unittest.TestCase):
    """The helper reviews the head commit's changes while the working tree, and so its configuration, stay the base."""

    @classmethod
    def setUpClass(cls):
        cls.helper = _load_helper()
        cls.tmp = tempfile.mkdtemp(prefix="gemini-review-")
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        cls.env = env

        def git(*args, cwd):
            return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        origin = os.path.join(cls.tmp, "origin")
        work = os.path.join(cls.tmp, "author")
        git("init", "-q", "--bare", origin, cwd=cls.tmp)
        git("init", "-q", "-b", "main", work, cwd=cls.tmp)

        def write(rel, text):
            path = os.path.join(work, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)

        write(".gemini/config.yaml", 'comment_severity_threshold: "MEDIUM"\nignore_patterns:\n  - "*.lock"\n')
        write(".github/scripts/gemini_review.py", "print('base helper')\n")
        write("src/app.py", "x = 1\n")
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "base", cwd=work)
        cls.base = git("rev-parse", "HEAD", cwd=work)
        git("push", "-q", origin, "main", cwd=work)

        git("checkout", "-q", "-b", "feature", cwd=work)
        write(".gemini/config.yaml", 'comment_severity_threshold: "HIGH"\nignore_patterns:\n  - "src/**"\n')
        write(".github/scripts/gemini_review.py", "print('head helper')\n")
        write("src/app.py", "x = 2\n")
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "head", cwd=work)
        cls.head = git("rev-parse", "HEAD", cwd=work)
        # a pull request ref, as GitHub keeps one for every pull request, branch or fork
        git("push", "-q", origin, "HEAD:refs/pull/7/head", cwd=work)

        # the job's checkout: the base commit, with the base branch's history and no pull request refs
        cls.checkout = os.path.join(cls.tmp, "checkout")
        git("clone", "-q", "--no-checkout", origin, cls.checkout, cwd=cls.tmp)
        git("checkout", "-q", "--detach", cls.base, cwd=cls.checkout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def in_checkout(self, fn, *args):
        here = os.getcwd()
        saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL")}
        os.environ.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        os.chdir(self.checkout)
        try:
            return fn(*args)
        finally:
            os.chdir(here)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_the_diff_is_the_head_commits_changes(self):
        diff = self.in_checkout(self.helper.get_diff, self.base, self.head, [])
        self.assertIn("+x = 2", diff)
        self.assertIn("+print('head helper')", diff)

    def test_the_working_tree_and_its_configuration_stay_the_base(self):
        self.in_checkout(self.helper.get_diff, self.base, self.head, [])
        threshold, ignore = self.in_checkout(self.helper.load_repo_config, ".gemini/config.yaml")
        self.assertEqual((threshold, ignore), ('"MEDIUM"', ["*.lock"]), "the review settings came from the head")
        with open(os.path.join(self.checkout, ".github", "scripts", "gemini_review.py"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "print('base helper')\n")

    def test_the_base_ignore_list_applies_to_the_head(self):
        _, ignore = self.in_checkout(self.helper.load_repo_config, ".gemini/config.yaml")
        diff = self.in_checkout(self.helper.get_diff, self.base, self.head, ignore)
        self.assertIn("+x = 2", diff, "the head's own ignore list must not hide its changes")

    def test_only_full_commit_ids_reach_git(self):
        for base, head in ((self.base, "--upload-pack=x"), ("main", self.head), (self.base, ""), (self.base, None)):
            with self.assertRaises(ValueError):
                self.in_checkout(self.helper.get_diff, base, head, [])


if __name__ == "__main__":
    unittest.main()
