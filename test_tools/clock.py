"""Set the match phase clock (time left, seconds) on twin games: python diag/twin/clock.py SECONDS [A|B|AB]
Only touches a game in UpdatePhase (phase 6); the clock is par[0x120] +8 (float)."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5b3cdf8


def main():
    secs = float(sys.argv[1])
    who = sys.argv[2] if len(sys.argv) > 2 else 'AB'
    for w in who:
        m = Mem(w)
        par = m.u64(m.base + PAR)
        phase = m.u32(par + 0x50)
        clock = m.u64(par + 0x120)
        left = struct.unpack('<f', m.read(clock + 8, 4))[0]
        if phase != 6:
            print(w, 'phase', phase, '- not in UpdatePhase, clock left', left)
            continue
        m.write(clock + 8, struct.pack('<f', secs))
        print(w, f'clock {left:.1f} -> {secs:.1f} s')


if __name__ == '__main__':
    main()
