#!/usr/bin/env bash
# Rebuild everything in showcase/ from a clean clone, offline, with fixed seeds.
#
# Requirements:
#   - Python >= 3.10 with venv and pip (network access to PyPI for the first install)
#   - ffmpeg (H.264 encoder libx264)
#   - vhs >= 0.10 (https://github.com/charmbracelet/vhs) and ttyd >= 1.7 on PATH
#     (vhs downloads a headless Chromium on first run)
#   - fonts "DejaVu Sans Mono" and "Noto Color Emoji" (apt: fonts-dejavu-core fonts-noto-color-emoji)
#
# Outputs: showcase/poster.png, showcase/showcase.json, showcase/demo.mp4, showcase/demo.gif
# Usage:   bash showcase/make_showcase.sh            (from anywhere inside the repo)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export DEMO_VENV="${DEMO_VENV:-$ROOT/.showcase-venv}"
export PYTHONHASHSEED=0

for tool in python3 ffmpeg vhs ttyd; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done

echo "== 1/5 venv + install ($DEMO_VENV)"
[ -d "$DEMO_VENV" ] || python3 -m venv "$DEMO_VENV"
# shellcheck disable=SC1091
source "$DEMO_VENV/bin/activate"
pip install -q --upgrade pip
pip install -q . pytest "matplotlib>=3.7"

echo "== 2/5 regression contract (Table I vs the manuscript)"
python -m pytest -q tests/test_eval_table1.py

echo "== 3/5 datasets are deterministic (regenerate and diff)"
python scripts/gen_eval.py >/dev/null
python scripts/gen_realistic_eval.py 200 >/dev/null
git diff --quiet -- fixtures/eval fixtures/eval_realistic \
  || { echo "regenerated fixtures differ from the committed ones" >&2; exit 1; }

echo "== 4/5 poster.png + showcase.json (parsed from slacheck eval --both, realistic_study.py)"
python showcase/build_assets.py

echo "== 5/5 terminal demo (vhs, live run) -> demo.mp4 + demo.gif"
vhs showcase/demo.tape
ffmpeg -y -loglevel error -i showcase/demo_raw.mp4 -t 40 \
  -vf "scale='min(1280,iw)':-2,fps=25" -c:v libx264 -pix_fmt yuv420p -crf 23 \
  -movflags +faststart showcase/demo.mp4
ffmpeg -y -loglevel error -i showcase/demo.mp4 \
  -vf "fps=8,scale=1100:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none" \
  showcase/demo.gif
rm -f showcase/demo_raw.mp4

ls -lh showcase/demo.gif showcase/demo.mp4 showcase/poster.png showcase/showcase.json
