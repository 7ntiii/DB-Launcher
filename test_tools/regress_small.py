"""Regression tests for the cheap "IN THE BUILD BUT UNTESTED" rows of diag/net/feature_status_v36.md (TEST RIG ONLY).

python diag/twin/regress_small.py GROUP|TEST [GROUP|TEST ...] [games=AB] [actor=B] [nowait] [budget=SCALE]
python diag/twin/regress_small.py list           every test, its status-table row, group and budget

Start it once both games are in Phase I with the clock held (python diag/twin/hold_clock.py AB). Groups (the lead
advances the clock between calls; every test checks the step it needs and SKIPs with the reason otherwise):
  phase1        stake_refill contested_kill flame_small flame_medium blood_crystal markers pin_place arm_1300
  phase2        lever_bell kin_levelup small_circle kin_replace kin_recall kin_death arm_1220
  site          pledge_takeover   (Phase II / III with the Ritual Site OPEN: run hold_clock.py AB 95 for it,
                                   the site opens only with under ~100 s left)
  phase3        event_gala ally_form          (ally_form needs 3+ games: 2 allied players end the match)
  intermission  start_area                    (call it right after cutting a phase; waits for the menu)
  final         alliance_end spectate         (both need 3+ games, TWIN_GAMES=ABC / games=ABC)
  not in a group (by name): arm_1210 event_star (star fragment), kin_summon (row 26, already proven)
Options: games=AB (default TWIN_GAMES or AB), actor=B (the game that acts; default the second game: a guest),
  nowait (skip the 20 s phase-age wait), budget=2 (double every time budget).

Each test prints what it does, acts with the existing twin tools (subprocesses with time-outs, or their
read-only functions), reads the state on EVERY game before and after, and ends with ONE line
  RESULT <test> <PASS|FAIL|SKIP|PARTIAL|MANUAL|SETUP> row <n>: <reason> | <values>
PARTIAL = part of the row proven (named in the reason); MANUAL = screenshots taken, judge them by eye; SETUP = an
arming step for a later group. A failing test never stops the others. A summary table follows; the RESULT lines are
also appended to diag/twin/regress_small_results.txt. Cross-call state (armed events, alliance formed) is kept in
diag/twin/regress_small_state.json.

Rules kept: no player is teleported (W.goto, approach.py, fightfoe.py) before ~20 s into a phase (phase age from the
clock when it is still below the phase length, else from this script's own observation); every loop and subprocess
has a time-out; arm_* use force_event.py, which writes the stock draw word back itself after the draw or its
--timeout. Writes this script does itself (all TEST ONLY): player teleports, button / stick input, the local player's
HP set to 0 through hp.py / final_kills.py (stake_refill, spectate), the kin's HP set to 0 (kin_death) and, only if
the menu pick fails, the documented start-area test pick (u8 3 at slot+0x10, area at +0x14; startarea_fix_notes 7).
Nothing it writes needs restoring (no param / code word stays changed). Run from anywhere (it chdirs to the workspace).
Method and handoff evidence per test: diag/net/regress_small_notes.md."""
import json
import math
import os
import re
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
os.chdir(WS)                                   # the tools use sys.path 'diag/twin' relative to the workspace
os.environ.pop('DUSK_BASE', None)              # one fixed base would be wrong for 2+ games
sys.path.insert(0, str(WS / 'diag' / 'twin'))
from world_lib import W, ENEMY_VT, fmt3  # noqa: E402
import tctl  # noqa: E402
import taken as TK  # noqa: E402          read-only helpers (slot_map, players_of)
import kinstate as KS  # noqa: E402       read-only helpers (players, kins, circles)
import force_event as FE  # noqa: E402    read-only helper G(w).current() / history()
import levers as LV  # noqa: E402         read-only helper entries(w)
import circles as CI  # noqa: E402        read-only kin pools per circle type (kin2_notes.md section 1)

PY = sys.executable
TWIN = WS / 'diag' / 'twin'
STATE_FILE = TWIN / 'regress_small_state.json'
RESULTS_FILE = TWIN / 'regress_small_results.txt'

# globals (main-relative), all [V] in the tools named
PAR_G, GDM_G, AM_G, GL_G, ITEMMAN_G = 0x5B3CDF8, 0x5B57EB8, 0x5B3CDD0, 0x5B3CDB0, 0x5B3CDC0
MEDIATOR_G, SPECTATOR_G, ROLE_B = 0x5B44EA0, 0x5B55D30, 0x492AFD8
PHASE_LEN = {1: 360, 2: 360, 3: 300, 4: 240}  # 6 / 6 / 5 / 4 minutes in this regulation (handoff 8.9n)
FLAME_S, FLAME_M = 99280, 99281
BIG_CIRCLES, SMALL_CIRCLE = (99290, 99291, 99292), 99295


# =============================================================== small helpers
class Skip(Exception):
    pass


class Timeout(Exception):
    pass


_W = {}


def gw(w):
    """cached world_lib.W per game (one debug connection per game)"""
    if w not in _W:
        _W[w] = W(w)
    return _W[w]


def drop_w(w):
    _W.pop(w, None)


def say(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def tool(args, timeout=180, quiet=False):
    """run an existing twin tool from the workspace root; (returncode or None on time-out, output text)"""
    args = [str(a) for a in args]
    if not quiet:
        say('$ python ' + ' '.join(args))
    try:
        r = subprocess.run([PY] + args, capture_output=True, text=True, timeout=max(5, timeout), cwd=WS,
                           env=dict(os.environ, TWIN_GAMES=CFG['games']))
        out = (r.stdout or '') + (('\n[stderr] ' + r.stderr.strip()) if r.stderr and r.stderr.strip() else '')
        rc = r.returncode
    except subprocess.TimeoutExpired as ex:
        out, rc = (ex.stdout or '') if isinstance(ex.stdout, str) else '', None
        out += '\n[time-out after %d s]' % timeout
    if not quiet:
        tail = out.strip().splitlines()[-12:]
        for ln in tail:
            print('    | ' + ln)
    return rc, out


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(st):
    try:
        STATE_FILE.write_text(json.dumps(st, indent=1))
    except Exception as ex:
        say('state file not written: %s' % ex)


def shot(w, name):
    out = TWIN / ('%s_%s.png' % (w, name))
    try:
        tctl.call(w, {'method': 'screenshot', 'params': {'height': 480}}, out)
    except Exception as ex:
        return 'shot failed: %s' % ex
    return str(out.relative_to(WS))


def press(w, btn, frames=6, after=20):
    tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': frames},
                                                                    {'frames': after}]}})


def stick(w, which, xy, frames, after=10):
    tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{which: [xy[0], xy[1]], 'frames': frames},
                                                                    {'frames': after}]}})


def step_round(w):
    """(step, round); (-1, 0) no stage; (-2, 0) unreadable"""
    try:
        x = gw(w)
        par = x.g(PAR_G)
        return (x.d(par + 0x50), x.d(par + 0xB8)) if par else (-1, 0)
    except Exception:
        drop_w(w)
        return (-2, 0)


def clock_left(w):
    x = gw(w)
    par = x.g(PAR_G)
    c = x.q(par + 0x120) if par else None
    return x.f(c + 8) if c else None


def states_text(games):
    return ' '.join('%s %s/%s' % (w, *step_round(w)) for w in games)


# =============================================================== the 20-second rule
_seen = {}


def settle(ctx, min_age=20.0, max_wait=75.0):
    """wait until every game is in UpdatePhase (step 6) of the same round and the phase is >= min_age s old"""
    t0 = time.time()
    while True:
        s = {w: step_round(w) for w in ctx.games}
        rnds = set(v[1] for v in s.values())
        if all(v[0] == 6 for v in s.values()) and len(rnds) == 1:
            r = rnds.pop()
            first = _seen.setdefault(r, time.time())
            ages = []
            for w in ctx.games:
                left = clock_left(w)
                if left is not None and r in PHASE_LEN and left <= PHASE_LEN[r]:
                    ages.append(PHASE_LEN[r] - left)
            age = max([time.time() - first] + ([min(ages)] if ages else []))
            if age >= min_age or (ctx.nowait and min_age <= 20):
                ctx.settled = r
                return r
            if time.time() - t0 > max_wait:
                raise Skip('phase only %.0f s old after waiting %.0f s' % (age, max_wait))
        else:
            _seen.clear()
            if time.time() - t0 > max_wait:
                raise Skip('not every game in UpdatePhase of one round: %s' % states_text(ctx.games))
        time.sleep(1.0)


def need_teleport_ok(ctx):
    r = step_round(ctx.games[0])[1]
    if ctx.settled != r:
        settle(ctx)


def tp(ctx, w, pos, yaw=None, nudge=True):
    need_teleport_ok(ctx)
    if not gw(w).goto(pos, yaw, nudge):
        raise Skip('%s: teleport failed (no local player physics)' % w)
    time.sleep(0.4)


# =============================================================== readers (null-safe, read only)
def local_pgd(w):
    x = gw(w)
    g = x.g(GDM_G)
    return x.q(g + 0x20) if g else None


def local_no(w):
    p = local_pgd(w)
    return gw(w).i(p + 0xD0) if p else None


def player_rows(w):
    x, rows = gw(w), []
    for k, e in enumerate(x.players()):
        c = e[0]
        data = x.q(c + 0x20)
        pgd = x.q(data + 0x1D0) if data else None
        rows.append({'k': k, 'chr': c, 'pgd': pgd, 'no': x.i(pgd + 0xD0) if pgd else None,
                     'fang': x.d(pgd + 0x44C8) if pgd else None, 'coll': x.d(pgd + 0x4458) if pgd else None,
                     'exp': x.d(pgd + 0x90) if pgd else None, 'lvl': x.d(pgd + 0x64) if pgd else None,
                     'pos': x.f3(e[5] + 0x70) if e[5] else None, 'hp': x.chr_hp(c)})
    return rows


def by_no(rows):
    return {r['no']: r for r in rows if r['no'] is not None}


def master_hp(w):
    x = gw(w)
    e = x.player_entry(0)
    return x.i(e[3] + 0xF30) if e and e[3] else None


def my_pos(w):
    return gw(w).me()[2]


def stake_line(w):
    x = gw(w)
    p = local_pgd(w)
    if not p:
        return None
    return {'no': x.i(p + 0xD0), 'type': x.b(p + 0x40D0), 'count': x.b(p + 0x4649), 'max': x.b(p + 0x4648),
            'base': x.b(p + 0x110), 'level': x.d(p + 0x78), 'blood': x.d(p + 0x7C)}


def sync_enemies(w):
    """{handle: {chr, own (>= 0: this game drives it), phys}} from the chr sync sets WCM+0x540 (credit.py)"""
    x, out = gw(w), {}
    wcm = x.wcm()
    sm = x.q(wcm + 0x540) if wcm else None
    if not sm:
        return out
    for i in range(min(x.d(sm + 8) or 0, 16)):
        s = x.q(sm + 0x10 + 8 * i)
        if not s:
            continue
        n, chrset, own = x.d(s + 0x10), x.q(s + 8), x.q(s + 0x18)
        if not n or n > 4096 or not chrset or not own:
            continue
        first = x.q(chrset + 8)
        raw = x.big(first, 0x38 * n) if first else None
        if not raw:
            continue
        for j in range(n):
            c = struct.unpack_from('<Q', raw, 0x38 * j)[0]
            if c and x.q(c) == x.base + ENEMY_VT:
                h = x.d(c + 8)
                if h is not None:
                    out[h] = {'chr': c, 'own_addr': own + 2 * j, 'phys': struct.unpack_from('<Q', raw, 0x38 * j + 0x28)[0]}
    return out


def enemy_view(w, e):
    x = gw(w)
    c = e['chr']
    m = x.q(c + 0x2470)
    mod = x.q(m + 0x18) if m else None
    data = x.q(c + 0x20)
    return {'hp': x.i(mod + 0x290) if mod else None, 'max': x.i(mod + 0x294) if mod else None,
            'own': x._u(e['own_addr'], '<h', 2), 'pos': x.f3(e['phys'] + 0x70) if e['phys'] else None,
            'lastno': x.i(data + 0x11C) if data else None}


def kin_chrs(w):
    try:
        _, ks = KS.kins(gw(w))
        return set(k['chr'] for k in ks if k['chr'])
    except Exception:
        return set()


def pick_enemy(w, near, max_hp=3000, own_only=True, exclude=()):
    """alive enemy driven by game w (own >= 0), not a kin, max HP <= max_hp, nearest to `near`"""
    ens, kc, best = sync_enemies(w), kin_chrs(w), None
    for h, e in ens.items():
        if e['chr'] in kc or h in exclude:
            continue
        v = enemy_view(w, e)
        if not v['hp'] or v['hp'] <= 0 or not v['pos'] or (v['max'] or 0) > max_hp:
            continue
        if own_only and (v['own'] is None or v['own'] < 0):
            continue
        d = math.dist(near, v['pos']) if near else 0
        if best is None or d < best[0]:
            best = (d, h, e, v)
    return best


def virtue_totals(games):
    """virtue.py parsed (as match4.py): {game: {player no: (banked, live or None, own)}}"""
    _, out = tool(['diag/twin/virtue.py', games], 120, quiet=True)
    per, cur = {}, None
    for line in out.splitlines():
        h = re.match(r'([A-D]) box total (-?\d+) count (\d+)', line)
        if h:
            cur = h.group(1)
            per[cur] = {}
            continue
        p = re.match(r'\s+(\S+)\s+no (\d+) banked (-?\d+)', line)
        if p and cur:
            live = re.search(r'live >= (-?\d+)', line)
            no, own = int(p.group(2)), p.group(1).endswith('*')
            if no not in per[cur] or own:
                per[cur][no] = (int(p.group(3)), int(live.group(1)) if live else None, own)
    return per


def vtext(per):
    return '; '.join('%s: %s' % (w, ' '.join('p%d %s/%s%s' % (n, b, '-' if lv is None else lv, '*' if o else '')
                                             for n, (b, lv, o) in sorted(ps.items()))) for w, ps in per.items()) or '-'


def rewards_state(games):
    """rewards.py parsed: {game: {no, offers, banked, counters{name: value}}} (local player of each game)"""
    _, out = tool(['diag/twin/rewards.py', games], 150, quiet=True)
    res, cur = {}, None
    for line in out.splitlines():
        h = re.match(r'([A-D]) offline', line)
        if h:
            cur = h.group(1)
            res[cur] = {'no': None, 'offers': None, 'banked': None, 'counters': {}}
            continue
        if not cur:
            continue
        p = re.match(r'\s+player (-?\d+) slot', line)
        if p:
            res[cur]['no'] = int(p.group(1))
        o = re.search(r'skill-enhancement offers pending (\d+)', line)
        if o:
            res[cur]['offers'] = int(o.group(1))
        c = re.search(r'Virtue banked (-?\d+) .*counters (.*)$', line)
        if c:
            res[cur]['banked'] = int(c.group(1))
            for tok in c.group(2).split():
                k, _, v = tok.partition('=')
                if _:
                    res[cur]['counters'][k] = None if v == '?' else int(v) if v.lstrip('-').isdigit() else v
    return res


def counter(rs, w, name):
    return (rs.get(w) or {}).get('counters', {}).get(name)


def env_current(w):
    try:
        return FE.G(w).current()
    except Exception:
        return None


def am_count(w):
    x = gw(w)
    am = x.g(AM_G)
    return x.d(am + 0x38) if am else None


# ---------- action-menu assets (Flame corpses, circles) ----------
_scan = {}


def scan_assets(w, aids, fresh=False):
    """[{aid, ins, h, pos}] of every loaded geom with one of the asset ids (walks all geoms: slow, cached per round)"""
    key = (w, step_round(w)[1], tuple(sorted(aids)))
    if key in _scan and not fresh:
        return _scan[key]
    x, out = gw(w), []
    say('%s: walking every loaded geom for assets %s (slow) ...' % (w, sorted(aids)))
    for blockid, k, ins in x.all_geoms(limit=200000):
        info = x.q(ins + 0x10)
        raw = x.i(info + 0x18) if info else None
        if raw is None or raw <= 0:
            continue
        aid = raw % 10000000
        if aid in aids:
            out.append({'aid': aid, 'ins': ins, 'h': x.d(ins + 8), 'pos': x.geom_pos(ins)})
    _scan[key] = out
    return out


def asset_state(w, ins):
    x = gw(w)
    info = x.q(ins + 0x10)
    if not info:
        return None
    row = x.q(info + 0x20)
    bits = (x.q(info + 0x468) or 0) & 0xFFF
    try:
        players = TK.players_of(bits, TK.slot_map(x))
    except Exception:
        players = None
    return {'en': (x.b(ins + 0x126) or 0) & 3, 'off': bool(row) and x.b(row + 0xD) == 1, 'bits': bits,
            'players': players, 'used': x.b(info + 0x470), 'hold': x.i(info + 0x460), 'type': x.b(info + 0x306)}


def stext(s):
    return 'none' if not s else 'p=%s used=%s hold=%s bits=%03x%s' % (
        ','.join(map(str, s['players'] or [])) or '-', s['used'], s['hold'], s['bits'], ' off' if s['off'] else '')


def same_object(ctx, w_src, obj, w_dst):
    """the same object (by its 0x74 handle) on another game; loads the area by moving w_dst near it if needed"""
    for o in scan_assets(w_dst, {obj['aid']}):
        if o['h'] == obj['h']:
            return o
    if obj['pos']:
        say('%s: object h=%08x not loaded on %s: moving %s near it' % (w_src, obj['h'], w_dst, w_dst))
        p = obj['pos']
        tp(ctx, w_dst, (p[0] + 3.0, p[1] + 0.5, p[2] + 3.0))
        time.sleep(3.0)
        for o in scan_assets(w_dst, {obj['aid']}, fresh=True):
            if o['h'] == obj['h']:
                return o
    return None


def use_asset(ctx, who, ins, label, dist=1.5, hold='Y:10', budget=None, need_stand=False):
    """stand at the prompt spot of an action-menu asset (promptcheck.py STAND AT, as the kin summon of 15:10) with
    approach.py, facing it, and hold the button. (ok, text). budget = seconds for both tools (default 120 + 240);
    need_stand=True: no STAND AT from promptcheck -> (False, 'no STAND AT ...') without walking (stand point not
    usable)"""
    x = gw(who)
    pos = x.geom_pos(ins)
    if not pos:
        return False, 'geom position unreadable'
    t_end = time.time() + budget if budget else None
    tp(ctx, who, (pos[0], pos[1] + 0.5, pos[2]))          # load the object's pose before promptcheck
    time.sleep(1.5)
    _, out = tool(['diag/twin/promptcheck.py', who, 'circle', '0x%x' % ins],
                  120 if not t_end else max(10, min(120, t_end - time.time())), quiet=True)
    b = re.search(r'button \((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)', out)
    s = re.search(r'STAND AT \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\) FACING yaw=(-?[\d.]+) \(dir (-?[\d.]+), (-?[\d.]+);', out)
    if b and s:
        tgt = (float(b.group(1)), float(b.group(2)), float(b.group(3)))
        extra = ['facing=%s,%s' % (s.group(5), s.group(6))]
        how = 'promptcheck button %s, facing (%s, %s)' % (fmt3(tgt), s.group(5), s.group(6))
    elif need_stand:
        return False, 'no STAND AT from promptcheck (prompt / stand point not usable)'
    else:
        tgt, extra, how = pos, [], 'geom origin (promptcheck gave no STAND AT)'
    rc, out2 = tool(['diag/twin/approach.py', who, '%.2f' % tgt[0], '%.2f' % tgt[1], '%.2f' % tgt[2],
                     'dist=%.2f' % dist] + extra + ['hold=%s' % hold, 'shot=rs_%s' % label],
                    240 if not t_end else max(10, min(240, t_end - time.time())))
    return rc == 0, '%s; approach rc %s (%s)' % (how, rc, 'OK' if rc == 0 else 'see output')


# =============================================================== test registry
TESTS = {}


def test(name, row, group, budget):
    def deco(f):
        TESTS[name] = {'f': f, 'row': row, 'group': group, 'budget': budget, 'doc': (f.__doc__ or '').strip()}
        return f
    return deco


class Ctx:
    def __init__(self, games, actor, nowait, scale):
        self.games, self.actor, self.nowait, self.scale = games, actor, nowait, scale
        self.host = games[0]
        self.other = next(w for w in games if w != actor) if len(games) > 1 else None
        self.settled = None
        self.deadline = None

    def left(self):
        return self.deadline - time.time()

    def check(self, what=''):
        if time.time() > self.deadline:
            raise Timeout('time budget used up %s' % what)


GROUPS = {
    'phase1': ['stake_refill', 'contested_kill', 'flame_small', 'flame_medium', 'blood_crystal', 'markers', 'pin_place',
               'arm_1300'],
    'phase2': ['lever_bell', 'kin_levelup', 'small_circle', 'kin_replace', 'kin_recall', 'kin_death', 'arm_1220'],
    'site': ['pledge_takeover'],
    'phase3': ['event_gala', 'ally_form'],
    'intermission': ['start_area'],
    'final': ['alliance_end', 'spectate'],
}


# =============================================================== row 48: stake refill
@test('stake_refill', 48, 'phase1', 300)
def t_stake_refill(ctx):
    """Use the actor's Goldblood Stakes (use_item.py validate = D-pad Up), kill the actor (hp.py set 0), revive
    (revive.py), expect count = max(count, base) once on the actor's game and the other games' own lines unchanged;
    then one stake used + one enemy kill (fightfoe.py) for the kill top-up."""
    a = ctx.actor
    settle(ctx)
    s0 = {w: stake_line(w) for w in ctx.games}
    say('before: %s' % s0)
    if not s0[a] or s0[a]['type'] != 1:
        raise Skip('no local PlayerGameData of type 1 on %s: %s' % (a, s0[a]))
    for k in range(3):
        cur = stake_line(a)
        if cur['count'] == 0:
            break
        tool(['diag/twin/use_item.py', a, 'validate'], 60)
        time.sleep(2.5)
    s1 = {w: stake_line(w) for w in ctx.games}
    say('after the uses: %s' % s1)
    if s1[a]['count'] >= s0[a]['count'] and s0[a]['count'] > 0:
        return 'FAIL', 'using a stake did not lower the count', 'count %s -> %s' % (s0[a]['count'], s1[a]['count'])
    tool(['diag/twin/hp.py', a, 'set', '0'], 30)
    t0 = time.time()
    while master_hp(a) not in (0, None) and time.time() - t0 < 10:
        time.sleep(0.5)
    time.sleep(5.0)                                   # death animation, then the revival map
    rc, _ = tool(['diag/twin/revive.py', a], min(240, ctx.left()))
    t0 = time.time()
    while (master_hp(a) or 0) <= 0 and time.time() - t0 < 30:
        time.sleep(1.0)
    if (master_hp(a) or 0) <= 0:
        return 'FAIL', 'player %s not revived (revive.py rc %s): see %s_revive_fail.png' % (a, rc, a), 'stakes %s' % stake_line(a)
    time.sleep(3.0)
    s2 = {w: stake_line(w) for w in ctx.games}
    seen, t0 = [s2[a]['count']], time.time()
    while time.time() - t0 < 8:                       # a second refill without a new death = double refill
        c = stake_line(a)['count']
        if c != seen[-1]:
            seen.append(c)
        time.sleep(0.5)
    want = max(s1[a]['count'], s2[a]['base'])
    death_ok = s2[a]['count'] == want and s2[a]['count'] > s1[a]['count'] and len(seen) == 1
    others_ok = all(s2[w]['count'] == s0[w]['count'] for w in ctx.games if w != a and s0[w])
    vals = 'actor %s: %s -> uses %s -> after revive %s (want %d), later %s; others %s -> %s' % (
        a, s0[a]['count'], s1[a]['count'], s2[a]['count'], want, seen,
        {w: s0[w]['count'] for w in ctx.games if w != a}, {w: s2[w]['count'] for w in ctx.games if w != a})
    # kill top-up (fair_notes: level +1 -> stakes +1, max cap)
    kill_txt = 'kill top-up not tried'
    if ctx.left() > 90:
        if stake_line(a)['count'] >= (stake_line(a)['max'] or 0) and stake_line(a)['count'] > 0:
            tool(['diag/twin/use_item.py', a, 'validate'], 60)
            time.sleep(2.5)
        k0 = stake_line(a)
        best = pick_enemy(a, my_pos(a))
        if best:
            tool(['diag/twin/fightfoe.py', a, '%x' % best[2]['chr'], 'seconds=90'], min(150, ctx.left()))
            time.sleep(3.0)
            k1 = stake_line(a)
            kill_txt = 'kill: level %s -> %s, stakes %s -> %s (max %s)' % (k0['level'], k1['level'], k0['count'],
                                                                           k1['count'], k1['max'])
            if k1['level'] > k0['level'] and k1['count'] <= k0['count'] and k0['count'] < k0['max']:
                kill_txt += ' NO TOP-UP'
        else:
            kill_txt = 'kill top-up: no enemy driven by %s nearby' % a
    vals += '; ' + kill_txt
    if death_ok and others_ok:
        return 'PASS', 'death refill to base once on the actor, other games unchanged', vals
    return 'FAIL', 'refill wrong (death_ok %s, others unchanged %s)' % (death_ok, others_ok), vals


# =============================================================== row 13: contested kill
@test('contested_kill', 13, 'phase1', 240)
def t_contested_kill(ctx):
    """Host and actor both hit ONE enemy driven by the host until it dies (both lock on and press R together).
    Expect: the same last attacker (chrdata+0x11C) on every game that has the enemy, and only that player's
    Bloodfang / EXP grows, by the same amount on every game (credit.py fields)."""
    h, a = ctx.host, ctx.actor
    if h == a:
        raise Skip('actor must not be the host for this test')
    settle(ctx)
    best = pick_enemy(h, my_pos(h))
    if not best:
        raise Skip('no alive enemy driven by %s' % h)
    _, handle, e_h, v = best
    e_a = sync_enemies(a).get(handle)
    say('target %08x hp %s/%s at %s (driven by %s; on %s: %s)' % (handle, v['hp'], v['max'], fmt3(v['pos']), h, a,
                                                                    'loaded' if e_a else 'not loaded yet'))
    before = {w: by_no(player_rows(w)) for w in ctx.games}

    def place():
        ep = enemy_view(h, e_h)['pos']
        if not ep:
            return False
        ph = my_pos(h) or (ep[0], ep[1], ep[2] - 2)
        yaw = math.atan2(ep[0] - ph[0], ep[2] - ph[2])
        for w, ang, d in ((h, yaw, 1.4), (a, yaw + math.pi, 1.4)):
            spot = (ep[0] - d * math.sin(ang), ep[1] + 0.3, ep[2] - d * math.cos(ang))
            tp(ctx, w, spot, ang)
        time.sleep(1.0)
        for w in (h, a):
            tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4},
                                                                         {'frames': 10}]}})
        return True

    if not place():
        raise Skip('enemy position unreadable')
    hitters, rounds, dead = set(), 0, False
    while rounds < 30 and ctx.left() > 25:
        rounds += 1
        th = [threading.Thread(target=lambda w=w: tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [
            {'buttons': ['R'], 'frames': 5}, {'frames': 25}]}})) for w in (h, a)]
        for t in th:
            t.start()
        for t in th:
            t.join(60)
        vh = enemy_view(h, e_h)
        if vh['lastno'] is not None and vh['lastno'] >= 1:
            hitters.add(vh['lastno'])
        print('  round %d: enemy hp %s (on %s), last attacker no %s, hitters %s' % (rounds, vh['hp'], h, vh['lastno'],
                                                                                  sorted(hitters)), flush=True)
        if vh['hp'] is not None and vh['hp'] <= 0:
            dead = True
            break
        if rounds % 6 == 0:
            p_h, p_a = my_pos(h), my_pos(a)
            if vh['pos'] and p_h and p_a and (math.dist(vh['pos'], p_h) > 3 or math.dist(vh['pos'], p_a) > 3):
                place()
    time.sleep(3.0)
    after = {w: by_no(player_rows(w)) for w in ctx.games}
    last = {}
    for w in ctx.games:
        e = sync_enemies(w).get(handle)
        last[w] = enemy_view(w, e)['lastno'] if e else 'not loaded'
    d_fang = {w: {n: (after[w][n]['fang'] or 0) - (before[w].get(n, {}).get('fang') or 0) for n in after[w]}
              for w in ctx.games}
    d_exp = {w: {n: (after[w][n]['exp'] or 0) - (before[w].get(n, {}).get('exp') or 0) for n in after[w]}
             for w in ctx.games}
    vals = 'rounds %d dead %s hitters %s | last attacker per game %s | fang +%s | exp +%s' % (
        rounds, dead, sorted(hitters), last, d_fang, d_exp)
    if not dead:
        return 'FAIL', 'enemy not dead after %d rounds' % rounds, vals
    if len(hitters) < 2:
        return 'SKIP', 'only player(s) %s landed hits: not a contested kill, run again' % sorted(hitters), vals
    lasts = set(v for v in last.values() if v != 'not loaded')
    winners = set(n for w in ctx.games for n, dv in d_fang[w].items() if dv > 0)
    same = len(lasts) == 1 and len(winners) == 1 and lasts == winners and \
        len(set(d_fang[w].get(next(iter(winners)), 0) for w in ctx.games)) == 1
    if same:
        return 'PASS', 'one killer (player %s) on every game, credited once' % next(iter(winners)), vals
    return 'FAIL', 'games disagree on the killer or credit went to two / no players', vals


# =============================================================== row 8: small / medium Flame corpses
def flame_test(ctx, aid, label):
    a, o = ctx.actor, ctx.other
    if not o:
        raise Skip('needs two games')
    settle(ctx)
    me = my_pos(a)
    slot_a = gw(a).b((local_pgd(a) or 0) + 0x104)
    cands = []
    for ob in scan_assets(a, {aid}):
        s = asset_state(a, ob['ins'])
        if s and s['en'] == 3 and not s['off'] and not s['used'] and not (s['bits'] >> (slot_a or 0) & 1) and ob['pos']:
            cands.append((math.dist(me, ob['pos']) if me else 0, ob))
    if not cands:
        raise Skip('no usable asset %d on %s this round (map content comes from round 2: run it by name in phase2)' % (aid, a))
    cands.sort(key=lambda t: t[0])
    obj = cands[0][1]
    peer = same_object(ctx, a, obj, o)
    if not peer:
        raise Skip('object h=%08x not found on %s' % (obj['h'], o))
    st0 = {a: asset_state(a, obj['ins']), o: asset_state(o, peer['ins'])}
    rs0, v0 = rewards_state(ctx.games), virtue_totals(ctx.games)
    say('object %d h=%08x at %s; before %s | Virtue %s' % (aid, obj['h'], fmt3(obj['pos']),
                                                            {w: stext(s) for w, s in st0.items()}, vtext(v0)))
    ok, how = use_asset(ctx, a, obj['ins'], label, dist=1.3)
    time.sleep(5.0)
    st1 = {a: asset_state(a, obj['ins']), o: asset_state(o, peer['ins'])}
    rs1, v1 = rewards_state(ctx.games), virtue_totals(ctx.games)
    cname = 'FlameS' if aid == FLAME_S else 'FlameL'
    na, no_ = local_no(a), local_no(o)
    c_a = (counter(rs0, a, cname), counter(rs1, a, cname))
    vals = '%s; after actor: %s | %s %s %s->%s | Virtue %s' % (how, {w: stext(s) for w, s in st1.items()}, a, cname,
                                                              c_a[0], c_a[1], vtext(v1))
    first_ok = all(st1[w] and na in (st1[w]['players'] or []) for w in (a, o))
    if aid == FLAME_M:
        first_ok = first_ok and all(st1[w]['used'] == 1 for w in (a, o))
    if not first_ok:
        return 'FAIL', 'the actor\'s use is not shown the same on both games', vals
    # second player at the same object
    ok2, how2 = use_asset(ctx, o, peer['ins'], label + '2', dist=1.3)
    time.sleep(5.0)
    st2 = {a: asset_state(a, obj['ins']), o: asset_state(o, peer['ins'])}
    rs2, v2 = rewards_state(ctx.games), virtue_totals(ctx.games)
    c_o = (counter(rs1, o, cname), counter(rs2, o, cname))
    vals += ' || second player %s: %s | %s %s %s->%s | Virtue %s' % (o, {w: stext(s) for w, s in st2.items()}, o, cname,
                                                                    c_o[0], c_o[1], vtext(v2))
    same = stext(st2[a]).split(' bits')[0] == stext(st2[o]).split(' bits')[0]
    if aid == FLAME_S:
        both = all(st2[w] and set([na, no_]) <= set(st2[w]['players'] or []) for w in (a, o))
        if both and same and (c_a[1] or 0) > (c_a[0] or 0):
            return 'PASS', 'small corpse: once per player, both uses shown on both games, Flame Virtue counted', vals
        return 'FAIL', 'small corpse: expected both players listed on both games and a counter rise', vals
    blocked = all(no_ not in (st2[w]['players'] or []) for w in (a, o)) and (c_o[1] or 0) == (c_o[0] or 0)
    if blocked and same and (c_a[1] or 0) > (c_a[0] or 0):
        return 'PASS', 'medium corpse (99281): first player paid, second player got nothing, same state on both', vals
    return 'FAIL', 'medium corpse: second player was not blocked or the games differ', vals


@test('flame_small', 8, 'phase1', 420)
def t_flame_small(ctx):
    """Small Flame corpse 99280 (once per player): actor lights it, then the other player lights the same one.
    Expect both player numbers in the 'taken' bits on both games (taken.py), FlameS counter +1 on each user."""
    return flame_test(ctx, FLAME_S, 'flameS')


@test('flame_medium', 8, 'phase1', 420)
def t_flame_medium(ctx):
    """'Medium' Flame corpse = 99281 (flameL, pay once, reset each phase; 99282 was the proven one): actor lights
    it, the other player tries. Expect used=1 + actor's bit on both games, FlameL +1 on the actor, nothing for the
    second player."""
    return flame_test(ctx, FLAME_M, 'flameM')


# =============================================================== row 45: blood crystal
def item_nodes(w):
    x, out = gw(w), {}
    im = x.g(ITEMMAN_G)
    if not im:
        return out
    for off in (0x18, 0x48, 0x78):
        node, n = x.q(im + off), 0
        while node and n < 200:
            iid = x.d(node + 0x30)
            if iid is not None:
                out[iid] = x.f3(node + 0x40)
            node, n = x.q(node + 0x10), n + 1
    return out


@test('blood_crystal', 45, 'phase1', 420)
def t_blood_crystal(ctx):
    """Kill an enemy near the rewards2_notes Bloodsac candidate spots (c2130 [I]) with fightfoe.py, pick up its drop
    (stand on it, Y), expect 'skill-enhancement offers pending 2' on the actor (rewards.py); then A on the offer
    page and pending 0. Drops are 5-15 %: up to 3 enemies."""
    a = ctx.actor
    settle(ctx)
    spots = [(139.2, -121.2, 120.0), (253.7, -50.1, 537.0), (79.0, -59.9, 467.5)]
    r0 = rewards_state(ctx.games)
    if not r0.get(a) or r0[a]['offers'] is None:
        raise Skip('rewards.py gives no offer line for %s (item manager / slot unreadable)' % a)
    say('offers before: %s' % {w: r0[w]['offers'] for w in r0})
    tries, got_item, txt = 0, None, []
    for sp in spots:
        if ctx.left() < 120 or got_item:
            break
        tp(ctx, a, (sp[0], sp[1] + 1.0, sp[2]))
        time.sleep(3.0)
        for _ in range(2):
            if ctx.left() < 100:
                break
            best = pick_enemy(a, my_pos(a), max_hp=5000)
            if not best:
                txt.append('no enemy driven by %s near %s' % (a, fmt3(sp)))
                break
            tries += 1
            items0 = {w: item_nodes(w) for w in ctx.games}
            tool(['diag/twin/fightfoe.py', a, '%x' % best[2]['chr'], 'seconds=90'], min(150, ctx.left()))
            time.sleep(4.0)
            items1 = {w: item_nodes(w) for w in ctx.games}
            new = {w: sorted(set(items1[w]) - set(items0[w])) for w in ctx.games}
            txt.append('kill %d (enemy %08x): new items %s' % (tries, best[1], {w: ['%x' % i for i in v] for w, v in new.items()}))
            if new[a]:
                got_item = (new[a][0], items1[a][new[a][0]], new)
                break
    if not got_item:
        return 'SKIP', 'no drop after %d kills (5-15 %% chance; or c2130 is not a Bloodsac)' % tries, '; '.join(txt)
    iid, ipos, new = got_item
    if ipos:
        tp(ctx, a, (ipos[0], ipos[1] + 0.3, ipos[2]))
        time.sleep(1.0)
    press(a, 'Y', 10, 60)
    time.sleep(3.0)
    r1 = rewards_state(ctx.games)
    gone = {w: iid not in item_nodes(w) for w in ctx.games}
    txt.append('picked item %x at %s: gone %s, offers %s' % (iid, fmt3(ipos), gone, {w: r1[w]['offers'] for w in r1}))
    if not r1.get(a) or not r1[a]['offers']:
        if all(gone.values()):
            return 'FAIL', 'item picked up but no skill-enhancement offer (not a crystal, or award lost)', '; '.join(txt)
        return 'SKIP', 'the pickup did not happen (item still listed)', '; '.join(txt)
    sh = shot(a, 'rs_crystal_offer')
    press(a, 'A', 6, 60)
    time.sleep(3.0)
    r2 = rewards_state(ctx.games)
    txt.append('after A: offers %s, shot %s' % ({w: r2[w]['offers'] for w in r2}, sh))
    if r2[a]['offers'] == 0:
        return 'PASS', 'crystal gave a two-option offer and the pick consumed it (judge the effect in the shot)', '; '.join(txt)
    return 'PARTIAL', 'crystal offer appeared; the pick did not go through with one A press (pick by hand)', '; '.join(txt)


# =============================================================== row 54: markers (manual)
# =============================================================== arming events (setup for the next phase)
def arm(ctx, eid):
    h = ctx.host
    s, r = step_round(h)
    if s != 6:
        raise Skip('host %s not in UpdatePhase (step %s)' % (h, s))
    cur = env_current(h)
    log = TWIN / ('regress_small_arm_%d.log' % eid)
    guests = ''.join(w for w in ctx.games if w != h)
    base = {w: len(sync_enemies(w)) for w in ctx.games}
    items = {w: len(item_nodes(w)) for w in ctx.games}
    fh = open(log, 'w')
    p = subprocess.Popen([PY, '-u', 'diag/twin/force_event.py', h, str(eid), 'arm', guests, '--timeout', '900'],
                         stdout=fh, stderr=subprocess.STDOUT, cwd=WS, env=dict(os.environ, TWIN_GAMES=CFG['games']))
    time.sleep(4.0)
    fh.flush()
    head = log.read_text(errors='replace') if log.exists() else ''
    st = load_state()
    st['armed'] = {'event': eid, 'round': r, 'pid': p.pid, 'log': str(log), 'time': time.time(),
                   'enemies': base, 'items': items}
    save_state(st)
    if p.poll() is not None and 'armed:' not in head:
        return 'FAIL', 'force_event.py exited at once (rc %s)' % p.returncode, head.strip()[-300:]
    why = ('host %s armed for event %d at the next draw (round %d): cut the clock now (clock.py 5 %s); '
           'force_event.py restores the stock word after the draw or after 900 s' % (h, eid, r + 1, ctx.games))
    vals = 'current event %s, baseline enemies %s items %s, log %s' % (cur, base, items, log.relative_to(WS))
    return 'SETUP', why, vals


@test('arm_1300', 57, 'phase1', 30)
def t_arm_1300(ctx):
    """SETUP for lever_bell: force event 1300 (bell, Dusk's Toll) for the next phase with force_event.py."""
    return arm(ctx, 1300)


@test('arm_1220', 42, 'phase2', 30)
def t_arm_1220(ctx):
    """SETUP for event_gala: force event 1220 (Bloodsac Gala) for the next phase with force_event.py."""
    return arm(ctx, 1220)


@test('arm_1210', 42, '-', 30)
def t_arm_1210(ctx):
    """SETUP for event_star: force event 1210 (Star Fragment) for the next phase (Phase III) with force_event.py."""
    return arm(ctx, 1210)


# =============================================================== row 57: levers / gates (the bell pull)
@test('lever_bell', 57, 'phase2', 240)
def t_lever_bell(ctx):
    """The map's only asset-access entry (#0, param 9005, the Clock Tower bell pull; levers.py found no other lever /
    gate). Needs event 1300 current (arm_1300). Host walks to the pull (approach.py from=-0.50,-0.87 dist=1.3, the
    15:52 spot), turns the camera with the right stick and presses Y until the entry or the Virtue changes. Expect
    the entry's holder / busy / mask the same on every game, and A's Virtue +6 on every game."""
    h = ctx.host
    settle(ctx)
    cur = {w: env_current(w) for w in ctx.games}
    if any(v != 1300 for v in cur.values()):
        raise Skip('event 1300 not current on every game (%s): run arm_1300 in the phase before' % cur)

    def entry(w):
        r = next((x for x in LV.entries(gw(w)) if x['n'] == 0), None)
        return None if not r else {'param': r['param'], 'holder': r['holder'], 'busy': r['busy'],
                                   'mask': None if r['mask'] is None else r['mask'] & 0xFFF, 'pos': fmt3(r['pos'])}
    e0 = {w: entry(w) for w in ctx.games}
    v0 = virtue_totals(ctx.games)
    say('entry #0 before %s | Virtue %s' % (e0, vtext(v0)))
    if not e0[h] or e0[h]['param'] != 9005:
        raise Skip('entry #0 is not the bell (param 9005) on %s: %s' % (h, e0[h]))
    tool(['diag/twin/approach.py', h, '147.5', '133.7', '101.6', 'dist=1.3', 'from=-0.50,-0.87', 'shot=rs_bell'], 240)
    turns = [None, (0, 1), (0, 1), (0, -1), (0, -1), (0, -1), (-1, 0), (1, 0), (1, 0), (0, 1)]
    changed, k = False, 0
    for k, t in enumerate(turns):
        if ctx.left() < 30:
            break
        if t:
            stick(h, 'right_stick', t, 8, 10)
        press(h, 'Y', 10, 40)
        time.sleep(2.0)
        e1 = entry(h)
        v1 = virtue_totals(h)
        own = next((lv for n, (b, lv, o) in (v1.get(h) or {}).items() if o), None)
        own0 = next((lv for n, (b, lv, o) in (v0.get(h) or {}).items() if o), None)
        if e1 != e0[h] or (own is not None and own0 is not None and own > own0):
            changed = True
            break
    sh = shot(h, 'rs_bell_after')
    time.sleep(3.0)
    e2 = {w: entry(w) for w in ctx.games}
    v2 = virtue_totals(ctx.games)
    vals = 'tries %d, entry after %s | Virtue after %s | shot %s' % (k + 1, e2, vtext(v2), sh)
    if not changed:
        return 'FAIL', 'no change of the bell entry or the host\'s Virtue after %d presses (camera not on the pull?)' % (k + 1), vals
    same = len(set((e['holder'], e['busy'], e['mask']) for e in e2.values() if e)) == 1
    return ('PASS' if same else 'FAIL'), ('bell pull used; entry state equal on every game' if same else
                                          'bell pull used, but the entry state differs between games'), vals


# =============================================================== kin helpers (rows 27, 28, 29)
def kin_view(w, owner):
    x = gw(w)
    head, ks = KS.kins(x)
    mine = [k for k in ks if k['owner'] == owner]
    ring = next((p['ring'] for p in KS.players(x) if p['ring'] and p['ring']['no'] == owner), None)
    return {'count': head['count'] if head else None, 'kins': len(mine),
            'buddy': mine[0]['buddy'] if mine else None, 'state': mine[0]['state'] if mine else None,
            'cc': mine[0]['cc'] if mine else None, 'hp': mine[0]['hp'] if mine else None,
            'chr': mine[0]['chr'] if mine else None, 'id': mine[0]['id'] if mine else None,
            'cur': ring['cur'] if ring else None, 'level': ring['now_lvl'] if ring else None,
            'exp': ring['now_exp'] if ring else None}


def ktext(v):
    return 'kins %s buddy %s state %s lvl %s exp %s cur %s' % (v['kins'], v['buddy'], v['state'], v['level'], v['exp'], v['cur'])


def kin_step(w, owner):
    """summon state step of the owner's kin on game w = [BM node + 0x30] (kinstate.py: state +0x50, flags +0xC0 / +0xC8)"""
    x = gw(w)
    _, ks = KS.kins(x)
    k = next((k for k in ks if k['owner'] == owner), None)
    return x.q(k['node'] + 0x30) if k and k['node'] else None


def kin_summon_out(ctx, owner, wait=20.0):
    """TEST ONLY: make the actor's (owner's) kin come out (state 3 Summon) if it is in state 2 Unsummon. Writes u8 1 at
    step+0xC8 on the owner's game = the request flag UnsummonState 0xD82FC0 takes like the Function Menu action
    0x165 (0xD83180..0xD83190, owner chr == local player); the game clears it itself (0xD831CC). (ok, text)"""
    a = ctx.actor
    v = kin_view(a, owner)
    if v['state'] == 3:
        return True, 'already out (state 3)'
    if v['state'] != 2:
        return False, 'kin in state %s, not 2 Unsummon (dead / waiting to revive?)' % v['state']
    st = kin_step(a, owner)
    if not st:
        return False, 'summon step unreadable'
    gw(a).write(st + 0xC8, b'\x01')
    t0 = time.time()
    while time.time() - t0 < wait:
        if kin_view(a, owner)['state'] == 3:
            return True, 'summoned through step+0xC8 in %.1f s' % (time.time() - t0)
        time.sleep(0.5)
    return False, 'step+0xC8 = 1 written, state still %s after %.0f s' % (kin_view(a, owner)['state'], wait)


def big_circles(w, exclude=()):
    out = []
    for aid, ins, typ, holder, mask, used, off, pos in KS.circles(gw(w))[0]:
        if aid in BIG_CIRCLES and not off and holder in (-1, None) and ins not in exclude and pos:
            out.append({'aid': aid, 'ins': ins, 'type': typ, 'pos': pos})
    return out


KIN_TRIES, KIN_WAIT, KIN_TOTAL = 4, 30.0, 150.0     # ensure_kin: circles tried, wait after a press, total s


def ensure_kin(ctx, exclude=()):
    """the actor owns a kin on its game (summons one at a free big circle if not); returns (owner no, circle ins)"""
    a = ctx.actor
    owner = local_no(a)
    if kin_view(a, owner)['kins']:
        return owner, None
    r = step_round(a)[1]
    if r < 2:
        raise Skip('kin circles exist from round 2 on (round %s)' % r)
    me = my_pos(a)
    cs = sorted(big_circles(a, exclude), key=lambda c: math.dist(me, c['pos']) if me else 0)
    if not cs:
        raise Skip('no free big summoning circle on %s' % a)
    # 2026-11-16 robust: up to KIN_TRIES circles, the nearest of each type first, then the rest by distance; a circle
    # with a live enemy within 15 m (host / actor) or with no promptcheck STAND AT is skipped; a failed approach
    # (rc != 0) or no kin KIN_WAIT s after the press -> the next circle; everything inside KIN_TOTAL s
    seen, first, rest = set(), [], []
    for c in cs:
        (rest if c['type'] in seen else first).append(c)
        seen.add(c['type'])
    t_end, tries, log = time.time() + KIN_TOTAL, 0, []
    for c in first + rest:
        if tries >= KIN_TRIES:
            break
        left = t_end - time.time()
        if left < 30:
            log.append('%.0f s left: stopped' % left)
            break
        tag = '%d type %s (%s) %s' % (c['aid'], c['type'], CI.TYPE_NAME.get(c['type'], '?'), fmt3(c['pos']))
        foes = enemies_near(ctx, c['pos'], 15.0)
        if foes:
            log.append('%s: skipped, enemy within 15 m %s' % (tag, foes[:3]))
            say('kin circle ' + log[-1])
            continue
        tries += 1
        say('%s: summoning at circle %s (try %d/%d, %.0f s left)' % (a, tag, tries, KIN_TRIES, left))
        ok, how = use_asset(ctx, a, c['ins'], 'kin', dist=1.5, budget=max(20, left - KIN_WAIT - 5), need_stand=True)
        if not ok and not kin_view(a, owner)['kins']:
            log.append('%s: %s' % (tag, how))
            say('kin circle ' + log[-1])
            continue
        t0 = time.time()
        wait = max(5, min(KIN_WAIT, t_end - t0))
        while time.time() - t0 < wait:
            if all(kin_view(w, owner)['kins'] for w in ctx.games):
                say('KIN CIRCLE OK: %s (try %d, %.0f s in total)' % (tag, tries, KIN_TOTAL - (t_end - time.time())))
                return owner, c['ins']
            time.sleep(2.0)
            if not kin_view(a, owner)['kins'] and time.time() - t0 > 6:
                press(a, 'A', 5, 30)                  # a dialog line of the compact drama, if one is open
        v = {w: ktext(kin_view(w, owner)) for w in ctx.games}
        if kin_view(a, owner)['kins']:
            # the summon worked on the actor: another circle cannot fix a missing copy on the other game
            raise Skip('kin out on %s only after circle %s (%s): %s' % (a, tag, how, v))
        log.append('%s: no kin %.0f s after the press (%s)' % (tag, wait, how))
        say('kin circle ' + log[-1])
    raise Skip('no kin after %d circle(s) in %.0f s: %s; now %s' % (
        tries, KIN_TOTAL - max(0, t_end - time.time()), ' | '.join(log) or 'no circle usable',
        {w: ktext(kin_view(w, owner)) for w in ctx.games}))


@test('kin_summon', 26, '-', 240)
def t_kin_summon(ctx):
    """(row 26, already proven) summon a kin for the actor at a free big circle; kin listed on every game."""
    settle(ctx)
    owner, ins = ensure_kin(ctx)
    v = {w: kin_view(w, owner) for w in ctx.games}
    return 'PASS', 'player %s has a kin on every game%s' % (owner, '' if ins else ' (already had one)'), \
        '; '.join('%s: %s' % (w, ktext(x)) for w, x in v.items())


@test('kin_levelup', 27, 'phase2', 480)
def t_kin_levelup(ctx):
    """With the actor's kin out, the actor kills enemies it drives (fightfoe.py, never the kin) until the kin's level
    rises. Expect the owner's kin EXP / level equal on every game after each kill (kinstate.py ring)."""
    settle(ctx)
    owner, _ = ensure_kin(ctx)
    a = ctx.actor
    v0 = {w: kin_view(w, owner) for w in ctx.games}
    say('before: %s' % {w: ktext(x) for w, x in v0.items()})
    lv0, kills, log = v0[a]['level'], 0, []
    while kills < 6 and ctx.left() > 100:
        best = pick_enemy(a, my_pos(a))
        if not best:
            log.append('no enemy driven by %s nearby' % a)
            break
        rc, _ = tool(['diag/twin/fightfoe.py', a, '%x' % best[2]['chr'], 'seconds=90'], min(150, ctx.left()))
        kills += 1 if rc == 0 else 0
        time.sleep(3.0)
        v = {w: kin_view(w, owner) for w in ctx.games}
        log.append('kill %d (rc %s): %s' % (kills, rc, ' | '.join('%s lvl %s exp %s' % (w, x['level'], x['exp']) for w, x in v.items())))
        if v[a]['level'] is not None and lv0 is not None and v[a]['level'] > lv0:
            break
    v1 = {w: kin_view(w, owner) for w in ctx.games}
    equal = len(set((x['level'], x['exp'], x['cur']) for x in v1.values())) == 1
    vals = '; '.join(log) + ' || after %s' % {w: ktext(x) for w, x in v1.items()}
    if v1[a]['level'] is not None and lv0 is not None and v1[a]['level'] > lv0 and equal:
        return 'PASS', 'kin level %s -> %s from kills, equal on every game' % (lv0, v1[a]['level']), vals
    if (v1[a]['exp'] or 0) > (v0[a]['exp'] or 0) and equal:
        return 'PARTIAL', 'kin EXP rose and is equal on every game, no level-up within %d kills' % kills, vals
    return 'FAIL', 'kin EXP did not rise or differs between games', vals


@test('small_circle', 29, 'phase2', 420)
def t_small_circle(ctx):
    """With a kin out, the actor uses a small summoning circle 99295 ('Strengthen kin'). Expect the kin's EXP /
    level up equally on every game and the circle used up FOR THAT PLAYER ONLY: the actor's slot bit in info+0x468
    on every game and the shared byte info+0x470 still 0. That is the game's own rule (kin2_notes.md section 1:
    asset kind 14 -> processor mgr+0x78 with +8 = 0 -> vt+0x48 'per player' true -> grant 0x11A3838 skips +0x470),
    reset at each phase change (vt+0x58 = 1). used=1 anywhere would be a deviation (PARTIAL)."""
    settle(ctx)
    owner, _ = ensure_kin(ctx)
    a, o = ctx.actor, ctx.other
    me = my_pos(a)
    cands = []
    for ob in scan_assets(a, {SMALL_CIRCLE}):
        s = asset_state(a, ob['ins'])
        if s and not s['off'] and not s['used'] and not s['bits'] and ob['pos']:
            cands.append((math.dist(me, ob['pos']) if me else 0, ob))
    if not cands:
        raise Skip('no unused small circle on %s' % a)
    obj = sorted(cands, key=lambda t: t[0])[0][1]
    peer = same_object(ctx, a, obj, o) if o else None
    k0 = {w: kin_view(w, owner) for w in ctx.games}
    s0 = {a: asset_state(a, obj['ins']), o: asset_state(o, peer['ins']) if peer else None}
    say('small circle h=%08x at %s; before %s | %s' % (obj['h'], fmt3(obj['pos']), {w: stext(s) for w, s in s0.items()},
                                                       {w: ktext(x) for w, x in k0.items()}))
    ok, how = use_asset(ctx, a, obj['ins'], 'small', dist=1.3)
    time.sleep(6.0)
    k1 = {w: kin_view(w, owner) for w in ctx.games}
    s1 = {a: asset_state(a, obj['ins']), o: asset_state(o, peer['ins']) if peer else None}
    vals = '%s | after %s | %s' % (how, {w: stext(s) for w, s in s1.items()}, {w: ktext(x) for w, x in k1.items()})
    exp_up = (k1[a]['exp'] or 0) > (k0[a]['exp'] or 0) or (k1[a]['level'] or 0) > (k0[a]['level'] or 0)
    equal = len(set((x['level'], x['exp']) for x in k1.values())) == 1
    mine_all = all(s and owner in (s['players'] or []) for s in s1.values())
    shared_free = all(s and not s['used'] for s in s1.values())
    if exp_up and equal and mine_all and shared_free:
        return 'PASS', 'small circle gave kin EXP (equal on every game) and is used up for player %s only, on every ' \
                       'game (per-player rule of the game)' % owner, vals
    if exp_up and equal:
        return 'PARTIAL', 'kin EXP part works; taken state differs from the per-player rule (own bit on every game %s, ' \
                          'shared byte 0 on every game %s)' % (mine_all, shared_free), vals
    return 'FAIL', 'no kin EXP from the small circle or the games differ (exp_up %s equal %s own bit %s shared 0 %s)' % (
        exp_up, equal, mine_all, shared_free), vals


@test('kin_replace', 29, 'phase2', 360)
def t_kin_replace(ctx):
    """With a kin, the actor compacts at another big circle of a DIFFERENT TYPE than its kin's (circles.py pools:
    such a circle cannot offer the current kin; the game also drops the own species from any pool, 0xD7F578).
    Expect one kin for the owner on every game (old one gone), a new buddy id from that circle's pool, the same on
    every game, and level = max(old, 2) - 1 (kin_rules_notes section 2). A after 6 s confirms a dialog if one opens."""
    settle(ctx)
    owner, first = ensure_kin(ctx)
    a = ctx.actor
    k0 = {w: kin_view(w, owner) for w in ctx.games}
    old_b = k0[a]['buddy']
    old_t = CI.kin_type(old_b)
    me = my_pos(a)
    cs = [c for c in big_circles(a, exclude=(first,) if first else ()) if c['ins'] != first and c['type']]
    diff = [c for c in cs if old_t is None or c['type'] != old_t]
    if not diff:
        raise Skip('no free big circle of another type than the kin %s (%s) on %s (free: %s)' % (
            old_b, CI.TYPE_NAME.get(old_t, '?'), a, sorted(set(CI.TYPE_NAME.get(c['type'], c['type']) for c in cs)) or 'none'))
    diff.sort(key=lambda c: math.dist(me, c['pos']) if me else 0)
    c = diff[0]
    pool = CI.offers(c['type'], old_b)
    say('%s: kin %s (%s); compact at %d %s pool %s %s' % (a, old_b, CI.TYPE_NAME.get(old_t, '?'), c['aid'],
                                                          CI.TYPE_NAME.get(c['type'], '?'), pool, fmt3(c['pos'])))
    # With a kin of his own the circle shows button 903x (info+0x338, 0x119F440), a HOLD gauge (ActionButtonParam
    # byte +2 = 2, like the stones / forge; kin3_notes.md): a 10-frame tap never presses it. Hold as for the pillar.
    ok, how = use_asset(ctx, a, c['ins'], 'kin2', dist=1.5, hold='Y:420')
    t0, k1, pressed = time.time(), None, False
    while time.time() - t0 < 40:
        k1 = {w: kin_view(w, owner) for w in ctx.games}
        if all(x['kins'] == 1 and x['buddy'] != old_b for x in k1.values()):
            break
        if not pressed and time.time() - t0 > 6:
            press(a, 'A', 5, 30)                      # a dialog line of the compact drama, if one is open
            pressed = True
        time.sleep(2.0)
    want = max(k0[a]['level'] or 1, 2) - 1
    vals = '%s | circle %d type %s pool %s | before %s | after %s | want level %d' % (
        how, c['aid'], c['type'], pool, {w: ktext(x) for w, x in k0.items()}, {w: ktext(x) for w, x in k1.items()}, want)
    one = all(x['kins'] == 1 for x in k1.values())
    new = all(x['buddy'] != old_b and x['buddy'] in pool for x in k1.values())
    moved = all(x['cur'] != k0[w]['cur'] for w, x in k1.items())
    lv_ok = all(x['level'] == want for x in k1.values())
    same = len(set((x['buddy'], x['level'], x['cur']) for x in k1.values())) == 1
    if one and new and moved and lv_ok and same:
        return 'PASS', 'new compact replaced kin %s by %s on every game, level %d' % (old_b, k1[a]['buddy'], want), vals
    if all(x['buddy'] == old_b for x in k1.values()) and not moved:
        return 'FAIL', 'nothing changed on any game (press not granted, drama not confirmed, or lottery kept the kin)', vals
    return 'FAIL', 'replacement not equal on every game (one %s new %s ring moved %s level ok %s same %s)' % (
        one, new, moved, lv_ok, same), vals


KD_GONE = 20   # kin11: the kin must be gone (state 2) on every game within this many s of its own state 7
KD_ATTACK, KD_SWITCH = 120, 30   # kin_death v3: attack seconds, switch to strike.py after this without a connect
KD_LAG = 8.0                     # runmix_review: a copy may trail the owner's HP by this many seconds (status word)


@test('kin_death', 28, 'phase2', 480)
def t_kin_death(ctx):
    """TEST ONLY (kin5_notes.md 5). A rival (the other game's player, not allied) kills the actor's kin with REAL hits
    only; nothing is written to any HP on any game. (The old HP-1 cap on the owner wrote only the visible value +0x290; a real
    hit is applied to the property's MASTER copy (P+0x40, the full HP), so the cap could never make one hit lethal,
    and the rival's copy died on a predicted value instead.)
    (1) owner's game: summon the kin out (kin_summon_out, step+0xC8 = 1), wait for state 3;
    (1b) printed once on both games: the inputs of KIN_AUTH v3's ownership test (summoner handle, own handle,
        entries 1..11, GENERATOR_IDLE, the verdict) and the kin's "no dead" bit;
    (1c) control (kin5_notes 10): an ordinary enemy from the RIVAL's own loaded list (npcs.find, as kill.py), nearest
        to the kin there, hit by killchr.py; its HP on the rival (swings land?) and on the owner (forwarded?);
    (2) the rival runs killchr.py on ITS copy of the kin (kill.py's sequence: teleport 1.5 m at the target's height,
        face, StickR, R presses; re-aimed every 4 presses) for up to 150 s, output to diag/twin/kin_death_<rival>.log.
        NO HP WRITE ON ANY GAME (fightfoe.py is no longer used: its hold wrote the rival's HP). Every 5 s: kin HP on
        both games and last attacker / hit bit on both;
    (3) PASS (kindeath3_live.py: KIN_AUTH v3 + KIN_SEND + KIN_PRED built in, kin5_notes 9): the owner's HP falls
        with the rival's hits (2+ drops, then 0); while the kin lives every copy stays within one hit (the owner's
        largest drop) of the owner's HP; on EVERY game 7 DeadAnim -> 8 FinishUnsummon -> 9 WaitRevive -> 2 Unsummon,
        the 7 no earlier than the owner's HP 0 (0.3 s read slack). PARTIAL: only 8 unseen (shorter than a read).
        Printed, not judged: the revive-ok bit (cc bit 4) on the other games, and the re-summon (4);
    (4) back in state 2 everywhere: the summon request again; state 3 on every game = re-summon.
    REAL GAP: another game's copy reached 7, or its HP fell, while the owner's kin stayed in 3 with its HP unchanged
    (no hit reached / was applied on the owner). NO HIT: nothing landed anywhere (SKIP, not judged).
    v2 (2026-11-16, row 19's method): budget 360 s (the 6-minute cap). The OWNER (actor) is protected with the
    engine's no-dead bit on ITS OWN player chr only (nodeath.py bit mode: u16 [[player+0x2470]+0x18]+0x4A0 bit 2;
    re-asserted every 5 s, cleared at the end); the kin's own flag word must have no-dead / immortal / no-damage
    clear, and the global debug byte main+0x5B84290 must be off. No input on the owner: it stands still (a dead
    owner sends the kin to 5 RequestForceUnsummon). The kin is summoned with the REAL input (hold Y + D-pad Down,
    summon_out_input) and must be in state 3 on every game. The rival waits (up to 20 s) until its copy of the kin
    is within 2 m of the kin's real position (the owner's copy), then attacks with strike.py (validated
    ground-tested positioning, mode R, no HP write, no lock-on: strike never presses StickR); killchr.py only if
    strike's probe does not say "loaded YES". Every 5 s: kin HP on both games, last attacker / hit bit on both, and
    whether kindeath3 (KIN_AUTH hook word at 0x173D99C) is applied."""
    settle(ctx)
    owner, _ = ensure_kin(ctx)
    a, o = ctx.actor, ctx.other
    if not o:
        raise Skip('needs a second game to attack the kin')
    built = {w: gw(w).d(gw(w).base + 0x173D99C) != 0xD503237F for w in ctx.games}   # KIN_AUTH hook word
    import nodeath
    alive, ahow = owner_alive(a)
    if not alive:
        raise Skip('owner not alive: %s' % ahow)
    for w in ctx.games:
        if gw(w).b(gw(w).base + nodeath.PLAYER_NODEAD_G):
            raise Skip('%s: debug no-dead byte main+0x%X is on (run nodeath.py %s off)' % (
                w, nodeath.PLAYER_NODEAD_G, w))
    nd_b, nd_a = nodeath.set_nodeath(gw(a), True, 'bit', quiet=True)
    if nd_a is None:
        raise Skip('owner %s: no-dead bit could not be set (%s)' % (a, nd_b.get('why')))
    say('TEST ONLY owner %s protected: no-dead bit on its own player chr (%s)' % (a, nodeath.fmt(nd_a)))
    try:
        # runkr2 fix (2026-11-16 15:16, "NO HIT ... my hp 0"): the RIVAL died among 8 enemies and nothing landed.
        # TEST ONLY: the rival gets the same no-dead bit on its own player chr, cleared below on every exit.
        alive_o, ohow = owner_alive(o, 60.0)
        if not alive_o:
            raise Skip('rival %s not alive: %s' % (o, ohow))
        nd_ob, nd_oa = nodeath.set_nodeath(gw(o), True, 'bit', quiet=True)
        if nd_oa is None:
            raise Skip('rival %s: no-dead bit could not be set (%s)' % (o, nd_ob.get('why')))
        say('TEST ONLY rival %s protected: no-dead bit on its own player chr (%s)' % (o, nodeath.fmt(nd_oa)))
        return kin_death_body(ctx, owner, a, o, built, nodeath)
    finally:
        for w_, role_ in ((a, 'owner'), (o, 'rival')):
            try:
                nodeath.set_nodeath(gw(w_), False, 'bit', quiet=True)
                say('%s %s: no-dead bit off again' % (role_, w_))
            except Exception as ex:
                say('%s %s: no-dead bit NOT cleared (%s): run  python diag/twin/nodeath.py %s off' % (
                    role_, w_, ex, w_))


def pos_ok(p):
    """a usable position: three finite floats, not all near 0, not huge (no teleport on nan / garbage)"""
    try:
        return (p is not None and len(p) == 3 and all(math.isfinite(v) and abs(v) < 1e5 for v in p)
                and any(abs(v) > 1.0 for v in p))
    except TypeError:
        return False


def top_up(w):
    """TEST ONLY: the local player's master HP (entry 0 module +0xF30) up to its max (data module
    [[chr+0x20]+0x1D0]+0xC, hp.py) when it is below and above 0 (a dead player is not touched). -> text"""
    x = gw(w)
    e = x.player_entry(0)
    if not e or not e[0] or not e[3]:
        return '%s: no player entry' % w
    d = x.q(e[0] + 0x20)
    data = x.q(d + 0x1D0) if d else None
    hp, mx = x.i(e[3] + 0xF30), (x.i(data + 0xC) if data else None)
    if hp is None or mx is None or not 0 < mx <= 100000:
        return '%s HP %s / max %s unreadable: not topped up' % (w, hp, mx)
    if 0 < hp < mx:
        x.write(e[3] + 0xF30, struct.pack('<i', mx))
        return '%s HP %s -> %s' % (w, hp, x.i(e[3] + 0xF30))
    return '%s HP %s / %s' % (w, hp, mx)


def kd_prepare(ctx, a, o, owner, nodeath):
    """runkr2 fix: before the kin comes out, (1) clear the owner's area (make_safe: real hits by the owner within
    25 m, else a move to a quiet spot; a second, smaller pass 15 / 25 m if that failed), (2) both players alive
    and topped up, (3) the rival moved 3 m beside the owner (validated positions only). -> text"""
    safe, how = make_safe(ctx, a, owner, clear_secs=75.0)
    if not safe:
        safe2, how2 = make_safe(ctx, a, owner, kill_r=15.0, clear_r=25.0, clear_secs=30.0)
        how += ' || second pass (15 / 25 m) safe %s: %s' % (safe2, how2)
        safe = safe2
    for w_ in (a, o):
        nodeath.set_nodeath(gw(w_), True, 'bit', quiet=True)      # re-assert (the game may clear it)
    alive_o, ohow = owner_alive(o, 60.0)
    if not alive_o:
        raise Skip('rival %s not alive after making the area safe: %s' % (o, ohow))
    pa = my_pos(a)
    if not pos_ok(pa):
        raise Skip('owner %s position %s not valid: no teleport' % (a, pa))
    spot = (pa[0] + 3.0, pa[1] + 0.3, pa[2])
    tp(ctx, o, spot)
    time.sleep(1.5)
    po = my_pos(o)
    if not pos_ok(po) or math.dist(po, spot) > 6.0:
        raise Skip('rival %s not beside the owner after the move (at %s, wanted %s)' % (o, po, spot))
    ups = [top_up(w_) for w_ in (a, o)]
    near_o = near_here(o, po, 25.0)
    return 'safe %s (%s) | rival %s moved 3 m beside the owner | %s | enemies within 25 m of the rival %d' % (
        safe, how, o, '; '.join(ups), len(near_o))


def kin_death_body(ctx, owner, a, o, built, nodeath):
    prep = kd_prepare(ctx, a, o, owner, nodeath)
    say('kin_death safety: %s' % prep)
    out_ok, out_how = summon_out_input(ctx, a, owner)
    if not out_ok:
        raise Skip('kin could not be brought out with Y + Down: %s' % out_how)
    t_w = time.time()
    while time.time() - t_w < 20 and not all(kin_view(w, owner)['state'] == 3 for w in ctx.games):
        time.sleep(0.5)
    k0 = {w: kin_view(w, owner) for w in ctx.games}
    if not all(v['state'] == 3 for v in k0.values()):
        raise Skip('kin not in state 3 on every game 20 s after the summon: %s' % {w: v['state'] for w, v in k0.items()})
    kc = k0[a]['chr']
    km = gw(a).q(kc + 0x2470) if kc else None
    kmod = gw(a).q(km + 0x18) if km else None
    kfl = gw(a).h(kmod + 0x4A0) if kmod else None
    if kfl is None or kfl & 0x7:
        raise Skip("the kin's own flag word on the owner is %s (no-dead / immortal / no-damage set or unreadable): "
                   'the kill would be void' % (None if kfl is None else '0x%04x' % kfl))
    if not k0[o]['chr']:
        raise Skip("no copy of player %s's kin on %s" % (owner, o))
    if (k0[o]['buddy'], k0[o]['id']) != (k0[a]['buddy'], k0[a]['id']):
        raise Skip("%s's copy differs from the owner's (buddy %s id %s vs buddy %s id %s)" % (
            o, k0[o]['buddy'], k0[o]['id'], k0[a]['buddy'], k0[a]['id']))
    t_start = time.time()
    seq = {w: [(k0[w]['state'], 0.0)] for w in ctx.games}        # (state, seconds since start)
    cc_at = {w: None for w in ctx.games}                          # first time cc bit 4 was seen
    hp = {w: [k0[w]['hp']] for w in ctx.games}
    pairs = []                                                    # (t, {game: HP}) per read

    def look():
        t = time.time() - t_start
        now = {}
        pairs.append((t, now))
        for w in ctx.games:
            v = kin_view(w, owner)
            now[w] = v['hp']
            if v['state'] != seq[w][-1][0]:
                seq[w].append((v['state'], round(t, 1)))
            if v['hp'] != hp[w][-1] and len(hp[w]) < 40:
                hp[w].append(v['hp'])
            if v['cc'] is not None and v['cc'] & 0x10 and cc_at[w] is None:
                cc_at[w] = round(t, 1)

    def first(w, st, after=None):
        return next((t for s, t in seq[w] if s == st and (after is None or t >= after)), None)

    def dead_on(w):
        return any(s in (7, 8, 9) for s, _ in seq[w])

    def hit_probe(w):
        """strike.py's reading: last attacker u16 [[chr+0x20]+0x114], hit bit ([chr+0x12C5] >> 25) & 1; plus
        the game's own player handle (u16), so 'last attacker = rival' can be told."""
        x = gw(w)
        c = kin_view(w, owner)['chr']
        d = x.q(c + 0x20) if c else None
        la = x.d(d + 0x114) if d else None
        st = x.d(c + 0x12C5) if c else None
        me = x.q(x.g(0x5B3CD88) + 0x1A8) if x.g(0x5B3CD88) else None
        md = x.q(me + 0x20) if me else None
        mh = x.d(md + 0x78) if md else None
        return 'last attacker %s hit bit %s (own player %s)' % (
            '%04x' % (la & 0xFFFF) if la is not None else '?', (st >> 25) & 1 if st is not None else '?',
            '%04x' % (mh & 0xFFFF) if mh is not None else '?')

    def own_probe(w):
        """the inputs of KIN_AUTH v4's kin_test on game w (kindeath4_gen.py): the kin's owner PLAYER NUMBER
        data+0xB8, our pgd number [[[WCM+0x1A8]+0x20]+0x1D0]+0xD0, the numbers of player entries 1..11
        (WCM+0x30, 0x38 each), GENERATOR_IDLE u32 main+0x492AFD8 (0 = authority), and the verdict the caves reach;
        plus the kin's engine "no dead" bit [[chr+0x2470]+0x18]+0x4A0 bit 2 (a set bit stops HP at 1).
        v4 (kin8_notes): v3 compared +0xB8 with chr handles (+0x78) and never matched."""
        x = gw(w)

        def pno(chr_):
            dd = x.q(chr_ + 0x20) if chr_ else None
            pg = x.q(dd + 0x1D0) if dd else None
            return x.d(pg + 0xD0) if pg else None
        c = kin_view(w, owner)['chr']
        d = x.q(c + 0x20) if c else None
        sh = x.d(d + 0xB8) if d else None
        wcm = x.g(0x5B3CD88)
        me = x.q(wcm + 0x1A8) if wcm else None
        mh = pno(me)
        ents = x.q(wcm + 0x30) if wcm else None
        hs = []
        for k in range(1, 12):
            ec = x.q(ents + 0x38 * k) if ents else None
            hs.append(pno(ec) if ec else None)
        idle = x.d(x.base + 0x492AFD8)
        if sh is None or not mh:
            verdict = 'unreadable (stock path)'
        elif sh == mh:
            verdict = 'OURS (owner)'
        elif sh in hs:
            verdict = 'theirs (summoner present)'
        else:
            verdict = 'summoner NOT in entries 1..11 -> authority rule: %s' % ('OURS' if idle == 0 else 'theirs')
        m_ = x.q(c + 0x2470) if c else None
        mod = x.q(m_ + 0x18) if m_ else None
        nd = x.d(mod + 0x4A0) if mod else None
        return 'summoner no %s own-no %s entries-no %s idle %s -> %s; no-dead bit %s' % (
            '%x' % sh if sh is not None else '?', '%x' % mh if mh is not None else '?',
            ['%x' % h for h in hs if h], idle, verdict, (nd >> 2) & 1 if nd is not None else '?')

    def status(t):
        nodeath.set_nodeath(gw(a), True, 'bit', quiet=True)     # the game may clear it (0xEE1AD4): re-assert
        nodeath.set_nodeath(gw(o), True, 'bit', quiet=True)     # runkr2 fix: the rival too
        say('   rival safety: %s' % top_up(o))
        say('t=%3.0f s kin HP %s | %s | kindeath3 applied %s | owner HP %s' % (
            t, {w: kin_view(w, owner)['hp'] for w in ctx.games}, {w: hit_probe(w) for w in ctx.games}, built,
            master_hp(a)))

    probes = {w: own_probe(w) for w in ctx.games}
    say('kin ownership as the caves see it: %s' % probes)
    kd4 = {w: gw(w).d(gw(w).base + 0xC502CD0) not in (None, 0) for w in ctx.games}   # KAUTH4 cave present
    say('kindeath4 cave words present: %s' % kd4)
    # kin8 gate: with the owner's game not taking its own kin, no swing can tell anything (the 2026-11-16 run)
    if 'OURS (owner)' not in probes[a]:
        raise Skip('NOT JUDGED: ownership test wrong on the owner %s (%s); kindeath4 caves %s; no swing made' % (
            a, probes[a], kd4))
    bad = {w: probes[w] for w in ctx.games if w != a and 'theirs (summoner present)' not in probes[w]}
    if bad:                                  # kin9_review R1: every non-owner game must say "theirs"
        raise Skip('NOT JUDGED: ownership test wrong on the rival(s) %s (needs "theirs (summoner present)"); '
                   'kindeath4 caves %s; no swing made' % (bad, kd4))
    # control (kin5_notes 10): an ordinary enemy from the RIVAL's own loaded list (npcs.find: the list kill.py uses),
    # nearest to the kin there, hit with killchr.py (kill.py's sequence, no HP write). Its HP falling on the rival =
    # the swings land; falling on the owner too (its copy of the same handle) = forwarding works for enemies.
    control = 'no control enemy in %s\'s own list' % o
    try:
        import npcs
        kpos = gw(o).chr_pos(k0[o]['chr']) or my_pos(o)
        skip = kin_chrs(o)
        rows = [r for r in npcs.find(gw(o).m) if r['phys'] and r['flags'] & 0xFF == 5 and r['chr'] not in skip]
        live = []
        for r in rows:
            v = gw(o).chr_hp(r['chr'])
            hp_ = v[0] if isinstance(v, (tuple, list)) else v
            if hp_ and 0 < hp_ <= 3000:
                live.append((math.dist(kpos, r['pos']) if kpos else 0.0, r, hp_))
        live.sort(key=lambda z: z[0])
    except Exception as ex:
        live, control = [], 'control enemy search failed on %s: %s' % (o, ex)
    if os.environ.get('KD_CONTROL', '1') == '0':
        live, control = [], 'control enemy skipped (KD_CONTROL=0; "rival swings LAND" shown 15:16 and 15:27)'
    if live and live[0][0] < 40.0:
        dist0, r, ohp0 = live[0]
        h = r['handle'] & 0xFFFFFFFF
        ea = sync_enemies(a).get(h)
        ahp0 = enemy_view(a, ea)['hp'] if ea else None
        rc, out_ = tool(['diag/twin/killchr.py', o, 'chr=%x' % r['chr'], 'rounds=16', 'every=4'],
                        min(45, max(10, ctx.left() - 230)), quiet=True)
        time.sleep(2.0)
        v1 = gw(o).chr_hp(r['chr'])
        ohp1 = v1[0] if isinstance(v1, (tuple, list)) else v1
        ea = sync_enemies(a).get(h)
        ahp1 = enemy_view(a, ea)['hp'] if ea else None
        land = ohp1 is not None and ohp1 < ohp0
        fwd = ahp0 is not None and ahp1 is not None and ahp1 < ahp0
        control = ('control enemy handle %x chr %x (%s\'s list, %.1f m from the kin): HP on %s %s -> %s, on %s %s -> %s: '
                   '%s; %s (killchr rc %s, tail %s)' % (
                       h, r['chr'], o, dist0, o, ohp0, ohp1, a, ahp0, ahp1,
                       'rival swings LAND' if land else 'rival swings MISS (no HP change on its own copy)',
                       'the driver applies them' if fwd else ('not on %s' % a if ahp0 is None else 'no change on %s' % a),
                       rc, ' / '.join((out_ or '').strip().splitlines()[-2:])))
    elif live:
        control = 'nearest control enemy in %s\'s list is %.0f m from the kin (> 40 m): none used' % (o, live[0][0])
    say(control)
    probe0 = {w: hit_probe(w) for w in ctx.games}
    say('%s: kin out (%s); %s attacks its copy chr %x with killchr.py (kill.py sequence, no HP write anywhere); '
        'KIN_AUTH built in: %s; kin probe %s' % (a, out_how, o, k0[o]['chr'], built, probe0))
    # v3 (2026-11-17, after "NO HIT in 16 s"): (a) the rival stands 1.5 m from its copy of the kin, at its height,
    # and both stand still for 3 s (the owner has the no-dead bit and gets no input, so the kin, which follows its
    # owner, stays put); (b) up to KD_ATTACK s of attack: killchr.py first (kill.py's sequence: teleport 1.5 m at
    # the target's height, face, StickR lock-on, R presses, re-aimed every 4), strike.py mode=R (no lock-on) after
    # KD_SWITCH s without a connect; a tool that ends early is started again; (c) a CONNECT = the kin's HP changed
    # on the RIVAL's game; a line every 5 s.
    kc_o = kin_view(o, owner)['chr']
    kp = gw(o).chr_pos(kc_o) if kc_o else None
    near_k = near_here(o, kp, 12.0) if pos_ok(kp) else []
    if near_k:
        say('%d live enemies within 12 m of the kin on %s (nearest %s m): the owner moves first' % (
            len(near_k), o, near_k[0][0]))
        safe_k, how_k = make_safe(ctx, a, owner, kill_r=12.0, clear_r=25.0, clear_secs=20.0)
        time.sleep(6.0)                                       # the kin follows its owner
        kc_o = kin_view(o, owner)['chr']
        kp = gw(o).chr_pos(kc_o) if kc_o else None
        near_k = near_here(o, kp, 12.0) if pos_ok(kp) else []
        prep += ' | before the attack: moved, safe %s (%s), enemies within 12 m of the kin on %s now %d' % (
            safe_k, how_k, o, len(near_k))
        say(prep.split(' | before the attack: ')[-1])
    if not pos_ok(kp):
        raise Skip("%s: its copy of the kin has no valid position (%s): no teleport" % (o, kp))
    pa0 = gw(a).chr_pos(kin_view(a, owner)['chr'])
    tp(ctx, o, (kp[0] + 1.5, kp[1], kp[2]), math.atan2(kp[0] - (kp[0] + 1.5), 0.0))
    time.sleep(3.0)
    pa1 = gw(a).chr_pos(kin_view(a, owner)['chr'])
    kp1 = gw(o).chr_pos(kin_view(o, owner)['chr'])
    mp = my_pos(o)
    say('still 3 s: kin (owner copy) moved %s m; rival copy vs real kin gap %s m; rival %s m from its copy' % (
        round(math.dist(pa0, pa1), 2) if pa0 and pa1 else '?', round(math.dist(pa1, kp1), 2) if pa1 and kp1 else '?',
        round(math.dist(mp, kp1), 2) if mp and kp1 else '?'))
    log_path = WS / 'diag' / 'twin' / ('kin_death_%s.log' % o)
    log_f = open(log_path, 'w')

    def launch(method):
        c_ = kin_view(o, owner)['chr']
        if method == 'killchr':
            args_ = [PY, 'diag/twin/killchr.py', o, 'chr=%x' % c_, 'seconds=%d' % KD_ATTACK, 'every=4']
        else:
            args_ = [PY, 'diag/twin/strike.py', o, 'c:0x%x' % c_, 'mode=R', 'seconds=%d' % KD_ATTACK,
                     'games=%s' % ''.join(ctx.games)]
        log_f.write('==== %s\n' % ' '.join(args_[1:]))
        log_f.flush()
        say('$ python ' + ' '.join(args_[1:]) + '  >> ' + str(log_path))
        return subprocess.Popen(args_, cwd=WS, stdout=log_f, stderr=subprocess.STDOUT, text=True,
                                env=dict(os.environ, TWIN_GAMES=CFG['games']))

    # kin10 (2026-11-17): with KIN4_PRED the rival's copy never changes HP locally (by design) and follows the owner
    # only through the status word, so a CONNECT = the kin's HP DROPPING ON THE OWNER's game (a). The rival's copy
    # changes are counted separately (copy_moves) to show whether the owner's value comes back to it.
    method, restarts, connects, t_conn = 'killchr', 0, 0, None
    prev_a, prev_o, copy_moves, drops = kin_view(a, owner)['hp'], kin_view(o, owner)['hp'], 0, []
    proc = launch(method)
    t_atk = time.time()
    t_copy = None
    t_status = 0.0
    try:
        while time.time() - t_atk < KD_ATTACK and ctx.left() > 60:
            look()
            h_a = kin_view(a, owner)['hp']
            if h_a is not None and prev_a is not None and h_a < prev_a:
                connects += 1
                t_conn = time.time() - t_atk
                drops.append((round(t_conn, 1), prev_a, h_a, method))
            if h_a is not None:
                prev_a = h_a
            h_o = kin_view(o, owner)['hp']
            if h_o is not None and prev_o is not None and h_o != prev_o:
                copy_moves += 1
            if h_o is not None:
                prev_o = h_o
            if time.time() - t_start >= t_status:
                status(time.time() - t_start)
                say('   attack t=%3.0f s method %s (restarts %d) | CONNECTS %d (kin HP dropped on the owner %s; last at '
                    '%s) | rival copy %s HP changes %d (now %s, owner %s)' % (
                        time.time() - t_atk, method, restarts, connects, a,
                        '%.0f s' % t_conn if t_conn is not None else 'never', o, copy_moves, prev_o, prev_a))
                t_status += 5.0
            if dead_on(a):
                break
            if t_copy is None and any(dead_on(w) for w in ctx.games if w != a):
                t_copy = time.time()
            if t_copy is not None and time.time() - t_copy > 20:
                break
            if method == 'killchr' and connects == 0 and time.time() - t_atk > KD_SWITCH:
                proc.kill()
                proc.wait(timeout=10)
                method = 'strike'
                say('   no connect in %d s with killchr (lock-on): strike.py without lock-on' % KD_SWITCH)
                proc = launch(method)
            elif proc.poll() is not None:
                if t_copy is not None or dead_on(a):
                    break
                restarts += 1
                if restarts > 6:
                    say('   %s ended %d times: stopping the attack' % (method, restarts))
                    break
                time.sleep(1.0)
                proc = launch(method)
            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        log_f.close()
    say('attack over: %.0f s, method %s, connects %d on the owner %s (last %s; drops %s), rival copy HP changes %d '
        '(copy %s vs owner %s at the end: %s), restarts %d' % (
            time.time() - t_atk, method, connects, a, '%.0f s' % t_conn if t_conn is not None else 'never', drops,
            copy_moves, prev_o, prev_a, 'FOLLOWS' if prev_o == prev_a else 'COPY NOT UPDATED from the owner', restarts))
    try:
        ff = open(log_path).read().strip().splitlines()
        ff = ff[:1] + ff[-3:]
    except Exception:
        ff = []
    status(time.time() - t_start)
    probe1 = {w: hit_probe(w) for w in ctx.games}
    say('killchr head/tail: %s | states %s | HP %s | kin probe after %s | ownership %s' % (
        ' / '.join(ff), seq, hp, probe1, {w: own_probe(w) for w in ctx.games}))
    if not dead_on(a):
        o_fell = any(y < x for x, y in zip(hp[o], hp[o][1:]) if x is not None and y is not None)
        a_fell = any(y < x for x, y in zip(hp[a], hp[a][1:]) if x is not None and y is not None)
        if t_copy is not None or (o_fell and not a_fell):
            return 'FAIL', ("REAL GAP: %s's copy %s while the owner's kin stayed in state 3 with HP %s (rival hits "
                            "not applied on the owner; kindeath3 applied %s, kin5_notes.md 4)" % (
                                o, 'died' if t_copy is not None else 'lost HP', hp[a][-1], built)), \
                'states %s | HP %s | %s | kin probe before %s after %s' % (seq, hp, control, probe0, probe1)
        if not o_fell and not a_fell:
            raise Skip('NO HIT: nothing landed in %.0f s (kin HP unchanged on every game): not judged | states %s | '
                       '%s | kin probe before %s after %s' % (time.time() - t_start, seq, control, probe0, probe1))
        raise Skip('no kill within %.0f s: states %s HP %s | %s | kin probe before %s after %s (last attacker = '
                   "the rival's own player handle on the rival = its swings land; also on the owner = the hit reached "
                   'it but was not applied; neither = swings missed, kin5_notes 9)' % (
                       time.time() - t_start, seq, hp, control, probe0, probe1))
    while time.time() - t_start < 300 and ctx.left() > 45:      # wait-revive of every game
        look()
        if all(first(w, 7) is not None and first(w, 2, first(w, 7)) is not None for w in ctx.games):
            break
        time.sleep(0.3)
    # kin5_notes 8 (v2 criteria): the owner's HP falls with the rival's hits, the copies stay within one hit of
    # each other while the kin lives, and 7 -> 8 -> 9 -> 2 shows on EVERY game, starting after the owner's HP is 0.
    drops = [x - y for x, y in zip(hp[a], hp[a][1:]) if x is not None and y is not None and y < x]
    one_hit = max(drops) if drops else 0
    t_hp0 = next((t for t, v in pairs if v.get(a) is not None and v[a] <= 0), None)
    # runmix_review (2026-11-16): a copy follows the owner only through the assist's status word (kin10 notes:
    # about 6 s late), so each copy is compared with the owner's values of the last KD_LAG s, not only with the
    # owner's value at the same read: two quick hits inside the lag are no "gap".
    def owner_near(t):
        return [u[a] for tu, u in pairs if t - KD_LAG <= tu <= t and u.get(a) is not None]

    gaps = [max(min(abs(v[w] - x) for x in (owner_near(t) or [v[a]])) for w in ctx.games if v.get(w) is not None)
            for t, v in pairs if v.get(a) is not None and v[a] > 0 and (t_hp0 is None or t < t_hp0)]
    worst = max(gaps) if gaps else 0
    falls = len(drops) >= 2 and t_hp0 is not None
    close = worst <= one_hit
    # kin11 (2026-11-17): 7 -> 8 -> 9 -> 2 on a copy can take less than one read (the revive-ok bit comes with the
    # owner's 0x54 kind 2 before the copy's 9 is sampled). runkd4 12:12: A 7@99.7, then 2 inside the 4-s wait loop
    # (the loop broke on it), printed as "2@None" because 2 was looked for only after a 9. What a player sees is
    # the kin gone (state 2) in order after the owner's HP 0: judged on 7 and 2 (2 within KD_GONE s of 7); 8 / 9
    # must be in order when seen; unseen 8 / 9 make a PARTIAL only on the OWNER (there they last seconds).
    order, checks, no8 = {}, [], []
    for w in ctx.games:
        t7 = first(w, 7)
        t8 = first(w, 8, t7) if t7 is not None else None
        t9 = first(w, 9, t7) if t7 is not None else None
        t2 = first(w, 2, t9 if t9 is not None else (t8 if t8 is not None else t7)) if t7 is not None else None
        after0 = t7 is not None and t_hp0 is not None and t7 >= t_hp0 - 0.3
        seen = [t for t in (t7, t8, t9, t2) if t is not None]
        ok = after0 and t2 is not None and seen == sorted(seen) and t2 - t7 <= KD_GONE
        if ok and (t8 is None or t9 is None) and w == a:
            no8.append(w)
        line = '%s 7@%s 8@%s 9@%s 2@%s (seq %s)' % (w, t7, t8, t9, t2,
                                                    [x for x in seq[w] if x[1] >= (t7 or 0)][:8])
        line += '' if ok else (' 7 BEFORE THE OWNER\'S HP 0' if t7 is not None and not after0 else ' OUT OF ORDER / MISSING')
        if w != a:
            line += ' revive-ok bit@%s' % cc_at[w]
        order[w] = ok
        checks.append(line)
    again, resum = None, ''
    if os.environ.get('KD_RESUMMON_INPUT') == '1':
        # runkr2 (b), 2026-11-16: re-summon with the owner's REAL input (hold Y + D-pad = summon_out_input, the
        # path kin_summon / kin_recall use) instead of the step+0xC8 write; a round every 5 s until the kin is out
        # or 150 s. Reports how long after the owner's own state 2 the kin came back (the game's wait for a kin
        # that died). Judged separately (RESUMMON-INPUT PASS / FAIL in the values); the kin_death verdict is as before.
        t2a = first(a, 2, first(a, 7)) if first(a, 7) is not None else None
        t_r, rounds, ok2, how2 = time.time(), 0, False, 'not tried (time budget)'
        flags = []      # review (helper 4): step+0xC8 before each press; a 1 = a tool's request flag still pending
        while time.time() - t_r < 150 and ctx.left() > 25:
            rounds += 1
            stp = kin_step(a, owner)
            flags.append(gw(a).b(stp + 0xC8) if stp else None)
            ok2, how2 = summon_out_input(ctx, a, owner)
            if ok2:
                break
            time.sleep(5.0)
        t_out = time.time() - t_start
        time.sleep(2.0)
        states = {w: kin_view(w, owner)['state'] for w in ctx.games}
        # review (helper 4): PASS only for a real press that took the kin 2 -> 3 ('Y + ...'), never for "already out"
        # / "came out by itself", and only if step+0xC8 was 0 before every press (else the tool's flag did it)
        real = ok2 and how2.startswith('Y + ') and all(f == 0 for f in flags)
        good = real and all(s == 3 for s in states.values())
        how2 += '; step+0xC8 before presses %s' % flags
        resum = 'RESUMMON-INPUT %s: %s after %d round(s); out %s s after the owner\'s state 2 (2@%s, out@%.1f); ' \
                'states now %s | ' % ('PASS' if good else 'FAIL', how2, rounds,
                                      '%.1f' % (t_out - t2a) if t2a is not None and ok2 else '-', t2a, t_out, states)
    elif seq[a][-1][0] == 2 and ctx.left() > 40:
        ok2, how2 = kin_summon_out(ctx, owner, wait=30.0)
        time.sleep(2.0)
        again = (ok2, how2, {w: kin_view(w, owner)['state'] for w in ctx.games})
    vals = resum + 'safety: %s | ' % prep + '%s | owner HP 0 at %s | owner drops %s (one hit = %s) | worst copy gap %s | HP %s | re-summon %s | ' \
           'KIN_AUTH %s' % ('; '.join(checks), t_hp0, drops, one_hit, worst, hp, again, built)
    if falls and close and all(order.values()) and not no8:
        return 'PASS', 'owner HP fell with the hits, copies within one hit, 7 -> (8 -> 9) -> 2 on every game ' \
                       'after the owner reached 0 (2 within %d s; a copy\'s 8 / 9 may be shorter than a read)' % (
                           KD_GONE), vals
    if falls and close and all(order.values()):
        return 'PARTIAL', 'all right, but state 8 or 9 was not seen on the owner %s (shorter than a read?)' % no8, vals
    return 'FAIL', 'falls %s, copies within one hit %s (worst gap %s, one hit %s), order after the owner\'s 0 %s' % (
        falls, close, worst, one_hit, order), vals


# =============================================================== Function Menu (diag/net/menus_notes.md)
def fmenu(w, dpad, hold=40, pick=10):
    """hold Y (= Action, KeyAssignDisplayParam row 24 key 10: hold opens the Function Menu), press a D-pad direction
    while Y is still held, release. Item directions (menus_notes.md 5): Right = place pin (live: B's own map got the
    pin), Down = summon / dismiss kin [I: combo row 105 = row 24 + row 32, key 5 = D-pad Down, verified live as Use
    Item], Up = petition for alliance [I], Left = observation [I]."""
    tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [
        {'buttons': ['Y'], 'frames': hold}, {'buttons': ['Y', dpad], 'frames': pick},
        {'buttons': ['Y'], 'frames': 10}, {'frames': 30}]}})


KIN_DIRS = ('Down', 'Up')   # summon / dismiss kin: Down first (param combo), Up (the old guess) as the fall-back


KINRECALL_SITE, KINRECALL_STOCK = 0xD838A8, 0xAA1303E0   # kinrecall_live.py hook word / stock `mov x0, x19`
KINRECALL_HOOK_WORD = 0x17FE0D49                          # kinrecall_b_live.py HOOK_WORD (b to the KREC cave)


def owner_hold(w):
    """the owner-side hold that kinrecall_b keeps (0xD8375C): [[chr+0x2470]+0]+0x10 bit 6 of our player, and the
    +0xA58 handle the stock then checks (a lock-on / combat target [I]; 0xFFFFFFFF / 0 = none)"""
    x = gw(w)
    c = x.me()[0]
    m = x.q(c + 0x2470) if c else None
    ctrl = x.q(m) if m else None
    b = x.b(ctrl + 0x10) if ctrl else None
    h = x.d(c + 0xA58) if c else None
    return {'held': None if b is None else bool(b & 0x40), 'target': h,
            'locked': h not in (None, 0, 0xFFFFFFFF) and (h & 0x0FFFFFFF) != 0x0FFFFFFF}


def htext(v):
    return 'held %s target %s' % (v['held'], 'none' if not v['locked'] else '%08x' % v['target'])


def near_here(w, pos, radius):
    """[(dist, hp, chr)] live non-kin enemies within radius of pos on game w, nearest first"""
    kc, out = kin_chrs(w), []
    for e in sync_enemies(w).values():
        if e['chr'] in kc:
            continue
        v = enemy_view(w, e)
        if v['hp'] and v['hp'] > 0 and v['pos'] and pos and math.dist(pos, v['pos']) <= radius:
            out.append((round(math.dist(pos, v['pos']), 1), v['hp'], e['chr']))
    return sorted(out)


START_MED_G = 0x5B44EA0     # start-point mediator (startarea.py MEDIATOR_G): decided list +0x290, 0x68 each, pos +0x40


def start_spots(w):
    """the start points of this phase as game w decided them (startarea.py's decided list; the Phase I start
    areas were quiet in the coordinator's runs) -> [(x, y, z)]"""
    x = gw(w)
    m = x.g(START_MED_G)
    n = x.q(m + 0x5D8) if m else None
    out = []
    for k in range(min(n or 0, 8)):
        p = x.f3(m + 0x290 + k * 0x68 + 0x40)
        if p and all(v == v for v in p) and any(abs(v) > 1.0 for v in p):
            out.append(p)
    return out


def make_safe(ctx, a, owner, kill_r=25.0, clear_r=40.0, clear_secs=60.0):
    """TEST ONLY (kin6_notes.md 4): no live enemy within kill_r of the owner a. At most clear_secs of killing
    (killchr.py, real hits, nearest first, 10 s per call, a progress line every call); if enemies are still near,
    move the owner at once (the kin follows) beside another player, else to a start point of this phase
    (start_spots), with no enemy within clear_r. -> (safe, text)"""
    log = []
    t0 = time.time()
    while time.time() - t0 < clear_secs and ctx.left() > 100:
        near = near_here(a, my_pos(a), kill_r)
        if not near:
            break
        d, hp, c = near[0]
        rc, _ = tool(['diag/twin/killchr.py', a, 'chr=%x' % c, 'seconds=10', 'every=3'], timeout=30, quiet=True)
        log.append('kill %x at %.0f m rc %s' % (c, d, rc))
        say('kin_recall %s: clearing %.0f s, %d enemies within %.0f m, hit %x (HP %s) rc %s' % (
            a, time.time() - t0, len(near), kill_r, c, hp, rc))
    left = near_here(a, my_pos(a), kill_r)
    if left:
        spots = [('beside %s' % w, my_pos(w)) for w in ctx.games if w != a]
        spots += [('start point %d' % i, p) for i, p in enumerate(start_spots(a))]
        moved = None
        for name, spot in spots:
            if spot and not near_here(a, spot, clear_r) and not enemies_near(ctx, spot, clear_r):
                tp(ctx, a, (spot[0] + 2.0, spot[1] + 0.3, spot[2]))
                time.sleep(6.0)                               # the kin follows its owner
                moved = name
                break
        log.append('moved %s' % moved if moved else 'no quiet spot among %d (%s)' % (
            len(spots), ', '.join(n for n, _ in spots)))
        say('kin_recall %s: %s' % (a, log[-1]))
        left = near_here(a, my_pos(a), kill_r)
    me = my_pos(a)
    kin = next((k for k in KS.kins(gw(a))[1] if k['owner'] == owner), None)
    kd = round(math.dist(me, kin['pos']), 1) if kin and kin.get('pos') and me else None
    far = near_here(a, me, clear_r)
    return not left, '%s | enemies within %.0f m %d, within %.0f m %d (nearest %s m) | kin %s m from the owner' % (
        '; '.join(log) or 'no kill needed', kill_r, len(left), clear_r, len(far), far[0][0] if far else None, kd)


def owner_alive(a, secs=45.0):
    """wait until the owner a has HP > 0 for 3 s in a row (a dead owner sends a Summon kin to 5 RequestForceUnsummon:
    SummonState 0xD833E8..0xD8353C, owner chr HP < 1). -> (alive, text)"""
    t0, ok_since = time.time(), None
    while time.time() - t0 < secs:
        hp = master_hp(a)
        if hp and hp > 0:
            ok_since = ok_since or time.time()
            if time.time() - ok_since >= 3.0:
                return True, 'owner HP %s' % hp
        else:
            ok_since = None
        time.sleep(0.5)
    return False, 'owner %s HP %s for %.0f s (dead / respawning)' % (a, master_hp(a), secs)


def summon_out_input(ctx, a, owner):
    """REAL INPUT: bring the kin of owner a out (state 3) with hold Y + D-pad (KIN_DIRS: Down, then Up) = Function
    Menu 'Summon / Dismiss Kin' (a toggle: only pressed while the kin is in 2 Unsummon). Waits for the owner to be
    alive first and for a kin in 4/5/8/9 to reach 2. -> (ok, text)"""
    st = kin_view(a, owner)['state']
    if st == 3:
        return True, 'already out (state 3)'
    alive, ahow = owner_alive(a)
    if not alive:
        return False, ahow
    t0 = time.time()
    while st != 2 and time.time() - t0 < 25 and ctx.left() > 40:
        time.sleep(1.0)
        st = kin_view(a, owner)['state']
        if st == 3:
            return True, 'came out by itself (state 3)'
    if st != 2:
        return False, 'kin state %s %s after 25 s, not 2 Unsummon (5 = RequestForceUnsummon: the owner had HP 0 '             'while it was out; %s)' % (st, {4: 'RequestUnsummon', 5: 'RequestForceUnsummon', 8: 'FinishUnsummon',
                                            9: 'WaitRevive'}.get(st, '?'), ahow)
    tried = []
    for d in KIN_DIRS:
        if ctx.left() < 30:
            break
        tried.append(d)
        fmenu(a, d)
        t1 = time.time()
        while time.time() - t1 < 12:
            st = kin_view(a, owner)['state']
            if st == 3:
                return True, 'Y + %s: 2 -> 3 in %.1f s (%s)' % (d, time.time() - t1, ahow)
            if st != 2:
                break
            time.sleep(0.3)
        if st not in (2, 3):
            return False, 'Y + %s took the kin to state %s, not 3' % (d, st)
    return False, 'Y + %s did not bring the kin out (state %s)' % (' / Y + '.join(tried), st)


def recall_once(ctx, a, stage=None):
    """one owner a: kin out, area made safe, lock-on released, 5 s, Y + Down (then Up) = dismiss watched 15 s,
    then the same again = summon. stage['now'] names the current step for the progress line. -> (status, why, vals)"""
    stage = stage if stage is not None else {}
    saved = ctx.actor
    ctx.actor = a
    try:
        stage['now'] = 'kin out'
        owner, _ = ensure_kin(ctx)
        ok, how = summon_out_input(ctx, a, owner)
        if not ok:
            return 'SKIP', 'kin of %s not out before the recall: %s' % (a, how), ''
        stage['now'] = 'making the area safe'
        safe, safe_how = make_safe(ctx, a, owner)
        stage['now'] = 'lock-on release'
        h0 = owner_hold(a)
        lock_how = 'no lock-on'
        for i in range(2):                                    # StickR toggles the lock-on (killchr.py set it)
            if not owner_hold(a)['locked']:
                break
            tctl.call(a, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4},
                                                                         {'frames': 20}]}})
            time.sleep(1.0)
            lock_how = 'StickR x%d -> %s' % (i + 1, htext(owner_hold(a)))
        ok, how = summon_out_input(ctx, a, owner)             # a kin that died in the fight (real input)
        if not ok:
            return 'SKIP', 'kin of %s not out after making the area safe: %s | %s' % (a, how, safe_how), ''
        if ctx.left() < 50:
            return 'SKIP', 'owner %s: only %.0f s left after making the area safe (%s): the press not tried' % (
                a, ctx.left(), safe_how), ''
        time.sleep(5.0)
        seq = {w: [kin_view(w, owner)['state']] for w in ctx.games}
        in4 = {'max': 0.0, 'held': 0, 'locked': 0, 'reads': 0}

        def watch(until, secs):
            secs = max(3.0, min(secs, ctx.left() - 8))
            t0 = time.time()
            try:
                import nodeath
                nodeath.set_nodeath(gw(a), True, 'bit', quiet=True)   # the game may clear it: re-assert
            except Exception:
                pass
            while time.time() - t0 < secs:
                for w in ctx.games:
                    s_ = kin_view(w, owner)['state']
                    if s_ != seq[w][-1]:
                        seq[w].append(s_)
                    if w == a and s_ == 4:
                        st = kin_step(a, owner)
                        e0 = gw(a).f(st + 0xE0) if st else None
                        if e0 is not None and e0 == e0:
                            in4['max'] = max(in4['max'], round(e0, 1))
                        hv = owner_hold(a)
                        in4['reads'] += 1
                        in4['held'] += 1 if hv['held'] else 0
                        in4['locked'] += 1 if hv['locked'] else 0
                if all(seq[w][-1] == until for w in ctx.games):
                    return True
                time.sleep(0.3)
            return False

        used, back, tried = None, False, []
        for d in KIN_DIRS:
            if ctx.left() < 60:
                break
            tried.append(d)
            stage['now'] = 'Y + %s (dismiss), watching' % d
            fmenu(a, d)
            back = watch(2, 15)
            if back or seq[a][-1] != 3:
                used = d
                break
            time.sleep(2.0)
        s1 = shot(a, 'rs_kin_recall_%s' % a)
        near_now = near_here(a, my_pos(a), 25.0)
        out, sum_how = None, ''
        if back:
            time.sleep(3.0)
            for d2 in [used] + [d for d in KIN_DIRS if d != used]:   # kin12: the same press, then the other dir
                if ctx.left() < 30:
                    break
                stage['now'] = 'Y + %s (summon again), watching' % d2
                fmenu(a, d2)
                out = watch(3, 20)
                stp = kin_step(a, owner)
                sum_how += 'Y+%s: owner state %s, step +0xC0 %s +0xC8 %s; ' % (
                    d2, seq[a][-1], gw(a).b(stp + 0xC0) if stp else None, gw(a).b(stp + 0xC8) if stp else None)
                if out or seq[a][-1] != 2:
                    break
        role = 'host' if a == ctx.host else 'guest'
        hold4 = 'in state 4: %d reads, owner held %d, lock target %d' % (in4['reads'], in4['held'], in4['locked'])
        sa = seq[a]
        to8 = any(sa[i] == 4 and sa[i + 1] == 8 for i in range(len(sa) - 1))
        fired = 'KINRECALL 6 s path %s (owner state 4 up to %.1f s, then %s)' % (
            'FIRED' if to8 and in4['max'] >= 5.5 else 'not fired', in4['max'], '8' if to8 else 'no 8')
        hold4 = fired + '; ' + hold4
        vals = 'owner %s (%s) | safe %s: %s | before the press %s; %s | tried Y+%s, worked %s | state sequences %s | ' \
               '%s | enemies within 25 m after %d | owner +0xE0 in state 4 up to %.1f s | shot %s' % (
                   a, role, safe, safe_how, htext(h0), lock_how, '/Y+'.join(tried), used, seq, hold4, len(near_now),
                   in4['max'], s1)
        if any(5 in sq for sq in seq.values()):
            return 'SKIP', ('NOT JUDGED: state 5 RequestForceUnsummon seen (%s): the owner chr had HP < 1 '
                            '(0xD833FC), not a recall rule; owner master HP now %s' % (
                                {w: sq for w, sq in seq.items() if 5 in sq}, master_hp(a))), vals
        if back and out:
            return 'PASS', '%s owner %s: 3 -> 4 -> 2 and 2 -> 3 on every game (safe place %s)' % (role, a, safe), vals
        if back:
            if seq[a][-1] == 2:
                where = ('the OWNER %s itself stayed in 2 (+0xC0 0 = press not taken, 1 = summon refused): '
                         'not a sync gap' % a)
            else:
                where = 'owner %s at %s; not 3 on %s' % (a, seq[a][-1], [w for w in ctx.games if seq[w][-1] != 3])
            return 'PARTIAL', '%s owner %s: Y + %s dismissed the kin (3 -> 2) on every game; the summon again ' \
                              'failed: %s | %s' % (role, a, used, where, sum_how), vals
        if used:
            if not safe or near_now:
                why = 'enemies still near (%d within 25 m): the stock in-combat wait is possible' % len(near_now)
            elif in4['held'] or in4['locked']:
                why = "the owner was held (%s): the game's own hold, kinrecall_b keeps it" % hold4
            else:
                why = 'REAL GAP: no enemy within 25 m, no lock-on, owner not held, still no answer'
            return 'FAIL', '%s owner %s: Y + %s took the kin to %s but not to state 2 on every game; %s' % (
                role, a, used, seq[a][-1], why), vals
        return 'FAIL', '%s owner %s: neither Y + %s dismissed the kin on the owner (kin still state 3)' % (
            role, a, ' nor Y + '.join(tried)), vals
    except Skip as e:
        return 'SKIP', '%s: %s' % (a, e), ''
    finally:
        ctx.actor = saved


@test('kin_recall', 28, 'phase2', 240)
def t_kin_recall(ctx):
    """Real input, no memory write for the recall itself: with the actor's kin out (state 3), hold Y + a D-pad
    direction on the actor (the owner; one owner per call, run it again with actor=<host> for the host owner) =
    Function Menu 'Summon / Dismiss Kin' (menus_notes.md 5: Down by the key-assign data, Up tried second). Verified
    only by the kin state: 3 -> 2 Unsummon (through 4) on EVERY game; then the same input again: 2 -> 3 on every game.
    Before the press the area is made safe (make_safe: at most 60 s of killing within 25 m, then at once a move
    beside another player or to a start point of this phase with no enemy within 40 m), the lock-on is released and
    5 s pass. A progress line every ~10 s; a time-out ends with SKIP and the reason. The result names whether the
    KINRECALL hook (kinrecall_b, word 0xD838A8) is built in and whether its 6 s path fired (owner in state 4 for
    >= 5.5 s on step+0xE0, then 8 FinishUnsummon); a FAIL names the owner's hold (kinrecall_b)."""
    import threading
    hook = {w: gw(w).d(gw(w).base + KINRECALL_SITE) for w in ctx.games}
    built = {w: ('built in' if h == KINRECALL_HOOK_WORD else 'stock' if h == KINRECALL_STOCK else
                 'other %s' % (None if h is None else '%08x' % h)) for w, h in hook.items()}
    stage = {'now': 'start'}
    t_start = time.time()

    def beat():                                        # a progress line every 10 s, whatever the test is doing
        while not stop.wait(10.0):
            say('kin_recall %s: %.0f s, %s, %.0f s of the budget left' % (
                ctx.actor, time.time() - t_start, stage['now'], ctx.left()))
            if ctx.left() < -25:                       # a tool call hangs: the RESULT line must still come
                print('RESULT %-15s %-7s row %-2s: %s | %s (%.0f s)' % (
                    'kin_recall', 'SKIP', 28, 'time-out: stuck in %s, 25 s past the budget' % stage['now'],
                    'KINRECALL hook %s' % built, time.time() - t_start), flush=True)
                os._exit(3)
    stop = threading.Event()
    threading.Thread(target=beat, daemon=True).start()
    try:
        stage['now'] = 'settling'
        settle(ctx, 20.0, 30.0)
        stage['now'] = 'recall (kin out, area safe, press)'
        # kin7 (2026-11-17): state 5 RequestForceUnsummon comes ONLY from SummonState when the OWNER chr's HP
        # [[owner+0x2470]+0x18]+0x290 < 1 (0xD833E8..0xD8353C); no combat or cooldown rule is on that path. The four
        # inconclusive runs = the owner died during make_safe / the wait. TEST ONLY: the owner gets the engine's
        # no-dead bit on its own player chr (as kin_death), re-asserted by the watch, cleared at the end.
        import nodeath
        nd_b, nd_a = nodeath.set_nodeath(gw(ctx.actor), True, 'bit', quiet=True)
        if nd_a is None:
            raise Skip('owner %s: no-dead bit could not be set (%s)' % (ctx.actor, nd_b.get('why')))
        say('TEST ONLY owner %s protected: no-dead bit on its own player chr (%s)' % (ctx.actor, nodeath.fmt(nd_a)))
        try:
            st, why, vals = recall_once(ctx, ctx.actor, stage)
        finally:
            try:
                nodeath.set_nodeath(gw(ctx.actor), False, 'bit', quiet=True)
                say('owner %s: no-dead bit off again' % ctx.actor)
            except Exception as ex:
                say('owner %s: no-dead bit NOT cleared (%s): run  python diag/twin/nodeath.py %s off' % (
                    ctx.actor, ex, ctx.actor))
    except Skip as e:
        st, why, vals = 'SKIP', str(e), ''
    except Timeout as e:
        st, why, vals = 'SKIP', 'time-out during %s: %s' % (stage['now'], e), ''
    finally:
        stop.set()
    vals = 'KINRECALL hook %s || %s' % (built, vals)
    return st, why, vals


# =============================================================== row 54: map pins and player markers
def alliance_pairs(w):
    """[(a, b)] player-number pairs of the alliance deque AM+0x10..+0x38 on game w (alliance_notes.md 1.2) or None"""
    x = gw(w)
    am = x.g(AM_G)
    if not am:
        return None
    mp, start, n = x.q(am + 0x10), x.q(am + 0x30) or 0, x.d(am + 0x38) or 0
    out = []
    for i in range(min(n, 8)):
        k = start + i
        blk = x.q(mp + 8 * (k >> 7)) if mp else None
        e = blk + (k & 0x7F) * 0x20 if blk else None
        if e:
            out.append((x.i(e), x.i(e + 4)))
    return out


def relation(ctx, w):
    """'ally' or 'rival' of game w's player to the actor, as the actor's game holds the alliances"""
    pa, pw = local_no(ctx.actor), local_no(w)
    pairs = alliance_pairs(ctx.actor) or []
    return 'ally' if any({pa, pw} == {x, y} for x, y in pairs) else 'rival'


def map_shots(ctx, tag, games=None):
    out = {}
    for w in games or ctx.games:
        press(w, 'Plus', 6, 60)
        time.sleep(1.5)
        out[w] = shot(w, tag)
        for _ in range(3):
            press(w, 'B', 5, 15)
    return out


def mapdiff1(before, after):
    """one pair through mapdiff.py: ('PASS' new blob / 'FAIL' none / 'UNUSABLE' / 'NOSHOT', blob count, last line)"""
    if before.startswith('shot failed') or after.startswith('shot failed'):
        return 'NOSHOT', None, '%s / %s' % (before, after)
    rc, out = tool(['diag/twin/mapdiff.py', before, after], 60, quiet=True)
    last = [l for l in (out or '').splitlines() if l.startswith('MAPDIFF')]
    m = re.search(r': (\d+) blob\(s\)', out or '')
    v = last[-1].split()[1].rstrip(':') if last else 'NOLINE'
    return v, int(m.group(1)) if m else None, (last[-1] if last else (out or '').strip()[-120:])


R_BLOB = re.compile(r'blob at x ([\d.]+) y ([\d.]+)\s+size (\d+)\s+colour after \((\d+), (\d+), (\d+)\)')


def map_blobs(before, after):
    """[(x, y, size, (r, g, b))] new blobs of one pair (mapdiff.py lines), or None when the pair is not usable"""
    if before.startswith('shot failed') or after.startswith('shot failed'):
        return None
    rc, out = tool(['diag/twin/mapdiff.py', before, after], 60, quiet=True)
    if 'UNUSABLE' in (out or ''):
        return None
    return [(float(m[1]), float(m[2]), int(m[3]), (int(m[4]), int(m[5]), int(m[6]))) for m in R_BLOB.finditer(out or '')]


PIN_WIN = 0.025        # pin window: fraction of the image width around the actor's new pin blob
PIN_RGB = 60           # and at most this colour distance (max channel) from it


def near_pin(pins, blobs):
    """blobs of another game that sit inside the window of one of the actor's pin blobs, with a similar colour"""
    return [b for b in blobs for p in pins if math.dist(b[:2], p[:2]) <= PIN_WIN and
            max(abs(u - v) for u, v in zip(b[3], p[3])) <= PIN_RGB]


@test('pin_place', 54, 'phase1', 120)
def t_pin_place(ctx):
    """Real input: the actor holds Y + D-pad Right = Function Menu 'place a pin' toward where the camera faces. Map
    shot (Plus) on every game before and after, judged per game by mapdiff.py (one pair each). Who should see it
    (menus_notes.md 6): the placer always; a RIVAL never (pins are a personal map aid in the game's text, and the
    only pin code found is the local HUD list; no pin message is known); an ALLY is not decided by the data (INFO,
    reported, not judged). Run it once per match: a second Y + Right REMOVES the pin (LineHelp 130413)."""
    a = ctx.actor
    rel = {w: relation(ctx, w) for w in ctx.games if w != a}
    before = map_shots(ctx, 'rs_pin_before')
    time.sleep(1.0)
    fmenu(a, 'Right')
    time.sleep(3.0)
    s_act = shot(a, 'rs_pin_placed')
    after = map_shots(ctx, 'rs_pin_after')
    md = {w: mapdiff1(before[w], after[w]) for w in ctx.games}
    bl = {w: map_blobs(before[w], after[w]) for w in ctx.games}
    # the pin = the actor's own new blob(s); another game "shows" it only with a blob inside a small window around
    # that place (PIN_WIN of the width, similar colour): other map changes (clock, markers, events) do not count
    pins = bl.get(a) or []
    win = {w: near_pin(pins, bl[w] or []) for w in ctx.games if w != a}
    seen = {w: bool(win[w]) for w in win}
    seen[a] = md[a][0] == 'PASS' and bool(pins)
    vals = 'mapdiff %s | actor pin blob(s) %s | inside the %.3f window %s | relation to %s %s | actor view %s | '            'actor at %s' % ({w: '%s %s blob(s)' % v[:2] for w, v in md.items()},
                            [(round(p[0], 3), round(p[1], 3), p[2]) for p in pins], PIN_WIN,
                            {w: [(round(b[0], 3), round(b[1], 3)) for b in v] for w, v in win.items()}, a, rel, s_act,
                            fmt3(my_pos(a)))
    if any(md[w][0] in ('UNUSABLE', 'NOSHOT', 'NOLINE') for w in ctx.games) or any(v is None for v in bl.values()):
        return 'SKIP', 'a map pair is not usable (%s): take the shots again' % {w: v[2] for w, v in md.items()}, vals
    if not seen[a]:
        return 'FAIL', 'no new pin on the actor %s own map after Y + Right' % a, vals
    leak = [w for w, r in rel.items() if r == 'rival' and seen[w]]
    allies = {w: seen[w] for w, r in rel.items() if r == 'ally'}
    ally_txt = (' ; ally sees it: %s (INFO, design not known)' % allies) if allies else ''
    if leak:
        return 'FAIL', 'the pin of %s shows on the rival map(s) %s inside the pin window (pins are personal)' % (
            a, ''.join(leak)), vals
    return 'PASS', 'pin on the actor\'s own map, on no rival map%s' % ally_txt, vals


@test('markers', 54, 'phase1', 120)
def t_markers(ctx):
    """Other players' markers (TutorialBody 10201010: the map 'indicates the locations of other Bloodsworn', icon
    547025 'Other Bloodsworn (last known location)'). The actor is put 12 m from the host for 10 s (so the host has
    seen it); the observers (every other game) stand still. Map shots before / after on every observer, judged per
    observer by mapdiff.py. Expect: the host's map changes (the actor's marker moved / appeared); other observers
    are reported with their relation to the actor (ally / rival) and NOT judged: 'last known' means a far observer
    may legally keep the old place (menus_notes.md 6)."""
    a, h = ctx.actor, ctx.host
    if a == h:
        raise Skip('actor is the host: run with actor=<a guest>')
    obs = [w for w in ctx.games if w != a]
    rel = {w: relation(ctx, w) for w in obs}
    hp_ = my_pos(h)
    if not hp_:
        raise Skip('host position unreadable')
    p0 = my_pos(a)
    before = map_shots(ctx, 'rs_mark_before', obs)
    tp(ctx, a, (hp_[0] + 12.0, hp_[1] + 0.3, hp_[2]))
    time.sleep(10.0)
    after = map_shots(ctx, 'rs_mark_after', obs)
    md = {w: mapdiff1(before[w], after[w]) for w in obs}
    vals = 'mapdiff %s | relation to %s %s | actor %s -> %s, host at %s' % (
        {w: '%s %s blob(s)' % v[:2] for w, v in md.items()}, a, rel, fmt3(p0), fmt3(my_pos(a)), fmt3(hp_))
    if md[h][0] in ('UNUSABLE', 'NOSHOT', 'NOLINE'):
        return 'SKIP', 'the host map pair is not usable (%s): take the shots again' % md[h][2], vals
    if md[h][0] == 'PASS':
        return 'PASS', 'the host map shows the actor\'s marker at its new place (others: INFO)', vals
    return 'FAIL', 'the host map did not change after %s stood 12 m away for 10 s (no other-player marker)' % a, vals


# =============================================================== row 11: pledge taken over
def pledge_rows(w):
    x = gw(w)
    gl = x.g(GL_G)
    if not gl:
        return None, []
    sites = [(x.b(gl + 0x10 + i * 0x1A0), x.b(gl + 0x10 + i * 0x1A0 + 0x188)) for i in range(min(x.q(gl + 0x4F8) or 0, 8))]
    nl = x.q(gl + 0x780)
    out = []
    if nl:
        for i in range(min(x.q(nl + 0xA60) or 0, 15)):
            e = nl + 8 + i * 0xB0
            out.append({'i': i, 'id': x.h(e), 'h': x.d(e + 4), 'owner': x.i(e + 8), 'gold': x.b(e + 0xC),
                        'signer': x.i(e + 0x10)})
    return sites, out


@test('pledge_takeover', 11, 'site', 360)
def t_pledge_takeover(ctx):
    """Phase II / III with the Ritual Site open. A take-over = a pillar owned by one player is sworn to by the other.
    Order used (the host's own pledge was the step that failed on 2026-11-15): the actor (guest) owns a pillar, or
    swears at a free one first; then the HOST swears at that pillar. Expect owner = actor, then owner = host on every
    game (PLEDGE_HOST: the host decides), Virtue changes on both. Pillars with a live enemy (not a kin) within 15 m
    (host's and actor's view) are not used; every swear is retried up to 3 times (approach.py dist=1.4 hold=Y:420
    from another side each time), with the 15 m check again before each retry."""
    h, a = ctx.host, ctx.actor
    if h == a:
        raise Skip('actor is the host: run with actor=<a guest>')
    settle(ctx)
    sites, pil = pledge_rows(h)
    if not sites or all(cl != 0 for _, cl in sites):
        raise Skip('no open Ritual Site on %s (sites %s): restart hold_clock.py AB 95 and wait until it opens' % (h, sites))
    if not pil:
        raise Skip('no pledge pillar in the name list on %s' % h)
    nh, na = local_no(h), local_no(a)
    me = my_pos(h)

    def pillar_pos(p):
        g = gw(h).geom_from_handle(p['h']) if p['h'] else None
        return gw(h).geom_pos(g) if g else None

    def owner_on(w, pid):
        return next((r['owner'] for r in pledge_rows(w)[1] if r['id'] == pid), None)

    cands, dirty = [], []
    for p in pil:
        pos = pillar_pos(p)
        if not pos:
            continue
        near = enemies_near(ctx, pos, 5.0)
        if near:
            dirty.append((p['id'], near))
            continue
        own = {w: owner_on(w, p['id']) for w in ctx.games}
        rank = 0 if all(v == na for v in own.values()) else 1 if all(v in (-1, 0, None) for v in own.values()) else 2
        if rank < 2:
            cands.append((rank, math.dist(me, pos) if me else 0, p, pos))
    if not cands:
        raise Skip('no pledge pillar owned by %s or free without an enemy within 15 m (with enemies: %s)' % (a, dirty))
    cands.sort(key=lambda t: (t[0], t[1]))
    rank, _, p, pos = cands[0]
    v0 = virtue_totals(ctx.games)
    say('pillar id %s at %s owner %s (%s) | Virtue %s' % (p['id'], fmt3(pos), {w: owner_on(w, p['id']) for w in ctx.games},
                                                         'actor owns it' if rank == 0 else 'free', vtext(v0)))
    steps = []
    order = ([] if rank == 0 else [(a, na)]) + [(h, nh)]
    for who, want in order:
        ok, ow = swear(ctx, who, p['id'], pos, want, owner_on)
        steps.append((who, want, ow, ok))
        if not ok:
            break
    v1 = virtue_totals(ctx.games)
    vals = 'steps %s | Virtue before %s after %s' % (steps, vtext(v0), vtext(v1))
    if rank != 0 and not steps[0][3]:
        return 'FAIL', 'the guest pledge (player %s) was not recorded on every game' % na, vals
    if steps[-1][0] == h and steps[-1][3]:
        return 'PASS', 'pillar of player %s taken over by the host (player %s) on every game' % (na, nh), vals
    return 'FAIL', 'host pledge at the guest\'s pillar not shown on every game (%s)' % steps[-1][2], vals


def enemies_near(ctx, pos, radius):
    """[(game, hp, distance)] of live enemies (not kin) within radius of pos, on the host's and the actor's game"""
    out = []
    for w in dict.fromkeys((ctx.host, ctx.actor)):
        kc = kin_chrs(w)
        for hnd, e in sync_enemies(w).items():
            if e['chr'] in kc:
                continue
            v = enemy_view(w, e)
            if v['hp'] and v['hp'] > 0 and v['pos'] and math.dist(pos, v['pos']) <= radius:
                out.append((w, v['hp'], round(math.dist(pos, v['pos']), 1)))
    return out


def swear(ctx, who, pid, pos, want, owner_on, tries=3):
    """approach + hold Y at pillar pid until owner == want on every game; another side per try. (ok, owners)"""
    sides = ('1,0', '0,1', '-1,0', '0,-1')
    ow = {}
    for i in range(tries):
        if ctx.left() < 60:
            break
        near = enemies_near(ctx, pos, 5.0)
        if near:
            say('%s: enemy within 15 m of pillar %s before try %d: %s; waiting 8 s' % (who, pid, i + 1, near))
            time.sleep(8.0)
            if enemies_near(ctx, pos, 5.0):
                break
        tool(['diag/twin/approach.py', who, '%.2f' % pos[0], '%.2f' % pos[1], '%.2f' % pos[2], 'dist=1.4',
              'from=%s' % sides[i % len(sides)], 'hold=Y:420', 'shot=rs_pledge_%s%d' % (who, i + 1)], 240)
        t0 = time.time()
        while time.time() - t0 < 30:
            ow = {w: owner_on(w, pid) for w in ctx.games}
            if all(v == want for v in ow.values()):
                return True, ow
            time.sleep(2.0)
        say('%s: try %d at pillar %s: owners %s (want %s)' % (who, i + 1, pid, ow, want))
    return False, ow


# =============================================================== row 42: other environment events
@test('event_gala', 42, 'phase3', 120)
def t_event_gala(ctx):
    """With event 1220 (Bloodsac Gala) current (arm_1220 in the phase before): same event on every game, the same
    enemy handle set on every game (MapSystem lists shared since v3.3) and the count change against the baseline
    stored by arm_1220. The swarm itself is [I]: judge the screenshots."""
    settle(ctx)
    cur = {w: env_current(w) for w in ctx.games}
    if any(v != 1220 for v in cur.values()):
        raise Skip('event 1220 not current on every game: %s' % cur)
    base = (load_state().get('armed') or {}).get('enemies', {})
    ens = {w: sync_enemies(w) for w in ctx.games}
    sets = {w: set(e) for w, e in ens.items()}
    common = set.intersection(*sets.values())
    only = {w: len(s - common) for w, s in sets.items()}
    shots = {w: shot(w, 'rs_gala') for w in ctx.games}
    vals = 'event %s | enemies %s (baseline %s) | only on one game %s | shots %s' % (
        cur, {w: len(s) for w, s in sets.items()}, base, only, shots)
    if all(v == 0 for v in only.values()):
        if base and all(len(sets[w]) != base.get(w) for w in ctx.games):
            return 'PASS', 'Gala: same event and same enemy set on every game, enemy count changed', vals
        return 'PARTIAL', 'Gala: same event and same enemy set; no visible count change (judge the shots)', vals
    return 'FAIL', 'enemy sets differ between games under the Gala', vals


@test('event_star', 42, '-', 120)
def t_event_star(ctx):
    """With event 1210 (Star Fragment) current (arm_1210): the same event on every game and the same world-item ids
    on every game (fragments are items, DROPS-networked); counts against the baseline of arm_1210."""
    settle(ctx)
    cur = {w: env_current(w) for w in ctx.games}
    if any(v != 1210 for v in cur.values()):
        raise Skip('event 1210 not current on every game: %s' % cur)
    base = (load_state().get('armed') or {}).get('items', {})
    its = {w: set(item_nodes(w)) for w in ctx.games}
    same = len(set(frozenset(v) for v in its.values())) == 1
    vals = 'event %s | items %s (baseline %s) equal %s' % (cur, {w: len(v) for w, v in its.items()}, base, same)
    if same and any(len(v) for v in its.values()):
        return 'PASS', 'star fragments: same world items on every game', vals
    if same:
        return 'PARTIAL', 'same (empty) item lists: no fragment seen yet; run again later in the phase', vals
    return 'FAIL', 'world items differ between games', vals


# =============================================================== row 18: alliance ends at the final
@test('ally_form', 18, 'phase3', 240)
def t_ally_form(ctx):
    """3+ games only (two allied players of two end the match): host and actor form an alliance (ally_test.py, the
    players are put 2 m apart first). Stored for alliance_end."""
    if len(ctx.games) < 3:
        raise Skip('2 games: an alliance of the only two players ends the match at once (handoff 12:00)')
    h, a = ctx.host, ctx.actor
    settle(ctx)
    c0 = {w: am_count(w) for w in ctx.games}
    ph = my_pos(h)
    if ph:
        tp(ctx, a, (ph[0] + 2.0, ph[1] + 0.3, ph[2]))
    time.sleep(2.0)
    tool(['diag/twin/ally_test.py', h, a, 'accept'], 180)
    time.sleep(2.0)
    c1 = {w: am_count(w) for w in ctx.games}
    st = load_state()
    st['ally'] = {'counts': c1, 'round': step_round(h)[1], 'time': time.time(), 'pair': [h, a]}
    save_state(st)
    if (c1[h] or 0) >= 1 and (c1[a] or 0) >= 1:
        return 'SETUP', 'alliance %s+%s formed; cut to the final and run alliance_end' % (h, a), 'counts %s -> %s' % (c0, c1)
    return 'FAIL', 'alliance not formed', 'counts %s -> %s' % (c0, c1)


@test('alliance_end', 18, 'final', 120)
def t_alliance_end(ctx):
    """In the final (round 4): alliance count AM+0x38 = 0 on every game (ALLIANCE_FINAL_END) after ally_form."""
    if len(ctx.games) < 3:
        raise Skip('needs 3+ games (see ally_form)')
    r = settle(ctx, 5)
    if r != 4:
        raise Skip('not the final (round %s)' % r)
    ally = load_state().get('ally')
    c = {w: am_count(w) for w in ctx.games}
    vals = 'counts in the final %s | stored %s' % (c, ally)
    if ally and time.time() - (ally.get('time') or 0) > 1800:
        return 'SKIP', 'the stored ally_form result is %.0f min old (another match): run ally_form in phase3 of this match' % (
            (time.time() - (ally.get('time') or 0)) / 60), vals
    if not ally or max([v or 0 for v in (ally.get('counts') or {}).values()] or [0]) < 1:
        return 'SKIP', 'no alliance was formed before the final (run ally_form in phase3)', vals
    if all(v == 0 for v in c.values()):
        return 'PASS', 'alliance dissolved on every game at the final', vals
    return 'FAIL', 'alliance still counted in the final', vals


# =============================================================== row 19: spectating
HIT_SECS = 120          # spectate: real hits per life before 'could not be hit' (SKIP, not FAIL)


@test('spectate', 19, 'final', 1080)
def t_spectate(ctx):
    """3+ games, final, >= 45 s in: the LAST game's player (victim) is killed twice by REAL damage: the first game's
    player (attacker, the host) fights the victim's chr on its own game with killchr.py (kill.py's sequence). No HP
    write (spectate_notes.md: a forced HP 0, final_kills.py kill, right after a respawn gives HP 0 without the death
    processing: net byte [[chr+0x18]+0x30]+0x18 stays 00, so the host's collector 0x116C638 never lists the player
    and it stays dead, stock 0, stage 01 01 00 00 - the run3 FAIL). Between the lives: wait for the respawn AND until
    it is over (rsp chrdata+0x2D0 bit 0, respawn flag chr+0x26E4 bit 16, warp marker chr+0x25E9 all clear, HP > 0)
    plus 5 s. Printed per death: net byte / listable on the victim's game and the host, and the 0x9C tracker.
    Part 1 (spectate_notes.md 9: the game's own path - par+0x164 = 1 ends the eliminated game's UpdatePhase at once,
    0x114BA9C, and online the watching is the server's CSGameWatchingMan, which LAN has not): expect the victim's
    game at the Outcome (step 29..36), every other game still at step 6, and the victim listed ONCE in the kill
    tracker on every game (run3_check.py final's rule: out deque or tracker node).
    Part 2 (the end of the final, needs assist V402): the attacker kills the second game's player twice the same
    way; expect the Outcome on both, result rows equal on every game (run4_check.py final) and the ranks in the
    order attacker < second player < victim (1 / 2 / 3)."""
    if len(ctx.games) < 3:
        raise Skip('needs 3+ games: with 2 the second elimination ends the match')
    v = ctx.games[-1]
    r = settle(ctx, 45, 120)
    if r != 4:
        raise Skip('not the final (round %s)' % r)

    def spec(w):
        x = gw(w)
        sp = x.g(SPECTATOR_G)
        par = x.g(PAR_G)
        chr_ = x.me()[0]
        return {'step': step_round(w), 'smode': x.d(sp + 0x50) if sp else None, 's17a': x.b(sp + 0x17A) if sp else None,
                'p164': x.b(par + 0x164) if par else None, 'out': bool((x.d(chr_ + 0x26E4) or 0) & 0x400) if chr_ else None,
                'hp': master_hp(w)}
    s0 = spec(v)
    att = ctx.games[0] if ctx.games[0] != v else ctx.games[1]
    sec = [w for w in ctx.games if w not in (att, v)][0]

    def own_no(w):
        x = gw(w)
        c = x.me()[0]
        d = x.q(c + 0x20) if c else None
        pgd = x.q(d + 0x1D0) if d else None
        return x.d(pgd + 0xD0) if pgd else None

    def chr_of(w, no):
        """the chr of player `no` on game w (player entries WCM+0x30, 0x38 each; number pgd+0xD0)"""
        x = gw(w)
        ents = x.q(x.g(0x5B3CD88) + 0x30) if x.g(0x5B3CD88) else None
        for k in range(12):
            c = x.q(ents + 0x38 * k) if ents else None
            d = x.q(c + 0x20) if c else None
            pgd = x.q(d + 0x1D0) if d else None
            if pgd and x.d(pgd + 0xD0) == no:
                return c
        return None

    def death_state(w, no):
        """lives.py's fields of player `no` on game w: HP, stock, stage, net byte, rsp, respawn flag, warp marker"""
        x = gw(w)
        c = chr_of(w, no)
        if not c:
            return None
        d = x.q(c + 0x20)
        pgd = x.q(d + 0x1D0) if d else None
        net = x.q(c + 0x18)
        sub = x.q(net + 0x30) if net else None
        return {'hp': x.chr_hp(c), 'stock': x.b(pgd + 0x42A4) if pgd else None,
                'stage': (x.d(pgd + 0x46B0) or 0) & 0xFF if pgd else None, 'net': x.b(sub + 0x18) if sub else None,
                'rsp': (x.b(d + 0x2D0) or 0) & 1 if d else None, 'flag': ((x.d(c + 0x26E4) or 0) >> 16) & 1,
                'pend': x.b(c + 0x25E9)}

    def listed_once(w, no):
        """run3_check.py final's rule: player `no` once in the out deque (par+0x38A0), or, with the deque
        already drained, once as a dead node of the kill tracker (par+0x3398); returns (ok, text)"""
        import final_kills
        try:
            s = final_kills.snap(gw(w)) or {}
        except Exception as e:                         # a read error must not end the test
            return False, 'snap error %s' % e
        dq = sum(1 for x in (s.get('deque') or (0, []))[1] if x and x[0] == no)
        nd = sum(1 for n, dead in s.get('nodes', []) if n == no and dead)
        return dq == 1 or (dq == 0 and nd == 1), 'deque %d nodes %d' % (dq, nd)

    def kill_twice(vg, vno, part, log):
        """two real deaths of player vno (game vg) by att; None when both happened, else (verdict, why)"""
        for life in (1, 2):
            target = chr_of(att, vno)
            if not target:
                return 'SKIP', '%s: no chr of player %s (%s) on the attacker %s' % (part, vno, vg, att)
            before = death_state(vg, vno)
            hp0 = master_hp(vg)
            secs = min(HIT_SECS, ctx.left() - 70)      # keep room for the respawn wait and the judging
            if secs < 30:
                return 'SKIP', '%s kill %d: only %.0f s of the time budget left for real hits (budget=2 gives more)' % (
                    part, life, ctx.left())
            # the attacker's copy must stand where the victim really is (after a respawn the copy jumps to the
            # respawn point a moment later): wait up to 20 s until both views agree within 2 m
            t_s, gap = time.time(), None
            while time.time() - t_s < 20:
                target = chr_of(att, vno) or target           # re-resolved: a respawn may give a new chr
                xa = gw(att)
                bag = xa.q(target + 0x2470)
                ph = xa.q(bag + 0xE8) if bag else None
                pa, pv = (xa.f3(ph + 0x70) if ph else None), my_pos(vg)
                gap = math.dist(pa, pv) if pa and pv else None
                if gap is not None and gap <= 2.0:
                    break
                time.sleep(1.0)
            log.append('%s kill %d: attacker copy %x vs the victim own position: gap %s m' % (
                part, life, target, None if gap is None else round(gap, 1)))
            # strike.py: validated positioning (ground test per side, refuses bad spots), real R hits, no HP write;
            # maxjump 400 because the respawn point can be far from the attacker. killchr.py only as the fallback.
            prc, pout = tool(['diag/twin/strike.py', att, 'c:0x%x' % target, 'probe',
                              'games=%s' % ''.join(ctx.games)], 60, quiet=True)   # writes nothing
            if 'loaded YES' in (pout or ''):
                rc, out_ = tool(['diag/twin/strike.py', att, 'c:0x%x' % target, 'mode=R', 'seconds=%d' % secs,
                                 'maxjump=400', 'games=%s' % ''.join(ctx.games)], secs + 40, quiet=True)
            else:
                rc, out_ = 2, 'strike probe: not loaded (%s)' % ' / '.join(
                    l.strip() for l in (pout or '').splitlines() if 'loaded' in l)[:200]
            if rc in (2, 4) and (master_hp(vg) or 0) > 0:
                log.append('%s kill %d: strike.py rc %s (%s): killchr.py fallback' % (
                    part, life, rc, ' / '.join((out_ or '').strip().splitlines()[-1:])))
                secs = min(HIT_SECS, ctx.left() - 70)
                if secs >= 30:
                    rc, out_ = tool(['diag/twin/killchr.py', att, 'chr=%x' % target, 'seconds=%d' % secs,
                                     'every=3'], secs + 30, quiet=True)
                    rc = 2 if rc == 2 else (0 if rc == 0 else 1)
            elif rc == 4:
                rc = 1
            t0 = time.time()
            while time.time() - t0 < 8 and (master_hp(vg) or 0) > 0:
                time.sleep(0.5)
            time.sleep(2.0)
            seen = {'victim': death_state(vg, vno), 'host': death_state(att, vno)}
            trk = tool(['diag/twin/final_kills.py', ''.join(ctx.games)], 30, quiet=True)[1].strip().splitlines()[-3:]
            log.append('%s kill %d (real hits by %s, killchr rc %s, last %s): before %s, after %s | tracker %s' % (
                part, life, att, rc, ' / '.join((out_ or '').strip().splitlines()[-1:]), before, seen, ' / '.join(trk)))
            hp1 = master_hp(vg)
            if rc == 2:
                return 'SKIP', '%s kill %d: killchr.py could not read the victim %s chr %x on %s (rc 2): not judged' % (
                    part, life, vg, target, att)
            if (hp1 or 0) > 0:
                if hp0 is not None and hp1 is not None and hp1 >= hp0:
                    why = 'victim %s could not be hit within %d s by %s (HP %s -> %s, killchr rc %s): no kill, not judged' % (
                        vg, secs, att, hp0, hp1, rc)
                else:
                    why = 'victim %s was hit but not killed within %d s by %s (HP %s -> %s, killchr rc %s): not judged' % (
                        vg, secs, att, hp0, hp1, rc)
                return 'SKIP', '%s kill %d: %s' % (part, life, why)
            if life == 1:                              # respawn, and wait until it is over
                t0 = time.time()
                while time.time() - t0 < 45:
                    st = death_state(vg, vno)
                    if st and (st['hp'] or 0) > 0 and not st['rsp'] and not st['flag'] and not st['pend']:
                        break
                    time.sleep(1.0)
                else:
                    return 'FAIL', '%s: no respawn after the first real death' % part
                time.sleep(5.0)
                log.append('%s respawned: %s' % (part, death_state(vg, vno)))
        return None

    vno = own_no(v)
    if not vno:
        raise Skip('victim %s: own player number unreadable' % v)
    log = []
    bad = kill_twice(v, vno, 'part 1', log)
    if bad:
        return bad[0], bad[1], '; '.join(log)
    time.sleep(8.0)
    s1 = spec(v)
    others = {w: step_round(w) for w in ctx.games if w != v}
    trk1 = {w: listed_once(w, vno) for w in ctx.games}
    sh = shot(v, 'rs_spectate')
    vals = 'victim %s (no %s) before %s | %s | now %s | others %s | tracker %s | shot %s' % (
        v, vno, s0, '; '.join(log), s1, others, trk1, sh)
    once = all(ok for ok, _t in trk1.values())
    if s1['step'][0] not in range(29, 37):
        return 'FAIL', 'part 1: the eliminated game is not at the Outcome (step %s; the game\'s own path ends its ' \
            'UpdatePhase at once)' % (s1['step'],), vals
    if not all(s[0] == 6 for s in others.values()):
        return 'FAIL', 'part 1: the other games are not all at step 6 %s (the final must go on)' % others, vals
    if not once:
        return 'FAIL', 'part 1: elimination of player %s not listed exactly once on every game %s' % (vno, trk1), vals
    log.append('part 1 PASS: victim at the Outcome, others at step 6, listed once')
    # ---- part 2: the end of the final
    sno, ano = own_no(sec), own_no(att)
    if not sno or not ano:
        return 'PARTIAL', 'part 1 passed; part 2 not run: player numbers unreadable (%s %s, %s %s)' % (
            att, ano, sec, sno), vals
    bad = kill_twice(sec, sno, 'part 2', log)
    vals += ' || part 2 %s' % '; '.join(log)
    if bad:
        return ('PARTIAL' if bad[0] == 'SKIP' else bad[0]), 'part 1 passed; %s' % bad[1], vals
    t0 = time.time()
    while time.time() - t0 < 40 and not all(step_round(w)[0] in range(29, 37) for w in (att, sec)):
        time.sleep(1.0)
    time.sleep(3.0)
    steps = {w: step_round(w) for w in ctx.games}
    rc, fin = tool(['diag/twin/run4_check.py', 'final', ''.join(ctx.games)], 60, quiet=True)
    fin = (fin or '').strip().splitlines()[-1:] or ['-']
    import run4_check
    rows = {w: run4_check.result_rows(gw(w)) for w in ctx.games}
    vals += ' | steps after %s | %s | rows (no, rank, place, Virtue) %s' % (steps, fin[0][:600], rows)
    if not all(steps[w][0] in range(29, 37) for w in (att, sec)):
        return 'FAIL', 'part 2: the final did not end after the second player\'s two deaths (steps %s)' % steps, vals
    rk = {}
    for w, rr in rows.items():
        rk[w] = {no: rank for no, rank, _p, _v in (rr or [])}
    ordered = all(r.get(ano) is not None and r.get(sno) is not None and r.get(vno) is not None and
                  r[ano] < r[sno] < r[vno] for r in rk.values())
    if fin[0].startswith('FINAL PASS') and ordered:
        return 'PASS', 'eliminated player at the Outcome while the final went on; the final ended with ranks ' \
            '%s 1 / %s 2 / %s 3 equal on every game' % (att, sec, v), vals
    return 'FAIL', 'part 2: ranks not equal or not in the order %s < %s < %s (run4_check %s, ranks %s)' % (
        att, sec, v, fin[0][:12], rk), vals


# =============================================================== row 14: start-area pick
@test('start_area', 14, 'intermission', 420)
def t_start_area(ctx):
    """Intermission: wait for the start-area menu (mediator state 3 PointSelecting) on the actor, pick through the
    menu (A, then stick nudges + A); if no pick registers, the documented test pick (memory, startarea_fix_notes 7).
    Expect the same decided list on every game and, in the next phase, the actor standing at its decided point
    (startarea.py fields)."""
    a = ctx.actor
    t0 = time.time()

    def med(w):
        x = gw(w)
        return x, x.g(MEDIATOR_G)
    x, m = med(a)
    while time.time() - t0 < 240:
        x, m = med(a)
        if m and x.d(m + 0x50) == 3:
            break
        time.sleep(1.0)
    else:
        raise Skip('no start-area menu (mediator state 3) on %s within 240 s: %s' % (a, states_text(ctx.games)))
    me = local_no(a)
    areas = []
    a0, a1 = x.q(m + 0x628), x.q(m + 0x630)
    if a0 and a1 and a1 > a0 and a1 - a0 <= 0x400:
        areas = [(x.b(p + 8), x.i(p + 0xC)) for p in range(a0, a1, 0x10)]
    # A slot exists only after its player picked: the slot list M+0xC0 is emptied at WaitCloseMenu (0x10F7004) and
    # at init (0x10EE4F4), and filled only by the upsert 0x10F1220 (from a local click 0x10F05AC, a received 0x45, or
    # the timeout's final locked 0x45). No slot before the first pick is the stock design, not a LAN gap
    # (kin4_notes.md section 2). So the slot is looked up again after every press.
    def own_slot():
        for k in range(min(x.q(m + 0x248) or 0, 8)):
            s = m + 0xC0 + k * 0x30
            if x.d(s) == me:
                return s
        return None

    def pick():
        s = own_slot()
        return (x.b(s + 0x10), x.i(s + 0x14)) if s else (4, -1)
    p0 = pick()
    say('areas %s, own pick before %s' % (areas, p0))
    shot(a, 'rs_area_menu')
    method = 'menu'
    tries = [None, (1, 0), (0, -1), (-1, 0), (0, 1), (1, 1), (-1, -1)] if p0[0] != 3 else []
    if not tries:
        method = 'menu (picked before the test started)'
    for t in tries:
        if t:
            stick(a, 'left_stick', t, 8, 10)
        press(a, 'A', 6, 40)
        time.sleep(1.0)
        if pick() != p0 and pick()[0] == 3:
            break
    if pick()[0] != 3:
        kinds = [ar for ar in areas if ar[0] == 3]
        if not kinds:
            raise Skip('pick did not register and no area of kind 3 is listed: %s' % areas)
        slot = own_slot()
        if slot is None:
            raise Skip('menu presses created no slot for player %s (no pick registered; the memory test pick needs '
                       'an existing slot): areas %s' % (me, areas))
        method = 'memory (test pick)'
        x.write(slot + 0x10, bytes([3]))
        x.write(slot + 0x14, struct.pack('<i', kinds[-1][1]))
    p1 = pick()

    def decided(w):
        y, mm = med(w)
        if not mm:
            return None
        return [(y.d(mm + 0x290 + k * 0x68), y.i(mm + 0x290 + k * 0x68 + 0x24), y.f3(mm + 0x290 + k * 0x68 + 0x40))
                for k in range(min(y.q(mm + 0x5D8) or 0, 8))]
    t0, lists = time.time(), {}
    while time.time() - t0 < 150:
        lists = {w: decided(w) for w in ctx.games}
        if all(lists.values()):
            break
        time.sleep(1.5)
    key = {w: sorted((n, ar) for n, ar, _ in (l or [])) for w, l in lists.items()}
    same = len(set(tuple(v) for v in key.values())) == 1 and all(key.values())
    mine = next(((n, ar, pos) for n, ar, pos in (lists.get(a) or []) if n == me), None)
    t0 = time.time()
    while time.time() - t0 < 200:
        if all(step_round(w)[0] == 6 for w in ctx.games):
            break
        time.sleep(2.0)
    time.sleep(4.0)
    here = my_pos(a)
    seen = {}
    for w in ctx.games:
        r = by_no(player_rows(w)).get(me)
        seen[w] = r['pos'] if r else None
    dist = math.dist(here, mine[2]) if here and mine and mine[2] else None
    vals = 'method %s, pick %s -> %s | decided %s | own entry %s | actor at %s (%.1f m) | as seen %s' % (
        method, p0, p1, key, mine, fmt3(here), dist if dist is not None else -1,
        {w: fmt3(p) for w, p in seen.items()})
    near = dist is not None and dist < 8
    if same and near and p1[0] == 3:
        if method.startswith('menu'):
            return 'PASS', 'menu pick: same list on every game, actor starts at its point', vals
        return 'PARTIAL', 'test pick (memory): same list on every game, actor at its point; menu pick still manual', vals
    return 'FAIL', 'lists differ (%s) or the actor is not at its point (%s)' % (not same, not near), vals


# =============================================================== main
def run(names, ctx):
    results = []
    for name in names:
        t = TESTS[name]
        budget = t['budget'] * ctx.scale
        ctx.deadline = time.time() + budget
        print('\n' + '=' * 30, name, '(row %s, budget %d s)' % (t['row'], budget), '=' * 30, flush=True)
        print(t['doc'], flush=True)
        say('states: %s' % states_text(ctx.games))
        t0 = time.time()
        try:
            st, why, vals = t['f'](ctx)
        except Skip as ex:
            st, why, vals = 'SKIP', str(ex), ''
        except Timeout as ex:
            st, why, vals = 'FAIL', str(ex), ''
        except Exception as ex:                       # a broken test must not stop the others
            import traceback
            traceback.print_exc()
            st, why, vals = 'FAIL', 'exception %s: %s' % (type(ex).__name__, ex), ''
            _W.clear()
        line = 'RESULT %-15s %-7s row %-2s: %s | %s (%.0f s)' % (name, st, t['row'], why, vals, time.time() - t0)
        print(line, flush=True)
        results.append((name, st, t['row'], why))
        try:
            with open(RESULTS_FILE, 'a') as fh:
                fh.write('%s games %s actor %s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), ctx.games, ctx.actor, line))
        except Exception:
            pass
    print('\n' + '=' * 30, 'summary', '=' * 30)
    for name, st, row, why in results:
        print('  %-15s %-7s row %-2s %s' % (name, st, row, why[:150]))
    return results


CFG = {'games': os.environ.get('TWIN_GAMES', 'AB')}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == 'list':
        for n, t in TESTS.items():
            print('%-15s row %-2s group %-12s budget %4d s  %s' % (n, t['row'], t['group'], t['budget'],
                                                                  t['doc'].split('\n')[0][:90]))
        return 0
    opts = {k: v for k, _, v in (a.partition('=') for a in args if '=' in a)}
    games = opts.get('games', CFG['games'])
    CFG['games'] = games
    actor = opts.get('actor', games[1] if len(games) > 1 else games[0])
    nowait = 'nowait' in args
    scale = float(opts.get('budget', 1))
    names = []
    for a in args:
        if '=' in a or a == 'nowait':
            continue
        if a in GROUPS:
            names += GROUPS[a]
        elif a in TESTS:
            names.append(a)
        else:
            print('unknown group or test %s (groups %s; "list" shows the tests)' % (a, ', '.join(GROUPS)))
            return 1
    if not re.fullmatch(r'[A-D]{1,4}', games) or actor not in games:
        print('bad games=%s / actor=%s' % (games, actor))
        return 1
    ctx = Ctx(games, actor, nowait, scale)
    say('regress_small: games %s (host %s), actor %s, tests %s' % (games, ctx.host, actor, names))
    res = run(list(dict.fromkeys(names)), ctx)
    return 0 if all(r[1] not in ('FAIL',) for r in res) else 1


if __name__ == '__main__':
    sys.exit(main())
