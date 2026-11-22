"""Test helper: from round 4 on keep MS+0x20 (lists ready -> PrepareThird applies) at 0 on the given games.
python diag/twin/hold_noapply.py [GAMES=AB] [SECONDS=900]"""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 900
ms = {w: Mem(w) for w in games}
t0 = time.time()
n = 0
while time.time() - t0 < limit:
    for w, m in ms.items():
        try:
            par = m.u64(m.base + 0x5B3CDF8)
            if not par:
                continue
            step, rnd = m.u32(par + 0x50), m.u32(par + 0xB8)
            msys = m.u64(par + 0x2D8)
            if msys and rnd >= 4:
                if m.read(msys + 0x20, 1)[0]:
                    m.write(msys + 0x20, b'\0')
                    n += 1
                    print(time.strftime('%H:%M:%S'), w, 'cleared the ready flag at step', step, 'round', rnd, flush=True)
        except Exception:
            pass
    time.sleep(0.03)
