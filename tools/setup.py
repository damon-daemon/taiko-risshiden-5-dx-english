"""Create the working folder script/ from your own game files and the English in tl/.

script/ holds the Japanese text extracted from the game next to the English, so it is
generated on each machine and never distributed. Run this once after cloning (and again
after editing tl/), then tools/build.py.

usage: .venv/bin/python tools/setup.py [GAME_DIR]     (default: game_clean/)
"""
import hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import msgfile, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'script')
TL = os.path.join(ROOT, 'tl')
CLEAN = os.path.join(ROOT, 'game_clean')

# Taiko Risshiden V DX v1.2.1 (Steam): the files the patch reads
CLEAN_SHA1 = {
    'Taiko5DX.exe': 'ad85eaeb4531887266a2d59779ced538b6a366e3',
    'data/TAI5MSG_JP.DAT': '8b9ae554e33035b05cd73dfe5c2e5cf8dda6f7c7',
    'data/FONT/FONT_JPN.G1T': '226de4ffc34671e91153e95c872e2ba9255f06e1',
    'data/CMENU/INITTOP.G1T': 'b480d4c9e7dbe4fa88fd3040a970b51e9bbaf257',
    'data/MP/MAINBOX.G1T': '20282a2c0e82c3ef41b92086433882b39b800c4b',
    'data/MP/HANAFUDA0_CROP.G1T': '0df055d303014604b7b6577bf7077cca05528f9d',
    'data/UI/UI_COMMON_MARKERS.G1T': 'f4fd7981fb51270aa62ea6905ecb17e85adc490c',
    'data/UI/UI_BATTLE_PBATTLE.G1T': 'bc5ba9d809ca218910a6e159397e2309c18a6c60',
    'data/PBBATTLE/PBGRP1.G1T': '70858d873aee5d8d990f747d7b509a9e8f5894e6',
    'data/BASE/MAIN.G1T': '8daeffac9b2ddd45543e6b302fa65ac102132dfb',
    'data/MG/MG00.G1T': '9f436fc4f7f450a6c1969848873bb936c49554e8',
    'data/MG/MG01.G1T': 'eeb14766c8db613b84c6577482d11ad8f4897460',
    'data/MG/MG04.G1T': '01a797e1e9c117c02683d576b1f7e51eb37e59a3',
    'data/MG/MG09.G1T': '524b546d40f6d544ae023f2842db47ccd6af5bb1',
    'data/MG/MG10.G1T': 'e2e810a7287f6aa1c96efa9ba8ad76559b6eb26e',
    'data/MG/MG13.G1T': '36a50891dc0e8c979aed793a9cf69f5ae78fd634',
    'data/MG/MG14.G1T': '1ce96a088ec56f201d618220bee5499cd67d86ae',
    'data/MG/MG23.G1T': '0322caea6a455fad5d8cd83124c6dc4c1ce7a63d',
    'data/MG/MG21.G1T': 'da13a89e784bbf4545593f95448d43b11aba06cd',
    'data/UI/UI_MAP_MMAP.G1T': 'b73a193ebc248d2c4024545a4b64860875b43fff',
    'data/MG/MG24.G1T': 'fccb9be55fec433057c20b6d723cef7d00105870',
    'data/CMENU/SNR/SNR0_JP.TR5': 'f3fe0088c8fcf80d199e98c98e55c5010ac133ac',
    'data/CMENU/SNR/SNR1_JP.TR5': 'ff5067d073007335bbd97930c1552a5a291a661c',
    'data/CMENU/SNR/SNR2_JP.TR5': '551e5843278a403627cea0cc9f39accdee4f07d8',
    'data/CMENU/SNR/SNR3_JP.TR5': 'b2337e049851db2aeca88ef13936fa31263e9bb1',
    'data/CMENU/SNR/SNR4_JP.TR5': 'c78b1365e67a6dcb0bd583e338ef618c08204ccb',
    'data/CMENU/SNR/SNR5_JP.TR5': '550761d3133ccd770bc1b2a805493ca62e8cf8e1',
    'data/CMENU/SNR/SNR6_JP.TR5': '37e7cd415ced1bb0bb2ada3bbd5bd90e7d394957',
    'data/CMENU/SNR/SNR7_JP.TR5': 'c7100f56071162fdb8eb735a8d31b4318ee37993',
    'data/CMENU/SNR/SNR8_JP.TR5': 'a16549f289cfa4a1db6f20f071ab570cbbd2b7e6',
}
MSG = 'data/TAI5MSG_JP.DAT'
# data/EVENT/*.TS5: SHA-1 over (file name + bytes) of every file in name order
EVENT_SHA1 = '263d7401a3a0149a6d519c15494ad1de532b19e9'

def events_sha1(game):
    import glob
    h = hashlib.sha1()
    for p in sorted(glob.glob(os.path.join(game, 'data', 'EVENT', '*.TS5'))):
        h.update(os.path.basename(p).encode())
        h.update(open(p, 'rb').read())
    return h.hexdigest()

def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()

def check(game):
    bad = []
    for rel, digest in CLEAN_SHA1.items():
        p = os.path.join(game, rel)
        if not os.path.exists(p):
            bad.append('%s: missing' % rel)
        elif sha1(p) != digest:
            bad.append('%s: SHA-1 does not match the clean v1.2.1 file' % rel)
    if events_sha1(game) != EVENT_SHA1:
        bad.append('data/EVENT/*.TS5: do not match the clean v1.2.1 files')
    if bad:
        sys.exit('\n'.join(bad))

def msg_json(n):
    return os.path.join(SCRIPT, 'msg', 'msg%02d.json' % n)

def msg_count():
    return len(os.listdir(os.path.join(SCRIPT, 'msg')))

def export_messages(game):
    os.makedirs(os.path.join(SCRIPT, 'msg'), exist_ok=True)
    data = open(os.path.join(game, MSG), 'rb').read()
    for n, strings in enumerate(msgfile.blocks(data)):
        rows = [{'id': i, 'jp': text.decode(s), 'en': ''} for i, s in enumerate(strings)]
        json.dump(rows, open(msg_json(n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def main():
    game = sys.argv[1] if len(sys.argv) > 1 else CLEAN
    check(game)
    export_messages(game)
    import tl
    ok = True
    for n in range(msg_count()):
        if os.path.exists(os.path.join(TL, 'msg%02d.txt' % n)):
            ok &= tl.apply(n)
    if not ok:
        sys.exit('errors in tl/: fix them and run setup again')
    print('script/ ready; now run tools/build.py')

if __name__ == '__main__':
    main()
