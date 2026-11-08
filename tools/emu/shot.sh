#!/bin/bash
# Screenshot the game window: tools/emu/shot.sh out.png
G=$(hyprctl clients -j | python -I -c "import json,sys
w=[x for x in json.load(sys.stdin) if x['class']=='steam_app_1842810']
x=w[0]; print('%d,%d %dx%d'%(*x['at'],*x['size']))")
grim -g "$G" "$1"
