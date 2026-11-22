"""to_match2b_new2.py (2026-11-16, static, NOT swapped in): all games from the hub into ONE match, with proof,
and with no press that can split the games' searches. Notes: diag/net/pkgtest399_notes.md (second section).

Why: to_match2b_new.py (rejected, kept as to_match2b_proof_rejected.py) and the old to_match2b.py both press Y a
second time 2 s after the search press on every game whose screen still looks like the open menu, unless
TO_MATCH_ONE_PRESS is set (pkgtest.sh does not set it). In pkgtest 20:24 the match was made at 20:27:00 (tickets
1 + 2 at 20:26:59, both JoinGameSession at 20:27:01, lan-pair-join), but B's screen still showed the menu while
it loaded; the second Y reached B, B sent a new ticket (3, 20:27:16), left the shared session (20:27:28) and
re-joined alone (20:27:29); A sat alone and timed out (20:27:45); the games then kept searching on their own,
never together again (pkgtest's panel Start is pressed once). The proof also passed wrongly: it counted
JoinGameSession CALLS (3: A once, B twice) instead of distinct games.

Rules here (every press is either together on all games or a cancel):
  1. Menu phase as to_match2b (Travel overlay -> B; 'hub' or 'other' = possible idle hub: B, Minus, then up to
     TO_MATCH_MENU_OPEN_WAIT s polling for the menu; B_stuck_*.png case). A game that is in a LAN session (its
     dusk_lan.txt: last 'joined a LAN session' after the last 'session over') is never pressed.
  2. Search: Y on all games at once (threads), ONE press. No blind second press.
  3. A dropped press is decided only by the server log: after TO_MATCH_TICKET_WAIT s (default 12) fewer
     distinct ticket pids than games AND no match made (no online_match / online_matched_reply since the press).
  4. Re-search only after a dropped press, and only when ALL games are provably idle: every searching game is
     cancelled (Y on its 'mmgo' Cancel row), then wait until every peer's last matching request in frontdoor.log
     is a Cancel (or it never sent one), no game is in a session, and every screen reads 'mmenu' on two grabs
     2 s apart; then Y on all together. Otherwise no press at all.
  5. Once a match is made (online_match since the press) nothing is pressed again: the script only watches
     until joined or the time runs out (TO_MATCH_WAIT, default 15 s, + TO_MATCH_PROOF_WAIT, default 30 s).
  6. "both joined" = server: JoinGameSession from as many distinct users as games since the press, AND every
     game's dusk_lan.txt after its latest join since the press shows its player number ('player no ' or
     'message 4 delivered') and no 'alone for 30 s'. Exit 0. Otherwise exit 1 'FAILED: no proven join'.
Run folder: RUN_DIR, else the newest run folder with a frontdoor.log among diag/twin/runs/* and the pkgtest
scratch run (PKGTEST_DIR or diag/twin/pkgtest: state.json "run" and .../duskbloods_test/runs/*). Without a
run folder there is no proof and no re-press: the script waits for the log proof only, then exits.
Log paths come from lanlog.LAN (pkgtest.py run points them at its games)."""
import glob
import json
import os
import re
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from screen import grab, state, press
from tctl import GAMES, call
import lanlog
import to_hub2b_ref as REF

MENU_OPEN_WAIT = float(os.environ.get('TO_MATCH_MENU_OPEN_WAIT', '6'))
TICKET_WAIT = float(os.environ.get('TO_MATCH_TICKET_WAIT', '12'))
LOG_WAIT = float(os.environ.get('TO_MATCH_WAIT', '15'))
PROOF_WAIT = float(os.environ.get('TO_MATCH_PROOF_WAIT', '30'))
IDLE_WAIT = float(os.environ.get('TO_MATCH_IDLE_WAIT', '60'))
MENU_SECS = float(os.environ.get('TO_MATCH_MENU_SECS', '300'))
N = len(GAMES)


# ---------------------------------------------------------------- server logs
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


def server(since):
    """What the server logs show after `since`: ticket pids, match made, open-ticket peers, join users."""
    d = run_dir()
    out = {'dir': d, 'tickets': set(), 'matched': False, 'open': set(), 'users': set()}
    if not d:
        return out
    last, pid_ip = {}, {}
    for r in records(os.path.join(d, 'frontdoor.log')):
        t = r.get('time', 0)
        e = r.get('event')
        if e == 'online_player':
            pid_ip[r.get('pid')] = r.get('ip')
        if e == 'frontend_type':                      # whole history: an open ticket may predate `since`
            ty = str(r.get('type') or '')
            if ty in ('RequestMatchingTicketParams', 'RequestCancelMatchingTicketParams'):
                last[r.get('peer')] = ty
        if e == 'online_matched_reply' and pid_ip.get(r.get('pid')) in last:
            last[pid_ip[r.get('pid')]] = 'matched'    # a matched ticket is not an open one
        if t < since:
            continue
        if e == 'online_ticket' and r.get('pid') is not None:
            out['tickets'].add(r.get('pid'))
        if e in ('online_match', 'online_matched_reply'):
            out['matched'] = True
    # per-peer tracking only when every game has its own address (pkgtest: 127.0.0.1 + LAN IP); on a rig
    # where games share one address the screens ('mmenu' = "Start matchmaking" row, not "Cancel") decide.
    if len(last) >= N:
        out['open'] = {p for p, ty in last.items() if ty == 'RequestMatchingTicketParams'}
    for r in records(os.path.join(d, 'server.log')):
        if r.get('ev') == 'call' and r.get('t', 0) >= since and \
                str(r.get('method', '')).endswith('/JoinGameSession'):
            meta = r.get('meta') if isinstance(r.get('meta'), dict) else {}
            out['users'].add(meta.get('uid') or meta.get('authorization') or id(r))
    return out


# ---------------------------------------------------------------- game logs
_T = re.compile(r'^(\d\d):(\d\d):(\d\d) ')


def _lines_since(w, since):
    """dusk_lan.txt lines of game w stamped at or after `since` (local HH:MM:SS, same day)."""
    lo = time.localtime(since)
    lo_s = lo.tm_hour * 3600 + lo.tm_min * 60 + lo.tm_sec
    out = []
    for ln in lanlog.text(lanlog.LAN[w]).splitlines():
        m = _T.match(ln)
        if m and int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) >= lo_s:
            out.append(ln)
    return out


def in_session(w):
    txt = lanlog.text(lanlog.LAN[w])
    return txt.rfind('joined a LAN session') > max(txt.rfind('session over'), txt.rfind('left the LAN session'))


def game_joined(w, since):
    """(ok, text): latest join since the press has a player number and no 'alone for 30 s' after it."""
    ls = _lines_since(w, since)
    idx = [i for i, ln in enumerate(ls) if 'joined a LAN session' in ln]
    if not idx:
        return False, 'no join'
    after = ls[idx[-1]:]
    if any('alone for 30 s' in ln for ln in after):
        return False, 'alone in its session'
    if any(('player no ' in ln) or ('message 4 delivered' in ln) for ln in after):
        return True, f'joined, {len(idx)} join(s)'
    return False, 'joined, no player number yet'


# ---------------------------------------------------------------- screens
def wait_menu(w, secs):
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
        if in_session(w):                      # never press a game that is in (or loading into) a session
            res[w] = 'session'
            return
        im = grab(w)
        s = state(im)[0]
        if REF.is_travel(im):
            s = 'travel'
        if s in ('mmenu', 'black'):
            res[w] = s
            return
        if s == 'mmgo':                        # searching: leave it to the caller (cancel only together)
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
            continue
        press(w, {'err': 'A', 'settings': 'B', 'travel': 'B'}.get(s, 'B'))
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


def all_idle():
    """Every game provably back on the menu with no ticket: frontdoor + logs + two screen reads."""
    sv = server(0)
    if sv['open'] or any(in_session(w) for w in GAMES):
        return False, f'open tickets {sorted(map(str, sv["open"]))}, sessions ' \
                      f'{[w for w in GAMES if in_session(w)]}'
    s1 = {w: state(grab(w))[0] for w in GAMES}
    time.sleep(2)
    s2 = {w: state(grab(w))[0] for w in GAMES}
    ok = all(s1[w] == s2[w] == 'mmenu' for w in GAMES)
    return ok, f'screens {s1} / {s2}'


def cancel_all():
    """Cancel every search together (Y on the 'mmgo' Cancel row), then wait until all are idle."""
    st = {w: state(grab(w))[0] for w in GAMES}
    go = [w for w in GAMES if st[w] == 'mmgo' and not in_session(w)]
    if go:
        print(f'  cancel searches on {"".join(go)} together', flush=True)
        ts = [threading.Thread(target=press, args=(w, 'Y')) for w in go]
        [t.start() for t in ts]
        [t.join() for t in ts]
    t = time.time()
    why = ''
    while time.time() - t < IDLE_WAIT:
        ok, why = all_idle()
        if ok:
            return True, why
        time.sleep(2)
    return False, why


# ---------------------------------------------------------------- main
t_menu = time.time()
attempt = 0
last = 'no try reached the press'
pressed_once = False
while attempt < 5:
    attempt += 1
    res = {}
    both(to_menu, res, attempt)
    print(f'try {attempt} {time.strftime("%H:%M:%S")}: {res}', flush=True)
    if any(v == 'session' for v in res.values()):
        last = f'a game is in a session before the search: {res}; nothing pressed'
        break                                  # a press now could split the session
    if res != {w: 'mmenu' for w in GAMES}:
        if 'black' in res.values() and time.time() - t_menu < MENU_SECS:
            attempt -= 1
            time.sleep(10)
            continue
        if 'mmgo' in res.values():
            ok, why = cancel_all()
            print(f'  idle check: {ok} ({why})', flush=True)
            if not ok:
                last = f'could not bring every game back to an idle menu: {why}'
                break
        last = f'not on the menu: {res}'
        time.sleep(2)
        continue
    if pressed_once:
        ok, why = all_idle()                   # rule 4: provably idle, no ticket, before a second search
        if not ok:
            last = f'second search refused, not all idle: {why}'
            break
    since = time.time() - 1
    print(f'  search: Y on {"".join(GAMES)} together {time.strftime("%H:%M:%S")}', flush=True)
    both(lambda w: press(w, 'Y'))
    pressed_once = True
    if not run_dir():
        print('  no run folder: no server proof, no re-press', flush=True)
    # rule 3: dropped press? (server only; nothing is pressed while waiting)
    t = time.time()
    sv = server(since)
    while time.time() - t < TICKET_WAIT and len(sv['tickets']) < N and not sv['matched']:
        time.sleep(1)
        sv = server(since)
    if run_dir() and len(sv['tickets']) < N and not sv['matched']:
        last = f'dropped press: tickets from {len(sv["tickets"])} of {N} games, no match'
        print(f'  {last}; cancel all, then search again together', flush=True)
        ok, why = cancel_all()
        if not ok:
            last += f'; not all idle afterwards: {why}'
            break
        continue
    # rule 5/6: a match is made (or no proof source): only watch from here
    t = time.time()
    while time.time() - t < LOG_WAIT + PROOF_WAIT:
        sv = server(since)
        gj = {w: game_joined(w, since) for w in GAMES}
        srv_ok = (len(sv['users']) >= N) if sv['dir'] else True
        if srv_ok and all(v[0] for v in gj.values()):
            print('both joined', time.strftime('%H:%M:%S'), f'| {os.path.basename(sv["dir"])}: tickets from '
                  f'{len(sv["tickets"])} game(s), JoinGameSession from {len(sv["users"])} user(s)',
                  {w: v[1] for w, v in gj.items()}, flush=True)
            sys.exit(0)
        if any(v[1] == 'alone in its session' for v in gj.values()):
            break
        time.sleep(1)
    last = (f'match made: {sv["matched"]}; tickets {len(sv["tickets"])}, JoinGameSession users '
            f'{len(sv["users"])} (need {N}); games {({w: v[1] for w, v in gj.items()})}')
    break                                     # never search again after a match was made (rule 5)
print(f'FAILED: no proven join (no shared session for every game). Last: {last}', flush=True)
sys.exit(1)
