"""Print changes of the TERMWHY slot (main+0x563E8E0: reason x1, caller, transport error code): python diag/twin/termwatch.py A SECONDS"""
import struct, sys, time
sys.path.insert(0, 'diag/twin')
from mem import Mem
who, secs = sys.argv[1], float(sys.argv[2])
m = Mem(who); last = None; t0 = time.time()
while time.time() - t0 < secs:
    try:
        x1, lr, code = struct.unpack('<QQI', m.read(m.base + 0x563E8E0, 20))
        cur = (x1 & 0xFFFFFFFF, (lr & 0xFFFFFFFFFF) - m.base if lr else 0, code)
        if cur != last:
            last = cur
            print(time.strftime('%H:%M:%S'), who, 'terminate reason %d caller main+0x%X code 0x%08X' % cur, flush=True)
    except Exception:
        pass
    time.sleep(0.3)
