"""Watch what UpdatePhase (match phase 6, handler 0x114b9cc) waits on, in both twin games.
python diag/twin/phase6.py [seconds=600] [every=5]   (workspace root; prints a line when a value changes)

0x114b9cc: if par+0xc0 bit 0 -> end the phase (0x1149160, then vt+0x38). Else if the sub-object at
par+0x4ce8 answers vt+0x60 == 1 (its state +0x50): end only once par+0x4db1 is set (server 0xc1 event 8;
the c1 stub sets it when the game sends type 7). Else the timer par+0x3388 (vt+0x58 = time left) runs;
when byte par+0x4b40 and timer+0x10 are both 0 the phase ends (0x114bcb0 first), and a set byte at
[par+0x3398]+8 also ends it (when *(main+0x5b44240)+0xc is set)."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5b3cdf8


def snap(m):
    par = m.u64(m.base + PAR)
    if par == 0:
        return {'par': 0}
    st, nx = struct.unpack('<II', m.read(par + 0x50, 8))
    out = {'st': st, 'nx': nx}
    sub = m.u64(par + 0x4ce8)
    if sub:
        out['sub'] = f'vt+{m.u64(sub) - m.base:#x} st {m.u32(sub + 0x50)}/{m.u32(sub + 0x54)}'
    for name, off in (('c0', 0xc0), ('164', 0x164), ('16d', 0x16d), ('4b40', 0x4b40), ('4db1', 0x4db1)):
        out[name] = m.read(par + off, 1)[0]
    timer = m.u64(par + 0x3388)
    if timer:
        raw = m.read(timer, 0x30)
        floats = struct.unpack('<8f', raw[0x10:0x30])
        out['timer'] = f'vt+{struct.unpack("<Q", raw[:8])[0] - m.base:#x} +8 {raw[8:0x10].hex()} ' + \
            ' '.join(f'{v:.2f}' if abs(v) < 1e6 else '-' for v in floats)
    x3398 = m.u64(par + 0x3398)
    if x3398:
        out['3398+8'] = m.read(x3398 + 8, 1)[0]
    g = m.u64(m.base + 0x5b44240)
    if g:
        out['5b44240+c'] = m.read(g + 0xc, 1)[0]
    return out


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 600
    every = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    mems = {w: Mem(w) for w in 'AB'}
    last = {}
    end = time.time() + seconds
    while time.time() < end:
        for w, m in mems.items():
            try:
                s = snap(m)
            except Exception as ex:  # a game closed or is between pages
                s = {'err': str(ex)[:80]}
            if s != last.get(w):
                print(time.strftime('%H:%M:%S'), w, ' '.join(f'{k}={v}' for k, v in s.items()), flush=True)
                last[w] = s
        time.sleep(every)


if __name__ == '__main__':
    main()
