"""Graph construction from fixtures: nodes, edges, SLO attributes, cycle-breaking."""

import networkx as nx
import pytest

from slacheck.datadog.fixture_client import FixtureClient
from slacheck.graph.builder import build_graph


@pytest.fixture
def built():
    g, dropped = build_graph(FixtureClient(), entrypoint="ts-gateway-service")
    return g, dropped


def test_all_services_are_nodes(built):
    g, _ = built
    expected = {
        "ts-gateway-service",
        "ts-travel-service",
        "ts-order-service",
        "ts-route-service",
        "ts-train-service",
        "ts-station-service",
    }
    assert set(g.nodes) == expected


def test_graph_is_dag_after_breaking_cycle(built):
    g, dropped = built
    assert nx.is_directed_acyclic_graph(g)
    # exactly one back-edge closes the cycle (station -> travel); it is the one dropped,
    # so all forward reachability from the entrypoint is preserved.
    assert dropped == [("ts-station-service", "ts-travel-service")]


def test_forward_reachability_preserved(built):
    g, _ = built
    # route must remain reachable (the worst-availability node): not severed by cycle-breaking
    assert nx.has_path(g, "ts-gateway-service", "ts-route-service")


def test_nodes_carry_measured_slo(built):
    g, _ = built
    route = g.nodes["ts-route-service"]["component"]
    # route: errors 250 / requests 50000 -> 99.5% availability; p99 18 ms
    assert route.slo.availability_pct == pytest.approx(99.5)
    assert route.slo.response_time_ms == 18.0
    assert g.nodes["ts-travel-service"]["component"].slo.response_time_ms == 24.0


def test_cost_is_none_from_datadog(built):
    g, _ = built
    assert g.nodes["ts-gateway-service"]["component"].slo.cost_eur_h is None
