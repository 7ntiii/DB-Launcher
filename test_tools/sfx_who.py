"""Who creates an effect? One-shot breakpoint probe at the SFX wrapper constructors (read only apart from the
breakpoint; the game is resumed after every hit and at the end).
    python diag/twin/pkgtest.py run diag/twin/sfx_who.py A|B [SECONDS=6] [HITS=12]
Breakpoints: main+0x1D429E4 and main+0x1D42D0C (CSFD4SingleSfxIns vptr writes), main+0x1D410C8 (CSFD4SfxIns).
Each hit prints x0-x8, x19-x28, lr and the frame-pointer chain (up to 10 return addresses, as main+off), so the
requester of the effect is the first frame outside the SFX code (0x1D40000..0x1D50000 / 0x1580000..0x1590000).
At the end: the return chains grouped by count. Never leaves the game halted."""
import socket
import struct
import sys
import time
from collections import Counter

sys.path.insert(0, 'diag/twin')
sys.path.insert(0, 'diag/net')
from mem import Mem
from gdb import Gdb

OFFS = [0x1D429E4, 0x1D42D0C, 0x1D410C8]


def chain(g, base, fp, n=10):
    out = []
    for _ in range(n):
        if fp < 0x1000 or fp & 7:
            break
        try:
            b = g.mem(fp, 16)
        except Exception:
            break
        if not b or len(b) < 16:
            break
        fp, lr = struct.unpack('<QQ', b[:16])
        lr &= 0x0000FFFFFFFFFFFF  # drop a pointer-authentication code, if any
        off = lr - base
        out.append(off if 0 <= off < 0x6000000 else -1)
    return out


def main():
    who = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 6
    want = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    hold = sys.argv[sys.argv.index('--hold') + 1] if '--hold' in sys.argv else None
    base = None if hold else Mem(who).base
    g = None
    for _ in range(180):
        try:
            g = Gdb(6543 if who == 'A' else 6544)
            break
        except OSError:
            time.sleep(1)
    print('connected', g.cmd('?')[:20], flush=True)
    if hold:
        # the stub closes (and the game halts) when its one client leaves: stay connected for the whole
        # session, let the game run, and probe when the trigger file appears
        import os
        g._send('c')
        print('holding; game runs; waiting for', hold, flush=True)
        while not os.path.exists(hold):
            time.sleep(0.5)
        os.remove(hold)
        g.s.sendall(b'')
        try:
            g._recv(timeout=5)
        except socket.timeout:
            pass
        base = Mem(who).base
        print(time.strftime('%H:%M:%S'), 'trigger: probing', flush=True)
    for o in OFFS:
        print(f'bp main+{o:#x}', g.cmd(f'Z0,{base + o:x},4'), flush=True)
    g._send('c')
    end = time.time() + secs
    hits, seen = 0, Counter()
    try:
        while time.time() < end and hits < want:
            try:
                r = g._recv(timeout=max(0.1, end - time.time()))
            except socket.timeout:
                break
            if r.startswith('O') or r in ('OK', ''):
                continue
            x = g.regs()
            pc, off = x[32], x[32] - base
            hits += 1
            ch = chain(g, base, x[29])
            lr = (x[30] & 0x0000FFFFFFFFFFFF) - base
            regs = ' '.join(f'x{i}={x[i]:#x}' for i in list(range(0, 9)) + list(range(19, 29)))
            print(time.strftime('%H:%M:%S'), f'hit main+{off:#x} lr=main+{lr:#x}', regs, flush=True)
            print('    chain', ' <- '.join('?' if c < 0 else f'{c:#x}' for c in ch), flush=True)
            seen[(off, lr) + tuple(ch[:6])] += 1
            g._send('c')  # as bpprobe.py --keep does: the stub steps over its own breakpoint
    finally:
        g.s.sendall(b'\x03')
        try:
            g._recv(timeout=5)
        except socket.timeout:
            pass
        for o in OFFS:
            g.cmd(f'z0,{base + o:x},4')
        g._send('c')
        time.sleep(0.3)
        print(f'resumed; {hits} hit(s)', flush=True)
        for key, n in seen.most_common(8):
            print(f'  x{n}: at {key[0]:#x} lr {key[1]:#x} chain ' + ' <- '.join('?' if c < 0 else f'{c:#x}' for c in key[2:]), flush=True)
        if hold:
            print('still holding the connection so the game keeps running (kill me only after the match)', flush=True)
            while True:
                time.sleep(5)
        g.s.close()
    for key, n in seen.most_common(8):
        print(f'  x{n}: at {key[0]:#x} lr {key[1]:#x} chain ' + ' <- '.join('?' if c < 0 else f'{c:#x}' for c in key[2:]))


if __name__ == '__main__':
    main()
