"""Live DatadogSource over datadog-api-client v2 (Phase 3).

This is the only module that talks to the real API. It is import-safe without the
``datadog`` extra installed: the SDK is imported lazily inside methods, so the offline
fixture pipeline never requires it.

Note on the APM Service Map: ``datadog-api-client`` 2.x does NOT codegen a
``service_dependencies_api``, so the runtime topology endpoint
(``GET /api/v1/service_dependencies``) is called via the SDK's low-level ``call_api``.
If that endpoint is unavailable, we fall back to declared Software Catalog ``dependsOn``
relations. Validate exact shapes with ``slacheck record`` and refresh fixtures.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from slacheck.config import Settings

# One grouped query per metric family; we parse the per-service series by scope tag.
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

    # ------------------------------------------------------------------ validate
    def validate(self) -> bool:
        """Hit GET /api/v1/validate to confirm the API key + site are accepted."""
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.authentication_api import AuthenticationApi

        with ApiClient(self._config) as client:
            resp = AuthenticationApi(client).validate()
        return bool(getattr(resp, "valid", False))

    # ------------------------------------------------------------- topology
    def service_dependencies(self) -> dict:
        """Runtime APM service map, normalized to ``{svc: {"calls": [...]}}``.

        Tries the un-codegen'd ``/api/v1/service_dependencies`` first; on any failure
        falls back to declared Software Catalog dependencies.
        """
        try:
            return self._service_dependencies_apm()
        except Exception:  # noqa: BLE001 — fall back to declared deps on any API error
            return self._service_dependencies_catalog()

    def _service_dependencies_apm(self) -> dict:
        from datadog_api_client import ApiClient

        with ApiClient(self._config) as client:
            raw: Any = client.call_api(
                resource_path="/api/v1/service_dependencies",
                method="GET",
                query_params=[("env", self._settings.env)],
                header_params={"Accept": "application/json"},
                response_type=(dict,),
                return_http_data_only=True,
            )
        # raw maps service -> {"calls": [...]} already; normalize defensively
        return {
            svc: {"calls": list((info or {}).get("calls", []) or [])}
            for svc, info in dict(raw).items()
        }

    def _service_dependencies_catalog(self) -> dict:
        """Declared dependsOn relations from the Software Catalog (v2)."""
        from datadog_api_client import ApiClient
        from datadog_api_client.v2.api.software_catalog_api import SoftwareCatalogApi
        from datadog_api_client.v2.model.relation_type import RelationType

        deps: dict[str, dict] = {}
        with ApiClient(self._config) as client:
            api = SoftwareCatalogApi(client)
            resp = api.list_catalog_relation(filter_type=RelationType.RELATIONTYPEDEPENDSON)
        for rel in getattr(resp, "data", []) or []:
            attrs = getattr(rel, "attributes", None)
            from_ref = getattr(attrs, "from_ref", None) if attrs else None
            to_ref = getattr(attrs, "to_ref", None) if attrs else None
            if not from_ref or not to_ref:
                continue
            caller = _strip_ref(from_ref)
            callee = _strip_ref(to_ref)
            deps.setdefault(caller, {"calls": []})["calls"].append(callee)
            deps.setdefault(callee, {"calls": []})
        return deps

    # ------------------------------------------------------------- metrics
    def metric_series(self, kind: Literal["latency_p99", "error_count", "request_count"]) -> dict:
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.metrics_api import MetricsApi

        now = int(time.time())
        with ApiClient(self._config) as client:
            api = MetricsApi(client)
            resp = api.query_metrics(_from=now - self._window, to=now, query=_QUERIES[kind])

        # resp.series is a list of MetricsQueryMetadata models; read attributes, not .get()
        series = []
        for s in getattr(resp, "series", []) or []:
            scope = getattr(s, "scope", "") or ""
            pointlist = getattr(s, "pointlist", []) or []
            series.append({"scope": scope, "pointlist": [list(p) for p in pointlist]})
        return {"series": series}

    # --------------------------------------------------------------- slos
    def list_slos(self) -> dict:
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.service_level_objectives_api import (
            ServiceLevelObjectivesApi,
        )

        with ApiClient(self._config) as client:
            resp = ServiceLevelObjectivesApi(client).list_slos()
        return resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)


def _strip_ref(ref: str) -> str:
    """Catalog refs look like ``service:ts-auth-service`` -> ``ts-auth-service``."""
    return ref.split(":", 1)[1] if ":" in ref else ref
