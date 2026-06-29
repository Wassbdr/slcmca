"""Project the impure nx.DiGraph into the pure typed DependencyGraph (paper-v2).

Datadog APM call edges carry no AND/OR semantics, so every edge defaults to
**conjunctive** (a caller fanning out to N callees needs all of them — the common
micro-service reality). Redundant provider groups are marked disjunctive via an optional
``edge_overrides`` mapping (see fixtures/scenarios/edge_overrides.example.yaml), mirroring
the cost_overrides pattern.
"""

from __future__ import annotations

import networkx as nx

from slacheck.models import Component, DependencyEdge, DependencyGraph, EdgeType


def project_to_dependency_graph(
    g: nx.DiGraph, entrypoint: str, edge_overrides: dict | None = None
) -> DependencyGraph:
    """Convert ``g`` (nodes carry a ``component`` attr) into a pure DependencyGraph.

    ``edge_overrides`` shape::

        disjunctive_groups:
          - { parent: <svc>, children: [<svc>, <svc>] }   # mark these edges disjunctive
        edge_types:
          - { source: <svc>, target: <svc>, edge_type: conjunctive|disjunctive }
    """
    overrides = edge_overrides or {}
    disjunctive: set[tuple[str, str]] = set()
    for grp in overrides.get("disjunctive_groups", []) or []:
        parent = grp["parent"]
        for child in grp.get("children", []):
            disjunctive.add((parent, child))
    explicit: dict[tuple[str, str], EdgeType] = {
        (e["source"], e["target"]): e["edge_type"]
        for e in overrides.get("edge_types", []) or []
    }

    components: dict[str, Component] = {
        n: g.nodes[n]["component"] for n in g.nodes
    }
    edges: list[DependencyEdge] = []
    for u, v in g.edges:
        etype: EdgeType = explicit.get(
            (u, v), "disjunctive" if (u, v) in disjunctive else "conjunctive"
        )
        edges.append(DependencyEdge(source=u, target=v, edge_type=etype))

    return DependencyGraph(components=components, edges=edges, entrypoint=entrypoint)


def infer_edge_types_from_traces(*_args, **_kwargs) -> dict:
    """Future hook: derive disjunctive groups from APM trace spans (retry/failover/replica
    siblings) once trace ingestion is available. Returns an edge_overrides-shaped dict.

    Not implemented — APM trace ingestion is currently blocked org-side (see
    docs/datadog_api_catalog.md "Live findings"). Use explicit edge_overrides meanwhile.
    """
    raise NotImplementedError(
        "trace-based edge-type inference pending APM ingestion; use edge_overrides.yaml"
    )
