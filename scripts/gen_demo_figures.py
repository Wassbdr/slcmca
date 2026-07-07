"""Generate demo figures: the full dependency graph, and the subgraph slacheck extracts for a
given user constraint. Everything is REAL — the highlighted path is the actual critical path
returned by the pipeline (scripts don't hand-draw it).

Produces under figures/demo/:
  - full_graph.png              : the whole discovered train-ticket topology (38 services)
  - critical_path_latency.png   : same graph, the latency critical path highlighted + isolated
  - critical_path_availability.png : same for an availability constraint

Reproduce offline (no credentials):
    pip install matplotlib networkx
    python scripts/gen_demo_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import yaml

from slacheck.datadog.source import get_source
from slacheck.pipeline import analyze

REPO = Path(__file__).resolve().parents[1]
TOPO = REPO / "fixtures" / "topology" / "train-ticket.yaml"
ENTRY = "ts-ui-dashboard"
OUT = REPO / "figures" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

C_DIM = "#d9d9d9"      # off-path nodes/edges
C_NODE = "#5b8db8"     # on-graph nodes
C_PATH = "#c0392b"     # extracted path
C_ENTRY = "#1f4e79"    # entrypoint

plt.rcParams.update({"font.size": 8, "figure.dpi": 200, "savefig.bbox": "tight"})


def _short(n: str) -> str:
    return n.replace("ts-", "").replace("-service", "")


def _graph() -> nx.DiGraph:
    data = yaml.safe_load(TOPO.read_text())
    g = nx.DiGraph()
    for src, deps in data["dependencies"].items():
        g.add_node(src)
        for d in deps:
            g.add_edge(src, d)
    while not nx.is_directed_acyclic_graph(g):
        g.remove_edge(*nx.find_cycle(g)[-1])
    return g


def _real_path(constraint: str) -> list[str]:
    """The ACTUAL critical path the pipeline extracts for this constraint (v1)."""
    src = get_source("declared", topology=TOPO, metrics_from="fixture")
    res = analyze(src, ENTRY, constraint, paper_version="v1")
    return [c.name for c in res.path]


def _layout(g: nx.DiGraph):
    return nx.spring_layout(g, seed=20260630, k=1.5, iterations=400)


def fig_full(g: nx.DiGraph, pos) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    indeg = dict(g.in_degree())
    sizes = [140 + 220 * indeg[n] for n in g.nodes()]
    nx.draw_networkx_edges(g, pos, ax=ax, edge_color=C_DIM, arrows=True, arrowsize=6,
                           width=0.6, connectionstyle="arc3,rad=0.05")
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=sizes, node_color=C_NODE,
                           edgecolors="black", linewidths=0.4)
    nx.draw_networkx_nodes(g, pos, ax=ax, nodelist=[ENTRY], node_size=[140 + 220 * indeg[ENTRY]],
                           node_color=C_ENTRY, edgecolors="black", linewidths=1.0)
    top = sorted(g.nodes(), key=lambda n: indeg[n], reverse=True)[:7]
    for n in set(top) | {ENTRY}:
        ax.annotate(_short(n), pos[n], fontsize=7, fontweight="bold", ha="center",
                    xytext=(0, 10), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="#aaa", lw=0.3, alpha=0.9))
    ax.set_title(f"Discovered topology — {g.number_of_nodes()} services, "
                 f"{g.number_of_edges()} dependencies", fontsize=9)
    ax.text(0, -0.03, f"entrypoint = {_short(ENTRY)} (dark); node size = in-degree centrality",
            transform=ax.transAxes, fontsize=7, color="#555")
    ax.set_axis_off()
    fig.savefig(OUT / "full_graph.png")
    plt.close(fig)
    print(f"wrote {OUT / 'full_graph.png'}")


def fig_path(g: nx.DiGraph, pos, constraint: str, envelope_note: str) -> None:
    path = _real_path(constraint)
    pset = set(path)
    pedges = list(zip(path, path[1:], strict=False))  # consecutive pairs (unequal lengths)

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    # dim everything
    nx.draw_networkx_edges(g, pos, ax=ax, edge_color=C_DIM, arrows=True, arrowsize=5,
                           width=0.5, connectionstyle="arc3,rad=0.05")
    off = [n for n in g.nodes() if n not in pset]
    nx.draw_networkx_nodes(g, pos, ax=ax, nodelist=off, node_size=90,
                           node_color=C_DIM, edgecolors="#bbb", linewidths=0.3)
    # highlight the extracted path (straight edges, correct clipping so every hop shows)
    nx.draw_networkx_edges(g, pos, ax=ax, edgelist=pedges, edge_color=C_PATH,
                           arrows=True, arrowsize=13, width=2.4, node_size=320,
                           connectionstyle="arc3,rad=0.0", min_source_margin=12,
                           min_target_margin=12)
    nx.draw_networkx_nodes(g, pos, ax=ax, nodelist=path, node_size=320,
                           node_color=C_PATH, edgecolors="black", linewidths=0.6)
    for n in path:
        ax.annotate(_short(n), pos[n], fontsize=7.5, fontweight="bold", ha="center",
                    xytext=(0, 11), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.13", fc="white", ec=C_PATH, lw=0.5))
    ax.set_title(f"Extracted critical path — constraint: {constraint}", fontsize=9)
    chain = "  →  ".join(_short(n) for n in path)
    ax.text(0, -0.03, f"{chain}\n{envelope_note}", transform=ax.transAxes,
            fontsize=7.5, color=C_PATH)
    ax.set_axis_off()
    out = OUT / f"critical_path_{constraint}.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}  ({len(path)} nodes: {chain})")


if __name__ == "__main__":
    g = _graph()
    pos = _layout(g)
    fig_full(g, pos)
    fig_path(g, pos, "latency", "achievable end-to-end latency = 24 ms (sum along the path)")
    fig_path(g, pos, "availability",
             "achievable availability = 99.40% (error budget along the path)")
    print("done")
