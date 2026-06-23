"""Pure SLA aggregation math (paper §IV). MUST NOT import from slacheck.datadog."""

from slacheck.envelope.aggregate import compute_envelope
from slacheck.envelope.decompose import decompose
from slacheck.envelope.faults import detect_ascending, detect_descending, evaluate
from slacheck.envelope.operators import agg_availability, agg_cost, agg_response_time

__all__ = [
    "agg_availability",
    "agg_cost",
    "agg_response_time",
    "compute_envelope",
    "decompose",
    "detect_ascending",
    "detect_descending",
    "evaluate",
]
