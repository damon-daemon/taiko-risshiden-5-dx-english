"""Port the PS2 project's event English (tl/ev/NNN.txt) to the DX event files.

usage: (once) ~/Projects/taiko_risshiden_5_translation/.venv/bin/python tools/dev/ps2_ev_dump.py build/ps2_ev.json
       port_ev.py map             # PS2 entry <-> DX file summary
       port_ev.py write [OUT_DIR] # write tl/ev/NAME.txt (default tl/ev) + tl/names_persons.json

DX files (sorted by name) are the PS2 script entries 244, 246, ... 574 in order, plus three
new ones (NEW). Per file the strings (all scripts, in order) are aligned on their Japanese
with person ids (\\#XXXX) ignored and kana folded (difflib; replaced runs of equal length
are paired in order, others by similarity).

A DX string gets the PS2 English when its normalised Japanese equals the PS2 string's;
escapes are remapped (the PS2 \\#XXXX of the Japanese -> the DX one at the same place).
Strings whose Japanese changed get '#~ @k.n  PS2 English' comments. A string whose English
the memory (an identical Japanese string earlier in tl/ev) already gives is not written.
Names (5A speaker, 3C) are skipped (names step).
"""
import collections, difflib, json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import evtl, setup, text

DUMP = os.path.join(setup.ROOT, 'build', 'ps2_ev.json')
NEW = {'EFF1E300', 'EFF27500', 'EFF2D500'}
PERSON = re.compile(rb'\\#([0-9A-Fa-f]{4})')

def mapping():
    names = [n for n in evtl.script_entries() if n not in NEW]
    d = json.load(open(DUMP, encoding='utf-8'))
    entries = sorted(d['entries'], key=int)
    assert len(names) == len(entries), (len(names), len(entries))
    return list(zip(entries, names)), d

def esc_kind(e):
    """Escape (bytes, no backslash) -> its kind without the id: '#', '%02', 'A', ..."""
    if e[:1] == b'#':
        return '#'
    if e[:1] == b'%':
        return e[:3].decode()
    return e[:1].decode()

def norm(b):
    """Comparison key of a Japanese string: escape ids dropped, kana folded."""
    s = text.decode(evtl.ESC.sub(lambda m: b'\\' + esc_kind(m.group(1)).encode() + b'~', b))
    s = unicodedata.normalize('NFKC', s)
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in s)

def align(pk, dk):
    sm = difflib.SequenceMatcher(None, pk, dk, autojunk=False)
    m = {}
    for op, a, b, c, e in sm.get_opcodes():
        if op == 'equal' or op == 'replace' and b - a == e - c:
            m.update({a + i: c + i for i in range(b - a)})
        elif op == 'replace':
            j = c
            for i in range(a, b):
                best = max(range(j, e), key=lambda x: difflib.SequenceMatcher(
                    None, pk[i], dk[x], autojunk=False).ratio(), default=None)
                if best is not None and difflib.SequenceMatcher(
                        None, pk[i], dk[best], autojunk=False).ratio() > 0.6:
                    m[i] = best
                    j = best + 1
    return m

def remap(src, pjp, djp):
    """PS2 English src -> with the DX escapes (paired by position in the Japanese), or
    None if they don't pair up."""
    pe = [m.group(1) for m in evtl.ESC.finditer(pjp)]
    de = [m.group(1) for m in evtl.ESC.finditer(djp)]
    if [esc_kind(x) for x in pe] != [esc_kind(x) for x in de]:
        return None
    sub = {}
    for a, b in zip(pe, de):
        a, b = a.decode().upper(), b.decode()
        if sub.setdefault(a, b) != b:
            return None
    pat = evtl.ESC.pattern.decode()
    return re.sub(pat, lambda m: '\\' + sub.get(m.group(1).upper(), m.group(1)), src)

def port():
    """-> {name: [(k, n, kind, dx jp, src or None, old English or None)]}, person pairs."""
    pairs, d = mapping()
    out, persons = {}, collections.Counter()
    glob_ = {}                  # normalised key -> (PS2 Japanese, English), any entry
    for rows in d['entries'].values():
        for r in rows:
            if r[5] is not None:
                p = (evtl.kind(type('I', (), {'op': r[2]}), r[3]), bytes.fromhex(r[4]))
                glob_.setdefault(p[0] + norm(p[1]), (p[1], r[5]))
    for entry, name in pairs + [(None, n) for n in sorted(NEW)]:
        dx = [(k, n, evtl.kind(ins, j), ins.strs[j]) for k, n, ins, j in evtl.units_ro(name)]
        ps = [(r[0], r[1], evtl.kind(type('I', (), {'op': r[2]}), r[3]), bytes.fromhex(r[4]), r[5])
              for r in d['entries'][entry]] if entry else []
        pk = [p[2] + norm(p[3]) for p in ps]
        dk = [x[2] + norm(x[3]) for x in dx]
        m = align(pk, dk) if ps else {}
        back = {v: k for k, v in m.items()}
        rows = []
        for i, (k, n, kd, jp) in enumerate(dx):
            src = old = None
            if kd != 'name' and i in back:
                p = ps[back[i]]
                for a, b in zip(PERSON.findall(p[3]), PERSON.findall(jp)):
                    persons[(int(a, 16) & 0x7FF, int(b, 16) & 0x7FF)] += 1
                if p[4] is not None:
                    en = remap(p[4], p[3], jp)
                    if pk[back[i]] == dk[i] and en is not None:
                        src = en
                    else:
                        old = en if en is not None else p[4]
            if kd != 'name' and src is None and dk[i] in glob_:
                g = glob_[dk[i]]
                src = remap(g[1], g[0], jp)
                if src is not None:
                    old = None
            rows.append((k, n, kd, jp, src, old))
        out[name] = rows
    return out, persons, d

def person_table(persons, d):
    best = {}
    for (p, x), c in persons.most_common():
        best.setdefault(x, p)
    out = []
    for x in sorted(best):
        names = d['persons'].get(str(best[x]))
        if names:
            r = {'id': x, 'en': names[0]}
            for i, v in enumerate(names[1:]):
                r['v%d' % i] = v      # other scenario forms (widths only)
            out.append(r)
    return out

def write(out_dir):
    res, persons, d = port()
    mem = {}
    tot = collections.Counter()
    os.makedirs(out_dir, exist_ok=True)
    for name, rows in res.items():
        lines = []
        for k, n, kd, jp, src, old in rows:
            key = (kd, jp)
            if kd == 'name':
                continue
            tot['strings'] += 1
            if src is not None:
                tot['ported'] += 1
                if mem.get(key) == src:
                    continue
                mem.setdefault(key, src)
                lines += ['@%d.%d' % (k, n), src]
            elif key in mem:
                tot['memory'] += 1
            else:
                tot['old' if old else 'new'] += 1
                if old:
                    lines.append('#~ @%d.%d  %s' % (k, n, old))
        if lines:
            with open(os.path.join(out_dir, name + '.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
    print(dict(tot))
    return persons, d

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'map':
        pairs, d = mapping()
        for entry, name in pairs:
            print(entry, name)
        print('new:', ' '.join(sorted(NEW)))
    elif cmd == 'write':
        out = sys.argv[2] if len(sys.argv) > 2 else evtl.TL_EV
        persons, d = write(out)
        tab = person_table(persons, d)
        json.dump(tab, open(os.path.join(setup.TL, 'names_persons.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=0)
        print('%d persons -> tl/names_persons.json' % len(tab))
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
