"""Name tables in the exe: fixed records with a name and its half-width kana reading.

The same 19 tables as the PS2 ELF (PS2 tools/elftables.py), same record layouts and
order; DX appends records to some (techniques, battle skills, items, schools) and
inserts title 103 (陰流). Each table has Chinese copies (SC/TC) elsewhere; only the
Japanese one is translated, in place.

English needs no reading, so a name may run on into the reading field: it may use
the bytes from the name up to the first data byte (measured from the clean exe over
all records: any non-zero byte that is not name or reading text), minus one for the
NUL. The town reading accessors return "" in Japanese mode (exepatch.TOWN_READING).

tl/tables/<table>.txt: "index<TAB>English" lines; missing indexes keep the Japanese.

  tables.py export      -> script/tables/<table>.json (index, Japanese, reading, English, room)
  tables.py todo        records without English
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'tables')
SCRIPT = os.path.join(ROOT, 'script', 'tables')
CLEAN_EXE = os.path.join(ROOT, 'game_clean', 'Taiko5DX.exe')
IMAGE_BASE = 0x140000000

# name: (VA of record 0, stride, count, name offset, reading offset)
TABLES = {
    'towns':      (0x140B512A0, 24, 310, 1, 12),
    'sights':     (0x140BB7980, 40, 58, 4, 19),
    'techniques': (0x140BB9A50, 40, 94, 0, 15),
    'battleskills': (0x140BBEE1C, 34, 75, 4, 20),
    'cards':      (0x140BEE3A0, 31, 55, 0, 15),
    'provinces':  (0x140C0D620, 24, 66, 0, 11),
    'items':      (0x140C14880, 40, 355, 0, 15),
    'ninja':      (0x140C25A70, 22, 30, 0, 9),
    'seas':       (0x140C26500, 28, 20, 0, 11),
    'offices':    (0x140C4A6C0, 26, 150, 0, 11),
    'schools':    (0x140C56650, 22, 25, 0, 9),
    'shops':      (0x140C56FE0, 18, 41, 0, 7),    # shop-name stems
    'pirates':    (0x140C57B90, 18, 30, 0, 7),    # pirate band names
    'courtranks': (0x141060CF0, 20, 15, 0, 9),
    'goods':      (0x1410612C0, 26, 100, 0, 9),
    'titles':     (0x140BBC660, 32, 106, 0, 16),  # honorary titles and school titles
    'missions':   (0x140C21090, 32, 150, 0, 0),   # mission (主命) names per role
    'tasks':      (0x140C25440, 14, 18, 0, 0),    # trade/production commands
    'regions':    (0x140C58740, 11, 19, 0, 0),
}

# Buffer limits from the PS2 audit (overflow.py there), not re-audited in DX.
LIMITS = {'techniques': (15, 'technique rename: strcpy into 16-byte stack buffers (PS2 0x32B488)')}

def _off(exe):
    import pefile
    pe = pefile.PE(data=bytes(exe[:0x1000]), fast_load=True)
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData) for s in pe.sections]
    def off(va):
        r = va - IMAGE_BASE
        for a, n, p in secs:
            if a <= r < a + n:
                return r - a + p
        raise ValueError(hex(va))
    return off

def _cstr(exe, o):
    return bytes(exe[o:exe.index(b'\0', o)])

def text_end(exe, name, off=None):
    """Offset (in the record) of the first data byte after the name that is not part
    of the name or reading text (over all records): the name may run on up to there."""
    va, stride, count, no, ro = TABLES[name]
    base = (off or _off(exe))(va)
    end = stride
    for i in range(count):
        o = base + i * stride
        text = set(range(no, no + len(_cstr(exe, o + no)) + 1)) | set(range(ro, ro + len(_cstr(exe, o + ro)) + 1))
        nz = next((k for k in range(no, stride) if exe[o + k] and k not in text), stride)
        end = min(end, nz)
    return end

def room(exe, name, off=None):
    return text_end(exe, name, off) - TABLES[name][3] - 1

def records(exe, name, off=None):
    va, stride, count, no, ro = TABLES[name]
    base = (off or _off(exe))(va)
    return [(i, _cstr(exe, base + i * stride + no), _cstr(exe, base + i * stride + ro)) for i in range(count)]

def load_tl(name):
    path = os.path.join(TL, name + '.txt')
    out = {}
    if os.path.exists(path):
        for n, line in enumerate(open(path, encoding='ascii').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                assert tab, '%s:%d: no tab' % (path, n)
                out[int(k)] = v
    return out

def apply(exe):
    """Write the English of every table into exe (bytearray, clean layout); returns the count."""
    off = _off(exe)
    clean = open(CLEAN_EXE, 'rb').read()
    n, errors = 0, []
    for name, (va, stride, count, no, ro) in TABLES.items():
        tl = load_tl(name)
        r = room(clean, name, off)
        limit, why = LIMITS.get(name, (r, ''))
        base = off(va)
        for i, en in sorted(tl.items()):
            b = en.encode('ascii')
            if i >= count:
                errors.append('%s %d: no such record (%d)' % (name, i, count))
            elif len(b) > r:
                errors.append('%s %d: %r is %d bytes, room %d' % (name, i, en, len(b), r))
            elif len(b) > limit:
                errors.append('%s %d: %r is %d bytes > %d: %s' % (name, i, en, len(b), limit, why))
            else:
                o = base + i * stride + no
                exe[o:o + r + 1] = b + bytes(r + 1 - len(b))
                n += 1
    if errors:
        raise ValueError('\n'.join(errors))
    return n

def export(exe):
    os.makedirs(SCRIPT, exist_ok=True)
    off = _off(exe)
    for name in TABLES:
        tl = load_tl(name)
        rows = [{'id': i, 'jp': jp.decode('cp932', 'replace'), 'reading': rd.decode('cp932', 'replace'),
                 'en': tl.get(i, '')} for i, jp, rd in records(exe, name, off)]
        json.dump({'room': room(exe, name, off), 'rows': rows},
                  open(os.path.join(SCRIPT, name + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

if __name__ == '__main__':
    exe = open(CLEAN_EXE, 'rb').read()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'export':
        export(exe)
        print('wrote', SCRIPT)
    elif cmd == 'todo':
        off = _off(exe)
        for name in TABLES:
            tl = load_tl(name)
            r = room(exe, name, off)
            for i, jp, rd in records(exe, name, off):
                if i not in tl:
                    print('%s\t%d\t%s\t%s\troom %d' % (name, i, jp.decode('cp932', 'replace'), rd.decode('cp932', 'replace'), r))
    elif cmd == 'check':
        print('%d names OK' % apply(bytearray(exe)))
    else:
        print(__doc__)
