"""World-map place labels: horizontal plates for English names.

The map label code (0x1404A6550, one label per base/town) draws the name on a vertical
plate: plate 34 x L px, L = max(W + 16, 88) with W = the name measured by 0x14000568C
(font size 3), built from three slices of UI_MAP_MMAP.G1T tex 5 (136 x 114: four colour
columns of 34 px, top cap 43 / middle 28 / bottom cap 43; UV rects table 0x1425E30B0,
12 x 16 bytes, filled by 0x140169870 and used only here), and a text object one character
wide (x 5, y (L - W)/2, box 34 x L) so the Japanese stacks vertically. English in that box
wraps per letter (or, widened by the set-text hook, runs across the plate).

Now: the texture gets rotated copies of the four columns (114 x 34 each, row y = 114;
texture 456 x 148, the original area unchanged), the UV table points at their left cap /
middle / right cap, the plate is L x 34 with horizontal slices, and the text box is
L x 34 at x (L - W)/2, y 5. The positioning code after it centres the plate on the icon
by the plate's own height, so it needs no change.
"""
import os, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import g1t

TEX = ('data/UI/UI_MAP_MMAP.G1T', 5)
COL_W, CAP, MID = 34, 43, 28              # original column width, cap and middle heights
STRIP = CAP + MID + CAP                   # 114
# UV table order (entries 0-11 = 4 variants x left/middle/right): original column x
VARIANT_X = [0x22, 0x66, 0x00, 0x44]

def texture(data):
    ts = g1t.textures(data)
    t = ts[TEX[1]]
    im = g1t.decode(data, t)
    assert im.size == (4 * COL_W, STRIP), im.size
    out = Image.new('RGBA', (4 * STRIP, STRIP + COL_W), (0, 0, 0, 0))
    out.paste(im, (0, 0))
    for c in range(4):
        col = im.crop((c * COL_W, 0, (c + 1) * COL_W, STRIP))
        out.paste(col.transpose(Image.Transpose.ROTATE_90), (c * STRIP, STRIP))   # top cap -> left
    return g1t.replace_resized(data, TEX[1], out)

def apply_files(game):
    data = open(os.path.join(game, TEX[0]), 'rb').read()
    return {TEX[0]: texture(data)}

# ---------------------------------------------------------------- exe

UV_STUB = """
uv_base:
{fills}
add rsp, 0x38
ret
"""
UV_FILL = """
mov dword ptr [rsp + 0x20], {h}
mov r9d, {w}
mov r8d, {y}
mov edx, {x}
lea rcx, [rip + uv_base]
add rcx, {entry}
call 0x140003f21
"""
UV_TABLE = 0x1425E30B0

RECT_STUB = """
mov dword ptr [rsp + 0x20], {h}
mov r9d, {cap}
xor r8d, r8d
xor edx, edx
lea rcx, [rbp - 0x31]
call 0x140003f21
mov dword ptr [rsp + 0x20], {h}
mov r9d, dword ptr [rbp - 0x71]
sub r9d, {cap2}
xor r8d, r8d
mov edx, {cap}
lea rcx, [rbp - 0x21]
call 0x140003f21
mov dword ptr [rsp + 0x20], {h}
mov r9d, {cap}
xor r8d, r8d
mov edx, dword ptr [rbp - 0x71]
sub edx, {cap}
lea rcx, [rbp - 0x11]
call 0x140003f21
jmp 0x1404a6839
"""

TEXT_STUB = """
mov eax, dword ptr [rbp - 0x71]
sub eax, dword ptr [rbp - 0x69]
cdq
sub eax, edx
sar eax, 1
mov edx, eax
mov byte ptr [rsp + 0x38], 0
mov dword ptr [rsp + 0x30], {font}
mov dword ptr [rsp + 0x28], 2
mov eax, dword ptr [rbp - 0x6d]
mov dword ptr [rsp + 0x20], eax
mov r9d, dword ptr [rbp - 0x71]
mov r8d, {ty}
jmp 0x1404a6935
"""

# Name: the label asks 0x140023fc9 (town name + type suffix, sprintf into a static buffer
# rebuilt each call). User 2026-11-07: map labels show bare names (the icon shows the
# type): " Castle", " Manor", " Village", " Fort" are cut; " Temple" -> "ji" (the one
# temple base: "Ishiyama Hongan Temple" -> "Ishiyama Honganji"). Towns have no suffix.
SUFFIXES = [(' Castle', ''), (' Manor', ''), (' Village', ''), (' Fort', ''), (' Temple', 'ji')]
NAME_STUB = """
sub rsp, 0x28
call 0x140023fc9
add rsp, 0x28
push rsi
push rdi
mov rcx, rax
xor edx, edx
ns_len:
cmp byte ptr [rcx + rdx], 0
je ns_have
inc edx
cmp edx, 200
jb ns_len
jmp ns_ret
ns_have:
lea rsi, [rip + ns_tab]
ns_next:
movzx r8d, byte ptr [rsi]
test r8d, r8d
jz ns_ret
cmp edx, r8d
jbe ns_skip
lea rdi, [rcx + rdx]
sub rdi, r8
xor r9d, r9d
ns_cmp:
mov r10b, byte ptr [rsi + 2 + r9]
cmp r10b, byte ptr [rdi + r9]
jne ns_skip
inc r9d
cmp r9d, r8d
jb ns_cmp
movzx r9d, byte ptr [rsi + 1]
lea rsi, [rsi + 2 + r8]
xor r10d, r10d
ns_rep:
cmp r10d, r9d
jae ns_end
mov r11b, byte ptr [rsi + r10]
mov byte ptr [rdi + r10], r11b
inc r10d
jmp ns_rep
ns_end:
mov byte ptr [rdi + r10], 0
jmp ns_ret
ns_skip:
movzx r9d, byte ptr [rsi + 1]
lea rsi, [rsi + 2 + r8]
add rsi, r9
jmp ns_next
ns_ret:
pop rdi
pop rsi
ret
ns_tab:
{table}
"""

def name_stub():
    data = b''.join(bytes([len(a), len(b)]) + a.encode() + b.encode() for a, b in SUFFIXES) + b'\0'
    return NAME_STUB.replace('{table}', '.byte ' + ', '.join(str(x) for x in data))

# Label font: size id (0x140C7C628 table: 0 = 16 px, 1 = 14, 3 = 24 (original)), used to
# measure the name (0x1404A67A4) and for the text object. Smaller = shorter plates, less
# overlap between close places.
FONT = 0
FONT_PX = {0: 16, 1: 14, 3: 24}
PAD, MIN_L = 14, 40

# Labels drawn on the LEFT of their icon (towns table index = word [[base + 0x10] + 2],
# base = 0x14001a514(0x14001a096(), esi = base id) in 0x1404A6550): where
# a town and a castle sit side by side, the right-hand plate of the
# left member ran into its neighbour's icon. Normal x = icon right - 8; flipped x =
# icon left + 8 - L (L = plate width [[plate + 0x88] + 8], rcx = plate object;
# [rbp - 0x71] is only L when the label is created).
FLIP_LEFT = [225, 171, 269, 198, 294, 257, 226, 219, 252, 239, 221, 245, 234, 165, 151]
FLIP_STUB = """
push rcx
sub rsp, 0x28
call 0x14001a096
mov edx, esi
mov rcx, rax
call 0x14001a514
mov rcx, qword ptr [rax + 0x10]
movzx eax, word ptr [rcx + 2]
add rsp, 0x28
pop rcx
mov edx, dword ptr [r12]
cmp eax, {n}
jae fl_norm
lea r8, [rip + fl_bits]
bt dword ptr [r8], eax
jnc fl_norm
add edx, r14d
add edx, 8
mov r8, qword ptr [rcx + 0x88]
sub edx, dword ptr [r8 + 8]
jmp 0x1404a6a9e
fl_norm:
add edx, -8
add edx, edi
jmp 0x1404a6a9e
fl_bits:
{bits}
"""

def flip_stub():
    n = (max(FLIP_LEFT) // 8 + 4) & ~3
    bits = bytearray(n)
    for i in FLIP_LEFT:
        bits[i // 8] |= 1 << (i % 8)
    return FLIP_STUB.replace('{n}', str(8 * n)).replace('{bits}', '.byte ' + ', '.join(map(str, bits)))

# (va, original bytes (prefix checked), end of the replaced region, new code or stub name)
SITES = [
    # plate size {w, h} = {L, 34} (was {34, L})
    (0x1404A67C6, 'c7 45 8f 22 00 00 00 89 55 93', 0x1404A67D0,
     'mov dword ptr [rbp - 0x71], edx\nmov dword ptr [rbp - 0x6d], 0x22'),
    (0x1404A67E1, 'c7 44 24 20 2b 00 00 00 41 b9 22 00 00 00', 0x1404A6839, 'rect'),
    (0x1404A6900, '44 8b 4d 93 41 8b c1 2b 45 97', 0x1404A6935, 'text'),
    (0x140169880, '41 b9 22 00 00 00 c7 44 24 20 2b 00', 0x140169A06, 'uv'),
    (0x1404A679B, 'e8 29 d8 b7 ff', 0x1404A67A0, 'call name'),
    (0x1404A67A4, '41 b8 03 00 00 00', 0x1404A67AA, 'mov r8d, %d' % FONT),
    # plate length L = max(W + PAD, MIN_L) (was max(W + 16, 88))
    (0x1404A67B6, '8b 4d 97 83 c1 10 ba 58 00 00 00', 0x1404A67C1,
     'mov ecx, dword ptr [rbp - 0x69]\nadd ecx, %d\nmov edx, %d' % (PAD, MIN_L)),
    # plate x (flipped labels left of the icon)
    (0x1404A6A95, '41 8b 14 24 83 c2 f8 03 d7', 0x1404A6A9E, 'flip'),
]

def apply(seg):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    fills = []
    for v, x0 in enumerate(VARIANT_X):
        bx = (x0 // COL_W) * STRIP
        for k, (dx, w) in enumerate(((0, CAP), (CAP, MID), (CAP + MID, CAP))):
            fills.append(UV_FILL.format(h=COL_W, w=w, y=STRIP, x=bx + dx,
                                        entry='{off_%d}' % (3 * v + k)))
    stubs = {'uv': UV_STUB.format(fills=''.join(fills)),  # {off_n} filled at its address
             'rect': RECT_STUB.format(h=COL_W, cap=CAP, cap2=2 * CAP),
             'text': TEXT_STUB.replace('{font}', str(FONT)).replace('{ty}', str((34 - FONT_PX[FONT]) // 2 - 1)),
             'name': name_stub(), 'flip': flip_stub()}
    at = {}
    for name, src in stubs.items():
        va = seg.add(b'', align=16, share=False)
        for n in range(12):
            src = src.replace('{off_%d}' % n, '%d' % (UV_TABLE + 16 * n - va))
        assert seg.add(bytes(ks.asm(src, va)[0]), share=False) == va
        at[name] = va
    for va, old, end, src in SITES:
        o = seg.va2off(va)
        old = bytes.fromhex(old)
        if bytes(seg.exe[o:o + len(old)]) != old:
            raise SystemExit('maplabels: %X: expected %s, found %s' % (va, old.hex(), seg.exe[o:o + len(old)].hex()))
        if src in at:
            src = 'jmp 0x%x' % at[src]
        elif src.startswith('call ') and src[5:] in at:
            src = 'call 0x%x' % at[src[5:]]
        code = bytes(ks.asm(src, va)[0])
        assert len(code) <= end - va
        seg.exe[o:o + (end - va)] = code + b'\xcc' * (end - va - len(code))
    return len(SITES)

if __name__ == '__main__':
    import setup
    S = sys.argv[1] if len(sys.argv) > 1 else 'maplabels.png'
    d = texture(open(os.path.join(setup.CLEAN, TEX[0]), 'rb').read())
    t = g1t.textures(d)[TEX[1]]
    im = g1t.decode(d, t)
    bg = Image.new('RGBA', im.size, (60, 60, 60, 255))
    bg.alpha_composite(im)
    bg.resize((im.width * 3, im.height * 3), Image.NEAREST).save(S)
    print(S)
