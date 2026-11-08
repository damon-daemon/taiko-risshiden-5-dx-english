#!/bin/bash
# Run the test install (build/game) with GE-Proton in its own prefix (build/prefix).
# usage: tools/emu/run.sh [exe]   (default Taiko5DX.exe; Taiko5DXLauncher.exe for settings)
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PROTON=${PROTON:-$HOME/.local/share/Steam/compatibilitytools.d/GE-Proton10-34/proton}
export STEAM_COMPAT_DATA_PATH=$ROOT/build/prefix
export STEAM_COMPAT_CLIENT_INSTALL_PATH=$HOME/.local/share/Steam
export SteamAppId=1842810 SteamGameId=1842810
mkdir -p "$STEAM_COMPAT_DATA_PATH"
cd "$ROOT/build/game" || exit 1
exec "$HOME/.local/share/Steam/steamapps/common/SteamLinuxRuntime_sniper/_v2-entry-point" --verb=waitforexitandrun -- "$PROTON" waitforexitandrun "./${1:-Taiko5DX.exe}" > "$ROOT/build/run.log" 2>&1
