"""clock.py for 3+ games (run4.sh; diag/net/run4_dry_notes.md 2): python diag/twin/clock4.py SECONDS GAMES
Same writes and output lines as clock.py ("W clock L -> S s" / "W phase P - not in UpdatePhase ..."), but
  1. every game is resolved FIRST (debug connection, main base from the logs, phase, clock address), and
  2. then the clocks are written back to back, the cut authority (u8 main+0x492AFD8 GENERATOR_IDLE == 0) first.
clock.py resolves and writes one game after the other: main_base() re-reads each game's whole logs, so with four
games the last write came seconds after the first. A guest whose phase ended before the authority's then held
its clock for the authority's list (CUTAUTH) and its cut came late: false FAILs in run4_check.py cutlog
(hold_max 1.5 s, end lag). Last line: "order AUTH..., spread N ms". Writes only the phase clock, as clock.py."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5b3cdf8
GENERATOR_IDLE = 0x492AFD8


def main():
    secs = float(sys.argv[1])
    who = sys.argv[2] if len(sys.argv) > 2 else 'AB'
    ready = []
    for w in who:
        try:
            m = Mem(w)
            par = m.u64(m.base + PAR)
            phase = m.u32(par + 0x50)
            clock = m.u64(par + 0x120)
            left = struct.unpack('<f', m.read(clock + 8, 4))[0]
            idle = m.read(m.base + GENERATOR_IDLE, 1)[0]
        except Exception as ex:                 # clock.py would stop here with a traceback
            print(w, 'unreachable -', ex)
            continue
        if phase != 6:
            print(w, 'phase', phase, '- not in UpdatePhase, clock left', left)
            continue
        ready.append((idle != 0, w, m, clock, left))
    ready.sort(key=lambda r: r[0])              # stable: the authority first, then the given order
    t0 = time.perf_counter()
    for _, w, m, clock, _left in ready:
        m.write(clock + 8, struct.pack('<f', secs))
    spread = (time.perf_counter() - t0) * 1000
    for idle, w, _m, _clock, left in ready:
        print(w, f'clock {left:.1f} -> {secs:.1f} s' + ('' if idle else ' (authority)'))
    print('order %s, spread %.0f ms' % (''.join(r[1] for r in ready) or '-', spread))


if __name__ == '__main__':
    main()
