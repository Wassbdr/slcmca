"""Declared-topology DatadogSource: edges from a hand-written topology.yaml.

This is the pragmatic stand-in for APM while trace ingestion is unavailable. The *call
graph* (which APM normally provides) is declared explicitly in YAML — appropriate for a
well-documented app like train-ticket whose structure is static and known — while the
per-service SLO/resource *metrics* are delegated to an inner source (live or fixture). So
you get real live metrics on a real (declared) topology, with no dependency on trace
ingestion. When APM is unblocked, switch back to ``--source live`` for automatic edges.

topology.yaml shape::

    entrypoint: ts-gateway-service          # informational
    services: [ts-gateway-service, ts-travel-service, ...]   # optional; inferred from edges
    dependencies:                           # caller -> [callees]
      ts-gateway-service: [ts-travel-service, ts-order-service]
      ts-travel-service: [ts-route-service, ts-train-service]
"""

from __future__ import annotations

from pathlib import Path

import yaml

from slacheck.datadog.source import DatadogSource, K8sMetricKind, MetricKind


class DeclaredClient:
    """Edges from a YAML topology; metrics delegated to an inner source."""

    def __init__(self, topology_path: Path, metrics_source: DatadogSource) -> None:
        self._topology = yaml.safe_load(Path(topology_path).read_text()) or {}
        self._metrics = metrics_source

    def service_dependencies(self) -> dict:
        deps = self._topology.get("dependencies", {}) or {}
        out: dict[str, dict] = {}
        for caller, callees in deps.items():
            out.setdefault(caller, {"calls": []})["calls"].extend(callees or [])
            for callee in callees or []:
                out.setdefault(callee, {"calls": []})
        # include any explicitly-listed services with no edges
        for svc in self._topology.get("services", []) or []:
            out.setdefault(svc, {"calls": []})
        return out

    def metric_series(self, kind: MetricKind) -> dict:
        return self._metrics.metric_series(kind)

    def k8s_metric_series(self, kind: K8sMetricKind) -> dict:
        return self._metrics.k8s_metric_series(kind)

    def list_slos(self) -> dict:
        return self._metrics.list_slos()
