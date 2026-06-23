"""Ascending aggregation: a series path of components → the guaranteeable Envelope (paper §IV.B)."""

from __future__ import annotations

from collections.abc import Sequence

from slacheck.envelope.operators import agg_availability, agg_cost, agg_response_time
from slacheck.models import Component, Envelope


def compute_envelope(path: Sequence[Component]) -> Envelope:
    """Aggregate the Sub-SLOs along a series ``path`` into the achievable global envelope.

    Each metric is aggregated only over the components that actually report it, so a
    missing ``cost_eur_h`` (the common Datadog case) yields ``cost_eur_h = None`` rather
    than a fabricated number.
    """
    if not path:
        raise ValueError("compute_envelope requires a non-empty path")

    latencies = [c.slo.response_time_ms for c in path if c.slo.response_time_ms is not None]
    avails = [c.slo.availability_pct for c in path if c.slo.availability_pct is not None]
    costs = [c.slo.cost_eur_h for c in path if c.slo.cost_eur_h is not None]

    return Envelope(
        response_time_ms=agg_response_time(latencies) if latencies else None,
        availability_pct=agg_availability(avails) if avails else None,
        cost_eur_h=agg_cost(costs) if costs else None,
        path=[c.name for c in path],
    )
