"""Walk the CSInitializeSyncStep loader of both games one step at a time while they sit in a step
(st 8, where the watcher's QW_WALK does not act). Usage: python diag/twin/walk8.py [stall_s] [max_step]"""
import sys, time, struct, os
sys.path.insert(0, 'diag/twin')
from mem import Mem
stall = float(sys.argv[1]) if len(sys.argv) > 1 else 6
top = int(sys.argv[2]) if len(sys.argv) > 2 else 17
ms = {w: Mem(w) for w in 'AB'}
port = {'A': 6543, 'B': 6544}
last = {}
t0 = time.time()
while time.time() - t0 < 300:
    done = True
    for w, m in ms.items():
        mgr = m.u64(m.u64(m.base + 0x59dfec8)); ld = m.u64(mgr + 0x14c8)
        st = struct.unpack('<I', m.read(mgr + 0x126c, 4))[0]
        cur = struct.unpack('<I', m.read(ld + 0x50, 4))[0] if ld else -1
        if cur < top:
            done = False
        k = (st, cur)
        if last.get(w, (None, 0))[0] != k:
            last[w] = (k, time.time()); print(f'{time.strftime("%H:%M:%S")} {w} st={st} step={cur}', flush=True)
        elif st == 8 and 0 < cur < top and time.time() - last[w][1] >= stall:
            with open(f'diag/net/qw_cmd_{port[w]}.txt', 'a') as f:
                f.write(f'M {ld + 0x54:x} {struct.pack("<I", cur + 1).hex()}\n')
            print(f'{time.strftime("%H:%M:%S")} {w} walk {cur}->{cur + 1}', flush=True)
            last[w] = (k, time.time())
    if done:
        break
    time.sleep(1)
