import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_benchmark_without_reference_tools(tmp_path):
    results = tmp_path / "benchmarks"
    results.mkdir()
    run = subprocess.run(
        [sys.executable, "-m", "scripts.bench"],
        cwd=tmp_path,
        env={**os.environ, "PATH": "", "PYTHONPATH": str(REPO)},
        capture_output=True, text=True, timeout=60,
    )
    assert run.returncode == 0, run.stderr
    assert run.stderr.count("not installed") == 3
    report = (results / "results.md").read_text()
    assert "| Pyrra | not installed |" in report
    assert "| slacheck independent | 15/15 | 15/15 | 0 | 369/369 |" in report
    assert "| Hand error budget | 19/19 | 19/19 | 0 | not computed |" in report
