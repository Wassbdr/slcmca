Output showcase/demo_raw.mp4

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 20
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "Builtin Dark"
Set TypingSpeed 18ms
Set WindowBar Colorful

Hide
Type "source $DEMO_VENV/bin/activate && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show

Type "slacheck check examples/shop.yaml --independent --slo 99.94"
Enter
Wait+Screen@8s /Single-service repairs/
Sleep 8s
Type "clear"
Enter
Type "slacheck check examples/shop-openslo.yaml --graph examples/shop.yaml --independent"
Enter
Wait+Screen@8s /Feasible/
Sleep 5s
