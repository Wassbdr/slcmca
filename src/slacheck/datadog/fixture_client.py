"""Offline DatadogSource: replays fixtures/datadog/*.json. Implements DatadogSource."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "datadog"

_METRIC_FILES = {
    "latency_p99": "metrics_latency_p99.json",
    "error_count": "metrics_error_rate.json",
    "request_count": "metrics_request_rate.json",
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

    def list_slos(self) -> dict:
        return self._load("slo_list.json")
