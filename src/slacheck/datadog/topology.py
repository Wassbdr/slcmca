"""Parse the raw service-dependency map into directed edges."""

from __future__ import annotations

from collections.abc import Sequence


def filter_deps(
    deps: dict,
    include_prefix: str | None = None,
    include: Sequence[str] | None = None,
    exclude_contains: str | None = None,
) -> dict:
    """Restrict a raw dependency map to the services under study.

    A live APM map contains every service in the org (infra, other apps); this keeps only
    the relevant ones and prunes edges pointing outside the kept set, so the graph is the
    app, not the whole cluster.

    - ``include_prefix``: keep services whose name starts with this (e.g. ``"ts-"``).
    - ``include``: explicit allow-list of service names.
    - ``exclude_contains``: drop services whose name contains this (e.g. ``"with-jaeger"``).

    With no criteria, returns ``deps`` unchanged. A kept callee that has no own entry is
    added as an isolated node so it still appears in the graph.
    """
    if include_prefix is None and include is None and exclude_contains is None:
        return deps

    allow = set(include) if include is not None else None

    def keep(name: str) -> bool:
        if allow is not None and name not in allow:
            return False
        if include_prefix is not None and not name.startswith(include_prefix):
            return False
        if exclude_contains is not None and exclude_contains in name:
            return False
        return True

    out: dict[str, dict] = {}
    for svc, info in deps.items():
        if not keep(svc):
            continue
        out[svc] = {"calls": [c for c in info.get("calls", []) if keep(c)]}
    # ensure kept callees that lacked their own entry appear as isolated nodes
    for info in list(out.values()):
        for callee in info["calls"]:
            out.setdefault(callee, {"calls": []})
    return out


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
