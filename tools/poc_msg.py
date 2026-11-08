"""Proof of concept: put a few English test strings into TAI5MSG_JP.DAT.

usage: poc_msg.py CLEAN_DAT OUT_DAT

Replaces strings of msg21 shown on the way into a new game (settings screen + the
"starting the game" line) with ASCII test text, to see how the unmodified engine draws
Latin letters.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
import msgfile, text

TESTS = {
    (21, 32): 'Then let the game begin! ABCDEFGHIJKLM\nnopqrstuvwxyz 0123456789 .,!?\'"-:;()',
    (21, 35): 'Adjust the brightness of your TV. WWWW iiii',
    (21, 36): 'Use {1B}H5 to move the screen. Mixed: ｱｲｳ 漢字 ok',
}

def main():
    src, dst = sys.argv[1:3]
    blocks = msgfile.blocks(open(src, 'rb').read())
    assert msgfile.pack(blocks) == open(src, 'rb').read(), 'identity repack failed'
    for (m, k), s in TESTS.items():
        blocks[m][k] = text.encode(s) + b'\x05\x05\x05'
    open(dst, 'wb').write(msgfile.pack(blocks))
    print('wrote', dst)

if __name__ == '__main__':
    main()
