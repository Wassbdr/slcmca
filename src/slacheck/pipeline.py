"""Orchestrator: source -> graph -> critical path -> envelope -> Verdict.

Wires the layers together so the CLI and the dashboard builder share one code path.
Lives outside ``envelope/`` because it touches the Datadog adapter; ``envelope/`` stays pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from slacheck.datadog.source import DatadogSource
from slacheck.envelope.faults import evaluate
from slacheck.graph.builder import build_graph
from slacheck.graph.critical_path import critical_path
from slacheck.models import Component, Constraint, SloValues, Verdict


@dataclass
class AnalysisResult:
    """Everything a caller (CLI / dashboard) needs to render an analysis."""

    entrypoint: str
    constraint: Constraint
    path: list[Component]
    verdict: Verdict
    dropped_edges: list[tuple[str, str]]


def analyze(
    source: DatadogSource,
    entrypoint: str,
    constraint: Constraint,
    target: SloValues | None = None,
    sink: str | None = None,
) -> AnalysisResult:
    """Run the full pipeline against a Datadog source (live or fixture)."""
    graph, dropped = build_graph(source, entrypoint=entrypoint)
    path = critical_path(graph, entrypoint, constraint, target=sink)
    verdict = evaluate(path, target)
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
    )
