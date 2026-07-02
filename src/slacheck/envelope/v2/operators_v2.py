"""Topology-sensitive aggregation operators (paper §III-B).

The operator applied to a metric depends on the dependency type τ(e) of the fan-in:
- cost is τ-independent (everything provisioned incurs charges);
- conjunctive availability degrades the error budget (= paper-v1);
- disjunctive availability composes as a redundancy product (NEW — redundancy improves it);
- conjunctive latency takes the worst root-to-leaf path; disjunctive takes the responding branch.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def agg_cost_v2(values: Sequence[float]) -> float:
    """A*_cost = Σ vᵢ over all components, regardless of τ."""
    return sum(values)


def _check_availability(values: Sequence[float]) -> None:
    """Reject physically-impossible availabilities (> 100). Values < 0 are allowed because
    composition legitimately yields negative *intermediates* for an over-committed chain
    (the error budget exceeds 100% — i.e. structurally impossible). Leaf SLO values are
    range-validated upstream at ingestion; this guards only against absurd inputs."""
    for v in values:
        if v > 100.0:
            raise ValueError(f"availability cannot exceed 100, got {v}")


def agg_availability_conjunctive(values: Sequence[float]) -> float:
    """Conjunctive: 100 − Σ(100 − vᵢ). Identical to paper-v1 error-budget composition.

    May return a negative value when the composed error budget exceeds 100% — a valid
    "structurally impossible" signal for a deeply over-committed chain."""
    if not values:
        raise ValueError("agg_availability_conjunctive requires at least one value")
    _check_availability(values)
    return 100.0 - sum(100.0 - v for v in values)


def agg_availability_disjunctive(values: Sequence[float]) -> float:
    """Disjunctive: 100 − Π((100 − vᵢ)/100). The system is up if at least one provider is up,
    so combined unavailability is the product of individual unavailabilities."""
    if not values:
        raise ValueError("agg_availability_disjunctive requires at least one value")
    _check_availability(values)
    unavail_product = math.prod((100.0 - v) / 100.0 for v in values)
    return 100.0 - unavail_product * 100.0


def agg_latency_conjunctive_paths(path_sums: Sequence[float]) -> float:
    """A*_lat = max over root-to-leaf paths of Σ vᵢ. Input: the latency sum of each path."""
    if not path_sums:
        raise ValueError("agg_latency_conjunctive_paths requires at least one path")
    return max(path_sums)


def agg_latency_disjunctive(branch_values: Sequence[float]) -> float:
    """Disjunctive latency: only the responding (fastest) branch contributes → min."""
    if not branch_values:
        raise ValueError("agg_latency_disjunctive requires at least one branch")
    return min(branch_values)
