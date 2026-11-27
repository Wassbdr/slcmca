"""Availability of a typed graph with independent service states."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from slacheck.models import DependencyGraph

_NODE_LIMIT = 100_000


@dataclass(frozen=True)
class AvailabilityCheck:
    achievable_pct: float
    target_pct: float
    feasible: bool
    thresholds_pct: dict[str, float | None]


@dataclass(frozen=True)
class ServiceImprovement:
    service: str
    current_pct: float
    required_pct: float
    increase_pp: float
    estimated_cost: float | None


def suggest_improvements(
    graph: DependencyGraph,
    result: AvailabilityCheck,
    costs_per_point: Mapping[str, float] | None = None,
) -> list[ServiceImprovement]:
    """Rank single-service repairs by supplied linear cost, or by percentage-point increase."""
    if costs_per_point is not None:
        for name, price in costs_per_point.items():
            if name not in graph.components:
                raise ValueError(f"remove unknown service {name!r} from the improvement costs.")
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not (
                math.isfinite(price) and price >= 0
            ):
                raise ValueError(f"set the improvement cost for {name!r} to a nonnegative number.")
    if result.feasible:
        return []

    repairs = []
    for name, threshold in result.thresholds_pct.items():
        if threshold is None:
            continue
        value = graph.components[name].slo.availability_pct
        current = _percentage(value, f"{name}.availability_pct")
        increase = threshold - current
        if increase <= 0:
            continue
        cost = None
        if costs_per_point is not None:
            if name not in costs_per_point:
                raise ValueError(f"add an improvement cost for {name!r} to the cost file.")
            cost = costs_per_point[name] * increase
            if not math.isfinite(cost):
                raise ValueError(f"lower the improvement cost for {name!r}; estimate overflow.")
        repairs.append(ServiceImprovement(name, current, threshold, increase, cost))
    return sorted(repairs, key=lambda repair: (
        repair.increase_pp if repair.estimated_cost is None else repair.estimated_cost,
        repair.increase_pp,
        repair.service,
    ))


class _DecisionDiagram:
    def __init__(self, size: int) -> None:
        self.nodes = [(size, 0, 0), (size, 1, 1)]
        self.unique: dict[tuple[int, int, int], int] = {}
        self.merged: dict[tuple[bool, int, int], int] = {}

    def node(self, variable: int, down: int, up: int) -> int:
        if down == up:
            return down
        key = (variable, down, up)
        if key in self.unique:
            return self.unique[key]
        if len(self.nodes) >= _NODE_LIMIT:
            raise ValueError(
                "availability graph exceeds the decision diagram limit; "
                "split it into smaller commitment scopes."
            )
        idx = len(self.nodes)
        self.unique[key] = idx
        self.nodes.append(key)
        return idx

    def merge(self, required: bool, a: int, b: int) -> int:
        if a > b:
            a, b = b, a
        if a == b:
            return a
        if a == 0:
            return 0 if required else b
        if a == 1:
            return b if required else 1
        key = (required, a, b)
        if key not in self.merged:
            if len(self.merged) >= _NODE_LIMIT:
                raise ValueError(
                    "availability graph exceeds the decision diagram limit; "
                    "split it into smaller commitment scopes."
                )
            va, da, ua = self.nodes[a]
            vb, db, ub = self.nodes[b]
            v = min(va, vb)
            self.merged[key] = self.node(
                v,
                self.merge(required, da if va == v else a, db if vb == v else b),
                self.merge(required, ua if va == v else a, ub if vb == v else b),
            )
        return self.merged[key]

    def group(self, required: bool, members: list[int]) -> int:
        result = int(required)
        for member in sorted(set(members), key=self.nodes.__getitem__, reverse=True):
            result = self.merge(required, result, member)
        return result

    def failure_and_slopes(self, root: int, downtime: list[float]) -> tuple[float, list[float]]:
        failure = [1.0, 0.0]
        for v, down, up in self.nodes[2:]:
            failure.append(downtime[v] * failure[down] + (1 - downtime[v]) * failure[up])
        reach = [0.0] * (root + 1)
        reach[root] = 1.0
        slopes = [0.0] * len(downtime)
        for idx in range(root, 1, -1):
            if reach[idx]:
                v, down, up = self.nodes[idx]
                mass = reach[idx]
                slopes[v] += mass * (failure[down] - failure[up])
                reach[down] += mass * downtime[v]
                reach[up] += mass * (1 - downtime[v])
        return failure[root], slopes


def _percentage(value: float | None, field: str) -> float:
    if value is None or not 0 <= value <= 100:
        raise ValueError(f"set {field} to an availability percentage between 0 and 100.")
    return value


def check_availability(graph: DependencyGraph, target_pct: float) -> AvailabilityCheck:
    """Check entrypoint availability and return exact conditional thresholds.

    Distinct services have independent up/down states. Repeated references to
    one service use the same state. Each caller needs every conjunctive callee
    and at least one disjunctive callee if it has a disjunctive group.

    Thresholds hold all other service measurements fixed; None means the target
    cannot be met by changing that service alone. Unreachable services are not
    included. Raises ValueError for invalid inputs or excessive diagram size.
    """
    target_pct = _percentage(target_pct, "the target")
    if graph.entrypoint not in graph.components:
        raise ValueError("add an entrypoint service to the topology.")
    required: dict[str, list[str]] = {name: [] for name in graph.components}
    fallback: dict[str, list[str]] = {name: [] for name in graph.components}
    for edge in graph.edges:
        group = required if edge.edge_type == "conjunctive" else fallback
        group[edge.source].append(edge.target)

    index: dict[str, int] = {}
    pending = [graph.entrypoint]
    while pending:
        name = pending.pop()
        if name not in index:
            index[name] = len(index)
            pending.extend(reversed(required[name] + fallback[name]))
    downtime = [
        (100 - _percentage(graph.components[name].slo.availability_pct, f"{name}.availability_pct"))
        / 100
        for name in index
    ]
    diagram = _DecisionDiagram(len(index))
    roots: dict[str, int] = {}
    try:
        for name in reversed(graph.topological_order()):
            if name not in index:
                continue
            members = [diagram.node(index[name], 0, 1), *(roots[c] for c in required[name])]
            if fallback[name]:
                members.append(diagram.group(False, [roots[c] for c in fallback[name]]))
            roots[name] = diagram.group(True, members)
    except RecursionError as exc:
        raise ValueError(
            "availability graph exceeds the decision diagram depth limit; "
            "split it into smaller commitment scopes."
        ) from exc

    failure, slopes = diagram.failure_and_slopes(roots[graph.entrypoint], downtime)
    budget = (100 - target_pct) / 100
    tolerance = 8 * math.ulp(budget) if budget else 0
    thresholds: dict[str, float | None] = {}
    for name, q, slope in zip(index, downtime, slopes, strict=True):
        up = failure - q * slope
        down = failure + (1 - q) * slope
        if up > budget + tolerance:
            thresholds[name] = None
        elif down <= budget + tolerance:
            thresholds[name] = 0.0
        else:
            thresholds[name] = min(100.0, 100 * (down - budget) / slope)
    return AvailabilityCheck(
        achievable_pct=100 - 100 * failure,
        target_pct=target_pct,
        feasible=failure <= budget + tolerance,
        thresholds_pct=thresholds,
    )
