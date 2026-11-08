"""The English program patch as a loader: tl_patch.bin + dinput8.dll (tools/loader/loader.c).

The game's Taiko5DX.exe is never shipped or changed on disk. build.py makes the patched
program as before (exepatch, pesect .tl section, ...) only as an intermediate, and this
module turns the difference into tl_patch.bin:
  - every changed byte range of the existing sections, as RVA + new bytes + the CRC32 of
    the original bytes (so no game code is shipped) + the positions of the qwords the
    base relocation adjusts there (the loader adds the ASLR delta to those),
  - the .tl section (our code and English), mapped by the DLL at its RVA, or nearby when
    something else already sits there (Wine may map a DLL right after the image),
  - every reference to .tl (rel32 / RVA / absolute qword), found by building the patched
    program twice with .tl SHIFT bytes apart, adjusted by the loader when .tl moves,
  - the import slots the DLL hooks to apply the patch once the code is decrypted.
See loader.c for the format and the run-time side.

usage (normally via build.py):
    .venv/bin/python tools/loader.py dll OUT.dll      # compile the DLL only
"""
import os, struct, subprocess, sys, tempfile, zlib

sys.path.insert(0, os.path.dirname(__file__))
import setup

SRC = os.path.join(os.path.dirname(__file__), 'loader', 'loader.c')
DLL_NAME = 'dinput8.dll'
BLOB_NAME = 'tl_patch.bin'
HOOKS = [(b'KERNEL32.dll', b'GetSystemTimeAsFileTime'), (b'KERNEL32.dll', b'QueryPerformanceCounter')]
MERGE_GAP = 16
SHIFT = 0x10000                 # .tl offset of the second build (build.py)

def _pe(data):
    import pefile
    return pefile.PE(data=data)

def relocs(pe):
    out = set()
    for blk in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
        for e in blk.entries:
            if e.type == 10:            # IMAGE_REL_BASED_DIR64
                out.add(e.rva)
    return out

def hook_slots(pe):
    want = {(d.upper(), n) for d, n in HOOKS}
    slots = {}
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        for i in e.imports:
            if (e.dll.upper(), i.name) in want:
                slots[i.name] = i.address - pe.OPTIONAL_HEADER.ImageBase
    return [slots[n] for _, n in HOOKS]

def changed_ranges(clean, patched, pe):
    """[(rva, length)] of the bytes that differ inside the clean exe's sections."""
    out = []
    for s in pe.sections:
        off, size, va = s.PointerToRawData, s.SizeOfRawData, s.VirtualAddress
        a, b = clean[off:off + size], patched[off:off + size]
        i, n = 0, len(a)
        while i < n:
            if a[i] == b[i]:
                i += 1
                continue
            j = i + 1
            last = i
            while j < n and j - last <= MERGE_GAP:
                if a[j] != b[j]:
                    last = j
                j += 1
            out.append((va + i, last + 1 - i))
            i = last + 1
    return out

def fixups(pe, pp, patched, shifted, rel):
    """References to .tl: [rva | kind << 30], kind 0 = int32 + d (rel32 from the image
    into .tl, or an RVA), 1 = int32 - d (rel32 from .tl into the image), 2 = qword + d
    (a relocated pointer), where d = how far the loader moved .tl. Positions inside .tl
    are given as tl_rva + offset."""
    tl = pp.sections[-1]
    sp = _pe(shifted)
    t2 = sp.sections[-1]
    assert t2.VirtualAddress == tl.VirtualAddress + SHIFT and \
           t2.Misc_VirtualSize == tl.Misc_VirtualSize, '.tl differs in the shifted build'
    areas = [(s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData) for s in pp.sections[:-1]]
    areas.append((tl.VirtualAddress, tl.PointerToRawData, tl.Misc_VirtualSize))
    out = []
    for i, (va, off, size) in enumerate(areas):
        off2 = t2.PointerToRawData if i == len(areas) - 1 else off
        a, b = patched[off:off + size], shifted[off2:off2 + size]
        k = 0
        while k < size:
            if a[k] == b[k]:
                k += 1
                continue
            q = next((j for j in range(k - 7, k + 1) if va + j in rel), None)
            if q is not None and int.from_bytes(b[q:q + 8], 'little') - \
                    int.from_bytes(a[q:q + 8], 'little') == SHIFT:
                out.append(va + q | 2 << 30)
                k = q + 8
                continue
            j = k - 2                       # +-SHIFT changes byte 2 (and maybe 3) of a dword
            dv = int.from_bytes(b[j:j + 4], 'little', signed=True) - \
                 int.from_bytes(a[j:j + 4], 'little', signed=True)
            assert dv in (SHIFT, -SHIFT), 'odd .tl reference at rva %#x' % (va + k)
            assert a[j:j + 2] == b[j:j + 2]
            out.append(va + j | (0 if dv > 0 else 1) << 30)
            k = j + 4
    return out

def blob(clean, patched, shifted):
    """tl_patch.bin bytes from the clean and the patched exe."""
    pe = _pe(clean)
    pp = _pe(patched)
    assert len(pp.sections) == len(pe.sections) + 1, 'expected one added section (.tl)'
    for s, t in zip(pe.sections, pp.sections):
        assert (s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData) == \
               (t.VirtualAddress, t.PointerToRawData, t.SizeOfRawData), 'section layout changed'
    tl = pp.sections[-1]
    tl_bytes = patched[tl.PointerToRawData:tl.PointerToRawData + tl.Misc_VirtualSize]
    rel = relocs(pe)
    assert relocs(pp) == rel, 'base relocations changed'
    rva2off = lambda rva: pe.get_offset_from_rva(rva)
    # grow ranges over every relocated qword they touch, then merge overlaps
    rng = []
    for rva, n in changed_ranges(clean, patched, pe):
        a, z = rva, rva + n
        for k in range(a - 7, z):
            if k in rel:
                a, z = min(a, k), max(z, k + 8)
        if rng and a <= rng[-1][1]:
            rng[-1][1] = max(rng[-1][1], z)
        else:
            rng.append([a, z])
    fix = fixups(pe, pp, patched, shifted, rel)
    out = bytearray(b'TLP2')
    out += struct.pack('<I', 0)                       # image size check: off (Steam differs)
    slots = hook_slots(pe)
    out += struct.pack('<I', len(slots)) + b''.join(struct.pack('<I', s) for s in slots)
    out += struct.pack('<III', tl.VirtualAddress, len(tl_bytes), len(rng))
    for a, z in rng:
        o = rva2off(a)
        old, new = clean[o:o + z - a], patched[o:o + z - a]
        rs = [k - a for k in range(a, z) if k in rel]
        out += struct.pack('<IIII', a, z - a, zlib.crc32(old), len(rs))
        out += b''.join(struct.pack('<I', r) for r in rs)
        out += new + b'\0' * (-len(new) % 4)
    out += tl_bytes + b'\0' * (-len(tl_bytes) % 4)
    out += struct.pack('<I', len(fix)) + b''.join(struct.pack('<I', f) for f in fix)
    return bytes(out), len(rng), len(fix)

# ---------------------------------------------------------------- the DLL

KERNEL32 = ['GetModuleHandleW', 'GetModuleFileNameW', 'GetSystemDirectoryW', 'LoadLibraryW',
            'GetProcAddress', 'CreateFileW', 'ReadFile', 'WriteFile', 'SetFilePointer',
            'GetFileSize', 'CloseHandle', 'VirtualAlloc', 'VirtualFree', 'VirtualProtect',
            'FlushInstructionCache', 'GetCurrentProcess', 'GetSystemTimeAsFileTime',
            'QueryPerformanceCounter', 'GetProcessHeap', 'HeapAlloc']

def build_dll(out):
    with tempfile.TemporaryDirectory() as t:
        obj = os.path.join(t, 'loader.obj')
        defn = os.path.join(t, 'kernel32.def')
        lib = os.path.join(t, 'kernel32.lib')
        open(defn, 'w').write('LIBRARY KERNEL32.dll\nEXPORTS\n' + ''.join('  %s\n' % f for f in KERNEL32))
        subprocess.run(['llvm-dlltool', '-m', 'i386:x86-64', '-d', defn, '-l', lib], check=True)
        subprocess.run(['clang', '--target=x86_64-pc-windows-msvc', '-O2', '-ffreestanding',
                        '-fno-builtin', '-nostdlib', '-mno-stack-arg-probe', '-fno-stack-protector',
                        '-Wall', '-Wno-incompatible-pointer-types', '-Wno-pointer-sign',
                        *(['-DTEST_DEFER'] if os.environ.get('TL_TEST_DEFER') else []),
                        *(['-DTEST_MOVE=' + os.environ['TL_TEST_MOVE']] if os.environ.get('TL_TEST_MOVE') else []),
                        '-c', SRC, '-o', obj], check=True)
        subprocess.run(['lld-link', '/dll', '/entry:DllMain', '/nodefaultlib', '/subsystem:windows',
                        '/machine:x64', '/Brepro', '/out:' + out, obj, lib], check=True)
    lib_left = os.path.splitext(out)[0] + '.lib'
    for ext in ('.lib', '.exp'):
        p = os.path.splitext(out)[0] + ext
        if os.path.exists(p):
            os.remove(p)
    return open(out, 'rb').read()

def files(clean_exe, patched_exe, shifted_exe):
    """{relative path: bytes} for the game folder: tl_patch.bin and dinput8.dll
    (+ 'n_fix': the number of .tl references)."""
    b, n, nf = blob(clean_exe, patched_exe, shifted_exe)
    with tempfile.TemporaryDirectory() as t:
        dll = build_dll(os.path.join(t, DLL_NAME))
    return {BLOB_NAME: b, DLL_NAME: dll, 'n_fix': nf}, n

if __name__ == '__main__':
    if sys.argv[1] == 'dll':
        build_dll(sys.argv[2])
        print('wrote', sys.argv[2])
