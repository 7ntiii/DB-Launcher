"""Large Flame corpse race between the two twin games (TEST RIG ONLY; helper of runnet_flame.sh, written
2026-11-16 as static work, never run). Notes: diag/net/runnet_flame_notes.md.

python diag/twin/flamerace.py N MODE [period=45] [at=S] [gap=3.5] [games=AB] [strict=1]
  N       corpse number in this run (label only)
  MODE    same       both games press Y at the same moment (two threads, one kept-open debug connection each,
                     released by one barrier: the closest the tools allow, a few ms apart)
          ab | ba    the first game presses, the second gap s later (A then B / B then A)
  period  the simulator's stall period (LICHII_NET_SIM 4th field); the first press is timed at
          unix time % period == at (netsim_notes.md "Stall": the stall windows start at multiples of the period
          in unix time, so at=0.3 is 0.3 s into a stall, at=20 is far from one). Also used in the control run,
          so both runs press at the same phase.
Steps: the nearest usable large corpse (99281 flameL / 99282 flameL*: used 0, enabled, nobody's bit) loaded on
both games (regress_small scan_assets / same_object); A to promptcheck's STAND AT (approach.py, facing it), B at
the same distance 45 deg to one side (then -45 deg, then behind A) until promptcheck says
"first failing check: none" for both; FlameL counters (rewards.py) and Virtue (virtue.py) before; the presses;
then every second for 20 s the taken state on both games (the data taken.py shows); 6 s later the counters again.
Verdict (last line "FLAME PASS|FAIL|SKIP corpse N MODE: reason | values"):
  ab / ba  PASS = the first presser +1 FlameL, the second +0, used = 1 and the same players on both games within
           20 s of the first press. A second pay = FAIL ("double pay": the take did not reach the other game before
           its press, gap s later). The first presser not paid = SKIP (no take happened).
  same     PASS = state converged on both within 20 s, no counter rose by more than 1, and either one player paid
           or both paid with a "first-taker race" line on both games: the documented same-moment window
           (taken_share_notes "Deliberately not handled": the loser keeps a reward already given). Not converged
           = FAIL.
  strict=1 (for a build with TAKERACE, layout_notes 2.5): in `same` both paid = FAIL even with race lines, and one
           paid needs a "takerace: ... refused" line for this h on the other game (else SKIP: the fix did not act).
           Also good for `ab gap=0.1` / `ba gap=0.1` (inside the old race window: PASS needs the same refusal).
Writes: approach.py's teleport / stick / turn (the only memory write is W.goto) and the Y presses. Nothing else."""
import math
import re
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import regress_small as RS  # noqa: E402  (chdir to the workspace on import)
from dbg import Dbg  # noqa: E402
from lanlog import LAN  # noqa: E402

LARGE = {99281, 99282}


def opt(name, default):
    for a in sys.argv[3:]:
        if a.startswith(name + '='):
            return type(default)(a.split('=', 1)[1])
    return default


def say(*a):
    RS.say(*a)


def done(status, why, vals=''):
    print('FLAME %s corpse %s %s: %s | %s' % (status, N, MODE, why, vals), flush=True)
    sys.exit(0)


def stand_spot(who, ins):
    """promptcheck's button and STAND AT facing for this game (None when it gives none)"""
    _, out = RS.tool(['diag/twin/promptcheck.py', who, 'circle', '0x%x' % ins], 120, quiet=True)
    b = re.search(r'button \((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)', out)
    s = re.search(r'STAND AT \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\) FACING yaw=(-?[\d.]+) \(dir (-?[\d.]+), '
                  r'(-?[\d.]+);', out)
    if not (b and s):
        return None
    return (float(b[1]), float(b[2]), float(b[3])), (float(s[5]), float(s[6]))


def prompt_ok(who, ins):
    _, out = RS.tool(['diag/twin/promptcheck.py', who, 'circle', '0x%x' % ins], 120, quiet=True)
    m = re.search(r'first failing check: (.*)', out)
    return bool(m) and m[1].startswith('none'), (m[1].strip() if m else 'no verdict line')[:80]


def approach(who, tgt, extra, label):
    rc, _ = RS.tool(['diag/twin/approach.py', who, '%.2f' % tgt[0], '%.2f' % tgt[1], '%.2f' % tgt[2],
                     'dist=1.30'] + extra + ['shot=fr_%s' % label], 240)
    return rc == 0


def rot(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return v[0] * c - v[1] * s, v[0] * s + v[1] * c


def flamel(rs, w):
    v = RS.counter(rs, w, 'FlameL')
    return v if isinstance(v, int) else None


def lan_lines(w, handle, since):
    """dusk_lan.txt lines about this handle from `since` (HH:MM:SS) on: (sent, applied, races, refused, timeouts)"""
    sent = applied = races = refused = timeouts = 0
    hs = 'h=%08x' % handle
    try:
        for line in open(LAN[w], encoding='utf-8', errors='replace'):
            if line[:8] < since or hs not in line:
                continue
            if 'sent to the others' in line:
                sent += 1
            if 'from player' in line and 'applied' in line:
                applied += 1
            if 'first-taker race' in line:
                races += 1
            if line[9:].startswith('takerace: ') and 'refused' in line:
                refused += 1
            if line[9:].startswith('takerace: ') and 'no answer from the authority' in line:
                timeouts += 1
    except OSError:
        return None
    return sent, applied, races, refused, timeouts


def main():
    games = opt('games', 'AB')
    if len(games) != 2:
        done('SKIP', 'two games only')
    a, b = games[0], games[1]
    period, at, gap = opt('period', 45.0), opt('at', 20.0), opt('gap', 3.5)
    ctx = RS.Ctx(games, b, False, 1.0)
    ctx.deadline = time.time() + 560
    RS.CFG['games'] = games
    try:
        RS.settle(ctx)
    except RS.Skip as ex:
        done('SKIP', str(ex))
    rnd = RS.step_round(a)[1]
    me = RS.my_pos(a)
    slots = {w: RS.gw(w).b((RS.local_pgd(w) or 0) + 0x104) for w in games}
    cands = []
    for ob in RS.scan_assets(a, LARGE, fresh=True):
        s = RS.asset_state(a, ob['ins'])
        if s and s['en'] == 3 and not s['off'] and not s['used'] and not s['bits'] and ob['pos']:
            cands.append((math.dist(me, ob['pos']) if me else 0, ob))
    if not cands:
        done('SKIP', 'no unused large Flame corpse (99281 / 99282) loaded on %s in round %s' % (a, rnd))
    cands.sort(key=lambda t: t[0])
    obj = None
    for _, ob in cands[:4]:
        peer = RS.same_object(ctx, a, ob, b)
        if peer:
            obj = ob
            break
    if not obj:
        done('SKIP', 'the nearest corpses are not found on %s by handle' % b)
    ins = {a: obj['ins'], b: peer['ins']}
    say('corpse %s: asset %d h=%08x at %s, round %s, ins %s' % (N, obj['aid'], obj['h'], RS.fmt3(obj['pos']), rnd,
                                                               {w: hex(v) for w, v in ins.items()}))
    # both players at the prompt
    sp = stand_spot(a, ins[a])
    if not sp:
        done('SKIP', 'promptcheck gave no STAND AT for %s' % a)
    tgt, face = sp
    back = (-face[0], -face[1])
    RS.tp(ctx, a, (tgt[0], tgt[1] + 0.5, tgt[2]))
    time.sleep(1.5)
    approach(a, tgt, ['facing=%.3f,%.3f' % face], 'A%s' % N)
    pa = prompt_ok(a, ins[a])
    pb, how_b = (False, ''), ''
    for deg in (45, -45, 0):
        v = rot(back, deg)
        extra = ['from=%.3f,%.3f' % v] if deg else ['facing=%.3f,%.3f' % face]
        if deg == 0:
            tgt_b = (tgt[0] - 0.6 * face[0], tgt[1], tgt[2] - 0.6 * face[1])   # behind A
        else:
            tgt_b = tgt
        approach(b, tgt_b, extra, 'B%s' % N)
        pb = prompt_ok(b, ins[b])
        how_b = 'side %+d deg' % deg if deg else 'behind A'
        if pb[0]:
            break
    pa = prompt_ok(a, ins[a])                  # again: B may have pushed A
    if not (pa[0] and pb[0]):
        done('SKIP', 'no prompt for both players (A: %s; B %s: %s): not a race' % (pa[1], how_b, pb[1]))
    rs0, v0 = RS.rewards_state(games), RS.virtue_totals(games)
    c0 = {w: flamel(rs0, w) for w in games}
    # the presses, timed against the simulator's stall phase
    dbg = {w: Dbg(w) for w in games}
    t_wait = time.time()
    while abs((time.time() - at) % period) > 0.05 and time.time() - t_wait < period + 2:
        time.sleep(0.01)
    first, second = (a, b) if MODE in ('same', 'ab') else (b, a)
    seq = {'steps': [{'buttons': ['Y'], 'frames': 10}, {'frames': 30}]}
    pressed, bar = {}, threading.Barrier(2)

    def press(w, delay):
        bar.wait(5)
        if delay:
            time.sleep(delay)
        pressed[w] = time.time()
        try:
            dbg[w].call('input_sequence', seq)
        except Exception as ex:
            pressed[w + '_err'] = str(ex)

    th = [threading.Thread(target=press, args=(first, 0.0)),
          threading.Thread(target=press, args=(second, 0.0 if MODE == 'same' else gap))]
    since = time.strftime('%H:%M:%S')
    for t in th:
        t.start()
    for t in th:
        t.join(30)
    t1 = min(v for k, v in pressed.items() if not k.endswith('_err'))
    phase = (t1 % period)
    say('presses %s (unix %% %.0f of the first: %.2f s: %s)' % (
        {k: ('%.3f' % (v - t1) if isinstance(v, float) else v) for k, v in pressed.items()}, period, phase,
        'inside the stall window' if phase < 2.0 else 'outside the stall window'))
    # taken state on both games, every second for 20 s
    conv, st = None, {}
    while time.time() - t1 < 20:
        st = {w: RS.asset_state(w, ins[w]) for w in games}
        if all(s and s['used'] == 1 for s in st.values()) and \
                len(set(tuple(sorted(s['players'] or [])) for s in st.values())) == 1:
            conv = time.time() - t1
            break
        time.sleep(1.0)
    time.sleep(6.0)
    st = {w: RS.asset_state(w, ins[w]) for w in games}
    rs1, v1 = RS.rewards_state(games), RS.virtue_totals(games)
    c1 = {w: flamel(rs1, w) for w in games}
    d = {w: (c1[w] - c0[w]) if c1[w] is not None and c0[w] is not None else None for w in games}
    _, tk = RS.tool(['diag/twin/taken.py', games], 150, quiet=True)
    tk_diff = next((ln.strip() for ln in tk.splitlines() if 'rows that differ' in ln), 'taken.py: no summary line')
    ll = {w: lan_lines(w, obj['h'], since) for w in games}
    vals = ('h=%08x round %s | FlameL +%s | taken %s | converged %s | %s | dusk_lan (sent / applied / '
            'first-taker race lines) %s | press phase %.2f s | Virtue before %s after %s | B stood %s') % (
        obj['h'], rnd, d, {w: RS.stext(s) for w, s in st.items()},
        '%.0f s' % conv if conv is not None else 'NO (20 s)', tk_diff, ll, phase, RS.vtext(v0), RS.vtext(v1), how_b)
    if any(v is None for v in d.values()):
        done('SKIP', 'FlameL counter unreadable', vals)
    if any(v > 1 for v in d.values()):
        done('FAIL', 'a FlameL counter rose by more than 1', vals)
    if conv is None:
        done('FAIL', 'the taken state did not agree on both games within 20 s', vals)
    paid = [w for w in games if d[w] == 1]
    strict = opt('strict', 0) == 1
    if strict:
        if not paid:
            done('SKIP', 'nobody was paid (no take happened)', vals)
        if len(paid) == 2:
            done('FAIL', 'DOUBLE PAY with TAKERACE (strict): both paid, the authority did not refuse one', vals)
        loser = [w for w in games if w not in paid][0]
        if not (ll[loser] and ll[loser][3]):
            done('SKIP', '%s was paid alone, but %s has no "takerace: ... refused" line for this h (the second '
                         'press came too late, or TAKERACE is not in this build)' % (paid[0], loser), vals)
        done('PASS', 'strict: %s paid once, %s refused by the authority, state equal on both after %.0f s' % (
            paid[0], loser, conv), vals)
    if MODE == 'same':
        if not paid:
            done('SKIP', 'nobody was paid (no take happened)', vals)
        if len(paid) == 1:
            done('PASS', 'same moment: one player paid (%s), state equal on both after %.0f s' % (paid[0], conv), vals)
        races = [w for w in games if ll[w] and ll[w][2]]
        if len(races) == 2:
            done('PASS', 'same moment: both paid inside the documented race window, "first-taker race" on both, '
                         'state equal after %.0f s' % conv, vals)
        done('FAIL', 'both paid but the first-taker race is not logged on both games (%s)' % races, vals)
    if d[first] != 1:
        done('SKIP', 'the first presser (%s) was not paid: no take happened' % first, vals)
    if d[second]:
        done('FAIL', 'DOUBLE PAY: %s was paid %.1f s after %s\'s take' % (second, gap, first), vals)
    done('PASS', '%s paid once, %s nothing %.1f s later, state equal on both after %.0f s' % (first, second, gap, conv),
         vals)


if __name__ == '__main__':
    N = sys.argv[1] if len(sys.argv) > 1 else '?'
    MODE = sys.argv[2] if len(sys.argv) > 2 else ''
    if MODE not in ('same', 'ab', 'ba'):
        print(__doc__)
        sys.exit(1)
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        done('SKIP', 'tool error: %s: %s' % (type(ex).__name__, ex))
