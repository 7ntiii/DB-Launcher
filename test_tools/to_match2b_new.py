"""to_match2b.py = to_match2.py (all games from the hub into one match) made safe against the hub's Travel overlay.
Written 2026-11-17 for go4b.sh; to_match2.py is unchanged. Notes: diag/net/run4_notes.md 7.
to_match2b_new.py (2026-11-16, static, swap in between runs): + the proof-and-retry of to_match2.py and
+ the idle-hub fix below.

Differences from to_match2.py:
- 'hub' is answered with B first (closes the Travel overlay, which the classifier can still call 'hub': run 1
  'stuck:hub'), 1 s, then Minus (opens the Dusk Battle menu). B in the idle hub does nothing [I].
- A Travel overlay recognised by reference (diag/twin/ref_travel*.png, see to_hub2b.py) gets B.
- When a game stays stuck, its last screen is saved as diag/twin/<W>_stuck_<try>.png for the reference set.

Idle hub with no menu (pkgtest v3.9.9 19:54-19:57, B_stuck_1..5.png): the game stood in the idle hub on the
warp circle, camera turned; screen.py called every shot 'other' (distance 17-32, not 'hub'), so the old loop
pressed only B (the default for 'other'), which does nothing there, and Minus was never sent. Now an 'other'
screen that is not the Travel overlay is treated as a possible idle hub: B, 1 s, Minus, then up to
TO_MATCH_MENU_OPEN_WAIT (default 6 s) polling for the menu before the next press (so a slow menu is not shut
again). Minus on a screen that is not the hub opens at most a game menu, which the next B closes.

"Joined" needs BOTH (as to_match2.py):
  - the logs (watcher mgr3-join or LAN assist 'joined a LAN session') counted up on every game, and
  - proof from this run's server logs: after the press, a matching ticket from every game (frontdoor.log
    "online_ticket", distinct pids) or a JoinGameSession call per game (server.log).
  Run folder: RUN_DIR if set, else the newest run folder with a frontdoor.log among diag/twin/runs/* and the
  pkgtest scratch run (PKGTEST_DIR or diag/twin/pkgtest, its state.json "run", else
  .../Lichii/user/duskbloods_test/runs/<newest, not game1_*>).
Waits are bounded: TO_MATCH_WAIT (default 15 s) for the log joins, TO_MATCH_PROOF_WAIT (default 30 s) for the
server proof; then the search is pressed again (next try). Exit 1 after 5 tries with "FAILED: no proven join".
The menu phase keeps its time budget (TO_MATCH_MENU_SECS, default 300 s) while a game is black."""
import glob
import json
import os
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from screen import grab, state, press
from tctl import GAMES, call
from lanlog import joins
import to_hub2b_ref as REF

MENU_OPEN_WAIT = float(os.environ.get('TO_MATCH_MENU_OPEN_WAIT', '6'))


# ---------------------------------------------------------------- server proof (from to_match2.py)
def _run_candidates():
    out = [p for p in glob.glob('diag/twin/runs/*') if os.path.isdir(p)]
    pt = os.environ.get('PKGTEST_DIR') or 'diag/twin/pkgtest'
    try:
        with open(os.path.join(pt, 'state.json'), errors='replace') as f:
            r = json.load(f).get('run')
        if r and os.path.isdir(r):
            out.append(r)
    except (OSError, ValueError, AttributeError):
        pass
    out += [p for p in glob.glob(os.path.join(pt, '*', 'Lichii', 'user', 'duskbloods_test', 'runs', '*'))
            if os.path.isdir(p) and not os.path.basename(p).startswith('game')]
    return out


def run_dir():
    d = os.environ.get('RUN_DIR')
    if d:
        return d
    best, bt = '', -1.0
    for p in _run_candidates():
        try:
            t = os.path.getmtime(os.path.join(p, 'frontdoor.log'))
        except OSError:
            continue
        if t > bt:
            best, bt = p, t
    return best


def records(path):
    try:
        with open(path, errors='replace') as f:
            for line in f:
                line = line.strip()
                if line.startswith('{'):
                    try:
                        yield json.loads(line)
                    except ValueError:
                        pass
    except OSError:
        return


def proof(since):
    """(proved, text): tickets / JoinGameSession calls in this run's server logs after `since`."""
    d = run_dir()
    if not d:
        return False, 'no run folder with a frontdoor.log'
    pids = {r.get('pid') for r in records(os.path.join(d, 'frontdoor.log'))
            if r.get('event') == 'online_ticket' and r.get('time', 0) >= since}
    pids.discard(None)
    joins_s = sum(1 for r in records(os.path.join(d, 'server.log'))
                  if r.get('ev') == 'call' and r.get('t', 0) >= since and
                  str(r.get('method', '')).endswith('/JoinGameSession'))
    need = len(GAMES)
    ok = len(pids) >= need or joins_s >= need
    return ok, f'{os.path.basename(d)}: tickets from {len(pids)} game(s), JoinGameSession {joins_s} (need {need})'


# ---------------------------------------------------------------- menu
def wait_menu(w, secs):
    """Poll up to secs for the open Dusk Battle menu; returns the last state."""
    s = '?'
    t = time.time()
    while time.time() - t < secs:
        time.sleep(1.0)
        s = state(grab(w))[0]
        if s in ('mmenu', 'black'):
            break
    return s


def to_menu(w, res, attempt):
    s = '?'
    for _ in range(10):
        im = grab(w)
        s = state(im)[0]
        if REF.is_travel(im):                  # also when screen.py says 'hub' (run 1: 'stuck:hub')
            s = 'travel'
        if s in ('mmenu', 'black'):
            res[w] = s
            return
        if s in ('hub', 'other'):              # 'other': idle hub at another camera angle (B_stuck_*.png)
            press(w, 'B')
            time.sleep(1.0)
            press(w, 'Minus')
            s2 = wait_menu(w, MENU_OPEN_WAIT)
            if s2 in ('mmenu', 'black'):
                res[w] = s2
                return
            if s == 'other':
                print(f'  {w}: idle hub? ({s} -> {s2} after Minus), menu-open step again', flush=True)
            continue
        press(w, {'err': 'A', 'settings': 'B', 'mmgo': 'Y', 'travel': 'B'}.get(s, 'B'))
        time.sleep(2)
    res[w] = 'stuck:' + s
    try:
        call(w, {'method': 'screenshot', 'params': {'height': 360}}, 'diag/twin/%s_stuck_%d.png' % (w, attempt))
    except Exception:
        pass


def both(f, *a):
    ts = [threading.Thread(target=f, args=(w,) + a) for w in GAMES]
    [t.start() for t in ts]
    [t.join() for t in ts]


# run4_retry_notes.md 2: a 'black' game (loading / slow) is not a finished try; the menu phase has a time
# budget (TO_MATCH_MENU_SECS, default 300 s) and waits 10 s while any game is black.
MENU_SECS = float(os.environ.get('TO_MATCH_MENU_SECS', '300'))
t_menu = time.time()
attempt = 0
last = 'no try reached the press'
while attempt < 5:
    attempt += 1
    res = {}
    both(to_menu, res, attempt)
    print(f'try {attempt} {time.strftime("%H:%M:%S")}: {res}', flush=True)
    if res != {w: 'mmenu' for w in GAMES}:
        black = [w for w, s in res.items() if s == 'black']
        if black and time.time() - t_menu < MENU_SECS:
            attempt -= 1                       # a black screen is not a failed try: wait for it
            print(f'  waiting for {"".join(sorted(black))} (black), {time.time() - t_menu:.0f} of '
                  f'{MENU_SECS:.0f} s', flush=True)
            time.sleep(10)
            continue
        if black:
            for w in black:
                try:
                    call(w, {'method': 'screenshot', 'params': {'height': 360}},
                         'diag/twin/%s_stuck_black.png' % w)
                except Exception:
                    pass
        last = f'not on the menu: {res}'
        time.sleep(2)
        continue
    j0 = {w: joins(w) for w in GAMES}
    since = time.time() - 1
    both(lambda w: press(w, 'Y'))
    time.sleep(2)
    for w in ('' if os.environ.get('TO_MATCH_ONE_PRESS') else GAMES):   # a dropped press: still on the menu
        if state(grab(w))[0] == 'mmenu':
            print(w, 'Y again', flush=True)
            press(w, 'Y')
    t = time.time()
    logs_ok = False
    while time.time() - t < float(os.environ.get('TO_MATCH_WAIT', '15')):
        if all(joins(w) > j0[w] for w in GAMES):
            logs_ok = True
            break
        time.sleep(1)
    ok, why = proof(since)
    t = time.time()
    while not ok and time.time() - t < float(os.environ.get('TO_MATCH_PROOF_WAIT', '30')):
        time.sleep(1)
        ok, why = proof(since)
    if logs_ok and ok:
        print('both joined', time.strftime('%H:%M:%S'), '|', why, flush=True)
        sys.exit(0)
    last = f'log joins {"seen" if logs_ok else "missing"}; server proof: {why}'
    print(f'no join (try {attempt}): {last};', {w: state(grab(w))[0] for w in GAMES},
          '-> search pressed again', flush=True)
print(f'FAILED: no proven join after 5 tries (no matching ticket / JoinGameSession for every game '
      f'in the server logs). Last: {last}', flush=True)
sys.exit(1)
