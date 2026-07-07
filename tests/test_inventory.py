"""Inventory summarizers and report rendering (offline — no SDK, no network)."""

from unittest.mock import patch

from slacheck.datadog.inventory import (
    Section,
    format_report,
    run_inventory,
    summarize_catalog,
    summarize_dashboards,
    summarize_dependencies,
    summarize_metric_names,
    summarize_monitors,
    summarize_slos,
)


def test_summarize_dependencies_counts_and_hubs():
    deps = {
        "gw": {"calls": ["a", "b"]},
        "a": {"calls": ["b"]},
        "b": {"calls": []},
        "lonely": {"calls": []},
    }
    lines = summarize_dependencies(deps)
    assert lines[0] == "4 services, 3 dependency edges"
    assert any("gw (2)" in line for line in lines)  # top caller
    assert any("b (2)" in line for line in lines)  # most depended-on
    assert any("lonely" in line and "isolated" in line for line in lines)


def test_summarize_metric_names_groups_and_caps():
    names = [f"system.cpu.metric{i}" for i in range(5000)] + [
        "trace.servlet.request",
        "trace.servlet.request.errors",
        "trace.http.request.hits",
    ]
    lines = summarize_metric_names(names)
    assert lines[0].startswith("5003 active metrics")
    # never dumps the raw list: whole summary stays small
    assert len("\n".join(lines)) < 1000
    assert any("system.cpu (5000)" in line for line in lines)
    # trace.* families are surfaced as DD_TRACE_STAT candidates
    assert any("trace.servlet" in line and "DD_TRACE_STAT" in line for line in lines)


def test_summarize_slos_targets():
    raw = {
        "data": [
            {
                "name": "checkout availability",
                "type": "metric",
                "thresholds": [{"target": 99.9, "timeframe": "30d"}],
            },
            {"name": "bare", "type": "monitor", "thresholds": []},
        ]
    }
    lines = summarize_slos(raw)
    assert lines[0] == "2 SLOs declared in the org"
    assert "- checkout availability [metric] target 99.9% / 30d" in lines
    assert "- bare [monitor] target no threshold" in lines


def test_summarize_monitors_states():
    monitors = [
        {"name": "m1", "type": "metric alert", "overall_state": "OK"},
        {"name": "m2", "type": "metric alert", "overall_state": "Alert"},
    ]
    lines = summarize_monitors(monitors)
    assert lines[0] == "2 monitors"
    assert any("metric alert (2)" in line for line in lines)
    assert any("Alert (1)" in line for line in lines)


def test_summarize_dashboards_flags_ours():
    raw = {"dashboards": [{"title": "slacheck — ts-gateway"}, {"title": "team infra"}]}
    lines = summarize_dashboards(raw)
    assert lines[0] == "2 dashboards (1 published by slacheck)"
    assert any("slacheck — ts-gateway" in line and "<- slacheck" in line for line in lines)


def test_summarize_catalog_diffs_against_apm():
    entities = [{"attributes": {"name": "a"}}, {"attributes": {"name": "declared-only"}}]
    lines = summarize_catalog(entities, [], apm_services={"a", "apm-only"})
    assert lines[0] == "2 declared entities, 0 dependsOn relations"
    assert any("declared but not seen in APM: 1" in line for line in lines)
    assert any("seen in APM but not declared: 1" in line for line in lines)


def test_run_inventory_fails_soft_per_section():
    """One failing fetch yields ok=False on its section; the others still render."""
    deps = {"a": {"calls": ["b"]}, "b": {"calls": []}}
    with (
        patch("slacheck.datadog.inventory._fetch_validate", return_value={"valid": True}),
        patch("slacheck.datadog.inventory._fetch_dependencies", return_value=deps),
        patch(
            "slacheck.datadog.inventory._fetch_active_metrics",
            side_effect=RuntimeError("403 Forbidden"),
        ),
        patch("slacheck.datadog.inventory._fetch_slos", return_value={"data": []}),
        patch("slacheck.datadog.inventory._fetch_monitors", return_value=[]),
        patch("slacheck.datadog.inventory._fetch_dashboards", return_value={"dashboards": []}),
        patch("slacheck.datadog.inventory._fetch_catalog", return_value=([], [])),
        patch("slacheck.datadog.inventory._fetch_host_totals", return_value={"total_up": 3}),
    ):
        sections = run_inventory()

    assert len(sections) == 8
    by_title = {s.title: s for s in sections}
    metrics = by_title["Active metrics (last 24h)"]
    assert not metrics.ok
    assert "403 Forbidden" in metrics.error
    assert "scope" in metrics.error  # the 403 hint points at the scopes doc
    assert all(s.ok for t, s in by_title.items() if t != "Active metrics (last 24h)")
    # the catalog diff uses the discovered APM services
    catalog_lines = by_title["Software Catalog"].lines
    assert any("seen in APM but not declared: 2" in line for line in catalog_lines)


def test_format_report_renders_every_section_and_errors():
    sections = [
        Section(title="Good", ok=True, lines=["one", "two"]),
        Section(title="Bad", ok=False, error="ApiException: 403"),
    ]
    report = format_report(sections)
    assert "== Good ==" in report
    assert "  one" in report
    assert "== Bad ==" in report
    assert "!! ApiException: 403" in report
    assert "1/2 sections available." in report
