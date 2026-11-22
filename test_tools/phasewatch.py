"""Log every match-phase change of both twin games; optionally open the phase-result gate (phase 9,
gate+0x38) like newer assists do. python diag/twin/phasewatch.py SECONDS [--gate38]"""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR, GATE = 0x5b3cdf8, 0x5b3ce18


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 600
    gate38 = '--gate38' in sys.argv
    mems = {w: Mem(w) for w in 'AB'}
    last = {}
    end = time.time() + seconds
    while time.time() < end:
        for w, m in mems.items():
            try:
                par = m.u64(m.base + PAR)
                phase = m.u32(par + 0x50)
                if phase != last.get(w):
                    print(time.strftime('%H:%M:%S'), w, 'phase', phase, flush=True)
                    last[w] = phase
                if gate38 and phase == 9:
                    gate = m.u64(m.base + GATE)
                    if gate and m.read(gate + 0x38, 1)[0] == 0:
                        m.write(gate + 0x38, b'\x01')
                        print(time.strftime('%H:%M:%S'), w, 'gate+0x38 set', flush=True)
            except Exception as ex:  # a game closed or a page is between maps
                if last.get(w) != 'err':
                    print(time.strftime('%H:%M:%S'), w, 'error', str(ex)[:80], flush=True)
                    last[w] = 'err'
        time.sleep(2)


if __name__ == '__main__':
    main()
