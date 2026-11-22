"""Fast poll of the phase step of one game: python diag/twin/fastphase.py A SECONDS
Prints every change of par+0x50 (step), par+0xB8 (round), par+0xC0 (rule byte) and the buddy manager count,
polling as fast as the debug server answers (to catch short steps such as 27 / 28)."""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

who, secs = sys.argv[1], float(sys.argv[2])
m = Mem(who)
last, t0, n = None, time.time(), 0
while time.time() - t0 < secs:
    try:
        par = m.u64(m.base + 0x5B3CDF8)
        if not par:
            time.sleep(0.2)
            continue
        wcm = m.u64(m.base + 0x5B3CD88)
        h = m.u64(wcm + 0x5B8) if wcm else 0
        bm = m.u64(h + 0x10) if h else 0
        cur = (m.u32(par + 0x50), m.u32(par + 0xB8), m.read(par + 0xC0, 1)[0], m.u32(bm + 0x20) if bm else -1)
    except Exception as e:
        cur = ('err', str(e)[:40])
    n += 1
    if cur != last:
        print(time.strftime('%H:%M:%S'), '%.2f' % (time.time() - t0), 'step %s round %s c0 %s buddies %s' % cur
              if len(cur) == 4 else cur, flush=True)
        last = cur
print('polls', n)
