"""Kubernetes resource-based cost model: cost ≈ cpu_cores·price_cpu + mem_gb·price_mem.

A transparent per-service cost proxy from reserved k8s resources, usable when Datadog has
no per-microservice cost (Cloud Cost = the cloud bill, not per-service). It is a
resource-reservation estimate, NOT a real invoice.
"""

import pytest

from slacheck.datadog.metrics import k8s_cost_model
from slacheck.models import Pricing


class _StubSource:
    def __init__(self, cpu: dict[str, float], mem: dict[str, float]):
        self._cpu = cpu
        self._mem = mem

    def _series(self, values):
        return {
            "series": [
                {
                    "scope": f"kube_deployment:{n},kube_namespace:tt-slacheck",
                    "pointlist": [[1700000060000, v]],
                }
                for n, v in values.items()
            ]
        }

    def k8s_metric_series(self, kind):
        if kind == "cpu_requests":
            return self._series(self._cpu)
        if kind == "mem_requests":
            return self._series(self._mem)
        return {"series": []}


_PRICING = Pricing(cpu_eur_per_core_h=0.04, mem_eur_per_gb_h=0.005)


def test_cost_combines_cpu_and_memory():
    # 0.5 cores → 0.02 €/h ; 2 GiB → 0.01 €/h ; total 0.03 €/h
    src = _StubSource(cpu={"ts-a": 0.5}, mem={"ts-a": 2 * 1024**3})
    cost = k8s_cost_model(src, _PRICING)
    assert cost["ts-a"] == pytest.approx(0.5 * 0.04 + 2 * 0.005)


def test_cpu_only_when_memory_missing():
    src = _StubSource(cpu={"ts-a": 1.0}, mem={})
    assert k8s_cost_model(src, _PRICING)["ts-a"] == pytest.approx(0.04)


def test_service_with_no_resources_absent():
    src = _StubSource(cpu={}, mem={})
    assert k8s_cost_model(src, _PRICING) == {}


def test_builder_fills_cost_only_when_pricing_given():
    from slacheck.datadog.fixture_client import FixtureClient
    from slacheck.graph.builder import build_graph

    # without pricing → cost stays None (APM/declared cost absent in fixtures)
    g, _ = build_graph(FixtureClient(), entrypoint="ts-gateway-service")
    assert g.nodes["ts-travel-service"]["component"].slo.cost_eur_h is None

    # with pricing → cost estimated from the k8s request fixtures
    g2, _ = build_graph(FixtureClient(), entrypoint="ts-gateway-service", pricing=_PRICING)
    comp = g2.nodes["ts-travel-service"]["component"]
    assert comp.slo.cost_eur_h is not None
    assert comp.sample.get("cost_source") == "k8s_resource_model"
