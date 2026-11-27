"""Read an availability objective from OpenSLO v1 YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class OpenSloTarget:
    service: str
    availability_pct: float


def load_openslo_target(path: Path, name: str | None = None) -> OpenSloTarget:
    """Read one occurrence-based SLO and its service reference from an OpenSLO bundle."""
    with path.open(encoding="utf-8") as source:
        documents = [doc for doc in yaml.safe_load_all(source) if doc is not None]
    services: set[str] = set()
    slos: dict[str, dict] = {}
    for doc in documents:
        if not isinstance(doc, dict) or doc.get("apiVersion") != "openslo/v1":
            raise ValueError("use OpenSLO documents with apiVersion: openslo/v1.")
        kind = doc.get("kind")
        if kind not in ("SLO", "Service"):
            continue
        metadata, spec = doc.get("metadata"), doc.get("spec")
        key = metadata.get("name") if isinstance(metadata, dict) else None
        if not isinstance(key, str) or not key:
            raise ValueError(f"set metadata.name on each OpenSLO {kind}.")
        if kind == "Service":
            services.add(key)
        elif key in slos:
            raise ValueError(f"keep only one OpenSLO SLO named {key!r}.")
        elif isinstance(spec, dict):
            slos[key] = spec
        else:
            raise ValueError(f"set spec on OpenSLO SLO {key!r}.")
    if not slos:
        raise ValueError("include an OpenSLO SLO document.")
    if name is None:
        if len(slos) != 1:
            raise ValueError("select one OpenSLO SLO with --slo-name.")
        name = next(iter(slos))
    if name not in slos:
        raise ValueError(f"select an existing SLO with --slo-name: {', '.join(slos)}.")

    spec = slos[name]
    service = spec.get("service")
    if not isinstance(service, str) or not service:
        raise ValueError(f"set spec.service on OpenSLO SLO {name!r}.")
    if services and service not in services:
        raise ValueError(f"include an OpenSLO Service named {service!r} or fix spec.service.")
    if spec.get("budgetingMethod") != "Occurrences":
        raise ValueError("use budgetingMethod: Occurrences for request availability.")
    objectives = spec.get("objectives")
    if not (
        isinstance(objectives, list) and len(objectives) == 1 and isinstance(objectives[0], dict)
    ):
        raise ValueError("set exactly one request availability objective in spec.objectives.")
    objective = objectives[0]
    target = objective.get("target")
    if (
        "op" in objective or "value" in objective
        or not isinstance(target, (int, float)) or isinstance(target, bool)
        or not 0 < target <= 1
    ):
        raise ValueError("set the availability objective target as a fraction, such as 0.999.")
    return OpenSloTarget(service, 100 * target)
