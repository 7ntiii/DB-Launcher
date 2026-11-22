"""TEST ONLY (DECIDEONCE, 2026-11-20): host's start slots / decided / locked flags per 0.1 s in round 4. Read only.
python diag/twin/slot_watch.py A [SECONDS=600]"""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

STAGE_PHASE, P_ROUND, P_STATE = 0x5B3CDF8, 0xB8, 0x50
MEDIATOR, MED_DECIDED, MED_LOCKED, MED_LIST_COUNT = 0x5B44EA0, 0xB9, 0xBA, 0x5D8
MED_SLOTS, MED_SLOT_SIZE, MED_SLOT_COUNT = 0xC0, 0x30, 0x248


def main():
    m = Mem(sys.argv[1])
    end = time.time() + (float(sys.argv[2]) if len(sys.argv) > 2 else 600)
    last = None
    while time.time() < end:
        try:
            stage = m.u64(m.base + STAGE_PHASE)
            med = m.u64(m.base + MEDIATOR)
            if not stage or not med:
                time.sleep(0.1)
                continue
            rnd, phase = m.u32(stage + P_ROUND), m.u32(stage + P_STATE)
            n = m.u64(med + MED_SLOT_COUNT)
            nos = [m.u32(med + MED_SLOTS + i * MED_SLOT_SIZE) for i in range(min(n, 8))]
            dec, lck = m.read(med + MED_DECIDED, 2)
            lc = m.u64(med + MED_LIST_COUNT)
        except Exception as e:
            print('read failed', e, flush=True)
            return 1
        if rnd == 4 or (rnd == 3 and phase in (9, 10, 11, 18)):
            cur = (rnd, phase, n, tuple(nos), dec, lck, lc)
            if cur != last:
                print('%s round %d phase %2d slots %d %s decided %d locked %d list %d' % (
                    time.strftime('%T'), rnd, phase, n, nos, dec, lck, lc), flush=True)
                last = cur
            if rnd == 4 and phase == 6:
                return 0
        time.sleep(0.05)
    return 0


if __name__ == '__main__':
    sys.exit(main())
