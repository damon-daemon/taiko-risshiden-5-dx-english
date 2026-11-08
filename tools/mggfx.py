"""Mini-game textures with baked-in Japanese labels (data/MG/MGnn.G1T, RGBA8).

Each item is a grid of label plates (wood, grey or coloured panels with dark ink).
Per cell, inside the frame: pixels much darker than their row's median are ink; they
are refilled row by row by interpolating between the clean pixels left and right
(plate grain runs horizontally, gradients vertically, so rows are nearly flat). The
English is then drawn centered in Noto Serif SemiBold with the original ink colour, at a
cap height taken from the original lettering, shrunk to fit.

Per-language copies sit next to each other (JP, TC, SC); only the JP ones are redrawn.

tl/mggfx.txt: "FILE<TAB>TEX<TAB>English" ('|' separates the labels of the item, in
the order of ITEMS[...]['labels']; a cell uses label cell_label(item, n)).

usage: mggfx.py preview OUT.png
"""
import os, sys
from collections import Counter
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import g1t, setup

TL = os.path.join(setup.ROOT, 'tl', 'mggfx.txt')
FONT = '/usr/share/fonts/noto/NotoSerif-SemiBold.ttf'
BOLD = os.path.join(os.path.dirname(FONT), 'NotoSerif-Bold.ttf')
CAP = 0.62           # English cap height / height of the original lettering (tallest cell)
PAD = 3              # px kept free left and right of the English
SS = 4               # supersampling for the lettering

def grid(x0, y0, cw, ch, cols, rows, n=None, step=None):
    sx, sy = step or (cw, ch)
    cells = [(x0 + c * sx, y0 + r * sy, cw, ch) for r in range(rows) for c in range(cols)]
    return cells[:n] if n else cells

def tiles(boxes, cols, step):
    """Several boxes (x, y, w, h) per tile, tiles repeated cols times step px apart."""
    return [(x + c * step, y, w, h) for c in range(cols) for (x, y, w, h) in boxes]

# (file, tex) -> cells, inset (frame width kept), and how cells map to labels:
#   'map': list of label indexes per cell (default: cell n -> label n)
ITEMS = {
    # Oicho-Kabu: player plates 子1-3, 4 states (columns) x 3 players (rows)
    ('data/MG/MG21.G1T', 16): dict(cells=grid(0, 0, 152, 44, 4, 3), inset=(10, 7),
                                   map=[r for r in range(3) for c in range(4)]),
    # player plates 子1-3, 2 states (rows) x 3 players
    ('data/MG/MG21.G1T', 19): dict(cells=grid(0, 0, 120, 56, 3, 2), inset=(10, 8),
                                   map=[0, 1, 2, 0, 1, 2]),
    # dealer plate 親, 3 states
    ('data/MG/MG21.G1T', 68): dict(cells=grid(0, 0, 152, 44, 3, 1), inset=(10, 7),
                                   map=[0, 0, 0]),
    # hand names
    ('data/MG/MG21.G1T', 72): dict(cells=grid(0, 0, 156, 44, 3, 5, 13), inset=(7, 7)),
    # speech bubbles もう一丁 / 勝負！
    ('data/MG/MG21.G1T', 0): dict(cells=[(0, 0, 148, 60)], inset=(10, 8), cap=14),
    ('data/MG/MG21.G1T', 3): dict(cells=[(0, 0, 148, 60)], inset=(10, 8), cap=14),
    # Chinchirorin: 振番 (whose roll), 親 (two states)
    ('data/MG/MG24.G1T', 0): dict(cells=[(0, 0, 118, 56)], inset=(10, 9)),
    ('data/MG/MG24.G1T', 3): dict(cells=grid(0, 0, 118, 56, 2, 1), inset=(10, 9),
                                  map=[0, 0]),
    # Gold mining (MG01 roulette): 止 button, 4 states (the pressed one sits 4,3 px lower right)
    ('data/MG/MG01.G1T', 0): dict(cells=[(14, 14, 96, 44), (142, 14, 96, 44),
                                         (274, 17, 96, 44), (398, 14, 96, 44)],
                                  inset=(0, 0), map=[0, 0, 0, 0]),
    # MG04: 獲得した金塊 [n] 個 (the count is drawn between): label + counter erased
    ('data/MG/MG04.G1T', 11): dict(cells=[(40, 14, 266, 58), (410, 14, 62, 58)], inset=(0, 0)),
    # Medicine mixing (MG10): pots ①薬 ②薬 ③薬 (JP bars 13/16/19; 14/17/20 TC, 15/18/21 SC)
    **{('data/MG/MG10.G1T', k): dict(cells=[(206, 8, 300, 72)], inset=(0, 0), align='left',
                                     map=[0]) for k in (13, 16, 19)},
    # herb jars い ろ は with a small 薬 (JP 26/29/32; 6 states 176 px apart): 薬 erased
    **{('data/MG/MG10.G1T', k): dict(cells=tiles([(88, 12, 70, 80), (8, 84, 152, 158)], 6, 176),
                                     inset=(0, 0), ink=True, map=[0, 1] * 6) for k in (26, 29, 32)},
    # 成功 banner (red, white outline, no shadow)
    ('data/MG/MG10.G1T', 3): dict(banner=True, opts=dict(outline=7, shadow=0)),
    # Go-stone / card game tiles 一二三四 (MG13: grid of 4 x 8 states, big tiles 7-22)
    ('data/MG/MG13.G1T', 4): dict(cells=[(c * 54 + 6, round(r * 278 / 8) + 6, 42, 24)
                                         for r in range(8) for c in range(4)],
                                  inset=(0, 0), map=[0, 1, 2, 3] * 8, cap=13, bold=True,
                                  thresh=14),
    **{('data/MG/MG13.G1T', k): dict(cells=[(24, 18, 88, 50)], inset=(0, 0), cap=26, bold=True)
       for k in range(7, 23)},
    # kanji numeral strips on transparency (一..六; MG14 starts at 二)
    ('data/MG/MG09.G1T', 2): dict(cells=grid(0, 0, 52, 52, 6, 1), inset=(0, 0), clear=True,
                                  cap=30, bold=True),
    ('data/MG/MG14.G1T', 16): dict(cells=grid(0, 0, 80, 80, 5, 1), inset=(0, 0), clear=True,
                                   cap=40, bold=True),
    ('data/MG/MG00.G1T', 7): dict(cells=grid(0, 0, 80, 80, 6, 1), inset=(0, 0), clear=True,
                                  cap=40, bold=True),
    # result banners 圧勝 当たり 大成功！ 敗北 引き分け 完璧！ 完全勝利！ 無傷突破！ 大当たり！
    # 勝利 当代随一！ 全問正解！ 上出来 (shared by the mini-games)
    **{('data/MG/MG23.G1T', k): dict(banner=True) for k in range(13)},
    # duel results (PBBATTLE, seen 2026-11-07 dojo duel tutorial): 連勝中 勝 敗 on transparency,
    # 引き分け 勝利 敗北 over a dark brush stroke (kept). 20-25 SC, 26-31 TC copies.
    **{('data/PBBATTLE/PBGRP1.G1T', k): dict(banner=True, opts=dict(outline=7, shadow=5))
       for k in (0, 1, 2)},
    **{('data/PBBATTLE/PBGRP1.G1T', k): dict(banner=True, brush=True,
                                             opts=dict(outline=8, shadow=0, margin=60))
       for k in (4, 5, 6)},
}

def load_tl():
    out = {}
    if not os.path.exists(TL):
        return out
    for line in open(TL, encoding='utf-8').read().splitlines():
        if line.strip() and not line.startswith('#'):
            f, i, text = line.split('\t')
            out[(f, int(i))] = text.split('|')
    return out

def luma(p):
    return (p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000

def erase(px, box, thresh=28):
    """Remove dark lettering from box (x0, y0, x1, y1); returns (ink colour, ink bbox)."""
    x0, y0, x1, y1 = box
    ink = set()
    for y in range(y0, y1):
        row = sorted(luma(px[x, y]) for x in range(x0, x1))
        med = row[len(row) // 2]
        for x in range(x0, x1):
            if luma(px[x, y]) < med - thresh:
                ink.add((x, y))
    if not ink:
        return None, None
    darkest = sorted(ink, key=lambda q: luma(px[q]))[:max(1, len(ink) // 5)]
    colour = tuple(sum(px[q][c] for q in darkest) // len(darkest) for c in range(3))
    xs = [q[0] for q in ink]; ys = [q[1] for q in ink]
    bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    # grow by 2 px (anti-aliased edges)
    grown = set()
    for (x, y) in ink:
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-1, 0, 1):
                if x0 <= x + dx < x1 and y0 <= y + dy < y1:
                    grown.add((x + dx, y + dy))
    for y in range(y0, y1):
        x = x0
        while x < x1:
            if (x, y) not in grown:
                x += 1
                continue
            s = x
            while x < x1 and (x, y) in grown:
                x += 1
            left = [px[k, y] for k in range(max(x0, s - 3), s)]
            right = [px[k, y] for k in range(x, min(x1, x + 3))]
            if not left:
                left = right
            if not right:
                right = left
            if not left:
                continue
            a = [sum(p[c] for p in left) / len(left) for c in range(4)]
            b = [sum(p[c] for p in right) / len(right) for c in range(4)]
            n = x - s + 1
            for k in range(s, x):
                t = (k - s + 1) / n
                px[k, y] = tuple(int(round(a[c] * (1 - t) + b[c] * t)) for c in range(4))
    return colour, bbox

def erase_ink(px, box, frac=0.45, grow=1):
    """Remove flat-coloured lettering that dominates its rows (big kana on a jar, or
    ink lighter than the ground): the ground colour is the median of the box border,
    the ink colour the pixels farthest from it; pixels near the ink colour are refilled
    row by row from the nearest clean pixels."""
    x0, y0, x1, y1 = box
    border = [px[x, y] for x in range(x0, x1) for y in (y0, y1 - 1)] + \
             [px[x, y] for y in range(y0, y1) for x in (x0, x1 - 1)]
    border.sort(key=luma)
    ground = border[len(border) // 2]
    dist = lambda p, q: sum((p[c] - q[c]) ** 2 for c in range(3)) ** 0.5
    allp = sorted((px[x, y] for x in range(x0, x1) for y in range(y0, y1)),
                  key=lambda p: -dist(p, ground))
    top = allp[:max(1, len(allp) // 12)]
    ink = tuple(sum(p[c] for p in top) / len(top) for c in range(3))
    t = frac * dist(ink, ground)
    core = {(x, y) for x in range(x0, x1) for y in range(y0, y1) if dist(px[x, y], ink) < t}
    if not core:
        return None, None
    mask = set()
    for (x, y) in core:
        for dx in range(-grow - 1, grow + 2):
            for dy in range(-grow, grow + 1):
                if x0 <= x + dx < x1 and y0 <= y + dy < y1:
                    mask.add((x + dx, y + dy))
    ys = [q[1] for q in core]
    _fill_rows(px, box, mask)
    return tuple(int(c) for c in ink), (x0, min(ys), x1, max(ys) + 1)

def clear_box(px, box):
    """Lettering on transparency: take its colour and clear the box."""
    x0, y0, x1, y1 = box
    ink = [(x, y) for x in range(x0, x1) for y in range(y0, y1) if px[x, y][3] > 200]
    if not ink:
        return None, None
    dark = sorted(ink, key=lambda q: luma(px[q]))[:max(1, len(ink) // 3)]
    colour = tuple(sum(px[q][c] for q in dark) // len(dark) for c in range(3))
    ys = [q[1] for q in ink]
    for x in range(x0, x1):
        for y in range(y0, y1):
            px[x, y] = colour + (0,)
    return colour, (x0, min(ys), x1, max(ys) + 1)

def _fill_rows(px, box, mask):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        x = x0
        while x < x1:
            if (x, y) not in mask:
                x += 1
                continue
            s = x
            while x < x1 and (x, y) in mask:
                x += 1
            left = [px[k, y] for k in range(max(x0, s - 3), s)]
            right = [px[k, y] for k in range(x, min(x1, x + 3))]
            left, right = left or right, right or left
            if not left:
                continue
            a = [sum(p[c] for p in left) / len(left) for c in range(4)]
            b = [sum(p[c] for p in right) / len(right) for c in range(4)]
            n = x - s + 1
            for k in range(s, x):
                f = (k - s + 1) / n
                px[k, y] = tuple(int(round(a[c] * (1 - f) + b[c] * f)) for c in range(4))

def draw_text(im, box, text, colour, cap, align='center', clear=False, font_file=FONT):
    """Centered (or left-aligned) text in box (x0, y0, x1, y1), cap height <= cap, fitted to the width."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    for size in range(80, 6, -1):
        font = ImageFont.truetype(font_file, size * SS)
        capb = font.getbbox('H')
        caph = (capb[3] - capb[1]) / SS
        tb = font.getbbox(text)
        tw, th = (tb[2] - tb[0]) / SS, (tb[3] - tb[1]) / SS
        if caph <= cap and tw <= w and th <= h:
            break
    layer = Image.new('L', (w * SS, h * SS), 0)
    d = ImageDraw.Draw(layer)
    # vertical: center the cap height (descenders hang below)
    tx = (w * SS - (tb[2] - tb[0])) / 2 - tb[0] if align == 'center' else -tb[0]
    ty = (h * SS - (capb[3] - capb[1])) / 2 - capb[1]
    d.text((tx, ty), text, font=font, fill=255)
    mask = layer.resize((w, h), Image.LANCZOS)
    solid = Image.new('RGBA', (w, h), colour + (255,))
    region = im.crop((x0, y0, x1, y1))
    a = mask if clear else region.split()[3]
    region.paste(solid, (0, 0), mask)
    region.putalpha(a)
    im.paste(region, (x0, y0))

def redraw(im, item, labels):
    if item.get('banner') and item.get('brush'):
        back, letters = split_brush(im)
        back.alpha_composite(banner(letters, labels[0], **item.get('opts', {})))
        return back
    if item.get('banner'):
        return banner(im, labels[0], **item.get('opts', {}))
    im = im.copy()
    px = im.load()
    mp = item.get('map') or list(range(len(item['cells'])))
    ix, iy = item['inset']
    done = []
    for n, (cx, cy, cw, ch) in enumerate(item['cells']):
        box = (cx + ix, cy + iy, cx + cw - ix, cy + ch - iy)
        if item.get('clear'):
            colour, bbox = clear_box(px, box)
        else:
            colour, bbox = (erase_ink(px, box) if item.get('ink') else
                            erase(px, box, item.get('thresh', 28)))
        if colour is not None:
            done.append((box, labels[mp[n]], colour, bbox[3] - bbox[1]))
    done = [d for d in done if d[1]]          # empty label: erase only
    if not done:
        return im
    cap = item.get('cap') or CAP * max(d[3] for d in done)
    for (x0, y0, x1, y1), text, colour, _ in done:
        draw_text(im, (x0 + PAD, y0, x1 - PAD, y1), text, colour, cap, item.get('align', 'center'),
                  item.get('clear', False), BOLD if item.get('bold') else FONT)
    return im

# ---------------------------------------------------------------- banners

BANNER_FONTS = ['NotoSerif-Bold.ttf', 'NotoSerif-SemiCondensedBold.ttf',
                'NotoSerif-CondensedBold.ttf', 'NotoSerif-ExtraCondensedBold.ttf']

def banner_style(im):
    """Measure an outlined banner (lettering on transparency): per-row fill colours,
    light outline colour, shadow colour and the rows of the lettering."""
    px = im.load()
    w, h = im.size
    light = Counter()
    shadow = Counter()
    rows = {}
    for y in range(h):
        fill = []
        for x in range(w):
            p = px[x, y]
            if p[3] == 255:
                if luma(p) >= 215:
                    light[p[:3]] += 1
                else:
                    fill.append(p)
            elif 0 < p[3] < 120:
                shadow[p[:3]] += 1
        if len(fill) > 6:
            fill.sort(key=luma)
            # upper half by brightness: skip the dark bevel at the stroke edges
            rows[y] = fill[len(fill) * 2 // 3][:3]
    ys = sorted(rows)
    # smooth over +-6 rows (the per-row picks are noisy and show as stripes)
    rows = {y: tuple(sum(rows[k][c] for k in ys if abs(k - y) <= 6) /
                     sum(1 for k in ys if abs(k - y) <= 6) for c in range(3)) for y in ys}
    return dict(rows=rows, y0=ys[0], y1=ys[-1], light=light.most_common(1)[0][0],
                shadow=shadow.most_common(1)[0][0] if shadow else (0, 0, 0))

CLOSE_Q = 8          # closing radius (quarter-scale px) rebuilding the brush under letters
BRUSH_LUMA = 70      # brush stroke pixels: dark, low-saturation browns

def split_brush(im, grow=6):
    """Banner lettering over a dark brush stroke -> (brush alone, lettering alone). The
    lettering area (grown by `grow` px: shadow, bevel) is repainted with the row's brush
    colour where it lies within the brush's row or column span, else cleared."""
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()
    is_brush = lambda p: p[3] > 200 and luma(p) < BRUSH_LUMA and max(p[:3]) - min(p[:3]) < 70
    letter = Image.new('L', (w, h), 0)
    lm = letter.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[3] > 0 and luma(p) >= BRUSH_LUMA:
                lm[x, y] = 255
    near = letter.filter(ImageFilter.MaxFilter(2 * grow + 1)).load()
    rows = {}
    cols = {}
    for y in range(h):
        for x in range(w):
            if is_brush(px[x, y]) and not near[x, y]:
                r = rows.setdefault(y, [x, x, [0, 0, 0], 0])
                r[0], r[1] = min(r[0], x), max(r[1], x)
                for k in range(3):
                    r[2][k] += px[x, y][k]
                r[3] += 1
                c = cols.setdefault(x, [y, y])
                c[0], c[1] = min(c[0], y), max(c[1], y)
    ys = sorted(rows)
    def colour(y):
        r = rows.get(y) or rows[min(ys, key=lambda k: abs(k - y))]
        return tuple(v // r[3] for v in r[2]) + (255,)
    # brush shape under the lettering: closing of the visible brush (quarter scale)
    vis = Image.new('L', (w, h), 0)
    vm = vis.load()
    for y in range(h):
        for x in range(w):
            if is_brush(px[x, y]) and not near[x, y]:
                vm[x, y] = 255
    q = vis.resize((w // 4, h // 4), Image.BOX).point(lambda v: 255 if v > 60 else 0)
    # round closing: dilate (blur, low threshold) then erode (blur, high threshold)
    q = q.filter(ImageFilter.GaussianBlur(CLOSE_Q)).point(lambda v: 255 if v > 8 else 0)
    q = q.filter(ImageFilter.GaussianBlur(CLOSE_Q)).point(lambda v: 255 if v > 247 else 0)
    # fill holes: whatever the outside cannot reach belongs to the brush
    outside = Image.new('L', (q.width + 2, q.height + 2), 0)
    outside.paste(q, (1, 1))
    ImageDraw.floodfill(outside, (0, 0), 128)
    q = outside.crop((1, 1, q.width + 1, q.height + 1)).point(lambda v: 0 if v == 128 else 255)
    shape = q.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5)).load()
    back = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    lets = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    bp, lp = back.load(), lets.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if lm[x, y]:
                lp[x, y] = p
            if near[x, y]:
                if shape[x, y]:
                    bp[x, y] = colour(y)[:3] + (shape[x, y],)
            elif p[3] and luma(p) < BRUSH_LUMA:
                bp[x, y] = p
    return back, lets

def banner(im, text, outline=5, shadow=4, margin=24, cap=None):
    """Replace the lettering of a banner with text, same colours, centred."""
    st = banner_style(im)
    y0, y1 = st['y0'], st['y1']
    w, h = im.size
    cap = cap or (y1 - y0) * 0.6
    room = w - 2 * (margin + outline + shadow)
    for size in range(int(cap * 1.6), 10, -1):
        for name in BANNER_FONTS:
            font = ImageFont.truetype(os.path.join(os.path.dirname(FONT), name), size * SS)
            capb = font.getbbox('H')
            tb = font.getbbox(text)
            if (capb[3] - capb[1]) / SS <= cap and (tb[2] - tb[0]) / SS <= room:
                break
        else:
            continue
        break
    mask = Image.new('L', (w * SS, h * SS), 0)
    d = ImageDraw.Draw(mask)
    tx = (w * SS - (tb[2] - tb[0])) / 2 - tb[0]
    ty = ((y0 + y1) * SS - (capb[3] - capb[1])) / 2 - capb[1]
    d.text((tx, ty), text, font=font, fill=255)
    out = Image.new('L', (w * SS, h * SS), 0)
    ImageDraw.Draw(out).text((tx, ty), text, font=font, fill=255,
                             stroke_width=outline * SS, stroke_fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = out.resize((w, h), Image.LANCZOS)
    # dark bevel along the stroke edges (bottom-weighted, like the originals)
    inner = mask.filter(ImageFilter.MinFilter(5))
    edge = ImageChops.subtract(mask, ImageChops.offset(inner, 0, -1))
    sh = (ImageChops.offset(out.filter(ImageFilter.GaussianBlur(shadow)), 2, 3) if shadow
          else Image.new('L', (w, h), 0))
    rows = st['rows']
    ys = sorted(rows)
    res = Image.new('RGBA', (w, h))
    rp = res.load()
    mp, op, ep, sp = mask.load(), out.load(), edge.load(), sh.load()
    for y in range(h):
        fy = min(max(y, ys[0]), ys[-1])
        fc = rows.get(fy) or rows[min(ys, key=lambda r: abs(r - fy))]
        for x in range(w):
            m, o, e, s = mp[x, y] / 255, op[x, y] / 255, ep[x, y] / 255, sp[x, y] / 255
            f = tuple(c * (1 - 0.35 * e) for c in fc)
            # fill over outline over shadow
            col = tuple(f[c] * m + st['light'][c] * (1 - m) for c in range(3))
            a = max(o, m)
            sa = s * 0.55 * (1 - a)
            ta = a + sa
            if ta <= 0:
                rp[x, y] = tuple(int(round(c)) for c in fc) + (0,)
                continue
            col = tuple((col[c] * a + st['shadow'][c] * sa) / ta for c in range(3))
            rp[x, y] = tuple(int(round(c)) for c in col) + (int(round(ta * 255)),)
    return res

def jobs():
    tl = load_tl()
    return [(f, i, item, tl[(f, i)]) for (f, i), item in ITEMS.items() if (f, i) in tl]

def apply(game):
    by_file = {}
    for f, i, item, labels in jobs():
        by_file.setdefault(f, []).append((i, item, labels))
    files = {}
    for f, items in by_file.items():
        data = open(os.path.join(game, f), 'rb').read()
        ts = g1t.textures(data)
        for i, item, labels in items:
            data = g1t.replace(data, i, redraw(g1t.decode(data, ts[i]), item, labels))
        files[f] = data
    return files

def preview(out, scale=2):
    ims = []
    for f, i, item, labels in jobs():
        data = open(os.path.join(setup.CLEAN, f), 'rb').read()
        old = g1t.decode(data, g1t.textures(data)[i])
        for im in (old, redraw(old, item, labels)):
            ims.append(im.resize((im.width * scale, im.height * scale), Image.NEAREST))
    W = max(i.width for i in ims)
    sheet = Image.new('RGBA', (W, sum(i.height + 8 for i in ims)), (255, 0, 255, 255))
    y = 0
    for i in ims:
        sheet.alpha_composite(i, (0, y))
        y += i.height + 8
    sheet.save(out)

if __name__ == '__main__':
    if sys.argv[1] == 'preview':
        preview(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2)
