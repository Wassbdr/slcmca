"""Reduce the branching DAG to ONE series path that answers a user's SLA constraint.

This is the move that makes the paper's series-only operators legitimately applicable
to a real topology (the prior-practice baseline of paper §V). We find the heaviest path
from the entrypoint:

- constraint="latency": node weight = p99 latency. The max-weight path is the bottleneck
  chain that dominates achievable end-to-end latency under MaxType.
- constraint="availability": node weight = error budget (100 - availability). The
  max-total-budget path is exactly the worst achievable-availability path under
  error-budget composition.

Ties are broken toward the higher-request-volume (hottest) successor.
"""

from __future__ import annotations

import networkx as nx

from slacheck.models import Component, Constraint


def _node_weight(comp: Component, constraint: Constraint) -> float:
    slo = comp.slo
    if constraint == "latency":
        return slo.response_time_ms or 0.0
    # availability: weight by error budget; unknown availability contributes 0 budget
    if slo.availability_pct is None:
        return 0.0
    return 100.0 - slo.availability_pct


def _volume(comp: Component) -> float:
    return comp.sample.get("request_count") or 0.0


def critical_path(
    g: nx.DiGraph,
    entrypoint: str,
    constraint: Constraint,
    target: str | None = None,
) -> list[Component]:
    """Return the ordered list of components on the critical series path.

    The result is the series ``S`` consumed directly by ``envelope.compute_envelope``.
    """
    if entrypoint not in g:
        raise ValueError(f"entrypoint {entrypoint!r} not in graph")
    if not nx.is_directed_acyclic_graph(g):
        raise ValueError("critical_path requires a DAG (build_graph breaks cycles first)")

    order = list(nx.topological_sort(g))
    weight = {n: _node_weight(g.nodes[n]["component"], constraint) for n in g}

    # Longest-path DP over the DAG, starting only from the entrypoint.
    best: dict[str, float] = {}
    pred: dict[str, str | None] = {}
    for n in order:
        if n == entrypoint:
            best[n] = weight[n]
            pred[n] = None
        elif n in best:
            pass  # reachable, already relaxed by a predecessor below
        # relax successors
        if n in best:
            for succ in g.successors(n):
                cand = best[n] + weight[succ]
                # tie-break toward the hotter successor path
                if (
                    succ not in best
                    or cand > best[succ]
                    or (cand == best[succ] and _volume(g.nodes[succ]["component"]) > _volume(
                        g.nodes[pred.get(succ, succ) or succ]["component"]
                    ))
                ):
                    best[succ] = cand
                    pred[succ] = n

    # choose the end node: explicit target, else the reachable node with max best-weight
    if target is not None:
        if target not in best:
            raise ValueError(f"target {target!r} not reachable from {entrypoint!r}")
        end = target
    else:
        end = max(best, key=lambda n: (best[n], _volume(g.nodes[n]["component"])))

    # reconstruct path
    chain: list[str] = []
    cur: str | None = end
    while cur is not None:
        chain.append(cur)
        cur = pred[cur]
    chain.reverse()
    return [g.nodes[n]["component"] for n in chain]
