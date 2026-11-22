"""TEST ONLY - NEVER SHIP. Get game WHO's player (normally A = the host) a SUMMONED kin, for the live test "a guest
hits the host's kin" (the laptop player attacks it).
python diag/twin/kin_live.py A [games=AB] [tries=3] [clear=60] [radius=15] [nowait]

Why: regress_small's kin_summon failed 4 times live ("skipped, enemy within 15 m", "no STAND AT from promptcheck").
Here:
 1. already a kin? state 2 (Unsummon) -> brought out (regress_small.kin_summon_out); state 3 -> done.
 2. Every free big circle (regress_small.big_circles, round 2+) is scored by the live non-kin enemies within
    `radius` m on WHO and on the other rig game; the fewest first, then the nearest.
 3. WHO's own "no dead" bit is set for the whole run (nodeath.py mode=bit, as kin_death does) and CLEARED on exit
    (also on errors / Ctrl-C).
 4. Per circle: teleport WHO beside it, kill the enemies within `radius` m with killchr.py (real hits, nearest
    first, 10 s per call, at most `clear` s), then summon with promptcheck's STAND AT; if promptcheck gives no
    STAND AT, once more from the circle's own position (approach.py, hold Y). Wait up to 30 s for the kin.
 5. Ends with ONE line
      RESULT kin_live PASS|FAIL|SKIP: <reason> | kin chr per game | kin position
    and the line to bring WHO's player beside the laptop player: live3.py WHO bring 2.
Writes (all TEST ONLY): WHO's player position (teleports, validated), button input, WHO's no-dead bit (cleared at
the end), killchr's player moves. Never an HP or any enemy field. Run it through pkgtest.py run in the pkgtest rig."""
import math
import sys
import time

sys.path.insert(0, 'diag/twin')
import regress_small as RS  # noqa: E402   (chdirs to the workspace; its main() is not run on import)
import nodeath  # noqa: E402
from world_lib import fmt3  # noqa: E402


def opts(argv):
    o = {'who': argv[1] if len(argv) > 1 else None, 'games': None, 'tries': 3, 'clear': 60.0, 'radius': 15.0,
         'nowait': False}
    for a in argv[2:]:
        k, eq, v = a.partition('=')
        if a == 'nowait':
            o['nowait'] = True
        elif k == 'games':
            o['games'] = v
        elif k == 'tries':
            o['tries'] = int(v)
        elif k in ('clear', 'radius'):
            o[k] = float(v)
    return o


def foes_at(ctx, pos, radius):
    """live non-kin enemies within radius of pos: on the actor's game (with chr) and on the host's (count)"""
    mine = RS.near_here(ctx.actor, pos, radius)
    other = RS.enemies_near(ctx, pos, radius)
    return mine, len(mine) + sum(1 for g, _, _ in other if g != ctx.actor)


def clear_circle(ctx, a, pos, o):
    log, t0 = [], time.time()
    while time.time() - t0 < o['clear']:
        near, _ = foes_at(ctx, pos, o['radius'])
        if not near:
            break
        d, hp, c = near[0]
        rc, _ = RS.tool(['diag/twin/killchr.py', a, 'chr=%x' % c, 'seconds=10', 'every=3'], timeout=30, quiet=True)
        log.append('hit %x (HP %s, %.0f m) rc %s' % (c, hp, d, rc))
        RS.say('kin_live %s: clearing %.0f s, %d enemies within %.0f m, %s' % (a, time.time() - t0, len(near),
                                                                            o['radius'], log[-1]))
    near, n_all = foes_at(ctx, pos, o['radius'])
    return not n_all, '%s | left within %.0f m: %d' % ('; '.join(log) or 'nothing to clear', o['radius'], n_all)


def kin_line(ctx, owner):
    out = []
    for g in ctx.games:
        v = RS.kin_view(g, owner)
        out.append('%s: chr %s state %s hp %s' % (g, '%x' % v['chr'] if v['chr'] else None, v['state'], v['hp']))
    a = ctx.actor
    k = next((k for k in RS.KS.kins(RS.gw(a))[1] if k['owner'] == owner), None)
    return ' ; '.join(out), (fmt3(k['pos']) if k and k.get('pos') else '?')


def summon(ctx, a, owner, o):
    """(ok, text)"""
    v = RS.kin_view(a, owner)
    if v['kins'] and v['state'] == 3:
        return True, 'already out (state 3)'
    if v['kins'] and v['state'] == 2:
        okk, how = RS.kin_summon_out(ctx, owner)
        return okk, 'existing kin brought out: %s' % how
    if v['kins']:
        return False, 'kin in state %s (dead / waiting to revive): try again in a minute' % v['state']
    r = RS.step_round(a)[1]
    if r < 2:
        return False, 'kin circles exist from round 2 on (round %s)' % r
    me = RS.my_pos(a)
    cs = RS.big_circles(a)
    if not cs:
        return False, 'no free big summoning circle on %s' % a
    scored = []
    for c in cs:
        _, n = foes_at(ctx, c['pos'], o['radius'])
        scored.append((n, math.dist(me, c['pos']) if me else 0.0, c))
    scored.sort(key=lambda s: (s[0], s[1]))
    RS.say('kin_live %s: %d free big circles; best: %s' % (a, len(scored), ', '.join(
        '%d (%d foes, %.0f m)' % (c['aid'], n, d) for n, d, c in scored[:5])))
    log = []
    for n, d, c in scored[:o['tries']]:
        tag = 'circle %d %s (%d foes)' % (c['aid'], fmt3(c['pos']), n)
        RS.tp(ctx, a, (c['pos'][0] + 2.0, c['pos'][1] + 0.5, c['pos'][2]))
        time.sleep(1.0)
        safe, how = clear_circle(ctx, a, c['pos'], o)
        nodeath.set_nodeath(RS.gw(a), True, 'bit', quiet=True)          # re-assert (the game may clear it)
        if not safe:
            log.append('%s: not cleared (%s)' % (tag, how))
            RS.say('kin_live ' + log[-1])
            continue
        okk, h1 = RS.use_asset(ctx, a, c['ins'], 'kinlive', dist=1.5, budget=120, need_stand=True)
        if not okk and not RS.kin_view(a, owner)['kins']:
            okk, h2 = RS.use_asset(ctx, a, c['ins'], 'kinlive2', dist=1.2, budget=120, need_stand=False)
            h1 += ' || from the circle origin: ' + h2
        t0 = time.time()
        while time.time() - t0 < 30:
            v = RS.kin_view(a, owner)
            if v['kins'] and v['state'] == 3:
                return True, '%s: summoned (%s)' % (tag, h1)
            time.sleep(2.0)
            if not v['kins'] and time.time() - t0 > 6:
                RS.press(a, 'A', 5, 30)                                   # a drama line, if one is open
        log.append('%s: no kin 30 s after the press (%s)' % (tag, h1))
        RS.say('kin_live ' + log[-1])
    return False, ' | '.join(log) or 'no circle tried'


def main():
    o = opts(sys.argv)
    a = o['who']
    if a not in ('A', 'B', 'C', 'D'):
        print(__doc__)
        return 2
    games = o['games'] or RS.CFG['games']
    if a not in games:
        games = a + games
    ctx = RS.Ctx(games, a, o['nowait'], 1.0)
    ctx.deadline = time.time() + 900
    owner = RS.local_no(a)
    if owner is None:
        print('RESULT kin_live SKIP: player number of %s unreadable' % a)
        return 2
    nodeath.set_nodeath(RS.gw(a), True, 'bit', quiet=True)
    try:
        okk, how = summon(ctx, a, owner, o)
    except RS.Skip as e:
        okk, how = False, 'skip: %s' % e
    except RS.Timeout as e:
        okk, how = False, 'timeout: %s' % e
    finally:
        try:
            nodeath.set_nodeath(RS.gw(a), False, 'bit', quiet=True)
        except Exception as e:  # noqa: BLE001
            print('!! could not clear the no-dead bit on %s: %s (run nodeath.py %s off)' % (a, e, a))
    kins, kpos = kin_line(ctx, owner)
    print('RESULT kin_live %s: player %s (%s) %s | %s | kin at %s' % (
        'PASS' if okk else 'FAIL', owner, a, how, kins, kpos), flush=True)
    if okk:
        print('next: python diag/twin/pkgtest.py run diag/twin/live3.py %s bring 2   (the host beside the laptop '
              'player; the kin follows)' % a)
    return 0 if okk else 1


if __name__ == '__main__':
    sys.exit(main())
