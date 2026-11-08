"""Scenario titles and intro texts (scenario choice of a new game).

data/CMENU/SNR/SNR0-8_JP.TR5 = scenarios 0-8 (ILNK; 0-7 = the PS2 scenarios 1-8, 8 = new
DX "Naniwa"). Subfile 0: +0x00 5 bytes (start date), +0x05 title[17], +0x16 intro[400].

tl/scenarios.txt: "N.title<TAB>text" and "N.intro<TAB>text" (N = SNR file number 0-8).
The intro panel wraps at any character (splits words), so the English is wrapped here at
WIDTH px (tl.widths; seen 2026-11-06: a 682 px line fits, 682+ wraps).
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import setup, tl

TL = os.path.join(setup.ROOT, 'tl', 'scenarios.txt')
SNR = 'data/CMENU/SNR/SNR%d_JP.TR5'
WIDTH = 660
FIELDS = {'title': (0x05, 17), 'intro': (0x16, 400)}

def load_tl():
    out = {}
    for line in open(TL, encoding='ascii').read().splitlines():
        if line.strip() and not line.startswith('#'):
            k, _, v = line.partition('\t')
            n, _, field = k.partition('.')
            out.setdefault(int(n), {})[field] = v.replace('\\n', '\n')
    return out

def wrap(text, width=WIDTH):
    w = tl.widths()
    lines, cur = [], ''
    for word in text.split(' '):
        cand = (cur + ' ' + word) if cur else word
        if sum(w[c] for c in cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return '\n'.join(lines)

def sub0(e):
    return struct.unpack_from('<I', e, 8)[0]

def apply(game):
    """-> {relative path: new bytes}."""
    files, errors = {}, []
    for n, fields in sorted(load_tl().items()):
        rel = SNR % n
        e = bytearray(open(os.path.join(game, rel), 'rb').read())
        a = sub0(e)
        for field, t in fields.items():
            off, size = FIELDS[field]
            b = (wrap(t) if field == 'intro' else t).encode('ascii')
            if len(b) >= size:
                errors.append('%s %d.%s: %d bytes, room %d' % (TL, n, field, len(b), size - 1))
                continue
            e[a + off:a + off + size] = b.ljust(size, b'\0')
        files[rel] = bytes(e)
    if errors:
        raise ValueError('\n'.join(errors))
    return files

def main():
    for n in range(9):
        e = open(os.path.join(setup.CLEAN, SNR % n), 'rb').read()
        a = sub0(e)
        for field, (off, size) in FIELDS.items():
            print('%d.%s\t%s' % (n, field, e[a + off:a + off + size].split(b'\0')[0].decode('cp932')))

if __name__ == '__main__':
    main()
