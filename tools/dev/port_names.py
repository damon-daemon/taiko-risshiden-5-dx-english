"""Port person names from the PS2 translation (by Japanese (family, given) pair).

  port_names.py write    # tl/names_persons.json (keeps entries already in it: --keep)
  port_names.py new      # list pairs that got a romanized (not PS2) English

Pairs the PS2 lacks get Hepburn romaji of the DX reading (subfile 15) of the same
scenario; marked in build/names_new.txt for review.
"""
import collections, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import names, setup

PS2 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation')

def ps2_pairs():
    jp = json.load(open(os.path.join(PS2, 'script', 'names_persons.json'), encoding='utf-8'))
    tl = {d['id']: d for d in json.load(open(os.path.join(PS2, 'tl', 'names_persons.json'), encoding='utf-8'))}
    out = {}
    for d in jp:
        t = tl.get(d['id'])
        if t:
            for s, (f, g) in d['jp'].items():
                out[(f, g)] = tuple(t.get(s, t['en']))
    return out

def romanized(jp, rd):
    f, g = jp
    rf, rg = rd if rd else ('', '')
    return (names.romaji(rf) if f else '', names.romaji(rg) if g else '')

def port():
    nm, rd = names.all_names()
    ps2 = ps2_pairs()
    tab, new = {}, collections.OrderedDict()
    for pid in range(len(nm[0])):
        per = {}
        for n in names.SCENARIOS:
            jp = nm[n][pid]
            if not any(jp):
                continue
            if jp in ps2:
                per[n] = ps2[jp]
            else:
                r = rd[n][pid] if pid < len(rd[n]) else None
                per[n] = romanized(jp, r)
                new.setdefault(jp, (pid, n, r, per[n]))
        if not per:
            continue
        common = collections.Counter(per.values()).most_common(1)[0][0]
        r = {'id': pid, 'en': list(common)}
        for n, en in per.items():
            if en != common:
                r['s%d' % n] = list(en)
        tab[pid] = r
    return tab, new

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    tab, new = port()
    if cmd == 'write':
        names.save_tl(tab)
        with open(os.path.join(setup.ROOT, 'build', 'names_new.txt'), 'w', encoding='utf-8') as f:
            for jp, (pid, n, r, en) in new.items():
                f.write('%d\ts%d\t%s %s\t%s\t%s %s\n' % (pid, n, jp[0], jp[1], r, en[0], en[1]))
        print('%d persons, %d new pairs romanized -> build/names_new.txt' % (len(tab), len(new)))
    elif cmd == 'new':
        for jp, v in new.items():
            print(v[0], 's%d' % v[1], jp, v[2], v[3])
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
