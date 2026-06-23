"""compute_envelope over the paper's 3-component series path."""

import pytest

from slacheck.envelope.aggregate import compute_envelope
from slacheck.models import Component, SloValues


def test_envelope_matches_paper(paper_scenario):
    env = compute_envelope(paper_scenario["components"])
    assert env.availability_pct == pytest.approx(99.7)
    assert env.response_time_ms == 14.0  # max(10, 14, 12)
    assert env.cost_eur_h == pytest.approx(23.0)  # 8 + 6 + 9
    assert env.path == ["UI", "Auth", "Stor"]


def test_envelope_skips_missing_cost():
    # Datadog's common case: no per-service cost -> cost_eur_h is None, not fabricated.
    path = [
        Component(name="a", slo=SloValues(response_time_ms=5, availability_pct=99.95)),
        Component(name="b", slo=SloValues(response_time_ms=8, availability_pct=99.95)),
    ]
    env = compute_envelope(path)
    assert env.cost_eur_h is None
    assert env.availability_pct == pytest.approx(99.9)
    assert env.response_time_ms == 8.0


def test_empty_path_raises():
    with pytest.raises(ValueError):
        compute_envelope([])
