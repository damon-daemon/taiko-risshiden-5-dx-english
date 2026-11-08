"""Translation helper for TAI5MSG_JP.DAT: show units, validate + wrap + apply English.

(Port of the PS2 project's tl.py; same tl/ format.)

A message is split into text units by tools/msgscript.py: the runs of text between
structural codes (conditions, END, variant/register commands). Only units are
translated; the structure around them is kept byte for byte.

tl/msgNN.txt holds the English (no Japanese), one block per unit:

    # comment (a line starting with #; English text never does)
    @<entry>          unit 0 of the entry (same as @<entry>.0)
    @<entry>.<unit>
    @<entry>.*        every unit of the entry     @<a>-<b>.*  every unit of a range
    English text, possibly over several physical lines (joined with spaces).

  \\n or ||  forced line break        \\_  a space that line stripping would eat
  =          (whole block) keep the Japanese of this unit
  Inline codes are copied from `show` as printed ({02}{01}d = a variable,
  {01}C1{00} = insert msg00 entry 0x31, {1B}C3..{1B}C0 = colour, %w = field filled
  in by the game). They may move; {01}C/{02} inserts may be dropped (word endings,
  pronouns), not added. Kana toggles ({1B}K {1B}H {1B}k) are dropped from English.
  A '%' that is not one of the unit's %-fields becomes full-width ％.

Units are word-wrapped with the advances of the patched font (font.advance_table) to
the box of their block and checked: the message window holds 40 characters a line (one
text object per character, 40 slots a line), lines per page, and the whole message
re-parsed must keep the Japanese structure.

Widths are in pixels of the message-window font (full-width 34, half-width 17 px, so
one half cell = 17 px). Other panels use other font sizes but the same cell layout, so
their boxes are given in the same units (cells x 17).

usage:
    tl.py show  NN [from] [to]     # print Japanese units (codes visible) to translate
    tl.py apply NN [batch.txt]     # merge batch into tl/msgNN.txt, validate, rebuild
                                   # script/msg/msgNN.json (no batch: tl/msgNN.txt only)
    tl.py stats                    # progress per block
"""
import collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import font, msgscript, setup, text

ROOT = setup.ROOT
TL = setup.TL

FULL_PX, HALF_PX = 34, 17   # message-window font (size id 34): full / half cell

def cells(n):
    """Width of n half cells."""
    return round(n * HALF_PX)

def ps2(px, size='large'):
    """A PS2 box width (24px font: 12 px a half cell; 'small' 20px font: 10) in DX units."""
    return cells(px / (12 if size == 'large' else 10))

# Boxes: (width, lines per page) = a window that pages, or (width, lines, head) = a fixed
# panel holding `lines` lines plus `head` heading lines (the bios' dates line).
# Blocks not listed use FIT: each unit is wrapped to its widest Japanese line (at least
# the block's usual line width) and may not have more lines than the Japanese.
#
# Message window (verified in DX, wrap check 0x1406DEAA0): wraps at x > 680 px, 3 lines a
# page; text objects in slots [line][40] (0x1406DE344, no bounds check: a 41st character
# on a line overwrites the next line's slots), so LINE_CHARS = 40 is a hard limit.
WINDOW = (680, 3)
LINE_CHARS = 40
#
# The rest is the PS2 geometry converted to cells (DX keeps the PS2 layouts at a higher
# resolution, e.g. the window: 480 px of 12 = 680 px of 17): NOT YET MEASURED IN DX.
BOXES = {n: WINDOW for n in list(range(17)) + [21, 24]}
BOXES[23] = (ps2(360), 5)      # msg23 card descriptions
BOXES[25] = (ps2(396), 11)     # battle advisor panel
BOXES[26] = (ps2(420), 9)      # battle advisor (castle defense lines)
BOXES[27] = (ps2(420), 9)      # #0-165 battle advisor (low-troop lines)
for _n in range(28, 33):       # officer bios on the Card List hero cards (dates line + 6)
    BOXES[_n] = (ps2(410, 'small'), 6, 1)
# Entries of window blocks shown in other panels (FIT mode instead of the window box)
NOT_WINDOW = {8: range(402, 439), 10: range(350, 1000), 11: {*range(531, 604), *range(789, 823)},
              22: range(458, 1000),  # town descriptions
              23: {*range(0, 84), *range(305, 369), *range(424, 1000)},
              24: range(215, 1000),  # mission help pages
              27: range(166, 181)}   # tea-ware crafting prompts
# Entries with their own box inside a block
ENTRY_BOXES = {27: [(range(181, 1000), WINDOW)],              # tea-party dialogue
               0: [(range(445, 450), (ps2(336), 3))],         # profession blurbs
               21: [(range(44, 62), (ps2(336), 8))]}          # mini-game descriptions
ENTRY_BOXES.setdefault(23, []).append((range(84, 424), (ps2(310, 'small'), 5, 0)))  # card texts
ENTRY_BOXES.setdefault(22, []).append((range(0, 458), (ps2(310, 'small'), 5, 0)))   # items
# Panels not measured: units keep to their Japanese (no line wider than its widest line,
# no more lines).
# msg17-20 #0-199 = officer bios: in DX the hero-select panel (seen 2026-11-06, msg19 #117)
# is as wide as the Japanese lines (19 full-width) and holds their 6 lines + dates line.
# The panel wraps over-wide lines itself at any character (splits English words): measured
# 2026-11-06 (msg19 #149), a 747 px line fits and 756 px wraps. DX joined many Japanese
# bios into long lines, so their width is the panel's, not the Japanese lines'.
BIO_PANEL = (747, 7)            # dates line + 6 lines
BIOS = range(200)
# msg23 #456-616 = bios of other people (merchants, ninja, new DX people): shown in the
# Person Info panel (Common Home -> Rumours, seen 2026-11-07 msg23 #505), the same 747 px
# panel, dates in the header (first line not shown) + 6 lines.
OTHER_BIOS = range(456, 617)
# msg22 #463-533 = town descriptions (destination map -> Bases -> a town; seen 2026-11-07
# msg22 #499 Kyoto): the panel wraps at any character like the bio panel (758 px fits,
# 764 wraps); 5 lines as in the Japanese.
TOWN_DESC = range(463, 534)
TOWN_PANEL = (747, 5)
STRICT = {**{n: range(1000) for n in range(17, 21)}, 22: range(458, 1000),
          23: {*range(0, 84), *range(424, 1000)}, 24: range(215, 1000),
          25: range(1000), 26: range(1000), 27: range(181)}
STRICT.update({n: NOT_WINDOW[n] for n in (8, 10, 11)})
# Help indexes: one-line topic headings are items of one list, drawn in a column as wide
# as its widest item, so a heading may be as wide as the widest one-line Japanese unit.
STRICT_COLUMN = {8, 10, 11, 19, 20, 24}
# Printed values ({02} x field): names etc. ~ 10 cells / 12 characters; numbers (field 'd',
# dates x=0x84) 6 digits. Estimates: the window patch (exepatch WRAP40) wraps a line that
# reaches 40 characters at run time, so a longer value cannot overflow the slots.
VAR_PX, VAR_CHARS = cells(10), 12
NUM_PX, NUM_CHARS = 6 * 16, 6
FIELD_PX, FIELD_CHARS = cells(10 / 3), 8   # %w-style field
FLOW_PX = cells(700 / 12)             # wider Japanese lines are paragraphs the text flows

KANA_TOGGLE = re.compile(rb'\x1b[KHk]')
FULL_LATIN = re.compile('[０-９Ａ-Ｚａ-ｚ]')

_W = {}

def widths():
    """{char: advance px} as the patched advance() computes it at half width 17."""
    if not _W:
        for i, q in enumerate(font.advance_table()):
            _W[chr(0x20 + i)] = (q * HALF_PX + 32) >> 6
    return _W

# ---------------------------------------------------------------- script access

def load(n):
    return json.load(open(setup.msg_json(n), encoding='utf-8'))

def save(n, rows):
    json.dump(rows, open(setup.msg_json(n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

_ROWS = {}

def rows_of(n):
    if n not in _ROWS:
        _ROWS[n] = load(n)
    return _ROWS[n]

def target(lo, hi):
    """Message inserted by {01}C / {01}J lo hi -> (block, entry)."""
    i = lo | hi << 8
    return (0, i) if i < 1000 else (i // 1000, i % 1000)

# ---------------------------------------------------------------- measuring

def insert_size(code, depth=0):
    """(px, chars) of an inline code when shown."""
    k = code[0]
    if k == 0x02:
        if len(code) == 3 and (code[2] == ord('d') or code[1] == 0x84):
            return NUM_PX, NUM_CHARS
        return VAR_PX, VAR_CHARS
    if k == 0x25:
        return FIELD_PX, FIELD_CHARS
    if k == 0x01 and len(code) == 4 and depth < 3:
        b, e = target(code[2], code[3])
        try:
            row = rows_of(b)[e]
        except (IndexError, FileNotFoundError):
            return 0, 0
        s = text.encode(row['en'] or row['jp'])
        toks, spans = msgscript.units(s)
        best = (0, 0)
        for a, z in spans:
            first = []
            for kind, t in toks[a:z]:
                if kind == 'nl':
                    break
                first.append((kind, t))
            best = max(best, measure(first, depth + 1))
        return best
    return 0, 0

def measure(toks, depth=0):
    """(px, characters) of one line given as tokens."""
    px = nc = 0
    W = widths()
    for kind, t in toks:
        if kind == 'text':
            i = 0
            while i < len(t):
                c = t[i]
                if msgscript._sjis_lead(c) and i + 1 < len(t):
                    px += FULL_PX; nc += 1; i += 2
                    continue
                px += W.get(chr(c), HALF_PX) if c < 0x80 else HALF_PX
                nc += 1; i += 1
        elif kind == 'inline':
            p, n = insert_size(t, depth)
            px += p; nc += n
    return px, nc

def jp_px(toks):
    """Width of a Japanese line as the game shows it: half-width kana stand for
    full-width hiragana, the voicing marks combine with them."""
    px = 0
    for kind, t in toks:
        if kind == 'text':
            i = 0
            while i < len(t):
                c = t[i]
                if msgscript._sjis_lead(c) and i + 1 < len(t):
                    px += FULL_PX; i += 2; continue
                px += FULL_PX if 0xA1 <= c <= 0xDD else 0 if c in (0xDE, 0xDF) else HALF_PX
                i += 1
        elif kind == 'inline':
            px += insert_size(t)[0]
    return px

_ENDS = {}

def ends_line(code):
    """True if a {01}C/J insert's text ends with a newline (the line ends there)."""
    if not (code[0] == 0x01 and len(code) == 4):
        return False
    if code not in _ENDS:
        b, e = target(code[2], code[3])
        try:
            row = rows_of(b)[e]
        except (IndexError, FileNotFoundError):
            _ENDS[code] = False
            return False
        toks, spans = msgscript.units(text.encode(row['en'] or row['jp']))
        _ENDS[code] = any(toks[z - 1][0] == 'nl' for a, z in spans)
    return _ENDS[code]

def lines_of(toks):
    """Split tokens into display lines; a line ended by an insert that itself ends
    with a newline gets a ('soft', b'') marker (no newline is written after it)."""
    out, cur = [], []
    for kind, t in toks:
        if kind == 'nl':
            out.append(cur); cur = []
        else:
            cur.append((kind, t))
            if kind == 'inline' and ends_line(t):
                out.append(cur + [('soft', b'')]); cur = []
    return out + [cur]

def join_lines(lines):
    out = b''
    for i, l in enumerate(lines):
        out += b''.join(t for k, t in l)
        if i < len(lines) - 1 and not (l and l[-1][0] == 'soft'):
            out += b'\n'
    return out

# ---------------------------------------------------------------- wrapping

def words(toks):
    """Split a token line into words (lists of tokens) at ASCII spaces."""
    out, cur = [], []
    for kind, t in toks:
        if kind != 'text':
            cur.append((kind, t)); continue
        parts = t.split(b' ')
        for j, p in enumerate(parts):
            if j:
                out.append(cur); cur = []
            if p:
                cur.append(('text', p))
    out.append(cur)
    return [w for w in out if w]

def join(ws):
    toks = []
    for j, w in enumerate(ws):
        if j:
            toks.append(('text', b' '))
        toks += w
    return toks

def wrap(toks, width, chars=None):
    """Word-wrap tokens (with 'nl' forced breaks) -> list of lines (token lists), no
    line wider than width px (nor longer than chars characters, if given)."""
    out = []
    for para in lines_of(toks):
        line = []
        for w in words(para):
            px, nc = measure(join(line + [w]))
            if line and (px > width or chars and nc > chars):
                out.append(join(line)); line = [w]
            else:
                line.append(w)
        out.append(join(line))
    return out

class Limits:
    """How a unit is laid out: width px, max lines, lines per page (0 = no paging),
    max characters a line (None = no limit), strict (overflow is an error)."""
    def __init__(self, width, lines, page=0, chars=None, strict=False):
        self.width, self.lines, self.page, self.chars, self.strict = width, lines, page, chars, strict

class Box:
    def __init__(self, n, rows):
        self.n = n
        self.fixed = BOXES.get(n)
        ws = []
        for r in rows:
            toks, spans = msgscript.units(text.encode(r['jp']))
            for a, z in spans:
                ls = lines_of(toks[a:z])
                if len(ls) > 1:
                    ws += [x for x in (jp_px(l) for l in ls) if x <= FLOW_PX]
        ws.sort()
        self.floor = ws[len(ws) * 3 // 4] if ws else 0
        self.column = 0
        if n in STRICT_COLUMN:
            for r in rows:
                if r['id'] in STRICT[n]:
                    toks, spans = msgscript.units(text.encode(r['jp']))
                    for a, z in spans:
                        ls = lines_of(toks[a:z])
                        if len(ls) == 1:
                            self.column = max(self.column, jp_px(ls[0]))

    def limits(self, jp_toks, entry=None):
        jl = [jp_px(l) for l in lines_of(jp_toks)]
        if (17 <= self.n <= 20 and entry in BIOS) or (self.n == 23 and entry in OTHER_BIOS):
            return Limits(BIO_PANEL[0], BIO_PANEL[1], strict=True)
        if self.n == 22 and entry in TOWN_DESC:
            return Limits(TOWN_PANEL[0], TOWN_PANEL[1], strict=True)
        if entry in STRICT.get(self.n, ()):
            if len(jl) == 1 and self.column:
                return Limits(self.column, 1, strict=True)
            return Limits(max(jl), len(jl), strict=True)
        fixed = next((b for r, b in ENTRY_BOXES.get(self.n, ()) if entry in r), None)
        if not fixed and entry not in NOT_WINDOW.get(self.n, ()):
            fixed = self.fixed
        if fixed:
            w, page = fixed[:2]
            if len(fixed) > 2:          # a fixed panel: page = all the lines it holds
                return Limits(w, page + fixed[2], page)
            # a paging window wraps long lines itself: count the lines as shown
            shown = sum(max(1, -(-x // w)) for x in jl)
            return Limits(w, -(-shown // page) * page, page, LINE_CHARS if fixed is WINDOW else None)
        manual = [x for x in jl if x <= FLOW_PX]
        flowing = len(manual) < len(jl)
        return Limits(max([self.floor] + manual), 10 ** 6 if flowing else len(jl))

# ---------------------------------------------------------------- tl files

KEY = re.compile(r'@(\d+)(?:-(\d+))?(?:\.(\d+|\*))?\s*')

def parse_tl(path):
    """-> {key: text}, key as written without '@': '12', '12.3', '12.*' or '63-99.*'."""
    out, key, buf = {}, None, []
    def flush():
        if key is not None:
            out[key] = ' '.join(buf)
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        m = KEY.fullmatch(line)
        if m:
            flush()
            a, b, u = m.groups()
            if b and u != '*':
                sys.exit('%s: %s: a range needs .*' % (path, line))
            key = '%s%s%s' % (a, '-' + b if b else '', '.' + u if u and u != '0' else '')
            buf = []
        elif line.lstrip().startswith('#'):
            continue
        elif key is not None and line.strip():
            buf.append(line.strip())
    flush()
    return out

def _key_order(k):
    m = re.fullmatch(r'(\d+)(?:-(\d+))?(?:\.(\d+|\*))?', k)
    a, b, u = m.groups()
    return int(a), int(b or a), -1 if u == '*' else int(u or 0)

def expand(units, rows):
    """{key: text} -> {(entry, unit): text}; explicit units beat N.*, which beats ranges."""
    out = {}
    spec = sorted(units, key=lambda k: (('-' not in k) + ('*' not in k), _key_order(k)))
    for k in spec:
        a, b, u = _key_order(k)
        for e in range(a, (b if a == b else min(b, len(rows) - 1)) + 1):
            if u >= 0 or e >= len(rows):
                out[(e, max(u, 0))] = units[k]
            else:
                n = len(msgscript.units(text.encode(rows[e]['jp']))[1])
                for i in range(n):
                    out[(e, i)] = units[k]
    return out

OLD_EN = re.compile(r'#~ @(\d+(?:\.\d+)?)  ')

def write_tl(path, new):
    """Merge {key: text} into a tl file: existing blocks and '#~ @key' comments are
    replaced in place (other comments and order kept), new ones appended in key order."""
    lines = open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else []
    out, i, done = [], 0, set()
    while i < len(lines):
        m = KEY.fullmatch(lines[i])
        key = None
        if m:
            a, b, u = m.groups()
            key = '%s%s%s' % (a, '-' + b if b else '', '.' + u if u and u != '0' else '')
        else:
            c = OLD_EN.match(lines[i])     # '#~ @key  old English' (port_msg): replace it
            if c and c.group(1) in new and c.group(1) not in done:
                out += ['@' + c.group(1), new[c.group(1)]]
                done.add(c.group(1))
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
    for k in sorted(set(new) - done, key=_key_order):
        out += ['@' + k, new[k]]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')

def english_bytes(src, jp_unit):
    """Batch text -> bytes: codes decoded, kana toggles dropped (a leading one is kept
    when the Japanese has it: it separates text from a number before it), '%' that
    is not one of the Japanese %-fields made full-width."""
    s = src.replace(' || ', '\n').replace('||', '\n').replace('\\n ', '\n').replace('\\n', '\n')
    s = s.replace('\\_', ' ').replace(' \n', '\n')
    b = text.encode(s)
    lead = KANA_TOGGLE.match(jp_unit)
    b = (lead.group() if lead else b'') + KANA_TOGGLE.sub(b'', b)
    fields = {t for k, t in msgscript.tokens(jp_unit) if k == 'inline' and t[:1] == b'%'}
    return b''.join(t if k != 'inline' or t[:1] != b'%' or t in fields else '％'.encode('cp932') + t[1:]
                    for k, t in msgscript.tokens(b))

# ---------------------------------------------------------------- validation

def code_str(t):
    """A code as written in tl/ files: printable ASCII as is, other bytes {XX}."""
    return ''.join(chr(c) if 0x20 <= c <= 0x7E and c not in (0x7B, 0x7D) else '{%02X}' % c for c in t)

def unit_str(toks):
    """Japanese unit for display: text decoded, codes via code_str, kana toggles dropped."""
    return ''.join(text.decode(t) if k in ('text', 'nl') else '' if KANA_TOGGLE.fullmatch(t) else code_str(t)
                   for k, t in toks)

def inline_codes(toks):
    return collections.Counter(t for k, t in toks if k == 'inline' and not KANA_TOGGLE.fullmatch(t))

DROPPABLE = (0x02, 0x25)

def check_unit(jp_toks, en):
    errs, warns = [], []
    try:
        et = msgscript.tokens(en)
    except msgscript.ParseError as e:
        return ['parse: %s' % e], warns, None
    bad = [t for k, t in et if k not in msgscript.INLINE]
    if bad:
        errs.append('structural code in English: %s' % ' '.join(code_str(t) for t in bad))
    jc, ec = inline_codes(jp_toks), inline_codes(et)
    for t in (ec - jc).elements():
        if t[0] == 0x02 and len(t) == 3:
            warns.append('added variable %s' % code_str(t))
        else:
            errs.append('code not in the Japanese: %s' % code_str(t))
    for t, n in (jc - ec).items():
        if t[0] == 0x01 and t[1] == 0x43 or t[0] in DROPPABLE:
            if t[0] == 0x02:
                warns.append('dropped variable %s' % code_str(t))
        else:
            errs.append('missing code %s' % code_str(t))
    if FULL_LATIN.search(en.decode('cp932', 'replace')):
        errs.append('full-width Latin/digits in English')
    return errs, warns, et

def layout(et, lim):
    """Wrap English tokens to a unit's limits -> (lines, errors, warnings)."""
    errs, warns = [], []
    lines = wrap(et, lim.width, lim.chars)
    for i, l in enumerate(lines):
        px, nc = measure(l)
        if px > lim.width:
            (errs if lim.strict else warns).append('line %d is %d px > %d' % (i + 1, px, lim.width))
        if lim.chars and nc > lim.chars:
            warns.append('line %d has %d characters > %d' % (i + 1, nc, lim.chars))
    if len(lines) > lim.lines:
        (errs if lim.strict else warns).append(
            '%d lines > %d%s' % (len(lines), lim.lines, ' (%d a page)' % lim.page if lim.page else ''))
    return lines, errs, warns

def build_entry(jp, units_en, box, tag, log):
    """Substitute English units into one message. -> en string ('' if none)."""
    jb = text.encode(jp)
    toks, spans = msgscript.units(jb)
    out = [t for k, t in toks]
    entry = int(tag.split('@')[1])
    used = False
    for u, (a, z) in enumerate(spans):
        src = units_en.pop(u, None)
        if src is None:
            continue
        if src.strip() == '=':
            used = True
            continue
        jp_unit = b''.join(t for k, t in toks[a:z])
        try:
            en = english_bytes(src, jp_unit)
        except ValueError as e:
            log('%s.%d ERROR %s' % (tag, u, e), True); continue
        errs, warns, et = check_unit(toks[a:z], en)
        if et is not None and not errs:
            lines, e2, w2 = layout(et, box.limits(toks[a:z], entry))
            errs += e2; warns += w2
        for e in errs:
            log('%s.%d ERROR %s' % (tag, u, e), True)
        for w in warns:
            log('%s.%d warn  %s' % (tag, u, w), False)
        if et is None or errs:
            continue
        for i in range(a, z):
            out[i] = b''
        out[a] = join_lines(lines)
        used = True
    for u in units_en:
        log('%s.%d ERROR no such unit (entry has %d)' % (tag, u, len(spans)), True)
    if not used:
        return ''
    nb = b''.join(out)
    # the rebuilt message must parse to the same structure as the Japanese
    try:
        new_struct = [t for k, t in msgscript.tokens(nb) if k not in msgscript.INLINE]
    except msgscript.ParseError as e:
        log('%s ERROR rebuilt message does not parse: %s' % (tag, e), True)
        return ''
    if new_struct != [t for k, t in toks if k not in msgscript.INLINE]:
        log('%s ERROR English changes the message structure (text after a code eaten as '
            'its argument? a digit right after a condition number needs {1B}H before it)' % tag, True)
        return ''
    return text.decode(nb)

def apply(n, batch=None):
    path = os.path.join(TL, 'msg%02d.txt' % n)
    units = parse_tl(path) if os.path.exists(path) else {}
    new = {}
    if batch and os.path.abspath(batch) != os.path.abspath(path):
        new = parse_tl(batch)
        units.update(new)
        print('msg%02d: %d blocks from %s' % (n, len(new), batch))
    rows = load(n)
    _ROWS[n] = rows
    box = Box(n, rows)
    per = collections.defaultdict(dict)
    for (e, u), src in expand(units, rows).items():
        per[e][u] = src
    bad = []
    def log(msg, err):
        print(msg)
        if err:
            bad.append(msg)
    # two passes: an insert of a later entry of this block is measured as its English
    # from the first (silent) pass, not as its Japanese
    for r in rows:
        r['en'] = ''
    targets = {target(t[2], t[3])[1] for r in rows for k, t in msgscript.tokens(text.encode(r['jp']))
               if k == 'inline' and t[:2] == b'\x01C' and len(t) == 4 and target(t[2], t[3])[0] == n}
    for _ in range(3):      # inserts inside inserts: repeat until their English settles
        first = {e: build_entry(rows[e]['jp'], dict(per[e]), box, 'msg%02d@%d' % (n, e), lambda m, err: None)
                 for e in targets if e in per and e < len(rows)}
        if all(rows[e]['en'] == en for e, en in first.items()):
            break
        for e, en in first.items():
            rows[e]['en'] = en
    for e, us in sorted(per.items()):
        if e >= len(rows):
            log('msg%02d@%d ERROR no such entry' % (n, e), True); continue
        rows[e]['en'] = build_entry(rows[e]['jp'], dict(us), box, 'msg%02d@%d' % (n, e), log)
    if bad and new:
        print('msg%02d: %d errors: nothing written' % (n, len(bad)))
    else:
        save(n, rows)
        if new:
            os.makedirs(TL, exist_ok=True)
            write_tl(path, new)
    total = sum(len(msgscript.units(text.encode(r['jp']))[1]) for r in rows)
    print('msg%02d: %d/%d units translated, %d errors' % (n, len(expand(units, rows)), total, len(bad)))
    return not bad

# ---------------------------------------------------------------- show / stats

def context(toks, a):
    """What leads to a unit: the structural code just before it."""
    for k, t in reversed(toks[:a]):
        if k == 'if':
            return 'if ' + text.decode(t[3:])
        if k == 'end':
            return 'else'
        if k == 'cmd':
            return text.decode(t)
        if k not in msgscript.INLINE:
            break
    return ''

def show(n, a=0, b=None):
    rows = load(n)
    path = os.path.join(TL, 'msg%02d.txt' % n)
    done = expand(parse_tl(path), rows) if os.path.exists(path) else {}
    for r in rows[a:b]:
        toks, spans = msgscript.units(text.encode(r['jp']))
        for u, (x, z) in enumerate(spans):
            jp = unit_str(toks[x:z])
            ctx = context(toks, x)
            print('@%d%s%s%s  %s' % (r['id'], '.%d' % u if u else '', ' [done]' if (r['id'], u) in done else '',
                                     '  # ' + ctx if ctx else '', jp.replace('\n', '⏎')))

def stats():
    tot = done = 0
    for n in range(setup.msg_count()):
        rows = load(n)
        t = sum(len(msgscript.units(text.encode(r['jp']))[1]) for r in rows)
        path = os.path.join(TL, 'msg%02d.txt' % n)
        d = len(expand(parse_tl(path), rows)) if os.path.exists(path) else 0
        tot += t; done += d
        print('msg%02d %5d/%5d' % (n, d, t))
    print('total %d/%d units' % (done, tot))

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'show':
        show(int(sys.argv[2]), *(int(x) for x in sys.argv[3:5]))
    elif cmd == 'apply':
        sys.exit(0 if apply(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None) else 1)
    elif cmd == 'stats':
        stats()
    else:
        sys.exit(__doc__)
