#!/bin/bash
# Stop the game (and its wineserver) started by run.sh. An instance can survive
# wineserver -k (it then keeps running the previous exe): its processes (launched as
# dot-slash exe name) get SIGTERM, then SIGKILL.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
pids() { ps -eo pid,args | awk '$0 ~ /\.\/Taiko5D[X]/ {print $1}'; }
for p in $(pids); do kill $p 2>/dev/null; done
WINEPREFIX=$ROOT/build/prefix/pfx "$HOME/.local/share/Steam/compatibilitytools.d/GE-Proton10-34/files/bin/wineserver" -k 2>/dev/null
sleep 3
for p in $(pids); do kill -9 $p 2>/dev/null; done
sleep 1
n=$(pids | wc -l); [ "$n" = 0 ] || echo "stop.sh: $n game processes left"
