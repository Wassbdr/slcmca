"""Dashboard JSON structure (offline, no network)."""

import json

import pytest

from slacheck.dashboard.builder import build_dashboard
from slacheck.datadog.fixture_client import FixtureClient
from slacheck.models import SloValues
from slacheck.pipeline import analyze


@pytest.fixture
def result_feasible():
    return analyze(FixtureClient(), "ts-gateway-service", "availability")


@pytest.fixture
def result_overcommitted():
    # demand 99.99% availability, which the ~99.25% envelope cannot meet
    target = SloValues(availability_pct=99.99)
    return analyze(FixtureClient(), "ts-gateway-service", "availability", target=target)


def test_dashboard_has_expected_structure(result_feasible):
    dash = build_dashboard(result_feasible)
    assert dash["title"].startswith("slacheck")
    assert dash["layout_type"] == "ordered"
    titles = [w["definition"].get("title") for w in dash["widgets"]]
    assert "Critical Path" in titles
    assert "Over-Commitment Faults" in titles


def test_critical_path_group_has_one_widget_per_service(result_feasible):
    dash = build_dashboard(result_feasible)
    group = next(w for w in dash["widgets"] if w["definition"].get("title") == "Critical Path")
    n_services = len(result_feasible.verdict.envelope.path)
    assert len(group["definition"]["widgets"]) == n_services


def test_overcommitted_dashboard_is_red_with_fault_notes(result_overcommitted):
    dash = build_dashboard(result_overcommitted)
    verdict_note = dash["widgets"][0]["definition"]
    assert verdict_note["background_color"] == "red"
    faults = next(
        w for w in dash["widgets"] if w["definition"].get("title") == "Over-Commitment Faults"
    )
    fault_widgets = faults["definition"]["widgets"]
    assert any(fw["definition"]["background_color"] == "red" for fw in fault_widgets)


def test_dashboard_is_json_serializable(result_feasible):
    json.dumps(build_dashboard(result_feasible))  # must not raise
