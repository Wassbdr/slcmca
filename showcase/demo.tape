# Live terminal demo: every number on screen is computed by the commands as they run.
# Rendered by showcase/make_showcase.sh (needs vhs, ttyd, ffmpeg). Assumes $DEMO_VENV exists
# with the runtime dependencies pre-installed so `pip install .` is fast on camera.
Output showcase/demo_raw.mp4

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 17
Set Width 1280
Set Height 720
Set Padding 18
Set Theme "Builtin Dark"
Set TypingSpeed 25ms
Set WindowBar Colorful

Hide
Type "source $DEMO_VENV/bin/activate && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show

Type "# slacheck - which SLO can this app actually meet? (live run)"
Enter
Type "pip install -q ."
Enter
Wait+Line@60s /^\$\s*$/
Sleep 300ms
Type "slacheck eval --both     # 113 injected faults, v1 baseline vs v2"
Enter
Wait+Screen@30s /Total.*113\s+113/
Sleep 7s
Type "clear"
Enter
Type "# a reconfiguration scenario: autoscaler scales up only at cpu > 86%"
Enter
Type "slacheck check fixtures/eval/reconfig/reconfig_01.yaml --both | grep -E '===|FAULT|\]|No over|v1 has'"
Enter
Wait+Screen@30s /cpu_pct le 80/
Sleep 7s
Type "clear"
Enter
Type "# your own topology: can this 7-service shop promise 99.9%?"
Enter
Type "slacheck check examples/shop.yaml --slo 99.9 | grep -E 'FAULT|\]'"
Enter
Wait+Screen@30s /payment:/
Sleep 6s
