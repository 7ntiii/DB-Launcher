"""Both twin games from the hub into one match: get both onto the open Dusk Battle menu (screen
checked), press Y together, confirm both joined, retry if not.

"Joined" needs BOTH of:
  - the logs (watcher mgr3-join or LAN assist 'joined a LAN session') counted up on every game, and
  - proof from this run's server logs (diag/twin/runs/<newest>/ or RUN_DIR): after the press, a
    matching ticket from every game (frontdoor.log "online_ticket", distinct pids) or a
    JoinGameSession call per game (server.log).
The 15:59 run printed "both joined" with no ticket at all (frontdoor.log had only
CancelMatchingTicket), so the log count alone is not enough.
Waits are bounded: TO_MATCH_WAIT (default 15 s) for the log joins, TO_MATCH_PROOF_WAIT (default
30 s) for the server proof; then the search is pressed again (next try). Exit 1 after 5 tries."""
import glob, json, os, sys, threading, time
sys.path.insert(0, 'diag/twin')
from screen import grab, state, press
from tctl import GAMES
from lanlog import joins          # watcher mgr3-join or LAN assist 'joined a LAN session'


def run_dir():
    d = os.environ.get('RUN_DIR')
    if d:
        return d
    dirs = [p for p in glob.glob('diag/twin/runs/*') if os.path.isdir(p)]
    return max(dirs, key=os.path.getmtime) if dirs else ''


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
        return False, 'no run folder under diag/twin/runs'
    pids = {r.get('pid') for r in records(os.path.join(d, 'frontdoor.log'))
            if r.get('event') == 'online_ticket' and r.get('time', 0) >= since}
    pids.discard(None)
    joins_s = sum(1 for r in records(os.path.join(d, 'server.log'))
                  if r.get('ev') == 'call' and r.get('t', 0) >= since and
                  str(r.get('method', '')).endswith('/JoinGameSession'))
    need = len(GAMES)
    ok = len(pids) >= need or joins_s >= need
    return ok, f'{os.path.basename(d)}: tickets from {len(pids)} game(s), JoinGameSession {joins_s} (need {need})'


def to_menu(w, res):
    for _ in range(10):
        s, _d = state(grab(w))
        if s in ('mmenu', 'black'):
            res[w] = s; return
        press(w, {'hub': 'Minus', 'err': 'A', 'settings': 'B', 'mmgo': 'Y'}.get(s, 'B'))
        time.sleep(2)
    res[w] = 'stuck:' + s


def both(f, *a):
    ts = [threading.Thread(target=f, args=(w,) + a) for w in GAMES]
    [t.start() for t in ts]; [t.join() for t in ts]


last = 'no try reached the press'
for attempt in range(1, 6):
    res = {}; both(to_menu, res)
    print(f'try {attempt} {time.strftime("%H:%M:%S")}: {res}', flush=True)
    if res != {w: 'mmenu' for w in GAMES}:
        last = f'not on the menu: {res}'
        time.sleep(2); continue
    j0 = {w: joins(w) for w in GAMES}
    since = time.time() - 1
    both(lambda w: press(w, 'Y'))
    time.sleep(2)
    for w in ('' if os.environ.get('TO_MATCH_ONE_PRESS') else GAMES):   # a dropped press: still on the menu -> press again
        if state(grab(w))[0] == 'mmenu':
            print(w, 'Y again', flush=True); press(w, 'Y')
    t = time.time()
    logs_ok = False
    while time.time() - t < float(os.environ.get('TO_MATCH_WAIT', '15')):   # longer with the host-start hold
        if all(joins(w) > j0[w] for w in GAMES):
            logs_ok = True; break
        time.sleep(1)
    ok, why = proof(since)
    t = time.time()
    while not ok and time.time() - t < float(os.environ.get('TO_MATCH_PROOF_WAIT', '30')):
        time.sleep(1)
        ok, why = proof(since)
    if logs_ok and ok:
        print('both joined', time.strftime('%H:%M:%S'), '|', why, flush=True); sys.exit(0)
    last = f'log joins {"seen" if logs_ok else "missing"}; server proof: {why}'
    print(f'no join (try {attempt}): {last};',
          {w: state(grab(w))[0] for w in GAMES}, '-> search pressed again', flush=True)
print(f'FAILED: no proven join after 5 tries (no matching ticket / JoinGameSession for every game '
      f'in the server logs). Last: {last}', flush=True)
sys.exit(1)
