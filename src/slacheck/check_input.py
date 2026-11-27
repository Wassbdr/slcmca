"""Load the part of a declared topology needed for an availability check."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from slacheck.availability import AvailabilityTopology

_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _mapping(value: Any, key: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"set {key} to a mapping.")
    return value


def _list(value: Any, key: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"set {key} to a list.")
    return value


def _name(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"set {key} to a service name.")
    return value


def _availability(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            return float(value)
        except (ValueError, OverflowError):
            pass
    raise ValueError(f"set {key} to an availability percentage.")


def load_check_input(path: Path) -> tuple[AvailabilityTopology, float | None]:
    with path.open(encoding="utf-8") as source:
        raw = _mapping(yaml.load(source, Loader=_LOADER), "the topology")
    entrypoint = _name(raw.get("entrypoint"), "entrypoint")
    availability = {}
    for item in _list(raw.get("components"), "components"):
        component = _mapping(item, "each component")
        name = _name(component.get("name"), "component.name")
        if name in availability:
            raise ValueError(f"declare service {name!r} only once.")
        slo = _mapping(component.get("slo", {}), f"{name}.slo")
        availability[name] = _availability(slo.get("availability_pct"), f"{name}.availability_pct")
    edges = []
    incoming: dict[str, str] = {}
    for item in _list(raw.get("edges", []), "edges"):
        edge = _mapping(item, "each edge")
        a = _name(edge.get("source"), "edge.source")
        b = _name(edge.get("target"), "edge.target")
        kind = edge.get("edge_type", "conjunctive")
        if kind not in ("conjunctive", "disjunctive"):
            raise ValueError(f"set edge {a!r} to {b!r} to conjunctive or disjunctive.")
        if incoming.setdefault(b, kind) != kind:
            raise ValueError(f"use one dependency type for all edges into {b!r}.")
        edges.append((a, b, kind))
    target = raw.get("global_target")
    value = None if target is None else _mapping(target, "global_target").get("availability_pct")
    return AvailabilityTopology(entrypoint, availability, edges), _availability(value, "target")
