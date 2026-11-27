"""Offline DatadogSource: replays fixtures/datadog/*.json. Implements DatadogSource."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from slacheck.datadog.source import K8sMetricKind

_REPO_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "datadog"
# Source checkout (editable install) first; for a regular `pip install .` fall back to ./fixtures.
_FIXTURES = _REPO_FIXTURES if _REPO_FIXTURES.is_dir() else Path.cwd() / "fixtures" / "datadog"

_METRIC_FILES = {
    "latency_p99": "metrics_latency_p99.json",
    "error_count": "metrics_error_rate.json",
    "request_count": "metrics_request_rate.json",
}

_K8S_FILES = {
    "cpu_nanocores": "k8s_cpu_nanocores.json",
    "mem_bytes": "k8s_mem_bytes.json",
    "restarts": "k8s_restarts.json",
    "replicas_ready": "k8s_replicas_ready.json",
    "replicas_desired": "k8s_replicas_desired.json",
    "cpu_requests": "k8s_cpu_requests.json",
    "mem_requests": "k8s_mem_requests.json",
}


class FixtureClient:
    """Reads recorded JSON. The whole pipeline runs on this with no credentials."""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or _FIXTURES

    def _load(self, name: str) -> dict:
        return json.loads((self._dir / name).read_text())

    def service_dependencies(self) -> dict:
        data = self._load("service_dependencies.json")
        # tolerate a leading "_comment" key in hand-authored fixtures
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def metric_series(self, kind: Literal["latency_p99", "error_count", "request_count"]) -> dict:
        return self._load(_METRIC_FILES[kind])

    def k8s_metric_series(self, kind: K8sMetricKind) -> dict:
        path = self._dir / _K8S_FILES[kind]
        if not path.exists():  # k8s enrichment is optional in offline fixtures
            return {"series": []}
        return json.loads(path.read_text())

    def list_slos(self) -> dict:
        return self._load("slo_list.json")
