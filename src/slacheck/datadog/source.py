"""The live/fixture seam. Everything downstream depends only on this protocol.

A ``DatadogSource`` returns *raw* Datadog-shaped data; parsing into slacheck models
happens in topology.py / metrics.py so the same parsers run on live and fixture data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from slacheck.config import Settings

SourceKind = Literal["fixture", "live", "declared"]
MetricKind = Literal["latency_p99", "error_count", "request_count"]
K8sMetricKind = Literal[
    "cpu_nanocores", "mem_bytes", "restarts",
    "replicas_ready", "replicas_desired",
    "cpu_requests", "mem_requests",
]


@runtime_checkable
class DatadogSource(Protocol):
    """Minimal surface slacheck needs from Datadog (raw responses)."""

    def service_dependencies(self) -> dict:
        """Map of ``{service: {"calls": [downstream, ...]}}`` (APM service map)."""
        ...

    def metric_series(self, kind: MetricKind) -> dict:
        """Raw timeseries response: ``{"series": [{"scope": "service:X", "pointlist": [...]}]}``."""
        ...

    def k8s_metric_series(self, kind: K8sMetricKind) -> dict:
        """Raw k8s resource timeseries grouped by kube_deployment (scope ``kube_deployment:X``)."""
        ...

    def list_slos(self) -> dict:
        """Raw GET /api/v1/slo response (reference only)."""
        ...


def get_source(
    kind: SourceKind,
    settings: Settings | None = None,
    topology: Path | None = None,
    metrics_from: Literal["live", "fixture"] = "fixture",
) -> DatadogSource:
    """Factory for a DatadogSource.

    - ``fixture``: offline, replays fixtures/datadog/*.json (default for dev).
    - ``live``: real Datadog API (needs credentials).
    - ``declared``: edges from a hand-written ``topology`` YAML (the APM stand-in while
      trace ingestion is blocked), with metrics delegated to ``metrics_from`` (live/fixture).
    """
    if kind == "fixture":
        from slacheck.datadog.fixture_client import FixtureClient

        return FixtureClient()

    if kind == "live":
        from slacheck.datadog.live_client import LiveClient

        settings = settings or Settings()
        if not settings.has_credentials:
            raise RuntimeError(
                "Live source requires DD_API_KEY and DD_APP_KEY. Copy .env.example -> .env "
                "(see docs/datadog_api_catalog.md 'Access checklist')."
            )
        return LiveClient(settings)

    if kind == "declared":
        from slacheck.datadog.declared_client import DeclaredClient

        if topology is None:
            raise ValueError("declared source requires a topology YAML path")
        inner = get_source(metrics_from, settings)
        return DeclaredClient(topology, inner)

    raise ValueError(f"unknown source kind: {kind!r}")
