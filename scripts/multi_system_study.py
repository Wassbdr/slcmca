"""Multi-system real-world study: slacheck v1 vs v2 on several real microservice topologies.

Extends the single train-ticket case study to a second real system whose call graph is extracted
from an AUTHORITATIVE source (no edges are guessed):
  - train-ticket    (38 services) — documented static call graph, with the real per-service trace
    metrics in fixtures/datadog/. This is the PRIMARY evidence: v2's weighted decomposition targets
    the high-centrality hubs (ts-order/station/train) that v1's single critical path never visits.
  - Online Boutique (10 services) — *_SERVICE_ADDR from the official GCP k8s manifest. We have no
    per-service trace metrics for it, so it serves as STRUCTURAL evidence only: with a uniform
    nominal Sub-SLO it shows v2 aggregates the whole DAG below the target and verifies every
    service against its weighted threshold, whereas v1 reduces the graph to one critical path and
    checks only the services on it. We report this as a topology-coverage fact, not hub-targeting.

Only benchmarks whose edges are extractable from an official manifest/paper are included. Sock Shop
and DeathStarBench were considered but EXCLUDED: their call graphs are published only as
architecture images, so encoding them would require guessing edges.

Reproduce offline (no credentials):
    python scripts/multi_system_study.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from slacheck.datadog.declared_client import DeclaredClient
from slacheck.datadog.source import MetricKind, get_source
from slacheck.models import SloValues
from slacheck.pipeline import AnalysisResult, analyze

REPO = Path(__file__).resolve().parents[1]
TT_TOPO = REPO / "fixtures/topology/train-ticket.yaml"
OB_TOPO = REPO / "fixtures/topology/real/online-boutique.yaml"

NOMINAL_AVAIL = 99.9   # % per-service Sub-SLO for systems without trace fixtures
AVAIL_TARGET = 99.9    # % architect Global-SLO


# ---- train-ticket: real trace metrics (primary evidence; same config as case_study.py) -------


def _tt(version: Literal["v1", "v2"]) -> AnalysisResult:
    src = get_source("declared", topology=TT_TOPO, metrics_from="fixture")
    return analyze(src, "ts-ui-dashboard", "availability",
                   target=SloValues(availability_pct=AVAIL_TARGET), paper_version=version)


# ---- Online Boutique: nominal Sub-SLO (structural-coverage evidence) --------------------------


class NominalSource:
    """Declared edges + a uniform nominal availability per service (errors/requests proxy)."""

    def __init__(self, topology_path: Path, nominal_avail: float) -> None:
        self._declared = DeclaredClient(topology_path, self)
        self._services = list(self._declared.service_dependencies().keys())
        self._err = (100.0 - nominal_avail) / 100.0  # availability = (1-err/req)*100 = nominal

    def service_dependencies(self) -> dict:
        return self._declared.service_dependencies()

    def metric_series(self, kind: MetricKind) -> dict:
        if kind == "request_count":
            val = 1.0
        elif kind == "error_count":
            val = self._err
        else:
            return {"series": []}
        return {"series": [
            {"scope": f"service:{s}", "pointlist": [[0.0, val]]} for s in self._services
        ]}

    def list_slos(self) -> dict:
        return {"data": []}


def _ob(version: Literal["v1", "v2"]) -> AnalysisResult:
    src = NominalSource(OB_TOPO, NOMINAL_AVAIL)
    return analyze(src, "frontend", "availability",
                   target=SloValues(availability_pct=AVAIL_TARGET), paper_version=version)


def _faults(r: AnalysisResult) -> int:
    return len(r.verdict.faults)


def _path_len(r: AnalysisResult) -> int:
    return len(r.verdict.envelope.path)


def format_latex(tt1, tt2, ob1, ob2) -> str:
    return (
        "\\begin{table}[htbp]\n"
        "\\caption{Real-world systems at a 99.9\\% availability Global-SLO. train-ticket uses real "
        "trace metrics; Online Boutique uses a uniform nominal Sub-SLO (structural coverage).}\n"
        "\\begin{center}\n"
        "\\begin{tabular}{|l|c|c|c|c|c|}\n"
        "\\hline\n"
        "\\textbf{System} & \\textbf{Svc.} & \\textbf{A* v1} & \\textbf{A* v2} "
        "& \\textbf{v1 flt} & \\textbf{v2 flt} \\\\\n"
        "\\hline\n"
        f"train-ticket & 38 & {tt1.verdict.envelope.availability_pct:.2f}\\% "
        f"& {tt2.verdict.envelope.availability_pct:.2f}\\% & {_faults(tt1)} & {_faults(tt2)} \\\\\n"
        f"Online Boutique & 10 & {ob1.verdict.envelope.availability_pct:.2f}\\% "
        f"& {ob2.verdict.envelope.availability_pct:.2f}\\% & {_faults(ob1)} & {_faults(ob2)} \\\\\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\label{tab:realsystems}\n"
        "\\end{center}\n"
        "\\end{table}"
    )


def main() -> None:
    tt1, tt2 = _tt("v1"), _tt("v2")
    ob1, ob2 = _ob("v1"), _ob("v2")

    print("=== Real-world systems (Global-SLO 99.9% availability) ===\n")
    print("train-ticket (38 services, REAL trace metrics) — primary evidence:")
    print(f"  v1: envelope {tt1.verdict.envelope.availability_pct:.2f}%, {_faults(tt1)} faults, "
          f"critical path = {_path_len(tt1)} services")
    print(f"  v2: envelope {tt2.verdict.envelope.availability_pct:.2f}%, {_faults(tt2)} faults, "
          f"full DAG = {_path_len(tt2)} services")
    print("  → v2 targets high-centrality hubs off v1's critical path (see case_study.py)\n")

    print("Online Boutique (10 services, nominal Sub-SLO) — structural coverage:")
    print(f"  v1: envelope {ob1.verdict.envelope.availability_pct:.2f}%, {_faults(ob1)} faults, "
          f"critical path = {_path_len(ob1)} services")
    print(f"  v2: envelope {ob2.verdict.envelope.availability_pct:.2f}%, {_faults(ob2)} faults, "
          f"full DAG = {_path_len(ob2)} services")
    print("  → v2 aggregates all 10 services below the target; v1 checks only its path\n")

    print(format_latex(tt1, tt2, ob1, ob2))


if __name__ == "__main__":
    main()
