"""Build the showcase poster and metadata from the measured benchmark."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"
CHECK = "slacheck check examples/shop.yaml --slo 99.94"


def benchmark() -> tuple[dict[str, list[int]], str, float]:
    section = ""
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for line in (ROOT / "benchmarks/results.md").read_text().splitlines():
        if line.startswith("CPU:"):
            hardware = line
        elif line.startswith("## "):
            section = line
        elif line.startswith("| ") and section in ("## Development", "## Held-out"):
            method, recall, _, false_positives, thresholds = (
                field.strip() for field in line.strip("|").split("|")
            )
            if "/" not in recall:
                continue
            found, possible = map(int, recall.split("/"))
            stats[method][0] += found
            stats[method][1] += possible
            stats[method][2] += int(false_positives)
            if "/" in thresholds:
                stats[method][3] += int(thresholds.split("/")[0])
        elif section == "## Runtime" and line.startswith("| slacheck independent CLI |"):
            timing = max(float(cell.split("/")[-1]) for cell in line.strip("|").split("|")[1:])
    return stats, hardware, timing


def poster(stats: dict[str, list[int]], hardware: str, timing: float) -> None:
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100, facecolor="#f8fafc")
    fig.text(0.07, 0.90, "slacheck", fontsize=37, weight="bold", color="#0f172a")
    fig.text(0.07, 0.82, "Find infeasible availability commitments before shipping",
             fontsize=20, color="#334155")
    ax = fig.add_axes((0.26, 0.29, 0.65, 0.46))
    ax.set_facecolor("#f8fafc")
    names = [
        "slacheck independent", "Hand error budget", "slacheck v2", "Sloth", "Pyrra", "OpenSLO",
    ]
    found = [stats[name][0] for name in names]
    possible = stats[names[0]][1]
    bars = ax.barh(names, found, color=["#0369a1", *(["#94a3b8"] * (len(names) - 1))])
    ax.bar_label(bars, labels=[f"{value}/{possible}" for value in found], padding=6, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, possible + 6)
    ax.spines[["top", "right", "bottom", "left"]].set_visible(False)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks([])
    ax.set_title("Infeasible commitments detected", loc="left", fontsize=15, pad=12)
    thresholds = stats[names[0]][3]
    timing_label = f"{thresholds} exact thresholds  |  {timing:.0f} ms slowest 200-service CLI run"
    fig.text(0.07, 0.20, timing_label, fontsize=17, weight="bold", color="#0f172a")
    setup = "72 synthetic graphs; 6 seeds; exhaustive oracle. Validators receive the root SLO only."
    fig.text(0.07, 0.13, setup, fontsize=11, color="#475569")
    fig.text(0.07, 0.08, hardware, fontsize=10, color="#475569")
    fig.savefig(SHOWCASE / "poster.png", dpi=100)
    plt.close(fig)


def write_metadata(stats: dict[str, list[int]], hardware: str, timing: float) -> None:
    path = SHOWCASE / "showcase.json"
    role = json.loads(path.read_text())["role"]
    found, possible, false_positives, thresholds = stats["slacheck independent"]
    structure = "72 synthetic graphs, six seeds, separate held-out family, exhaustive oracle."
    doc = {
        "slug": "slcmca",
        "title": "slacheck: availability commitments for distributed applications",
        "tagline": "Check an availability objective and find the smallest single-service repair.",
        "problem": "A service-level objective can exceed what its required dependencies deliver.",
        "approach": (
            "A reduced decision diagram evaluates required and alternative dependencies, "
            "counts each shared service once and solves the minimum conditional thresholds."
        ),
        "stack": ["Python", "Pydantic", "Typer", "OpenSLO", "OpenTelemetry", "GitHub Actions"],
        "demo": {
            "gif": "showcase/demo.gif",
            "mp4": "showcase/demo.mp4",
            "poster": "showcase/poster.png",
            "kind": "live",
            "caption": "Check an infeasible shop objective, then print its highest-ranked repair.",
        },
        "reproduce": ["python -m pip install .", CHECK, "make bench", "make showcase"],
        "results": [
            {"label": "Infeasible commitments detected", "value": f"{found}/{possible}",
             "command": "make bench", "setup": structure},
            {"label": "False positives", "value": str(false_positives),
             "command": "make bench", "setup": structure},
            {"label": "Conditional thresholds matched", "value": str(thresholds),
             "command": "make bench", "setup": structure},
            {"label": "Slowest 200-service CLI run", "value": f"{timing:.2f} ms",
             "command": "make bench", "setup": f"Two graphs, seven serial runs each. {hardware}"},
        ],
        "limits": [
            "The exact calculation assumes independent failure states for distinct services.",
            "Trace imports do not infer redundancy or local service availability.",
            "The repair ranking changes one service at a time.",
        ],
        "role": role,
        "repo": "https://github.com/Wassbdr/slcmca",
    }
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    results, cpu, slowest = benchmark()
    poster(results, cpu, slowest)
    write_metadata(results, cpu, slowest)
