"""The paper's three aggregation operators (§III-B). Correctness anchor.

These encode the publication exactly and are the non-regression contract:
    agg_availability([99.9, 99.9, 99.9]) == 99.7   (paper §IV)

Do NOT change these without updating tests/test_operators.py.
All operators assume a *series* path (one value per component on the path).
"""

from __future__ import annotations

from collections.abc import Sequence


def agg_response_time(values: Sequence[float]) -> float:
    """MaxType: end-to-end latency is dominated by the slowest component → max(vᵢ)."""
    if not values:
        raise ValueError("agg_response_time requires at least one value")
    return max(values)


def agg_cost(values: Sequence[float]) -> float:
    """SumType: financial cost accumulates → Σ vᵢ."""
    return sum(values)


def agg_availability(values: Sequence[float]) -> float:
    """Error-budget composition: availability cannot be averaged.

    Global error budget = sum of local error budgets, so
        global_availability = 100 − Σ(100 − vᵢ).
    """
    if not values:
        raise ValueError("agg_availability requires at least one value")
    return 100.0 - sum(100.0 - v for v in values)
