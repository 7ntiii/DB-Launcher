"""Kill tracker and elimination state of the final, both games side by side.
python diag/twin/final_kills.py AB                 print once (read only)
python diag/twin/final_kills.py AB watch SECONDS   print every second
python diag/twin/final_kills.py A kill             write 0 to game A's local player HP (master copy), then print
Recipe (diag/net/live_enumeration_notes.md section 5), par = *(main+0x5B3CDF8):
  K = [par+0x3398] last-phase kill tracker; map T = K+0x40 (0x9C reader 0x1165040 is called with K+0x40) [V 0x1140AE4]
      node list: first [K+0x60], next node+0; node +0x10 u32 victim player id, +0x14 u8 dead mark          [V 0x1165128, 0x1165470]
      K+8 u8 'local elimination handled', listener [K+0x80]                                               [V 0x1166688]
  *(main+0x5B44240)+0xC u8: when set, 0x1166688 does nothing                                              [V]
  par+0x38A0.. libc++ deque of 8-byte {u32 player no, u8 flag}: map begin +0x38A8, end +0x38B0, start +0x38C8,
      size +0x38D0, 512 per block (0x1143580, queued by 0x116FD20 -> 0x1143580 when 0x11435B0 is patched)  [V]
  par+0x164 spectate byte (offline local death), +0x16C all-stage-4, +0x16D ended by clock; local chr +0x26E4 bit 0x400 [V]
  HP: master [entry0+0x18]+0xF30, copy pgd+8 (pgd = [[chr+0x20]+0x1D0]), pgd+0x46B0 stage word     [V hp.py, notes]"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, PAR_G, KILLGATE_G


def snap(w):
    s = {}
    par = w.g(PAR_G)
    if not par:
        w.null('par *(main+0x5B3CDF8)')
        return s
    s['phase'], s['next'], s['round'] = w.d(par + 0x50), w.d(par + 0x54), w.d(par + 0xB8)
    b = w.rd(par + 0x164, 0xC)
    s['164'], s['16c'], s['16d'] = (b[0], b[8], b[9]) if b else (None, None, None)
    s['coord'] = w.q(par + 0x3388)
    k = w.q(par + 0x3398)
    s['K'] = k
    nodes = []
    if k:
        s['K8'] = w.b(k + 8)
        s['size'] = w.q(k + 0x68)
        n, guard = w.q(k + 0x60), 0
        while n and guard < 32:
            nodes.append((w.d(n + 0x10), w.b(n + 0x14)))
            n, guard = w.q(n), guard + 1
    else:
        w.null('kill tracker par+0x3398 (only in the last phase)')
    s['nodes'] = nodes
    gate = w.g(KILLGATE_G)
    s['gate'] = w.b(gate + 0xC) if gate else None
    beg, end, start, size = (w.q(par + o) for o in (0x38A8, 0x38B0, 0x38C8, 0x38D0))
    ev = []
    if size and beg and end and start is not None and size < 64:
        for i in range(size):
            idx = start + i
            blk = w.q(beg + 8 * (idx >> 9))
            e = w.rd(blk + 8 * (idx & 0x1FF), 8) if blk else None
            ev.append((struct.unpack_from('<I', e)[0], e[4]) if e else None)
    s['deque'] = (size, ev)
    pl = []
    for e in w.players():
        c = e[0]
        data = w.q(c + 0x20)
        pgd = w.q(data + 0x1D0) if data else None
        st = w.rd(pgd + 0x46B0, 4) if pgd else None
        pl.append({'no': w.d(pgd + 0xD0) if pgd else None, 'hp': w.i(pgd + 8) if pgd else None,
                   'master': w.i(e[3] + 0xF30) if e[3] else None, 'stage': st.hex() if st else None,
                   'ranked': w.b(pgd + 0x46A0) if pgd else None, '26e4': w.d(c + 0x26E4)})
    s['players'] = pl
    return s


def line(w, s):
    if not s:
        return '%s: no par' % w.who
    pl = ' '.join('[no %s hp %s/%s stage %s rk %s %s]' % (
        p['no'], p['master'], p['hp'], p['stage'], p['ranked'],
        'OUT' if p['26e4'] is not None and p['26e4'] & 0x400 else '') for p in s['players'])
    return ('%s: phase %s->%s round %s | tracker %s K+8 %s nodes(victim,dead) %s | gate %s | deque %s | '
            '164 %s 16C %s 16D %s | %s') % (
        w.who, s['phase'], s['next'], s['round'], w.rel(s.get('K')), s.get('K8'), s['nodes'], s['gate'],
        s['deque'], s['164'], s['16c'], s['16d'], pl)


def main():
    games = sys.argv[1]
    verb = sys.argv[2] if len(sys.argv) > 2 else 'show'
    ws = [W(g) for g in games]
    if verb == 'kill':
        w = ws[0]
        e = w.player_entry(0)
        if not e or not e[3]:
            print('no local player entry')
        else:
            old = w.i(e[3] + 0xF30)
            w.write(e[3] + 0xF30, struct.pack('<i', 0))
            print('%s: master HP %s -> 0 ([entry0+0x18]+0xF30)' % (w.who, old))
            time.sleep(1.0)
    secs = float(sys.argv[3]) if verb == 'watch' and len(sys.argv) > 3 else 0
    t0 = time.time()
    while True:
        for w in ws:
            print(line(w, snap(w)), flush=True)
        if time.time() - t0 >= secs:
            break
        time.sleep(1.0)
    for w in ws:
        w.report_missing()


if __name__ == '__main__':
    main()
