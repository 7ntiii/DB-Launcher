"""TEST ONLY. Set the phase clock (seconds left) once on rig games: python diag/twin/set_clock.py GAMES SECONDS
Same address as hold_clock.py; only in UpdatePhase (phase 6)."""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
for w in sys.argv[1]:
    m = Mem(w)
    par = m.u64(m.base + 0x5B3CDF8)
    if par and m.u32(par + 0x50) == 6:
        clock = m.u64(par + 0x120)
        old = struct.unpack('<f', m.read(clock + 8, 4))[0]
        m.write(clock + 8, struct.pack('<f', float(sys.argv[2])))
        print(w, 'clock', round(old), '->', sys.argv[2])
    else:
        print(w, 'not in UpdatePhase')
