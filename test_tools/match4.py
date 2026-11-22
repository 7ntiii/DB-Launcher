"""Hands-free whole match on the twin games (2-4 of A B C D), started once every game is in Phase I.
python diag/twin/match4.py GAMES [bloodbound] [taken] [options]       (from anywhere; runs from the workspace)

  GAMES        e.g. ABCD (default: TWIN_GAMES, else ABCD)
  bloodbound   also print pairs.py each phase and check the rule byte is 2 on every game at the start;
               it does NOT choose the rule: that must happen in the hub before matchmaking
               (go4.sh GO4_RULE=4, which runs set_rule.py; see diag/net/four_games_run_notes.md)
  taken        also print taken.py each phase (slow with 4 games: it walks every loaded geom)
  --start-wait S   seconds to wait for all games in step 6 round 1 (default 600)
  --phase-wait S   seconds into each phase before the snapshots (default 10, as fullmatch.py / to_final.py)
  --cut S          clock value the phase is cut to with clock.py (default 5)
  --limit S        whole-run limit in seconds (default 2400)
  --phase1-only    only wait for Phase I on every game (exit 0 when reached; used by go4.sh GO4_PHASE1=1)

Per phase (every game of GAMES that is still in the match): mapsys.py, rules.py, [pairs.py], virtue totals
(virtue.py parsed: each player's live total per game, and whether every game holds the same banked value),
then clock.py CUT for the games in UpdatePhase. A game that reaches the Outcome steps (29..36) or loses its
stage before the others is reported as cut / out and left alone. At the end: endgame.py on every game, the
ranks (result rows; phase entries when there are no rows) per game and whether all games agree.

Memory: READ only (mem.Mem.read / u32 / u64 for the step reads); the only writes are those of clock.py,
which this script runs as a subprocess. Every wait has a time-out, every subprocess one too.
Exit 0 = match over and ranks agree on every game; 1 = otherwise. Last line 'match4 done ...' or
'match4 FAILED: reason'."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
os.chdir(WS)                                   # the tools use sys.path 'diag/twin' relative to the workspace
os.environ.pop('DUSK_BASE', None)              # one fixed base would be wrong for 2+ games
sys.path.insert(0, str(WS / 'diag' / 'twin'))
from mem import Mem  # noqa: E402

PAR = 0x5B3CDF8
RULE = 0x5B65C70
OUTCOME_STEPS = range(29, 37)                  # 29..36: the Outcome copy par[0x4708] is used (handoff 8.9)
TOOL_TIMEOUT = 180


def opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        try:
            return float(sys.argv[i + 1])
        except (IndexError, ValueError):
            fail('%s needs a number' % name)
    return default


def fail(why):
    print('match4 FAILED: %s' % why, flush=True)
    sys.exit(1)


VALUE_OPTS = ('--start-wait', '--phase-wait', '--cut', '--limit', '--final-wait')
pos, skip = [], False
for a in sys.argv[1:]:
    if skip:
        skip = False
    elif a in VALUE_OPTS:
        skip = True
    elif a.startswith('--'):
        if a != '--phase1-only':
            fail('unknown option %s' % a)
    else:
        pos.append(a)
PHASE1_ONLY = '--phase1-only' in sys.argv
GAMES = next((a for a in pos if re.fullmatch(r'[A-D]{1,4}', a)), os.environ.get('TWIN_GAMES', 'ABCD'))
if len(set(GAMES)) != len(GAMES):
    fail('GAMES %s names a game twice' % GAMES)
BLOODBOUND = 'bloodbound' in pos
TAKEN = 'taken' in pos
START_WAIT = opt('--start-wait', 600)
PHASE_WAIT = opt('--phase-wait', 10)
CUT = opt('--cut', 5)
LIMIT = opt('--limit', 2400)
# --final-wait S (opt-in, 2026-11-17, runnet3.sh): in round 4 wait S s before the snapshots and the cut, so another
# script can land an elimination in the final first; a game that reaches its result screen meanwhile is left out
# of the snapshot and the cut. Default = --phase-wait (unchanged behaviour).
FINAL_WAIT = opt('--final-wait', PHASE_WAIT)
T0 = time.time()
ENV = dict(os.environ, TWIN_GAMES=GAMES)


def ts():
    return '%s +%4.0fs' % (time.strftime('%H:%M:%S'), time.time() - T0)


def say(*a):
    print(ts(), *a, flush=True)


def left():
    return LIMIT - (time.time() - T0)


_mem = {}


def st(w):
    """(step, round) of game w; (-1, 0) no stage; (-2, 0) debug server / base not readable."""
    try:
        m = _mem.get(w) or _mem.setdefault(w, Mem(w))
        par = m.u64(m.base + PAR)
        return (m.u32(par + 0x50), m.u32(par + 0xB8)) if par else (-1, 0)
    except Exception:
        _mem.pop(w, None)                      # reconnect next time (Dbg keeps one socket open)
        return (-2, 0)


def states(games):
    return {w: st(w) for w in games}


def show(now):
    return ' '.join('%s %d/%d' % (w, s[0], s[1]) for w, s in now.items())


def tool(args, timeout=TOOL_TIMEOUT, quiet=False):
    """Run an existing twin tool; returns its output text (also printed unless quiet)."""
    try:
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=timeout,
                           env=ENV, cwd=WS)
        out = (r.stdout or '') + (('\n[stderr] ' + r.stderr.strip()) if r.returncode and r.stderr else '')
    except subprocess.TimeoutExpired:
        out = '[%s: no answer in %d s]' % (' '.join(args), timeout)
    if not quiet:
        print('--- %s' % ' '.join(args))
        print(out.rstrip(), flush=True)
    return out


def virtue_totals(games):
    """virtue.py parsed: {game: {player no: (banked, live or None, local)}}; prints a compact table."""
    out = tool(['diag/twin/virtue.py', games], quiet=True)
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
            no, local = int(p.group(2)), p.group(1).endswith('*')
            if no not in per[cur] or local:
                per[cur][no] = (int(p.group(3)), int(live.group(1)) if live else None, local)
    if not per:
        print('--- virtue.py: nothing parsed:\n' + out.rstrip(), flush=True)
        return per
    print('--- virtue totals (virtue.py %s; live = banked + plain counters as that game reads them, * = own player)'
          % games)
    for w, ps in per.items():
        print('  %s: %s' % (w, '  '.join('p%d %s%s (banked %d)' % (no, '-' if lv is None else lv, '*' if loc else '', bk)
                                         for no, (bk, lv, loc) in sorted(ps.items())) or 'no players'))
    nos = sorted(set(n for ps in per.values() for n in ps))
    diff = [n for n in nos if len(set(ps[n][0] for ps in per.values() if n in ps)) > 1]
    own = {n: ps[n][1] for ps in per.values() for n in ps if ps[n][2]}
    print('  own totals: %s | banked equal on every game: %s' % (
        ' '.join('p%d %s' % (n, own[n]) for n in sorted(own)) or '-',
        'yes' if not diff else 'NO (players %s)' % diff), flush=True)
    return per


def snapshot(games, rnd):
    print('=' * 20, 'round %d snapshot, games %s' % (rnd, games), '=' * 20, flush=True)
    tool(['diag/twin/mapsys.py', games])
    tool(['diag/twin/rules.py', games])
    if BLOODBOUND:
        tool(['diag/twin/pairs.py', games])
    virtue_totals(games)
    if TAKEN:
        tool(['diag/twin/taken.py', games], timeout=300)


def ranks(games, quiet=False):
    """endgame.py parsed: {game: ({player no: rank}, source)} from the result rows (entries when no rows)."""
    out = tool(['diag/twin/endgame.py', games], quiet=quiet)
    rows, ents, cur = {}, {}, None
    for line in out.splitlines():
        h = re.match(r'([A-D]) (step|no stage)', line)
        if h:
            cur = h.group(1)
            rows[cur], ents[cur] = {}, {}
            continue
        r = re.match(r'\s+row \d+ no (-?\d+) rank (\d+)', line)
        e = re.match(r'\s+entry \d+ no (-?\d+) rank (\d+)', line)
        if cur and r:
            rows[cur][int(r.group(1))] = int(r.group(2))
        elif cur and e:
            ents[cur][int(e.group(1))] = int(e.group(2))
    return {w: (rows[w] or ents.get(w, {}), 'rows' if rows[w] else 'entries') for w in rows}


# ---------------------------------------------------------------- 1. wait for Phase I on every game
say('match4: games %s%s%s, start-wait %d s, phase-wait %d s, cut %g s, limit %d s' % (
    GAMES, ' bloodbound' if BLOODBOUND else '', ' taken' if TAKEN else '', START_WAIT, PHASE_WAIT, CUT, LIMIT))
last, t_start = None, time.time()
while True:
    now = states(GAMES)
    if now != last:
        say('wait for Phase I:', show(now))
        last = now
    if all(s == (6, 1) for s in now.values()):
        say('phase I on all games')
        break
    same_round = len(set(s[1] for s in now.values())) == 1
    if not PHASE1_ONLY and same_round and all(s[0] == 6 and s[1] > 1 for s in now.values()):
        say('note: all games are already in round %d; starting from there' % now[GAMES[0]][1])
        break
    if time.time() - t_start > START_WAIT:
        fail('not every game in step 6 round 1 after %d s: %s' % (START_WAIT, show(now)))
    time.sleep(2)
if PHASE1_ONLY:
    sys.exit(0)

if BLOODBOUND:
    rule = {}
    for w in GAMES:
        try:
            m = _mem.get(w) or _mem.setdefault(w, Mem(w))
            rule[w] = m.read(m.base + RULE, 1)[0]
        except Exception as ex:
            rule[w] = 'unreadable (%s)' % ex
    say('rule byte main+0x5B65C70 per game (2 = Bloodbound):', rule)
    if any(v != 2 for v in rule.values()):
        say('WARNING: not Bloodbound on every game: the rule is chosen in the hub (go4.sh GO4_RULE=4 / set_rule.py);'
            ' this match goes on as it is')

# ---------------------------------------------------------------- 2. phase loop
active = GAMES                     # games still in the match
out_games = {}                     # game -> (step, round) when it was seen out
done_rounds = set()
rounds_seen = []
gone_since = {}
early = {}                         # game -> ranks read when it reached the Outcome
last, t_change = None, time.time()
while True:
    if left() <= 0:
        fail('whole-run limit %d s reached; states %s' % (LIMIT, show(states(GAMES))))
    now = states(active)
    for w, s in now.items():       # out of the match: Outcome steps, step 0 or no stage for 10 s
        if s[0] in OUTCOME_STEPS or s[0] in (0, -1):
            gone_since.setdefault(w, time.time())
            if s[0] in OUTCOME_STEPS or time.time() - gone_since[w] > 10:
                out_games[w] = s
        elif s[0] == -2:
            gone_since.setdefault(w, time.time())
            if time.time() - gone_since[w] > 60:
                out_games[w] = s
                say('game %s: debug server unreadable for 60 s: counted as out' % w)
        else:
            gone_since.pop(w, None)
    newly = [w for w in active if w in out_games]
    if newly:
        for w in newly:
            say('game %s left the match at step %d round %d (%s)' % (
                w, out_games[w][0], out_games[w][1],
                'Outcome / cut' if out_games[w][0] in OUTCOME_STEPS else 'no stage or unreadable'))
            if out_games[w][0] in OUTCOME_STEPS:   # its ranks now, in case its stage is gone at the end
                time.sleep(3)
                early[w] = ranks(w, quiet=True).get(w, ({}, '-'))
                say('  %s ranks at leaving (%s): %s' % (w, early[w][1], ' '.join(
                    'p%d=%d' % kv for kv in sorted(early[w][0].items())) or 'none'))
        active = ''.join(w for w in active if w not in out_games)
    if not active:
        say('match over on every game (rounds handled: %s)' % (sorted(done_rounds) or '-'))
        break
    now = {w: now[w] for w in active}
    rnds = set(s[1] for s in now.values())
    if all(s[0] == 6 for s in now.values()) and len(rnds) == 1 and rnds.pop() not in done_rounds:
        rnd = now[active[0]][1]
        say('round %d in UpdatePhase on %s%s' % (rnd, active, (' (out: %s)' % ''.join(sorted(out_games))) if out_games else ''))
        if rnd == 4 and FINAL_WAIT != PHASE_WAIT:
            say('final: waiting %d s before the cut (--final-wait)' % FINAL_WAIT)
            t_w = time.time()
            while time.time() - t_w < FINAL_WAIT and left() > 60:
                time.sleep(2)
        else:
            time.sleep(PHASE_WAIT)
        cut_set = ''.join(w for w, s in states(active).items() if s == (6, rnd))
        if cut_set != active:
            say('not in UpdatePhase any more (left out of the snapshot and the cut): %s' %
                ''.join(w for w in active if w not in cut_set))
        if not cut_set:
            continue
        snapshot(cut_set, rnd)
        say('cut round %d: clock.py %g %s' % (rnd, CUT, cut_set))
        tool(['diag/twin/clock.py', '%g' % CUT, cut_set], timeout=120)
        done_rounds.add(rnd)
        rounds_seen.append(rnd)
        t_cut = time.time()
        while time.time() - t_cut < 240:   # every active game leaves this UpdatePhase (or the match)
            s2 = states(active)
            if all(s[0] != 6 or s[1] != rnd for s in s2.values()):
                break
            time.sleep(2)
        else:
            stuck = show(states(active))
            say('WARNING: still in round %d UpdatePhase 240 s after the cut: %s; cutting once more' % (rnd, stuck))
            tool(['diag/twin/clock.py', '%g' % CUT, active], timeout=120)
        say('after the cut:', show(states(active)))
        continue
    # Waiting for the next UpdatePhase: report changes, and do not wait forever on a lagging game.
    if now != last:
        say('states:', show(now))
        last = dict(now)
        t_change = time.time()
    elif time.time() - t_change > 300:
        at6 = [w for w in active if now[w][0] == 6 and now[w][1] not in done_rounds]
        if at6:
            lag = ''.join(w for w in active if w not in at6)
            say('WARNING: %s in a new UpdatePhase, %s not for 300 s (%s): going on with %s only' % (
                ''.join(at6), lag, show(now), ''.join(at6)))
            for w in lag:
                out_games[w] = now[w]
            active = ''.join(at6)
            t_change = time.time()
            continue
        fail('no game changed step for 300 s and none is in a new UpdatePhase: %s' % show(now))
    time.sleep(2)

# ---------------------------------------------------------------- 3. result
time.sleep(5)                       # let the Outcome rows settle (rows are written during 29..36)
print('=' * 20, 'result', '=' * 20, flush=True)
res = ranks(GAMES)
for w, v in early.items():          # stage gone now (back in the hub): use what it showed at its Outcome
    if not res.get(w, ({}, ''))[0] and v[0]:
        res[w] = (v[0], v[1] + ' read at its Outcome')
for w in GAMES:
    r, src = res.get(w, ({}, '-'))
    print('  %s ranks (%s): %s%s' % (w, src, ' '.join('p%d=%d' % (no, rk) for no, rk in sorted(r.items())) or 'none',
                                     '  [left at step %d round %d]' % out_games[w] if w in out_games else ''))
filled = {w: v[0] for w, v in res.items() if v[0]}
agree = len(filled) == len(GAMES) and all(v == next(iter(filled.values())) for v in filled.values())
print('ranks agree on all games: %s' % ('yes' if agree else 'NO'), flush=True)
if not agree and filled:
    groups = {}
    for w, v in filled.items():
        groups.setdefault(tuple(sorted(v.items())), []).append(w)
    for k, ws in groups.items():
        print('  %s: %s' % (''.join(ws), ' '.join('p%d=%d' % kv for kv in k)))
if agree:
    print('match4 done %s: rounds %s, ranks agree on %s' % (ts(), rounds_seen, GAMES), flush=True)
    sys.exit(0)
fail('ranks differ or missing (rounds %s; see above)' % rounds_seen)
