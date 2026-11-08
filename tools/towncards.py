"""Town facility cards (data/MP/MAINBOX.G1T): English drawn into the vertical tags.

Two files carry the cards: data/MP/HANAFUDA0_CROP.G1T (the cards in the town screen):
MRLK of 837 = 3 languages x 31 facilities x 9 variants (development levels, selected;
208 x 344 BC3, the card at varying offsets), and MAINBOX.G1T, an MRLK of 100 G1Ts: 0 = scroll frames, 1-31 = the Japanese facility cards
(128 x 292, BC1), 32-62 Simplified Chinese, 63-93 Traditional Chinese, 94-99 pictures.
Each card has a paper tag in the top-right corner with a 3-px dark frame, ~37 px wide,
~34 px long per kanji (MAINBOX: x 83-119, top 8); found per texture by find_tag.

The kanji are removed (menugfx.erase: fill from the nearest paper pixel of the row);
when the English needs more room than the tag has, the tag is lengthened downward by
repeating a strip of its (erased) paper and moving the bottom frame down. The English
reads top to bottom (rotated), one line, or two lines when one would be too long.

tl/towncards.txt: "N<TAB>English" (N = facility 1-31 = MAINBOX member); "|" splits the two lines.
usage: towncards.py preview OUT.png
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import g1t, menugfx, setup

TL = os.path.join(setup.ROOT, 'tl', 'towncards.txt')
REL = 'data/MP/MAINBOX.G1T'
CROP = 'data/MP/HANAFUDA0_CROP.G1T'
# file -> member index -> facility number (1-31, as in tl/towncards.txt)
MEMBERS = {REL: {k: k for k in range(1, 32)},
           CROP: {k: k // 9 + 1 for k in range(31 * 9)}}
# kanji in each facility's Japanese label (tag length)
KANJI = dict(enumerate(map(len, '''城 武家宅 城練兵場 米屋 馬屋 酒場 宿屋 民家 商家 医師宅 茶人宅
    寺 鍛冶屋 職人宅 南蛮寺 南蛮商館 公家宅 御所 座 道場 交易所 忍び屋敷 里練兵場 里修業場 忍び宅
    海賊屋敷 砦練兵場 砦修業場 造船所 海賊宅 自宅'''.split()), 1))
FONT = menugfx.FONT
INK = (12, 8, 8)
FRAME = 3             # frame width inside the tag box
SIZE1 = 21            # font px, one line (shrunk down to MIN1 to fit MAXLEN1)
MIN1 = 18
MAXLEN1 = 150         # longest one-line text (px) before going to two lines
SIZE2 = 15            # font px, two lines
PAD = 7               # paper left at each end of the text

def lum(p):
    return menugfx.luma(p)

# tag geometry (outer frame box), the same in every texture of a file/variant group:
# x0, x1, top; bottom = top + HEIGHT[number of kanji]. HANAFUDA0_CROP variants: 1-4 =
# card placed higher (tag top 16), 0 (dimmed) and 5-8 (tag top 40). Checked over all
# 310 textures: the frame rows match (a few cards have dark art touching the frame).
HEIGHT = {1: 42, 2: 74, 3: 108, 4: 135}
GEOM = {REL: lambda k: (83, 119, 8),
        CROP: lambda k: (145, 181, 16 if 1 <= k % 9 <= 4 else 40)}

def find_tag(im, geom, n):
    x0, x1, top = geom
    return x0, top, x1, top + HEIGHT[n]

def text_image(text, inner_w):
    """Rotated (top to bottom) RGBA text, at most inner_w px across."""
    lines = text.split('|')
    if len(lines) == 1:
        size = SIZE1
        while size > MIN1 and ImageFont.truetype(FONT, size).getlength(text) > MAXLEN1:
            size -= 1
        font = ImageFont.truetype(FONT, size)
        if font.getlength(text) > MAXLEN1 and ' ' in text:
            a, _, b = text.rpartition(' ')
            lines = [a, b]
    if len(lines) == 2:
        size = SIZE2
        font = ImageFont.truetype(FONT, size)
    asc, desc = font.getmetrics()
    lh = asc + desc - 2 if len(lines) == 2 else asc + desc
    while lh * len(lines) > inner_w + 6:
        size -= 1
        font = ImageFont.truetype(FONT, size)
        asc, desc = font.getmetrics()
        lh = asc + desc - 2 if len(lines) == 2 else asc + desc
    W = max(int(font.getlength(s)) + 2 for s in lines)
    im = Image.new('RGBA', (W, lh * len(lines)), INK + (0,))
    dr = ImageDraw.Draw(im)
    for i, s in enumerate(lines):
        dr.text(((W - font.getlength(s)) / 2, i * lh), s, font=font, fill=INK + (255,))
    # trim empty columns/rows so the text is centred on its ink
    bb = im.getbbox()
    im = im.crop((bb[0], 0, bb[2], im.height)) if bb else im
    return im.rotate(-90, expand=True)

def draw(im, text, geom, n):
    x0, y0, x1, y1 = find_tag(im, geom, n)
    menugfx.erase(im, (x0 - menugfx.FRAME + FRAME, y0 - menugfx.FRAME + FRAME,
                       x1 + menugfx.FRAME - FRAME, y1 + menugfx.FRAME - FRAME))
    lab = text_image(text, x1 - x0 + 1 - 2 * FRAME)
    need = lab.height + 2 * PAD + 2 * FRAME
    have = y1 - y0 + 1
    if need > have:
        # lengthen: keep the top, repeat a paper strip, move the bottom edge down
        ext = need - have
        bottom = im.crop((x0, y1 - 6, x1 + 1, y1 + 1))
        strip = im.crop((x0, y0 + FRAME + 2, x1 + 1, y0 + FRAME + 12))
        y = y1 - 6
        while y < y1 - 6 + ext:
            im.paste(strip, (x0, y))
            y += strip.height
        im.paste(bottom, (x0, y1 - 6 + ext))
        # soft shadow left of and under the new part (the art keeps showing through)
        px = im.load()
        for x, f in ((x0 - 1, 0.55), (x0 - 2, 0.7), (x0 - 3, 0.85)):
            for y in range(y1 + 1, y1 + ext + 3 + (x0 - x)):
                r, g, b, a = px[x, y]
                px[x, y] = (int(r * f), int(g * f), int(b * f), a)
        for y, f in ((y1 + ext + 1, 0.55), (y1 + ext + 2, 0.75)):
            for x in range(x0 - 3, x1 - 1):
                r, g, b, a = px[x, y]
                px[x, y] = (int(r * f), int(g * f), int(b * f), a)
        y1 += ext
    cx = (x0 + x1 + 1) // 2
    cy = (y0 + y1 + 1) // 2
    im.alpha_composite(lab, (cx - lab.width // 2, cy - lab.height // 2))

def load_tl():
    out = {}
    for line in open(TL, encoding='ascii').read().splitlines():
        if line.strip() and not line.startswith('#'):
            k, _, v = line.partition('\t')
            out[int(k)] = v
    return out

def render(data, k, text, rel=REL):
    o, s = g1t.mrlk(data)[k]
    sub = data[o:o + s]
    im = g1t.decode(sub, g1t.textures(sub)[0])
    draw(im, text, GEOM[rel](k), KANJI[MEMBERS[rel][k]])
    return sub, im

def apply(game):
    tl = load_tl()
    out = {}
    for rel, members in MEMBERS.items():
        data = bytearray(open(os.path.join(game, rel), 'rb').read())
        for k, n in sorted(members.items()):
            if n not in tl:
                continue
            sub, im = render(bytes(data), k, tl[n], rel)
            o, s = g1t.mrlk(data)[k]
            new = g1t.replace(sub, 0, im)
            assert len(new) == s
            data[o:o + s] = new
        out[rel] = bytes(data)
    return out

def preview(out, rel=REL, step=1, scale=2):
    data = open(os.path.join(setup.CLEAN, rel), 'rb').read()
    tl = load_tl()
    items = [(k, tl[n]) for k, n in sorted(MEMBERS[rel].items()) if n in tl][::step]
    W = 8
    sheet = None
    for i, (k, text) in enumerate(items):
        sub, im = render(data, k, text, rel)
        if sheet is None:
            cw, ch = im.width + 4, im.height + 4
            sheet = Image.new('RGBA', (W * cw, (len(items) + W - 1) // W * ch), (60, 60, 60, 255))
        # round-trip through the encoder to see the BC1 result
        new = g1t.replace(sub, 0, im)
        im = g1t.decode(new, g1t.textures(new)[0])
        sheet.alpha_composite(im, (i % W * cw, i // W * ch))
    sheet.resize((sheet.width * scale, sheet.height * scale), Image.LANCZOS).save(out)

if __name__ == '__main__':
    if sys.argv[1:2] == ['preview']:
        # preview OUT [crop [STEP]]: MAINBOX cards, or the in-town cards (every STEP-th)
        if sys.argv[3:4] == ['crop']:
            preview(sys.argv[2], CROP, int(sys.argv[4]) if len(sys.argv) > 4 else 1, 1)
        else:
            preview(sys.argv[2])
    else:
        print(__doc__)
