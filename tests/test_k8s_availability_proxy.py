"""Kubernetes availability proxy: availability ≈ replicas_ready / replicas_desired.

A live signal usable when APM trace metrics are unavailable. It is a deployment-readiness
proxy (how many replicas serve vs are desired), NOT a true request-success or uptime SLO.
"""

import pytest

from slacheck.datadog.metrics import k8s_availability_proxy


class _StubSource:
    """Returns fixed k8s series for the two readiness metrics."""

    def __init__(self, ready: dict[str, float], desired: dict[str, float]):
        self._ready = ready
        self._desired = desired

    def _series(self, values):
        return {
            "series": [
                {
                    "scope": f"kube_deployment:{name},kube_namespace:tt-slacheck",
                    "pointlist": [[1700000060000, v]],
                }
                for name, v in values.items()
            ]
        }

    def k8s_metric_series(self, kind):
        if kind == "replicas_ready":
            return self._series(self._ready)
        if kind == "replicas_desired":
            return self._series(self._desired)
        return {"series": []}


def test_full_readiness_is_100():
    src = _StubSource(ready={"ts-a": 3.0}, desired={"ts-a": 3.0})
    proxy = k8s_availability_proxy(src)
    assert proxy["ts-a"] == pytest.approx(100.0)


def test_partial_readiness_is_proportional():
    src = _StubSource(ready={"ts-a": 1.0}, desired={"ts-a": 2.0})
    assert k8s_availability_proxy(src)["ts-a"] == pytest.approx(50.0)


def test_zero_desired_is_skipped():
    # a deployment scaled to 0 yields no proxy value (not a division-by-zero or 0%)
    src = _StubSource(ready={"ts-a": 0.0}, desired={"ts-a": 0.0})
    assert "ts-a" not in k8s_availability_proxy(src)


def test_missing_desired_is_skipped():
    src = _StubSource(ready={"ts-a": 1.0}, desired={})
    assert "ts-a" not in k8s_availability_proxy(src)
