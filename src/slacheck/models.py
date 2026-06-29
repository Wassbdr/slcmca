"""Data contracts shared across all layers. Datadog-agnostic (pydantic v2).

These are the lingua franca between the Datadog adapter, the graph layer, the pure
envelope engine, and the dashboard builder. Nothing here imports Datadog.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Metric = Literal["response_time", "availability", "cost", "reconfiguration"]
Direction = Literal["ascending", "descending"]
Constraint = Literal["latency", "availability"]

# --- paper-v2 additions ------------------------------------------------------
EdgeType = Literal["conjunctive", "disjunctive"]  # τ(e), paper-v2 §IV.B
PaperVersion = Literal["v1", "v2"]
CspTier = Literal["tier1", "tier2", "tier3", "tier4"]  # Uptime-Institute-style, ref [4]
CompareOp = Literal["gt", "lt", "ge", "le"]


class SloValues(BaseModel):
    """One component's measured Sub-SLO, or a target Global-SLO (paper §II.A).

    ``cost_eur_h`` is ``None`` when no cost source is available — Datadog does not
    expose per-microservice cost (see docs/datadog_api_catalog.md §5).
    """

    response_time_ms: float | None = None
    availability_pct: float | None = None  # 0..100
    cost_eur_h: float | None = None

    @property
    def error_budget(self) -> float | None:
        """100 − availability, the quantity that composes additively (SRE error budget)."""
        if self.availability_pct is None:
            return None
        return 100.0 - self.availability_pct


class ResourceMetrics(BaseModel):
    """Per-service Kubernetes resource signals (infra health, beyond the paper's SLOs).

    These come from ``kubernetes.*`` metrics tagged by ``kube_deployment`` and are
    available even when APM tracing is not (see docs/datadog_api_catalog.md §4). They
    enrich the verdict with a resource-pressure view; they do not feed the SLA operators.
    """

    cpu_nanocores: float | None = None  # avg kubernetes.cpu.usage.total (nanocores)
    mem_bytes: float | None = None  # avg kubernetes.memory.usage (bytes)
    restarts: float | None = None  # sum kubernetes.containers.restarts over the window


class CspProfile(BaseModel):
    """CSP reliability properties used to derive the paper-v2 safety margin γ (§IV.C).

    ``tier`` selects the conservative tier-floor; ``sigma`` is the empirical stddev of
    delivered performance (0 when no historical data → margin falls back to the floor).
    """

    tier: CspTier
    sigma: float = 0.0


class Component(BaseModel):
    """A service node: its name, optional CSP, measured Sub-SLO, infra resources, and raw sample.

    ``sample`` keeps the raw Datadog counters (request_count / error_count) for
    traceability so a verdict can be audited back to the metrics it came from.
    """

    name: str
    csp: str | None = None
    slo: SloValues = Field(default_factory=SloValues)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)
    csp_profile: CspProfile | None = None  # paper-v2: drives the safety margin γ
    sample: dict = Field(default_factory=dict)


class Envelope(BaseModel):
    """The guaranteeable envelope (ascending aggregation result, paper §IV.B).

    Values are achievable *over the series critical path* — not the whole DAG.
    ``cost_eur_h`` is ``None`` when cost data is unavailable.
    """

    response_time_ms: float | None = None
    availability_pct: float | None = None
    cost_eur_h: float | None = None
    path: list[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    """A typed functional dependency u → v (paper-v2 §IV.B)."""

    source: str
    target: str
    edge_type: EdgeType = "conjunctive"


class DependencyGraph(BaseModel):
    """Pure typed DAG consumed by the paper-v2 engine (no networkx, no Datadog).

    The impure ``graph/`` layer projects an ``nx.DiGraph`` into this. All traversal
    here is hand-rolled so ``envelope/v2`` stays import-pure.
    """

    components: dict[str, Component]
    edges: list[DependencyEdge] = Field(default_factory=list)
    entrypoint: str

    def model_post_init(self, __context: object) -> None:
        # A node's incoming edges must agree on a single type (the fan-in combines one way).
        by_target: dict[str, set[str]] = {}
        for e in self.edges:
            by_target.setdefault(e.target, set()).add(e.edge_type)
        for target, types in by_target.items():
            if len(types) > 1:
                raise ValueError(
                    f"node {target!r} has mixed incoming edge types {sorted(types)}; "
                    "a fan-in group must be all conjunctive or all disjunctive"
                )

    def indegree(self, name: str) -> int:
        return sum(1 for e in self.edges if e.target == name)

    def successors(self, name: str) -> list[str]:
        return [e.target for e in self.edges if e.source == name]

    def predecessors(self, name: str) -> list[str]:
        return [e.source for e in self.edges if e.target == name]

    def edge_type_into(self, name: str) -> EdgeType:
        """How ``name``'s parents combine. Defaults to conjunctive when no parents."""
        for e in self.edges:
            if e.target == name:
                return e.edge_type
        return "conjunctive"

    def topological_order(self) -> list[str]:
        """Kahn's algorithm. Raises ``ValueError`` on a cycle."""
        indeg = {n: 0 for n in self.components}
        for e in self.edges:
            indeg[e.target] = indeg.get(e.target, 0) + 1
        queue = sorted(n for n, d in indeg.items() if d == 0)
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for succ in sorted(self.successors(n)):
                indeg[succ] -= 1
                if indeg[succ] == 0:
                    queue.append(succ)
            queue.sort()
        if len(order) != len(self.components):
            raise ValueError("DependencyGraph is not acyclic")
        return order

    def root_to_leaf_paths(self) -> list[list[str]]:
        """All paths from the entrypoint down to leaf nodes (DFS over successors)."""
        paths: list[list[str]] = []

        def dfs(node: str, acc: list[str]) -> None:
            succs = self.successors(node)
            if not succs:
                paths.append(acc)
                return
            for s in succs:
                dfs(s, [*acc, s])

        dfs(self.entrypoint, [self.entrypoint])
        return paths


class MarginConfig(BaseModel):
    """Knowledge-base config for the safety margin γ (paper-v2 §IV.C)."""

    k: float = 2.0  # confidence factor; k=2 covers ~95% under a normal distribution
    tier_floor: dict[CspTier, float] = Field(default_factory=dict)  # γ_tier lookup


class ReconfigState(BaseModel):
    name: str


class ReconfigTransition(BaseModel):
    """A state-machine transition fired when ``trigger_metric trigger_op trigger_value``."""

    from_state: str
    to_state: str
    trigger_metric: str  # operational metric, e.g. "cpu_pct"
    trigger_op: CompareOp
    trigger_value: float


class ReconfigStrategy(BaseModel):
    """Elasticity strategy for a component, modeled as a state machine (paper-v2 §IV.E)."""

    name: str
    component: str
    states: list[ReconfigState] = Field(default_factory=list)
    transitions: list[ReconfigTransition] = Field(default_factory=list)
    actions: dict = Field(default_factory=dict)


class SloTranslationRule(BaseModel):
    """Translates a high-level SLO metric into the operational predicate that sustains it.

    e.g. throughput SLO requires cpu_pct ≤ 80 (paper-v2 §IV.E).
    """

    slo_metric: str
    operational_metric: str
    operational_op: CompareOp
    operational_value: float


class KnowledgeBase(BaseModel):
    """The configurable registry: SLO→operational translation + margin config (paper-v2 §V)."""

    translation_rules: list[SloTranslationRule] = Field(default_factory=list)
    margin_config: MarginConfig = Field(default_factory=MarginConfig)


class Threshold(BaseModel):
    """Descending per-component requirement (paper §IV.C)."""

    component: str
    required: SloValues


class Fault(BaseModel):
    """An over-commitment fault. ``component`` is None for ascending (whole-path) faults."""

    direction: Direction
    metric: Metric
    component: str | None
    target: float
    achievable: float
    message: str


class Verdict(BaseModel):
    """End-to-end result: the envelope, per-component thresholds, and any faults.

    ``commit_envelope`` and ``weights`` are populated only by the paper-v2 engine
    (margin-adjusted A_commit and the structural weight vector wᵢ).
    """

    envelope: Envelope
    thresholds: list[Threshold] = Field(default_factory=list)
    faults: list[Fault] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    commit_envelope: Envelope | None = None  # paper-v2: A_commit (after γ margins)
    weights: dict[str, float] = Field(default_factory=dict)  # paper-v2: structural wᵢ
    paper_version: PaperVersion = "v1"

    @property
    def feasible(self) -> bool:
        return not self.faults
