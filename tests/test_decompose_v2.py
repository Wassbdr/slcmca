"""Structural-weight decomposition: the headline paper §III-C worked numbers."""

import pytest

from slacheck.envelope.decompose import decompose as decompose_v1
from slacheck.envelope.v2.decompose_v2 import decompose_v2, structural_weights
from slacheck.models import SloValues


def test_structural_weights_match_paper(paper_scenario_v2):
    w = structural_weights(paper_scenario_v2["graph"])
    # indeg(UI)=0, indeg(Auth)=indeg(Stor)=1 → wUI=1/5, wAuth=wStor=2/5
    assert w["UI"] == pytest.approx(1 / 5)
    assert w["Auth"] == pytest.approx(2 / 5)
    assert w["Stor"] == pytest.approx(2 / 5)


def test_cost_thresholds_match_paper(paper_scenario_v2):
    thresholds = decompose_v2(SloValues(cost_eur_h=23.0), paper_scenario_v2["graph"])
    by = {t.component: t.required.cost_eur_h for t in thresholds}
    assert by["UI"] == pytest.approx(4.6)
    assert by["Auth"] == pytest.approx(9.2)
    assert by["Stor"] == pytest.approx(9.2)


def test_weighted_differs_from_uniform():
    # v1 uniform gives 23/3 ≈ 7.67 for every component; v2 weighting differentiates them.
    uniform = decompose_v1(SloValues(cost_eur_h=23.0), ["UI", "Auth", "Stor"])
    assert uniform[0].required.cost_eur_h == pytest.approx(23 / 3)


def test_availability_weighted_budget(paper_scenario_v2):
    thresholds = decompose_v2(SloValues(availability_pct=99.999), paper_scenario_v2["graph"])
    by = {t.component: t.required.availability_pct for t in thresholds}
    # sAuth = 100 − wAuth·(100−99.999) = 100 − 0.4·0.001
    assert by["Auth"] == pytest.approx(100 - 0.4 * 0.001)
