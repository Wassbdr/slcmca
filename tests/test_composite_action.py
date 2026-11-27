import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("target", "status", "findings"), [
    ("99.9", 0, 0),
    ("99.94", 1, 1),
    ("101", 2, None),
])
def test_action_publishes_sarif_before_enforcing_status(tmp_path, target, status, findings):
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    steps = action["runs"]["steps"]
    wrapper = next(step for step in steps if step.get("id") == "check")
    gate = steps[-1]
    output = tmp_path / "github-output"
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "RUNNER_TEMP": str(tmp_path),
        "TOPOLOGY": "examples/shop-openslo.yaml",
        "GRAPH": "examples/shop.yaml",
        "TARGET": target,
        "SLO_NAME": "shop-availability",
        "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}",
    }
    subprocess.run(["bash", "-e", "-c", wrapper["run"]], cwd=ROOT, env=env, check=True)
    results = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert results["status"] == str(status)
    if findings is None:
        assert "sarif-file" not in results
    else:
        document = json.loads(Path(results["sarif-file"]).read_text())
        assert len(document["runs"][0]["results"]) == findings
    enforced = subprocess.run(
        ["bash", "-e", "-c", gate["run"]],
        cwd=ROOT,
        env={**env, "CHECK_STATUS": results["status"]},
        check=False,
    )
    assert enforced.returncode == status
