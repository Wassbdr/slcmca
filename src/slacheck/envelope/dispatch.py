"""Version dispatch between the paper-v1 and paper-v2 engines (pure).

Keeps the v1 ``evaluate`` path byte-for-byte unchanged; routes to ``evaluate_v2`` when
``paper_version == "v2"``. Callers pass either a v1 series ``path`` or a v2 ``graph``.
"""

from __future__ import annotations

from collections.abc import Sequence

from slacheck.envelope.faults import evaluate
from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
from slacheck.models import (
    Component,
    DependencyGraph,
    KnowledgeBase,
    PaperVersion,
    ReconfigStrategy,
    SloValues,
    Verdict,
)


def evaluate_versioned(
    *,
    paper_version: PaperVersion,
    path: Sequence[Component] | None = None,
    graph: DependencyGraph | None = None,
    target: SloValues | None = None,
    kb: KnowledgeBase | None = None,
    strategies: Sequence[ReconfigStrategy] | None = None,
    target_slos: Sequence[str] | None = None,
) -> Verdict:
    if paper_version == "v1":
        if path is None:
            raise ValueError("paper_version v1 requires a series `path`")
        return evaluate(path, target)
    if graph is None:
        raise ValueError("paper_version v2 requires a `graph`")
    return evaluate_v2(graph, target, kb, strategies, target_slos)
