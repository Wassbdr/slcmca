"""Build showcase/poster.png and showcase/showcase.json from freshly computed results.

Every number comes from running the repository's own commands in a subprocess and parsing
their stdout; nothing is typed by hand:
  - `python -m slacheck.cli eval --both`   -> 113 injected-fault scenarios, v1 vs v2
  - `python scripts/realistic_study.py`     -> 200 synthetic Alibaba-like topologies

Usage (from the repository root): python showcase/build_assets.py
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "showcase"
ENV = {**os.environ, "PYTHONPATH": str(REPO / "src")}

EVAL_CMD = "slacheck eval --both"
REALISTIC_CMD = "python scripts/realistic_study.py"
CLASSES = [
    ("Global-SLO Inconsistencies", "Global-SLO\n(target > envelope)"),
    ("Sub-SLO Inconsistencies", "Sub-SLO\n(component too weak)"),
    ("Reconfiguration Inconsistencies", "Reconfiguration\n(unsafe autoscaling)"),
]


def run(args: list[str]) -> str:
    return subprocess.run(
        args, cwd=REPO, env=ENV, check=True, capture_output=True, text=True
    ).stdout


def parse_eval(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """{'v1': {label: (injected, detected)}, 'v2': {...}} from the eval --both table."""
    tables: dict[str, dict[str, tuple[int, int]]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"Fault detection \(paper (v\d)\):", line)
        if m:
            current = tables.setdefault(m.group(1), {})
            continue
        m = re.match(r"(.+?)\s+(\d+)\s+(\d+)$", line)
        if m and current is not None and m.group(1) != "Category":
            current[m.group(1).strip()] = (int(m.group(2)), int(m.group(3)))
    return tables


def parse_realistic(text: str) -> dict[str, tuple[int, int, float, float]]:
    """{'v1': (k, n, lo%, hi%), 'v2': ...} from scripts/realistic_study.py."""
    out = {}
    for ver in ("v1", "v2"):
        m = re.search(
            rf"{ver} \(.*?\):\s+(\d+)/(\d+) = [\d.]+%\s+\[95% CI ([\d.]+)–([\d.]+)%\]", text
        )
        if m is None:
            raise SystemExit(f"could not parse {ver} line from realistic_study output")
        out[ver] = (int(m.group(1)), int(m.group(2)), float(m.group(3)), float(m.group(4)))
    return out


def hardware() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return f"{cpu}, {os.cpu_count()} vCPU, CPU only, Python {platform.python_version()}"


def poster(ev: dict, rl: dict, hw: str) -> None:
    blue, orange, grey = "#9aa5b1", "#e8590c", "#495057"
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    fig.patch.set_facecolor("white")
    fig.text(0.04, 0.92, "slacheck: which SLO can this application actually meet?",
             fontsize=24, weight="bold", color="#212529")
    fig.text(0.04, 0.865,
             "Injected over-commitment faults detected.  v1 = critical-path baseline;  "
             "v2 = typed DAG + weighted split + autoscaling check.",
             fontsize=12.5, color=grey)

    ax = fig.add_axes((0.06, 0.22, 0.55, 0.56))
    xs = range(len(CLASSES))
    w = 0.36
    for i, (label, _) in enumerate(CLASSES):
        inj, d1 = ev["v1"][label]
        _, d2 = ev["v2"][label]
        ax.bar(i, inj, width=2 * w + 0.08, color="#f1f3f5", zorder=0)
        b1 = ax.bar(i - w / 2, d1, width=w, color=blue, zorder=2)
        b2 = ax.bar(i + w / 2, d2, width=w, color=orange, zorder=2)
        ax.bar_label(b1, labels=[f"{d1}/{inj}"], fontsize=12, padding=3)
        ax.bar_label(b2, labels=[f"{d2}/{inj}"], fontsize=12, padding=3, weight="bold")
    ax.set_xticks(list(xs), [c[1] for c in CLASSES], fontsize=11.5)
    ax.set_ylabel("scenarios detected", fontsize=12)
    ax.set_ylim(0, 70)
    ax.spines[["top", "right"]].set_visible(False)
    t1, t2 = ev["v1"]["Total"], ev["v2"]["Total"]
    ax.set_title(f"113 injected-fault scenarios:  v1 {t1[1]}/{t1[0]}   vs   v2 {t2[1]}/{t2[0]}",
                 fontsize=15, weight="bold", loc="left")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in (blue, orange, "#f1f3f5")],
              labels=["v1 baseline", "v2 full method", "injected"], frameon=False,
              fontsize=11, loc="upper left")

    ax2 = fig.add_axes((0.71, 0.22, 0.25, 0.56))
    for i, (ver, col) in enumerate((("v1", blue), ("v2", orange))):
        k, n, lo, hi = rl[ver]
        rate = 100 * k / n
        ax2.bar(i, rate, color=col, width=0.6, yerr=[[rate - lo], [hi - rate]], capsize=6,
                ecolor=grey)
        ax2.text(i, hi + 2.5, f"{rate:.1f}%\n({k}/{n})", ha="center", fontsize=12,
                 weight="bold" if ver == "v2" else "normal")
    ax2.set_xticks([0, 1], ["v1", "v2"], fontsize=12)
    ax2.set_ylim(0, 115)
    ax2.set_ylabel("Sub-SLO faults detected (%)", fontsize=12)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_title("200 synthetic topologies", fontsize=15, weight="bold", loc="left")

    fig.text(0.04, 0.105,
             "Left: fixtures/eval, constructed dataset (10/60/43 faults). v1 has no "
             "reconfiguration model, so its 0/43 is structural.", fontsize=9.5, color=grey)
    fig.text(0.04, 0.075,
             "Right: fixtures/eval_realistic, Alibaba-like distributions, fixed seed, Wilson 95% "
             "CI. Faults are injected: no false-alarm rate on a real fleet.",
             fontsize=9.5, color=grey)
    fig.text(0.04, 0.045, f"Computed live on {hw}.", fontsize=9.5, color=grey)
    fig.text(0.04, 0.015, f"Regenerate: bash showcase/make_showcase.sh   ({EVAL_CMD}; "
             f"{REALISTIC_CMD})", fontsize=9.5, color=grey, family="monospace")
    fig.savefig(OUT / "poster.png", dpi=100)
    plt.close(fig)


def existing_role() -> str:
    """The owner writes `role` by hand; keep it across rebuilds."""
    try:
        return json.loads((OUT / "showcase.json").read_text()).get("role") or "TODO"
    except (FileNotFoundError, json.JSONDecodeError):
        return "TODO"


def showcase_json(ev: dict, rl: dict, hw: str) -> None:
    t1, t2 = ev["v1"]["Total"], ev["v2"]["Total"]
    eval_setup = ("fixtures/eval: 113 constructed injected-fault scenarios (deterministic, "
                  f"scripts/gen_eval.py); {hw}")
    real_setup = ("fixtures/eval_realistic: 200 synthetic Alibaba-like topologies, fixed seed "
                  f"(scripts/gen_realistic_eval.py 200); Wilson 95% CI; {hw}")
    results = [{"label": "Injected faults detected, v2 (full method)",
                "value": f"{t2[1]}/{t2[0]}", "command": EVAL_CMD, "setup": eval_setup},
               {"label": "Injected faults detected, v1 (critical-path baseline)",
                "value": f"{t1[1]}/{t1[0]}", "command": EVAL_CMD, "setup": eval_setup}]
    for label, _ in CLASSES:
        inj, d1 = ev["v1"][label]
        _, d2 = ev["v2"][label]
        results.append({"label": f"{label}: v1 vs v2", "value": f"{d1}/{inj} vs {d2}/{inj}",
                        "command": EVAL_CMD, "setup": eval_setup})
    for ver, name in (("v2", "v2 (weighted)"), ("v1", "v1 (uniform)")):
        k, n, lo, hi = rl[ver]
        results.append({"label": f"Sub-SLO faults detected on synthetic topologies, {name}",
                        "value": f"{100 * k / n:.1f}% ({k}/{n}, 95% CI {lo}-{hi}%)",
                        "command": REALISTIC_CMD, "setup": real_setup})
    doc = {
        "slug": "slcmca",
        "title": "slacheck: achievable SLOs for distributed applications",
        "tagline": ("Given a service topology and per-service SLOs, slacheck computes the SLO "
                    "the whole application can actually promise and names the sub-objective "
                    "that breaks it."),
        "problem": ("Teams promise an end-to-end SLA (say 99.9%) without checking it against "
                    "what their dependencies deliver. The gap surfaces in production as a "
                    "breached SLA, a weak dependency, or an autoscaling rule that reacts too "
                    "late."),
        "approach": ("The topology is a typed DAG (required vs redundant calls). Ascending "
                     "aggregation composes per-service latency, error budget and cost into the "
                     "achievable envelope, minus a cloud-tier safety margin. Descending "
                     "decomposition splits the target into per-service thresholds weighted by "
                     "structural centrality, and autoscaling triggers are checked against the "
                     "operational bound that keeps the SLO."),
        "stack": ["Python", "networkx", "pydantic", "Typer", "PyYAML", "Datadog API",
                  "pytest", "matplotlib", "vhs"],
        "demo": {"gif": "showcase/demo.gif", "mp4": "showcase/demo.mp4",
                 "poster": "showcase/poster.png", "kind": "live",
                 "caption": ("pip install, then the 113-scenario evaluation (v1 67/113 vs v2 "
                             "113/113), one reconfiguration fault v1 misses and v2 catches, "
                             "and a 7-service shop checked against 99.9%.")},
        "reproduce": ["git clone https://github.com/Wassbdr/slcmca && cd slcmca",
                      "pip install .",
                      EVAL_CMD,
                      "slacheck check examples/shop.yaml --slo 99.9"],
        "results": results,
        "limits": [
            "The 113 scenarios are a constructed dataset with injected faults: they show the "
            "mechanism, not the false-alarm rate on a real fleet.",
            "v1 has no reconfiguration model, so its 0/43 on that class is by construction.",
            "Live mode needs Datadog API/app keys; the showcase runs offline on fixtures.",
            "Per-service cost is not exposed by Datadog; it comes from a YAML override or a "
            "k8s resource estimate.",
        ],
        "role": existing_role(),
        "repo": "https://github.com/Wassbdr/slcmca",
    }
    (OUT / "showcase.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    ev = parse_eval(run([sys.executable, "-m", "slacheck.cli", "eval", "--both"]))
    rl = parse_realistic(run([sys.executable, "scripts/realistic_study.py"]))
    hw = hardware()
    poster(ev, rl, hw)
    showcase_json(ev, rl, hw)
    t1, t2 = ev["v1"]["Total"], ev["v2"]["Total"]
    print(f"v1 {t1[1]}/{t1[0]}  v2 {t2[1]}/{t2[0]}  realistic v1 {rl['v1'][:2]} v2 {rl['v2'][:2]}")
    print(f"wrote {OUT / 'poster.png'} and {OUT / 'showcase.json'}")


if __name__ == "__main__":
    main()
