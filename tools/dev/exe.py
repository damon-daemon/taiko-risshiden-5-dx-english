"""Taiko5DX.exe analysis helpers (x64 PE).

  exe.py funcs                    # count .pdata functions
  exe.py str TEXT                 # find a string (ascii / utf-16 / cp932) and its code refs
  exe.py refs VA                  # code that references VA (rip-relative operands)
  exe.py dis VA [N]               # disassemble the function containing VA (or N instructions)
  exe.py imm VALUE                # instructions with this immediate (cmp/mov/sub ...)

Function boundaries come from .pdata. The rip-relative reference index is cached in
build/exe_refs.pickle.
"""
import bisect, os, pickle, struct, sys
import capstone, pefile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = os.path.join(ROOT, 'game_clean', 'Taiko5DX.exe')

pe = pefile.PE(EXE, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
DATA = open(EXE, 'rb').read()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

def sec(name):
    for s in pe.sections:
        if s.Name.rstrip(b'\0') == name:
            return s

TEXT = sec(b'.text')

def va2off(va):
    return pe.get_offset_from_rva(va - BASE)

def off2va(off):
    return pe.get_rva_from_offset(off) + BASE

def funcs():
    d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]          # exception directory
    o = pe.get_offset_from_rva(d.VirtualAddress)
    raw = DATA[o:o + d.Size]
    lo, hi = TEXT.VirtualAddress, TEXT.VirtualAddress + TEXT.Misc_VirtualSize
    out = []
    for i in range(0, len(raw) - 11, 12):
        a, b, _ = struct.unpack_from('<III', raw, i)
        if lo <= a < b <= hi:
            out.append((a + BASE, b + BASE))
    out.sort()
    return out

FUNCS = funcs()
STARTS = [a for a, _ in FUNCS]

def func_of(va):
    i = bisect.bisect_right(STARTS, va) - 1
    if i >= 0 and FUNCS[i][0] <= va < FUNCS[i][1]:
        return FUNCS[i]
    return None

def insns(a, b):
    o = va2off(a)
    return md.disasm(DATA[o:o + (b - a)], a)

def ref_index():
    cache = os.path.join(ROOT, 'build', 'exe_refs.pickle')
    if os.path.exists(cache):
        return pickle.load(open(cache, 'rb'))
    md2 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    idx = {}
    for a, b in FUNCS:
        o = va2off(a)
        for addr, size, mn, ops in md2.disasm_lite(DATA[o:o + (b - a)], a):
            if 'rip' in ops:
                k = ops.index('rip')
                rest = ops[k + 3:].split(']')[0].strip()
                if rest:
                    sign = -1 if rest[0] == '-' else 1
                    try:
                        disp = int(rest[1:].strip(), 0) * sign
                    except ValueError:
                        continue
                    idx.setdefault(addr + size + disp, []).append(addr)
    pickle.dump(idx, open(cache, 'wb'))
    return idx

def show(i):
    return '%x: %-8s %s' % (i.address, i.mnemonic, i.op_str)

def main():
    cmd = sys.argv[1]
    if cmd == 'funcs':
        print(len(FUNCS))
    elif cmd == 'str':
        t = sys.argv[2]
        idx = ref_index()
        for enc in ('ascii', 'utf-16-le', 'cp932'):
            try:
                pat = t.encode(enc)
            except UnicodeEncodeError:
                continue
            p = DATA.find(pat)
            while p >= 0:
                try:
                    va = off2va(p)
                except Exception:
                    va = None
                print(enc, hex(p), va and hex(va), [hex(r) for r in idx.get(va, [])])
                p = DATA.find(pat, p + 1)
    elif cmd == 'refs':
        va = int(sys.argv[2], 16)
        for r in ref_index().get(va, []):
            f = func_of(r)
            print(hex(r), 'in', f and hex(f[0]))
    elif cmd == 'dis':
        va = int(sys.argv[2], 16)
        if len(sys.argv) > 3:
            for k, i in enumerate(insns(va, va + 16 * int(sys.argv[3]))):
                if k >= int(sys.argv[3]):
                    break
                print(show(i))
        else:
            a, b = func_of(va)
            print('function %x-%x' % (a, b))
            for i in insns(a, b):
                print(show(i))
    elif cmd == 'calls':
        # callers of a function, directly or through its incremental-link thunk (E9 jmp)
        target = int(sys.argv[2], 16)
        names = {target}
        t = TEXT
        o0 = t.PointerToRawData
        lo = t.VirtualAddress + BASE
        d = DATA[o0:o0 + 0x40000]
        for i in range(len(d) - 5):
            if d[i] == 0xE9 and lo + i + 5 + struct.unpack_from('<i', d, i + 1)[0] == target:
                names.add(lo + i)
        want = {'0x%x' % n for n in names}
        md2 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for a, b in FUNCS:
            o = va2off(a)
            for addr, size, mn, ops in md2.disasm_lite(DATA[o:o + (b - a)], a):
                if mn in ('call', 'jmp') and ops in want:
                    print('%x in %x' % (addr, a))
    elif cmd == 'imm':
        v = int(sys.argv[2], 0)
        md2 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for a, b in FUNCS:
            o = va2off(a)
            for addr, size, mn, ops in md2.disasm_lite(DATA[o:o + (b - a)], a):
                if ops.endswith(', ' + hex(v)) and mn in ('cmp', 'sub', 'mov', 'add', 'and'):
                    print('%x %x: %s %s' % (a, addr, mn, ops))

if __name__ == '__main__':
    main()
