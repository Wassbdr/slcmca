"""Pure DependencyGraph (paper-v2): topological order, indegree, root-to-leaf paths."""

import pytest

from slacheck.models import Component, DependencyEdge, DependencyGraph, SloValues


def _comp(name: str) -> Component:
    return Component(name=name, slo=SloValues(availability_pct=99.9))


@pytest.fixture
def ui_auth_stor() -> DependencyGraph:
    # The paper's running case: UI -> Auth, UI -> Stor (both conjunctive).
    return DependencyGraph(
        components={n: _comp(n) for n in ("UI", "Auth", "Stor")},
        edges=[
            DependencyEdge(source="UI", target="Auth"),
            DependencyEdge(source="UI", target="Stor"),
        ],
        entrypoint="UI",
    )


def test_topological_order_parents_before_children(ui_auth_stor):
    order = ui_auth_stor.topological_order()
    assert order[0] == "UI"
    assert set(order) == {"UI", "Auth", "Stor"}


def test_indegrees_match_paper(ui_auth_stor):
    assert ui_auth_stor.indegree("UI") == 0
    assert ui_auth_stor.indegree("Auth") == 1
    assert ui_auth_stor.indegree("Stor") == 1


def test_root_to_leaf_paths(ui_auth_stor):
    paths = ui_auth_stor.root_to_leaf_paths()
    assert ["UI", "Auth"] in paths
    assert ["UI", "Stor"] in paths
    assert len(paths) == 2


def test_cycle_raises():
    g = DependencyGraph(
        components={n: _comp(n) for n in ("a", "b")},
        edges=[DependencyEdge(source="a", target="b"), DependencyEdge(source="b", target="a")],
        entrypoint="a",
    )
    with pytest.raises(ValueError):
        g.topological_order()


def test_mixed_incoming_edge_types_rejected():
    with pytest.raises(ValueError):
        DependencyGraph(
            components={n: _comp(n) for n in ("a", "b", "c")},
            edges=[
                DependencyEdge(source="a", target="c", edge_type="conjunctive"),
                DependencyEdge(source="b", target="c", edge_type="disjunctive"),
            ],
            entrypoint="a",
        )


def test_edge_type_into_defaults_conjunctive(ui_auth_stor):
    assert ui_auth_stor.edge_type_into("Auth") == "conjunctive"
    assert ui_auth_stor.edge_type_into("UI") == "conjunctive"  # no parents → default
