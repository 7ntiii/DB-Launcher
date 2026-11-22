"""force_event.py -- TEST ONLY: make the host's NEXT environment-event draw return a chosen event.

Usage (from the workspace root):
  python diag/twin/force_event.py A show                 box, role, round/phase, current event, candidates
  python diag/twin/force_event.py A 1120 [arm] [B|BC..]  arm on host A, wait for the draw, restore, check guests
  python diag/twin/force_event.py A 1120 show            same as show (the id is ignored)
  python diag/twin/force_event.py A off                  put the stock word back by hand
Options: --timeout SECONDS (default 900), --any (allow a final id outside the final / a mid id for the final)

How (diag/net/force_event_notes.md): on the HOST only, the stock load of the draw result at main+0xEFDD48
(`ldur w0,[x29,#-4]`, B85FC3A0) becomes `movz w0,#ID` (or `movn w0,#0` for -1). The built-in record cave
(0xEFDD4C -> 0x492AED0) then puts ID into the env box (+0xC, count +0x10), the host applies ID itself and the
assist shares it over the side channel (type 3) like any real draw; the guests take it through their stock wait
path. The tool polls the box count and writes the stock word back right after the draw (also on time-out,
Ctrl+C or an error), so later rounds draw normally again.
When: arm while the host is in the phase BEFORE the one that should get the event (Phase I for Phase II), then end
that phase (clock.py 5 AB). Never run against a game that is not part of the rig.
"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

PAR_G = 0x5B3CDF8          # par / stage: +0x50 phase step, +0xB8 round, +0xD0 phase cfgs
NETP_G = 0x5B57EB8         # [[*]+0x68] +0x58/+0x60 = env-event history (u32), last = current
ENV_BOX = 0x492AFC0        # +0 id, +4 armed, +8 mode, +0xC drawn, +0x10 count, +0x14 local draw running
ROLE = 0x492AFD8           # 0 = authority (host), 1 = guest
SITE = 0xEFDD48            # ldur w0,[x29,#-4] in EnvEventLot's draw 0xEFD4A0
STOCK = 0xB85FC3A0
HOOKS = [(0xEFD604, 0x14E8B61F, 'mode switch b 0x492AE80'),
         (0xEFD63C, 0x94E8B619, 'receive bl 0x492AEA0'),
         (0xEFDD4C, 0x94E8B461, 'record bl 0x492AED0')]
PHASE_ENV_LOT, PHASE_UPDATE = 17, 6
FINAL_ROUND = 4

# id: (type, name, event flag set while active)  [V EnvEventParam regulation dump, EnvEventText_Name]
EVENTS = {
    1120: (0x0A, 'Prowling Sword Lion (zeppelin)', 9580),
    1140: (0x0C, 'Nearle Storm', 9590),
    1210: (0x1A, 'Star Fragment', 5210),
    1220: (0x1B, 'Bloodsac Gala', 5220),
    1300: (0x26, "Dusk's Toll (bell)", None),
    2000: (0x10, 'Moon Blood Bestowal (final, 3 players)', 5800),
    2002: (0x10, 'Moon Blood Bestowal (final, alliances)', 5800),
    2030: (0x10, 'final variant (no name text)', 5800),
    -1: (None, 'no event', None),
}
FINALS = (2000, 2002, 2030)


def word_for(eid):
    if eid == -1:
        return 0x12800000                    # movn w0,#0
    if not 0 <= eid <= 0xFFFF:
        raise ValueError('id does not fit movz')
    return 0x52800000 | (eid << 5)           # movz w0,#eid


class G:
    def __init__(self, who):
        self.who = who
        self.m = Mem(who)
        self.base = self.m.base

    def rd(self, a, n):
        if not a or a < 0x10000:
            return None
        try:
            b = self.m.read(a, n)
            return b if b and len(b) == n else None
        except Exception:
            return None

    def u32(self, a):
        b = self.rd(a, 4)
        return struct.unpack('<I', b)[0] if b else None

    def s32(self, a):
        b = self.rd(a, 4)
        return struct.unpack('<i', b)[0] if b else None

    def u64(self, a):
        b = self.rd(a, 8)
        return struct.unpack('<Q', b)[0] if b else None

    def par(self):
        return self.u64(self.base + PAR_G)

    def phase_round(self):
        p = self.par()
        return (self.u32(p + 0x50), self.u32(p + 0xB8)) if p else (None, None)

    def box(self):
        b = self.rd(self.base + ENV_BOX, 0x18)
        return struct.unpack('<iIIiII', b) if b else None

    def role(self):
        return self.u32(self.base + ROLE)

    def site(self):
        return self.u32(self.base + SITE)

    def put_site(self, w):
        self.m.write(self.base + SITE, struct.pack('<I', w), code=True)

    def history(self):
        n = self.u64(self.base + NETP_G)
        h = self.u64(n + 0x68) if n else None
        b0, b1 = (self.u64(h + 0x58), self.u64(h + 0x60)) if h else (None, None)
        if not b0 or b1 is None or b1 < b0 or (b1 - b0) > 4 * 64 or (b1 - b0) % 4:
            return None if b0 is None else []
        raw = self.rd(b0, b1 - b0) if b1 > b0 else b''
        return list(struct.unpack('<%di' % ((b1 - b0) // 4), raw)) if raw is not None else None

    def current(self):
        h = self.history()
        return None if h is None else (h[-1] if h else -1)

    def chance(self, rnd):
        """PhaseInfoParam +0x89 (% chance of an event) of round rnd's cfg (par+0xD0+8*(rnd-1)) [V 0x1175C24]"""
        p = self.par()
        if not p or not rnd or rnd > 9:
            return None, None
        cfg = self.u64(p + 0xD0 + 8 * (rnd - 1))
        row = self.u64(cfg + 0x10) if cfg else None
        rid = self.u32(cfg + 8) if cfg else None
        b = self.rd(row + 0x89, 1) if row else None
        return rid, (b[0] if b else None)


def name(eid):
    e = EVENTS.get(eid)
    return '%s %s' % (eid, e[1] if e else '(unknown id)')


def flag_state(g, fid):
    if fid is None:
        return '-'
    try:
        from zeppelin import R, event_flag  # same walk as promptcheck.event_flag
        v = event_flag(R(g.who), fid)
    except Exception:
        v = None
    return {True: 'ON', False: 'off', None: '?'}[v]


def site_state(w, eid=None):
    if w == STOCK:
        return 'stock (ldur w0,[x29,#-4])'
    for k in EVENTS:
        if w == word_for(k):
            return 'FORCED %s' % name(k)
    return '?' if w is None else 'other %08X' % w


def show(who):
    g = G(who)
    ph, rnd = g.phase_round()
    bx = g.box()
    role = g.role()
    print('==== game %s ====  main %#x  phase %s round %s  role %s (%s)' % (
        who, g.base, ph, rnd, role, {0: 'host/authority', 1: 'guest'}.get(role, '?')))
    if bx:
        print('env box +0 id %d  +4 armed %d  +8 mode %d (%s)  +0xC drawn %d  +0x10 count %d  +0x14 local %d' % (
            bx[0], bx[1], bx[2], 'wait for host' if bx[2] == 1 else 'draw here', bx[3], bx[4], bx[5]))
    else:
        print('env box unreadable')
    hooks = []
    for off, want, what in HOOKS:
        w = g.u32(g.base + off)
        hooks.append('%#x %s' % (off, 'ok' if w == want else ('?' if w is None else 'NOT BUILT-IN %08X' % w)))
    print('built-in env hooks: ' + ', '.join(hooks))
    print('draw site %#x: %s' % (SITE, site_state(g.site())))
    h = g.history()
    cur = g.current()
    print('current event: %s   history %s' % (name(cur) if cur is not None else '?', h))
    for r in (rnd, (rnd or 0) + 1):
        if r and r <= FINAL_ROUND:
            rid, ch = g.chance(r)
            print('  round %d phase cfg row %s: event chance %s %%' % (r, rid, ch))
    print('candidates (EnvEventParam rows; flag = the one apply 0xEFDDC4 sets while active):')
    for eid, (ty, nm, fl) in EVENTS.items():
        if eid == -1:
            continue
        print('  %5d type %#04x %-40s flag %s=%s' % (eid, ty, nm, fl if fl else '-', flag_state(g, fl)))
    return g


def guest_ok(who, eid):
    g = G(who)
    bx = g.box()
    cur = g.current()
    return bx, cur, bool(bx and bx[0] == eid and bx[1] == 0 and cur == eid)


def arm(host, eid, guests, timeout, allow_any):
    g = G(host)
    ph, rnd = g.phase_round()
    bx = g.box()
    role = g.role()
    w0 = g.site()
    if w0 is None or bx is None:
        sys.exit('%s: memory not readable (game running? debug server up?)' % host)
    if w0 != STOCK and site_state(w0).startswith('other'):
        sys.exit('%s: draw site %#x holds %08X, not the stock word: another patch? not touching it' % (host, SITE, w0))
    if role != 0 or bx[2] != 0:
        sys.exit('%s is not the drawing game (role %s, box mode %s): run it on the host (lowest player number)'
                 % (host, role, bx[2]))
    # which round will the next draw be for
    # (only known inside a match phase; in the hub / at the Outcome the round is the old match's)
    nxt = (rnd + 1) if (rnd and ph == PHASE_UPDATE) else None
    if ph == PHASE_ENV_LOT:
        print('WARNING: host is at EnvEventLot (step 17) already; the draw of round %s may be over' % rnd)
    if not allow_any and nxt:
        if eid in FINALS and nxt != FINAL_ROUND:
            sys.exit('final id %d for round %d: refused (use --any)' % (eid, nxt))
        if eid not in FINALS and eid != -1 and nxt >= FINAL_ROUND:
            sys.exit('mid event %d would replace the final arena (round %d): refused (use --any)' % (eid, nxt))
    if eid == 1300 and nxt not in (None, 2) and not allow_any:
        print('note: 1300 has phase mask 0x02 (stock: Phase II only) [I]; forcing it anyway')
    count0 = bx[4]
    g.put_site(word_for(eid))
    chk = g.site()
    if chk != word_for(eid):
        g.put_site(STOCK)
        sys.exit('%s: write did not stick (%s); restored' % (host, chk))
    print('%s armed: next draw -> %s  (now phase %s round %s, expected draw round %s, box count %d)' % (
        host, name(eid), ph, rnd, nxt, count0))
    print('end the phase now if needed (python diag/twin/clock.py 5 %s%s); waiting up to %d s' % (
        host, guests, timeout))
    t0 = time.time()
    last = None
    drawn = None
    try:
        while time.time() - t0 < timeout:
            bx = g.box()
            ph, rnd = g.phase_round()
            role = g.role()
            st = (ph, rnd, role, bx[2] if bx else None)
            if st != last:
                print('  %5.1f s  phase %s round %s role %s mode %s' % (time.time() - t0, ph, rnd, role, st[3]))
                if last and role != last[2]:
                    print('  role changed: another game may draw; the forced id will not be used there')
                last = st
            if bx and bx[4] != count0:
                drawn = (bx[3], rnd)
                break
            time.sleep(0.1)
    finally:
        try:
            g.put_site(STOCK)
            print('%s draw site restored: %s' % (host, site_state(g.site())))
        except Exception as ex:
            print('!!! RESTORE FAILED (%s): run  python diag/twin/force_event.py %s off  NOW' % (ex, host))
    if not drawn:
        print('no draw on %s within %d s (count unchanged); nothing forced' % (host, timeout))
        return 1
    print('drawn %s (round %s) on %s  -> %s' % (drawn[0], drawn[1], host,
                                                'OK' if drawn[0] == eid else 'MISMATCH: draw left through an early exit?'))
    time.sleep(0.5)
    print('%s current event: %s, history %s' % (host, name(g.current()), g.history()))
    if not guests:
        return 0 if drawn[0] == eid else 1
    pending = set(guests)
    t1 = time.time()
    while pending and time.time() - t1 < 60:
        for w in sorted(pending):
            try:
                bx, cur, ok = guest_ok(w, drawn[0])
            except Exception as ex:
                bx, cur, ok = None, None, False
                print('  %s: %s' % (w, ex))
            if ok:
                print('  %s received %s through the side channel: box id %d armed %d, current %s (%.0f s)' % (
                    w, drawn[0], bx[0], bx[1], cur, time.time() - t1))
                pending.discard(w)
        time.sleep(0.5)
    for w in sorted(pending):
        bx, cur, _ = guest_ok(w, drawn[0])
        print('  %s NOT confirmed in 60 s: box %s current %s (check its dusk_lan.txt for "from player")' % (w, bx, cur))
    return 0 if not pending and drawn[0] == eid else 1


def main():
    args = [a for a in sys.argv[1:]]
    timeout, allow_any = 900.0, False
    if '--timeout' in args:
        i = args.index('--timeout')
        timeout = float(args[i + 1])
        del args[i:i + 2]
    if '--any' in args:
        allow_any = True
        args.remove('--any')
    if not args or len(args[0]) != 1 or not args[0].isupper():
        sys.exit(__doc__)
    host = args[0]
    rest = args[1:]
    if not rest or rest[0] == 'show' or (len(rest) > 1 and rest[1] == 'show'):
        show(host)
        return 0
    if rest[0] == 'off':
        g = G(host)
        w = g.site()
        if w is not None and w != STOCK and site_state(w).startswith('other'):
            sys.exit('%s: site holds %08X (not ours): not touching it' % (host, w))
        g.put_site(STOCK)
        print('%s draw site: %s -> %s' % (host, site_state(w), site_state(g.site())))
        return 0
    eid = int(rest[0], 0)
    if eid not in EVENTS:
        sys.exit('unknown event id %d; known: %s' % (eid, ', '.join(str(k) for k in EVENTS)))
    rest = rest[1:]
    if rest and rest[0] == 'arm':
        rest = rest[1:]
    guests = ''.join(rest).replace(host, '')
    if guests and not (guests.isalpha() and guests.isupper()):
        sys.exit('guests must be letters like B or BC')
    return arm(host, eid, guests, timeout, allow_any)


if __name__ == '__main__':
    sys.exit(main())
