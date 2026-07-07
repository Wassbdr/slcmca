"""Read-only inventory of everything slacheck can extract from a Datadog org.

Backs ``slacheck explore``. Each section pairs a thin fetcher (lazy SDK imports,
raw dicts out — same convention as live_client.py) with a pure summarizer that is
unit-testable offline. Sections fail soft: a missing scope or empty org yields a
section with ``ok=False`` and a hint, never a crash of the whole report.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from slacheck.config import Settings

_SAMPLE_CAP = 10  # max example items printed per section


@dataclass
class Section:
    """One block of the inventory report."""

    title: str
    ok: bool
    lines: list[str] = field(default_factory=list)
    error: str | None = None
    raw: Any = None  # payload behind the summary, for --json


# ------------------------------------------------------------------ summarizers (pure)


def summarize_dependencies(deps: dict) -> list[str]:
    """APM service map: counts, hubs (in/out-degree), isolated services."""
    edges = [(caller, callee) for caller, info in deps.items()
             for callee in (info or {}).get("calls", []) or []]
    out_deg = Counter(caller for caller, _ in edges)
    in_deg = Counter(callee for _, callee in edges)
    isolated = sorted(s for s in deps if not out_deg.get(s) and not in_deg.get(s))

    lines = [f"{len(deps)} services, {len(edges)} dependency edges"]
    if out_deg:
        top = ", ".join(f"{s} ({n})" for s, n in out_deg.most_common(5))
        lines.append(f"top callers (out-degree): {top}")
    if in_deg:
        top = ", ".join(f"{s} ({n})" for s, n in in_deg.most_common(5))
        lines.append(f"most depended-on (in-degree): {top}")
    if isolated:
        sample = ", ".join(isolated[:_SAMPLE_CAP])
        more = "…" if len(isolated) > _SAMPLE_CAP else ""
        lines.append(f"{len(isolated)} isolated services (no edges): {sample}{more}")
    return lines


def summarize_metric_names(names: list[str]) -> list[str]:
    """Group active metric names into families (first two dotted segments), never dump raw."""
    families = Counter(".".join(n.split(".")[:2]) for n in names)
    lines = [f"{len(names)} active metrics in {len(families)} families"]
    top = ", ".join(f"{fam} ({n})" for fam, n in families.most_common(_SAMPLE_CAP))
    if top:
        lines.append(f"largest families: {top}")
    trace_fams = sorted(f for f in families if f.startswith("trace."))
    if trace_fams:
        lines.append(
            "APM trace stats present: " + ", ".join(trace_fams)
            + "  (candidate DD_TRACE_STAT values)"
        )
    return lines


def summarize_slos(raw: dict) -> list[str]:
    """Existing SLOs: name, type, primary target."""
    slos = raw.get("data", []) or []
    lines = [f"{len(slos)} SLOs declared in the org"]
    for slo in slos[:_SAMPLE_CAP]:
        thresholds = slo.get("thresholds") or []
        target = thresholds[0].get("target") if thresholds else None
        target_s = f"{target}% / {thresholds[0].get('timeframe')}" if target else "no threshold"
        lines.append(f"- {slo.get('name', '?')} [{slo.get('type', '?')}] target {target_s}")
    if len(slos) > _SAMPLE_CAP:
        lines.append(f"… and {len(slos) - _SAMPLE_CAP} more")
    return lines


def summarize_monitors(monitors: list[dict]) -> list[str]:
    """Monitors: counts by type and alert state, plus a sample."""
    lines = [f"{len(monitors)} monitors"]
    by_type = Counter(m.get("type", "?") for m in monitors)
    by_state = Counter(str(m.get("overall_state", "?")) for m in monitors)
    if by_type:
        lines.append("by type: " + ", ".join(f"{t} ({n})" for t, n in by_type.most_common()))
    if by_state:
        lines.append("by state: " + ", ".join(f"{s} ({n})" for s, n in by_state.most_common()))
    for m in monitors[:_SAMPLE_CAP]:
        lines.append(f"- {m.get('name', '?')} [{m.get('overall_state', '?')}]")
    if len(monitors) > _SAMPLE_CAP:
        lines.append(f"… and {len(monitors) - _SAMPLE_CAP} more")
    return lines


def summarize_dashboards(raw: dict) -> list[str]:
    """Dashboards: count + titles, flagging the ones slacheck published."""
    dashboards = raw.get("dashboards", []) or []
    ours = [d for d in dashboards if str(d.get("title", "")).startswith("slacheck")]
    lines = [f"{len(dashboards)} dashboards ({len(ours)} published by slacheck)"]
    for d in dashboards[:_SAMPLE_CAP]:
        marker = "  <- slacheck" if d in ours else ""
        lines.append(f"- {d.get('title', '?')}{marker}")
    if len(dashboards) > _SAMPLE_CAP:
        lines.append(f"… and {len(dashboards) - _SAMPLE_CAP} more")
    return lines


def summarize_catalog(
    entities: list[dict], relations: list[dict], apm_services: set[str] | None = None
) -> list[str]:
    """Software Catalog: declared entities/relations vs the discovered APM topology."""
    names = {
        str(((e.get("attributes") or {}).get("name")) or "").strip()
        for e in entities
    } - {""}
    lines = [f"{len(entities)} declared entities, {len(relations)} dependsOn relations"]
    if apm_services is not None:
        declared_only = sorted(names - apm_services)
        apm_only = sorted(apm_services - names)
        lines.append(
            f"declared but not seen in APM: {len(declared_only)}; "
            f"seen in APM but not declared: {len(apm_only)}"
        )
    return lines


def summarize_hosts(raw: dict) -> list[str]:
    return [f"hosts up: {raw.get('total_up', '?')}, down: {raw.get('total_down', '?')}"]


# ------------------------------------------------------------------ fetchers (thin, lazy SDK)


def _fetch_validate(settings: Settings) -> dict:
    from slacheck.datadog.live_client import LiveClient

    return {"valid": LiveClient(settings).validate()}


def _fetch_dependencies(settings: Settings) -> dict:
    from slacheck.datadog.live_client import LiveClient

    return LiveClient(settings).service_dependencies()


def _fetch_active_metrics(settings: Settings, window_hours: int) -> list[str]:
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.metrics_api import MetricsApi

    from slacheck.datadog.live_client import build_config

    now = int(time.time())
    with ApiClient(build_config(settings)) as client:
        resp = MetricsApi(client).list_active_metrics(_from=now - window_hours * 3600)
    return [str(m) for m in getattr(resp, "metrics", []) or []]


def _fetch_slos(settings: Settings) -> dict:
    from slacheck.datadog.live_client import LiveClient

    return LiveClient(settings).list_slos()


def _fetch_monitors(settings: Settings) -> list[dict]:
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.monitors_api import MonitorsApi

    from slacheck.datadog.live_client import build_config

    with ApiClient(build_config(settings)) as client:
        resp = MonitorsApi(client).list_monitors()
    return [m.to_dict() for m in resp]


def _fetch_dashboards(settings: Settings) -> dict:
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.dashboards_api import DashboardsApi

    from slacheck.datadog.live_client import build_config

    with ApiClient(build_config(settings)) as client:
        resp = DashboardsApi(client).list_dashboards()
    return resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)


def _fetch_catalog(settings: Settings) -> tuple[list[dict], list[dict]]:
    from datadog_api_client import ApiClient
    from datadog_api_client.v2.api.software_catalog_api import SoftwareCatalogApi
    from datadog_api_client.v2.model.relation_type import RelationType

    from slacheck.datadog.live_client import build_config

    with ApiClient(build_config(settings)) as client:
        api = SoftwareCatalogApi(client)
        entities = api.list_catalog_entity()
        relations = api.list_catalog_relation(
            filter_type=RelationType.RELATIONTYPEDEPENDSON
        )

    def to_dicts(resp: Any) -> list[dict]:
        return [
            d.to_dict() if hasattr(d, "to_dict") else dict(d)
            for d in getattr(resp, "data", []) or []
        ]

    return to_dicts(entities), to_dicts(relations)


def _fetch_host_totals(settings: Settings) -> dict:
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.hosts_api import HostsApi

    from slacheck.datadog.live_client import build_config

    with ApiClient(build_config(settings)) as client:
        resp = HostsApi(client).get_host_totals()
    return resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)


# ------------------------------------------------------------------ orchestration


def _fmt_error(exc: Exception) -> str:
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    msg = f"{type(exc).__name__}: {first_line}"
    if "403" in msg or "Forbidden" in msg:
        msg += "  (missing app-key scope? see docs/datadog_api_catalog.md, app-key scopes)"
    return msg


def run_inventory(settings: Settings | None = None, window_hours: int = 24) -> list[Section]:
    """Query every read API slacheck knows about; one fail-soft Section per API."""
    settings = settings or Settings()
    sections: list[Section] = []

    def add(title: str, fetch: Callable[[], Any], summarize: Callable[[Any], list[str]]) -> Any:
        try:
            raw = fetch()
            lines = summarize(raw)
        except Exception as exc:  # noqa: BLE001 — inventory-what-you-can, report the rest
            sections.append(Section(title=title, ok=False, error=_fmt_error(exc)))
            return None
        sections.append(Section(title=title, ok=True, lines=lines, raw=raw))
        return raw

    add(
        "Auth & org",
        lambda: _fetch_validate(settings),
        lambda _: [f"site={settings.site}  env={settings.env}", "credentials valid"],
    )
    deps = add(
        "APM services & dependencies",
        lambda: _fetch_dependencies(settings),
        summarize_dependencies,
    )
    add(
        f"Active metrics (last {window_hours}h)",
        lambda: _fetch_active_metrics(settings, window_hours),
        summarize_metric_names,
    )
    add("SLOs", lambda: _fetch_slos(settings), summarize_slos)
    add("Monitors", lambda: _fetch_monitors(settings), summarize_monitors)
    add("Dashboards", lambda: _fetch_dashboards(settings), summarize_dashboards)
    apm_services = set(deps) if isinstance(deps, dict) else None

    def fetch_catalog() -> dict:
        entities, relations = _fetch_catalog(settings)
        return {"entities": entities, "relations": relations}

    add(
        "Software Catalog",
        fetch_catalog,
        lambda raw: summarize_catalog(raw["entities"], raw["relations"], apm_services),
    )
    add("Hosts", lambda: _fetch_host_totals(settings), summarize_hosts)
    return sections


def format_report(sections: list[Section]) -> str:
    """Render the inventory as plain console text."""
    blocks: list[str] = []
    for s in sections:
        header = f"== {s.title} =="
        if s.ok:
            body = "\n".join(f"  {line}" for line in s.lines)
        else:
            body = f"  !! {s.error}"
        blocks.append(f"{header}\n{body}")
    ok_count = sum(1 for s in sections if s.ok)
    blocks.append(f"{ok_count}/{len(sections)} sections available.")
    return "\n\n".join(blocks)
