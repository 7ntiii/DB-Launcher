"""Sandbox match: keep the phase clock of the twin games high so the match never ends, for live tests
without relaunching. python diag/twin/hold_clock.py [GAMES=AB] [SECONDS_LEFT=300] [RUN_FOR_S=7200]
Only touches games in UpdatePhase (phase 6). Stop it (kill this process) to let the match go on."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
keep = float(sys.argv[2]) if len(sys.argv) > 2 else 300
t_end = time.time() + (float(sys.argv[3]) if len(sys.argv) > 3 else 7200)
while time.time() < t_end:
    for w in games:
        try:
            m = Mem(w)
            par = m.u64(m.base + 0x5B3CDF8)
            if par and m.u32(par + 0x50) == 6:
                clock = m.u64(par + 0x120)
                if struct.unpack('<f', m.read(clock + 8, 4))[0] < keep - 30:
                    m.write(clock + 8, struct.pack('<f', keep))
                if 'nohp' not in sys.argv:
                    # keep the test player alive: master HP (entry module +0xF30) back to max
                    wcm = m.u64(m.base + 0x5B3CD88)
                    ent = m.u64(wcm + 0x30)
                    chr_, mod = m.u64(ent), m.u64(ent + 0x18)
                    data = m.u64(m.u64(chr_ + 0x20) + 0x1d0)
                    hp, mx = struct.unpack('<2i', m.read(data + 8, 8))
                    if 0 < hp < mx:
                        m.write(mod + 0xF30, struct.pack('<i', mx))
        except Exception:
            pass
    time.sleep(1.5)
