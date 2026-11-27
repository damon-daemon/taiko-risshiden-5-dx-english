"""Run the set-text entry of a patched Taiko5DX.exe in unicorn on sample texts: the
names.py hook, then the uihooks COUNT hook ("1 guns" -> "1 gun").

  test_counts.py [EXE]          (default: build/Taiko5DX_patched.exe)

Each text is run from 0x140694510 to 0x14069451E (where the game's own code goes on)
and checked: the text the routine goes on with, the registers it was given, its pushes,
that rsp is aligned for the calls in the hook, and that the original text is untouched
(it lies in read-only memory).
"""
import os, struct, sys
import unicorn
from unicorn import x86_const as X

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import names, setup

EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(setup.ROOT, 'build', 'Taiko5DX_patched.exe')
ENTRY, CONT = 0x140694510, 0x14069451E
OBJ, TEXT, STACK_TOP = 0x10010000, 0x20000000, 0x10080000

CASES = [
    (b'     1men', b'     1man'),                  # "%6u%s" + ui 56 "men"
    (b'  1500men', None),
    (b'Bought 1 horses', b'Bought 1 horse'),        # ui 1414 "Bought %y horses"
    (b'Bought 11 horses', None),
    (b'Bought 21 horses', None),
    (b'Capturing (1 castles left)', b'Capturing (1 castle left)'),
    (b'( 1 types)', b'( 1 type)'),
    (b'1 troops can be replenished.\nProceed?', b'1 troop can be replenished.\nProceed?'),
    (b' 1/ 1 shots', b' 1/ 1 shot'),
    (b' 1/10 shots', None),
    (b'1 people', b'1 person'),
    (b'1 guns, 1 ships and 1 days.', b'1 gun, 1 ship and 1 day.'),
    (b'0.1 days', None),
    (b'1,000 men', None),
    (b'1 mentors', None),
    (b'1 daysx', None),
    (b'Days left: 1', None),
    (b'1', None),
    (b'', None),
    (b'x' * 300 + b' 1 guns', None),                # longer than a ring slot: left as it is
    (b'x' * 240 + b' 1 guns', b'x' * 240 + b' 1 gun'),
    ('兵1人'.encode('cp932'), None),
    ('鉄砲'.encode('cp932') + b' 1 guns', '鉄砲'.encode('cp932') + b' 1 gun'),   # names.py path first
]

SENT = {X.UC_X86_REG_RBX: 0xB0B0, X.UC_X86_REG_RBP: 0xB1B1, X.UC_X86_REG_R12: 0xC0C0,
        X.UC_X86_REG_R15: 0xF0F0, X.UC_X86_REG_RSI: 0x5151, X.UC_X86_REG_RDI: 0xD1D1,
        X.UC_X86_REG_R10: 0xA0A0, X.UC_X86_REG_R11: 0xA1A1, X.UC_X86_REG_R9: 0x1,
        X.UC_X86_REG_RDX: 0x123, X.UC_X86_REG_RCX: OBJ}

def cbytes(mu, a):
    out = b''
    while True:
        c = bytes(mu.mem_read(a, 1))
        if c == b'\0':
            return out
        out += c
        a += 1

def main():
    mu, tl, pe = _load(EXE)
    mu.mem_map(TEXT, 0x1000, unicorn.UC_PROT_READ)
    calls = []
    def on_call(uc, addr, size, data):
        calls.append(uc.reg_read(X.UC_X86_REG_RSP) % 16)
    mu.hook_add(unicorn.UC_HOOK_CODE, on_call, begin=names.RING_ALLOC, end=names.RING_ALLOC)
    bad = 0
    for text, want in CASES:
        want = text if want is None else want
        mu.mem_protect(TEXT, 0x1000, unicorn.UC_PROT_ALL)
        mu.mem_write(TEXT, text + b'\0')
        mu.mem_protect(TEXT, 0x1000, unicorn.UC_PROT_READ)
        mu.mem_write(OBJ, b'\0' * 0x40)                    # box width [obj+0x24] = 0: no fit
        rsp = STACK_TOP - 8
        mu.mem_write(rsp, struct.pack('<Q', 0xDEAD0000))
        mu.reg_write(X.UC_X86_REG_RSP, rsp)
        for r, v in SENT.items():
            mu.reg_write(r, v)
        mu.reg_write(X.UC_X86_REG_R8, TEXT)
        del calls[:]
        mu.emu_start(ENTRY, CONT, count=200000)
        got_p = mu.reg_read(X.UC_X86_REG_R8)
        got = cbytes(mu, got_p)
        sp = mu.reg_read(X.UC_X86_REG_RSP)
        pushed = struct.unpack('<4Q', bytes(mu.mem_read(sp + 0x38, 32)))
        ok = (got == want and sp == rsp - 32 - 0x38 and pushed == (0xF0F0, 0xC0C0, 0xB1B1, 0xB0B0)
              and mu.reg_read(X.UC_X86_REG_RBP) == OBJ and cbytes(mu, TEXT) == text
              and all(mu.reg_read(r) == v for r, v in SENT.items() if r != X.UC_X86_REG_RBP)
              and all(c == 8 for c in calls) and (got_p == TEXT) == (got == text))
        bad += not ok
        print('%-4s %r -> %r%s' % ('ok' if ok else 'BAD', text[-40:], got[-40:],
                                   ' (copy)' if got_p != TEXT else ''))
    # no text at all
    mu.reg_write(X.UC_X86_REG_RSP, STACK_TOP - 8)
    for r, v in SENT.items():
        mu.reg_write(r, v)
    mu.reg_write(X.UC_X86_REG_R8, 0)
    mu.emu_start(ENTRY, CONT, count=200000)
    ok = mu.reg_read(X.UC_X86_REG_R8) == 0
    bad += not ok
    print('%-4s NULL text' % ('ok' if ok else 'BAD'))
    print('%d of %d failed' % (bad, len(CASES) + 1))
    return bad

def _load(path):
    sys.path.insert(0, os.path.dirname(__file__))
    import test_names
    test_names.EXE = path
    return test_names.load()

if __name__ == '__main__':
    sys.exit(1 if main() else 0)
