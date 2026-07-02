"""Unconstructed detection rate: faults drawn independently of the method boundary (paper §V-C).

The headline realistic dataset places each fault inside the window that only weighted decomposition
covers. To answer "what if the fault is NOT engineered to be weighted-only?", this study draws the
victim cost from a log-normal perturbation around the uniform threshold (mode="indep" in
gen_realistic_eval.py), independent of the [weighted, uniform] window, keeping only scenarios where
a genuine over-commitment exists. It then reports each method's detection rate.

This rate is lower than the windowed headline by construction — and that is the point: it is an
honest, non-constructed measurement of how the two decompositions compare when the fault location
is not chosen to favour either one. Weighted still dominates because its threshold is never looser
than uniform, but the gap reflects the natural fault distribution rather than the discriminating
window.

Reproduce offline (no credentials):
    python scripts/indep_study.py            # default N=200
    python scripts/indep_study.py 400
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_realistic_eval import generate  # noqa: E402

from slacheck.eval.runner import run_eval  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
INDEP_SUBDIR = "eval_realistic_indep"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run(n: int = 200) -> tuple[int, int, int]:
    """Returns (n_written, uniform_detected, weighted_detected)."""
    written, _ = generate(n, mode="indep", out_subdir=INDEP_SUBDIR)
    ds = REPO / "fixtures" / INDEP_SUBDIR
    v1 = run_eval(ds, "v1")
    v2 = run_eval(ds, "v2")
    return written, v1.detected("sub_slo"), v2.detected("sub_slo")


def main(n: int) -> None:
    written, d1, d2 = run(n)
    lo1, hi1 = wilson_ci(d1, written)
    lo2, hi2 = wilson_ci(d2, written)
    print(f"=== Independent-distribution population: {written} Sub-SLO scenarios ===\n")
    print(f"  uniform decomposition:  {d1}/{written} = {100*d1/written:.1f}%  "
          f"[95% CI {100*lo1:.1f}-{100*hi1:.1f}%]")
    print(f"  weighted decomposition: {d2}/{written} = {100*d2/written:.1f}%  "
          f"[95% CI {100*lo2:.1f}-{100*hi2:.1f}%]")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    main(n)
