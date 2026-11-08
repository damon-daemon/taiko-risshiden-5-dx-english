"""UI strings of the exe: the table of string pointers at the start of .data.

The table (0x141039000, 8-byte pointers into .rdata, null = unused) holds the PS2
ELF's 1650 UI strings in the same order, with about 2150 new entries in between
(DX features, debug labels). Each string is translated by writing the English into
the .tl section (pesect.py) and pointing its slot there; the Japanese stays.

tl/ui.txt: one line per string, "index<TAB>English" (\\n = newline), DX indexes.
Indexes missing from the file keep the Japanese. A line's printf conversions
(%d, %5d, %s, %u, %y, %w ...) must match the Japanese ones in order.

  ui.py export          -> script/ui.json (index, Japanese, English, PS2 index) for review
  ui.py todo [A B]      list entries without English (optionally index range)
"""
import json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'ui.txt')
SCRIPT = os.path.join(ROOT, 'script', 'ui.json')
CLEAN_EXE = os.path.join(ROOT, 'game_clean', 'Taiko5DX.exe')
TABLE, COUNT = 0x141039000, 3804
RDATA = (0x140B01000, 0x141039000)
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?[a-zA-Z]')

# Buffer limits carried over from the PS2 audit (overflow.py there), not re-audited in
# DX: temporary speaker name parts went to a 9-byte record field.
LIMITS = {}

# Kept Japanese on purpose: 506 "：" (the save/load screen crashes with ":", the code
# apparently searches other text for this exact separator).
KEEP = {506}

# Other pointer tables holding a slot's string: {table VA: first slot}, consecutive
# slots. 0x141067390 = chapter names 3621-3629 read when a save header is written.
ALIASES = {0x141067390: range(3621, 3630)}

def strings(exe):
    """[(index, pointer, bytes)] of the table (pointer 0 = no string)."""
    import pefile
    pe = pefile.PE(data=bytes(exe), fast_load=True)
    off = lambda va: pe.get_offset_from_rva(va - 0x140000000)
    t = off(TABLE)
    out = []
    for i in range(COUNT):
        p = struct.unpack_from('<Q', exe, t + 8 * i)[0]
        b = b''
        if p:
            assert RDATA[0] <= p < RDATA[1], 'ui %d: pointer %x outside .rdata' % (i, p)
            o = off(p)
            b = bytes(exe[o:exe.index(b'\0', o)])
        out.append((i, p, b))
    return out

def load_tl():
    out = {}
    if os.path.exists(TL):
        for n, line in enumerate(open(TL, encoding='utf-8').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                assert tab, 'tl/ui.txt:%d: no tab' % n
                out[int(k)] = v.replace('\\n', '\n')
    return out

def save_tl(tl):
    with open(TL, 'w', encoding='utf-8') as f:
        for i in sorted(tl):
            f.write('%d\t%s\n' % (i, tl[i].replace('\n', '\\n')))

def fmts(b):
    return [m.group().replace(b'%y', b'%d') for m in FMT.finditer(b)]

def errors(exe, tl):
    errs = []
    jps = {i: jp for i, p, jp in strings(exe) if p}
    for i, en in sorted(tl.items()):
        if i not in jps:
            errs.append('ui %d: no string in the table' % i)
            continue
        if i in KEEP:
            errs.append('ui %d: must stay Japanese (see KEEP)' % i)
            continue
        try:
            b = text.encode(en)
        except ValueError as e:
            errs.append('ui %d: %s' % (i, e))
            continue
        if fmts(b) != fmts(jps[i]):
            errs.append('ui %d %r: conversions %s, Japanese has %s'
                        % (i, en, fmts(b), fmts(jps[i])))
        if i in LIMITS and len(b) > LIMITS[i][0]:
            errs.append('ui %d %r: %d bytes > %d: %s' % (i, en, len(b), *LIMITS[i]))
    return errs

def apply(seg):
    """Point the slots of tl/ui.txt at English in seg (pesect.Segment)."""
    tl = load_tl()
    errs = errors(seg.exe, tl)
    if errs:
        raise SystemExit('\n'.join(errs))
    for i, en in tl.items():
        va = seg.add(text.encode(en) + b'\0')
        for t, slots in ALIASES.items():
            if i in slots:
                a = t + 8 * (i - slots[0])
                assert seg.get_q(a) == seg.get_q(TABLE + 8 * i), 'ui alias %x' % a
                seg.put_q(a, va)
        seg.put_q(TABLE + 8 * i, va)
    return len(tl)

def export(exe):
    tl = load_tl()
    rows = [{'id': i, 'jp': text.decode(jp), 'en': tl.get(i, '')}
            for i, p, jp in strings(exe) if p]
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return rows

def main():
    exe = open(CLEAN_EXE, 'rb').read()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'export':
        print(len(export(exe)), 'strings ->', SCRIPT)
    elif cmd == 'todo':
        lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, COUNT)
        tl = load_tl()
        for i, p, jp in strings(exe):
            if p and i not in tl and lo <= i < hi:
                print('%d\t%s' % (i, text.decode(jp).replace('\n', '\\n')))
    elif cmd == 'check':
        errs = errors(exe, load_tl())
        print('\n'.join(errs) or 'ok')
    else:
        print(__doc__)

if __name__ == '__main__':
    main()
