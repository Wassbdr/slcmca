import pytest
from typer.testing import CliRunner

from slacheck.availability import check_availability
from slacheck.cli import app
from slacheck.models import Component, DependencyEdge, DependencyGraph, SloValues


def _graph(values, links):
    return DependencyGraph(
        entrypoint="web",
        components={
            name: Component(name=name, slo=SloValues(availability_pct=value))
            for name, value in values.items()
        },
        edges=[DependencyEdge(source=a, target=b, edge_type=kind) for a, b, kind in links],
    )


def test_shared_fallback_dependency_is_not_independent_of_itself():
    graph = _graph(
        {"web": 100, "a": 80, "b": 80, "db": 99.9, "offline": None},
        [
            ("web", "a", "disjunctive"),
            ("web", "b", "disjunctive"),
            ("a", "db", "conjunctive"),
            ("b", "db", "conjunctive"),
        ],
    )
    result = check_availability(graph, 99)
    assert not result.feasible
    assert result.achievable_pct == pytest.approx(99.9 * (1 - 0.2 * 0.2))
    assert result.thresholds_pct == pytest.approx({
        "db": None,
        "web": None,
        "a": 100 * (1 - (1 - 99 / 99.9) / 0.2),
        "b": 100 * (1 - (1 - 99 / 99.9) / 0.2),
    })


def test_shared_required_service_is_counted_once():
    graph = _graph(
        {"web": 100, "a": 100, "b": 100, "db": 99.9},
        [(a, b, "conjunctive") for a, b in [
            ("web", "a"), ("web", "b"), ("a", "db"), ("b", "db"),
        ]],
    )
    result = check_availability(graph, 99.9)
    assert result.feasible
    assert result.achievable_pct == pytest.approx(99.9)
    assert result.thresholds_pct == pytest.approx({
        "web": 100, "a": 100, "b": 100, "db": 99.9,
    })


def test_zero_and_hundred_percent_targets():
    graph = _graph({"web": 99}, [])
    assert check_availability(graph, 0).thresholds_pct == {"web": 0}
    result = check_availability(graph, 100)
    assert not result.feasible
    assert result.thresholds_pct == {"web": 100}


@pytest.mark.parametrize("value", [None, -1, 101, float("nan")])
def test_invalid_reachable_measurements_name_the_service(value):
    with pytest.raises(ValueError, match=r"set web\.availability_pct"):
        check_availability(_graph({"web": value}, []), 99)


def test_independent_cli_reports_thresholds_and_exits_nonzero(tmp_path):
    topology = tmp_path / "topology.yaml"
    topology.write_text(
        "entrypoint: web\n"
        "global_target: {availability_pct: 99.9}\n"
        "components:\n"
        "  - {name: web, slo: {availability_pct: 99.8}}\n"
    )
    result = CliRunner().invoke(app, ["check", str(topology), "--independent"])
    assert result.exit_code == 1
    assert "Achievable: 99.8%" in result.stdout
    assert "web: 99.9%" in result.stdout
    assert "Infeasible" in result.stdout
