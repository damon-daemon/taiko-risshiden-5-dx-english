"""Loose strings of the exe (.rdata literals used by the code directly), i.e. strings
that are neither in the UI pointer table (ui.py) nor in a name table (tables.py).
The DX counterpart of the PS2 elfstr.py.

tl/exestr.txt: "VA<TAB>English" lines (VA in hex, \\n = newline, text.encode escapes).
The English goes into the .tl section (pesect.Segment) and every reference is
repointed; the Japanese stays. References:
  - rip-relative operands in .text (lea/mov ... [rip + disp32]): every position whose
    disp32 lands on the string is decoded (capstone) to check it is the displacement of
    a rip-relative instruction;
  - 8-aligned qwords equal to the string's VA in .rdata/.data (pointer tables; covered
    by base relocations, which still apply to the new value).
A string with no reference is an error (it may be reached by computed addresses).
printf conversion letters must match the Japanese (%y = %d; widths may differ).

  exestr.py check            errors of tl/exestr.txt
  exestr.py refs VA          references of a string
  exestr.py export           -> script/exestr.json: candidate strings (Japanese, refs, English)
"""
import collections, json, os, pickle, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'exestr.txt')
SCRIPT = os.path.join(ROOT, 'script', 'exestr.json')
CLEAN_EXE = os.path.join(ROOT, 'game_clean', 'Taiko5DX.exe')
CACHE = os.path.join(ROOT, 'build', 'exestr_refs.pickle')
IMAGE_BASE = 0x140000000
RDATA = (0x140B01000, 0x141039000)
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?[a-zA-Z]')

class Exe:
    def __init__(self, data):
        import pefile
        self.data = data
        pe = pefile.PE(data=bytes(data[:0x1000]), fast_load=True)
        self.secs = {s.Name.rstrip(b'\0'): (s.VirtualAddress + IMAGE_BASE, s.Misc_VirtualSize,
                                            s.PointerToRawData, s.SizeOfRawData) for s in pe.sections}

    def off(self, va):
        for a, n, p, r in self.secs.values():
            if a <= va < a + min(n, r):
                return va - a + p
        raise ValueError('%x not in the file' % va)

    def cstr(self, va):
        o = self.off(va)
        return bytes(self.data[o:self.data.index(b'\0', o)])

def _scan(exe):
    """{target: [(disp file offset, instruction end VA)]} for rip-relative operands
    into .rdata, and {target: [qword VA]} of pointers into .rdata."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    va0, n, p0, r = exe.secs[b'.text']
    d = exe.data
    lo, hi = RDATA
    code = collections.defaultdict(list)
    for k in range(4):
        m = memoryview(d[p0 + k:p0 + k + (min(n, r) - k) // 4 * 4]).cast('i')
        base = va0 + k + 4
        for j, disp in enumerate(m):
            t = base + 4 * j + disp
            if lo <= t < hi:
                pos = p0 + k + 4 * j           # file offset of the disp32
                pva = va0 + k + 4 * j
                for back in range(1, 9):       # instruction start before the disp
                    try:
                        i = next(md.disasm(bytes(d[pos - back:pos - back + 15]), pva - back), None)
                    except capstone.CsError:
                        i = None
                    if i is not None and i.disp_offset == back and i.disp_size == 4 and 'rip' in i.op_str \
                            and i.address + i.size + disp == t:
                        code[t].append((pos, i.address + i.size))
                        break
    data = collections.defaultdict(list)
    for name in (b'.rdata', b'.data'):
        a, n, p, r = exe.secs[name]
        m = memoryview(d[p:p + min(n, r) // 8 * 8]).cast('Q')
        for j, v in enumerate(m):
            if lo <= v < hi:
                data[v].append(a + 8 * j)
    return dict(code), dict(data)

def refs(exe):
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, 'rb'))
    r = _scan(exe)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(r, open(CACHE, 'wb'))
    return r

def load_tl():
    out = {}
    if os.path.exists(TL):
        for n, line in enumerate(open(TL, encoding='utf-8').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                assert tab, 'tl/exestr.txt:%d: no tab' % n
                out[int(k, 16)] = v.replace('\\n', '\n')
    return out

def fmts(b):
    """conversion letters (flags/width may differ: '%2d' -> '%d' is fine)"""
    return [m.group()[-1:].replace(b'y', b'd') for m in FMT.finditer(b)]

def ui_slots():
    import ui
    return set(range(ui.TABLE, ui.TABLE + 8 * ui.COUNT, 8))

def errors(exe, tl):
    code, data = refs(exe)
    slots = ui_slots()
    errs = []
    for va, en in sorted(tl.items()):
        if not (RDATA[0] <= va < RDATA[1]) or exe.data[exe.off(va) - 1] != 0:
            errs.append('exestr %x: not the start of a string in .rdata' % va)
            continue
        jp = exe.cstr(va)
        try:
            b = text.encode(en)
        except ValueError as e:
            errs.append('exestr %x: %s' % (va, e))
            continue
        if fmts(b) != fmts(jp):
            errs.append('exestr %x %r: conversions %s, Japanese has %s' % (va, en, fmts(b), fmts(jp)))
        d = [a for a in data.get(va, []) if a not in slots]
        if not code.get(va) and not d:
            errs.append('exestr %x %r: no reference found' % (va, en))
    return errs

def apply(seg):
    """Repoint the references of the strings in tl/exestr.txt to English in seg."""
    clean = Exe(open(CLEAN_EXE, 'rb').read())
    tl = load_tl()
    errs = errors(clean, tl)
    if errs:
        raise SystemExit('\n'.join(errs))
    code, data = refs(clean)
    slots = ui_slots()
    n = 0
    for va, en in tl.items():
        new = seg.add(text.encode(en) + b'\0')
        for pos, end in code.get(va, []):
            old = struct.unpack_from('<i', seg.exe, pos)[0]
            assert end + old == va, 'exestr %x: code at file %x already changed' % (va, pos)
            struct.pack_into('<i', seg.exe, pos, new - end)
            n += 1
        for a in data.get(va, []):
            if a not in slots:
                assert seg.get_q(a) == va
                seg.put_q(a, new)
                n += 1
    return len(tl), n

# ---------------------------------------------------------------- survey

def _is_text(b):
    i, jp = 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            if i + 1 >= len(b) or not (0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F):
                return False
            jp += 1
            i += 2
            continue
        if 0xA1 <= c <= 0xDF:
            jp += 1
        elif not (0x20 <= c < 0x7F or c in (0x0A, 0x1B)):
            return False
        i += 1
    return jp > 0

def candidates(exe):
    """[(VA, Japanese)] of Shift-JIS strings in .rdata that other tools do not cover."""
    import tables, ui
    covered = set()
    for i, p, b in ui.strings(exe.data):
        if p:
            covered.add(p)
    spans = [(va, va + st * cnt) for va, st, cnt, no, ro in tables.TABLES.values()]
    out = []
    a, n, p, r = exe.secs[b'.rdata']
    d = exe.data
    o, end = p, p + min(n, r)
    while o < end:
        if d[o] == 0:
            o += 1
            continue
        e = d.index(b'\0', o)
        b = bytes(d[o:e])
        va = a + o - p
        if _is_text(b) and va not in covered and not any(x <= va < y for x, y in spans):
            t = b.decode('cp932', 'replace')
            fw = len(re.findall('[぀-ヿ一-鿿！-～　-〿]', t))
            if '�' not in t and fw >= 1:
                out.append((va, b))
        o = e + 1
    return out

def export(exe):
    tl = load_tl()
    code, data = refs(exe)
    rows = [{'va': '%x' % va, 'code': len(code.get(va, [])), 'data': len(data.get(va, [])),
             'jp': text.decode(b), 'en': tl.get(va, '')} for va, b in candidates(exe)]
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return rows

if __name__ == '__main__':
    exe = Exe(open(CLEAN_EXE, 'rb').read())
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'check':
        print('\n'.join(errors(exe, load_tl())) or 'ok')
    elif cmd == 'refs':
        va = int(sys.argv[2], 16)
        code, data = refs(exe)
        print(text.decode(exe.cstr(va)))
        for pos, end in code.get(va, []):
            print('code %x' % (pos - exe.secs[b'.text'][2] + exe.secs[b'.text'][0]))
        for a in data.get(va, []):
            print('data %x' % a)
    elif cmd == 'export':
        print(len(export(exe)), 'strings ->', SCRIPT)
    else:
        print(__doc__)
