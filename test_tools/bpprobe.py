"""One-shot breakpoint probe on a running twin game:
    python diag/twin/bpprobe.py A|B SECONDS OFF[,OFF...] [--keep]
Sets software breakpoints at main+OFF, prints the first hit of each (pc, x0-x8, x19-x28, lr, sp),
clears it and resumes (--keep: leave it and print every hit up to 20), then after SECONDS clears all
and resumes the game before closing (never leave a twin game halted)."""
import socket
import sys
import time

sys.path.insert(0, 'diag/twin')
sys.path.insert(0, 'diag/net')
from mem import Mem
from gdb import Gdb


def main():
    who, secs = sys.argv[1], float(sys.argv[2])
    offs = [int(t, 16) for t in sys.argv[3].split(',')]
    keep = '--keep' in sys.argv
    base = Mem(who).base
    g = Gdb(6543 if who == 'A' else 6544)
    print('connected', g.cmd('?')[:20], flush=True)
    for o in offs:
        print(f'bp main+{o:#x}', g.cmd(f'Z0,{base + o:x},4'), flush=True)
    g._send('c')
    end = time.time() + secs
    left, hits = set(offs), 0
    try:
        while left and time.time() < end and hits < 20:
            try:
                r = g._recv(timeout=max(0.1, end - time.time()))
            except socket.timeout:
                break
            if r.startswith('O') or r in ('OK', ''):
                continue
            x = g.regs()
            pc = x[32]
            off = pc - base
            hits += 1
            regs = ' '.join(f'x{i}={x[i]:#x}' for i in list(range(0, 9)) + list(range(19, 29)))
            print(time.strftime('%H:%M:%S'), f'hit main+{off:#x}', regs,
                  f'lr=main+{x[30] - base:#x} sp={x[31]:#x}', flush=True)
            if off in left and not keep:
                g.cmd(f'z0,{pc:x},4')
                left.discard(off)
            g._send('c')
    finally:
        g.s.sendall(b'\x03')
        try:
            g._recv(timeout=5)
        except socket.timeout:
            pass
        for o in offs:
            g.cmd(f'z0,{base + o:x},4')
        g._send('c')
        time.sleep(0.3)
        g.s.close()
        print('resumed and closed; not hit:', ' '.join(hex(o) for o in sorted(left)) or '-', flush=True)


if __name__ == '__main__':
    main()
