from pathlib import Path

import pytest
from typer.testing import CliRunner

from slacheck.cli import app
from slacheck.openslo import load_openslo_target

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_check_openslo_bundle_and_graph():
    result = CliRunner().invoke(app, [
        "check", str(EXAMPLES / "shop-openslo.yaml"), "--graph", str(EXAMPLES / "shop.yaml"),
        "--independent",
    ])
    assert result.exit_code == 0, result.output
    assert "Target: 99.9%" in result.stdout
    assert "Feasible" in result.stdout


def test_multiple_slos_require_selection(tmp_path):
    path = tmp_path / "multiple.yaml"
    bundle = (EXAMPLES / "shop-openslo.yaml").read_text()
    second = bundle.split("---\n")[1].replace("shop-availability", "other-availability")
    path.write_text(f"{bundle}---\n{second.replace('0.999', '0.9999')}")
    with pytest.raises(ValueError, match="--slo-name"):
        load_openslo_target(path)
    target = load_openslo_target(path, "other-availability")
    assert target.service == "frontend"
    assert target.availability_pct == pytest.approx(99.99)


def test_service_must_match_topology_entrypoint(tmp_path):
    path = tmp_path / "unmatched.yaml"
    path.write_text((EXAMPLES / "shop-openslo.yaml").read_text().replace("frontend", "other"))
    result = CliRunner().invoke(app, [
        "check", str(path), "--graph", str(EXAMPLES / "shop.yaml"), "--independent",
    ])
    assert result.exit_code == 2
    assert "spec.service" in result.output


@pytest.mark.parametrize(("old", "new", "match"), [
    ("openslo/v1", "openslo/v2", "openslo/v1"),
    ("Occurrences", "Timeslices", "Occurrences"),
    ("0.999", "99.9", "fraction"),
    ("0.999", "true", "fraction"),
])
def test_rejects_unsupported_objective(tmp_path, old, new, match):
    path = tmp_path / "invalid.yaml"
    path.write_text((EXAMPLES / "shop-openslo.yaml").read_text().replace(old, new))
    with pytest.raises(ValueError, match=match):
        load_openslo_target(path)
