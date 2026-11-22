"""Which code applies the Blink / Neb-ra / Darkmoon SpEffects (vanish_death_notes.md 1). One game, short window.
    python diag/twin/blink_site.py A|B [SECONDS=8] [MAXHITS=300]
Start it, then cast the skill on THAT game's own player at once. A software breakpoint at NetChrIns::ApplySpecialEffect
0xE8BBC0 stops each call for a few ms. Every call is counted. Calls whose SpEffect id is 1400000..1449999 are
printed with w5 (1 = local only, never sent), the chr and LR, i.e. the site that applies it.
Then the breakpoint is cleared and the game resumed, in all cases (never leaves the game halted).
Cost: one halt per SpEffect apply in the window, capped at MAXHITS (then cleared). No heap search.
match 5 (fx_blink_m5.txt): the caster's own copy gets 1401010 (VFX 140110), 1401020 (VFX 140120) and 1401021
(VFX 140121); the other game's copy gets none. Neither id is in any param or code constant, so the site is the
open question: TAE (LR in 0x193xxxx..0x194xxxx) or the skill module (0xE69xxx..0xE71xxx)."""
import socket
import sys
import time

sys.path.insert(0, 'diag/twin')
sys.path.insert(0, 'diag/net')
from mem import Mem  # noqa: E402
from gdb import Gdb  # noqa: E402

APPLY = 0xE8BBC0


def main():
    who = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    m = Mem(who)
    base = m.base
    g = Gdb(6543 if who == 'A' else 6544)
    print('connected', g.cmd('?')[:20], flush=True)
    bp = base + APPLY
    print('bp main+%#x' % APPLY, g.cmd('Z0,%x,4' % bp), flush=True)
    g._send('c')
    end = time.time() + secs
    hits, shown, sites = 0, 0, {}
    try:
        while time.time() < end and hits < cap:
            try:
                r = g._recv(timeout=max(0.1, end - time.time()))
            except socket.timeout:
                break
            if r.startswith('O') or r in ('OK', ''):
                continue
            x = g.regs()
            hits += 1
            x1 = x[1]
            sid = None
            if 0 < (x1 & 0xFFFFFFFF) < 100000000 and x1 < 0x100000000:
                sid = x1 & 0xFFFFFFFF                       # the id itself
            else:
                try:
                    sid = int.from_bytes(m.read(x1, 4), 'little')   # or a pointer to it
                except Exception:
                    sid = None
            lr = x[30] - base
            if sid is not None and 1400000 <= sid < 1450000:
                shown += 1
                key = (sid, lr, x[5] & 1)
                sites[key] = sites.get(key, 0) + 1
                print(time.strftime('%H:%M:%S'), 'SpEffect %d w5=%d chr=%#x lr=main+%#x (site main+%#x)' % (
                    sid, x[5] & 0xFFFFFFFF, x[0], lr, lr - 4), flush=True)
            g._send('c')
    finally:
        g.s.sendall(b'\x03')
        try:
            g._recv(timeout=5)
        except socket.timeout:
            pass
        g.cmd('z0,%x,4' % bp)
        g._send('c')
        time.sleep(0.3)
        g.s.close()
        print('resumed and closed; %d applies seen, %d skill ids%s' % (hits, shown, ' (cap reached)' if hits >= cap else ''))
        for (sid, lr, w5), n in sorted(sites.items()):
            print('  %d  site main+%#x  w5 bit0 %d  x%d' % (sid, lr - 4, w5, n))


if __name__ == '__main__':
    main()
