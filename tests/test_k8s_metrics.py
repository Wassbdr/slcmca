"""Kubernetes resource enrichment: collect_k8s_metrics + graph builder attaches resources."""

import pytest

from slacheck.datadog.fixture_client import FixtureClient
from slacheck.datadog.metrics import collect_k8s_metrics
from slacheck.graph.builder import build_graph


@pytest.fixture
def k8s():
    return collect_k8s_metrics(FixtureClient())


def test_collects_resources_by_deployment(k8s):
    assert "ts-travel-service" in k8s
    rt = k8s["ts-travel-service"]
    # last point of cpu fixture is 47000000 nanocores; mem 512MB; restarts 3
    assert rt.cpu_nanocores == pytest.approx(47000000.0)
    assert rt.mem_bytes == pytest.approx(536870912.0)
    assert rt.restarts == pytest.approx(3.0)


def test_keyed_by_service_name_not_pod(k8s):
    # kube_deployment tag gives the clean service name (no replica suffix)
    assert all("-" in name or name.isalnum() for name in k8s)
    assert "ts-gateway-service" in k8s


def test_graph_builder_attaches_resources():
    g, _ = build_graph(FixtureClient(), entrypoint="ts-gateway-service")
    comp = g.nodes["ts-travel-service"]["component"]
    assert comp.resources.restarts == pytest.approx(3.0)
    assert comp.resources.cpu_nanocores == pytest.approx(47000000.0)


def test_missing_k8s_fixture_is_graceful(tmp_path):
    # a source with no k8s fixtures returns empty, not an error
    client = FixtureClient(fixtures_dir=tmp_path)
    assert client.k8s_metric_series("cpu_nanocores") == {"series": []}
