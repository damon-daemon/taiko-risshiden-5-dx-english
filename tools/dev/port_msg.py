"""Port the PS2 project's English (tl/msgNN.txt) to the DX message file.

usage: port_msg.py map                 # print the PS2 -> DX entry alignment summary
       port_msg.py diff [NN]            # changed units not yet in tl/: PS2 JP, DX JP, PS2 English
       port_msg.py write [OUT_DIR]      # write tl/msgNN.txt for DX (default tl/)

Entries are aligned per block on their Japanese with the {01}C/{01}J insert arguments
and newlines ignored (difflib; replaced runs of equal length are paired in order, others
by similarity). Insert arguments are then remapped through the alignment (PS2 entry ->
DX entry), in the Japanese for comparison and in the English.

A DX unit gets the PS2 English when its Japanese equals the PS2 unit's (after remapping,
ignoring newlines and kana toggles). Units whose Japanese changed get the PS2 English as a
comment ('#~ @e.u  english') to re-translate from; entries with no PS2 match get nothing.
"""
import collections, difflib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import msgscript, setup, text, tl

PS2 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation')
PS2_JSON = os.path.join(PS2, 'script', 'msg', 'msg%02d.json')
PS2_TL = os.path.join(PS2, 'tl', 'msg%02d.txt')
NBLOCKS = 33

def jp_rows(path, n):
    return [r['jp'] for r in json.load(open(path % n, encoding='utf-8'))]

def key(jp, args=False):
    """Alignment key: tokens without newlines and kana toggles (and without insert
    arguments unless args)."""
    out = []
    for k, t in msgscript.tokens(text.encode(jp) if isinstance(jp, str) else jp):
        if k == 'nl' or tl.KANA_TOGGLE.fullmatch(t):
            continue
        if k == 'inline' and t[:1] == b'\x01' and len(t) == 4 and not args:
            t = t[:2]
        out.append(t)
    return b''.join(out)

def align(p, d):
    """PS2 rows, DX rows (Japanese) -> {ps2 entry: dx entry}."""
    pk, dk = [key(x) for x in p], [key(x) for x in d]
    sm = difflib.SequenceMatcher(None, pk, dk, autojunk=False)
    m = {}
    for op, a, b, c, e in sm.get_opcodes():
        if op == 'equal' or op == 'replace' and b - a == e - c:
            m.update({a + i: c + i for i in range(b - a)})
        elif op == 'replace':
            j = c
            for i in range(a, b):       # greedy, in order, by similarity
                best = max(range(j, e), key=lambda x: difflib.SequenceMatcher(
                    None, pk[i], dk[x], autojunk=False).ratio(), default=None)
                if best is not None and difflib.SequenceMatcher(
                        None, pk[i], dk[best], autojunk=False).ratio() > 0.6:
                    m[i] = best
                    j = best + 1
    return m

def remap_id(i, g):
    b, e = tl.target(i & 0xFF, i >> 8)
    t = g.get((b, e))
    if t is None:
        return None
    return t[1] if t[0] == 0 else t[0] * 1000 + t[1]

def remap_bytes(b, g):
    """Remap {01}C/{01}J arguments in message bytes (unmapped targets kept)."""
    out = []
    for k, t in msgscript.tokens(b):
        if k == 'inline' and t[:1] == b'\x01' and len(t) == 4 and t[1:2] in b'CJ':
            new = remap_id(t[2] | t[3] << 8, g)
            if new is not None:
                t = t[:2] + bytes([new & 0xFF, new >> 8])
        out.append(t)
    return b''.join(out)

_CODE = re.compile(r'\{01\}([CJ])((?:\{[0-9A-Fa-f]{2}\}|[^{}\\])(?:\{[0-9A-Fa-f]{2}\}|[^{}\\]))')

def remap_en(s, g):
    """Remap {01}C/J arguments written in a tl string."""
    def one(m):
        raw = text.encode(m.group(2))
        if len(raw) != 2:
            return m.group()
        new = remap_id(raw[0] | raw[1] << 8, g)
        if new is None:
            return m.group()
        return '{01}' + m.group(1) + tl.code_str(bytes([new & 0xFF, new >> 8]))
    return _CODE.sub(one, s)

def unit_keys(jp_bytes):
    toks, spans = msgscript.units(jp_bytes)
    return [key(b''.join(t for k, t in toks[a:z]), True) for a, z in spans]

_POOL = {}

def pool(g):
    """{unit key (PS2 Japanese, remapped): English} over all blocks."""
    if not _POOL:
        for n in range(NBLOCKS):
            p_rows = json.load(open(PS2_JSON % n, encoding='utf-8'))
            if not os.path.exists(PS2_TL % n):
                continue
            en = tl.expand(tl.parse_tl(PS2_TL % n), p_rows)
            for e, r in enumerate(p_rows):
                for u, k in enumerate(unit_keys(remap_bytes(text.encode(r['jp']), g))):
                    if (e, u) in en and k:
                        _POOL.setdefault((n, k), remap_en(en[(e, u)], g))
                        _POOL.setdefault((None, k), _POOL[(n, k)])
    return _POOL

def port_block(n, g):
    """-> tl lines, stats. A DX unit takes the English of the aligned PS2 unit if their
    Japanese is equal, else of any PS2 unit with that Japanese (this block first);
    otherwise the aligned unit's English becomes a '#~' comment."""
    p_rows = json.load(open(PS2_JSON % n, encoding='utf-8'))
    d_rows = tl.load(n)
    units = tl.parse_tl(PS2_TL % n) if os.path.exists(PS2_TL % n) else {}
    en = tl.expand(units, p_rows)
    inv = {d: p for (b, p), (b2, d) in g.items() if b == n}
    P = pool(g)
    out, stats = [], collections.Counter()
    for d in range(len(d_rows)):
        dk = unit_keys(text.encode(d_rows[d]['jp']))
        p = inv.get(d)
        pk = unit_keys(remap_bytes(text.encode(p_rows[p]['jp']), g)) if p is not None else []
        for u in range(len(dk)):
            tag = '@%d%s' % (d, '.%d' % u if u else '')
            if len(pk) == len(dk) and pk[u] == dk[u] and (p, u) in en:
                out += [tag, remap_en(en[(p, u)], g)]
                stats['ported'] += 1
            elif (n, dk[u]) in P or (None, dk[u]) in P:
                out += [tag, P.get((n, dk[u])) or P[(None, dk[u])]]
                stats['ported (by text)'] += 1
            elif p is not None and len(pk) == len(dk) and (p, u) in en:
                out.append('#~ %s  %s' % (tag, remap_en(en[(p, u)], g)))
                stats['changed'] += 1
            else:
                stats['new'] += 1
    return out, stats

def diff_block(n, g):
    """Print the changed ('#~') units of a block: PS2 JP, DX JP, PS2 English."""
    p_rows = json.load(open(PS2_JSON % n, encoding='utf-8'))
    d_rows = tl.load(n)
    en = tl.expand(tl.parse_tl(PS2_TL % n), p_rows) if os.path.exists(PS2_TL % n) else {}
    inv = {d: p for (b, p), (b2, d) in g.items() if b == n}
    P = pool(g)
    dx_tl = os.path.join(setup.TL, 'msg%02d.txt' % n)
    done = tl.expand(tl.parse_tl(dx_tl), d_rows) if os.path.exists(dx_tl) else {}
    def ustr(jp, u):
        toks, spans = msgscript.units(jp)
        a, z = spans[u]
        return tl.unit_str(toks[a:z]).replace('\n', '⏎')
    for d in range(len(d_rows)):
        db = text.encode(d_rows[d]['jp'])
        dk = unit_keys(db)
        p = inv.get(d)
        if p is None:
            continue
        pb = remap_bytes(text.encode(p_rows[p]['jp']), g)
        pk = unit_keys(pb)
        for u in range(len(dk)):
            if (n, dk[u]) in P or (None, dk[u]) in P or len(pk) != len(dk) or (d, u) in done:
                continue
            if pk[u] != dk[u] and (p, u) in en:
                print('@%d%s  (PS2 @%d)' % (d, '.%d' % u if u else '', p))
                print('  PS2: ' + ustr(pb, u))
                print('  DX:  ' + ustr(db, u))
                print('  EN:  ' + remap_en(en[(p, u)], g))

def header(n):
    """The leading comment lines of the PS2 tl file."""
    if not os.path.exists(PS2_TL % n):
        return []
    out = []
    for line in open(PS2_TL % n, encoding='utf-8'):
        if not line.startswith('#'):
            break
        out.append(line.rstrip('\n'))
    return out

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    g = {}
    for n in range(NBLOCKS):
        for a, b in align(jp_rows(PS2_JSON, n), [r['jp'] for r in tl.load(n)]).items():
            g[(n, a)] = (n, b)
    if cmd == 'map':
        for n in range(NBLOCKS):
            pairs = sorted((a, b) for (x, a), (y, b) in g.items() if x == n)
            runs, prev = [], None
            for a, b in pairs:
                if prev and b - a == prev[2] and a == prev[1] + 1:
                    prev[1] = a
                else:
                    prev = [a, a, b - a]
                    runs.append(prev)
            print('msg%02d: %s' % (n, ', '.join('%d-%d%+d' % tuple(r) for r in runs if r[2] or len(runs) > 1)))
    elif cmd == 'diff':
        for n in ([int(sys.argv[2])] if len(sys.argv) > 2 else range(NBLOCKS)):
            print('==== msg%02d' % n)
            diff_block(n, g)
    elif cmd == 'write':
        out_dir = sys.argv[2] if len(sys.argv) > 2 else setup.TL
        os.makedirs(out_dir, exist_ok=True)
        tot = collections.Counter()
        for n in range(NBLOCKS):
            lines, st = port_block(n, g)
            tot += st
            print('msg%02d %s' % (n, dict(st)))
            with open(os.path.join(out_dir, 'msg%02d.txt' % n), 'w', encoding='utf-8') as f:
                f.write('\n'.join(header(n) + lines) + '\n')
        print('total', dict(tot))
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
