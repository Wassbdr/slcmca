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
# The metric namespace is the APM "trace.<integration>.request" stat. For the Java/Spring
# train-ticket app the integration is the servlet container, so the stat is
# ``trace.servlet.request`` (its duration is the base metric, NOT a ``.duration`` suffix).
# Other runtimes expose ``trace.http.request`` etc. — override DD_TRACE_STAT to switch.
# p99 latency is returned in SECONDS by Datadog; metrics.py converts to ms.
_QUERIES = {
    "latency_p99": "p99:trace.servlet.request{*} by {service}",
    "error_count": "sum:trace.servlet.request.errors{*} by {service}.as_count()",
    "request_count": "sum:trace.servlet.request.hits{*} by {service}.as_count()",
}

# Kubernetes resource metrics, grouped by kube_deployment (== service name for ts-*).
# {ns} is filled with the namespace filter at call time. Available without APM.
_K8S_QUERIES = {
    "cpu_nanocores": "avg:kubernetes.cpu.usage.total{{{ns}}} by {{kube_deployment}}",
    "mem_bytes": "avg:kubernetes.memory.usage{{{ns}}} by {{kube_deployment}}",
    "restarts": "sum:kubernetes.containers.restarts{{{ns}}} by {{kube_deployment}}",
    # deployment readiness → availability proxy when APM trace metrics are unavailable
    "replicas_ready": (
        "sum:kubernetes_state.deployment.replicas_ready{{{ns}}} by {{kube_deployment}}"
    ),
    "replicas_desired": (
        "sum:kubernetes_state.deployment.replicas_desired{{{ns}}} by {{kube_deployment}}"
    ),
    # reserved resources → cost model (cores, bytes)
    "cpu_requests": "sum:kubernetes.cpu.requests{{{ns}}} by {{kube_deployment}}",
    "mem_requests": "sum:kubernetes.memory.requests{{{ns}}} by {{kube_deployment}}",
}

_K8sKind = Literal[
    "cpu_nanocores", "mem_bytes", "restarts",
    "replicas_ready", "replicas_desired",
    "cpu_requests", "mem_requests",
]


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

        # call_api does NOT auto-attach auth (the SDK applies it inside generated API
        # methods, not here), so we set the Datadog auth headers explicitly.
        with ApiClient(self._config) as client:
            raw: Any = client.call_api(
                resource_path="/api/v1/service_dependencies",
                method="GET",
                query_params=[("env", self._settings.env)],
                header_params={
                    "Accept": "application/json",
                    "DD-API-KEY": self._settings.api_key,
                    "DD-APPLICATION-KEY": self._settings.app_key,
                },
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
    def _query(self, query: str) -> dict:
        """Run a timeseries query, normalize to {"series":[{"scope","pointlist"}]}."""
        from datadog_api_client import ApiClient
        from datadog_api_client.v1.api.metrics_api import MetricsApi

        now = int(time.time())
        with ApiClient(self._config) as client:
            resp = MetricsApi(client).query_metrics(
                _from=now - self._window, to=now, query=query
            )
        # resp.series is a list of MetricsQueryMetadata models; read attributes, not .get().
        # Each pointlist item is a Point model whose .value is the [timestamp, value] pair.
        series = []
        for s in getattr(resp, "series", []) or []:
            scope = getattr(s, "scope", "") or ""
            points = []
            for p in getattr(s, "pointlist", []) or []:
                pair = getattr(p, "value", None)
                if pair is not None:
                    points.append([float(pair[0]), pair[1]])
            series.append({"scope": scope, "pointlist": points})
        return {"series": series}

    def metric_series(self, kind: Literal["latency_p99", "error_count", "request_count"]) -> dict:
        series = self._query(_QUERIES[kind])
        if kind == "latency_p99":
            # Datadog returns trace duration in SECONDS; the model expects milliseconds
            # (fixtures are already in ms — convert only here, at the live edge).
            series = {
                "series": [
                    {
                        "scope": s["scope"],
                        "pointlist": [
                            [t, (v * 1000.0 if v is not None else None)]
                            for t, v in s["pointlist"]
                        ],
                    }
                    for s in series["series"]
                ]
            }
        return series

    def k8s_metric_series(self, kind: _K8sKind) -> dict:
        """Kubernetes resource metric grouped by kube_deployment, scoped to DD_K8S_NAMESPACE."""
        ns_filter = f"kube_namespace:{self._settings.k8s_namespace}"
        return self._query(_K8S_QUERIES[kind].format(ns=ns_filter))

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
