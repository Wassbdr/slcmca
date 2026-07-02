"""Critical-path extraction: latency = max-latency chain, availability = min-availability chain."""

import networkx as nx
import pytest

from slacheck.datadog.fixture_client import FixtureClient
from slacheck.graph.builder import build_graph
from slacheck.graph.critical_path import critical_path
from slacheck.models import Component, SloValues


@pytest.fixture
def g():
    graph, _ = build_graph(FixtureClient(), entrypoint="ts-gateway-service")
    return graph


def test_latency_path_is_max_weight_chain(g):
    path = [c.name for c in critical_path(g, "ts-gateway-service", "latency")]
    # gateway -> travel(24,slowest) -> route(18) -> station(13) dominates total latency
    assert path == [
        "ts-gateway-service",
        "ts-travel-service",
        "ts-route-service",
        "ts-station-service",
    ]


def test_availability_path_includes_worst_node(g):
    path = [c.name for c in critical_path(g, "ts-gateway-service", "availability")]
    # route is the worst-availability service (99.5%); the min-availability path must hit it
    assert "ts-route-service" in path


def test_target_constrains_endpoint(g):
    chain = critical_path(g, "ts-gateway-service", "latency", target="ts-train-service")
    path = [c.name for c in chain]
    assert path[0] == "ts-gateway-service"
    assert path[-1] == "ts-train-service"


def test_unknown_entrypoint_raises(g):
    with pytest.raises(ValueError):
        critical_path(g, "nope", "latency")


def test_unreachable_target_raises(g):
    with pytest.raises(ValueError):
        critical_path(g, "ts-train-service", "latency", target="ts-gateway-service")


def test_rejects_non_dag():
    bad = nx.DiGraph()
    bad.add_node("a", component=Component(name="a", slo=SloValues(response_time_ms=1)))
    bad.add_node("b", component=Component(name="b", slo=SloValues(response_time_ms=1)))
    bad.add_edge("a", "b")
    bad.add_edge("b", "a")
    with pytest.raises(ValueError):
        critical_path(bad, "a", "latency")
