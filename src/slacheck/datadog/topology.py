"""Parse the raw service-dependency map into directed edges."""

from __future__ import annotations


def parse_edges(deps: dict) -> list[tuple[str, str]]:
    """``{service: {"calls": [callee, ...]}}`` -> list of ``(caller, callee)`` edges.

    Every service mentioned (as a key or a callee) becomes a node via these edges;
    isolated services with no calls still appear as graph nodes (added in builder.py).
    """
    edges: list[tuple[str, str]] = []
    for caller, info in deps.items():
        for callee in info.get("calls", []):
            edges.append((caller, callee))
    return edges


def parse_services(deps: dict) -> set[str]:
    """All service names appearing as a caller or a callee."""
    names: set[str] = set(deps.keys())
    for info in deps.values():
        names.update(info.get("calls", []))
    return names
