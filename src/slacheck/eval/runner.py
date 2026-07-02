"""Run the injected-fault dataset through v1 or v2 and count detections (paper §V, Table I).

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

_LABELS = {
    "global_slo": "Global-SLO Inconsistencies",
    "sub_slo": "Sub-SLO Inconsistencies",
    "reconfig": "Reconfiguration Inconsistencies",
}


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
    """Run the engine and report whether the SPECIFIC injected fault was detected.

    Matches on the expected ``metric`` and, when given, the exact ``component`` and
    ``direction`` — so a fault on a different component (or direction) does NOT count as a
    detection. This is what makes the v1 57/60 vs v2 60/60 result meaningful.
    """
    exp = scenario["expected"]
    metric = exp.get("metric")
    component = exp.get("component")
    direction = exp.get("direction")
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

    def matches(f) -> bool:
        if metric is not None and f.metric != metric:
            return False
        if component is not None and f.component != component:
            return False
        if direction is not None and f.direction != direction:
            return False
        return True

    return any(matches(f) for f in verdict.faults)


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
    lines.append(f"{'Category':<32}{'Injected':>10}{'Detected':>10}")
    for cat in CATEGORIES:
        inj, det = report.by_category.get(cat, (0, 0))
        lines.append(f"{_LABELS[cat]:<32}{inj:>10}{det:>10}")
    return "\n".join(lines)


def format_latex(v1: EvalReport, v2: EvalReport) -> str:
    """Render the paper's Table I (``tab:eval``) from live detection counts.

    The code is the single source of truth for this table: the output is meant to be pasted
    verbatim into ``issre_paper.tex``. It therefore matches the paper's framing exactly —
    columns are the ablated **Baseline** (v1) and the **Full** method (v2), not "v1/v2" — and
    includes the injected/detected **Total** row. Regenerate with ``slacheck eval --both --latex``.
    """
    rows = []
    total_inj = total_d1 = total_d2 = 0
    # Left-align the category label to the paper's column width for a clean, stable diff.
    width = max(len(lbl) for lbl in _LABELS.values())
    for cat in CATEGORIES:
        inj = v2.injected(cat)  # injected count is the same for both engines
        d1 = v1.detected(cat)
        d2 = v2.detected(cat)
        total_inj += inj
        total_d1 += d1
        total_d2 += d2
        rows.append(f"{_LABELS[cat]:<{width}} & {inj} & {d1:>2} & {d2} \\\\")
    body = "\n".join(rows)
    total_cell = "\\textbf{Total}"
    total_label = f"{total_cell:<{width}}"
    total = (
        f"{total_label} & "
        f"\\textbf{{{total_inj}}} & \\textbf{{{total_d1}}} & \\textbf{{{total_d2}}} \\\\"
    )
    return (
        "\\begin{table}[htbp]\n"
        "\\caption{Fault detection across scenario categories: "
        "ablated baseline vs.\\ full method.}\n"
        "\\begin{center}\n"
        "\\begin{tabular}{|l|c|c|c|}\n"
        "\\hline\n"
        "\\textbf{Scenario Category} & \\textbf{Injected} &\n"
        "\\textbf{Baseline} & \\textbf{Full} \\\\\n"
        "\\hline\n"
        f"{body}\n"
        "\\hline\n"
        f"{total}\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\label{tab:eval}\n"
        "\\end{center}\n"
        "\\end{table}"
    )


def category_dirs(dataset_dir: Path) -> Iterable[Path]:
    return (dataset_dir / c for c in CATEGORIES)
