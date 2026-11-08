"""Endings list (DX feature): 39 endings x title / unlock hint / epilogue text.

The exe holds three tables (JP 0x140C26CE0, SC 0x140C308C0, TC 0x140C3A4A0) of 39
entries, stride 0x3FF: title[0x15] at +0, hint[0x1F5] at +0x15, text[0x1F5] at +0x20A.
The only accessor 0x140432100 (ending index -> entry; rbx = index * 0x3FF) has four
callers that use the entry pointer + 0 / + 0x15 / + 0x20A (offsets shared by all
languages, so they stay). English needs more room for the text, so the JP table is
rebuilt in .tl with stride 3 * 0x3FF (title < 21 bytes, hint < 501, text < 2557) and
the accessor's JP path (0x14043215C) returns that table.

tl/endings.txt: "N.title<TAB>text", "N.hint<TAB>text", "N.text<TAB>text" (\\n = newline,
N = 0-38). The panels wrap at any character, so text is pre-wrapped here at WIDTH px
(paragraphs = \\n in the source).

  endings.py export   -> script/endings.json (Japanese)
  endings.py check [FILE]   sizes / missing entries (of tl/endings.txt or FILE)
"""
import json, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import setup, tl

TL = os.path.join(setup.ROOT, 'tl', 'endings.txt')
SCRIPT = os.path.join(setup.ROOT, 'script', 'endings.json')
COUNT, STRIDE = 39, 0x3FF
JP_TABLE = 0x140C26CE0
FIELDS = {'title': (0, 0x15), 'hint': (0x15, 0x1F5), 'text': (0x20A, 3 * STRIDE - 0x20A)}
WIDTH = {'hint': 940, 'text': 940}   # tl px (half cell 17); panel box 0x350 = 848 px at half 15
ACCESSOR_JP = 0x14043215C
ACCESSOR_OLD = '48 8d 80 e0 6c c2 00 48 03 c3 48 83 c4 20 5b c3'

def load_tl(path=TL):
    out = {}
    if os.path.exists(path):
        for n, line in enumerate(open(path, encoding='ascii').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                assert tab, 'tl/endings.txt:%d: no tab' % n
                i, _, field = k.partition('.')
                assert field in FIELDS, 'tl/endings.txt:%d: bad key %r' % (n, k)
                out.setdefault(int(i), {})[field] = v.replace('\\n', '\n')
    return out

def wrap(text, width):
    if not width:
        return text
    w = tl.widths()
    out = []
    for para in text.split('\n'):
        # leading spaces kept; lines wrapped from a "- " bullet or an indented
        # line continue indented by two spaces
        body = para.lstrip(' ')
        lead = para[:len(para) - len(body)]
        cont = '  ' if (lead or body.startswith('- ')) else ''
        lines, cur = [], lead
        for word in body.split(' '):
            cand = (cur + ' ' + word) if cur.strip() else cur + word
            if sum(w[c] for c in cand) <= width or not cur.strip():
                cur = cand
            else:
                lines.append(cur)
                cur = cont + word
        lines.append(cur)
        out.append('\n'.join(lines))
    return '\n'.join(out)

def entries(exe):
    """Japanese entries [{title, hint, text}] of the clean exe."""
    import pefile
    pe = pefile.PE(data=bytes(exe), fast_load=True)
    out = []
    for i in range(COUNT):
        o = pe.get_offset_from_rva(JP_TABLE + i * STRIDE - 0x140000000)
        f = lambda a, n: exe[o + a:o + a + n].split(b'\0')[0]
        out.append({k: f(a, 0x15 if k == 'title' else 0x1F5) for k, (a, _) in FIELDS.items()})
    return out

def build(exe, path=TL):
    """-> (table bytes, errors). Untranslated fields keep the Japanese."""
    jp, en, errors = entries(exe), load_tl(path), []
    table = bytearray(COUNT * 3 * STRIDE)
    for i in range(COUNT):
        for k, (a, room) in FIELDS.items():
            s = en.get(i, {}).get(k)
            b = jp[i][k] if s is None else wrap(s, WIDTH.get(k)).encode('cp932')
            if len(b) >= room:
                errors.append('%d.%s: %d bytes > %d' % (i, k, len(b), room - 1))
                b = b[:room - 1]
            table[i * 3 * STRIDE + a:i * 3 * STRIDE + a + len(b)] = b
    return bytes(table), errors

def apply(seg):
    """Put the table into .tl and point the JP accessor at it. -> translated entries."""
    table, errors = build(seg.exe)
    if errors:
        raise SystemExit('endings: ' + '; '.join(errors))
    base = seg.add(table, align=16, share=False)
    # lea rbx, [rbx+rbx*2]; lea rax, [rip+table]; add rax, rbx; add rsp, 0x20; pop rbx; ret
    code = (bytes.fromhex('48 8d 1c 5b 48 8d 05') +
            struct.pack('<i', base - (ACCESSOR_JP + 11)) +
            bytes.fromhex('48 01 d8 48 83 c4 20 5b c3'))
    o = seg.va2off(ACCESSOR_JP)
    assert seg.exe[o:o + 16] == bytes.fromhex(ACCESSOR_OLD), 'endings accessor changed'
    end = o + 16
    while seg.exe[end] == 0xCC:
        end += 1
    assert len(code) <= end - o - 1, 'endings stub too long'
    seg.exe[o:o + len(code)] = code
    return len(load_tl())

def main():
    exe = open(os.path.join(setup.CLEAN, 'Taiko5DX.exe'), 'rb').read()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'export':
        out = [{'n': i, **{k: v.decode('cp932') for k, v in e.items()}}
               for i, e in enumerate(entries(exe))]
        json.dump(out, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('wrote', SCRIPT)
    elif cmd == 'check':
        path = sys.argv[2] if len(sys.argv) > 2 else TL
        _, errors = build(exe, path)
        en = load_tl(path)
        missing = ['%d.%s' % (i, k) for i in range(COUNT) for k in FIELDS
                   if k not in en.get(i, {})]
        for e in errors:
            print('ERROR', e)
        print('%d errors, %d fields untranslated' % (len(errors), len(missing)))
        if missing and len(missing) < 20:
            print(' '.join(missing))

if __name__ == '__main__':
    main()
