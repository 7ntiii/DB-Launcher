"""Fast full-match tests: whenever a twin game is in UpdatePhase (6) with more than SECONDS+10 s left,
cut its clock to SECONDS (once per round and game). python diag/twin/autoclock.py SECONDS RUNTIME"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5b3cdf8


def main():
    secs, runtime = float(sys.argv[1]), float(sys.argv[2])
    mems = {w: Mem(w) for w in 'AB'}
    end = time.time() + runtime
    while time.time() < end:
        for w, m in mems.items():
            try:
                par = m.u64(m.base + PAR)
                if m.u32(par + 0x50) != 6:
                    continue
                clock = m.u64(par + 0x120)
                left = struct.unpack('<f', m.read(clock + 8, 4))[0]
                if left > secs + 10:
                    m.write(clock + 8, struct.pack('<f', secs))
                    print(time.strftime('%H:%M:%S'), w, f'round {m.u32(par + 0xb8)}: clock {left:.1f} -> {secs:.1f} s',
                          flush=True)
            except Exception as ex:  # a game between maps or closed
                print(time.strftime('%H:%M:%S'), w, 'error', str(ex)[:80], flush=True)
                time.sleep(5)
        time.sleep(2)


if __name__ == '__main__':
    main()
