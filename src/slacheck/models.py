"""Data contracts shared across all layers. Datadog-agnostic (pydantic v2).

These are the lingua franca between the Datadog adapter, the graph layer, the pure
envelope engine, and the dashboard builder. Nothing here imports Datadog.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Metric = Literal["response_time", "availability", "cost"]
Direction = Literal["ascending", "descending"]
Constraint = Literal["latency", "availability"]


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


class Component(BaseModel):
    """A service node: its name, optional CSP, measured Sub-SLO, infra resources, and raw sample.

    ``sample`` keeps the raw Datadog counters (request_count / error_count) for
    traceability so a verdict can be audited back to the metrics it came from.
    """

    name: str
    csp: str | None = None
    slo: SloValues = Field(default_factory=SloValues)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)
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
    """End-to-end result: the envelope, per-component thresholds, and any faults."""

    envelope: Envelope
    thresholds: list[Threshold] = Field(default_factory=list)
    faults: list[Fault] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return not self.faults
