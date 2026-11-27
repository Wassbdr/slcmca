import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from slacheck.cli import app
from slacheck.graph.trace_import import TraceSource, load_trace_graph

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "hotrod.otlp.json"


def test_public_otlp_sample_imports_from_cli():
    imported = CliRunner().invoke(app, ["import-trace", str(EXAMPLE), "--source", "otlp"])
    assert imported.exit_code == 0, imported.output
    topology = yaml.safe_load(imported.stdout)
    assert topology["entrypoint"] == "frontend"
    assert {(edge["source"], edge["target"]) for edge in topology["edges"]} == {
        ("frontend", "customer"), ("frontend", "driver"), ("frontend", "route"),
        ("customer", "mysql"), ("driver", "redis"),
    }
    assert all(service["slo"]["availability_pct"] is None for service in topology["components"])


def test_jaeger_resolves_children_on_the_same_trace(tmp_path):
    path = tmp_path / "jaeger.json"
    path.write_text(json.dumps({"data": [{
        "traceID": "t",
        "processes": {"p1": {"serviceName": "web"}, "p2": {"serviceName": "db"}},
        "spans": [
            {"spanID": "child", "processID": "p2", "references": [
                {"refType": "CHILD_OF", "spanID": "root", "traceID": "t"},
            ]},
            {"spanID": "root", "processID": "p1"},
        ],
    }]}))
    graph = load_trace_graph(path, TraceSource.jaeger)
    assert graph.entrypoint == "web"
    assert [(edge.source, edge.target) for edge in graph.edges] == [("web", "db")]


@pytest.mark.parametrize("export", [
    'traces_service_graph_request_total{connection_type="database",client="web",server="db"} 7\n'
    'traces_service_graph_request_total{client="db",server="other"} 0\n',
    json.dumps({"status": "success", "data": {"resultType": "matrix", "result": [
        {"metric": {"client": "web", "server": "db"}, "values": [[1, "0"], [2, "7"]]},
        {"metric": {"client": "db", "server": "other"}, "values": [[1, "0"]]},
    ]}}),
])
def test_tempo_only_imports_positive_observed_edges(tmp_path, export):
    path = tmp_path / "tempo"
    path.write_text(export)
    graph = load_trace_graph(path, TraceSource.tempo)
    assert set(graph.components) == {"web", "db"}
    assert graph.entrypoint == "web"
    assert graph.edges[0].edge_type == "conjunctive"


def test_rejects_cycles_and_ambiguous_roots(tmp_path):
    path = tmp_path / "tempo"
    first = 'traces_service_graph_request_total{client="web",server="db"} 2\n'
    path.write_text(first + 'traces_service_graph_request_total{client="db",server="web"} 2\n')
    with pytest.raises(ValueError, match="cycle"):
        load_trace_graph(path, TraceSource.tempo, "web")
    path.write_text(first + 'traces_service_graph_request_total{client="job",server="db"} 2\n')
    with pytest.raises(ValueError, match="--entrypoint"):
        load_trace_graph(path, TraceSource.tempo)
    assert set(load_trace_graph(path, TraceSource.tempo, "web").components) == {"web", "db"}
