"""READ-ONLY. Who set (or never set) each player's state word: python diag/twin/state_src.py [GAMES] [secs]
Per player chr in the WCM chr set (pgd = [[chr+0x20]+0x1D0]) prints
  no pgd+0xD0 | slot pgd+0x104 | b46D1 pgd+0x46D1 | local pgd+0x40D0 | flag pgd+0x46A0 | state pgd+0x46B0 | pgd address
The match spawn writes slot +0x104, byte +0x46D1 and state 01 01 00 00 together (remote chr: 0xE80060 store
0xE80264; own: 0xED7180 store 0xED71D8). So on the copy that stays 00:
  slot/b46D1 also untouched -> that spawn never ran for this pgd; slot/b46D1 set but state 00 -> reset later.
With secs > 0 it repeats every 2 s and prints only changes (run from PrepareSecond to UpdatePhase)."""
import struct, sys, time
sys.path.insert(0, 'diag/twin')
from mem import Mem
games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0
mems = {w: Mem(w) for w in games}
last = {}


def snap(m):
    wcm = m.u64(m.base + 0x5B3CD88)
    arr = m.read(m.u64(wcm + 0x30), 0x38 * 8)
    out = []
    for i in range(8):
        c = struct.unpack_from('<Q', arr, 0x38 * i)[0]
        if not c:
            continue
        try:
            if m.u64(c) == m.base + 0x572B108:
                continue
            pgd = m.u64(m.u64(c + 0x20) + 0x1D0)
            if not pgd:
                out.append('chr %x no pgd' % c)
                continue
            out.append('no %d slot %d b46D1 %d local %d flag %d state %s pgd %x' % (
                m.u32(pgd + 0xD0), m.read(pgd + 0x104, 1)[0], m.read(pgd + 0x46D1, 1)[0],
                m.read(pgd + 0x40D0, 1)[0], m.read(pgd + 0x46A0, 1)[0], m.read(pgd + 0x46B0, 4).hex(), pgd))
        except Exception:
            out.append('err')
    return out


end = time.time() + secs
while True:
    for w, m in mems.items():
        try:
            s = snap(m)
        except Exception as e:
            s = ['read failed: %s' % e]
        if last.get(w) != s:
            print(time.strftime('%H:%M:%S'), w, s, flush=True)
            last[w] = s
    if time.time() >= end:
        break
    time.sleep(2)
