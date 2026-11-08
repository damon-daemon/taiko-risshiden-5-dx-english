"""Code patches for Taiko5DX.exe.

usage: exepatch.py CLEAN_EXE OUT_EXE

Each patch names a virtual address, the original bytes (checked; for a rewritten
function only its start) and the new bytes.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))

IMAGE_BASE = 0x140000000

# In Japanese mode the game turns ASCII letters into full-width Shift-JIS letters
# (a-z += 0x8220, A-Z += 0x821F) in two places: the "next character code" helper
# (0x140692F20) and the glyph advance function (0x1406930A0, which gives code > 0xFF
# the full-width advance). Skipping the Japanese branch (je -> jmp) keeps letters as
# single-byte ASCII.
PATCHES = [
    (0x140692FBE, '74 08', 'EB 08'),    # charcode a-z
    (0x14069300D, '74 08', 'EB 08'),    # charcode A-Z
    # KANA_READING: the reading converter (half-width kana -> full width, 0x140683230,
    # ~50 callers: lists of titles, schools, ...) returns "" when the reading does not
    # start with a high byte. English names that run on into a table's reading field
    # leave ASCII there, which it drew as ーーー. test cl, cl; je empty -> jns empty.
    (0x140683280, '74 56', '79 56'),
    # YIELD_UNIT: base panel yield sprintf("%d/%d%s", cur, max, ui 50 千石) gave
    # "39/100,000 koku"; the %s now takes ui 47 石 "koku" (buffer var 0x141099368) and
    # exestr 140c5a470 is "%dk/%dk %s" -> "39k/100k koku".
    (0x14046B76A, '48 8b 1d 0f dc c2 00', '48 8b 1d f7 db c2 00'),
]

# SAVE_HEADER: the save-slot header text is sprintf'd from this .rdata format (no direct
# reference found; patched in place, shorter) and stored in the save. The save/load list
# shows line 1 (play time), 4 (chapter), 5 (date), 6/7 (name) and line 3 after its "："
# (location). "：" kept (the load screen looks for that separator, see ui 506). Chapter
# names come from a second pointer table (ui.ALIASES).
SAVE_HEADER_VA = 0x140C65A20
SAVE_HEADER = ('%s %d年%d月%d日\n総時間：%d時間%02d分\n主人公：%s%s\n%s：%s\n%s\n%d年%d月%d日\n%s\n%s\n%d',
               '%s %d/%d/%d\nPlay time：%dh %02dm\n主人公：%s%s\n%s：%s\n%s\n%d/%d/%d\n%s\n%s\n%d')

def save_header_patch():
    old, new = [h.encode('cp932') for h in SAVE_HEADER]
    return (SAVE_HEADER_VA, (old + b'\0').hex(), new + b'\0' * (len(old) + 1 - len(new)))

# Proportional spacing: advance(code, full, half) (0x1406930A0, 196 bytes + 60 bytes of
# int3 padding) is rewritten: codes 0x20-0x7E get table[code] * half / 64 (table in
# quarter pixels of the 16-px-wide half cell, from font.py), other codes <= 0xFF the
# half width, larger codes the full width. The table follows the code in the same space.
ADVANCE_VA, ADVANCE_SIZE = 0x1406930A0, 0xC0     # + SPACING code up to 0x100
ADVANCE_ASM = """
    movzx eax, cx
    cmp eax, 0xff
    ja full
    sub eax, 0x20
    cmp eax, 0x5e
    ja half
    lea rcx, [rip + table]
    movzx eax, byte ptr [rcx + rax]
    imul eax, r8d
    add eax, 32
    shr eax, 6
    ret
half:
    mov eax, r8d
    ret
full:
    mov eax, edx
    ret
table:
"""

def advance_patch():
    import keystone, font
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    code, _ = ks.asm(ADVANCE_ASM, ADVANCE_VA)
    body = bytes(code) + font.advance_table()
    assert len(body) <= ADVANCE_SIZE, len(body)
    body += b'\xCC' * (ADVANCE_SIZE - len(body)) + spacing_code()
    assert len(body) <= 0x100, len(body)
    return (ADVANCE_VA, '48 89 5C 24 08 48 89 74 24 10 57',
            body + b'\xCC' * (0x100 - len(body)))

# Message backlog: the window (0x1406DE344) passes each character with column x/17 to
# 0x14041E9A0, which stores its bytes at that column of a 43-byte row (3 rows per entry,
# cleared when the entry starts, 0x14041C400). Proportional English characters share
# columns and overwrite each other, so the writer appends at the end of the row's text
# instead (same result for full-width text). Prologue (with its call) and epilogue kept.
BACKLOG_VA = 0x14041E9A0
BACKLOG_HEAD = ('48 89 5c 24 08 48 89 6c 24 10 48 89 74 24 18 57 48 83 ec 20 48 8b d9 49 63 f1'
                ' 48 8d 0d 33 f8 26 02 49 63 e8 48 8b fa e8 18 45 c0 ff')
BACKLOG_TAIL = '48 8b 5c 24 30 48 8b 6c 24 38 48 8b 74 24 40 48 83 c4 20 5f c3'
BACKLOG_SIZE = 0x90        # the last 0x20 bytes of int3 padding hold WRAP40_VA
BACKLOG_ASM = """
    movsxd rcx, dword ptr [rbx + 0x138]
    lea rcx, [rcx + rcx*2]
    add rcx, rsi
    imul rcx, rcx, 0x2b
    lea rcx, [rbx + rcx + 0x3e8]
    xor eax, eax
find:
    cmp byte ptr [rcx + rax], 0
    je copy
    inc eax
    cmp eax, 0x2a
    jl find
    jmp done
copy:
    movzx edx, byte ptr [rdi]
    test dl, dl
    je done
    mov byte ptr [rcx + rax], dl
    inc rdi
    inc eax
    cmp eax, 0x2a
    jl copy
done:
"""

def backlog_patch():
    import keystone
    head, tail = bytes.fromhex(BACKLOG_HEAD), bytes.fromhex(BACKLOG_TAIL)
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    code, _ = ks.asm(BACKLOG_ASM, BACKLOG_VA + len(head))
    body = head + bytes(code) + tail
    assert len(body) <= BACKLOG_SIZE, len(body)
    return BACKLOG_VA, BACKLOG_HEAD, body + b'\xCC' * (BACKLOG_SIZE - len(body))

# Message window: one text object per character in slots [line][40] with no bounds check.
# The per-character wrap test (call 0x1406DEAA0 at 0x1406DE504: x + advance > 680) goes
# through a stub that also wraps when the line already holds 40 characters
# (rbx = window, [rbx+0x90] = column). tl.py wraps English to 40 characters a line; this
# only guards against inserted names/numbers longer than estimated.
WRAP_CALL_VA, WRAP_CHECK_VA = 0x1406DE504, 0x1406DEAA0
WRAP40_VA = BACKLOG_VA + BACKLOG_SIZE
WRAP40_ASM = """
    cmp dword ptr [rbx + 0x90], 40
    jl {check:#x}
    mov al, 1
    ret
"""

def call_bytes(at, to):
    return b'\xE8' + (to - at - 5).to_bytes(4, 'little', signed=True)

def wrap40_patches():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    code, _ = ks.asm(WRAP40_ASM.format(check=WRAP_CHECK_VA), WRAP40_VA)
    assert len(code) <= 0x20, len(code)
    return [(WRAP40_VA, 'CC' * len(code), bytes(code)),
            (WRAP_CALL_VA, call_bytes(WRAP_CALL_VA, WRAP_CHECK_VA).hex(),
             call_bytes(WRAP_CALL_VA, WRAP40_VA))]

# Text objects (layout loop 0x1406948EC) add the object's letter spacing [obj+0x30] after
# every glyph (x += advance + spacing). The English advances already include the gap, so
# the spacing is skipped for single-byte codes < 0x80 (rsi = the current character).
SPACING_VA = ADVANCE_VA + ADVANCE_SIZE
SPACING_AT, SPACING_BACK = 0x140694A2B, 0x140694A36
SPACING_OLD = '0f b7 43 30 66 03 c5 66 01 43 28'
SPACING_ASM = """
    movzx eax, byte ptr [rsi]
    cmp al, 0x80
    mov eax, 0
    jb add
    movzx eax, word ptr [rbx + 0x30]
add:
    add ax, bp
    add word ptr [rbx + 0x28], ax
    jmp {back:#x}
"""

def spacing_code():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    return bytes(ks.asm(SPACING_ASM.format(back=SPACING_BACK), SPACING_VA)[0])

def spacing_patches():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    jmp, _ = ks.asm('jmp %#x' % SPACING_VA, SPACING_AT)
    n = len(bytes.fromhex(SPACING_OLD))
    return [(SPACING_AT, SPACING_OLD, bytes(jmp) + b'\x90' * (n - len(jmp)))]

# Town readings: the English town name runs on into the reading field (tables.py), so
# the three Japanese-mode accessors of the reading return "" instead (as in the PS2
# port). EMPTY is a zero byte in .rdata (a float constant 0x437F0000, low byte 0).
# 0x140361120 reading of a town object, 0x1403611A0 reading by index, 0x140361A10
# reading + kind suffix (sprintf). Chinese modes are unchanged.
EMPTY_VA = 0x140C717C4
TOWN_READING = [
    (0x140361163, 'e8 04 ae cc ff 84 c0 48 8d 0d 5b 3b 7f 00', """
        call 0x14002bf6c
        test al, al
        je jp_
        lea rax, [0x140b54ccc]
        add rax, rbx
        jmp done_
    jp_: lea rax, [{empty:#x}]
    done_: add rsp, 0x20
        pop rbx
        ret"""),
    (0x1403611FD, '48 8d 80 ac 12 b5 00 48 03 c3', """
        lea rax, [{empty:#x}]
        nop
        nop
        nop"""),
    (0x140361CC2, '83 f8 05 0f 87 c0 00 00 00', """
        lea rax, [{empty:#x}]
        mov rsi, qword ptr [rsp + 0x38]
        add rsp, 0x20
        pop rdi
        ret"""),
]

# Scenario choice button "%4d%s %s" (0x140C12A50: year, ui 1706 年, title): the 年 buffer
# is shared with the name entry ("Year"), so these two sites get "" instead ("1560 The Sun").
SCENARIO_YEAR = [(0x1403F1694, '48 8b 0d a5 b0 ca 00', '48 8d 0d'),   # mov rcx -> lea rcx
                 (0x1403F1A7D, '4c 8b 0d bc ac ca 00', '4c 8d 0d')]   # mov r9 -> lea r9

def scenario_year_patches():
    return [(va, old, bytes.fromhex(op) + struct.pack('<i', EMPTY_VA - (va + 7)))
            for va, old, op in SCENARIO_YEAR]

def town_reading_patches():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    out = []
    for va, old, src in TOWN_READING:
        b = bytes(ks.asm(src.format(empty=EMPTY_VA), va)[0])
        out.append((va, old, b))
    return out

# Numbers: the custom printf (0x1406920CD) prints %w (and %y below 10, and the parts of
# %k) through 0x140693C00 (buf, value, width, flags: bit 0 = pad with zeros), which
# writes full-width Shift-JIS digits ("４ left"). Rewritten in place (0x101 bytes) to
# write ASCII: padding (space or '0') up to width, '-', digits; returns the length.
DIGITS_VA, DIGITS_SIZE = 0x140693C00, 0x101
DIGITS_HEAD = '48 89 5c 24 08 48 89 6c 24 10 48 89 74 24 18 48 89 7c 24 20'
DIGITS_ASM = """
    push rbx
    push rdi
    sub rsp, 0x28
    xor ebx, ebx
    mov eax, edx
    xor r11d, r11d
    test eax, eax
    jns d_pos
    mov r11d, 1
    neg eax
d_pos:
    lea rdi, [rsp + 0x20]
    xor r10d, r10d
d_div:
    xor edx, edx
    push rcx
    mov ecx, 10
    div ecx
    pop rcx
    add dl, 0x30
    dec rdi
    mov byte ptr [rdi], dl
    inc r10d
    test eax, eax
    jnz d_div
    mov eax, r8d
    sub eax, r10d
    sub eax, r11d
    jle d_sign
    mov dl, 0x20
    test r9d, 1
    jz d_pad
    mov dl, 0x30
d_pad:
    mov byte ptr [rcx + rbx], dl
    inc ebx
    dec eax
    jnz d_pad
d_sign:
    test r11d, r11d
    jz d_copy
    mov byte ptr [rcx + rbx], 0x2d
    inc ebx
d_copy:
    mov dl, byte ptr [rdi]
    mov byte ptr [rcx + rbx], dl
    inc rdi
    inc ebx
    dec r10d
    jnz d_copy
    mov byte ptr [rcx + rbx], 0
    mov eax, ebx
    add rsp, 0x28
    pop rdi
    pop rbx
    ret
"""

def digits_patch():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    b = bytes(ks.asm(DIGITS_ASM, DIGITS_VA)[0])
    assert len(b) <= DIGITS_SIZE, len(b)
    return (DIGITS_VA, DIGITS_HEAD, b + b'\xcc' * (DIGITS_SIZE - len(b)))

# Money in messages: the emit-callback printf's money printer (0x1406EDFF0: emit rdi,
# value, width, r9b = full-width digits) prints each part (kan, then mon if a rest is
# left) as digits + one SJIS unit character from a per-language table (0x14108E4D8 =
# 貫 文). The unit emission (0x1406EE133-0x1406EE19C) is replaced by " kan" / " mon"
# (+ a space after "kan" when a mon part follows), and digits are always half-width.
MONEY_WIDE = (0x1406EE016, '45 0f b6 e9', '45 31 ed 90')     # movzx r13d, r9b -> xor r13d, r13d
# Integers in messages ({02} number fields, e.g. "Buy at least ３ cannons"): the emit-callback
# printf 0x1406EDCC0 -> number printer 0x1406ECE60 (dl = full-width, kept in r13) -> digit
# writer 0x1406ECCA0 (cl = full-width, recursive). Only the printer's flag is forced to 0:
# forcing the writer's own flag (0x1406ECCBA movzx ebp, cl -> xor) breaks the "Until
# council" panel ("1 days" -> "1": its layout counts on a 2-byte digit).
NUM_WIDE = [(0x1406ECE81, '44 0f b6 ea', '45 31 ed 90')]     # movzx r13d, dl -> xor r13d, r13d
MONEY_VA, MONEY_END = 0x1406EE133, 0x1406EE19C
MONEY_HEAD = '83 c5 02 e8 31 de 93 ff'
MONEY_ASM = """
    add ebp, 4
    mov ecx, 0x20
    call rdi
    test r15, r15
    jnz m_mon
    mov ecx, 0x6b
    call rdi
    mov ecx, 0x61
    call rdi
    mov ecx, 0x6e
    call rdi
    test r14, r14
    jz m_end
    mov ecx, 0x20
    call rdi
    inc ebp
    jmp m_end
m_mon:
    mov ecx, 0x6d
    call rdi
    mov ecx, 0x6f
    call rdi
    mov ecx, 0x6e
    call rdi
m_end:
"""

def money_patches():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    b = bytes(ks.asm(MONEY_ASM, MONEY_VA)[0])
    n = MONEY_END - MONEY_VA
    assert len(b) <= n, len(b)
    return [MONEY_WIDE, (MONEY_VA, MONEY_HEAD, b + b'\x90' * (n - len(b)))] + NUM_WIDE

def va2off(pe, va):
    return pe.get_offset_from_rva(va - IMAGE_BASE)

def apply(data):
    import pefile
    pe = pefile.PE(data=bytes(data), fast_load=True)
    out = bytearray(data)
    for va, old, new in PATCHES + [advance_patch(), backlog_patch(), digits_patch(), save_header_patch()] + wrap40_patches() + spacing_patches() + town_reading_patches() + money_patches() + scenario_year_patches():
        o = va2off(pe, va)
        old = bytes.fromhex(old)
        new = bytes.fromhex(new) if isinstance(new, str) else new
        if out[o:o + len(old)] != old:
            raise SystemExit('patch %X: expected %s, found %s'
                             % (va, old.hex(), out[o:o + len(old)].hex()))
        out[o:o + len(new)] = new
    return bytes(out)

if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    open(dst, 'wb').write(apply(open(src, 'rb').read()))
    print('wrote', dst)
