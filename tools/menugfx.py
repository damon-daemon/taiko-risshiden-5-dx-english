"""Title menu card labels (data/CMENU/INITTOP.G1T): English drawn into the vertical tags.

INITTOP.G1T is an MRLK container of 34 G1Ts: 0-10 = the Japanese menu cards (11 = the
background), then the same 11 again twice (Chinese). Each card G1T holds one texture with
the card twice (normal, highlighted) plus a locked '???' card. The label sits in a
vertical paper tag with a brown frame: TAGS = the tag's outer box on the normal card;
TAGS_HI the highlighted card's (found with find_tag; the highlight adds a glow margin,
an orange frame and a pinker paper).

The kana are removed by filling each dark pixel from the nearest paper pixel of its row
(keeps the paper's vertical gradient and grain), then the English is drawn rotated to
read top to bottom, in Noto Serif (system font, OFL), in the original ink colour.

tl/menu.txt: "N<TAB>English" (N = G1T 0-10).
usage: menugfx.py preview OUT.png     # the 11 textures with English, scaled down
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import g1t, setup

TL = os.path.join(setup.ROOT, 'tl', 'menu.txt')
REL = 'data/CMENU/INITTOP.G1T'
FONT = '/usr/share/fonts/noto/NotoSerif-SemiBold.ttf'
# outer box of the tag on the normal card: x0, y0, x1, y1 (inclusive)
TAGS = {0: (345, 25, 414, 275), 1: (24, 13, 91, 186), 2: (353, 14, 422, 370),
        3: (48, 153, 115, 422), 4: (263, 106, 330, 373), 5: (76, 17, 143, 286),
        6: (221, 49, 290, 318), 7: (45, 20, 114, 287), 8: (370, 62, 437, 282),
        9: (145, 34, 214, 157), 10: (205, 24, 274, 251)}
# the same tag on the highlighted card (found once with find_tag: frame match right of
# the normal card, the highlight adds a glow margin and an orange frame)
TAGS_HI = {0: (781, 25, 850, 275), 1: (324, 13, 391, 186), 2: (805, 12, 874, 368),
           3: (648, 152, 715, 421), 4: (643, 106, 710, 373), 5: (596, 16, 663, 285),
           6: (553, 48, 622, 317), 7: (486, 20, 555, 287), 8: (826, 62, 893, 282),
           9: (385, 34, 454, 157), 10: (505, 25, 574, 252)}
FRAME = 7            # frame + margin left untouched inside the outer box
INK = (16, 12, 12)
SIZE = 38            # font px (shrunk per label if it does not fit)
PAD = 14             # free space at each end of the text (along the tag)

def load_tl():
    out = {}
    for line in open(TL, encoding='ascii').read().splitlines():
        if line.strip() and not line.startswith('#'):
            k, _, v = line.partition('\t')
            out[int(k)] = v
    return out

def luma(p):
    return (p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000

def is_frame(p):
    r, g, b, a = p
    # brown (normal card, ~129,85,41) or orange (highlighted, ~195,103,27)
    return a > 200 and r > g > b and r - b > 60 and b <= 65 and luma(p) < 140

def find_tag(im, box, search):
    """Box of the same tag in the highlighted card: best frame match in the search area."""
    px = im.load()
    x0, y0, x1, y1 = box
    pts = [(x, y) for y in range(y0, y1 + 1, 3) for x in (x0 + 1, x0 + 3, x1 - 1, x1 - 3)]
    pts += [(x, y) for x in range(x0, x1 + 1, 3) for y in (y0 + 1, y0 + 3, y1 - 1, y1 - 3)]
    sx0, sx1, sy0, sy1 = search
    best = None
    for dy in range(sy0, sy1 + 1):
        for dx in range(sx0, sx1 + 1):
            score = 0
            for x, y in pts:
                if 0 <= x + dx < im.width and 0 <= y + dy < im.height and is_frame(px[x + dx, y + dy]):
                    score += 1
            if best is None or score > best[0]:
                best = (score, dx, dy)
    score, dx, dy = best
    assert score > len(pts) * 0.6, ('tag not found', box, best, len(pts))
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)

def erase(im, box):
    """Fill the ink inside the tag from the nearest paper pixel of the same row."""
    px = im.load()
    x0, y0, x1, y1 = box[0] + FRAME, box[1] + FRAME, box[2] - FRAME, box[3] - FRAME
    W, H = x1 - x0 + 1, y1 - y0 + 1
    dark = [[luma(px[x0 + i, y0 + j]) < 150 for i in range(W)] for j in range(H)]
    R = 2                                       # halo around the strokes (antialiasing)
    ink = [[any(dark[jj][ii] for jj in range(max(0, j - R), min(H, j + R + 1))
                for ii in range(max(0, i - R), min(W, i + R + 1))) for i in range(W)] for j in range(H)]
    for j in range(H):
        y = y0 + j
        row = [px[x0 + i, y] for i in range(W)]
        paper = [i for i in range(W) if not ink[j][i]]
        for i in range(W):
            if ink[j][i]:
                if paper:
                    k = min(paper, key=lambda k: abs(k - i))
                    # mirror around the nearest paper pixel to keep the grain varied
                    m = 2 * k - i
                    px[x0 + i, y] = row[m if 0 <= m < W and not ink[j][m] else k]
                else:
                    px[x0 + i, y] = px[x0 + i, y - 1]

def label(text, box):
    """RGBA image of the text rotated to read top to bottom, fitted to the tag."""
    w = box[2] - box[0] + 1 - 2 * FRAME
    h = box[3] - box[1] + 1 - 2 * FRAME
    size = SIZE
    while True:
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = font.getbbox(text)
        asc, desc = font.getmetrics()
        if r - l <= h - 2 * PAD and asc + desc <= w + 6:
            break
        size -= 1
    im = Image.new('RGBA', (r - l + 4, asc + desc), INK + (0,))
    ImageDraw.Draw(im).text((2 - l, 0), text, font=font, fill=INK + (255,))
    return im.rotate(-90, expand=True), size

def draw(im, box, text):
    erase(im, box)
    lab, size = label(text, box)
    cx = (box[0] + box[2] + 1) // 2
    cy = (box[1] + box[3] + 1) // 2
    im.alpha_composite(lab, (cx - lab.width // 2, cy - lab.height // 2))
    return size

def card_texture(data, k):
    o, s = g1t.mrlk(data)[k]
    sub = data[o:o + s]
    return sub, g1t.textures(sub)[0]

def render(data, k, text):
    sub, t = card_texture(data, k)
    im = g1t.decode(sub, t)
    draw(im, TAGS[k], text)
    draw(im, TAGS_HI[k], text)
    return sub, im

def apply(game):
    data = bytearray(open(os.path.join(game, REL), 'rb').read())
    for k, text in sorted(load_tl().items()):
        sub, im = render(bytes(data), k, text)
        o, s = g1t.mrlk(data)[k]
        new = g1t.replace(sub, 0, im)
        assert len(new) == s
        data[o:o + s] = new
    return {REL: bytes(data)}

def preview(out):
    data = open(os.path.join(setup.CLEAN, REL), 'rb').read()
    ims = []
    for k, text in sorted(load_tl().items()):
        sub, im = render(data, k, text)
        ims.append(im.crop((0, 0, min(im.width, 900), im.height)))
    W = max(i.width for i in ims)
    sheet = Image.new('RGBA', (W, sum(i.height for i in ims)), (60, 60, 60, 255))
    y = 0
    for i in ims:
        sheet.alpha_composite(i, (0, y))
        y += i.height
    sheet.save(out)

if __name__ == '__main__':
    if sys.argv[1] == 'preview':
        preview(sys.argv[2])
