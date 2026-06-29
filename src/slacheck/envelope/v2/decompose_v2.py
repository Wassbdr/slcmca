"""Structural-weight decomposition (paper-v2 §IV.D).

Instead of the uniform 1/n split (paper-v1), the global target is apportioned by each
component's structural centrality: wᵢ = (1 + deg⁻(i)) / Σⱼ(1 + deg⁻(j)), where deg⁻ is the
in-degree. A component depended on by many others carries a larger share. This closes the
3 Sub-SLO faults that uniform distribution misses (paper §VI).
"""

from __future__ import annotations

from slacheck.models import DependencyGraph, SloValues, Threshold


def structural_weights(graph: DependencyGraph) -> dict[str, float]:
    """wᵢ = (1 + deg⁻(i)) / Σⱼ(1 + deg⁻(j))."""
    raw = {name: 1 + graph.indegree(name) for name in graph.components}
    total = sum(raw.values())
    if total == 0:
        raise ValueError("structural_weights requires a non-empty graph")
    return {name: r / total for name, r in raw.items()}


def decompose_v2(target: SloValues, graph: DependencyGraph) -> list[Threshold]:
    """Apportion ``target`` across components by structural weight.

    - cumulative metrics (cost): sᵢ = wᵢ · T.
    - availability: sᵢ = 100 − wᵢ · (100 − T) (weighted error-budget split).
    - latency: MaxType → each component must individually meet the global bound (not split).
    """
    weights = structural_weights(graph)
    thresholds: list[Threshold] = []
    for name, w in weights.items():
        per_cost = target.cost_eur_h * w if target.cost_eur_h is not None else None
        per_avail = (
            100.0 - w * (100.0 - target.availability_pct)
            if target.availability_pct is not None
            else None
        )
        thresholds.append(
            Threshold(
                component=name,
                required=SloValues(
                    response_time_ms=target.response_time_ms,
                    availability_pct=per_avail,
                    cost_eur_h=per_cost,
                ),
            )
        )
    return thresholds
