"""The live/fixture seam. Everything downstream depends only on this protocol.

A ``DatadogSource`` returns *raw* Datadog-shaped data; parsing into slacheck models
happens in topology.py / metrics.py so the same parsers run on live and fixture data.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from slacheck.config import Settings

SourceKind = Literal["fixture", "live"]


@runtime_checkable
class DatadogSource(Protocol):
    """Minimal surface slacheck needs from Datadog (raw responses)."""

    def service_dependencies(self) -> dict:
        """Map of ``{service: {"calls": [downstream, ...]}}`` (APM service map)."""
        ...

    def metric_series(self, kind: Literal["latency_p99", "error_count", "request_count"]) -> dict:
        """Raw timeseries response: ``{"series": [{"scope": "service:X", "pointlist": [...]}]}``."""
        ...

    def list_slos(self) -> dict:
        """Raw GET /api/v1/slo response (reference only)."""
        ...


def get_source(kind: SourceKind, settings: Settings | None = None) -> DatadogSource:
    """Factory: ``fixture`` (offline, default for dev) or ``live`` (needs credentials)."""
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

    raise ValueError(f"unknown source kind: {kind!r}")
