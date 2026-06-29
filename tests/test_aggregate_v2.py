"""Paper-v2 topological aggregation over the typed DAG."""

import pytest

from slacheck.envelope.v2.aggregate_v2 import compute_envelope_v2


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
