"""Translation helper for the event scripts (data/EVENT/*.TS5, see tools/evscript.py).

(Port of the PS2 project's evtl.py; same tl/ev format, files named after the TS5 file.)

tl/ev/NAME.txt holds the English of data/EVENT/NAME.TS5 (no Japanese), one block per string:

    # comment
    #~ @<script>.<n>  old English (PS2 text of a string whose Japanese changed in DX)
    #ps2 @<script>.<n>  PS2 English of a string DX toned down (kept for a switch back)
    @<script>.<n>     string n (0, 1, ... in script order) of script <script>
    English text, possibly over several physical lines (joined with spaces).

  \\n or ||  forced line break        \\_  a space that line stripping would eat
  =          (whole block) keep the Japanese
  In a batch, a line '#soft' right before '@k.n' marks a string DX toned down (wording
  about suicide, executions, Korea...): its '#~' PS2 English is kept as '#ps2 @k.n'.
  Escapes are copied from `show` as printed and may move: \\#XXXX person name
  (XXXX & 0x7FF = person id; +0x800 given name, +0x1000 family name), \\%NN pronoun /
  address word (msg00, English already; \\%02 \\%04 \\%20 take 3 more hex digits, a
  person id), \\&NN, \\Xnnn (dates, ages, places, numbers...). \\%NN may be dropped, the
  others must stay. '%' becomes full-width ％ (the window treats it as a control character).

Strings without English of their own take the English of an identical Japanese string of
the same kind elsewhere in tl/ev (the memory: first file, script order), so a repeated
line is translated once.

Dialogue (11, 12, 13, 5A text) is wrapped to the message window (680 px, 40 characters,
3 lines a page) and may use more pages than the Japanese (a warning); choices (15) and
labels (1E 4A 42) must fit the widest Japanese line. Names (5A speaker, 3C rename) are
kept Japanese for now (names step).

usage:
    evtl.py show  NAME [script|a-b] [--todo]  # print the Japanese strings (--todo: only
                                          # those without English, own or from the memory;
                                          # 'old:' = PS2 English of a changed string)
    evtl.py apply NAME [batch.txt]        # merge a batch into tl/ev/NAME.txt and validate
    evtl.py check NAME batch.txt          # validate a batch only (writes nothing)
    evtl.py stats                         # progress per file
"""
import functools, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import evscript, setup, text, tl

ROOT = setup.ROOT
TL_EV = os.path.join(setup.TL, 'ev')
EVENT_DIR = 'data/EVENT'

FULL_PX, HALF_PX = tl.FULL_PX, tl.HALF_PX
WINDOW = tl.WINDOW                      # (680, 3)
LINE_CHARS = tl.LINE_CHARS              # 40
NARRATION = (tl.ps2(432), 3)            # 13: centred narration box (PS2 estimate; verify)
LABEL_PX = {0x15: tl.ps2(240)}          # choice menu items (PS2 assumption; verify)
DIALOGUE = {0x11, 0x12, 0x13}           # + the text (third string) of 5A
# Escapes when shown (px at half cell 17, characters). Person names: PS2 widths (in DX
# cells) until the DX name table exists (names step); \X values as in the PS2 project.
NAME_PX, NAME_CHARS = tl.ps2(150), 20   # full name (unknown person)
FAMILY_PX = tl.ps2(100)                 # \#: +0x1000 family / +0x800 given name only
VAR_PX, VAR_CHARS = tl.ps2(80), 12      # \Xnnn values (numbers, dates)
NAME_VAR_PX = {'3': NAME_PX}            # \3 person, places/clans/houses/items/regions
NAME_VAR_PX.update((c, tl.ps2(120)) for c in '456=<;NeABCDEFG>')
# \%NN: widest English of the msg00 entry it inserts (measured with the PS2 table of
# \% cases -> msg00 entries; the others insert nothing visible)
PRONOUN = {0: (6, 1), 1: (44, 3), 2: (156, 11), 3: (234, 17), 4: (234, 17), 32: (234, 17),
           39: (46, 3), 43: (32, 2), 44: (32, 2), 48: (32, 2)}

ESC = re.compile(rb'\\(#[0-9A-Fa-f]{4}|%(?:02|04|20)[0-9A-Fa-f]{3}|%[0-9A-Fa-f]{2}|&[0-9A-Fa-f]{2}'
                 rb'|[0-9;<=>?A-Za-z][0-9A-Fa-f]{3})')
FULL_LATIN = re.compile('[０-９Ａ-Ｚａ-ｚ]')
_entry = [None]                 # file being measured (for \Z00n)

# ---------------------------------------------------------------- data access

def event_path(name, game=None):
    return os.path.join(game or setup.CLEAN, EVENT_DIR, name + '.TS5')

@functools.lru_cache(None)
def clean_entry(name):
    return open(event_path(name), 'rb').read()

@functools.lru_cache(None)
def script_entries():
    out = []
    for p in sorted(glob.glob(os.path.join(setup.CLEAN, EVENT_DIR, '*.TS5'))):
        name = os.path.basename(p)[:-4]
        if evscript.is_script(clean_entry(name)):
            out.append(name)
    return out

def units(name):
    """-> (Entry, [(script, n, ins, j)]) for every string of the file (fresh parse)."""
    e = evscript.Entry(clean_entry(name))
    out = []
    for k, (items, _) in enumerate(e.scripts):
        for n, (path, ins, j) in enumerate(evscript.strings(items)):
            out.append((k, n, ins, j))
    return e, out

@functools.lru_cache(None)
def units_ro(name):
    return units(name)[1]

def kind(ins, j):
    if ins.op in DIALOGUE or ins.op == 0x5A and j == 2:
        return 'dialogue'
    if ins.op == 0x3C or ins.op == 0x5A:
        return 'name'
    return 'label'

@functools.lru_cache(None)
def person_names():
    """DX person id -> list of English (family, given) from tl/names_persons.json (if any)."""
    p = os.path.join(setup.TL, 'names_persons.json')
    if not os.path.exists(p):
        return {}
    out = {}
    for r in json.load(open(p, encoding='utf-8')):
        forms = [r['en']] + [v for k, v in r.items() if re.fullmatch(r'[sv]\d+', k)]
        out[r['id']] = [f for f in forms if isinstance(f, list)]
    return out

# ---------------------------------------------------------------- measuring

def esc_size(e):
    """(px, characters) of an escape (without the backslash) when shown in English."""
    c = e[:1]
    if c == b'#':
        v = int(e[1:], 16)
        pid, form = v & 0x7FF, v & 0x3800
        if form == 0x2000:
            return 0, 0
        names = person_names().get(pid)
        if not names:
            return (NAME_PX if form == 0 else FAMILY_PX), NAME_CHARS
        parts = [n[1] if form == 0x800 else n[0] if form == 0x1000 else '%s %s' % tuple(n)
                 for n in names]
        return (max(measure_text(p.encode('cp932'))[0] for p in parts), max(len(p) for p in parts))
    if c == b'%':
        return PRONOUN.get(int(e[1:3], 16), (0, 0))
    if c == b'&':
        return NAME_PX, NAME_CHARS
    if c == b'Z':
        slots = z_slots()
        w = slots.get((_entry[0], int(e[1:], 16))) or slots.get((None, int(e[1:], 16)))
        return w or (VAR_PX, VAR_CHARS)
    if chr(c[0]) in NAME_VAR_PX:
        return NAME_VAR_PX[chr(c[0])], NAME_CHARS
    return VAR_PX, VAR_CHARS

_z_busy = [False]

@functools.lru_cache(None)
def z_slots():
    """{(file or None, slot): (px, chars)} = widest English an op 1E puts in \\Z00<slot>
    (slot = head byte 1), per file and over all files."""
    if _z_busy[0]:
        return {}
    _z_busy[0] = True
    out, mem, own = {}, memory(), set(tl_entries())
    try:
        for name in script_entries():
            en = parse_tl(tl_path(name)) if name in own else {}
            for k, n, ins, j in units_ro(name):
                if ins.op != 0x1E:
                    continue
                src = en.get((k, n)) or mem.get((kind(ins, j), ins.strs[j]))
                b = english_bytes(src) if src and src.strip() != '=' else ins.strs[j]
                px, nc = measure(b)
                for key in ((name, ins.head[1]), (None, ins.head[1])):
                    o = out.get(key, (0, 0))
                    out[key] = (max(o[0], px), max(o[1], nc))
    finally:
        _z_busy[0] = False
    return out

def measure_text(b, jp=False):
    """(px, characters) of plain bytes. jp: half-width kana count full width (events
    write hiragana as half-width kana; the voicing marks combine)."""
    W = tl.widths()
    px = nc = i = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            px += FULL_PX; nc += 1; i += 2
            continue
        if c >= 0x80:
            if jp and c in (0xDE, 0xDF):
                pass
            else:
                px += FULL_PX if jp and 0xA1 <= c <= 0xDD else HALF_PX
                nc += 1
        else:
            px += W.get(chr(c), HALF_PX)
            nc += 1
        i += 1
    return px, nc

def measure(line, jp=False):
    px = nc = 0
    pos = 0
    for m in ESC.finditer(line):
        a, b = measure_text(line[pos:m.start()], jp)
        c, d = esc_size(m.group(1))
        px += a + c; nc += b + d
        pos = m.end()
    a, b = measure_text(line[pos:], jp)
    return px + a, nc + b

def wrap(s, width, chars=None):
    """Word-wrap bytes s (b'\\n' = forced break) to width px (and chars) -> lines."""
    out = []
    for para in s.split(b'\n'):
        line = b''
        for w in [w for w in para.split(b' ') if w]:
            cand = line + b' ' + w if line else w
            px, nc = measure(cand)
            if line and (px > width or chars and nc > chars):
                out.append(line)
                line = w
            else:
                line = cand
        out.append(line)
    return out

# ---------------------------------------------------------------- tl files

def tl_path(name):
    return os.path.join(TL_EV, name + '.txt')

KEY = re.compile(r'@(\d+)\.(\d+)\s*')
OLD_EN = re.compile(r'#~ @(\d+)\.(\d+)  ')

def parse_tl(path):
    """-> {(script, n): text}"""
    out, key, buf = {}, None, []
    def flush():
        if key is not None:
            out[key] = ' '.join(buf)
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        m = KEY.fullmatch(line)
        if m:
            flush()
            key, buf = (int(m.group(1)), int(m.group(2))), []
        elif line.lstrip().startswith('#'):
            continue
        elif key is not None and line.strip():
            buf.append(line.strip())
    flush()
    return out

def parse_old(path):
    """-> {(script, n): old English} from '#~ @k.n  text' comments."""
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            m = OLD_EN.match(line)
            if m:
                out[(int(m.group(1)), int(m.group(2)))] = line[m.end():].rstrip('\n')
    return out

def parse_soft(path):
    """Keys marked '#soft' in a batch."""
    out, mark = set(), False
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line == '#soft':
            mark = True
            continue
        m = KEY.fullmatch(line)
        if m and mark:
            out.add((int(m.group(1)), int(m.group(2))))
        if line:
            mark = False
    return out

def write_tl(path, new, soft=()):
    """Merge {(script, n): text} into a tl file: blocks and '#~ @k.n' comments replaced in
    place (kept as '#ps2 @k.n' for keys in soft), new ones appended."""
    lines = open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else []
    out, i, done = [], 0, set()
    while i < len(lines):
        m = KEY.fullmatch(lines[i])
        key = (int(m.group(1)), int(m.group(2))) if m else None
        c = OLD_EN.match(lines[i])
        if c:
            ck = (int(c.group(1)), int(c.group(2)))
            if ck in new and ck not in done:
                if ck in soft:
                    out.append('#ps2 @%d.%d  %s' % (ck + (lines[i][c.end():],)))
                out += ['@%d.%d' % ck, new[ck]]
                done.add(ck)
                i += 1
                continue
        if key in new:
            out += [lines[i], new[key]]
            done.add(key)
            i += 1
            while i < len(lines) and lines[i].strip() and not KEY.fullmatch(lines[i]) \
                    and not lines[i].lstrip().startswith('#'):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    while out and out[-1] == '':
        out.pop()
    for k in sorted(set(new) - done):
        out += ['@%d.%d' % k, new[k]]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')

# ---------------------------------------------------------------- validation

def english_bytes(src):
    s = src.replace(' || ', '\n').replace('||', '\n').replace('\\n ', '\n').replace('\\n', '\n')
    s = s.replace('\\_', ' ').replace(' \n', '\n')
    return text.encode(re.sub(r'(?<!\\)%', '％', s))

def escapes(b):
    return sorted(m.group(1) for m in ESC.finditer(b))

def check(jp, en, k, op=None):
    """-> (errors, warnings, final bytes)"""
    errs, warns = [], []
    if FULL_LATIN.search(en.decode('cp932', 'replace')):
        errs.append('full-width Latin/digits in English')
    if b'\\' in ESC.sub(b'', en):
        errs.append('backslash that is not an escape')
    je, ee = escapes(jp), escapes(en)
    for x in ee:
        if x in je:
            je.remove(x)
        else:
            errs.append('escape not in the Japanese: \\%s' % x.decode())
    for x in je:
        if x[:1] != b'%':
            errs.append('missing escape \\%s' % x.decode())
    if any(c < 0x20 and c != 0x0A for c in en):
        errs.append('control byte in English')
    if k == 'name':
        errs.append('names are not translated in tl/ev yet')
        return errs, warns, en
    if k == 'dialogue':
        width, page = NARRATION if op == 0x13 else WINDOW
        jl = [measure(l, True)[0] for l in jp.split(b'\n')]
        shown = sum(max(1, -(-x // width)) for x in jl)
        max_lines = -(-shown // page) * page
        lines = wrap(en, width, LINE_CHARS)
        for i, l in enumerate(lines):
            px, nc = measure(l)
            if px > width:
                errs.append('line %d is %d px > %d' % (i + 1, px, width))
            if nc > LINE_CHARS:
                errs.append('line %d is %d characters > %d' % (i + 1, nc, LINE_CHARS))
        if len(lines) > max_lines:
            warns.append('%d lines > %d (extra page)' % (len(lines), max_lines))
        return errs, warns, b'\n'.join(lines)
    # choices / labels: not wrapped; the menu sizes itself (check the real limits).
    # 1E sets a text variable (\\Z00n, e.g. the hero's career) shown inside other text.
    if op == 0x1E:
        return errs, warns, en
    width = max([LABEL_PX.get(op, 0)] + [measure(l, True)[0] for l in jp.split(b'\n')])
    max_lines = jp.count(b'\n') + 1
    for i, l in enumerate(en.split(b'\n')):
        if measure(l)[0] > width:
            warns.append('line %d is %d px > %d' % (i + 1, measure(l)[0], width))
    if en.count(b'\n') + 1 > max_lines:
        warns.append('%d lines > %d' % (en.count(b'\n') + 1, max_lines))
    return errs, warns, en

def english_entry(name, units_en, log, use_memory=True):
    """Apply {(script, n): text} to a clean file -> rebuilt bytes (or None if unchanged).
    use_memory: strings without English take that of an identical Japanese string."""
    e, us = units(name)
    index = {(k, n): (ins, j) for k, n, ins, j in us}
    changed = False
    z_slots()
    _entry[0] = name
    if use_memory:
        mem = memory()
        units_en = dict(units_en)
        for k, n, ins, j in us:
            if (k, n) not in units_en and kind(ins, j) != 'name':
                src = mem.get((kind(ins, j), ins.strs[j]))
                if src is not None:
                    units_en[(k, n)] = src
    for key, src in sorted(units_en.items()):
        tag = '%s@%d.%d' % ((name,) + key)
        if key not in index:
            log('%s ERROR no such string' % tag, True); continue
        if src.strip() == '=':
            continue
        ins, j = index[key]
        try:
            en = english_bytes(src)
        except ValueError as x:
            log('%s ERROR %s' % (tag, x), True); continue
        errs, warns, final = check(ins.strs[j], en, kind(ins, j), ins.op)
        for x in errs:
            log('%s ERROR %s' % (tag, x), True)
        for x in warns:
            log('%s warn  %s' % (tag, x), False)
        if not errs:
            ins.strs[j] = final
            changed = True
    if not changed:
        return None
    try:
        return e.build()
    except evscript.ParseError as x:
        log('%s ERROR %s' % (name, x), True)
        return None

def tl_entries():
    if not os.path.isdir(TL_EV):
        return []
    return sorted(n[:-4] for n in os.listdir(TL_EV) if re.fullmatch(r'E[0-9A-Z]{7}\.txt', n))

@functools.lru_cache(None)
def memory():
    """(kind, Japanese) -> English source from every tl/ev file (first file first)."""
    mem = {}
    for name in tl_entries():
        en = parse_tl(tl_path(name))
        for k, n, ins, j in units_ro(name):
            src = en.get((k, n))
            if src is not None and src.strip() != '=':
                mem.setdefault((kind(ins, j), ins.strs[j]), src)
    return mem

def apply(name, batch=None, dry=False):
    path = tl_path(name)
    units_en = parse_tl(path) if os.path.exists(path) else {}
    new = {}
    if batch and os.path.abspath(batch) != os.path.abspath(path):
        new = parse_tl(batch)
        units_en.update(new)
        print('%s: %d blocks from %s' % (name, len(new), batch))
    bad = []
    def log(msg, err):
        print(msg)
        if err:
            bad.append(msg)
    english_entry(name, units_en, log, use_memory=False)
    if bad and new:
        print('%s: %d errors: nothing written' % (name, len(bad)))
    elif new and not dry:
        write_tl(path, new, parse_soft(batch))
    print('%s: %d/%d strings translated here, %d errors' % (name, len(units_en), len(units_ro(name)), len(bad)))
    return not bad

def apply_all(log=None):
    """For build.py: {relative path: English bytes} for every file with English of its
    own or from the memory (exits on errors)."""
    out, bad, nwarn = {}, [], [0]
    def _log(msg, err):
        if err:
            bad.append(msg)
        else:
            nwarn[0] += 1
        if log:
            log(msg)
    mem = memory()
    own = set(tl_entries())
    for name in script_entries():
        if name not in own and not mem:
            continue
        units_en = parse_tl(tl_path(name)) if name in own else {}
        new = english_entry(name, units_en, _log)
        if new is not None:
            out['%s/%s.TS5' % (EVENT_DIR, name)] = new
    if bad:
        sys.exit('errors in tl/ev:\n' + '\n'.join(bad))
    return out, nwarn[0]

# ---------------------------------------------------------------- show / stats

def show(name, script=None, todo=False):
    us = units_ro(name)
    path = tl_path(name)
    done = parse_tl(path) if os.path.exists(path) else {}
    old = parse_old(path)
    mem = memory() if todo else {}
    count = {}
    for k, n, ins, j in us:
        key = (kind(ins, j), ins.strs[j])
        count[key] = count.get(key, 0) + 1
    seen = set()
    for k, n, ins, j in us:
        if script is not None and not script[0] <= k <= script[1] or kind(ins, j) == 'name':
            continue
        key = (kind(ins, j), ins.strs[j])
        if todo:
            if (k, n) in done or key in mem or key in seen:
                continue
            seen.add(key)
        s = text.decode(ins.strs[j]).replace('\n', '⏎')
        print('@%d.%d%s [%02X%s]%s  %s' % (k, n, ' [done]' if (k, n) in done else '', ins.op,
                                          '.%d' % j if len(ins.strs) > 1 else '',
                                          ' x%d' % count[key] if todo and count[key] > 1 else '', s))
        if todo and (k, n) in old:
            print('    old: ' + old[(k, n)])

def stats():
    """Per file: strings with English (own or from the memory) / all."""
    tot = done = 0
    mem = memory()
    for name in script_entries():
        own = parse_tl(tl_path(name)) if os.path.exists(tl_path(name)) else {}
        us = [(k, n, ins, j) for k, n, ins, j in units_ro(name) if kind(ins, j) != 'name']
        d = sum(1 for k, n, ins, j in us if (k, n) in own or (kind(ins, j), ins.strs[j]) in mem)
        tot += len(us); done += d
        if d < len(us):
            print('%s %5d/%5d' % (name, d, len(us)))
    print('total %d/%d strings' % (done, tot))

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    args = [a for a in sys.argv[2:] if a != '--todo']
    if cmd == 'show':
        r = None
        if len(args) > 1:
            a, _, b = args[1].partition('-')
            r = (int(a), int(b or a))
        show(args[0], r, '--todo' in sys.argv)
    elif cmd == 'apply':
        sys.exit(0 if apply(args[0], args[1] if len(args) > 1 else None) else 1)
    elif cmd == 'check':
        sys.exit(0 if apply(args[0], args[1], dry=True) else 1)
    elif cmd == 'stats':
        stats()
    else:
        sys.exit(__doc__)
