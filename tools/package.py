"""Package a release: release/<Name>_v<version>.zip with one xdelta patch per changed game
data file, the program loader (dinput8.dll + tl_patch.bin, tools/loader.py: the exe is
never changed), apply/restore scripts for Windows (.bat) and Linux (.sh), and README.txt.

usage: .venv/bin/python tools/package.py 0.1.0

Run tools/build.py first (it writes build/out/). Each file of build/out/ is diffed against
the same file of game_clean/ (xdelta3 -e), so the zip holds no game data. The apply
scripts copy each original file to <game>/backup_jp/ once and always patch from that
copy, so applying again (or a newer release) works; restore copies the backups back.
xdelta3 refuses a source file that differs from the one the patch was made from.

README.txt is generated from README.md (the notices, "What's translated", "Known
issues" and "Credits") plus install instructions.
"""
import hashlib, os, re, subprocess, sys, textwrap, zipfile

sys.path.insert(0, os.path.dirname(__file__))
import setup

ROOT = setup.ROOT
OUT = os.path.join(ROOT, 'build', 'out')
TITLE = 'Taiko Risshiden V DX - English Translation'
ZIP_NAME = 'Taiko_Risshiden_V_DX_English'
GAME_VERSION = '1.2.1'
XDELTA_URL = 'https://github.com/jmacd/xdelta-gpl/releases'

ADDED = ('dinput8.dll', 'tl_patch.bin')   # new files (tools/loader.py): copied, not patched

def built_files():
    out = []
    for d, _, fs in os.walk(OUT):
        for f in fs:
            out.append(os.path.relpath(os.path.join(d, f), OUT).replace(os.sep, '/'))
    return sorted(f for f in out if f not in ADDED)

def sha1(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()

# ---------------------------------------------------------------- scripts

BAT_HEAD = r'''@echo off
setlocal
rem {title} - applies the English patch to the game folder given as argument
rem (or dropped onto this file). Originals are kept in <game>\backup_jp\.
set "HERE=%~dp0"
set "GAME=%~1"
if "%GAME%"=="" (
  echo Drag the game folder ^(the one with Taiko5DX.exe^) onto apply.bat, or run:
  echo   apply.bat "C:\Program Files ^(x86^)\Steam\steamapps\common\<game folder>"
  pause
  exit /b 1
)
if not exist "%GAME%\Taiko5DX.exe" (
  echo Taiko5DX.exe not found in "%GAME%".
  pause
  exit /b 1
)
set "X=%HERE%xdelta3.exe"
if not exist "%X%" (
  echo xdelta3.exe not found next to apply.bat.
  echo Download xdelta3 for Windows from {xdelta}
  echo and put it next to apply.bat, renamed to xdelta3.exe.
  pause
  exit /b 1
)
echo Patching "%GAME%" ...
'''

BAT_TAIL = r'''copy /y "%HERE%dinput8.dll" "%GAME%\dinput8.dll" >nul || (set "F=dinput8.dll" & goto failed)
copy /y "%HERE%tl_patch.bin" "%GAME%\tl_patch.bin" >nul || (set "F=tl_patch.bin" & goto failed)
echo.
echo Done: {n} files patched. The Japanese originals are in "%GAME%\backup_jp".
pause
exit /b 0

:failed
echo.
echo FAILED on %F%. Is the game version {ver}, unmodified? Run restore.bat, or let
echo Steam verify the game files, then try again.
pause
exit /b 1

:patch
set "F=%~1"
if not exist "%GAME%\backup_jp\%F%" (
  if not exist "%GAME%\backup_jp\%~2" mkdir "%GAME%\backup_jp\%~2"
  copy /y "%GAME%\%F%" "%GAME%\backup_jp\%F%" >nul || exit /b 1
)
"%X%" -d -f -s "%GAME%\backup_jp\%F%" "%HERE%patches\%F%.xdelta" "%GAME%\%F%" || exit /b 1
exit /b 0
'''

RESTORE_BAT = r'''@echo off
setlocal
rem {title} - puts the Japanese originals from <game>\backup_jp\ back.
set "GAME=%~1"
if "%GAME%"=="" (
  echo Drag the game folder onto restore.bat, or run: restore.bat "<game folder>"
  pause
  exit /b 1
)
if not exist "%GAME%\backup_jp" (
  echo No backup_jp folder in "%GAME%": nothing to restore.
  pause
  exit /b 1
)
{restores}
del /q "%GAME%\dinput8.dll" "%GAME%\tl_patch.bin" "%GAME%\tl_patch.log" 2>nul
echo Restored. You can delete "%GAME%\backup_jp" now.
pause
'''

SH = '''#!/bin/sh
# {title} - applies the English patch to the game folder given as argument.
# Originals are kept in <game>/backup_jp/. Needs xdelta3 (package "xdelta3" or "xdelta").
set -e
here=$(cd "$(dirname "$0")" && pwd)
game=$1
if [ -z "$game" ] || [ ! -f "$game/Taiko5DX.exe" ]; then
    echo "usage: sh apply.sh <game folder with Taiko5DX.exe>"
    exit 1
fi
command -v xdelta3 >/dev/null || {{ echo "xdelta3 not found: install it first"; exit 1; }}
patch() {{
    if [ ! -f "$game/backup_jp/$1" ]; then
        mkdir -p "$game/backup_jp/$(dirname "$1")"
        cp -p "$game/$1" "$game/backup_jp/$1"
    fi
    xdelta3 -d -f -s "$game/backup_jp/$1" "$here/patches/$1.xdelta" "$game/$1" || {{
        echo "FAILED on $1. Is the game version {ver}, unmodified? Run restore.sh, or let"
        echo "Steam verify the game files, then try again."
        exit 1
    }}
}}
echo "Patching $game ..."
{calls}
cp "$here/dinput8.dll" "$here/tl_patch.bin" "$game/"
echo "Done: {n} files patched. The Japanese originals are in $game/backup_jp."
'''

RESTORE_SH = '''#!/bin/sh
# {title} - puts the Japanese originals from <game>/backup_jp/ back.
set -e
game=$1
if [ -z "$game" ] || [ ! -d "$game/backup_jp" ]; then
    echo "usage: sh restore.sh <game folder> (it must contain backup_jp/)"
    exit 1
fi
cp -rp "$game/backup_jp/." "$game/"
rm -f "$game/dinput8.dll" "$game/tl_patch.bin" "$game/tl_patch.log"
echo "Restored. You can delete $game/backup_jp now."
'''

def scripts(files):
    fmt = dict(title=TITLE, xdelta=XDELTA_URL, ver=GAME_VERSION, n=len(files))
    calls = []
    for f in files:
        w = f.replace('/', '\\')
        d = os.path.dirname(f).replace('/', '\\')
        calls.append('call :patch "%s" "%s" || goto failed' % (w, d))
    bat = BAT_HEAD.format(**fmt) + '\n'.join(calls) + '\n' + BAT_TAIL.format(**fmt)
    sh = SH.format(calls='\n'.join("patch '%s'" % f for f in files), **fmt)
    return {'apply.bat': bat.replace('\n', '\r\n'),
            'restore.bat': RESTORE_BAT.format(restores='\n'.join(
                'copy /y "%%GAME%%\\backup_jp\\%s" "%%GAME%%\\%s" >nul || (echo Could not restore %s & pause & exit /b 1)'
                % (f.replace('/', '\\'), f.replace('/', '\\'), f.replace('/', '\\')) for f in files),
                **fmt).replace('\n', '\r\n'),
            'apply.sh': sh, 'restore.sh': RESTORE_SH.format(**fmt)}

# ---------------------------------------------------------------- README.txt

def section(md, name):
    m = re.search(r'^## %s\n(.*?)(?=^## |\Z)' % re.escape(name), md, re.S | re.M)
    return m.group(1).strip() if m else ''

def plain(text):
    """Markdown -> readable plain text (bold, code, links, quotes)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'^> ?', '', text, flags=re.M)
    return text

def heading(t):
    return '%s\n%s\n' % (t, '-' * len(t))

INSTALL = '''\
You need Taiko Risshiden V DX for Windows (Steam), version {ver}, unmodified.

Windows:
1. Download xdelta3 for Windows ({xdelta}), and put the .exe next
   to apply.bat, renamed to xdelta3.exe.
2. Find the game folder: in Steam, right-click the game > Manage > Browse local files.
3. Drag that folder (the one with Taiko5DX.exe) onto apply.bat.

Linux / Steam Deck: install xdelta3, then run
   sh apply.sh "<game folder>"
and in Steam, set the game's launch options to
   WINEDLLOVERRIDES="dinput8=n,b" %command%
(Proton otherwise uses its own dinput8.dll instead of the one the patch adds.)

The scripts first copy each Japanese file they change into <game folder>/backup_jp/,
then patch it, and add two files: dinput8.dll and tl_patch.bin. The game program
(Taiko5DX.exe) is not changed: dinput8.dll applies the English patch for the program in
memory each time the game starts. If that fails (another game version), the game shows
a message, runs in Japanese and writes tl_patch.log. To undo, run restore.bat / restore.sh the same way, or let Steam verify
the game files. A game update from Steam also brings the Japanese files back: apply
the patch again (if a release supports the new version).

Existing saves load with the English files. A save's header (the line shown in the save
slot) is written when the game is saved, so older saves keep a Japanese header until
they are saved again.'''

def readme(md, version, n):
    out = [TITLE, 'Version %s' % version, '=' * len(TITLE), '']
    for pat in (r'^> \*\*This is a full machine translation.*?(?=\n\n)',
                r'^> \*\*This is a (?:beta|work in progress).*?(?=\n\n)'):
        m = re.search(pat, md, re.S | re.M)
        if m:
            out += [textwrap.fill(' '.join(plain(m.group(0)).split()), 78), '']
    out += [heading("What's translated"), plain(section(md, "What's translated")), '']
    out += [heading('How to install'),
            INSTALL.format(ver=GAME_VERSION, xdelta=XDELTA_URL), '']
    out += [heading('Known issues'), plain(section(md, 'Known issues')), '']
    out += [heading('Credits'), plain(section(md, 'Credits')), '']
    out += ['Source and bug reports: https://github.com/damon-daemon/taiko-risshiden-5-dx-english', '']
    return '\n'.join(out).replace('\n\n\n', '\n\n')

# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tools/package.py VERSION   (e.g. 0.1.0)')
    version = sys.argv[1]
    files = built_files()
    if not files:
        sys.exit('build/out/ is empty: run tools/build.py first')
    exe = os.path.join(OUT, 'tl_patch.bin')
    if not os.path.exists(exe) or os.path.exists(os.path.join(OUT, 'Taiko5DX.exe')):
        sys.exit('build/out/ must hold tl_patch.bin and no Taiko5DX.exe: re-run tools/build.py')
    if os.path.getmtime(exe) < max(os.path.getmtime(p) for p in
                                   [os.path.join(ROOT, 'tools', f) for f in os.listdir(os.path.join(ROOT, 'tools'))
                                    if f.endswith('.py') and f != 'package.py']):
        print('warning: build/out/ is older than some tools/*.py: re-run tools/build.py?')
    for f, h in setup.CLEAN_SHA1.items():
        if sha1(os.path.join(setup.CLEAN, f)) != h:
            sys.exit('game_clean/%s is not the clean v%s file' % (f, GAME_VERSION))
    tmp = os.path.join(ROOT, 'build', 'patches')
    os.makedirs(os.path.join(ROOT, 'release'), exist_ok=True)
    zpath = os.path.join(ROOT, 'release', '%s_v%s.zip' % (ZIP_NAME, version))
    md = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            src, dst = os.path.join(setup.CLEAN, f), os.path.join(OUT, f)
            if not os.path.exists(src):
                sys.exit('%s has no original in game_clean/' % f)
            pat = os.path.join(tmp, f + '.xdelta')
            os.makedirs(os.path.dirname(pat), exist_ok=True)
            subprocess.run(['xdelta3', '-e', '-9', '-f', '-s', src, dst, pat], check=True)
            z.write(pat, 'patches/%s.xdelta' % f, compress_type=zipfile.ZIP_STORED)
        for f in ADDED:
            z.write(os.path.join(OUT, f), f)
        for name, body in scripts(files).items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o755 if name.endswith('.sh') else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body)
        z.writestr('README.txt', readme(md, version, len(files)).replace('\n', '\r\n'))
        z.write(os.path.join(ROOT, 'LICENSE'), 'LICENSE.txt')
    print('%s: %d patches, %.1f MB' % (zpath, len(files), os.path.getsize(zpath) / 1e6))

if __name__ == '__main__':
    main()
