import json

import pytest
from typer.testing import CliRunner

from slacheck.cli import app


@pytest.fixture
def topology(tmp_path):
    path = tmp_path / "shop graph.yaml"
    path.write_text(
        "entrypoint: web\n"
        "global_target: {availability_pct: 99.85}\n"
        "components:\n"
        "  - {name: web, slo: {availability_pct: 99.9}}\n"
        "  - {name: db, slo: {availability_pct: 99.91}}\n"
        "edges:\n"
        "  - {source: web, target: db}\n"
    )
    return path


def test_json_reports_conditional_repairs(topology):
    run = CliRunner().invoke(app, ["check", str(topology), "--format", "json"])
    assert run.exit_code == 1
    report = json.loads(run.stdout)
    assert report["schema_version"] == 1
    assert report["entrypoint"] == "web"
    assert not report["feasible"]
    exact, = report["checks"]
    assert exact["model"] == "independent"
    assert exact["achievable_pct"] == pytest.approx(99.9 * 0.9991)
    assert [repair["service"] for repair in exact["improvements"]] == ["web", "db"]
    web = exact["improvements"][0]
    assert web["required_pct"] == pytest.approx(99.85 / 0.9991)
    assert web["increase_pp"] == pytest.approx(99.85 / 0.9991 - 99.9)
    assert web["estimated_cost"] is None


def test_rank_costed_repairs_and_validate_cost_coverage(topology, tmp_path):
    path = tmp_path / "costs.yaml"
    commands = [
        "check", str(topology), "--format", "json",
        "--improvement-costs", str(path),
    ]
    path.write_text("web: 5\ndb: 1\n")
    run = CliRunner().invoke(app, commands)
    assert run.exit_code == 1
    repairs = json.loads(run.stdout)["checks"][0]["improvements"]
    db, web = repairs
    assert [db["service"], web["service"]] == ["db", "web"]
    assert db["estimated_cost"] < web["estimated_cost"]

    path.write_text("web: 5\n")
    run = CliRunner().invoke(app, commands)
    assert run.exit_code == 2
    assert "add an improvement cost for 'db'" in run.output


def test_sarif_has_encoded_source_path_and_actionable_repair(topology, monkeypatch):
    monkeypatch.chdir(topology.parent)
    run = CliRunner().invoke(
        app, ["check", topology.name, "--format", "sarif"],
    )
    assert run.exit_code == 1
    report = json.loads(run.stdout)
    assert report["version"] == "2.1.0"
    checked, = report["runs"]
    issue, = checked["results"]
    rule, = checked["tool"]["driver"]["rules"]
    assert rule["id"] == issue["ruleId"] == "availability.infeasible"
    location = issue["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "shop%20graph.yaml"
    assert "improve web" in issue["message"]["text"]


def test_feasible_sarif_has_no_results(topology):
    run = CliRunner().invoke(
        app, ["check", str(topology), "--format", "sarif", "--slo", "99.8"],
    )
    assert run.exit_code == 0, run.output
    assert json.loads(run.stdout)["runs"][0]["results"] == []


def test_legacy_both_can_emit_json(topology):
    run = CliRunner().invoke(app, ["check", str(topology), "--both", "--format", "json"])
    assert run.exit_code == 1
    report = json.loads(run.stdout)
    assert [check["model"] for check in report["checks"]] == ["v1", "v2"]
    assert report["checks"][-1]["faults"]
