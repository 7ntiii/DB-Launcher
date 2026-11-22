"""Hold *(main+0x5B65C20)+0xBDA (the "offline match" flag) at 1 on twin games, logging changes.
python diag/twin/hold_bda.py [AB] [SECONDS]"""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
until = time.time() + (float(sys.argv[2]) if len(sys.argv) > 2 else 3600)
ms = {w: Mem(w) for w in games}
while time.time() < until:
    for w, m in ms.items():
        try:
            g = m.u64(m.base + 0x5B65C20)
            if g and m.read(g + 0xBDA, 1)[0] != 1:
                par = m.u64(m.base + 0x5B3CDF8)
                ph = m.u32(par + 0x50) if par else -1
                m.write(g + 0xBDA, b'\x01')
                print(time.strftime('%H:%M:%S'), w, 'flag was 0, set 1 (phase %d)' % ph, flush=True)
        except Exception as e:
            print(time.strftime('%H:%M:%S'), w, 'error', e, flush=True)
            time.sleep(2)
    time.sleep(0.05)
