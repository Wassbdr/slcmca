"""Reproduce the paper's evaluation Table I and the v1→v2 Sub-SLO improvement (57→60)."""

from pathlib import Path

from slacheck.eval.runner import run_eval

DATASET = Path(__file__).resolve().parents[1] / "fixtures" / "eval"


def test_v2_detects_all():
    r = run_eval(DATASET, "v2")
    assert r.by_category["global_slo"] == (10, 10)
    assert r.by_category["sub_slo"] == (60, 60)
    assert r.by_category["reconfig"] == (43, 43)


def test_v1_misses_three_sub_slo_and_all_reconfig():
    r = run_eval(DATASET, "v1")
    assert r.by_category["global_slo"] == (10, 10)
    assert r.by_category["sub_slo"] == (60, 57)  # the paper's headline number
    assert r.by_category["reconfig"] == (43, 0)  # v1 has no reconfiguration model


def test_the_three_missed_are_the_heterogeneous_gap_cases():
    r = run_eval(DATASET, "v1")
    sub_missed = [m for m in r.missed if m.startswith("sub_")]
    assert sorted(sub_missed) == ["sub_gap_01", "sub_gap_02", "sub_gap_03"]


def test_weighted_decomposition_closes_the_gap():
    v1 = run_eval(DATASET, "v1")
    v2 = run_eval(DATASET, "v2")
    assert v2.detected("sub_slo") - v1.detected("sub_slo") == 3


def test_latex_table_is_paper_ready():
    from slacheck.eval.runner import format_latex

    latex = format_latex(run_eval(DATASET, "v1"), run_eval(DATASET, "v2"))
    assert "\\begin{table}" in latex and "\\end{table}" in latex
    # the headline rows: v1 57 vs v2 60 Sub-SLO, v1 0 vs v2 43 reconfig
    assert "Sub-SLO Inconsistencies & 60 & 57 & 60" in latex
    assert "Reconfiguration Inconsistencies & 43 & 0 & 43" in latex
