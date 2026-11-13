"""Port the PS2 v0.12.1 translation polish (notes/ps2_v0.12.1_polish.json) to the DX tl/.

usage: port_polish.py OUT_DIR [OLD NEW]   # writes OUT_DIR/msgNN.txt and OUT_DIR/NAME.txt batches
                                 # (units whose DX English == the PS2 'old') and
                                 # OUT_DIR/hand.txt (the rest, to do by hand)

msg: PS2 entry -> DX entry through port_msg's alignment, {01}C/J arguments remapped.
ev:  PS2 entry -> DX file and string through port_ev's alignment, escape ids remapped by
     position. A DX string that has its English from the memory is changed at the string
     the memory takes it from.
With two more arguments (PS2 git revisions OLD NEW) the msg change set is the difference
of the PS2 tl/msgNN.txt between them instead (e.g. 4f21e3a^ 4f21e3a = the "you" insert
fix, which must go in before the polish), and no event changes.
Apply the batches with tl.py apply NN / evtl.py apply NAME (one at a time per file).
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import evtl, msgscript, setup, text, tl
import port_ev, port_msg

POLISH = os.path.join(setup.ROOT, 'notes', 'ps2_v0.12.1_polish.json')

_BRIT = [(r'(?i)\b(hon|col|arm|fav|rum)or(?!ific|ary|ous|ious|at)',
          r'\1our'),
         (r'(?i)\btravel(ed|ing|er)', r'travell\1'), (r'(?i)\benroll\b', 'enrol'),
         (r'(?i)\bsaltpeter', 'saltpetre')]

def brit(s):
    """The DX tl/ uses British spelling (the PS2 text is American)."""
    if s is None:
        return None
    for a, b in _BRIT:
        s = re.sub(a, lambda m: m.expand(b) if not m.group()[0].isupper() or b[0] != 'e' and b[0] != 's'
                   else m.expand(b).capitalize(), s)
    return s

def msg(items, out, hand):
    g = {}
    for n in range(port_msg.NBLOCKS):
        for a, b in port_msg.align(port_msg.jp_rows(port_msg.PS2_JSON, n), [r['jp'] for r in tl.load(n)]).items():
            g[(n, a)] = (n, b)
    by = collections.defaultdict(list)
    for x in items:
        by[x['block']].append(x)
    stats = collections.Counter()
    for n, xs in sorted(by.items()):
        rows = tl.load(n)
        cur = tl.expand(tl.parse_tl(os.path.join(setup.TL, 'msg%02d.txt' % n)), rows)
        batch = []
        for x in xs:
            d = g.get((n, x['entry']))
            old, new = brit(port_msg.remap_en(x['old'], g)), brit(port_msg.remap_en(x['new'], g))
            tag = 'msg%02d @%d%s' % (n, d[1] if d else -1, '.%d' % x['unit'] if x['unit'] else '')
            now = cur.get((d[1], x['unit'])) if d else None
            if now is not None and brit(now) == old:
                batch += ['@%d%s' % (d[1], '.%d' % x['unit'] if x['unit'] else ''), new]
                stats['auto'] += 1
            elif now == new:
                stats['already'] += 1
            else:
                jp = ''
                if d:
                    toks, spans = msgscript.units(text.encode(rows[d[1]]['jp']))
                    if x['unit'] < len(spans):
                        a, z = spans[x['unit']]
                        jp = tl.unit_str(toks[a:z]).replace('\n', '⏎')
                hand.append((tag + '  (PS2 @%d)' % x['entry'], x['jp'], jp, old, new, now))
                stats['hand'] += 1
        if batch:
            open(os.path.join(out, 'msg%02d.txt' % n), 'w', encoding='utf-8').write('\n'.join(batch) + '\n')
    print('msg', dict(stats))

def ev(items, out, hand):
    pairs, d = port_ev.mapping()
    name_of = dict(pairs)
    mem_src = {}                # (kind, jp) -> (name, key) the memory takes it from
    own = {}
    for name in evtl.tl_entries():
        own[name] = evtl.parse_tl(evtl.tl_path(name))
        for k, n, ins, j in evtl.units_ro(name):
            src = own[name].get((k, n))
            if src is not None and src.strip() != '=':
                mem_src.setdefault((evtl.kind(ins, j), ins.strs[j]), (name, (k, n)))
    by = collections.defaultdict(list)
    for x in items:
        by[str(x['entry'])].append(x)
    batches = collections.defaultdict(dict)
    stats = collections.Counter()
    for entry, xs in sorted(by.items(), key=lambda t: int(t[0])):
        name = name_of[entry]
        dx = [(k, n, evtl.kind(ins, j), ins.strs[j]) for k, n, ins, j in evtl.units_ro(name)]
        ps = [(r[0], r[1], evtl.kind(type('I', (), {'op': r[2]}), r[3]), bytes.fromhex(r[4]), r[5])
              for r in d['entries'][entry]]
        m = port_ev.align([p[2] + port_ev.norm(p[3]) for p in ps], [x_[2] + port_ev.norm(x_[3]) for x_ in dx])
        pidx = {(p[0], p[1]): i for i, p in enumerate(ps)}
        for x in xs:
            k, n = (int(v) for v in x['key'][1:].split('.'))
            i = pidx[(k, n)]
            tag = '%s (PS2 %s %s)' % (name, entry, x['key'])
            if i not in m:
                hand.append((tag + ' no DX string', x['jp'], '', x['old'], x['new'], None))
                stats['hand'] += 1
                continue
            dk, dn, kd, djp = dx[m[i]]
            tag = '%s @%d.%d  (PS2 %s %s)' % (name, dk, dn, entry, x['key'])
            old = brit(port_ev.remap(x['old'], ps[i][3], djp))
            new = brit(port_ev.remap(x['new'], ps[i][3], djp))
            where = (name, (dk, dn))
            now = own.get(name, {}).get((dk, dn))
            if now is None and (kd, djp) in mem_src:
                where = mem_src[(kd, djp)]
                now = own[where[0]][where[1]]
            if batches[where[0]].get(where[1]) == new and new is not None:
                stats['auto (same memory string)'] += 1
            elif old is not None and now is not None and brit(now) == old:
                batches[where[0]][where[1]] = new
                stats['auto'] += 1
            elif new is not None and now == new:
                stats['already'] += 1
            else:
                hand.append((tag + ('' if where[0] == name and where[1] == (dk, dn) else
                                    '  [memory: %s @%d.%d]' % ((where[0],) + where[1])),
                             x['jp'], text.decode(djp).replace('\n', '⏎'),
                             old or x['old'], new or x['new'], now))
                stats['hand'] += 1
    for name, b in batches.items():
        with open(os.path.join(out, name + '.txt'), 'w', encoding='utf-8') as f:
            for (k, n), s in sorted(b.items()):
                f.write('@%d.%d\n%s\n' % (k, n, s))
    print('ev', dict(stats))

def git_changes(old, new):
    """msg change list from two revisions of the PS2 tl/."""
    import subprocess, tempfile
    items = []
    for n in range(port_msg.NBLOCKS):
        rows = json.load(open(port_msg.PS2_JSON % n, encoding='utf-8'))
        en = []
        for rev in (old, new):
            r = subprocess.run(['git', '-C', port_msg.PS2, 'show', '%s:tl/msg%02d.txt' % (rev, n)],
                               capture_output=True)
            if r.returncode:
                en.append({})
                continue
            with tempfile.NamedTemporaryFile('wb', suffix='.txt') as f:
                f.write(r.stdout)
                f.flush()
                en.append(tl.expand(tl.parse_tl(f.name), rows))
        for (e, u), s in sorted(en[1].items()):
            if en[0].get((e, u), s) != s:
                toks, spans = msgscript.units(text.encode(rows[e]['jp']))
                a, z = spans[u]
                items.append({'block': n, 'entry': e, 'unit': u, 'jp': tl.unit_str(toks[a:z]),
                              'old': en[0][(e, u)], 'new': s})
    return {'msg': items, 'ev': []}

def main():
    if len(sys.argv) not in (2, 4):
        sys.exit(__doc__)
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    p = git_changes(*sys.argv[2:]) if len(sys.argv) == 4 else json.load(open(POLISH, encoding='utf-8'))
    hand = []
    msg(p['msg'], out, hand)
    nm = len(hand)
    ev(p['ev'], out, hand)
    with open(os.path.join(out, 'hand.txt'), 'w', encoding='utf-8') as f:
        for i, (tag, pjp, djp, old, new, now) in enumerate(hand):
            f.write('%s\n  PS2 jp: %s\n  DX jp:  %s\n  old: %s\n  new: %s\n  now: %s\n\n'
                    % (tag, pjp.replace('\n', '⏎'), djp, old, new, now))
    print('%d by hand (%d msg, %d ev) -> hand.txt' % (len(hand), nm, len(hand) - nm))

if __name__ == '__main__':
    main()
