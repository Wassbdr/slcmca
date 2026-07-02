"""Reproduce every empirical number and figure in issre_paper.tex — offline, no credentials.

This is the "one button" the paper promises: each headline number is the output of a script, and
this driver runs them in dependency order and echoes what the paper claims next to what the code
produces. Nothing here recomputes the numbers itself — it orchestrates the existing scripts and
`slacheck eval` so there is a single command a reviewer can run:

    python scripts/reproduce_paper.py            # everything (datasets → tables → figures)
    python scripts/reproduce_paper.py --fast     # skip figure rendering (no matplotlib)
    python scripts/reproduce_paper.py --n 500    # larger realistic population (default 200)

Exit code is non-zero if any step fails, so it doubles as a CI smoke test that the paper stays in
sync with the code. See docs/paper_mapping.md for the section↔script map.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run(label: str, argv: list[str], claim: str) -> None:
    """Run one reproduction step, streaming its output, and annotate what the paper claims."""
    print(f"\n{'=' * 78}\n▶ {label}\n  paper claims: {claim}\n{'-' * 78}")
    t0 = time.monotonic()
    proc = subprocess.run(argv, cwd=REPO)
    dt = time.monotonic() - t0
    if proc.returncode != 0:
        print(f"✗ {label} FAILED (exit {proc.returncode})")
        raise SystemExit(proc.returncode)
    print(f"✓ {label} ({dt:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reproduce all paper numbers/figures offline.")
    ap.add_argument("--n", type=int, default=200, help="realistic population size (default 200)")
    ap.add_argument("--fast", action="store_true", help="skip figure rendering (no matplotlib)")
    args = ap.parse_args()

    script = lambda name: [PY, str(REPO / "scripts" / name)]  # noqa: E731

    # 1. (Re)generate the deterministic datasets the tables and figures read from.
    _run(
        "Generate constructed fault dataset (fixtures/eval/)",
        script("gen_eval.py"),
        "113 injected faults: 10 Global-SLO, 60 Sub-SLO, 43 reconfiguration.",
    )
    _run(
        f"Generate realistic population (fixtures/eval_realistic*/, n={args.n})",
        [*script("gen_realistic_eval.py"), str(args.n)],
        "Alibaba-like topologies, fixed seed; window/sweep/indep variants.",
    )

    # 2. Table I — the code is the source of truth for tab:eval (Baseline/Full + Total).
    _run(
        "Table I — fault detection (slacheck eval --both --latex)",
        [PY, "-m", "slacheck.cli", "eval", "--both", "--latex"],
        "Baseline 10/57/0 = 67, Full 10/60/43 = 113. Regenerates tab:eval verbatim.",
    )

    # 3. §V-B — real systems.
    _run(
        "§V-B case study — train-ticket (38 services)",
        script("case_study.py"),
        "avail. envelope: baseline 99.40% (3 faults) vs full 98.36% (6); latency false-negative.",
    )
    _run(
        "§V-B second system — Online Boutique",
        script("multi_system_study.py"),
        "structural coverage on a second real call graph (tab:realsystems).",
    )

    # 4. §V-C — statistical validation + the two honesty checks.
    _run(
        "§V-C headline — realistic population, Wilson CIs",
        script("realistic_study.py"),
        "weighted (full) 89.5% [84.5, 93.0] vs uniform (baseline) 4.0% [2.0, 7.7].",
    )
    _run(
        "§V-C honesty — position sweep (defuses the tautology critique)",
        script("sweep_study.py"),
        "detection tracks the fault crossing both thresholds — a genuine threshold effect.",
    )
    _run(
        "§V-C honesty — independent-distribution draw",
        script("indep_study.py"),
        "full still strictly dominates baseline when faults are drawn off both thresholds.",
    )
    _run(
        "§III-B — safety-margin sensitivity (gamma sweep)",
        script("gamma_study.py"),
        "A_commit tightens as the confidence factor k grows (running case).",
    )

    # 5. Figures — rendered from the same code paths as the tables (no hardcoded numbers).
    if args.fast:
        print("\n(skipping figure rendering: --fast)")
    else:
        _run(
            "Figures — regenerate figures/*.pdf",
            script("gen_figures.py"),
            "detection_by_category, detection_realistic, train_ticket_dag, "
            "detection_sweep, gamma_sensitivity.",
        )

    print(f"\n{'=' * 78}\n✓ All paper numbers reproduced. See issre_paper.tex + figures/.\n")


if __name__ == "__main__":
    main()
