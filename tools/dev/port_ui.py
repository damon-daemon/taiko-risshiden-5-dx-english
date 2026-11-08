"""Port the PS2 tl/ui.txt to DX indexes (writes tl/ui.txt; existing lines win).

Aligned entries (same Japanese, difflib over the two tables) take the PS2 English;
new DX entries whose Japanese equals a PS2 string with one English take that.
usage: .venv/bin/python tools/dev/port_ui.py [write]
"""
import collections, difflib, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import text, ui

PS2 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation/script/ui.json')   # Japanese
PS2_TL = os.path.expanduser('~/Projects/taiko_risshiden_5_translation/tl/ui.txt')    # English

def main():
    exe = open(ui.CLEAN_EXE, 'rb').read()
    dx = {i: text.decode(jp) for i, p, jp in ui.strings(exe) if p}
    ps2 = json.load(open(PS2, encoding='utf-8'))
    en = {}
    for l in open(PS2_TL, encoding='ascii').read().splitlines():
        k, _, v = l.partition('\t')
        if l.strip() and '@' not in k:
            en[int(k)] = v.replace('\\n', '\n')
    for e in ps2:
        e['en'] = en.get(e['id'], '')
    a = [e['jp'] for e in ps2]
    keys = sorted(dx)
    b = [dx[i] for i in keys]
    tl = ui.load_tl()
    new = {}
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, a1, a2, b1, b2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(a2 - a1):
                if ps2[a1 + k]['en']:
                    new[keys[b1 + k]] = ps2[a1 + k]['en']
    by_jp = collections.defaultdict(set)
    for e in ps2:
        if e['en']:
            by_jp[e['jp']].add(e['en'])
    # PS2 loose ELF strings (tl/elfstr.txt by vaddr) and name tables, by Japanese
    P = os.path.dirname(PS2_TL)
    jp_va = {e['va']: e['jp'] for e in json.load(open(os.path.join(P, '..', 'script', 'elfstr.json'), encoding='utf-8'))}
    for l in open(os.path.join(P, 'elfstr.txt'), encoding='utf-8').read().splitlines():
        k, _, v = l.partition('\t')
        if l.strip() and not l.startswith('#') and k in jp_va:
            by_jp[jp_va[k]].add(v.replace('\\n', '\n'))
    T = os.path.join(P, '..', 'script', 'tables')
    for fn in sorted(os.listdir(T)):
        tt = os.path.join(P, 'tables', fn[:-5] + '.txt')
        if not os.path.exists(tt):
            continue
        en = dict(l.split('\t', 1) for l in open(tt, encoding='utf-8').read().splitlines() if '\t' in l)
        for r in json.load(open(os.path.join(T, fn), encoding='utf-8'))['rows']:
            if en.get(str(r['id'])):
                by_jp[r['jp']].add(en[str(r['id'])])
    n_dict = 0
    for i in keys:
        if i not in new and len(by_jp.get(dx[i], ())) == 1:
            new[i] = next(iter(by_jp[dx[i]]))
            n_dict += 1
    n = 0
    for i, en in new.items():
        if i not in tl:
            tl[i] = en
            n += 1
    print('aligned+dict %d (dict %d), added %d, total %d of %d' % (len(new), n_dict, n, len(tl), len(dx)))
    if sys.argv[1:] == ['write']:
        ui.save_tl(tl)
        print('wrote', ui.TL)
        print('\n'.join(ui.errors(exe, tl)) or 'check ok')

main()
