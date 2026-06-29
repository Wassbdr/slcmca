"""Paper-v2 entry point: typed-DAG envelope + margins + weighted decomposition + reconfig.

Chains the v2 pieces and reuses the v1 fault detectors (``detect_ascending`` /
``detect_descending`` are version-agnostic — they operate on Envelope/Threshold/Component).
Crucially, the ascending check compares the target against the margin-adjusted A_commit,
not the raw theoretical envelope A*.
"""

from __future__ import annotations

from collections.abc import Sequence

from slacheck.envelope.faults import detect_ascending, detect_descending
from slacheck.envelope.v2.aggregate_v2 import compute_commit_envelope_v2, compute_envelope_v2
from slacheck.envelope.v2.decompose_v2 import decompose_v2, structural_weights
from slacheck.envelope.v2.reconfig import detect_reconfig_faults
from slacheck.models import (
    DependencyGraph,
    KnowledgeBase,
    ReconfigStrategy,
    SloValues,
    Verdict,
)


def evaluate_v2(
    graph: DependencyGraph,
    target: SloValues | None = None,
    kb: KnowledgeBase | None = None,
    strategies: Sequence[ReconfigStrategy] | None = None,
    target_slos: Sequence[str] | None = None,
) -> Verdict:
    """Full paper-v2 evaluation over a typed dependency graph.

    With no ``target``, reports the achievable envelope A* and the safely-committable
    A_commit. With a ``target``, also flags ascending (vs A_commit), descending (weighted
    thresholds), and reconfiguration faults.
    """
    envelope = compute_envelope_v2(graph)
    commit = compute_commit_envelope_v2(graph, kb)
    weights = structural_weights(graph)
    components = list(graph.components.values())

    notes: list[str] = [
        "Envelope aggregated over the full typed DAG in topological order (paper-v2 §IV.C); "
        "disjunctive groups compose as redundancy products.",
    ]
    if envelope.cost_eur_h is None:
        notes.append(
            "Cost data unavailable from Datadog; supply cost_overrides.yaml to enable the cost SLO."
        )

    faults = []
    thresholds = []
    if target is not None:
        # Ascending fault is judged against the margin-adjusted A_commit, not A*.
        faults += detect_ascending(target, commit)
        # Descending decomposes the RAW target T, per paper-v2 §IV.D: "the descending
        # validation takes the target Global-SLO T fixed by the architect as input … both
        # operate on the same input data". The two passes are deliberately independent.
        thresholds = decompose_v2(target, graph)
        faults += detect_descending(components, thresholds)

    if strategies and kb is not None:
        faults += detect_reconfig_faults(strategies, kb, target_slos or [])

    return Verdict(
        envelope=envelope,
        commit_envelope=commit,
        weights=weights,
        thresholds=thresholds,
        faults=faults,
        notes=notes,
        paper_version="v2",
    )
