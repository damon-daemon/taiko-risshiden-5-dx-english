"""A new PE section for English data (strings the exe points at).

    seg = pesect.Segment(exe_bytes)
    va = seg.add(b'English\\0')        # virtual address of the bytes
    exe = seg.finish()                  # exe with the section appended

The section (.tl, read-only initialised data + hook code) gets the next section-aligned RVA after
the last section and is written at the end of the file (after the overlay: the
Authenticode blob that the stale security directory no longer points at; the
directory is cleared). Pointers into it that replace existing pointers keep their
base relocations, so ASLR still works; new absolute pointers would need relocations
(not supported: point only through existing slots or rip-relative code).
"""
import struct

IMAGE_BASE = 0x140000000
NAME = b'.tl\0\0\0\0\0'
CHARS = 0x60000060        # code + initialised data, readable + executable (names.py hooks)

def _align(x, a):
    return (x + a - 1) // a * a

class Segment:
    def __init__(self, exe):
        import pefile
        self.exe = bytearray(exe)
        pe = pefile.PE(data=bytes(exe), fast_load=True)
        self.pe = pe
        last = max(pe.sections, key=lambda s: s.VirtualAddress)
        self.salign = pe.OPTIONAL_HEADER.SectionAlignment
        self.falign = pe.OPTIONAL_HEADER.FileAlignment
        self.rva = _align(last.VirtualAddress + last.Misc_VirtualSize, self.salign)
        self.base = IMAGE_BASE + self.rva
        self.data = bytearray()
        self.index = {}

    def add(self, b, align=1, share=True):
        """Append bytes, return their VA (identical byte strings are stored once)."""
        b = bytes(b)
        if share and b in self.index:
            return self.index[b]
        while len(self.data) % align:
            self.data.append(0)
        va = self.base + len(self.data)
        self.data += b
        if share:
            self.index[b] = va
        return va

    def va2off(self, va):
        return self.pe.get_offset_from_rva(va - IMAGE_BASE)

    def put_q(self, va, value):
        struct.pack_into('<Q', self.exe, self.va2off(va), value)

    def get_q(self, va):
        return struct.unpack_from('<Q', self.exe, self.va2off(va))[0]

    def finish(self):
        if not self.data:
            return bytes(self.exe)
        pe, out = self.pe, self.exe
        fh = pe.FILE_HEADER
        n = fh.NumberOfSections
        hdr = pe.sections[-1].get_file_offset() + 40
        assert hdr + 40 <= pe.sections[0].PointerToRawData and \
            not any(out[hdr:hdr + 40]), 'no room for a section header'
        raw = _align(len(out), self.falign)
        out += b'\0' * (raw - len(out))
        size = _align(len(self.data), self.falign)
        out += self.data + b'\0' * (size - len(self.data))
        struct.pack_into('<8sIIIIIIHHI', out, hdr, NAME, len(self.data), self.rva, size, raw,
                         0, 0, 0, 0, CHARS)
        struct.pack_into('<H', out, fh.get_file_offset() + 2, n + 1)
        oh = pe.OPTIONAL_HEADER.get_file_offset()
        # PE32+ optional header: SizeOfImage at +56, CheckSum +64, data dirs at +112
        struct.pack_into('<I', out, oh + 56, _align(self.rva + len(self.data), self.salign))
        struct.pack_into('<I', out, oh + 64, 0)
        struct.pack_into('<II', out, oh + 112 + 8 * 4, 0, 0)     # security directory
        return bytes(out)
