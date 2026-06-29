"""Declared-topology source: edges from YAML, metrics delegated to an inner source."""

from pathlib import Path

import pytest

from slacheck.datadog.declared_client import DeclaredClient
from slacheck.datadog.fixture_client import FixtureClient
from slacheck.datadog.source import get_source
from slacheck.pipeline import analyze

REPO = Path(__file__).resolve().parents[1]
TT_TOPOLOGY = REPO / "fixtures" / "topology" / "train-ticket.yaml"


def _write(tmp_path, text):
    p = tmp_path / "topo.yaml"
    p.write_text(text)
    return p


def test_edges_come_from_yaml(tmp_path):
    topo = _write(
        tmp_path,
        "entrypoint: a\ndependencies:\n  a: [b, c]\n  b: [c]\n",
    )
    src = DeclaredClient(topo, FixtureClient())
    deps = src.service_dependencies()
    assert deps["a"]["calls"] == ["b", "c"]
    assert deps["b"]["calls"] == ["c"]
    assert deps["c"]["calls"] == []  # callee with no outgoing edges still appears


def test_metrics_delegated_to_inner_source(tmp_path):
    topo = _write(tmp_path, "entrypoint: a\ndependencies:\n  a: [b]\n")
    inner = FixtureClient()
    src = DeclaredClient(topo, inner)
    # delegation: same payload the inner source returns
    assert src.metric_series("latency_p99") == inner.metric_series("latency_p99")
    assert src.k8s_metric_series("cpu_nanocores") == inner.k8s_metric_series("cpu_nanocores")


def test_factory_requires_topology():
    with pytest.raises(ValueError, match="requires a topology"):
        get_source("declared")


def test_train_ticket_topology_is_valid_and_analyzable():
    # the bundled train-ticket topology drives the full pipeline with fixture metrics
    src = get_source("declared", topology=TT_TOPOLOGY, metrics_from="fixture")
    deps = src.service_dependencies()
    assert "ts-ui-dashboard" in deps
    assert "ts-travel-service" in deps["ts-ui-dashboard"]["calls"]
    # v1 pipeline runs end to end (metrics may be sparse from fixtures; topology is the point)
    result = analyze(src, "ts-ui-dashboard", "availability")
    assert result.verdict.envelope.path  # non-empty critical path
