"""Real-world case study (train-ticket): lock the v1-vs-v2 numbers used in the paper.

Drives the full pipeline on the declared train-ticket topology (38 services, fixture metrics)
and asserts the figures the paper's "Real-World Case Study" section reports. These are produced
by scripts/case_study.py; this test is the regression contract for them.

It exercises ONLY the public pipeline (analyze + get_source); it does not touch v1 internals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slacheck.datadog.source import get_source
from slacheck.models import SloValues
from slacheck.pipeline import analyze

REPO = Path(__file__).resolve().parents[1]
TOPOLOGY = REPO / "fixtures" / "topology" / "train-ticket.yaml"


def _run(version, constraint, target):
    src = get_source("declared", topology=TOPOLOGY, metrics_from="fixture")
    return analyze(src, "ts-ui-dashboard", constraint, target=target, paper_version=version)


def _descending(result) -> set[str]:
    return {
        f.component for f in result.verdict.faults if f.direction == "descending" and f.component
    }


# --- availability case: v2 (full DAG) catches high-centrality hubs off v1's critical path ----


def test_v1_availability_envelope_and_faults():
    r = _run("v1", "availability", SloValues(availability_pct=99.9))
    assert r.verdict.envelope.availability_pct == pytest.approx(99.40, abs=0.01)
    assert len(r.verdict.faults) == 3
    assert _descending(r) == {"ts-route-service", "ts-travel-service"}


def test_v2_availability_envelope_and_faults():
    r = _run("v2", "availability", SloValues(availability_pct=99.9))
    assert r.verdict.envelope.availability_pct == pytest.approx(98.36, abs=0.01)
    assert len(r.verdict.faults) == 6
    assert _descending(r) == {
        "ts-order-service",
        "ts-route-service",
        "ts-station-service",
        "ts-train-service",
        "ts-travel-service",
    }


def test_v2_recovers_three_hubs_v1_misses():
    """The headline: v2 flags exactly the 3 central hubs that lie off v1's single critical path."""
    v1 = _run("v1", "availability", SloValues(availability_pct=99.9))
    v2 = _run("v2", "availability", SloValues(availability_pct=99.9))
    assert _descending(v2) - _descending(v1) == {
        "ts-order-service",
        "ts-station-service",
        "ts-train-service",
    }
    # Check the direction of the change independently of the exact counts.
    assert len(v2.verdict.faults) > len(v1.verdict.faults)


# --- latency case: v1 reports FEASIBLE on a system that is actually over-committed -------------


def test_latency_false_negative():
    """At 30 ms, v1 (critical path) says feasible while v2 (full DAG) raises an ascending fault."""
    v1 = _run("v1", "latency", SloValues(response_time_ms=30.0))
    v2 = _run("v2", "latency", SloValues(response_time_ms=30.0))
    # v1: 24 ms on its 3-node path → no fault
    assert v1.verdict.feasible is True
    assert len(v1.verdict.faults) == 0
    # v2: 48 ms end-to-end over the whole DAG → exactly one ascending latency fault
    assert v2.verdict.feasible is False
    ascending_lat = [
        f
        for f in v2.verdict.faults
        if f.direction == "ascending" and f.metric == "response_time"
    ]
    assert len(ascending_lat) == 1


# --- the real topology has cycles (the toy example does not) -----------------------------------


def test_real_topology_has_a_broken_cycle():
    r = _run("v2", "availability", SloValues(availability_pct=99.9))
    assert r.dropped_edges  # non-empty: a real microservice graph is not a clean DAG
    assert ("ts-seat-service", "ts-travel-service") in r.dropped_edges


# --- second real system: Online Boutique (call graph from the official GCP k8s manifest) -------

OB_TOPOLOGY = REPO / "fixtures" / "topology" / "real" / "online-boutique.yaml"


def _online_boutique_graph():
    """Build the Online Boutique typed DAG with a uniform nominal 99.9% Sub-SLO per service."""
    import yaml

    from slacheck.models import Component, DependencyEdge, DependencyGraph
    from slacheck.models import SloValues as SV

    deps = yaml.safe_load(OB_TOPOLOGY.read_text())["dependencies"]
    names = list(deps)
    edges = [
        DependencyEdge(source=u, target=v, edge_type="conjunctive")
        for u, vs in deps.items()
        for v in vs
    ]
    comps = {n: Component(name=n, slo=SV(availability_pct=99.9)) for n in names}
    return DependencyGraph(components=comps, edges=edges, entrypoint="frontend")


def test_online_boutique_is_valid_and_acyclic():
    g = _online_boutique_graph()
    assert len(g.components) == 10
    assert sum(len(g.successors(n)) for n in g.components) == 14  # edges from the manifest


def test_online_boutique_productcatalog_is_most_central():
    """productcatalogservice is called by frontend, checkout and recommendation (in-degree 3)."""
    from slacheck.envelope.v2.decompose_v2 import structural_weights

    g = _online_boutique_graph()
    w = structural_weights(g)
    assert max(w, key=w.get) == "productcatalogservice"
    assert g.indegree("productcatalogservice") == 3


def test_online_boutique_envelope_below_target():
    """10 conjunctive services at 99.9% compose to an envelope under a 99.9% Global-SLO."""
    from slacheck.envelope.v2.aggregate_v2 import compute_envelope_v2

    env = compute_envelope_v2(_online_boutique_graph())
    assert env.availability_pct == pytest.approx(98.5, abs=0.01)
    assert env.availability_pct < 99.9  # the architect target is structurally unachievable
