"""Orchestrator: source -> graph -> critical path -> envelope -> Verdict.

Wires the layers together so the CLI and the dashboard builder share one code path.
Lives outside ``envelope/`` because it touches the Datadog adapter; ``envelope/`` stays pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from slacheck.datadog.source import DatadogSource
from slacheck.envelope.faults import evaluate
from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
from slacheck.graph.builder import build_graph
from slacheck.graph.critical_path import critical_path
from slacheck.graph.typed_graph import project_to_dependency_graph
from slacheck.models import (
    Component,
    Constraint,
    KnowledgeBase,
    PaperVersion,
    Pricing,
    ReconfigStrategy,
    SloValues,
    Verdict,
)


@dataclass
class AnalysisResult:
    """Everything a caller (CLI / dashboard) needs to render an analysis."""

    entrypoint: str
    constraint: Constraint
    path: list[Component]
    verdict: Verdict
    dropped_edges: list[tuple[str, str]]
    paper_version: PaperVersion = "v1"


def analyze(
    source: DatadogSource,
    entrypoint: str,
    constraint: Constraint,
    target: SloValues | None = None,
    sink: str | None = None,
    paper_version: PaperVersion = "v1",
    edge_overrides: dict | None = None,
    kb: KnowledgeBase | None = None,
    strategies: list[ReconfigStrategy] | None = None,
    target_slos: list[str] | None = None,
    pricing: Pricing | None = None,
    service_filter: dict | None = None,
) -> AnalysisResult:
    """Run the full pipeline against a Datadog source (live or fixture).

    paper_version "v1": reduce the DAG to a critical series path, then evaluate (default).
    paper_version "v2": aggregate over the whole typed DAG (margins, weighted decomposition,
    reconfiguration faults). ``pricing`` enables the k8s resource-based cost estimate.
    ``service_filter`` restricts a live cluster-wide topology to the app under study.
    """
    graph, dropped = build_graph(
        source, entrypoint=entrypoint, pricing=pricing, service_filter=service_filter
    )

    if paper_version == "v1":
        path = critical_path(graph, entrypoint, constraint, target=sink)
        verdict = evaluate(path, target)
    else:
        dep_graph = project_to_dependency_graph(graph, entrypoint, edge_overrides)
        verdict = evaluate_v2(dep_graph, target, kb, strategies, target_slos)
        path = [dep_graph.components[n] for n in verdict.envelope.path]

    if dropped:
        verdict.notes.append(
            "Topology cycles were broken to a DAG; dropped back-edges: "
            + ", ".join(f"{u}->{v}" for u, v in dropped)
            + "."
        )
    return AnalysisResult(
        entrypoint=entrypoint,
        constraint=constraint,
        path=path,
        verdict=verdict,
        dropped_edges=dropped,
        paper_version=paper_version,
    )
