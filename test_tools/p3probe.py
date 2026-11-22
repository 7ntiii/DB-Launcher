"""Print a twin game's PrepareThird readiness inputs whenever they (or the phase) change:
lot done [par+0x2e8]+0x1240 (byte), env loader par[0x2d0] state +0x50 / done +0xd8, par[0x2c0] +0xb/+0xc.
python diag/twin/p3probe.py RUNTIME"""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5b3cdf8


def main():
    runtime = float(sys.argv[1])
    mems = {}
    end = time.time() + runtime
    last = {}
    while time.time() < end:
        for w in 'AB':
            try:
                m = mems.get(w) or mems.setdefault(w, Mem(w))
                par = m.u64(m.base + PAR)
                phase = m.u32(par + 0x50)
                lot = m.read(par + 0x2e8 + 0x1240, 1)[0]
                ld = m.u64(par + 0x2d0)
                st = (m.u32(ld + 0x50), m.read(ld + 0xd8, 1)[0]) if ld else None
                p2c0 = m.u64(par + 0x2c0)
                e = m.read(p2c0 + 0xb, 2).hex() if p2c0 else None
                line = f'phase {phase} round {m.u32(par + 0xb8)} lot_done {lot} loader {st} p2c0+b/c {e}'
                if line != last.get(w):
                    print(time.strftime('%H:%M:%S'), w, line, flush=True)
                    last[w] = line
            except Exception as ex:
                if last.get(w) != 'err':
                    print(time.strftime('%H:%M:%S'), w, 'error', str(ex)[:80], flush=True)
                    last[w] = 'err'
        time.sleep(0.5)


if __name__ == '__main__':
    main()
