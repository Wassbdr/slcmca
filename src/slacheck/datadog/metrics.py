"""Convert raw Datadog timeseries into per-service SLO values (paper Sub-SLOs).

Conversions (see docs/datadog_api_catalog.md §2):
    response_time_ms = p99 trace duration (fixtures are already in ms)
    availability_pct = (1 - errors/requests) * 100   (request-success proxy, not uptime)
    request_count    = total hits (availability denominator + critical-path tie-breaker)
"""

from __future__ import annotations

from slacheck.datadog.source import DatadogSource
from slacheck.models import SloValues

_SERVICE_TAG = "service:"


def _last_value_by_service(series_response: dict) -> dict[str, float]:
    """Reduce a {"series": [...]} response to {service_name: last_point_value}."""
    out: dict[str, float] = {}
    for s in series_response.get("series", []):
        scope = s.get("scope", "")
        key = next(
            (
                tag.strip()[len(_SERVICE_TAG) :]
                for tag in scope.split(",")
                if tag.strip().startswith(_SERVICE_TAG)
            ),
            None,
        )
        points = s.get("pointlist", [])
        if key is None or not points:
            continue
        # pointlist is [[epoch_ms, value], ...]; take the most recent non-null value
        for _, value in reversed(points):
            if value is not None:
                out[key] = float(value)
                break
    return out


def collect_slo_values(source: DatadogSource) -> dict[str, SloValues]:
    """Pull the three metric families and assemble per-service SloValues + raw sample.

    Returns ``{service: (SloValues, sample_dict)}`` flattened to ``{service: SloValues}``;
    use :func:`collect_with_samples` if the raw counters are needed for traceability.
    """
    return {name: vals for name, (vals, _) in collect_with_samples(source).items()}


def collect_with_samples(source: DatadogSource) -> dict[str, tuple[SloValues, dict]]:
    """Like :func:`collect_slo_values` but also returns the raw request/error counters."""
    latency = _last_value_by_service(source.metric_series("latency_p99"))
    errors = _last_value_by_service(source.metric_series("error_count"))
    requests = _last_value_by_service(source.metric_series("request_count"))

    services = set(latency) | set(errors) | set(requests)
    result: dict[str, tuple[SloValues, dict]] = {}
    for svc in services:
        req = requests.get(svc)
        err = errors.get(svc)
        availability = None
        if req is not None and req > 0 and err is not None:
            availability = (1.0 - err / req) * 100.0

        sample = {"request_count": req, "error_count": err}
        result[svc] = (
            SloValues(
                response_time_ms=latency.get(svc),
                availability_pct=availability,
                cost_eur_h=None,  # Datadog gap — see catalog §5
            ),
            sample,
        )
    return result
