"""Live recorder for type-7 (player data) requests: which sender id do they carry?
python diag/twin/rec7.py ABC install | show
The LAN stub at main+0x1CD9D88 (x1 -> u64 sender id) is redirected to a cave at main+0x563E900 that keeps the last
8 sender ids in a ring at main+0x492AFA0 (the live tracer's map area: do not run msgtrace at the same time),
then does what the stub did (drop id -1, else b 0x14dc040)."""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
CAVE, BOX, STUB = 0x563E900, 0x492AFA0, 0x1CD9D88
def b(pc, t): return 0x14000000 | (((t - pc) // 4) & 0x3FFFFFF)
def adrp_add(pc, rd, t):
    pages = (t >> 12) - (pc >> 12)
    return [0x90000000 | ((pages & 3) << 29) | (((pages >> 2) & 0x7FFFF) << 5) | rd, 0x91000000 | ((t & 0xFFF) << 10) | (rd << 5) | rd]
words = adrp_add(CAVE, 9, BOX) + [
    0xF9400028,            # ldr x8, [x1]
    0xB9400D2A,            # ldr w10, [x9, #0xc]      count (ring index)
    0x1100054B,            # add w11, w10, #1
    0xB9000D2B,            # str w11, [x9, #0xc]
    0x1200014A,            # and w10, w10, #1         2 slots of 8 bytes at +0x10
    0x8B0A0D2B,            # add x11, x9, x10, lsl #3
    0xF9000968,            # str x8, [x11, #0x10]
    0xB100051F,            # cmn x8, #1
]
pc = CAVE + 4 * len(words)
words += [0x54000040, b(pc + 4, 0x14DC040), 0xD65F03C0]   # b.eq +8 ; b 0x14dc040 ; ret
op = sys.argv[2]
for w in sys.argv[1]:
    m = Mem(w)
    if op == 'install':
        m.write(m.base + BOX, bytes(32))
        m.write(m.base + CAVE, b''.join(struct.pack('<I', x) for x in words), code=True)
        m.write(m.base + STUB, struct.pack('<I', b(STUB, CAVE)), code=True)
        print(w, 'recorder installed')
    else:
        d = m.read(m.base + BOX, 32)
        print(w, 'requests seen', struct.unpack_from('<I', d, 0xc)[0], 'last ids', ['%x' % x for x in struct.unpack_from('<2Q', d, 0x10)])
