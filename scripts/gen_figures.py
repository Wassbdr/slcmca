"""Generate the paper's figures from real, reproducible evaluation data.

Produces, under figures/:
  - detection_by_category.pdf : per-category fault detection, ablated baseline vs full method
                                (constructed dataset, §V-A).
  - detection_realistic.pdf   : detection rate with Wilson 95% CI on the realistic population
                                (Alibaba-like topologies, §V-C).
  - train_ticket_dag.pdf      : the train-ticket dependency graph, node size/colour = in-degree
                                centrality, critical path highlighted, off-path recovered faults
                                circled (§V-B).
  - detection_sweep.pdf       : detection rate of both decompositions as the injected fault moves
                                THROUGH both thresholds (§V-C honesty check): shows the headline
                                gap is a genuine threshold effect, not a constructed point.
  - gamma_sensitivity.pdf     : safely-committable envelope A_commit vs the confidence factor k
                                (§III-B), illustrating the competitiveness/protection trade-off.

Every number is recomputed live from the same code paths as the tables: no value is hardcoded.

Reproduce offline (no credentials):
    pip install matplotlib networkx
    python scripts/gen_figures.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import yaml

from slacheck.eval.runner import run_eval

REPO = Path(__file__).resolve().parents[1]
FIGDIR = REPO / "figures"
FIGDIR.mkdir(exist_ok=True)

# A restrained, print-friendly palette (no reliance on colour alone: hatching/markers too).
C_BASE = "#bdbdbd"   # ablated baseline
C_FULL = "#1f4e79"   # full method
C_PATH = "#c0392b"   # critical path / highlight
plt.rcParams.update({
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
    "pdf.fonttype": 42,  # editable text in the PDF (TrueType), not Type3
})


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fig_detection_by_category() -> None:
    """Grouped bars: injected vs baseline-detected vs full-detected, per category."""
    r_full = run_eval(REPO / "fixtures" / "eval", "v2")
    r_base = run_eval(REPO / "fixtures" / "eval", "v1")
    cats = [
        ("global_slo", "Global-SLO"),
        ("sub_slo", "Sub-SLO"),
        ("reconfig", "Reconfiguration"),
    ]
    labels = [lbl for _, lbl in cats]
    injected = [r_full.injected(k) for k, _ in cats]
    base = [r_base.detected(k) for k, _ in cats]
    full = [r_full.detected(k) for k, _ in cats]

    x = range(len(cats))
    w = 0.38
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    ax.bar([i - w / 2 for i in x], base, w, label="Ablated baseline",
           color=C_BASE, edgecolor="black", linewidth=0.5)
    ax.bar([i + w / 2 for i in x], full, w, label="Full method",
           color=C_FULL, edgecolor="black", linewidth=0.5)
    # injected count as a thin reference marker on top
    for i, inj in enumerate(injected):
        ax.hlines(inj, i - w, i + w, colors=C_PATH, linestyles="--", linewidth=1.0)
        ax.text(i, inj + 1.5, f"{inj}", ha="center", va="bottom",
                fontsize=7.5, color=C_PATH)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Faults detected")
    ax.set_ylim(0, max(injected) * 1.18)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax.text(0.99, -0.30, "dashed = injected total", transform=ax.transAxes,
            ha="right", va="top", fontsize=6.5, color=C_PATH)
    out = FIGDIR / "detection_by_category.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  (baseline {sum(base)}/{sum(injected)}, full {sum(full)}/{sum(injected)})")


def fig_detection_realistic() -> None:
    """Detection rate with Wilson CI error bars on the realistic population."""
    ds = REPO / "fixtures" / "eval_realistic"
    r_full = run_eval(ds, "v2")
    r_base = run_eval(ds, "v1")
    n = r_full.injected("sub_slo")
    kb, kf = r_base.detected("sub_slo"), r_full.detected("sub_slo")
    pb, pf = 100 * kb / n, 100 * kf / n
    lob, hib = wilson_ci(kb, n)
    lof, hif = wilson_ci(kf, n)

    fig, ax = plt.subplots(figsize=(3.0, 2.3))
    xs = [0, 1]
    rates = [pb, pf]
    errs = [[pb - 100 * lob, pf - 100 * lof], [100 * hib - pb, 100 * hif - pf]]
    ax.bar(xs, rates, 0.55, color=[C_BASE, C_FULL],
           edgecolor="black", linewidth=0.5)
    ax.errorbar(xs, rates, yerr=errs, fmt="none", ecolor="black",
                elinewidth=1.0, capsize=4)
    for xi, r in zip(xs, rates, strict=True):
        ax.text(xi, r + 4, f"{r:.1f}%", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(["Uniform\n(ablated)", "Weighted\n(full)"])
    ax.set_ylabel("Sub-SLO detection rate (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"n = {n} realistic topologies", fontsize=8)
    out = FIGDIR / "detection_realistic.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  (uniform {pb:.1f}% [{100*lob:.1f},{100*hib:.1f}], "
          f"weighted {pf:.1f}% [{100*lof:.1f},{100*hif:.1f}])")


def _train_ticket_graph() -> nx.DiGraph:
    data = yaml.safe_load((REPO / "fixtures" / "topology" / "train-ticket.yaml").read_text())
    g = nx.DiGraph()
    for src, deps in data["dependencies"].items():
        g.add_node(src)
        for d in deps:
            g.add_edge(src, d)
    # Match the engine: reduce cycles to a DAG by dropping back-edges (deterministic).
    while not nx.is_directed_acyclic_graph(g):
        cycle = nx.find_cycle(g)
        g.remove_edge(*cycle[-1])
    return g


def fig_train_ticket_dag() -> None:
    """Real 38-service DAG: in-degree centrality as size/colour, off-path faults circled."""
    g = _train_ticket_graph()
    # Off-path high-centrality faults recovered by whole-graph aggregation (from case_study.py).
    recovered = {"ts-order-service", "ts-station-service", "ts-train-service"}

    indeg = dict(g.in_degree())
    pos = nx.spring_layout(g, seed=20260630, k=1.5, iterations=400)

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    sizes = [120 + 230 * indeg[n] for n in g.nodes()]
    colors = [indeg[n] for n in g.nodes()]
    nx.draw_networkx_edges(g, pos, ax=ax, edge_color="#cccccc",
                           arrows=True, arrowsize=6, width=0.6,
                           connectionstyle="arc3,rad=0.05")
    nodes = nx.draw_networkx_nodes(
        g, pos, ax=ax, node_size=sizes, node_color=colors,
        cmap="viridis", edgecolors="black", linewidths=0.4)
    # circle the recovered off-path faults
    rec_xy = [pos[n] for n in recovered if n in pos]
    if rec_xy:
        rx, ry = zip(*rec_xy, strict=True)
        ax.scatter(rx, ry, s=[sizes[list(g.nodes()).index(n)] + 350
                              for n in recovered if n in pos],
                   facecolors="none", edgecolors=C_PATH, linewidths=1.8, zorder=5)
    # label the top-centrality nodes only (keep it readable). Per-node offsets with
    # leader lines avoid stacking when the spring layout places two hubs adjacent.
    top = sorted(g.nodes(), key=lambda n: indeg[n], reverse=True)[:6]
    offsets = {
        "ts-order-service": (-26, 20),
        "ts-order-other-service": (22, -20),
        "ts-station-service": (-6, 24),
        "ts-travel-service": (4, -22),
        "ts-route-service": (0, 22),
        "ts-seat-service": (-22, 8),
        "ts-train-service": (0, -24),
    }
    for n in sorted(set(top) | recovered, key=lambda n: indeg[n], reverse=True):
        if n in pos:
            dx, dy = offsets.get(n, (0, 14))
            ax.annotate(n.replace("ts-", "").replace("-service", ""),
                        pos[n], fontsize=7, fontweight="bold", ha="center", va="center",
                        xytext=(dx, dy), textcoords="offset points",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                  ec="#888888", lw=0.4, alpha=0.95),
                        arrowprops=dict(arrowstyle="-", color="#888888", lw=0.5))
    cbar = fig.colorbar(nodes, ax=ax, shrink=0.7, pad=0.01)
    cbar.set_label("in-degree (structural centrality)", fontsize=8)
    ax.text(0.0, -0.04,
            "red circles: high-centrality services off the critical path, "
            "recovered only by whole-graph aggregation",
            transform=ax.transAxes, fontsize=7, color=C_PATH)
    ax.set_axis_off()
    out = FIGDIR / "train_ticket_dag.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  ({g.number_of_nodes()} nodes, {g.number_of_edges()} edges)")


def fig_detection_sweep() -> None:
    """Detection vs fault position as it moves through both decomposition thresholds."""
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    from sweep_study import run as sweep_run  # local import: sibling study script

    rows = sweep_run(n=200)  # [(pos, n, uniform_det, weighted_det), ...]
    pos = [r[0] for r in rows]
    uni = [100 * r[2] / r[1] for r in rows]
    wei = [100 * r[3] / r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    # shade the discriminating window (0,1)
    ax.axvspan(0, 1, color="#f0e6d2", alpha=0.6, lw=0)
    ax.text(0.5, 6, "window", ha="center", va="bottom", fontsize=6.5, color="#8a6d3b")
    ax.plot(pos, uni, "o-", color=C_BASE, markeredgecolor="black", markeredgewidth=0.4,
            markersize=4, label="Uniform (ablated)")
    ax.plot(pos, wei, "s-", color=C_FULL, markeredgecolor="black", markeredgewidth=0.4,
            markersize=4, label="Weighted (full)")
    ax.set_xlabel("fault position relative to thresholds\n"
                  "(<0 below weighted · (0,1) in window · >1 above uniform)", fontsize=7)
    ax.set_ylabel("Sub-SLO detection rate (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=7.5, loc="center right")
    out = FIGDIR / "detection_sweep.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  (positions {pos[0]}..{pos[-1]})")


def fig_gamma_sensitivity() -> None:
    """A_commit vs confidence factor k on the running example (§III-B trade-off)."""
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    from gamma_study import _graph as gamma_graph
    from gamma_study import run as gamma_run  # local import: sibling study script

    from slacheck.envelope.v2.aggregate_v2 import compute_envelope_v2

    ks, avail = gamma_run()  # ([k...], [A_commit availability %...])
    a_star = compute_envelope_v2(gamma_graph()).availability_pct  # theoretical max (no margin)

    fig, ax = plt.subplots(figsize=(3.2, 2.3))
    ax.axhline(a_star, ls="--", color=C_PATH, lw=1.0)
    ax.text(ks[-1], a_star + 0.01, f"$A^*$ = {a_star:.2f}% (no margin)",
            ha="right", va="bottom", fontsize=6.5, color=C_PATH)
    ax.plot(ks, avail, "o-", color=C_FULL, markeredgecolor="black",
            markeredgewidth=0.4, markersize=5)
    for k, a in zip(ks, avail, strict=True):
        ax.annotate(f"{a:.3f}%", (k, a), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=6.5)
    ax.set_xlabel("confidence factor $k$ (margin $\\gamma_i = k\\,\\sigma_i$)")
    ax.set_ylabel("$A_{\\mathrm{commit}}$ availability (%)")
    ax.set_xticks(ks)
    ax.margins(y=0.18)
    out = FIGDIR / "gamma_sensitivity.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  (k={ks}, A_commit={[round(a,3) for a in avail]})")


if __name__ == "__main__":
    fig_detection_by_category()
    fig_detection_realistic()
    fig_train_ticket_dag()
    fig_detection_sweep()
    fig_gamma_sensitivity()
    print("done")
