#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export DEMO_VENV="${DEMO_VENV:-$ROOT/.showcase-venv}"
export PYTHONHASHSEED=0

for tool in python3 ffmpeg vhs ttyd; do
  command -v "$tool" >/dev/null || { echo "Install $tool and put it on PATH." >&2; exit 1; }
done

[ -d "$DEMO_VENV" ] || python3 -m venv "$DEMO_VENV"
source "$DEMO_VENV/bin/activate"
if ! python -c 'import matplotlib, slacheck' >/dev/null 2>&1; then
  python -m pip install '.[showcase]'
fi

if [[ "${SHOWCASE_USE_RESULTS:-0}" != 1 ]]; then
  make bench
fi
python showcase/build_assets.py
vhs showcase/demo.tape
ffmpeg -y -loglevel error -i showcase/demo_raw.mp4 -t 40 \
  -vf 'scale=1280:-2,fps=25' -c:v libx264 -pix_fmt yuv420p -crf 23 \
  -movflags +faststart showcase/demo.mp4
ffmpeg -y -loglevel error -i showcase/demo.mp4 \
  -vf 'fps=8,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none' \
  showcase/demo.gif
rm -f showcase/demo_raw.mp4

test "$(wc -c < showcase/demo.gif)" -lt 10000000
ls -lh showcase/demo.gif showcase/demo.mp4 showcase/poster.png showcase/showcase.json
