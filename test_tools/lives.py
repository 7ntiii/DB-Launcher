"""Two-lives state of the final, every game side by side (READ ONLY: no write anywhere).
python diag/twin/lives.py AB                 print once
python diag/twin/lives.py AB watch SECONDS   print every second
Design: diag/net/lives_stuck_notes.md. Fields (pgd = [[chr+0x20]+0x1D0], par = *(main+0x5B3CDF8)):
  role  main+0x492AFD8 (0 = host)                                                   [V shipped gate 0x563EB00]
  C     par+0x3388 last-phase coordinator; vt main+0x56F5F70 = point select (0x116A6A0) [V final_variants_notes]
        C+0x10 active, C+0x138 respawn queue count, C+0xD0 entries {u32 player, i32 point, f32 timer} x 0xC [V 0x116C340]
  fade  [main+0x5B99BB0]+0x80: non-null -> a LOCAL queue entry waits (0x116A8EC)       [V]
  per player: no pgd+0xD0, stock pgd+0x42A4, stage pgd+0x46B0..B3 (01 01 00 00 in play, 04 05 01 01 out),
        flag chr+0x26E4 bit16 (respawn chosen), bit8 (0x17BEE4C called), bit 0x400 (OUT),
        rsp chrdata+0x2D0 bit0 (0x116C0C0 ran; cleared by revive 0x17BDA54), net [[chr+0x18]+0x30]+0x18
        (bit0: local warp 0x17BEE4C refuses), pend chr+0x25E9 (remote warp marker), HP master/copy.
  kill tracker / elimination deque: from final_kills.py snap()."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, PAR_G
import final_kills

ROLE = 0x492AFD8
FADE_G = 0x5B99BB0
VT_POINT = 0x56F5F70
VT_RANDOM = 0x56F5D68


def player(w, e, local_chr):
    c = e[0]
    data = w.q(c + 0x20)
    pgd = w.q(data + 0x1D0) if data else None
    net = w.q(c + 0x18)
    sub = w.q(net + 0x30) if net else None
    f = w.d(c + 0x26E4)
    st = w.rd(pgd + 0x46B0, 4) if pgd else None
    nb = w.b(sub + 0x18) if sub else None
    m2470 = w.q(c + 0x2470)
    m220 = w.q(m2470 + 0x220) if m2470 else None
    # host collector 0x116C638, exactly [V]: net bit1 -> needs (module +0x220 null or its +0x14 == 0) unless bit0;
    # net bit0 -> ok; neither -> skipped. Then rsp == 0 and stage byte 46B0 == 1.
    if nb is None:
        dead_ok = None
    elif nb & 1:
        dead_ok = True
    elif nb & 2:
        dead_ok = (m220 is None or m220 == 0) or w.b(m220 + 0x14) == 0
    else:
        dead_ok = False
    rspb = w.b(data + 0x2D0) if data else None
    listable = (dead_ok and rspb is not None and not (rspb & 1) and st is not None and st[0] == 1)
    return {
        'dead_ok': dead_ok, 'listable': listable,
        'no': w.d(pgd + 0xD0) if pgd else None,
        'local': c == local_chr,
        'stock': w.b(pgd + 0x42A4) if pgd else None,
        'stage': st.hex() if st else None,
        'flag': (f >> 16) & 1 if f is not None else None,
        'b8': (f >> 8) & 1 if f is not None else None,
        'out': (f >> 10) & 1 if f is not None else None,
        'rsp': (w.b(data + 0x2D0) & 1) if data and w.b(data + 0x2D0) is not None else None,
        'net': w.b(sub + 0x18) if sub else None,
        'pend': w.b(c + 0x25E9),
        'master': w.i(e[3] + 0xF30) if e[3] else None,
        'hp': w.i(pgd + 8) if pgd else None,
    }


def snap(w):
    s = {'role': w.b(w.base + ROLE)}
    # host death-list preconditions in 0x116A6A0 [V]: C+0x10 != 0 (0x116A6E0); the mode object
    # (GOT main+0x59DFEC8 -> global -> obj, obj+0x1268; 6 = guest read path first, host continues);
    # gamedata+0xBDA (0x116ACDC: 0 -> online path, the shipped cave then sends role 0 back to the list)
    gl = w.q(w.base + 0x59DFEC8)
    mo = w.q(gl) if gl else None
    s['mode'] = w.d(mo + 0x1268) if mo else None
    gd = w.g(0x5B65C20)
    s['bda'] = w.b(gd + 0xBDA) if gd else None
    par = w.g(PAR_G)
    c = w.q(par + 0x3388) if par else None
    s['C'] = c
    if c:
        b0, b8 = w.q(c + 0xB0), w.q(c + 0xB8)
        s['points'] = (b8 - b0) // 8 if b0 is not None and b8 is not None and b8 >= b0 else None
        vt = w.q(c)
        s['vt'] = {w.base + VT_POINT: 'point', w.base + VT_RANDOM: 'random'}.get(vt, w.rel(vt))
        s['active'] = w.b(c + 0x10)
        n = w.q(c + 0x138)
        s['qn'] = n
        q = []
        if n is not None and n <= 8:
            raw = w.rd(c + 0xD0, 0xC * n) if n else b''
            for i in range(n):
                q.append(struct.unpack_from('<IIf', raw, 0xC * i) if raw else None)
        s['q'] = q
    fade = w.g(FADE_G)
    s['fade'] = w.q(fade + 0x80) if fade else 'no obj'
    wcm = w.wcm()
    local = w.q(wcm + 0x1A8) if wcm else None
    s['pl'] = [player(w, e, local) for e in w.players()]
    s['fk'] = final_kills.snap(w)
    # placement: phase entries par+0x33D0 (0x60 each, count par+0x3858): +0 player no, +0x10 rank (0xFF none),
    # +0x28 points, +0x40..+0x43 stage/reason/flag/done; result rows par+0x3968 (0x190, count par+0x45F0):
    # +0 no, +0x10 state word, +0x20 rank, s16 +0x80 Virtue; queues: 0xBC par+0x3910, out deque par+0x38D0
    ent, rows = [], []
    if par:
        n = w.q(par + 0x3858)
        for i in range(min(n or 0, 12)):
            e = w.rd(par + 0x33D0 + 0x60 * i, 0x60)
            if e:
                ent.append((struct.unpack_from('<I', e, 0)[0], struct.unpack_from('<I', e, 0x10)[0],
                            struct.unpack_from('<I', e, 0x28)[0], e[0x40:0x44].hex()))
        n = w.q(par + 0x45F0)
        for i in range(min(n or 0, 8)):
            r = w.rd(par + 0x3968 + 0x190 * i, 0x90)
            if r:
                rows.append((struct.unpack_from('<I', r, 0)[0], struct.unpack_from('<I', r, 0x20)[0],
                             struct.unpack_from('<I', r, 0x10)[0], struct.unpack_from('<h', r, 0x80)[0]))
        s['bcq'], s['outq'], s['spect'] = w.q(par + 0x3910), w.q(par + 0x38D0), w.b(par + 0x164)
    s['ent'], s['rows'] = ent, rows
    return s


def verdict(s, p):
    """[I] reading of one player's state on one game (lives_stuck_notes.md section 4)."""
    if p['stage'] and p['stage'].startswith('04'):
        return 'ELIMINATED'
    dead = p['master'] is not None and p['master'] <= 0 if p['local'] else (p['hp'] is not None and p['hp'] <= 0)
    if not dead:
        return 'alive'
    queued = any(e and e[0] == p['no'] for e in s.get('q', []))
    if p['rsp']:
        if queued:
            return 'dead, respawn queued' + (' (fade wait)' if p['local'] and s['fade'] not in (0, None, 'no obj') else '')
        return 'STUCK: rsp set, no queue entry (warp dropped / not revived)'
    if not p['listable'] and not p['local'] and s['role'] == 0:
        return 'STUCK on host: collector skips it (net byte has no dead bit / rsp / stage) - no real death'
    if p['flag']:
        return 'dead, flag set, waiting for 0xC9' if p['local'] else 'dead, flag set (host lists it next frame)'
    return 'dead, no flag, rsp 0' + (' (stock %s)' % p['stock'])


def line(w, s):
    out = ['%s: role %s mode %s bda %s C %s %s active %s points %s queue %s %s fade %s' % (
        w.who, s['role'], s.get('mode'), s.get('bda'), w.rel(s.get('C')), s.get('vt'), s.get('active'),
        s.get('points'), s.get('qn'), s.get('q'),
        w.rel(s['fade']) if isinstance(s['fade'], int) else s['fade'])]
    for p in s['pl']:
        out.append('   no %s%s stock %s stage %s flag %s rsp %s net %s pend %s b8 %s out %s hp %s/%s '
                   'dead-bit-ok %s LISTABLE %s -> %s' % (
            p['no'], '*' if p['local'] else ' ', p['stock'], p['stage'], p['flag'], p['rsp'],
            None if p['net'] is None else '%02x' % p['net'], p['pend'], p['b8'], p['out'], p['master'], p['hp'],
            p['dead_ok'], p['listable'], verdict(s, p)))
    out.append('   entries (no, rank, points, stage) %s | rows (no, rank, state, virtue) %s | 0xBC queue %s '
               'out deque %s spect164 %s' % (s['ent'], s['rows'], s.get('bcq'), s.get('outq'), s.get('spect')))
    out.append('   ' + final_kills.line(w, s['fk']))
    return '\n'.join(out)


def main():
    ws = [W(g) for g in sys.argv[1]]
    verb = sys.argv[2] if len(sys.argv) > 2 else 'show'
    secs = float(sys.argv[3]) if verb == 'watch' and len(sys.argv) > 3 else 0
    t0 = time.time()
    while True:
        print('--- %.1f s' % (time.time() - t0))
        for w in ws:
            print(line(w, snap(w)), flush=True)
        if time.time() - t0 >= secs:
            break
        time.sleep(1.0)
    for w in ws:
        w.report_missing()


if __name__ == '__main__':
    main()
