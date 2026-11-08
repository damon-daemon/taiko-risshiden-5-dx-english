"""Run the names.py hooks of build/out/Taiko5DX.exe in unicorn on sample records.

  test_names.py [EXE]
"""
import os, struct, sys
import pefile, unicorn
from unicorn import x86_const as X

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import names, setup

EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(setup.ROOT, 'build', 'out', 'Taiko5DX.exe')

def load():
    pe = pefile.PE(EXE)
    mu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = (pe.OPTIONAL_HEADER.SizeOfImage + 0xFFFF) & ~0xFFFF
    mu.mem_map(base, size)
    for s in pe.sections:
        d = s.get_data()
        mu.mem_write(base + s.VirtualAddress, d[:max(s.Misc_VirtualSize, len(d))])
    tl = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.tl'][0]
    mu.mem_map(0x10000000, 0x100000)     # stack + scratch
    return mu, base + tl.VirtualAddress, pe

def record(f, g):
    b = lambda s: s.encode('cp932')[:9].ljust(9, b'\0')
    return b(f) + b(g) + b'\0' * 6

def run(mu, start, until, regs):
    mu.reg_write(X.UC_X86_REG_RSP, 0x10080000)
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.emu_start(start, until, count=100000)

def cstr(mu, a):
    out = b''
    while True:
        c = bytes(mu.mem_read(a, 1))
        if c == b'\0':
            return out.decode('cp932')
        out += c
        a += 1

def main():
    mu, code, pe = load()
    # entry slots: 0 = full-name tail, 1+i = names.SITES[i]
    mu.mem_write(0x10000000, struct.pack('<QQQ', 0, 0x10001000, 0))   # person obj: +8 = record
    buf = 0x10002000
    cases = [('木下', '藤吉郎'), ('羽柴', '秀吉'), ('', 'マリア'), ('弥', '助'), ('ハイレ', 'ディン'),
             ('木下', 'ほげ'), ('ほげ', 'ふが'), ('一柳', '直末')]
    for f, g in cases:
        mu.mem_write(0x10001000, record(f, g))
        mu.mem_write(buf, b'\xAA' * 64)
        run(mu, code, names.FULL_NAME_RET, {X.UC_X86_REG_RAX: buf, X.UC_X86_REG_RDI: 0x10000000})
        full = cstr(mu, mu.reg_read(X.UC_X86_REG_RBX))
        # msg 'e' (slot 1): rbx = person -> rax ; msg 'f' (slot 3): -> rdx
        run(mu, code + 64, names.SITES[0][3], {X.UC_X86_REG_RBX: 0x10000000})
        fam = cstr(mu, mu.reg_read(X.UC_X86_REG_RAX))
        run(mu, code + 64 * 3, names.SITES[2][3], {X.UC_X86_REG_RBX: 0x10000000})
        giv = cstr(mu, mu.reg_read(X.UC_X86_REG_RDX))
        # event given (slot 5): rax = person, rsi kept -> rcx = rsi, rdx = given
        run(mu, code + 64 * 5, names.SITES[4][3], {X.UC_X86_REG_RAX: 0x10000000, X.UC_X86_REG_RSI: 0x1234})
        assert mu.reg_read(X.UC_X86_REG_RCX) == 0x1234
        egiv = cstr(mu, mu.reg_read(X.UC_X86_REG_RDX))
        print('%s %s -> full %r, e %r, f %r, event f %r' % (f, g, full, fam, giv, egiv))
    # null record
    mu.mem_write(0x10000000, struct.pack('<QQQ', 0, 0, 0))
    run(mu, code, names.FULL_NAME_NULL, {X.UC_X86_REG_RAX: buf, X.UC_X86_REG_RDI: 0x10000000})
    print('null record ok, rax == buffer:', mu.reg_read(X.UC_X86_REG_RAX) == buf)

if __name__ == '__main__':
    main()
