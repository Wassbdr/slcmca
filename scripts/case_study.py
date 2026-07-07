"""Real-world case study: slacheck on the train-ticket microservice benchmark.

Runs the full pipeline on the declared train-ticket topology (38 services, real documented
call graph) with fixture metrics, under two architect Global-SLOs, and reports how the
uniform-decomposition / critical-path baseline (v1) compares to the full typed-DAG method (v2).

This is the empirical counterpart to the constructed dataset in scripts/gen_eval.py: the numbers
come from a real topology, not injected faults. It is the source of truth for the paper's
"Real-World Case Study" section — run it and paste the emitted LaTeX table.

IMPORTANT honesty note (must stay in the paper too): the two v1-vs-v2 gaps come from DIFFERENT
mechanisms. On the synthetic dataset, v1 misses faults because of uniform-vs-weighted
*decomposition*. On train-ticket, v1 misses faults because critical-path *reduction* collapses
the 38-node DAG to one series chain, hiding services that sit off that chain — which full-DAG
aggregation (v2) sees. The case study evidences the topology-coverage contribution.

Reproduce offline (no credentials):
    python scripts/case_study.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from slacheck.datadog.source import get_source
from slacheck.models import SloValues
from slacheck.pipeline import AnalysisResult, analyze

REPO = Path(__file__).resolve().parents[1]
TOPOLOGY = REPO / "fixtures" / "topology" / "train-ticket.yaml"
ENTRYPOINT = "ts-ui-dashboard"

# Architect Global-SLOs chosen to expose the topology-coverage gap on a real system.
AVAIL_TARGET = 99.9  # % — demanding but realistic for a booking system
LATENCY_TARGET = 30.0  # ms — exposes v1's critical-path false-negative


def _run(
    version: Literal["v1", "v2"],
    constraint: Literal["latency", "availability"],
    target: SloValues,
) -> AnalysisResult:
    """Run the pipeline on declared train-ticket with fixture metrics."""
    source = get_source("declared", topology=TOPOLOGY, metrics_from="fixture")
    return analyze(source, ENTRYPOINT, constraint, target=target, paper_version=version)


def _descending(result: AnalysisResult) -> set[str]:
    return {
        f.component for f in result.verdict.faults if f.direction == "descending" and f.component
    }


def availability_case() -> dict:
    """v1 vs v2 under availability >= AVAIL_TARGET."""
    target = SloValues(availability_pct=AVAIL_TARGET)
    v1, v2 = _run("v1", "availability", target), _run("v2", "availability", target)
    return {
        "v1_env": v1.verdict.envelope.availability_pct,
        "v2_env": v2.verdict.envelope.availability_pct,
        "v1_faults": len(v1.verdict.faults),
        "v2_faults": len(v2.verdict.faults),
        "v1_desc": sorted(_descending(v1)),
        "v2_desc": sorted(_descending(v2)),
        "recovered": sorted(_descending(v2) - _descending(v1)),
        "dropped_edges": v2.dropped_edges,
    }


def latency_case() -> dict:
    """v1 vs v2 under latency <= LATENCY_TARGET (the false-negative demonstration)."""
    target = SloValues(response_time_ms=LATENCY_TARGET)
    v1, v2 = _run("v1", "latency", target), _run("v2", "latency", target)
    return {
        "v1_env": v1.verdict.envelope.response_time_ms,
        "v2_env": v2.verdict.envelope.response_time_ms,
        "v1_feasible": v1.verdict.feasible,
        "v2_feasible": v2.verdict.feasible,
        "v1_faults": len(v1.verdict.faults),
        "v2_faults": len(v2.verdict.faults),
    }


def format_latex(av: dict, lat: dict) -> str:
    """Render the paper-ready case-study table (LaTeX, IEEEtran)."""
    return (
        "\\begin{table}[htbp]\n"
        "\\caption{train-ticket case study: detection on a real 38-service topology "
        "(declared graph, fixture metrics).}\n"
        "\\begin{center}\n"
        "\\begin{tabular}{|l|c|c|}\n"
        "\\hline\n"
        "\\textbf{Validation} & \\textbf{v1 (critical path)} & \\textbf{v2 (typed DAG)} \\\\\n"
        "\\hline\n"
        f"Achievable availability & {av['v1_env']:.2f}\\% & {av['v2_env']:.2f}\\% \\\\\n"
        f"Faults at avail.\\ $\\geq$ {AVAIL_TARGET:g}\\% & {av['v1_faults']} & {av['v2_faults']} "
        "\\\\\n"
        f"Achievable latency & {lat['v1_env']:g}\\,ms & {lat['v2_env']:g}\\,ms \\\\\n"
        f"Verdict at lat.\\ $\\leq$ {LATENCY_TARGET:g}\\,ms & "
        f"{'feasible' if lat['v1_feasible'] else 'fault'} & "
        f"{'feasible' if lat['v2_feasible'] else 'fault'} \\\\\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\label{tab:casestudy}\n"
        "\\end{center}\n"
        "\\end{table}"
    )


def main() -> None:
    av = availability_case()
    lat = latency_case()

    print("=== train-ticket case study (declared topology, fixture metrics) ===\n")
    print(f"Availability target >= {AVAIL_TARGET}%:")
    print(f"  v1: envelope {av['v1_env']:.2f}%, {av['v1_faults']} faults, desc {av['v1_desc']}")
    print(f"  v2: envelope {av['v2_env']:.2f}%, {av['v2_faults']} faults, desc {av['v2_desc']}")
    print(f"  v2 recovers (off v1's critical path): {av['recovered']}")
    print(f"  cycles broken to a DAG: {av['dropped_edges']}\n")

    print(f"Latency target <= {LATENCY_TARGET}ms (false-negative demonstration):")
    v1v = "feasible" if lat["v1_feasible"] else "fault"
    v2v = "feasible" if lat["v2_feasible"] else "fault"
    print(f"  v1: env {lat['v1_env']:g}ms -> {v1v} ({lat['v1_faults']} faults)")
    print(f"  v2: env {lat['v2_env']:g}ms -> {v2v} ({lat['v2_faults']} faults)\n")

    print(format_latex(av, lat))


if __name__ == "__main__":
    main()
