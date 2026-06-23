"""Live DatadogSource over datadog-api-client v2 (Phase 3).

This is the only module that talks to the real API. It is import-safe without the
``datadog`` extra installed: the SDK is imported lazily inside methods, so the offline
fixture pipeline never requires it. Wire-up is sketched against the documented endpoints
in docs/datadog_api_catalog.md; validate the exact response shapes with `slacheck record`
once credentials arrive, then refresh fixtures/datadog/*.json from the real responses.
"""

from __future__ import annotations

import time
from typing import Literal

from slacheck.config import Settings

# Metric queries per service-tag template. {svc} filled per service, but Datadog
# returns all matching series in one call when grouped by service, so we query once
# with a group-by and parse by scope (see metrics._last_value_by_service).
_QUERIES = {
    "latency_p99": "p99:trace.http.request.duration{*} by {service}",
    "error_count": "sum:trace.http.request.errors{*} by {service}.as_count()",
    "request_count": "sum:trace.http.request.hits{*} by {service}.as_count()",
}


class LiveClient:
    """Talks to the real Datadog API. Requires the ``datadog`` extra and credentials."""

    def __init__(self, settings: Settings, window_seconds: int = 3600) -> None:
        self._settings = settings
        self._window = window_seconds
        self._config = self._build_config(settings)

    @staticmethod
    def _build_config(settings: Settings):
        from datadog_api_client import Configuration

        config = Configuration()
        config.api_key["apiKeyAuth"] = settings.api_key
        config.api_key["appKeyAuth"] = settings.app_key
        config.server_variables["site"] = settings.site
        return config

    def service_dependencies(self) -> dict:
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.service_dependencies_api import ServiceDependenciesApi

        with ApiClient(self._config) as client:
            api = ServiceDependenciesApi(client)
            resp = api.list_service_dependencies(env=self._settings.env)
        # resp maps service -> object with .calls; normalize to plain dict
        return {
            svc: {"calls": list(getattr(v, "calls", []) or [])}
            for svc, v in dict(resp).items()
        }

    def metric_series(self, kind: Literal["latency_p99", "error_count", "request_count"]) -> dict:
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.metrics_api import MetricsApi

        now = int(time.time())
        with ApiClient(self._config) as client:
            api = MetricsApi(client)
            resp = api.query_metrics(
                _from=now - self._window, to=now, query=_QUERIES[kind]
            )
        # normalize SDK model to the {"series": [{"scope", "pointlist"}]} shape we parse
        series = []
        for s in resp.get("series", []) or []:
            series.append(
                {
                    "scope": s.get("scope", ""),
                    "pointlist": [list(p) for p in (s.get("pointlist", []) or [])],
                }
            )
        return {"series": series}

    def list_slos(self) -> dict:
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.service_level_objectives_api import (
            ServiceLevelObjectivesApi,
        )

        with ApiClient(self._config) as client:
            api = ServiceLevelObjectivesApi(client)
            resp = api.list_slos()
        return resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
