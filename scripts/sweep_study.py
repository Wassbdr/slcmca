"""Sweep the injected-fault position across the discriminating window (paper §VI-C, honesty check).

The headline realistic result (weighted vs uniform decomposition) injects each fault at the MIDDLE
of the window [weighted_threshold, uniform_threshold]. A fair reviewer will ask whether the
separation is an artefact of that single choice. This script sweeps the position pos across (0,1)
and reports, at each position, the detection rate of both methods over a fresh population.

We sweep pos beyond [0,1] so the victim cost moves THROUGH both thresholds, where the window is
[weighted, uniform] and cost = weighted + pos*(uniform - weighted):
  - pos < 0 : cost below the (strict) weighted threshold  -> NO over-commitment, neither detects;
  - 0 < pos < 1 : cost inside the window  -> only weighted detects (the discriminating regime);
  - pos > 1 : cost above the (lenient) uniform threshold  -> BOTH detect.
This traces the full discrimination curve: uniform stays at the floor until the fault grows past
its own lenient threshold, then catches up; weighted catches the fault as soon as it exceeds the
structurally-correct threshold. The headline 89.5% is one slice (the window) of this picture, and
the curve shows the separation is a genuine threshold effect, not a single constructed point.

Reproduce offline (no credentials):
    python scripts/sweep_study.py            # default N=200 per position
    python scripts/sweep_study.py 400
"""

from __future__ import annotations

import sys
from pathlib import Path

from gen_realistic_eval import generate  # noqa: E402  (sibling script)

from slacheck.eval.runner import run_eval

REPO = Path(__file__).resolve().parents[1]
SWEEP_SUBDIR = "eval_realistic_sweep"
# Sweep THROUGH both thresholds: <0 below weighted (no fault), (0,1) inside window (v2-only),
# >1 above uniform (both detect). This shows the full threshold-crossing behaviour.
POSITIONS = [-0.5, -0.2, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

sys.path.insert(0, str(Path(__file__).resolve().parent))  # import sibling gen_realistic_eval


def run(n: int = 200) -> list[tuple[float, int, int, int]]:
    """Returns [(pos, n, uniform_detected, weighted_detected), ...]."""
    rows: list[tuple[float, int, int, int]] = []
    for pos in POSITIONS:
        written, _ = generate(n, pos=pos, mode="window", out_subdir=SWEEP_SUBDIR)
        ds = REPO / "fixtures" / SWEEP_SUBDIR
        v1 = run_eval(ds, "v1")
        v2 = run_eval(ds, "v2")
        rows.append((pos, written, v1.detected("sub_slo"), v2.detected("sub_slo")))
    return rows


def main(n: int) -> None:
    rows = run(n)
    print(f"=== Position sweep over the discriminating window (N={n} per position) ===\n")
    print(f"{'pos':>5}{'n':>6}{'uniform':>10}{'weighted':>10}")
    for pos, nn, d1, d2 in rows:
        print(f"{pos:>5.1f}{nn:>6}{100*d1/nn:>9.1f}%{100*d2/nn:>9.1f}%")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    main(n)
