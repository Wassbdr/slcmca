"""Statistical v1-vs-v2 validation on the realistic population (paper §VI-C).

Runs the realistic dataset (scripts/gen_realistic_eval.py — topologies drawn from Alibaba-like
distributions) through both engines and reports, over the whole population:
  - v1 (uniform decomposition) detection rate,
  - v2 (structurally-weighted decomposition) detection rate,
  - a Wilson 95% confidence interval on each rate.

Every scenario injects a Sub-SLO fault on a low-centrality service whose actual cost sits between
the uniform and weighted thresholds — the regime that discriminates the two methods. The headline
is the v2 rate vs the v1 rate on a realistic population, not on a few chosen cases.

Reproduce offline (no credentials):
    python scripts/gen_realistic_eval.py 500      # (re)generate, fixed seed
    python scripts/realistic_study.py
"""

from __future__ import annotations

import math
from pathlib import Path

from slacheck.eval.runner import run_eval

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "fixtures" / "eval_realistic"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> None:
    if not (DATASET / "sub_slo").is_dir() or not any((DATASET / "sub_slo").glob("*.yaml")):
        raise SystemExit(
            "No realistic dataset found. Run: python scripts/gen_realistic_eval.py 500"
        )

    v1 = run_eval(DATASET, "v1")
    v2 = run_eval(DATASET, "v2")
    inj = v2.injected("sub_slo")
    d1, d2 = v1.detected("sub_slo"), v2.detected("sub_slo")
    lo1, hi1 = wilson_ci(d1, inj)
    lo2, hi2 = wilson_ci(d2, inj)

    print(f"=== Realistic population: {inj} Sub-SLO scenarios "
          "(Alibaba-like topologies, fixed seed) ===\n")
    print(f"  v1 (uniform decomposition):  {d1}/{inj} = {100*d1/inj:.1f}%  "
          f"[95% CI {100*lo1:.1f}–{100*hi1:.1f}%]")
    print(f"  v2 (weighted decomposition): {d2}/{inj} = {100*d2/inj:.1f}%  "
          f"[95% CI {100*lo2:.1f}–{100*hi2:.1f}%]")
    print(f"  v2 advantage: +{d2 - d1} scenarios "
          f"({100*(d2 - d1)/inj:.1f} pp of the population)\n")

    print("LaTeX:")
    print("\\begin{table}[htbp]")
    print("\\caption{Statistical validation on a realistic population of "
          f"{inj} Sub-SLO scenarios (Alibaba-like topologies).}}")
    print("\\begin{center}")
    print("\\begin{tabular}{|l|c|c|}")
    print("\\hline")
    print("\\textbf{Method} & \\textbf{Detection rate} & \\textbf{95\\% CI} \\\\")
    print("\\hline")
    print(f"v1 (uniform)  & {100*d1/inj:.1f}\\% & [{100*lo1:.1f}, {100*hi1:.1f}] \\\\")
    print(f"v2 (weighted) & {100*d2/inj:.1f}\\% & [{100*lo2:.1f}, {100*hi2:.1f}] \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\label{tab:realistic}")
    print("\\end{center}")
    print("\\end{table}")


if __name__ == "__main__":
    main()
