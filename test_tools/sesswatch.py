"""Fast log of the session / match state of one game: python diag/twin/sesswatch.py A SECONDS
Prints every change of: mgr3 state (+0x126C), mode (+0x1268), member count (+0x18), match step / round
(par+0x50 / +0xB8), watchdog armed / reason (par+0x47A8 / +0x47A9), MapSystem ready flag."""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

who, secs = sys.argv[1], float(sys.argv[2])
m = Mem(who)
last, t0 = None, time.time()
while time.time() - t0 < secs:
    try:
        mgr = m.u64(m.base + 0x5B3CE08)
        par = m.u64(m.base + 0x5B3CDF8)
        cur = [m.u32(mgr + 0x126C) if mgr else -1, m.u32(mgr + 0x1268) if mgr else -1, m.u32(mgr + 0x18) if mgr else -1]
        if par:
            ms = m.u64(par + 0x2D8)
            cur += [m.u32(par + 0x50), m.u32(par + 0xB8), m.read(par + 0x47A8, 2).hex(), m.read(ms + 0x20, 1)[0] if ms else -1]
        else:
            cur += ['no par']
        cur = tuple(cur)
    except Exception as e:
        cur = ('err', str(e)[:40])
    if cur != last:
        print(time.strftime('%H:%M:%S'), '%.2f' % (time.time() - t0), who, 'state/mode/members', cur[:3], 'step/round/watchdog/ready', cur[3:], flush=True)
        last = cur
