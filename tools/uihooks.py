"""Small exe layout hooks for English UI (code stubs in the .tl section).

CARD_LABEL: card list (title menu "Cards"): the category label (ui 1844-1849) was a
vertical text box 34 x 102 px on the card (English wrapped every 2 letters). Now a
horizontal box across the card, the text centered through the printf-style setter
0x140029dd4 (obj, flags 0, x = w/2, y 0, 0, 0, align 1 = center, "%s", text), like the
card's count line below it. The printf setter resets the colour: the stub sets it again
(0xE, or 7 when [r14 + [rbx+0x68]] != 0, as the original code before it).

CARD_READING: card detail panel (0x140463290) printed the kana reading above the name
(reading dispatcher 0x14036bfb0 via thunk 0x14002b585): that call returns "" instead.

SHOW: Power Map "Other" (0x140481d20): the 3 "Show" checkboxes (Merchant House / Ninja /
Pirates, ui 481/164/165) sat 148 px apart (later ones 34 px left), labels 68/102 px:
"Merchant House" ran into "Ninja". The x of each item (edi, checkbox at +0x1e, label at
+0x45) now comes from SHOW_X, and item 0's label pointer (array 0x142582C28) is set to
"Merchants" (ui 481 itself is used elsewhere). The hover frame (hit test loop
0x140483ff0, same formula) takes its x from SHOW_X too (SHOW_CURSOR_SITE).

BASEMAP: destination map / bases map panel (0x1406e0f00): header "Basic"+"Info" (ui 1344 +
1384) went through the pooled "%s%s" (0x140B4D044): now the lone "%s %s" at 0x140C12A48.
Its 4 checkboxes Castle/Town/Village/Fort (ui 179/180/183/184) sat 110 px apart from
x 0x24 (labels 34 px at +0x27): the checkbox x now comes from BASEMAP_X (index r12d),
the hover frame (0x1406e4fd0, index r14d) from the same table minus 6.

COLWIDTH: list column widths copied at first use from the runtime width table into
static column tables (e.g. 0x140638bc0: Bases list, Ninja Village tab, 32-byte entries).
Ninja Village: "14 (Medium)" ran into Backed Daimyo; Holder gives 25 px to Size.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))

CARD_W = 176                  # box width = the card's width on screen
CARD_X, CARD_Y = 0, 0x70      # box offset on the card (was 0x24, 0x70)
CARD_H = 0x28                 # box height (was 0x66)
# (va, old bytes, new asm or None for the stub call)
CARD_PATCHES = [
    (0x14042E6CC, 'c7 45 6f 24 00 00 00 c7 45 73 70 00 00 00',
     'mov dword ptr [rbp + 0x6f], %d\nmov dword ptr [rbp + 0x73], %d' % (CARD_X, CARD_Y)),
    (0x14042E70C, 'c7 44 24 20 66 00 00 00 41 b9 22 00 00 00',
     'mov dword ptr [rsp + 0x20], %d\nmov r9d, %d' % (CARD_H, CARD_W)),
]
# card list tabs (0x14042eb70): box 102 x 34, text centered at x 51 via the printf setter;
# "Techniques" wrapped. Wider box, same center (text may start left of the box).
TAB_W = 0x90
CARD_PATCHES.append((0x14042EE8C, '41 b9 66 00 00 00', 'mov r9d, %d' % TAB_W))
CARD_TEXT = (0x14042E758, '45 33 c9 48 8b 45 bf 4e 8b 04 38 33 d2 48 8b cf e8 1f c9 bd ff')
CARD_STUB = """
push rbx
sub rsp, 0x50
mov rax, qword ptr [rbp - 0x41]
mov rax, qword ptr [rax + r15]
mov qword ptr [rsp + 0x40], rax
lea rax, [rip + fmt_s]
mov qword ptr [rsp + 0x38], rax
mov dword ptr [rsp + 0x30], 1
mov qword ptr [rsp + 0x28], 0
mov qword ptr [rsp + 0x20], 0
xor r9d, r9d
mov r8d, {half}
xor edx, edx
mov rcx, rdi
call 0x140029dd4
mov rcx, qword ptr [rbx + 0x68]
mov edx, 0xe
cmp dword ptr [r14 + rcx], 0
mov eax, 7
cmova dx, ax
mov rcx, rdi
call 0x14002c2af
add rsp, 0x50
pop rbx
ret
fmt_s:
.byte 0x25, 0x73, 0
"""

CARD_READING = (0x140463464, 'e8 1c 81 bc ff')
EMPTY_STUB = """
lea rax, [rip + empty]
ret
empty:
.byte 0
"""

SHOW_SITE = (0x140481F05, '41 8b c7 45 85 f6 0f 45 c1 41 8b fc 2b f8')
SHOW_CURSOR_SITE = (0x140484128, 'b8 22 00 00 00 0f 45 d0 8b c6 2b c2')
SHOW_CURSOR_STUB = """
lea rax, [rip + tbl]
mov eax, dword ptr [rax + r14*4]
ret
tbl:
{tbl}
"""
SHOW_ARRAY = 0x142582C28
SHOW_X = (-6, 170, 282)
SHOW_STUB = """
here:
lea rax, [rip + tbl]
mov edi, dword ptr [rax + r14*4]
test r14d, r14d
jne done
push rcx
lea rcx, [rip + here]
add rcx, {arr_rel}
lea rax, [rip + merch]
mov qword ptr [rcx], rax
pop rcx
done:
ret
tbl:
{tbl}
merch:
.byte {merch}
"""

BASEMAP_FMT = (0x1406E1006, '4c 8d 05 37 c0 46 00', 0x140C12A48)
BASEMAP_X = (16, 134, 238, 359)
BASEMAP_LABEL_DX = 0x24         # label x - checkbox x (was 0x27)
BASEMAP_LABEL = (0x1406E10E6, '41 8d 55 27 c7 44 24 20 22 00 00 00')
BASEMAP_LABEL_STUB = """
lea rax, [rip + tbl]
mov edx, dword ptr [rax + r12*4]
add edx, {dx}
mov dword ptr [rsp + 0x28], 0x22
ret
tbl:
{tbl}
"""
BASEMAP_BOX = (0x1406E114C, 'c7 44 24 20 20 00 00 00 41 b9 20 00 00 00 45 8d 41 32 41 8b d5')
BASEMAP_BOX_STUB = """
lea rax, [rip + tbl]
mov edx, dword ptr [rax + r12*4]
mov dword ptr [rsp + 0x28], 0x20
mov r9d, 0x20
mov r8d, 0x52
ret
tbl:
{tbl}
"""
BASEMAP_HOVER = (0x1406E50EC, '89 7c 24 28 c7 44 24 2c 4c 00 00 00')
BASEMAP_HOVER_STUB = """
push rax
lea rax, [rip + tbl]
mov eax, dword ptr [rax + r14*4]
sub eax, 6
mov dword ptr [rsp + 0x38], eax
mov dword ptr [rsp + 0x3c], 0x4c
pop rax
ret
tbl:
{tbl}
"""

# (site of "mov eax, [rip + d]" (6 bytes), width address it loads, delta)
COLWIDTH = [
    (0x140638D18, 0x1425C3318, -25),     # Ninja Village: Holder
    (0x140638D32, 0x1425C3338, +25),     # Ninja Village: Size
]
COLWIDTH_STUB = """
here:
lea rax, [rip + here]
add rax, {rel}
mov eax, dword ptr [rax]
add eax, {delta}
ret
"""

def _stub(seg, ks, src):
    va = seg.add(b'', align=16, share=False)
    assert seg.add(bytes(ks.asm(src, va)[0]), share=False) == va
    return va

def _patch(seg, ks, at, old, asm_src):
    o = seg.va2off(at)
    old = bytes.fromhex(old)
    if bytes(seg.exe[o:o + len(old)]) != old:
        raise SystemExit('uihooks: patch %X: expected %s, found %s' % (at, old.hex(), seg.exe[o:o + len(old)].hex()))
    b = bytes(ks.asm(asm_src, at)[0])
    assert len(b) <= len(old), (hex(at), len(b))
    seg.exe[o:o + len(old)] = b + b'\x90' * (len(old) - len(b))

def apply(seg):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    va = seg.add(b'', align=16, share=False)
    code = bytes(ks.asm(CARD_STUB.format(half=CARD_W // 2), va)[0])
    assert seg.add(code, share=False) == va
    for at, old, src in CARD_PATCHES:
        _patch(seg, ks, at, old, src)
    _patch(seg, ks, CARD_TEXT[0], CARD_TEXT[1], 'call 0x%x' % va)
    va = seg.add(b'', align=16, share=False)
    assert seg.add(bytes(ks.asm(EMPTY_STUB, va)[0]), share=False) == va
    _patch(seg, ks, CARD_READING[0], CARD_READING[1], 'call 0x%x' % va)
    va = seg.add(b'', align=16, share=False)
    src = SHOW_STUB.format(arr_rel=SHOW_ARRAY - va,
                           tbl='\n'.join('.long %d' % x for x in SHOW_X),
                           merch=', '.join(str(c) for c in b'Merchants\0'))
    assert seg.add(bytes(ks.asm(src, va)[0]), share=False) == va
    _patch(seg, ks, SHOW_SITE[0], SHOW_SITE[1], 'call 0x%x' % va)
    va = seg.add(b'', align=16, share=False)
    src = SHOW_CURSOR_STUB.format(tbl='\n'.join('.long %d' % x for x in SHOW_X))
    assert seg.add(bytes(ks.asm(src, va)[0]), share=False) == va
    _patch(seg, ks, SHOW_CURSOR_SITE[0], SHOW_CURSOR_SITE[1], 'call 0x%x' % va)
    at, old, target = BASEMAP_FMT
    _patch(seg, ks, at, old, 'lea r8, [rip + 0x%x]' % (target - (at + 7)))
    tbl = '\n'.join('.long %d' % x for x in BASEMAP_X)
    for (at, old), src in ((BASEMAP_LABEL, BASEMAP_LABEL_STUB), (BASEMAP_BOX, BASEMAP_BOX_STUB),
                           (BASEMAP_HOVER, BASEMAP_HOVER_STUB)):
        _patch(seg, ks, at, old, "call 0x%x" % _stub(seg, ks, src.format(tbl=tbl, dx=BASEMAP_LABEL_DX)))
    for at, src_va, delta in COLWIDTH:
        o = seg.va2off(at)
        disp = int.from_bytes(seg.exe[o + 2:o + 6], 'little', signed=True)
        assert seg.exe[o:o + 2] == b'\x8b\x05' and at + 6 + disp == src_va, hex(at)
        va = seg.add(b'', align=16, share=False)
        code = bytes(ks.asm(COLWIDTH_STUB.format(rel=src_va - va, delta=delta), va)[0])
        assert seg.add(code, share=False) == va
        _patch(seg, ks, at, seg.exe[o:o + 6].hex(), 'call 0x%x' % va)
    return 8 + len(COLWIDTH)
