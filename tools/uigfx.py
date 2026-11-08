"""UI textures with baked-in text (white letters with a coloured glow on transparency).

The texture is redrawn from scratch: English in Noto Serif (system font, OFL), white,
with a glow made by dilating and blurring the letter mask, in the original glow colour.
Lines are centered; the font shrinks until every line fits the content box.

tl/uigfx.txt: "FILE<TAB>TEX<TAB>English" (FILE relative to the game dir, TEX = texture
index in the G1T; '|' splits lines).
Card list backs (UI/UI_COMMON_INIT.G1T tex 2, 7 cards of 176 x 280, drawn 1:1): the dark
vertical strip behind the old vertical label is divided out (per channel gain, column
profile x row profile) and a horizontal dark band is laid under the label instead
(uihooks.CARD_LABEL: box y 0x70, 40 px high).

Feeling-bar end tiles (UI/UI_COMMON_MARKERS.G1T tex 10 良 blue, 11 悪 red; 36 x 36): the
kanji is erased (dark ink inside the paper replaced by its row's paper colour) and a
'+' / '-' drawn in its place (SIGNS).

Power Map "Other" markers (BASE/MAIN.G1T tex 2 = clan crest atlas, 32 x 32 cells): 20
colour variants of 忍 (ninja, cells from 448) and 水 (pirates, from 512), black kanji
with a light halo on the colour, 2-px black border. Redrawn as "N" / "P" (the "Show"
checkboxes say Ninja / Pirates): TILES.

usage: uigfx.py preview OUT.png
"""
import os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import g1t, setup

TL = os.path.join(setup.ROOT, 'tl', 'uigfx.txt')
FONT = '/usr/share/fonts/noto/NotoSerif-Bold.ttf'
TEXT = (240, 240, 236)
TEXT_A = 240
GLOW = (48, 116, 20)
GLOW_A = 215
GLOW_R = 5           # glow width (px) around the letters
MARGIN = 2           # free space kept at the texture edges (beyond the glow)
LEADING = -7         # extra px between lines

def load_tl():
    out = []
    for line in open(TL, encoding='utf-8').read().splitlines():
        if line.strip() and not line.startswith('#'):
            f, i, text = line.split('\t')
            out.append((f, int(i), text.split('|')))
    return out

def fit(lines, w, h):
    """Largest font whose lines fit w x h; returns (font, line height)."""
    for size in range(48, 8, -1):
        font = ImageFont.truetype(FONT, size)
        asc, desc = font.getmetrics()
        lh = asc + desc + LEADING
        widths = [font.getlength(s) for s in lines]
        if max(widths) <= w and lh * len(lines) - LEADING <= h:
            return font, lh
    raise ValueError(lines)

def render(w, h, lines):
    pad = GLOW_R + MARGIN
    font, lh = fit(lines, w - 2 * pad, h - 2 * pad)
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    top = (h - (lh * len(lines) - LEADING)) // 2
    asc, desc = font.getmetrics()
    for n, s in enumerate(lines):
        x = (w - font.getlength(s)) / 2
        d.text((x, top + n * lh), s, font=font, fill=255)
    # glow: dilate the mask, then soften the outer edge
    glow = mask.filter(ImageFilter.MaxFilter(2 * GLOW_R - 1)).filter(ImageFilter.GaussianBlur(0.8))
    im = Image.new('RGBA', (w, h), GLOW + (0,))
    im.putalpha(glow.point(lambda v: v * GLOW_A // 255))
    txt = Image.new('RGBA', (w, h), TEXT + (0,))
    txt.putalpha(mask.point(lambda v: v * TEXT_A // 255))
    im.alpha_composite(txt)
    return im

CARDS = ('data/UI/UI_COMMON_INIT.G1T', 2)
CARD_W, CARD_N = 176, 7
STRIP_X, STRIP_Y = (28, 78), (70, 240)      # area holding the strip (card coordinates)
STRIP_CORE = (40, 64)                        # columns fully inside the strip
BAND_Y = (109, 151)                          # dark band under the label
BAND_K, BAND_RAMP, BAND_INSET = 0.55, 18, 8

def destrip(px, bx):
    x0, x1 = STRIP_X
    y0, y1 = STRIP_Y
    refx = list(range(x0 - 5, x0)) + list(range(x1, x1 + 5))
    c0, c1 = STRIP_CORE
    for ch in range(3):
        val = lambda x, y: px[bx + x, y][ch] + 1
        ref = {y: sum(val(x, y) for x in refx) / len(refx) for y in range(y0, y1)}
        rows = range(125, 190)
        col = {x: sum(val(x, y) / ref[y] for y in rows) / len(rows) for x in range(x0, x1)}
        core = sum(col[x] for x in range(c0, c1)) / (c1 - c0)
        w = {x: max(0, min(1.3, (1 - col[x]) / (1 - core))) for x in range(x0, x1)}
        r = {y: sum(val(x, y) for x in range(c0, c1)) / (c1 - c0) / ref[y] for y in range(y0, y1)}
        for y in range(y0, y1):
            win = [r[k] for k in range(y - 2, y + 3) if k in r]
            g = min(1, sum(win) / len(win))
            for x in range(x0, x1):
                f = 1 - (1 - g) * w[x]
                p = list(px[bx + x, y])
                p[ch] = max(0, min(255, round(val(x, y) / f) - 1))
                px[bx + x, y] = tuple(p)

def band(px, bx):
    y0, y1 = BAND_Y
    for y in range(y0, y1):
        fy = min(1, (y - y0 + 1) / 4, (y1 - y) / 4)
        for x in range(BAND_INSET, CARD_W - BAND_INSET):
            fx = min(1, (x - BAND_INSET + 1) / BAND_RAMP, (CARD_W - BAND_INSET - x) / BAND_RAMP)
            f = 1 - (1 - BAND_K) * fx * fy
            p = px[bx + x, y]
            px[bx + x, y] = tuple(int(v * f) for v in p[:3]) + (p[3],)

def cards(im):
    px = im.load()
    for c in range(CARD_N):
        destrip(px, c * CARD_W)
        band(px, c * CARD_W)
    return im

SIGNS = [('data/UI/UI_COMMON_MARKERS.G1T', 10, '+'), ('data/UI/UI_COMMON_MARKERS.G1T', 11, '-')]
SIGN_BOX = (6, 6, 30, 30)        # paper inside the coloured frame
SIGN_INK = (40, 36, 30)

def sign(im, kind):
    im = im.convert('RGBA')
    px = im.load()
    x0, y0, x1, y1 = SIGN_BOX
    luma = lambda c: (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000
    for y in range(y0, y1):
        row = [px[x, y] for x in range(x0, x1)]
        med = sorted(luma(c) for c in row)[len(row) * 3 // 4]
        paper = [c for c in row if luma(c) >= med - 8]
        avg = tuple(sum(c[k] for c in paper) // len(paper) for k in range(4))
        for x in range(x0, x1):
            if luma(px[x, y]) < med - 8:
                px[x, y] = avg
    S = 8
    mask = Image.new('L', (im.width * S, im.height * S), 0)
    d = ImageDraw.Draw(mask)
    cx, cy, half, th = 18 * S, 18 * S, 8 * S, 2.6 * S
    d.rectangle((cx - half, cy - th / 2, cx + half, cy + th / 2), fill=255)
    if kind == '+':
        d.rectangle((cx - th / 2, cy - half, cx + th / 2, cy + half), fill=255)
    mask = mask.resize(im.size, Image.LANCZOS)
    ink = Image.new('RGBA', im.size, SIGN_INK + (255,))
    im.paste(ink, (0, 0), mask)
    return im

TILES = ('data/BASE/MAIN.G1T', 2, [(448, 'N'), (512, 'P')])
TILE, TILE_N, TILE_BORDER = 32, 20, 2
TILE_FONT, TILE_SIZE = '/usr/share/fonts/noto/NotoSerif-Bold.ttf', 23
TILE_HALO = 0.64          # halo = fill + 0.64 x (white - fill)
TILE_HALO_W = 2.2         # halo width (px)

def tile(fill, letter):
    S = 8
    n = TILE * S
    font = ImageFont.truetype(TILE_FONT, TILE_SIZE * S)
    halo = tuple(round(c + TILE_HALO * (255 - c)) for c in fill)
    big = Image.new('RGB', (n, n), fill)
    d = ImageDraw.Draw(big)
    l, t, r, b = d.textbbox((0, 0), letter, font=font, stroke_width=0)
    x, y = (n - (r - l)) / 2 - l, (n - (b - t)) / 2 - t
    d.text((x, y), letter, font=font, fill=halo, stroke_width=round(TILE_HALO_W * S), stroke_fill=halo)
    d.text((x, y), letter, font=font, fill=(0, 0, 0))
    im = big.resize((TILE, TILE), Image.LANCZOS).convert('RGBA')
    ImageDraw.Draw(im).rectangle((0, 0, TILE - 1, TILE - 1), outline=(0, 0, 0, 255), width=TILE_BORDER)
    return im

def tiles(im, rows):
    im = im.convert('RGBA')
    for y0, letter in rows:
        for k in range(TILE_N):
            x, y = (k % 16) * TILE, y0 + (k // 16) * TILE
            fill = im.getpixel((x + 3, y + 3))[:3]
            im.paste(tile(fill, letter), (x, y))
    return im

# Duel status panel buff markers 攻撃 防御 命中 移動 (seen 2026-11-07, dojo duel tutorial):
# atlas of 2 columns (grey = off, coloured = on) x 4 rows of 68 x 52 cells; each cell is
# redrawn with an English word in the cell's own fill and outline colours (BC1: alpha 0/1).
STATUS = ('data/UI/UI_BATTLE_PBATTLE.G1T', 2, 'STATUS')
STATUS_CELL = (68, 52)
STATUS_WORDS = ['ATK', 'DEF', 'HIT', 'MOV']
STATUS_FONT, STATUS_SIZE, STATUS_STROKE = '/usr/share/fonts/noto/NotoSerif-Bold.ttf', 25, 3

def status(im):
    im = im.convert('RGBA')
    cw, ch = STATUS_CELL
    luma = lambda c: (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    S = 4
    font = ImageFont.truetype(STATUS_FONT, STATUS_SIZE * S)
    for row, word in enumerate(STATUS_WORDS):
        for col in range(2):
            box = (col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)
            px = [c for c in im.crop(box).getdata() if c[3] > 128]
            px.sort(key=luma)
            n = len(px)
            avg = lambda sel: tuple(sum(c[k] for c in sel) // len(sel) for k in range(3))
            ink, edge = avg(px[n * 9 // 10:]), avg(px[:n // 3])
            big = Image.new('RGBA', (cw * S, ch * S), (0, 0, 0, 0))
            d = ImageDraw.Draw(big)
            l, t, r, b = d.textbbox((0, 0), word, font=font, stroke_width=STATUS_STROKE * S)
            x, y = (cw * S - (r - l)) / 2 - l, (ch * S - (b - t)) / 2 - t
            d.text((x, y), word, font=font, fill=ink + (255,), stroke_width=STATUS_STROKE * S,
                   stroke_fill=edge + (255,))
            cell = big.resize((cw, ch), Image.LANCZOS)
            a = cell.getchannel('A').point(lambda v: 255 if v >= 100 else 0)
            cell.putalpha(a)
            out.paste(cell, box[:2])
    return out

def make(data, t, lines):
    if lines == 'STATUS':
        return status(g1t.decode(data, t))
    if isinstance(lines, list) and lines and isinstance(lines[0], tuple):
        return tiles(g1t.decode(data, t), lines)
    if lines is None:
        return cards(g1t.decode(data, t))
    if lines in ('+', '-'):
        return sign(g1t.decode(data, t), lines)
    return render(t.w, t.h, lines)

def build_file(data, items):
    ts = g1t.textures(data)
    for i, lines in items:
        t = ts[i]
        im = make(data, t, lines)
        data = g1t.replace(data, i, im)
    return data

def jobs():
    out = [(f, i, lines) for f, i, lines in load_tl()]
    return out + [(CARDS[0], CARDS[1], None)] + SIGNS + [TILES, STATUS]

def apply(game):
    files = {}
    by_file = {}
    for f, i, lines in jobs():
        by_file.setdefault(f, []).append((i, lines))
    for f, items in by_file.items():
        data = open(os.path.join(game, f), 'rb').read()
        files[f] = build_file(data, items)
    return files

def preview(out):
    ims = []
    for f, i, lines in jobs():
        data = open(os.path.join(setup.CLEAN, f), 'rb').read()
        t = g1t.textures(data)[i]
        new = make(data, t, lines)
        for im in (g1t.decode(data, t), new):
            ims.append(im.resize((im.width * 3, im.height * 3), Image.NEAREST))
    W = max(i.width for i in ims)
    sheet = Image.new('RGBA', (W, sum(i.height + 10 for i in ims)), (60, 90, 60, 255))
    y = 0
    for i in ims:
        sheet.alpha_composite(i, (0, y))
        y += i.height + 10
    sheet.save(out)

if __name__ == '__main__':
    if sys.argv[1] == 'preview':
        preview(sys.argv[2])
