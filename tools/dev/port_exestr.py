"""Map the PS2 tl/elfstr.txt (loose ELF strings) onto DX: by the Japanese text.

  port_exestr.py report        how each PS2 entry maps (ui index / exe string / none)
  port_exestr.py write         add the loose ones with references to tl/exestr.txt
"""
import collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import exestr, text, ui

PS2 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation')
sys.path.insert(0, os.path.join(PS2, 'tools'))

def ps2_entries():
    import elfstr
    elf = open(os.path.join(PS2, 'extract', 'SLPM_662.67'), 'rb').read()
    tl = elfstr.load_tl()
    return [(va, elfstr.slot(elf, va)[0], en) for va, en in sorted(tl.items())]

def main():
    exe = exestr.Exe(open(exestr.CLEAN_EXE, 'rb').read())
    code, data = exestr.refs(exe)
    uis = collections.defaultdict(list)
    for i, p, b in ui.strings(exe.data):
        if p:
            uis[b].append(i)
    uitl = ui.load_tl()
    # all .rdata strings by bytes
    a, n, p, r = exe.secs[b'.rdata']
    d = exe.data
    where = collections.defaultdict(list)
    o, end = p, p + min(n, r)
    while o < end:
        if d[o] == 0:
            o += 1
            continue
        e = d.index(b'\0', o)
        where[bytes(d[o:e])].append(a + o - p)
        o = e + 1
    slots = exestr.ui_slots()
    out, stats = {}, collections.Counter()
    rows = []
    for va, jp, en in ps2_entries():
        if jp in uis:
            k = 'ui ' + ','.join('%d%s' % (i, '' if i in uitl else '(todo)') for i in uis[jp])
            stats['ui'] += 1
        else:
            vs = [v for v in where.get(jp, []) if code.get(v) or [x for x in data.get(v, []) if x not in slots]]
            if vs:
                k = 'exe ' + ' '.join('%x' % v for v in vs)
                for v in vs:
                    out[v] = en
                stats['exe'] += 1
            elif jp in where:
                k = 'noref ' + ' '.join('%x' % v for v in where[jp])
                stats['noref'] += 1
            else:
                k = 'missing'
                stats['missing'] += 1
        rows.append('%x\t%s\t%s\t%s' % (va, k, text.decode(jp).replace('\n', '\\n'), en.replace('\n', '\\n')))
    return rows, out, stats

if __name__ == '__main__':
    rows, out, stats = main()
    if sys.argv[1:] == ['report']:
        print('\n'.join(rows))
        print(dict(stats))
    elif sys.argv[1:] == ['write']:
        tl = exestr.load_tl()
        new = {k: v for k, v in out.items() if k not in tl}
        tl.update(new)
        with open(exestr.TL, 'w', encoding='utf-8') as f:
            f.write('# Loose exe strings: VA<TAB>English (see tools/exestr.py)\n')
            for k in sorted(tl):
                f.write('%x\t%s\n' % (k, tl[k].replace('\n', '\\n')))
        print('added', len(new), dict(stats))
    else:
        print(__doc__)
