"""Merge "index<TAB>English" lines (stdin or file) into tl/ui.txt, then check.
usage: .venv/bin/python tools/dev/ui_add.py [FILE]"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import ui
src = open(sys.argv[1], encoding='utf-8') if len(sys.argv) > 1 else sys.stdin
tl = ui.load_tl()
n = 0
for line in src.read().splitlines():
    if line.strip() and not line.startswith('#'):
        k, _, v = line.partition('\t')
        tl[int(k)] = v.replace('\\n', '\n')
        n += 1
errs = ui.errors(open(ui.CLEAN_EXE, 'rb').read(), tl)
if errs:
    raise SystemExit('\n'.join(errs))
ui.save_tl(tl)
print('merged %d, total %d' % (n, len(tl)))
