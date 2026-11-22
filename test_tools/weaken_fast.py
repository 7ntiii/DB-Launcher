"""TEST ONLY: write an enemy's HP (chr HP and the low 19 bits of its NetChrSync status word) down to HP every
30 ms for SECONDS on WHO (run it on the game that owns the enemy), so the next real hit kills it.
python diag/twin/weaken_fast.py WHO CHR_HEX [HP=40] [SECONDS=90]"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

who, chr_ = sys.argv[1], int(sys.argv[2], 16)
hp = int(sys.argv[3]) if len(sys.argv) > 3 else 40
secs = float(sys.argv[4]) if len(sys.argv) > 4 else 90
m = Mem(who)
d = m.u64(m.u64(chr_ + 0x2470) + 0x18)


def status_addr():
    wcm = m.u64(m.base + 0x5B3CD88)
    sm = m.u64(wcm + 0x540)
    for i in range(min(m.u32(sm + 8), 16)):
        s = m.u64(sm + 0x10 + 8 * i)
        if not s:
            continue
        cs, cnt = m.u64(s + 8), m.u32(s + 0x10)
        first = m.u64(cs + 8) if cs else 0
        if not first or not cnt or cnt > 8192:
            continue
        for j0 in range(0, cnt, 64):
            k = min(64, cnt - j0)
            raw = m.read(first + 0x38 * j0, 0x38 * k)
            if not raw:
                continue
            for j in range(k):
                if struct.unpack_from('<Q', raw, 0x38 * j)[0] == chr_:
                    return m.u64(s + 0x30) + 4 * (j0 + j), m.u64(first + 0x38 * (j0 + j) + 0x18)
    return 0, 0


sa, mod = status_addr()
print(who, 'hp', m.u32(d + 0x290), 'status word at %x' % sa, 'module %x master hp %s' % (mod, m.u32(mod + 0xF30) if mod else None), flush=True)
t0 = time.time()
n = 0
while time.time() - t0 < secs:
    cur = struct.unpack('<i', m.read(d + 0x290, 4))[0]
    if cur <= 0:
        print(who, 'enemy hp', cur, 'after', n, 'writes: dead')
        break
    if cur > hp:
        m.write(d + 0x290, struct.pack('<i', hp))
        if mod and 0 < struct.unpack('<i', m.read(mod + 0xF30, 4))[0] != hp:
            m.write(mod + 0xF30, struct.pack('<i', hp))
        if sa:
            wv = m.u32(sa)
            m.write(sa, struct.pack('<I', (wv & ~0x7FFFF) | hp))
        n += 1
    time.sleep(0.03)
else:
    print(who, 'time-out, hp', m.u32(d + 0x290), 'writes', n)
