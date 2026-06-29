"""Run the injected-fault dataset through v1 or v2 and count detections (paper §VI, Table I).

Each scenario is a paper-v2 superset YAML with an ``expected`` block naming the injected
fault category. A scenario is "detected" when the chosen engine raises at least one fault
matching the expected category. v1 and v2 are run over the SAME dataset to reproduce the
paper's 57/60 (v1, uniform decomposition) vs 60/60 (v2, weighted) Sub-SLO result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from slacheck.envelope.faults import evaluate as evaluate_v1
from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
from slacheck.models import (
    Component,
    CspProfile,
    DependencyEdge,
    DependencyGraph,
    KnowledgeBase,
    PaperVersion,
    ReconfigStrategy,
    SloValues,
)

CATEGORIES = ("global_slo", "sub_slo", "reconfig")


@dataclass
class EvalReport:
    """(injected, detected) counts per Table I category."""

    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    missed: list[str] = field(default_factory=list)  # scenario names not detected

    def detected(self, category: str) -> int:
        return self.by_category.get(category, (0, 0))[1]

    def injected(self, category: str) -> int:
        return self.by_category.get(category, (0, 0))[0]


def _load_scenario(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text())
    components = {
        c["name"]: Component(
            name=c["name"],
            csp=c.get("csp"),
            slo=SloValues(**c["slo"]),
            csp_profile=CspProfile(**c["csp_profile"]) if c.get("csp_profile") else None,
        )
        for c in raw["components"]
    }
    graph = DependencyGraph(
        components=components,
        edges=[DependencyEdge(**e) for e in raw.get("edges", [])],
        entrypoint=raw["entrypoint"],
    )
    return {
        "name": path.stem,
        "graph": graph,
        "target": SloValues(**raw["global_target"]) if raw.get("global_target") else None,
        "kb": KnowledgeBase(**raw["knowledge_base"]) if raw.get("knowledge_base") else None,
        "strategies": [ReconfigStrategy(**s) for s in raw.get("reconfig_strategies", [])],
        "target_slos": raw.get("target_slos", []),
        "expected": raw["expected"],  # {category, metric}
    }


def _v1_series(graph: DependencyGraph) -> list[Component]:
    """v1 has no typed topology: flatten to the components in topological order."""
    return [graph.components[n] for n in graph.topological_order()]


def _detect(scenario: dict, paper_version: PaperVersion) -> bool:
    """Run the engine and return whether the expected fault category was detected."""
    exp = scenario["expected"]
    metric = exp.get("metric")
    category = exp["category"]

    if paper_version == "v1":
        # v1 cannot model reconfiguration or typed topology; uniform decomposition.
        if category == "reconfig":
            return False
        verdict = evaluate_v1(_v1_series(scenario["graph"]), scenario["target"])
    else:
        verdict = evaluate_v2(
            scenario["graph"],
            scenario["target"],
            scenario["kb"],
            scenario["strategies"],
            scenario["target_slos"],
        )

    return any(f.metric == metric for f in verdict.faults) if metric else bool(verdict.faults)


def run_eval(dataset_dir: Path, paper_version: PaperVersion) -> EvalReport:
    report = EvalReport()
    for category in CATEGORIES:
        cat_dir = dataset_dir / category
        scenarios = sorted(cat_dir.glob("*.yaml")) if cat_dir.is_dir() else []
        injected = len(scenarios)
        detected = 0
        for path in scenarios:
            scenario = _load_scenario(path)
            if _detect(scenario, paper_version):
                detected += 1
            else:
                report.missed.append(scenario["name"])
        report.by_category[category] = (injected, detected)
    return report


def format_table(report: EvalReport, paper_version: str) -> str:
    """Render the Table I rows for a report."""
    lines = [f"Fault detection (paper {paper_version}):", ""]
    lines.append(f"{'Category':<28}{'Injected':>10}{'Detected':>10}")
    labels = {
        "global_slo": "Global-SLO Inconsistencies",
        "sub_slo": "Sub-SLO Inconsistencies",
        "reconfig": "Reconfiguration Inconsistencies",
    }
    for cat in CATEGORIES:
        inj, det = report.by_category.get(cat, (0, 0))
        lines.append(f"{labels[cat]:<28}{inj:>10}{det:>10}")
    return "\n".join(lines)


def category_dirs(dataset_dir: Path) -> Iterable[Path]:
    return (dataset_dir / c for c in CATEGORIES)
