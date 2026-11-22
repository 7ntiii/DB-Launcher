"""TEST ONLY (final-crash trigger proof, 2026-11-20): LOADGRAVE's delete counter on one game, per 0.5 s, in round 4.
python diag/twin/gy_watch.py B [SECONDS=120]

Prints the match phase and GYBOX (main+0xC50F8F8, u32: load-process deletes so far) whenever either changes,
from round 4's first phase on, so the release burst can be placed against phases 21 / 26 / 4 / 6. Read only."""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

STAGE_PHASE, P_ROUND, P_STATE, GYBOX = 0x5B3CDF8, 0xB8, 0x50, 0xC50F8F8


def main():
    who = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 120
    m = Mem(who)
    end, last, t0 = time.time() + secs, None, None
    while time.time() < end:
        try:
            stage = m.u64(m.base + STAGE_PHASE)
            rnd = m.u32(stage + P_ROUND) if stage else 0
            phase = m.u32(stage + P_STATE) if stage else 0
            gy = m.u32(m.base + GYBOX)
        except Exception as e:  # the game went away
            print('%s read failed: %s' % (time.strftime('%T'), e), flush=True)
            return 1
        if rnd == 4:
            if t0 is None:
                t0, g0 = time.time(), gy
            if (phase, gy) != last:
                print('%s +%5.1f s phase %2d deletes %d (+%d since round 4)' % (
                    time.strftime('%T'), time.time() - t0, phase, gy, gy - g0), flush=True)
                last = (phase, gy)
        time.sleep(0.5)
    return 0


if __name__ == '__main__':
    sys.exit(main())
