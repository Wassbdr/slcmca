"""Descending decomposition: a target Global-SLO → per-component thresholds (paper §III-C).

LIMITATION (paper §V, ablated baseline): this apportions global budgets *uniformly* across the n
components — cost/n, and the global error budget split equally. Real systems are not
uniform (a DB consumes more budget than a stateless auth service), which is exactly the
source of the paper's 3 missed Sub-SLO faults. The ascending envelope (aggregate.py) is
the primary, exact result; this descending view is advisory.
"""

from __future__ import annotations

from slacheck.models import SloValues, Threshold


def decompose(global_slo: SloValues, components: list[str]) -> list[Threshold]:
    """Split ``global_slo`` evenly across ``components``.

    - response_time: MaxType means every component must individually be within the global
      latency, so the per-component requirement is the same global value (not divided).
    - cost: SumType → global_cost / n.
    - availability: split the global error budget equally → each component must reach
      100 − (global_error_budget / n).
    """
    n = len(components)
    if n == 0:
        raise ValueError("decompose requires at least one component")

    per_cost = global_slo.cost_eur_h / n if global_slo.cost_eur_h is not None else None

    per_avail: float | None = None
    if global_slo.availability_pct is not None:
        global_budget = 100.0 - global_slo.availability_pct
        per_avail = 100.0 - (global_budget / n)

    return [
        Threshold(
            component=name,
            required=SloValues(
                response_time_ms=global_slo.response_time_ms,
                availability_pct=per_avail,
                cost_eur_h=per_cost,
            ),
        )
        for name in components
    ]
