"""Supply-chain pins in this repository's own workflows (docs/VERSION-PINNING.md, "Third-Party Action Pinning").

A tag can be moved to other code, so every third-party action is pinned to a commit, a container image is pinned to
a digest, and the optional Snyk job installs an exact CLI version. Until v2.3.2 `claude.yml` (which holds the OAuth
token) and `semgrep.yml` were exceptions, the semgrep image had no tag or digest, and the Snyk job installed whatever
npm called latest.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))

ACTION_SHA = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
SNYK_INSTALL = re.compile(r"npm\s+install\s+(?:-g|--global)\s+snyk(\S*)")


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _uses(workflow):
    """Every `uses` value: a reusable-workflow call on a job, or a step."""
    for job in (workflow.get("jobs") or {}).values():
        if "uses" in job:
            yield job["uses"]
        for step in job.get("steps") or []:
            if "uses" in step:
                yield step["uses"]


def _images(workflow):
    for job in (workflow.get("jobs") or {}).values():
        container = job.get("container")
        if isinstance(container, str):
            yield container
        elif isinstance(container, dict) and "image" in container:
            yield container["image"]
        for service in (job.get("services") or {}).values():
            if isinstance(service, dict) and "image" in service:
                yield service["image"]


def test_the_workflows_were_found():
    # A guard against a glob that matches nothing, which would make every check below pass.
    assert len(WORKFLOWS) >= 10


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(path):
    for ref in _uses(_load(path)):
        if ref.startswith("./"):
            continue  # a workflow or action in this repository, at the commit being tested
        assert not ref.startswith("docker://"), f"{path.name}: {ref} runs an image by reference; use a digest"
        assert ACTION_SHA.match(ref), f"{path.name}: {ref} is not pinned to a 40-character commit"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_container_image_is_pinned_by_digest(path):
    for image in _images(_load(path)):
        assert IMAGE_DIGEST.search(image), f"{path.name}: image {image} has no @sha256 digest"


def test_the_snyk_job_installs_an_exact_version():
    installs = []
    for path in WORKFLOWS:
        for match in SNYK_INSTALL.finditer(path.read_text(encoding="utf-8")):
            installs.append((path.name, match.group(1)))
    assert installs, "the Snyk install was not found; the search no longer matches"
    for name, spec in installs:
        assert re.fullmatch(r"@\d+\.\d+\.\d+", spec), f"{name}: `npm install -g snyk{spec}` is not an exact version"
