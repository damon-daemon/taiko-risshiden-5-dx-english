"""G1T textures (GT1G0046 UI files and GT1G0600 fonts): list, decode, encode.

usage: g1t.py list G1T
       g1t.py dump G1T OUTDIR        # every texture as PNG (RGBA)

GT1G0046 layout: 'GT1G0046', u32 file size, u32 offset table position, u32 count, ...
Offsets are relative to the table. Texture header 8 bytes: [1] format, [2] log2 dims
(lo = width, hi = height; 0 = given in the extension), [7] = 1 extension follows;
extension: u32 size (0x14), 8 bytes, u32 width, u32 height (when dims byte is 0).
Formats: 0x01 RGBA8 (bytes R G B A? see decode), 0x59 BC1/DXT1, 0x5B BC3/DXT5.
MRLK files are containers of G1Ts (not handled here).
"""
import io, os, struct, sys
from PIL import Image

BPP = {0x01: 32, 0x59: 4, 0x5B: 8}

class Tex:
    def __init__(self, data, pos):
        h = data[pos:pos + 8]
        self.pos, self.fmt = pos, h[1]
        self.w, self.h = 1 << (h[2] & 15), 1 << (h[2] >> 4)
        ext = 0
        if h[7]:
            ext = struct.unpack_from('<I', data, pos + 8)[0]
            if h[2] == 0:
                self.w, self.h = struct.unpack_from('<2I', data, pos + 8 + 12)
        self.data_pos = pos + 8 + ext
        self.size = self.w * self.h * BPP[self.fmt] // 8

def textures(data):
    assert data[:4] == b'GT1G', data[:8]
    size, tbl, count = struct.unpack_from('<3I', data, 8)
    offs = struct.unpack_from('<%dI' % count, data, tbl)
    return [Tex(data, tbl + o) for o in offs]

def _dds(t, raw):
    fourcc = {0x59: b'DXT1', 0x5B: b'DXT5'}[t.fmt]
    h = struct.pack('<4s7I44x2I4s20xI16x', b'DDS ', 124, 0x81007, t.h, t.w, len(raw), 0, 1,
                    32, 4, fourcc, 0x1000)
    return h + raw

def decode(data, t):
    raw = data[t.data_pos:t.data_pos + t.size]
    if t.fmt == 0x01:
        return Image.frombytes('RGBA', (t.w, t.h), raw, 'raw', 'BGRA')
    im = Image.open(io.BytesIO(_dds(t, raw)))
    im.load()
    return im.convert('RGBA')

def encode(t, im):
    if t.fmt == 0x01:
        return im.convert('RGBA').tobytes('raw', 'BGRA')
    f = io.BytesIO()
    im.save(f, 'DDS', pixel_format={0x59: 'DXT1', 0x5B: 'DXT5'}[t.fmt])
    d = f.getvalue()
    return d[len(d) - t.size:]

def replace_resized(data, i, im):
    """Replace texture i (RGBA8 with explicit dims in its extension) by an image of any
    size: the texture's data grows or shrinks, later offsets and the file size follow."""
    ts = textures(data)
    t = ts[i]
    h = data[t.pos:t.pos + 8]
    assert t.fmt == 0x01 and h[2] == 0 and h[7], 'replace_resized: needs RGBA8 with ext dims'
    raw = im.convert('RGBA').tobytes('raw', 'BGRA')
    head = bytearray(data[t.pos:t.data_pos])
    struct.pack_into('<2I', head, 8 + 12, im.width, im.height)
    new_t = bytes(head) + raw
    old_end = t.data_pos + t.size
    delta = len(new_t) - (old_end - t.pos)
    out = bytearray(data[:t.pos] + new_t + data[old_end:])
    size, tbl, count = struct.unpack_from('<3I', data, 8)
    offs = list(struct.unpack_from('<%dI' % count, data, tbl))
    for k in range(count):
        if tbl + offs[k] > t.pos:
            offs[k] += delta
    struct.pack_into('<%dI' % count, out, tbl, *offs)
    struct.pack_into('<I', out, 8, size + delta)
    return bytes(out)

def replace(data, i, im):
    t = textures(data)[i]
    raw = encode(t, im)
    assert len(raw) == t.size
    out = bytearray(data)
    out[t.data_pos:t.data_pos + t.size] = raw
    return bytes(out)

def main():
    cmd, path = sys.argv[1:3]
    data = open(path, 'rb').read()
    ts = textures(data)
    if cmd == 'list':
        for i, t in enumerate(ts):
            print(i, hex(t.fmt), t.w, t.h, hex(t.data_pos))
    elif cmd == 'dump':
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        for i, t in enumerate(ts):
            decode(data, t).save(os.path.join(out, '%02d.png' % i))

if __name__ == '__main__':
    main()

def mrlk(data):
    """MRLK container -> [(offset, size)] of its member files."""
    assert data[:4] == b'MRLK'
    n = struct.unpack_from('<I', data, 4)[0]
    return [struct.unpack_from('<2I', data, 8 + 8 * i) for i in range(n)]
