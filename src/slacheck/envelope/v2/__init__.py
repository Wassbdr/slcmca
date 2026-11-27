"""Paper-v2 envelope engine: typed-DAG aggregation, safety margins, weighted decomposition,
reconfiguration faults. Pure: imports only ``slacheck.models`` and stdlib (no networkx/Datadog)."""

from slacheck.envelope.v2.aggregate_v2 import compute_commit_envelope_v2, compute_envelope_v2
from slacheck.envelope.v2.decompose_v2 import decompose_v2, structural_weights
from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
from slacheck.envelope.v2.margins import adjust_slo, gamma
from slacheck.envelope.v2.operators_v2 import (
    agg_availability_conjunctive,
    agg_availability_disjunctive,
    agg_cost_v2,
    agg_latency_conjunctive_paths,
    agg_latency_disjunctive,
)
from slacheck.envelope.v2.reconfig import detect_reconfig_faults, translate_slo

__all__ = [
    "adjust_slo",
    "agg_availability_conjunctive",
    "agg_availability_disjunctive",
    "agg_cost_v2",
    "agg_latency_conjunctive_paths",
    "agg_latency_disjunctive",
    "compute_commit_envelope_v2",
    "compute_envelope_v2",
    "decompose_v2",
    "detect_reconfig_faults",
    "evaluate_v2",
    "gamma",
    "structural_weights",
    "translate_slo",
]
