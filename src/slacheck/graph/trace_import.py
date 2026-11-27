"""Convert exported trace and service graph data into declared dependencies."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from slacheck.models import Component, DependencyEdge, DependencyGraph, SloValues

_REQUESTS = "traces_service_graph_request_total"
_SAMPLE = re.compile(r'traces_service_graph_request_total\{(.*)\}\s+(\S+)(?:\s.*)?')
_LABEL = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*")')


class TraceSource(str, Enum):
    otlp = "otlp"
    jaeger = "jaeger"
    tempo = "tempo"


SpanKey = tuple[str, str]
Span = tuple[SpanKey, str, tuple[SpanKey, ...]]
Link = tuple[str, str]


def _otlp(document: dict) -> Iterable[Span]:
    for resource in document["resourceSpans"]:
        attributes = resource.get("resource", {}).get("attributes", [])
        service = next((
            item["value"]["stringValue"] for item in attributes if item["key"] == "service.name"
        ), None)
        if not service:
            continue
        for scope in resource.get("scopeSpans", []):
            for span in scope["spans"]:
                trace = span["traceId"]
                parent = span.get("parentSpanId")
                yield (trace, span["spanId"]), service, ((trace, parent),) if parent else ()


def _jaeger(document: dict) -> Iterable[Span]:
    for trace in document["data"]:
        for span in trace["spans"]:
            service = trace["processes"][span["processID"]]["serviceName"]
            trace_id = span.get("traceID", trace["traceID"])
            parents = tuple(
                (ref["traceID"], ref["spanID"])
                for ref in span.get("references", []) if ref["refType"] == "CHILD_OF"
                and ref["traceID"] == trace_id
            )
            yield (trace_id, span["spanID"]), service, parents


def _trace_links(spans: Iterable[Span]) -> tuple[set[str], set[Link]]:
    index: dict[SpanKey, tuple[str, tuple[SpanKey, ...]]] = {}
    for key, service, parents in spans:
        if key in index and index[key] != (service, parents):
            raise ValueError("duplicate span ID with conflicting data; export complete traces.")
        if service:
            index[key] = (service, parents)
    services = {service for service, _ in index.values()}
    links = {
        (index[parent][0], service)
        for service, parents in index.values()
        for parent in parents
        if parent in index and index[parent][0] != service
    }
    return services, links


def _prometheus_json(data: str) -> Iterable[tuple[dict[str, str], float]]:
    document = json.loads(data)
    if document.get("status") != "success":
        raise ValueError("export a successful Prometheus vector or matrix response.")
    for item in document["data"]["result"]:
        labels = item["metric"]
        if labels.get("__name__", _REQUESTS) != _REQUESTS:
            continue
        if "values" in item:
            values = (float(value) for _, value in item["values"])
            yield labels, max((value for value in values if math.isfinite(value)), default=0)
        else:
            yield labels, float(item["value"][1])


def _prometheus_text(data: str) -> Iterable[tuple[dict[str, str], float]]:
    for raw in data.splitlines():
        line = raw.strip()
        if not line.startswith(f"{_REQUESTS}{{"):
            continue
        sample = _SAMPLE.fullmatch(line)
        if sample is None:
            raise ValueError(f"invalid sample for {_REQUESTS}; export Prometheus text or JSON.")
        labels, value = sample.groups()
        yield {key: json.loads(label) for key, label in _LABEL.findall(labels)}, float(value)


def load_trace_graph(
    path: Path, source: TraceSource, entrypoint: str | None = None,
) -> DependencyGraph:
    """Load a trace export as a typed graph without guessing availabilities or redundancy."""
    text = path.read_text(encoding="utf-8")
    try:
        if source is TraceSource.tempo:
            decode = _prometheus_json if text.lstrip().startswith("{") else _prometheus_text
            links = {
                (labels["client"], labels["server"])
                for labels, value in decode(text)
                if math.isfinite(value) and value > 0
                and labels.get("client") and labels.get("server")
                and labels["client"] != labels["server"]
            }
            services = {name for pair in links for name in pair}
        else:
            document = json.loads(text)
            services, links = _trace_links(
                _otlp(document) if source is TraceSource.otlp else _jaeger(document)
            )
    except (TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ValueError(f"unexpected {source.value} export structure; check --source.") from exc
    if not services:
        raise ValueError(f"no services found; export {source.value} data with service names.")
    names = ", ".join(sorted(services))
    if entrypoint is None:
        roots = sorted(services - {callee for _, callee in links})
        if len(roots) != 1:
            raise ValueError(f"pass --entrypoint; observed services: {names}.")
        entrypoint = roots[0]
    if entrypoint not in services:
        raise ValueError(f"choose an observed --entrypoint: {names}.")

    children: dict[str, list[str]] = {name: [] for name in services}
    for caller, callee in sorted(links):
        children[caller].append(callee)
    reachable: set[str] = set()
    pending = [entrypoint]
    while pending:
        service = pending.pop()
        if service not in reachable:
            reachable.add(service)
            pending.extend(children[service])
    try:
        return DependencyGraph(
            components={
                name: Component(name=name, slo=SloValues()) for name in sorted(reachable)
            },
            edges=[
                DependencyEdge(source=caller, target=callee)
                for caller, callee in sorted(links) if caller in reachable
            ],
            entrypoint=entrypoint,
        )
    except ValueError as exc:
        raise ValueError(
            "reachable service calls form a cycle; export a narrower trace scope or "
            "remove feedback edges from the source."
        ) from exc
