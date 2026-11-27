"""Over-commitment fault detection: the paper's headline ascending fault and more."""

import pytest

from slacheck.envelope.faults import detect_ascending, detect_descending, evaluate
from slacheck.models import Component, Envelope, SloValues, Threshold


def test_paper_ascending_availability_fault(paper_scenario):
    # 99.999% target vs 99.7% achievable envelope -> one ascending availability fault.
    verdict = evaluate(paper_scenario["components"], paper_scenario["global_target"])
    asc_avail = [
        f for f in verdict.faults if f.direction == "ascending" and f.metric == "availability"
    ]
    assert len(asc_avail) == 1
    assert asc_avail[0].target == pytest.approx(99.999)
    assert asc_avail[0].achievable == pytest.approx(99.7)
    assert not verdict.feasible


def test_no_fault_when_target_within_envelope(paper_scenario):
    # Latency target 18 ms vs achievable 14 ms -> NOT a fault (18 >= 14).
    verdict = evaluate(paper_scenario["components"], paper_scenario["global_target"])
    asc_latency = [
        f for f in verdict.faults if f.direction == "ascending" and f.metric == "response_time"
    ]
    assert asc_latency == []


def test_ascending_latency_fault():
    env = Envelope(response_time_ms=14.0, availability_pct=99.7)
    faults = detect_ascending(SloValues(response_time_ms=10.0), env)
    assert len(faults) == 1
    assert faults[0].metric == "response_time"


def test_descending_fault_when_component_short():
    comps = [Component(name="db", slo=SloValues(availability_pct=99.5))]
    thresholds = [Threshold(component="db", required=SloValues(availability_pct=99.9))]
    faults = detect_descending(comps, thresholds)
    assert len(faults) == 1
    assert faults[0].component == "db"
    assert faults[0].metric == "availability"


def test_evaluate_without_target_reports_envelope_only(paper_scenario):
    verdict = evaluate(paper_scenario["components"])
    assert verdict.faults == []
    assert verdict.feasible
    assert verdict.envelope.availability_pct == pytest.approx(99.7)


def test_evaluate_notes_cost_gap():
    comps = [Component(name="a", slo=SloValues(availability_pct=99.9, response_time_ms=5))]
    verdict = evaluate(comps)
    assert any("Cost data unavailable" in n for n in verdict.notes)
