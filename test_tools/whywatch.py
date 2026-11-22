"""Print every change of the CLOSEWHY / CLOSEWHY2 slots of one game: python diag/twin/whywatch.py A SECONDS
Slots (x1, caller): 0x1CD5E18 -> main+0x563E7F0; 0x1CD59E0 -> +0x563EDE0; 0x14BDA60 -> +0x563EDF0;
0x14C0354 -> +0x563EDD0. Also the session state and the match step."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

who, secs = sys.argv[1], float(sys.argv[2])
m = Mem(who)
SLOTS = (('1CD5E18', 0x563E7F0), ('1CD59E0', 0x563EDE0), ('14BDA60', 0x563EDF0), ('14C0354', 0x563EDD0))
last, t0 = {}, time.time()
while time.time() - t0 < secs:
    try:
        mgr = m.u64(m.base + 0x5B3CE08)
        par = m.u64(m.base + 0x5B3CDF8)
        st = (m.u32(mgr + 0x126C) if mgr else -1, m.u32(par + 0x50) if par else -1, m.u32(par + 0xB8) if par else -1)
        for name, off in SLOTS:
            x1, lr = struct.unpack('<QQ', m.read(m.base + off, 16))
            cur = (x1 & 0xFFFFFFFF, (lr & 0xFFFFFFFFFF) - m.base if lr else 0)
            if last.get(name) != cur:
                last[name] = cur
                print(time.strftime('%H:%M:%S'), who, 'fn', name, 'x1 %x caller main+0x%X' % cur, 'state/step/round', st, flush=True)
        if last.get('st') != st:
            last['st'] = st
            print(time.strftime('%H:%M:%S'), who, 'state/step/round', st, flush=True)
    except Exception as e:
        pass
    time.sleep(0.02)
