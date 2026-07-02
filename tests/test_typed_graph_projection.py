"""Projection nx.DiGraph -> pure DependencyGraph with edge typing (paper-v2)."""

import networkx as nx
import pytest

from slacheck.graph.typed_graph import project_to_dependency_graph
from slacheck.models import Component, SloValues


def _g():
    g = nx.DiGraph()
    for n in ("UI", "StorA", "StorB"):
        g.add_node(n, component=Component(name=n, slo=SloValues(availability_pct=99.9)))
    g.add_edge("UI", "StorA")
    g.add_edge("UI", "StorB")
    return g


def test_empty_graph_clear_error():
    with pytest.raises(ValueError, match="no services found"):
        project_to_dependency_graph(nx.DiGraph(), "UI")


def test_missing_component_attr_clear_error():
    g = nx.DiGraph()
    g.add_node("UI", component=Component(name="UI", slo=SloValues()))
    g.add_node("Auth")  # no component attribute
    g.add_edge("UI", "Auth")
    with pytest.raises(ValueError, match="no 'component' attribute"):
        project_to_dependency_graph(g, "UI")


def test_mixed_override_preflight_error():
    # StorB is reached by UI (disjunctive group) AND by Other (default conjunctive) -> mixed.
    g = nx.DiGraph()
    for n in ("UI", "Other", "StorB"):
        g.add_node(n, component=Component(name=n, slo=SloValues(availability_pct=99.9)))
    g.add_edge("UI", "StorB")
    g.add_edge("Other", "StorB")
    overrides = {"disjunctive_groups": [{"parent": "UI", "children": ["StorB"]}]}
    with pytest.raises(ValueError, match="mixed dependency types"):
        project_to_dependency_graph(g, "UI", overrides)


def test_default_edges_are_conjunctive():
    dep = project_to_dependency_graph(_g(), "UI")
    assert all(e.edge_type == "conjunctive" for e in dep.edges)


def test_disjunctive_group_override():
    overrides = {"disjunctive_groups": [{"parent": "UI", "children": ["StorA", "StorB"]}]}
    dep = project_to_dependency_graph(_g(), "UI", overrides)
    assert all(e.edge_type == "disjunctive" for e in dep.edges)


def test_explicit_edge_type_override():
    overrides = {"edge_types": [{"source": "UI", "target": "StorA", "edge_type": "disjunctive"}]}
    dep = project_to_dependency_graph(_g(), "UI", overrides)
    by = {(e.source, e.target): e.edge_type for e in dep.edges}
    assert by[("UI", "StorA")] == "disjunctive"
    assert by[("UI", "StorB")] == "conjunctive"


def test_components_carried_over():
    dep = project_to_dependency_graph(_g(), "UI")
    assert set(dep.components) == {"UI", "StorA", "StorB"}
    assert dep.entrypoint == "UI"


def test_dispatch_requires_right_input():
    from slacheck.envelope.dispatch import evaluate_versioned

    with pytest.raises(ValueError):
        evaluate_versioned(paper_version="v2", graph=None)
    with pytest.raises(ValueError):
        evaluate_versioned(paper_version="v1", path=None)
