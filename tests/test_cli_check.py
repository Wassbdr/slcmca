"""CLI smoke tests for `slacheck check` and `slacheck eval` (output layer only)."""

from pathlib import Path

from typer.testing import CliRunner

from slacheck.cli import app

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_shop_example_flags_payment_at_three_nines():
    r = runner.invoke(app, [
        "check", str(REPO / "examples" / "shop.yaml"), "--slo", "99.9", "--method", "v2",
    ])
    assert r.exit_code == 1
    assert "[descending/availability] payment" in r.output
    assert "[ascending/availability]" in r.output


def test_shop_example_passes_a_reachable_target():
    r = runner.invoke(app, [
        "check", str(REPO / "examples" / "shop.yaml"), "--slo", "99.5", "--paper-version", "v2",
    ])
    assert r.exit_code == 0
    assert "No over-commitment faults" in r.output


def test_shop_example_defaults_to_exact_availability():
    r = runner.invoke(app, ["check", str(REPO / "examples" / "shop.yaml"), "--slo", "99.9"])
    assert r.exit_code == 0
    assert "Achievable: 99.9150209983%" in r.output
    assert "Feasible" in r.output


def test_reconfig_scenario_missed_by_v1_caught_by_v2():
    path = REPO / "fixtures" / "eval" / "reconfig" / "reconfig_01.yaml"
    r = runner.invoke(app, ["check", str(path), "--both"])
    v1, v2 = r.output.split("=== v2 ===")
    assert "No over-commitment faults" in v1
    assert "[descending/reconfiguration] autoscale_1" in v2
    assert r.exit_code == 1


def test_eval_both_prints_totals():
    r = runner.invoke(app, ["eval", "--both"])
    assert r.exit_code == 0
    totals = [line.split()[-2:] for line in r.output.splitlines() if line.startswith("Total")]
    assert totals == [["113", "67"], ["113", "113"]]


def test_eval_refuses_an_empty_dataset(tmp_path):
    r = runner.invoke(app, ["eval", "--dataset", str(tmp_path)])
    assert r.exit_code == 2


def test_eval_default_dataset_has_all_scenarios() -> None:
    # Checkout fixtures (editable) or the packaged copy (pip install .): same 113 files.
    from slacheck import cli

    assert len(list(cli._EVAL_DATASET.glob("*/*.yaml"))) == 113
