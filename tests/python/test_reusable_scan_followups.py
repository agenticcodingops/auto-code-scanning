"""PR comments retain severity ordering independently of gate policy."""
import re
import shutil
import subprocess
from pathlib import Path
import pytest
import yaml
WORKFLOW = Path(__file__).resolve().parents[2] / '.github/workflows/reusable-scan.yml'
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))

# --- the PR comment's sort ---------------------------------------------------------------------

def comparator_body():
    steps = workflow()["jobs"]["pr-comment"]["steps"]
    script = next(step["with"]["script"] for step in steps if "github-script" in step.get("uses", ""))
    match = re.search(r"\.sort\(\(a, b\) => \{(.*?)\n\s*\}\)", script, re.S)
    assert match, "the PR comment's sort was not found"
    return match.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_pr_comment_lists_critical_findings_first():
    program = (
        "const cmp = (a, b) => {" + comparator_body() + "};\n"
        "const f = ['LOW', 'CRITICAL', 'MEDIUM', 'HIGH', 'UNKNOWN', 'CRITICAL']"
        ".map((severity) => ({ severity }));\n"
        "console.log(f.sort(cmp).map((x) => x.severity).join(','));\n"
    )
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CRITICAL,CRITICAL,HIGH,MEDIUM,LOW,UNKNOWN"


def test_the_sort_uses_nullish_coalescing_not_or():
    body = comparator_body()
    assert "?? 4" in body
    assert "|| 4" not in body
