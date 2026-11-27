"""Run from the repository root with make bench."""

from __future__ import annotations

import math
import platform
import random
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

import yaml
from scripts.bench_tools import TOOL_DIR
from scripts.gen_realistic_eval import _build_topology, _sample_size

from slacheck.availability import check_availability
from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
from slacheck.models import Component, DependencyEdge, DependencyGraph, SloValues

T = TypeVar("T")
SEEDS = {"development": (11, 29, 47), "held-out": (101, 131, 167)}


@dataclass
class Result:
    infeasible: bool
    thresholds: dict[str, float | None] | None = None


@dataclass
class Case:
    name: str
    graph: DependencyGraph
    target: float


def cases(split: str, seed: int, size: int | None = None) -> list[Case]:
    rng = random.Random(seed)
    result = []
    for i in range(12 if size is None else 1):
        n = size or min(12, max(6, _sample_size(rng)))
        if split == "development":
            names, pairs = _build_topology(rng, n)
            links = [(a, b, "conjunctive") for a, b in pairs]
            effective_size = n
        else:
            names = [f"s{j}" for j in range(n)]
            links = []
            stages = (n - 2) // 3
            for j in range(stages):
                gate, left, right = names[2 + 3 * j:5 + 3 * j]
                links.extend([
                    ("s0", gate, "conjunctive"),
                    (gate, left, "disjunctive"),
                    (gate, right, "disjunctive"),
                    (left, "s1", "conjunctive"),
                    (right, "s1", "conjunctive"),
                ])
            links.extend(("s0", name, "conjunctive") for name in names[2 + 3 * stages:])
            effective_size = n - 2 * stages
        # Service SLOs and target sampled without consulting any checker or oracle.
        failure = {name: rng.uniform(0.01, 0.8) for name in names}
        budget = min(99.0, effective_size * rng.uniform(0.25, 0.58))
        graph = DependencyGraph(
            components={
                name: Component(name=name, slo=SloValues(availability_pct=100 - failure[name]))
                for name in names
            },
            edges=[
                DependencyEdge(source=a, target=b, edge_type=kind) for a, b, kind in links
            ],
            entrypoint="s0",
        )
        result.append(Case(f"{split}-{seed}-{i:02d}", graph, 100 - budget))
    return result


def oracle(case: Case) -> Result:
    graph = case.graph
    names = list(graph.components)
    order = list(reversed(graph.topological_order()))
    children = {
        name: (
            [e.target for e in graph.edges if e.source == name and e.edge_type == "conjunctive"],
            [e.target for e in graph.edges if e.source == name and e.edge_type == "disjunctive"],
        )
        for name in names
    }
    p = {name: availability(graph, name) / 100 for name in names}
    failed: list[float] = []
    forced = {(name, up): [] for name in names for up in (False, True)}
    for values in product((False, True), repeat=len(names)):
        state = dict(zip(names, values, strict=True))
        works: dict[str, bool] = {}
        for name in order:
            needed, alternatives = children[name]
            works[name] = (
                state[name]
                and all(works[child] for child in needed)
                and (not alternatives or any(works[child] for child in alternatives))
            )
        if works[graph.entrypoint]:
            continue
        weights = [p[name] if state[name] else 1 - p[name] for name in names]
        prefix = [1.0]
        for weight in weights:
            prefix.append(prefix[-1] * weight)
        failed.append(prefix[-1])
        suffix = 1.0
        for j in reversed(range(len(names))):
            forced[names[j], values[j]].append(prefix[j] * suffix)
            suffix *= weights[j]
    budget = (100 - case.target) / 100
    thresholds: dict[str, float | None] = {}
    for name in names:
        down = math.fsum(forced[name, False])
        up = math.fsum(forced[name, True])
        if up > budget:
            thresholds[name] = None
        elif down <= budget:
            thresholds[name] = 0.0
        else:
            thresholds[name] = 100 * (down - budget) / (down - up)
    return Result(math.fsum(failed) > budget, thresholds)


def availability(graph: DependencyGraph, name: str) -> float:
    value = graph.components[name].slo.availability_pct
    assert value is not None
    return value


def legacy(case: Case) -> Result:
    verdict = evaluate_v2(case.graph, SloValues(availability_pct=case.target))
    return Result(
        any(f.direction == "ascending" for f in verdict.faults),
        {t.component: t.required.availability_pct for t in verdict.thresholds},
    )


def independent(case: Case) -> Result:
    result = check_availability(case.graph, case.target)
    return Result(not result.feasible, result.thresholds_pct)


def cli_time(root: Path, case: Case, expected: Result) -> float:
    path = root / f"{case.name}.yaml"
    graph = case.graph
    path.write_text(yaml.safe_dump({
        "entrypoint": graph.entrypoint,
        "components": [part.model_dump(exclude_none=True) for part in graph.components.values()],
        "edges": [edge.model_dump() for edge in graph.edges],
        "global_target": {"availability_pct": case.target},
    }))
    command = [sys.executable, "-m", "slacheck.cli", "check", str(path), "--independent"]
    run, ms = timed(lambda: subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False,
    ))
    if run.returncode != int(expected.infeasible) or (
        run.stdout.count("\n  s") != len(graph.components)
    ):
        raise SystemExit(f"slacheck failed on {case.name}:\n{run.stdout}{run.stderr}")
    return ms


def worksheet(case: Case) -> Result:
    graph = case.graph
    mandatory: dict[str, set[str]] = {}
    for name in reversed(graph.topological_order()):
        required = {name}
        fallback = []
        for e in graph.edges:
            if e.source != name:
                continue
            if e.edge_type == "conjunctive":
                required.update(mandatory[e.target])
            else:
                fallback.append(mandatory[e.target])
        if fallback:
            required.update(set.intersection(*fallback))
        mandatory[name] = required
    errors = math.fsum(100 - availability(graph, n) for n in mandatory[graph.entrypoint])
    return Result(errors > 100 - case.target)


def documents(case: Case) -> dict[str, dict]:
    service = case.name
    total = f'http_requests_total{{service="{service}"}}'
    errors = f'http_requests_total{{service="{service}",code=~"5.."}}'
    return {
        "sloth": {
            "version": "prometheus/v1",
            "service": service,
            "slos": [{
                "name": "availability",
                "objective": case.target,
                "sli": {"events": {
                    "error_query": f"sum(rate({errors}[{{{{.window}}}}]))",
                    "total_query": f"sum(rate({total}[{{{{.window}}}}]))",
                }},
                "alerting": {"name": "Availability"},
            }],
        },
        "pyrra": {
            "apiVersion": "pyrra.dev/v1alpha1",
            "kind": "ServiceLevelObjective",
            "metadata": {"name": service, "namespace": "default"},
            "spec": {
                "target": str(case.target),
                "window": "30d",
                "indicator": {"ratio": {
                    "errors": {"metric": errors}, "total": {"metric": total},
                }},
            },
        },
        "oslo": {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": service},
            "spec": {
                "service": service,
                "indicator": {
                    "metadata": {"name": f"{service}-sli"},
                    "spec": {"ratioMetric": {
                        "counter": True,
                        "bad": {"metricSource": {"type": "Prometheus", "spec": {"query": errors}}},
                        "total": {"metricSource": {"type": "Prometheus", "spec": {"query": total}}},
                    }},
                },
                "timeWindow": [{"duration": "30d", "isRolling": True}],
                "budgetingMethod": "Occurrences",
                "objectives": [{"target": case.target / 100}],
            },
        },
    }


def timed(fn: Callable[[], T]) -> tuple[T, float]:
    start = perf_counter()
    result = fn()
    return result, 1000 * (perf_counter() - start)


def find_tool(tool: str) -> str | None:
    return shutil.which(str(TOOL_DIR / tool)) or shutil.which(tool)


def run_tool(tool: str, executable: str, root: Path, case: Case) -> tuple[Result, float]:
    path = root / f"{tool}-{case.name}.yaml"
    path.write_text(yaml.safe_dump(documents(case)[tool]))
    out = root / "rules"
    output = out / path.name
    commands = {
        "sloth": ["validate", "-i", str(path)],
        "pyrra": ["generate", f"--config-files={path}", f"--prometheus-folder={out}"],
        "oslo": ["validate", "-f", str(path)],
    }
    if tool == "pyrra":
        output.unlink(missing_ok=True)
    run, ms = timed(lambda: subprocess.run(
        [executable, *commands[tool]], capture_output=True, text=True, timeout=30, check=False,
    ))
    if run.returncode or (tool == "pyrra" and not output.is_file()):
        raise SystemExit(f"{tool} failed on {case.name}:\n{run.stdout}{run.stderr}")
    return Result(False), ms


def score(truth: Sequence[Result], predictions: Sequence[Result]) -> tuple[int, int, int, int]:
    tp = fp = matched = total = 0
    for expected, actual in zip(truth, predictions, strict=True):
        tp += expected.infeasible and actual.infeasible
        fp += not expected.infeasible and actual.infeasible
        if expected.thresholds is None or actual.thresholds is None:
            continue
        for name, threshold in expected.thresholds.items():
            total += 1
            predicted = actual.thresholds[name]
            if threshold is None or predicted is None:
                matched += threshold is predicted
            else:
                matched += math.isclose(predicted, threshold, rel_tol=0, abs_tol=1e-8)
    return tp, fp, matched, total


def cpu_model() -> str:
    info = Path("/proc/cpuinfo")
    if info.is_file():
        for line in info.read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or platform.machine()


def main() -> None:
    series = [
        case for split, seeds in SEEDS.items() for seed in seeds for case in cases(split, seed)
    ]
    truth = [oracle(case) for case in series]
    big = [cases(split, seeds[0], 200)[0] for split, seeds in SEEDS.items()]
    methods = {
        "slacheck independent": independent,
        "slacheck v2": legacy,
        "Hand error budget": worksheet,
    }
    tools = {"Sloth": "sloth", "Pyrra": "pyrra", "OpenSLO": "oslo"}
    missing = set()
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "rules").mkdir()
        predictions = {name: [fn(case) for case in series] for name, fn in methods.items()}
        timings = {
            name: [[timed(partial(fn, case))[1] for _ in range(7)] for case in big]
            for name, fn in methods.items()
        }
        timings["slacheck independent CLI"] = [
            [cli_time(root, case, independent(case)) for _ in range(7)] for case in big
        ]
        for name, tool in tools.items():
            executable = find_tool(tool)
            if executable is None:
                missing.add(name)
                print(f"{name} ({tool}): not installed", file=sys.stderr)
                continue
            predictions[name] = [
                run_tool(tool, executable, root, case)[0] for case in series
            ]
            timings[name] = [
                [run_tool(tool, executable, root, case)[1] for _ in range(7)]
                for case in big
            ]

    lines = [
        "# Availability commitment benchmark", "",
        f"CPU: {cpu_model()} ({platform.machine()}); Python {platform.python_version()}; no GPU.",
        "Synthetic per-service probabilities; seeds and reference setup: [README](README.md).",
        "Service states are independent; shared dependencies reuse the same service state.",
        "Single-service thresholds hold all other measurements fixed. A threshold can be",
        "impossible even at 100%. Match tolerance: 0.00000001 percentage points.",
        "Classification uses global commitment faults only, not v2 budget allocation faults.",
        "",
    ]
    for split in SEEDS:
        ids = [i for i, case in enumerate(series) if case.name.startswith(split)]
        expected = [truth[i] for i in ids]
        positives = sum(item.infeasible for item in expected)
        lines.extend([
            f"## {split.capitalize()}", "",
            f"{len(ids)} graphs, {positives} infeasible.", "",
            "| Method | Recall | Precision | False positives | Thresholds matched |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        for name, actual in predictions.items():
            tp, fp, matched, total = score(expected, [actual[i] for i in ids])
            precision = f"{tp}/{tp + fp}" if tp + fp else "n/a"
            thresholds = f"{matched}/{total}" if total else "not computed"
            lines.append(f"| {name} | {tp}/{positives} | {precision} | {fp} | {thresholds} |")
        for name in tools:
            if name in missing:
                lines.append(f"| {name} | not installed | | | |")
        lines.append("")
        for name in methods:
            misses = [
                series[i].name for i in ids
                if truth[i].infeasible and not predictions[name][i].infeasible
            ]
            if misses:
                lines.append(f"{name} missed: {', '.join(misses)}.")
        lines.append("")

    lines.extend([
        "## Runtime", "",
        "Milliseconds for 200 services, seven serial samples per graph. Python methods run",
        "in process on parsed inputs. CLI timings include process start and YAML reading,",
        "plus threshold output for slacheck or validation or rule generation for references.",
        "Reference manifests carry the same root objective and an SLI selector,",
        "not the graph or service availabilities.", "",
        "| Method | Development median / max | Held-out median / max |",
        "| --- | ---: | ---: |",
    ])
    for name, samples in timings.items():
        formatted = [f"{statistics.median(values):.2f} / {max(values):.2f}" for values in samples]
        lines.append(f"| {name} | {' | '.join(formatted)} |")
    for name in tools:
        if name in missing:
            lines.append(f"| {name} | not installed | not installed |")
    baseline = score(truth, predictions["slacheck v2"])
    current = score(truth, predictions["slacheck independent"])
    positives = sum(item.infeasible for item in truth)
    lines.extend([
        "", "## Iteration 1: model shared service states and solve conditional thresholds", "",
        "V2 counted shared required services along each path, and treated fallback branches",
        "with a shared dependency as independent. Its service thresholds were budget",
        "allocations, not the minimum availability with other services held fixed.", "",
        "| Metric | Baseline v2 | Decision diagram | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Infeasible commitments found | {baseline[0]}/{positives} | "
        f"{current[0]}/{positives} | {current[0] - baseline[0]:+} |",
        f"| False positives | {baseline[1]} | {current[1]} | {current[1] - baseline[1]:+} |",
        f"| Exact conditional thresholds | {baseline[2]}/{baseline[3]} | "
        f"{current[2]}/{current[3]} | {current[2] - baseline[2]:+} |",
    ])
    output = Path("benchmarks/results.md")
    output.write_text("\n".join(lines) + "\n")
    print(f"Wrote {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
