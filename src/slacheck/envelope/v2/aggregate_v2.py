"""Topological aggregation over the typed DAG → the guaranteeable envelope (paper-v2 §IV.C).

Unlike paper-v1 (which reduces the DAG to one series path), v2 aggregates over the WHOLE
graph following its topological order, selecting the operator per metric and per the
dependency type τ of each fan-in group:

- cost: sum over all nodes (τ-independent).
- latency: max over all root-to-leaf path sums (conjunctive); disjunctive siblings take
  the responding (min) branch.
- availability: propagated bottom-up; each node combines its own value with the
  aggregation of its providers' propagated availabilities, conjunctive (Σ error budget)
  or disjunctive (Π unavailability) per ``edge_type_into``.
"""

from __future__ import annotations

from slacheck.envelope.v2.margins import adjust_slo
from slacheck.envelope.v2.operators_v2 import (
    agg_availability_conjunctive,
    agg_availability_disjunctive,
    agg_cost_v2,
    agg_latency_conjunctive_paths,
    agg_latency_disjunctive,
)
from slacheck.models import (
    Component,
    DependencyEdge,
    DependencyGraph,
    Envelope,
    KnowledgeBase,
)


def _propagated_availability(graph: DependencyGraph) -> float | None:
    """Availability at the entrypoint, composing providers bottom-up by fan-in type.

    A node's effective availability is its own SLO combined (conjunctively) with the
    aggregation of its children's effective availabilities. The children of a node form a
    fan-out group whose type is the type of the edges into them as seen from this node;
    we read it from the edge_type of each (node → child) edge.
    """
    order = graph.topological_order()
    eff: dict[str, float | None] = {}

    # process leaves first → reverse topological order
    for node in reversed(order):
        own = graph.components[node].slo.availability_pct
        children = graph.successors(node)
        if not children:
            eff[node] = own
            continue

        # group children by the type of the (node -> child) edge
        conj_vals: list[float] = []
        disj_vals: list[float] = []
        for child in children:
            etype = _edge_type(graph.edges, node, child)
            child_eff = eff.get(child)
            if child_eff is None:
                continue
            (disj_vals if etype == "disjunctive" else conj_vals).append(child_eff)

        # combine the disjunctive group into a single redundancy value, then treat the
        # disjunctive result + the conjunctive children + own as a conjunctive chain.
        chain: list[float] = []
        if own is not None:
            chain.append(own)
        chain.extend(conj_vals)
        if disj_vals:
            chain.append(agg_availability_disjunctive(disj_vals))

        eff[node] = agg_availability_conjunctive(chain) if chain else None

    return eff.get(graph.entrypoint)


def _edge_type(edges: list[DependencyEdge], source: str, target: str) -> str:
    for e in edges:
        if e.source == source and e.target == target:
            return e.edge_type
    return "conjunctive"


def _path_latency(graph: DependencyGraph) -> float | None:
    """Max over root-to-leaf path latency sums; disjunctive sibling branches take the min."""
    latencies = {
        n: c.slo.response_time_ms for n, c in graph.components.items()
    }
    if all(v is None for v in latencies.values()):
        return None

    # Sum latency along each enumerated root-to-leaf path (skipping None contributions).
    path_sums: list[float] = []
    for path in graph.root_to_leaf_paths():
        path_sums.append(sum(latencies[n] or 0.0 for n in path))

    # Disjunctive fan-outs: among sibling branches sharing a disjunctive parent edge, only
    # the responding branch counts → for those we keep the min, otherwise the max overall.
    # We approximate the mixed case by: max over conjunctive-dominated paths, but if a
    # parent has ALL-disjunctive children, those branches compete (min). Detect such groups.
    disj_mins = _disjunctive_branch_mins(graph, latencies)
    candidates = path_sums + disj_mins
    return agg_latency_conjunctive_paths(candidates) if candidates else None


def _disjunctive_branch_mins(
    graph: DependencyGraph, latencies: dict[str, float | None]
) -> list[float]:
    """For each node whose children are disjunctive, the group contributes min branch."""
    mins: list[float] = []
    for node in graph.components:
        children = graph.successors(node)
        if len(children) < 2:
            continue
        types = {_edge_type(graph.edges, node, c) for c in children}
        if types == {"disjunctive"}:
            branch_vals = [latencies[c] or 0.0 for c in children]
            prefix = latencies[node] or 0.0
            mins.append(prefix + agg_latency_disjunctive(branch_vals))
    return mins


def compute_envelope_v2(graph: DependencyGraph) -> Envelope:
    """Aggregate the typed DAG into the achievable global envelope A* (paper-v2 §IV.C)."""
    if not graph.components:
        raise ValueError("compute_envelope_v2 requires a non-empty graph")

    costs = [c.slo.cost_eur_h for c in graph.components.values() if c.slo.cost_eur_h is not None]

    return Envelope(
        response_time_ms=_path_latency(graph),
        availability_pct=_propagated_availability(graph),
        cost_eur_h=agg_cost_v2(costs) if costs else None,
        path=graph.topological_order(),
    )


def compute_commit_envelope_v2(graph: DependencyGraph, kb: KnowledgeBase | None) -> Envelope:
    """A_commit: the envelope computed from margin-adjusted Sub-SLOs ṽᵢ = vᵢ − γᵢ."""
    if kb is None:
        return compute_envelope_v2(graph)

    adjusted = {
        name: Component(
            name=comp.name,
            csp=comp.csp,
            slo=adjust_slo(comp.slo, comp.csp_profile, kb.margin_config),
            resources=comp.resources,
            csp_profile=comp.csp_profile,
            sample=comp.sample,
        )
        for name, comp in graph.components.items()
    }
    adjusted_graph = DependencyGraph(
        components=adjusted, edges=graph.edges, entrypoint=graph.entrypoint
    )
    return compute_envelope_v2(adjusted_graph)
