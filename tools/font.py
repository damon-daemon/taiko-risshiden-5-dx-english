"""FONT_JPN.G1T: decode textures, and redraw the ASCII glyphs with the Latin face.

usage: font.py dump G1T OUTDIR             # every texture's alpha channel as PNG
       font.py build CLEAN_G1T OUT_G1T     # ASCII 0x20-0x7E of texture 49 redrawn
       font.py preview OUT.png             # sample text with the new glyphs/advances

G1T 'GT1G0600': u32 file size, u32 offset of the offset table (0xE4), u32 count.
Offsets are relative to the table. Each texture: 8-byte header (byte 1 = format 0x5B
BC3, byte 2 = log2 dims 0x99 = 512x512) + 12-byte extension + 512*512 bytes of BC3.
Glyphs are the alpha channel, 32x32 cells, 16x16 per texture. Texture 49 holds the
single-byte codes (cell = code). The glyph UV code (0x140691AC5) samples codes <= 0x3F
from the left half (16x32) of their cell and codes >= 0x40 from the whole 32x32 cell,
squeezed into the same half-width quad (verified in game). So codes >= 0x40 are stored
stretched 2x horizontally.
Geometry below is in "half-cell" pixels (16 x 32).

The engine spaces single-byte glyphs by a fixed half width; exepatch.py replaces that
with ADVANCE (quarter texture pixels per code 0x20-0x7E), scaled to the font size.
"""
import io, os, struct, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import latinfont as lf

TEX = 512
CELL = 32
ASCII_TEX = 49

# Metrics in texture pixels (cell 16 x 32). The JP face: caps rows 4-28, descenders to 30.
BASE = 26.0          # baseline; descenders (3 units) end at row 31
CAP = 20.5           # cap height (outer edges)
STROKE = 2.5
LEFT = 1.0           # left side bearing (outer ink edge)
GAP = 2.0            # space after the right ink edge (+ LEFT before the next glyph)
TIGHT_CUT = 1.0      # less after glyphs open on the right (lf.TIGHT: r f t y)
SPACE_EXTRA = 2.0    # word space wider than the stroke font's own
MAXINK = 16 - GAP    # rightmost ink edge: advance must stay <= the 16 px cell. A wider advance
                     # makes the message window stretch the whole cell (seen 2026-11-06: 'w'
                     # at 17.25 inked to its edge, 'now in' read as 'nowin'); wide glyphs are
                     # drawn narrower instead.
SS = 8
KEEP = '\\'           # 0x5C is the yen sign in Shift-JIS: keep the game's glyph and width

def textures(data):
    assert data[:8] == b'GT1G0600', data[:8]
    size, tbl, count = struct.unpack_from('<3I', data, 8)
    offs = struct.unpack_from('<%dI' % count, data, tbl)
    out = []
    for o in offs:
        p = tbl + o
        assert data[p + 1] == 0x5B and data[p + 2] == 0x99, data[p:p + 8].hex()
        out.append(p + 20)
    return out

def dds(block_data):
    """A DDS file around TEX x TEX BC3 data (for Pillow)."""
    h = struct.pack('<4s7I44x2I4s20xI16x', b'DDS ', 124, 0x81007, TEX, TEX, TEX * TEX, 0, 1,
                    32, 4, b'DXT5', 0x1000)
    return h + block_data

def decode(data, i):
    p = textures(data)[i]
    im = Image.open(io.BytesIO(dds(data[p:p + TEX * TEX])))
    im.load()
    return im.convert('RGBA')

def encode(im):
    """RGBA TEX x TEX -> BC3 bytes (Pillow's encoder)."""
    f = io.BytesIO()
    im.save(f, 'DDS', pixel_format='DXT5')
    d = f.getvalue()
    return d[len(d) - TEX * TEX:]

# ---- glyphs ---------------------------------------------------------------------

def stretched(c):
    return ord(c) >= 0x40

def draw(c, f=1.0):
    """Alpha image of character c with its x scaled by f: 32 x 32 (stretched 2x) for
    codes >= 0x40, else 16 x 32 -> (img, right ink edge in half-cell px)."""
    w, strokes = lf.GLYPHS[c]
    s = (CAP - STROKE) / lf.C
    img = Image.new('L', (16 * SS, CELL * SS), 0)
    dr = ImageDraw.Draw(img)
    x0 = LEFT + STROKE / 2
    r = STROKE * SS / 2
    for st in strokes:
        pts = [((x0 + x * s * f) * SS, (BASE - STROKE / 2 - y * s) * SS) for x, y in st]
        if len(pts) > 1:
            dr.line(pts, fill=255, width=round(STROKE * SS), joint='curve')
        for px, py in pts[:1] + pts[-1:]:
            dr.ellipse((px - r, py - r, px + r, py + r), fill=255)
    xs = [x for st in strokes for x, y in st]
    right = x0 + max(xs) * s * f + STROKE / 2 if xs else None
    return img.resize((CELL if stretched(c) else 16, CELL), Image.BOX), right

def glyphs():
    """-> {char: (alpha image (see draw), advance in half-cell px)}."""
    s = (CAP - STROKE) / lf.C
    out = {}
    for c in lf.CHARS:
        if c in KEEP:
            continue
        f = 1.0
        while True:
            img, right = draw(c, f)
            if right is None or right <= MAXINK:
                break
            f *= 0.97
        if right is None:
            adv = lf.GLYPHS[c][0] * s + LEFT + SPACE_EXTRA * (c == " ")
        else:
            adv = right + GAP - TIGHT_CUT * (c in lf.TIGHT)
        out[c] = (img, adv)
    return out

def advance_table():
    """Bytes for codes 0x20-0x7E: advance in quarter half-cell pixels."""
    g = glyphs()
    return bytes(min(255, round(g[c][1] * 4)) if c in g else 64 for c in lf.CHARS)

# ---- build --------------------------------------------------------------------

def build(data):
    data = bytearray(data)
    p = textures(data)[ASCII_TEX]
    im = decode(data, ASCII_TEX)
    g = glyphs()
    alpha = im.getchannel('A')
    for c, (img, adv) in g.items():
        code = ord(c)
        x, y = code % 16 * CELL, code // 16 * CELL
        alpha.paste(0, (x, y, x + CELL, y + CELL))
        alpha.paste(img, (x, y))
    rgb = Image.new('RGB', im.size, (255, 255, 255))
    new = encode(Image.merge('RGBA', (*rgb.split(), alpha)))
    # replace only the 4x4 blocks of the ASCII cells (rows 2-7 of cells)
    bw = TEX // 4
    for code in range(0x20, 0x7F):
        cx, cy = code % 16 * CELL // 4, code // 16 * CELL // 4
        for by in range(cy, cy + CELL // 4):
            o = (by * bw + cx) * 16
            data[p + o:p + o + CELL // 4 * 16] = new[o:o + CELL // 4 * 16]
    return bytes(data)

def preview(path, text='The quick brown fox jumps over the lazy dog! 0123456789 (Oda Nobunaga) '
                       '"Kinoshita" WWMM iiii #$%&*+,-./:;<=>?@[\\]^_`{|}~', scale=24 / 32):
    """Text rendered as the game would at a 24 px font (glyph images drawn half-width)."""
    g = glyphs()
    tbl = advance_table()
    half = round(32 * scale / 2)
    lines = [text[i:i + 50] for i in range(0, len(text), 50)]
    H = round(CELL * scale)
    W = max(sum((tbl[ord(c) - 0x20] * half + 32) // 64 for c in l) for l in lines) + 8
    out = Image.new('L', (W, H * len(lines) + 4), 0)
    for k, l in enumerate(lines):
        x = 4
        for c in l:
            if c in g:
                img = g[c][0].resize((half, H), Image.BILINEAR)
                out.paste(255, (x, k * H + 2), img)
            x += (tbl[ord(c) - 0x20] * half + 32) // 64
    bg = Image.new('RGB', out.size, (235, 230, 215))
    bg.paste((30, 30, 30), (0, 0), out)
    bg.resize((W * 2, bg.height * 2), Image.NEAREST).save(path)

def main():
    cmd = sys.argv[1]
    if cmd == 'dump':
        data = open(sys.argv[2], 'rb').read()
        os.makedirs(sys.argv[3], exist_ok=True)
        for i in range(len(textures(data))):
            decode(data, i).getchannel('A').save(os.path.join(sys.argv[3], 't%02d_a.png' % i))
    elif cmd == 'build':
        open(sys.argv[3], 'wb').write(build(open(sys.argv[2], 'rb').read()))
        print('wrote', sys.argv[3])
    elif cmd == 'preview':
        preview(sys.argv[2])
    else:
        raise SystemExit(__doc__)

if __name__ == '__main__':
    main()
