"""Paper-v2 topological aggregation over the typed DAG."""

import pytest

from slacheck.envelope.v2.aggregate_v2 import compute_envelope_v2
from slacheck.models import Component, DependencyEdge, DependencyGraph, SloValues


def _c(name, lat=None, av=None):
    return Component(name=name, slo=SloValues(response_time_ms=lat, availability_pct=av))


def test_disjunctive_latency_takes_responding_branch():
    # UI -> Stor; Stor -> {StorA fast 5ms, StorB slow 50ms} disjunctive.
    # Responding (min) branch wins: 10 + 2 + 5 = 17, NOT the 62 of the slow path.
    g = DependencyGraph(
        components={
            "UI": _c("UI", lat=10),
            "Stor": _c("Stor", lat=2),
            "StorA": _c("StorA", lat=5),
            "StorB": _c("StorB", lat=50),
        },
        edges=[
            DependencyEdge(source="UI", target="Stor"),
            DependencyEdge(source="Stor", target="StorA", edge_type="disjunctive"),
            DependencyEdge(source="Stor", target="StorB", edge_type="disjunctive"),
        ],
        entrypoint="UI",
    )
    assert compute_envelope_v2(g).response_time_ms == pytest.approx(17.0)


def test_conjunctive_latency_takes_worst_path():
    # UI -> A(20), UI -> B(5), both conjunctive: worst path dominates = 10 + 20 = 30.
    g = DependencyGraph(
        components={"UI": _c("UI", lat=10), "A": _c("A", lat=20), "B": _c("B", lat=5)},
        edges=[
            DependencyEdge(source="UI", target="A"),
            DependencyEdge(source="UI", target="B"),
        ],
        entrypoint="UI",
    )
    assert compute_envelope_v2(g).response_time_ms == pytest.approx(30.0)


def test_envelope_matches_paper_conjunctive(paper_scenario_v2):
    env = compute_envelope_v2(paper_scenario_v2["graph"])
    assert env.availability_pct == pytest.approx(99.7)  # conjunctive == v1
    assert env.response_time_ms == 24.0  # max path: UI(10)+Auth(14)
    assert env.cost_eur_h == pytest.approx(23.0)  # 8 + 6 + 9


def test_redundancy_raises_availability(paper_scenario_v2_redundant):
    env = compute_envelope_v2(paper_scenario_v2_redundant["graph"])
    # all-conjunctive UI+Stor+StorA+StorB would give 99.6; disjunctive StorA/StorB lifts it.
    assert env.availability_pct > 99.79
    # UI (99.9) conjunctive with Stor-group; Stor-group ≈ 99.9 ⊗ (StorA‖StorB=99.9999)
    assert env.availability_pct == pytest.approx(99.8, abs=0.01)


def test_empty_graph_raises():
    from slacheck.models import DependencyGraph

    with pytest.raises(ValueError):
        compute_envelope_v2(DependencyGraph(components={}, edges=[], entrypoint="x"))
