"""LiveClient converts APM trace duration (seconds) to milliseconds; other metrics pass through.

Datadog returns ``trace.servlet.request`` p99 in SECONDS, but the model's ``response_time_ms``
is in milliseconds (fixtures are already in ms). The conversion must happen only at the live
edge, only for latency, and must tolerate null points (gaps in the series).
"""

from __future__ import annotations

from slacheck.datadog.live_client import LiveClient


def _client_with_query(stub_series: dict) -> LiveClient:
    """Build a LiveClient without touching the SDK, stubbing the raw query."""
    client = LiveClient.__new__(LiveClient)  # bypass __init__ (no creds/SDK needed)
    client._query = lambda query: stub_series  # type: ignore[attr-defined]
    return client


def test_latency_seconds_converted_to_ms():
    raw = {"series": [{"scope": "service:ts-auth-service", "pointlist": [[0.0, 1.2], [1.0, 0.9]]}]}
    out = _client_with_query(raw).metric_series("latency_p99")
    assert out["series"][0]["pointlist"] == [[0.0, 1200.0], [1.0, 900.0]]


def test_latency_tolerates_null_points():
    raw = {"series": [{"scope": "service:ts-x", "pointlist": [[0.0, None], [1.0, 2.5]]}]}
    out = _client_with_query(raw).metric_series("latency_p99")
    assert out["series"][0]["pointlist"] == [[0.0, None], [1.0, 2500.0]]


def test_request_count_not_scaled():
    raw = {"series": [{"scope": "service:ts-x", "pointlist": [[0.0, 42.0]]}]}
    out = _client_with_query(raw).metric_series("request_count")
    assert out["series"][0]["pointlist"] == [[0.0, 42.0]]
