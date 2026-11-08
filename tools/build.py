"""Build the English files from the clean game and script/ (run tools/setup.py first).

usage: .venv/bin/python tools/build.py [GAME_DIR] [OUT_DIR]
       (defaults: game_clean/ -> build/out/; with --install, also copy them into the test
       install build/game/, made as a reflink copy of GAME_DIR if missing)

Writes OUT_DIR/<same relative paths as the game>: Taiko5DX.exe, data/TAI5MSG_JP.DAT,
data/FONT/FONT_JPN.G1T, data/EVENT/*.TS5 (those with English),
data/CMENU/SNR/SNR0-8_JP.TR5 (scenario titles/intros), data/CMENU/INITTOP.G1T (title menu),
UI textures from tl/uigfx.txt.
"""
import os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import endings, evtl, exepatch, exestr, font, maplabels, menugfx, mggfx, towncards, msgfile, names, pesect, scenarios, setup, tables, text, tl, ui, uigfx, uihooks

CARD_TEXTS = range(28, 33)

def build_msg(clean):
    blocks = msgfile.blocks(clean)
    assert msgfile.pack(blocks) == clean, 'identity repack failed'
    n_en = 0
    for n in range(len(blocks)):
        for r in tl.load(n):
            if r['en']:
                en = r['en']
                # person card texts: the card panel appends the "(dates)" line to the
                # name; the Japanese full-width paren gave the gap
                if n in CARD_TEXTS and r['jp'].startswith('（') and en.startswith('('):
                    en = ' ' + en
                blocks[n][r['id']] = text.encode(en)
                n_en += 1
    return msgfile.pack(blocks), n_en

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    game = args[0] if args else setup.CLEAN
    out = args[1] if len(args) > 1 else os.path.join(setup.ROOT, 'build', 'out')
    setup.check(game)
    rd = lambda rel: open(os.path.join(game, rel), 'rb').read()
    files = {}
    exe = bytearray(exepatch.apply(rd('Taiko5DX.exe')))
    print('tables: %d names in English' % tables.apply(exe))
    seg = pesect.Segment(bytes(exe))
    print('ui: %d strings in English' % ui.apply(seg))
    print('exe strings: %d in English (%d references)' % exestr.apply(seg))
    print('names: %d lookup entries, %d officer-table names' % names.apply(seg))
    print('ui hooks: %d' % uihooks.apply(seg))
    print('map labels: %d patches' % maplabels.apply(seg))
    print('endings: %d in English' % endings.apply(seg))
    files['Taiko5DX.exe'] = seg.finish()
    files['data/FONT/FONT_JPN.G1T'] = font.build(rd('data/FONT/FONT_JPN.G1T'))
    files[setup.MSG], n_en = build_msg(rd(setup.MSG))
    print('messages: %d entries in English' % n_en)
    files.update(menugfx.apply(game))
    print('title menu labels drawn')
    files.update(towncards.apply(game))
    print('town facility cards drawn')
    files.update(maplabels.apply_files(game))
    ug = uigfx.apply(game)
    files.update(ug)
    print('ui textures: %d files' % len(ug))
    mg = mggfx.apply(game)
    files.update(mg)
    print('mini-game textures: %d files' % len(mg))
    sc = scenarios.apply(game)
    files.update(sc)
    print('scenarios: %d files' % len(sc))
    ev, nwarn = evtl.apply_all()
    files.update(ev)
    print('events: %d files in English (%d layout warnings)' % (len(ev), nwarn))
    for rel, data in files.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(data)
    print('wrote', out)
    if '--install' in sys.argv:
        inst = os.path.join(setup.ROOT, 'build', 'game')
        if not os.path.isdir(inst):
            subprocess.run(['cp', '-r', '--reflink=auto', game, inst], check=True)
        for rel in files:
            dst = os.path.join(inst, rel)
            if os.path.exists(dst):
                os.remove(dst)      # never write through a reflink/hard link into the clean copy
            shutil.copyfile(os.path.join(out, rel), dst)
        print('installed into', inst)

if __name__ == '__main__':
    main()
