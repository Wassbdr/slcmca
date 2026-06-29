"""Build an nx.DiGraph topology from Datadog deps + metrics, then make it a DAG.

The Service Map often contains cycles (retries, shared utilities). The paper's
operators and the longest-path critical-path extraction both require a DAG, so we break
cycles deterministically by dropping the lowest-request-volume back-edge. Dropped edges
are recorded so the verdict can disclose them (honesty over silent mutation).
"""

from __future__ import annotations

import networkx as nx

from slacheck.datadog.metrics import (
    collect_k8s_metrics,
    collect_with_samples,
    k8s_availability_proxy,
)
from slacheck.datadog.source import DatadogSource
from slacheck.datadog.topology import parse_edges, parse_services
from slacheck.models import Component, ResourceMetrics, SloValues


def build_graph(
    source: DatadogSource, entrypoint: str | None = None
) -> tuple[nx.DiGraph, list[tuple[str, str]]]:
    """Assemble the topology graph. Returns ``(dag, dropped_edges)``.

    Each node carries a ``component`` attribute (a :class:`Component` with measured SLOs).
    If ``entrypoint`` is given, cycles are broken from its perspective (back-edges first),
    which preserves forward reachability from the entrypoint.
    """
    deps = source.service_dependencies()
    edges = parse_edges(deps)
    services = parse_services(deps)
    slo_by_service = collect_with_samples(source)
    k8s_by_service = collect_k8s_metrics(source)
    avail_proxy = k8s_availability_proxy(source)

    g = nx.DiGraph()
    for name in sorted(services):
        slo, sample = slo_by_service.get(name, (SloValues(), {}))
        # fall back to the k8s readiness proxy only when APM gives no availability
        if slo.availability_pct is None and name in avail_proxy:
            slo = slo.model_copy(update={"availability_pct": avail_proxy[name]})
            sample = {**sample, "availability_source": "k8s_readiness_proxy"}
        resources = k8s_by_service.get(name, ResourceMetrics())
        g.add_node(
            name,
            component=Component(name=name, slo=slo, resources=resources, sample=sample),
        )
    g.add_edges_from(edges)

    dropped = _break_cycles(g, entrypoint)
    return g, dropped


def _break_cycles(g: nx.DiGraph, entrypoint: str | None) -> list[tuple[str, str]]:
    """Make ``g`` a DAG by removing back-edges, preferring those rooted at ``entrypoint``.

    A back-edge points to a node already on the current DFS stack — removing it breaks the
    cycle without severing any *forward* path. Rooting the DFS at the entrypoint guarantees
    the service we actually care about keeps all its downstream reachability. Edges are
    visited in descending request-volume order so the lowest-volume back-edge is the one
    dropped, matching the heuristic in docs (least-trafficked call is the safest to cut).
    """
    dropped: list[tuple[str, str]] = []
    roots: list[str] = [entrypoint] if entrypoint is not None and entrypoint in g else []
    # also cover any nodes not reachable from the entrypoint, for completeness
    roots += [n for n in g if n not in roots]

    while not nx.is_directed_acyclic_graph(g):
        removed = _remove_one_back_edge(g, roots)
        if removed is None:  # safety net; should not happen
            cycle = next(iter(nx.simple_cycles(g)))
            removed = (cycle[-1], cycle[0])
            g.remove_edge(*removed)
        dropped.append(removed)
    return dropped


def _remove_one_back_edge(
    g: nx.DiGraph, roots: list[str]
) -> tuple[str, str] | None:
    """DFS from roots; remove the lowest-volume back-edge found. Returns it, or None."""
    color: dict[str, int] = {}  # 0=unseen, 1=on-stack, 2=done

    def volume(u: str, v: str) -> float:
        cu = g.nodes[u]["component"].sample.get("request_count") or 0.0
        cv = g.nodes[v]["component"].sample.get("request_count") or 0.0
        return min(cu, cv)

    back_edges: list[tuple[str, str]] = []

    def dfs(node: str) -> None:
        color[node] = 1
        for succ in g.successors(node):
            if color.get(succ, 0) == 1:
                back_edges.append((node, succ))
            elif color.get(succ, 0) == 0:
                dfs(succ)
        color[node] = 2

    for root in roots:
        if color.get(root, 0) == 0:
            dfs(root)

    if not back_edges:
        return None
    edge = min(back_edges, key=lambda e: volume(*e))
    g.remove_edge(*edge)
    return edge
