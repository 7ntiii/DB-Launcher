"""TEST ONLY: Eye of Muralis, hands-free: identify (third eye + lock-on), then a REAL kill, Virtue before / after.
Notes: diag/net/sigil15_notes.md section 2 + 6, sigil11 / sigil12 notes. Run from the workspace root, Phase I+.

HUB (by hand, before the match; pick_sigil.py is not used):
  INQ game: Minus, R (Bloodsworn Selection), 2nd column = 600010 Bloodhand Jan, Down to the SIGIL row, A
            (Eye of Muralis, skill 1010020, quest 200). Close the first-time popup with Plus.
  HER game: any Bloodsworn WITHOUT a sigil (the default row is fine). With two players the host's selector makes
            the only non-bearer the Heretic (quest 205, slot 2).
  Then L, and Y on both games at once. In the match, `python diag/twin/sigils.py AB` should show B's EYE
  "WAIT: Heretic listed" and A's "HERETIC p<A> ... p<B> ...: WAIT". This tool re-checks that and refuses otherwise.

python diag/twin/heretic_test.py INQ HER [mode=heretic] [pre=0] [then=0] [dir=315] [secs=120] [force=1] [dry]
  mode=heretic   (b) the Heretic's own reward: identify, then the HERETIC kills the Inquisitor
                     PASS = p<HER> +5 on HER's game (row 2050, once), p<INQ> +0
  mode=inquisitor (a) the proven control: identify, then the INQUISITOR kills the Heretic
                     PASS = p<INQ> +5 on INQ's game (row 2000)
  pre=1          before identifying: the Heretic kills the Inquisitor (control: must pay NOTHING, the bit is not
                 set yet). Costs the Inquisitor a life (two lives: with mode=heretic he dies twice).
  then=1         after the main kill, the OTHER player kills once more (after-check, expected +0 for everybody:
                 the first decisive kill ends the 205 module [I strong]). Costs one more life.
  dir=315        emote wheel direction of 22160 (proven), secs = per-kill time limit, force=1 skips the start
                 check, dry = start check + Virtue only, no input, no write.
Outcomes in ONE match: only one of (a) / (b). The first decisive kill (either side) clears the Heretic's 205
module, so the other outcome needs a FRESH match. pre=1 (kill before identification) fits in front of either.

ALL MEMORY WRITES: only the ATTACKER's own player on the attacker's own game (world_lib.W.goto): physics
  [WCM+0x30 entry 0 +0x28] + 0x70 (12 bytes x y z) and + 0x64 (4 bytes yaw): a stand-off spot 1.4 m (identify) /
  1.5 m (fight) from the victim's copy on that game, at the victim's height, facing him. Re-written every 4 presses
  (the victim moves). No HP write, no write on the victim's game, no flag write.
INPUT: INQ: the emote sequence of emote.py (Plus held, right stick DIR, A), StickR (lock-on) only when the lock
  tracker SQM+0xB8 does not hold the victim, R presses (5 frames down, 25 up; killchr.py's attack).
READS: modules (sigils._love_logic_of with the Eye / Heretic vtables): team masks +0x38, state +0x18, condition
  lists; third eye (sigils._third_eye); SIGIL12_EYE words; HP [[chr+0x2470]+0x18]+0x290 of the victim's OWN chr
  on his own game; Virtue of both players on both games as virtue.py: own player = box total main+0x492AFF8, others = banked
  pgd+0x42C8 (the assist mirror).
Exit 0 every outcome run PASS / 1 a FAIL / 2 start check or setup failed."""
import math
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402
import tctl  # noqa: E402
import sigils  # noqa: E402
import emote  # noqa: E402
import love_accept as LA  # noqa: E402

VT_EYE, VT_HER = sigils.VT_EYE, sigils.VT_HERETIC
WRITES = []
RESULTS = []


# ------------------------------------------------------------------ readers
def own_no(w):
    p = LA.pgd_local(w)
    return w.i(p + 0xD0) if p else None


def team_of(w, no):
    return next((t for n, t in sigils._chr_by_handle(w).values() if n == no), None)


def module(w, no, vt):
    """(module, logic, mask, state, listed player nos) of player `no`'s Eye / Heretic module on game w"""
    mm, lg = sigils._love_logic_of(w, no, vt)
    if not mm:
        return None
    holder = w.q(mm + 0x20) or w.q(mm + 0x28)
    root = w.q(holder + 0x18) if holder else None
    cond = (w.q(root + 0x90) or w.q(root + 0x98)) if root else None
    n = (w.q(cond + 0x58) or 0) if cond else 0
    hmap = sigils._chr_by_handle(w)
    nos = [hmap.get((w.d(cond + 0x10 + 4 * k) or 0) & 0xFFFF, (None, None))[0] for k in range(min(n, 16))]
    return {'m': mm, 'lg': lg, 'mask': (w.q(mm + 0x38) or 0) & 0xFFF, 'state': w.i(mm + 0x18), 'list': nos}


def bit(mask, team):
    return team is not None and 0 <= team <= 0xB and (mask >> team) & 1


def hp_own(w):
    c = w.me()[0]
    return w.chr_hp(c) if c else None


def lock_no(w):
    sqm = w.g(sigils.SQM_G)
    return w.i(sqm + 0xB8) if sqm else None


BOX_G = 0x492AFF8          # virtue_live.py VIRTUE_PUB box: u32 own total, u32 publish count (virtue.py "box total")


def totals(games):
    """{game: {player no: total}} as virtue.py reads it: the OWN player = the box total main+0x492AFF8 (the own
    pgd's banked / counters are not the live total: counters can read 0xFFFFFFFF), every other player = banked
    s16 pgd+0x42C8 (the assist mirrors the owner's live total there)."""
    out = {}
    for name, w in games:
        me = own_no(w)
        v = {no: (x[0] or 0) for no, x in LA.virtue(w).items()}
        box = w.d(w.base + BOX_G)
        if me is not None and box is not None:
            v[me] = box
        out[name] = v
    return out


def print_totals(tag, games):
    t = totals(games)
    for name, _ in games:
        print('%s Virtue on %s: %s (own = box total, others = banked)' % (
            tag, name, ' | '.join('p%s %s' % (no, t[name][no]) for no in sorted(t[name])) or 'none'))
    return t


def change(a, b):
    return (b or 0) - (a or 0)


def state_line(ctx):
    wi, wh, inq, her = ctx['wi'], ctx['wh'], ctx['inq'], ctx['her']
    e = module(wi, inq, VT_EYE)
    h = module(wh, her, VT_HER)
    ti, th = team_of(wh, inq), team_of(wi, her)
    return ('Eye p%s on %s: %s | Heretic p%s on %s: %s' % (
        inq, ctx['I'], 'gone' if not e else 'mask 0x%X (Heretic team %s bit %s) list %s state %s' % (
            e['mask'], th, bit(e['mask'], th), e['list'], e['state']),
        her, ctx['H'], 'gone (cleared)' if not h else 'mask 0x%X (Inquisitor team %s bit %s) list %s state %s' % (
            h['mask'], ti, bit(h['mask'], ti), h['list'], h['state'])))


# ------------------------------------------------------------------ actions
def approach(wa, who, victim_no, dist, lock=True):
    """attacker: stand `dist` m from the victim's copy on the attacker's game, at its height, facing it"""
    c = sigils._module_chr(wa, victim_no)
    tp = wa.chr_pos(c) if c else None
    here = wa.me()[2]
    if not tp or not here or not all(map(math.isfinite, tp)) or not all(map(math.isfinite, here)):
        print('%s: victim p%s copy / own position unreadable' % (who, victim_no))
        return False
    yaw = math.atan2(tp[0] - here[0], tp[2] - here[2]) if math.dist(here, tp) > 0.01 else 0.0
    spot = (tp[0] - dist * math.sin(yaw), tp[1], tp[2] - dist * math.cos(yaw))
    wa.goto(spot, yaw)
    WRITES.append('%s own pos (%.2f %.2f %.2f) yaw %.2f' % (who, spot[0], spot[1], spot[2], yaw))
    time.sleep(0.3)
    if lock and lock_no(wa) != victim_no:
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4},
                                                                          {'frames': 10}]}})
    return True


def kill(ctx, att, vic, label):
    """killchr.py's attack by `att` on `vic` until vic's own HP <= 0 (real hits). True when he died."""
    A, V = ctx['names'][att], ctx['names'][vic]
    wa, wv = ctx['w'][att], ctx['w'][vic]
    vno = ctx['no'][vic]
    print('-- %s: %s (p%s) attacks %s (p%s), victim HP %s' % (label, A, ctx['no'][att], V, vno, hp_own(wv)))
    t0, n = time.time(), 0
    if not approach(wa, A, vno, 1.5):
        return False
    while time.time() - t0 < ctx['secs']:
        if n and n % 4 == 0:
            approach(wa, A, vno, 1.5)
        tctl.call(A, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['R'], 'frames': 5},
                                                                        {'frames': 25}]}})
        n += 1
        hv, ha = hp_own(wv), hp_own(wa)
        print('%5.1f s press %d: victim HP %s (own game) | attacker HP %s | lock p%s' % (
            time.time() - t0, n, hv, ha, lock_no(wa)), flush=True)
        if ha is not None and ha <= 0:
            print('%s: the attacker died: abort' % A)
            return False
        if hv is not None and hv <= 0:
            print('%s: victim dead after %d presses' % (label, n))
            return True
    print('%s: time limit (%.0f s), victim alive' % (label, ctx['secs']))
    return False


def wait_alive(w, who, secs=60):
    t0 = time.time()
    while time.time() - t0 < secs:
        h = hp_own(w)
        if h is not None and h > 0:
            return True
        time.sleep(1.0)
    print('%s: still not alive after %d s' % (who, secs))
    return False


def identify(ctx):
    wi, wh, I = ctx['wi'], ctx['wh'], ctx['I']
    inq, her = ctx['inq'], ctx['her']
    print('-- identify: %s plays 22160 dir %d; on "third eye ACTIVE" it locks on to p%s' % (I, ctx['dir'], her))
    steps, _ = emote.build('hold', 'Plus', ctx['dir'], 60)
    th = threading.Thread(target=lambda: tctl.call(I, {'method': 'input_sequence', 'params': {'steps': steps}}))
    t0 = time.time()
    th.start()
    seen = None
    while time.time() - t0 < 25:
        if sigils._third_eye(wi, wi.me()[0]):
            seen = time.time() - t0
            break
        time.sleep(0.2)
    th.join(timeout=20)
    if seen is None:
        print('identify: third eye never ACTIVE (try `emote.py %s probe 22160`)' % I)
        return False
    print('t+%.1f third eye ACTIVE: approach + lock-on' % seen)
    approach(wi, I, her, 1.4)
    ok_i = ok_h = False
    t1 = time.time()
    while time.time() - t1 < 12:
        e, h = module(wi, inq, VT_EYE), module(wh, her, VT_HER)
        ok_i = bool(e and bit(e['mask'], team_of(wi, her)))
        ok_h = bool(h and bit(h['mask'], team_of(wh, inq)))
        if ok_i and ok_h:
            break
        time.sleep(0.5)
    print('identify: lock p%s, third eye %s | %s' % (lock_no(wi), sigils._third_eye(wi, wi.me()[0]), state_line(ctx)))
    return ok_i and ok_h


def step_kill(ctx, label, att, vic, expect):
    """one kill with Virtue before / after; expect = {(game, player no): delta or (allowed deltas)}; a mirror game
    may show the owner's +5 or not yet (0); every other player must be +0"""
    games = ctx['games']
    t_b = print_totals('BEFORE ' + label, games)
    died = kill(ctx, att, vic, label)
    time.sleep(8.0)
    t_a = print_totals('AFTER  ' + label, games)
    print('  ' + state_line(ctx))
    if not died:
        RESULTS.append((label, 'FAIL', 'no kill'))
        return False
    bad, seen = [], []
    for g in t_a:
        for no in sorted(set(t_a[g]) | set(t_b.get(g, {}))):
            d = change(t_b.get(g, {}).get(no), t_a[g].get(no))
            want = expect.get((g, no), (0,))
            want = want if isinstance(want, tuple) else (want,)
            seen.append('%s p%s %+d' % (g, no, d))
            if d not in want:
                bad.append('%s p%s %+d (want %s)' % (g, no, d, ' or '.join('%+d' % x for x in want)))
    verdict = 'PASS' if not bad else 'FAIL'
    RESULTS.append((label, verdict, ', '.join(seen) + ('' if not bad else ' | wrong: ' + ', '.join(bad))))
    wait_alive(ctx['w'][vic], ctx['names'][vic])
    return not bad


# ------------------------------------------------------------------ main
def parse(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    o = {'I': argv[1], 'H': argv[2], 'mode': 'heretic', 'pre': 0, 'then': 0, 'dir': 315, 'secs': 120.0,
         'force': 0, 'dry': False}
    for a in argv[3:]:
        k, _, v = a.partition('=')
        if k == 'dry':
            o['dry'] = True
        elif k in ('pre', 'then', 'dir', 'force'):
            o[k] = int(v)
        elif k == 'secs':
            o[k] = float(v)
        elif k == 'mode' and v in ('heretic', 'inquisitor'):
            o[k] = v
        else:
            sys.exit('bad option %r' % a)
    return o


def main():
    o = parse(sys.argv)
    I, H = o['I'], o['H']
    wi, wh = W(I), W(H)
    inq, her = own_no(wi), own_no(wh)
    ctx = dict(o, wi=wi, wh=wh, inq=inq, her=her, games=[(I, wi), (H, wh)],
               w={'i': wi, 'h': wh}, names={'i': I, 'h': H}, no={'i': inq, 'h': her})
    print('Inquisitor %s: player %s | Heretic %s: player %s | mode %s pre %s then %s' % (
        I, inq, H, her, o['mode'], o['pre'], o['then']))
    # start check: the sigils.py AB pair on BOTH games
    bad = []
    for g, w in ((I, wi), (H, wh)):
        e, h = module(w, inq, VT_EYE), module(w, her, VT_HER)
        if not e:
            bad.append('%s: no Eye (quest 200) module for p%s (INQ must pick 600010 Jan WITH the sigil)' % (g, inq))
        elif g == I and her not in e['list']:
            bad.append('%s: the Eye of p%s does not list p%s (sigils.py: "WAIT: no Heretic listed")' % (g, inq, her))
        if not h:
            bad.append('%s: no Heretic (quest 205) module for p%s (HER must pick NO sigil; selector not done)'
                       % (g, her))
        elif g == H and inq not in h['list']:
            bad.append('%s: the Heretic module of p%s does not list p%s' % (g, her, inq))
        s12 = sigils._s12_state(w)
        if s12 != 'PATCHED':
            bad.append('%s: SIGIL12_EYE %s' % (g, s12))
    e, h = module(wi, inq, VT_EYE), module(wh, her, VT_HER)
    if e and bit(e['mask'], team_of(wi, her)):
        bad.append('already identified this match: pre=1 is impossible, and (a)/(b) may be spent')
    if h and h['state'] not in (0, None):
        bad.append('the Heretic module is decided already (state %s): fresh match needed' % h['state'])
    print('start: ' + state_line(ctx))
    if bad and not o['force']:
        print('START CHECK FAIL: ' + '; '.join(bad) + ' (force=1 to run anyway)')
        return 2
    for b in bad:
        print('warning (force): ' + b)
    print_totals('START', ctx['games'])
    if o['dry']:
        print('DRY: no input, no write')
        return 0

    if o['pre']:
        step_kill(ctx, 'pre-control (Heretic kills before identification, expect +0)', 'h', 'i', {})
    else:
        RESULTS.append(('pre-control', 'SKIP', 'pre=0'))
    if not identify(ctx):
        RESULTS.append(('identify', 'FAIL', state_line(ctx)))
        for r in RESULTS:
            print('%-60s %s  %s' % r)
        print('memory writes made: %s' % ('; '.join(WRITES) or 'none'))
        return 1
    RESULTS.append(('identify', 'PASS', 'Eye bit on %s and ARMED on %s' % (I, H)))
    if o['mode'] == 'heretic':
        step_kill(ctx, '(b) Heretic kills the identified Inquisitor, expect p%s +5' % her, 'h', 'i',
                  {(H, her): 5, (I, her): (5, 0)})
        RESULTS.append(('(a) Inquisitor kill (control)', 'SKIP', 'needs a fresh match (module decided)'))
        if o['then']:
            step_kill(ctx, 'after-check: Inquisitor kills, expect +0 (205 cleared)', 'i', 'h', {})
    else:
        step_kill(ctx, '(a) Inquisitor kills the identified Heretic, expect p%s +5' % inq, 'i', 'h',
                  {(I, inq): 5, (H, inq): (5, 0)})
        RESULTS.append(('(b) Heretic kill', 'SKIP', 'needs a fresh match (module decided)'))
        if o['then']:
            step_kill(ctx, 'after-check: Heretic kills, expect +0 (205 decided)', 'h', 'i', {})
    print()
    for r in RESULTS:
        print('RESULT %-62s %s  %s' % r)
    print('memory writes made: %s' % ('; '.join(WRITES) or 'none'))
    return 1 if any(r[1] == 'FAIL' for r in RESULTS) else 0


if __name__ == '__main__':
    sys.exit(main())
