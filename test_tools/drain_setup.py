"""TEST ONLY - NEVER SHIP. Make one ordinary enemy a safe drain practice target for a real player (live 3-player tests).
python diag/twin/pkgtest.py run diag/twin/drain_setup.py auto NO [secs=180] [chr=ADDR] [gauge=1] [gset=0.5] [maxhp=3000]

  auto     A and B are both read; the enemy is held on the rig game that DRIVES it (owner flag >= 0)
  NO       player number (e.g. 2 = the laptop); the driven enemy nearest to that player is picked
  secs     how long to hold (max 900); every hold is cleared on every exit (end, Ctrl+C, error)
  chr=     use this chr (hex) instead of the nearest one (still fully validated)
  gauge=0  do not write the stagger gauge (only AI hold + HP top-up)
  gset     the gauge value written ("the next counted hit breaks it"); default 0.5

Per 0.25 s, on the driving game only, after re-validating the chr (enemy vtable main+0x572B108, entry [chr+0x18]
points back, entry flags 5, data module +8 == chr, not kin / Bloodsac / Trespasser, 1 <= max HP <= maxhp, alive,
owner flag >= 0 re-read):
 (1) passive: byte [[chr+0x2470]]+0x14CD bit 0x80 (this chr's "no AI update", gate 0xDA6508, crystal_test AI_BYTE)
     set; restored to its old value at the end;
 (2) alive: HP i32 [[chr+0x2470]+0x18]+0x290 set to max (+0x294) when below 60 %;
 (3) stagger brink: gauge module [[chr+0x2470]+0xC0] (drain2_notes: max f32 +0x10, current f32 +0x14 counts down,
     hit timer f32 +0x18, lock i32 +0x20; hit function 0xDE3AFC). Current is set to gset ONLY when the gauge is idle
     (timer <= 0, lock <= 0, 0 < max <= 2000, current finite in (gset, max]), so a stagger window is never touched
     and the gauge re-arms by itself after each stagger. LIMIT (drain2_notes, live): a hit counts only if its attack's
     slot byte is 8; in the last runs R / ZR / ZL / L never lowered the gauge, so the brink may not give a stagger.
Status every 5 s: hp, AI bit, gauge max/cur/timer, STAGGERED? (cur back at max with timer > 1.5 s after a write),
drain-ready, and friendly-group slots (a drink puts the drinker's slot there).
Exit 0 = held to the end, 1 = target lost / refused mid-way, 2 = refused at start."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, ENEMY_VT  # noqa: E402
import npcs  # noqa: E402
from strike import target, sync_map, kin_map, own_now, fg_slots  # noqa: E402
from starfrag import player_positions  # noqa: E402

AI_BYTE, AI_BIT = 0x14CD, 0x80
SA_SLOT = 0xC0
TRES_MGR = 0x5B3CD90
LIMIT = 20000.0


def ok3(p):
    return (p is not None and len(p) == 3 and all(isinstance(v, float) and math.isfinite(v) and abs(v) < LIMIT
                                                  for v in p))


def fin(v, lo=-1e6, hi=1e6):
    return isinstance(v, float) and math.isfinite(v) and lo <= v <= hi


def opts(argv):
    o = {'secs': 180.0, 'chr': None, 'gauge': 1, 'gset': 0.5, 'maxhp': 3000}
    pos = []
    for a in argv:
        k, eq, v = a.partition('=')
        if not eq:
            pos.append(a)
        elif k == 'chr':
            o['chr'] = int(v, 16)
        elif k in ('gauge', 'maxhp'):
            o[k] = int(v)
        elif k in ('secs', 'gset'):
            o[k] = float(v)
        else:
            raise SystemExit('unknown option %s' % a)
    o['secs'] = max(5.0, min(o['secs'], 900.0))
    if not (0.0 < o['gset'] <= 5.0):
        raise SystemExit('gset must be in (0, 5]')
    return pos, o


def tres_keys(w):
    keys = set()
    m = w.g(TRES_MGR)
    lo, hi = (w.q(m + 8), w.q(m + 0x10)) if m else (None, None)
    if lo and hi and lo <= hi and (hi - lo) // 8 <= 64:
        for a in range(lo, hi, 8):
            ins = w.q(a)
            iid = w.d(ins + 0xC0) if ins else None
            if iid:
                keys.add(iid >> 16)
    return keys


def chr_key(w, c):
    p = w.q(c + 0x20)
    v = w.d(p + 0x78) if p else None
    return None if v is None else v & 0xFFFF


def check(w, c, o, tk=None):
    """(view, None) when chr c may be written on game w now, else (view or None, reason)"""
    t = target(w, c, 'auto', sm=sync_map(w), km=kin_map(w))
    if t is None:
        return None, 'not a chr any more (data module +8 != chr)'
    why = []
    if t['vt'] != w.base + ENEMY_VT:
        why.append('not the enemy class')
    if not t['entry_ok']:
        why.append('entry does not point back')
    elif t['eflags'] != 5:
        why.append('entry flags %s' % t['eflags'])
    if t['kin'] is not None:
        why.append('kin')
    if t['sac']:
        why.append('Bloodsac')
    if t['gone'] or t['hp'] is None or t['hp'] < 1:
        why.append('dead / no HP (%s)' % t['hp'])
    if t['max'] is None or not (1 <= t['max'] <= o['maxhp']) or (t['hp'] or 0) > t['max']:
        why.append('HP %s / %s outside 1..maxhp %d' % (t['hp'], t['max'], o['maxhp']))
    if not ok3(t['pos_e']):
        why.append('position not valid')
    own = own_now(w, t['own_addr']) if t['own_addr'] else None
    if own is None:
        why.append('no owner flag')
    elif own < 0:
        why.append('driven by another game (owner flag %d)' % own)
    k = chr_key(w, c)
    if k is not None and k in (tres_keys(w) if tk is None else tk):
        why.append('Trespasser')
    return t, '; '.join(why) or None


def gauge(w, c):
    bag = w.q(c + 0x2470)
    sa = w.q(bag + SA_SLOT) if bag else None
    r = w.rd(sa + 0x10, 0x14) if sa else None
    if not r or len(r) < 0x14:
        return None
    mx, cur, tm = struct.unpack_from('<3f', r, 0)
    lock = struct.unpack_from('<i', r, 0x10)[0]
    return {'sa': sa, 'max': mx, 'cur': cur, 'timer': tm, 'lock': lock}


def gstr(g):
    if not g:
        return 'gauge unreadable'
    return 'gauge %.1f/%.1f timer %.2f lock %d' % (g['cur'], g['max'], g['timer'], g['lock'])


def pick(o, no):
    best = None
    for gname in ('A', 'B'):
        w = W(gname)
        tp = player_positions(w).get(no)
        if not ok3(tp):
            print('%s: no valid position for player %s' % (gname, no))
            continue
        tk = tres_keys(w)
        chrs = [o['chr']] if o['chr'] else [r['chr'] for r in npcs.find(w.m)]
        for c in chrs:
            t, why = check(w, c, o, tk)
            if o['chr']:
                print('%s: chr %x: %s' % (gname, c, why or 'usable (driven here)'))
            if why is None:
                d = math.dist(tp, t['pos_e'])
                if best is None or d < best[0]:
                    best = (d, w, t)
    return best


def main():
    pos, o = opts(sys.argv[1:])
    if len(pos) < 2 or pos[0] != 'auto':
        print(__doc__)
        return 2
    no = int(pos[1])
    best = pick(o, no)
    if best is None:
        print('REFUSED: no usable enemy driven by A or B%s; nothing written' % (
            ' (chr=%x)' % o['chr'] if o['chr'] else ''))
        return 2
    d, w, t = best
    c = t['chr']
    bag = w.q(c + 0x2470)
    m0 = w.q(bag) if bag else None
    old = w.b(m0 + AI_BYTE) if m0 else None
    if old is None:
        print('REFUSED: [[chr+0x2470]]+0x%X unreadable; nothing written' % AI_BYTE)
        return 2
    g0 = gauge(w, c)
    gauge_on = bool(o['gauge'])
    if gauge_on and not (g0 and fin(g0['max'], 0.001, 2000.0) and fin(g0['cur'], -1.0, 2000.0)
                         and fin(g0['timer'], -100.0, 100.0) and -100000 <= g0['lock'] <= 100000):
        print('gauge NOT written (field not plausible: %s): only AI hold + HP top-up' % gstr(g0))
        gauge_on = False
    print('%s drives chr %x handle %04x hp %s/%s at %.1f m from player %s; AI byte %02x; %s; holding %.0f s' % (
        w.who, c, t['handle'] or 0, t['hp'], t['max'], d, no, old, gstr(g0), o['secs']), flush=True)
    t_end, t_next = time.time() + o['secs'], 0.0
    code, wrote_gauge, stag, heals, gw = 0, None, 0, 0, 0
    try:
        while time.time() < t_end:
            t, why = check(w, c, o)
            if why is not None:
                print('STOP: chr %x %s; no more writes' % (c, why), flush=True)
                code = 1
                break
            if w.q(w.q(c + 0x2470)) != m0:
                print('STOP: AI module of %x changed; no more writes' % c, flush=True)
                code = 1
                break
            b = w.b(m0 + AI_BYTE)
            if b is not None and not b & AI_BIT:
                w.write(m0 + AI_BYTE, bytes([b | AI_BIT]))
            if t['hp'] < 0.6 * t['max']:
                w.write(t['dmod'] + 0x290, struct.pack('<i', t['max']))
                heals += 1
            g = gauge(w, c) if gauge_on else None
            if gauge_on and g and fin(g['max'], 0.001, 2000.0) and fin(g['cur'], -1.0, 2000.0) \
                    and fin(g['timer'], -100.0, 100.0):
                if wrote_gauge and g['cur'] >= g['max'] - 0.01 and g['timer'] > 1.5:
                    stag += 1
                    print('STAGGERED: gauge broke (cur %.1f = max, timer %.2f): press R now to drink' % (
                        g['cur'], g['timer']), flush=True)
                    wrote_gauge = None
                elif g['timer'] <= 0.0 and g['lock'] <= 0 and o['gset'] < g['cur'] <= g['max']:
                    if g['sa'] == gauge(w, c)['sa']:
                        w.write(g['sa'] + 0x14, struct.pack('<f', o['gset']))
                        wrote_gauge = time.time()
                        gw += 1
            if time.time() >= t_next:
                t_next = time.time() + 5.0
                g = gauge(w, c)
                ready = bool(g and fin(g['cur']) and fin(g['timer']) and g['cur'] >= g['max'] - 0.01
                             and g['timer'] > 1.5)
                b = w.b(m0 + AI_BYTE)
                print('%3.0f s left: hp %s/%s (top-ups %d)  AI hold %s  %s  brink %s  staggers %d  drain-ready %s  '
                      'friendly slots %s' % (
                          t_end - time.time(), t['hp'], t['max'], heals, 'on' if b is not None and b & AI_BIT
                          else 'OFF', gstr(g), 'armed' if wrote_gauge else 'off' if not gauge_on else 'waiting',
                          stag, 'YES' if ready else 'no', sorted(fg_slots(w, c) or [])), flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print('Ctrl+C: clearing')
    finally:
        try:
            m_now = w.q(w.q(c + 0x2470) + 0) if w.q(c + 0x2470) else None
            b = w.b(m0 + AI_BYTE) if m_now == m0 else None
            if b is not None:
                w.write(m0 + AI_BYTE, bytes([(b & ~AI_BIT) | (old & AI_BIT)]))
                print('AI byte restored (%02x -> %02x)' % (b, w.b(m0 + AI_BYTE) or 0))
            else:
                print('AI byte not restored: module changed / chr gone (a reset clears the bit anyway)')
        except Exception as e:  # noqa: BLE001
            print('AI byte restore FAILED: %r: check python diag/twin/mem.py %s r8 0x%x' % (e, w.who, m0 + AI_BYTE))
    print('RESULT drain_setup %s: chr %x on %s, %d HP top-ups, %d gauge writes, %d staggers seen' % (
        'PASS' if code == 0 else 'STOPPED', c, w.who, heals, gw, stag))
    return code


if __name__ == '__main__':
    sys.exit(main())
