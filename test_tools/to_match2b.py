"""to_match2b.py = to_match2.py (all games from the hub into one match) made safe against the hub's Travel overlay.
Written 2026-11-17 for go4b.sh (static; not run yet); to_match2.py is unchanged. Notes: diag/net/run4_notes.md 7.

Differences from to_match2.py:
- 'hub' is answered with B first (closes the Travel overlay, which the classifier can still call 'hub': run 1
  'stuck:hub'), 1 s, then Minus (opens the Dusk Battle menu). B in the idle hub does nothing [I].
- A Travel overlay recognised by reference (diag/twin/ref_travel*.png, see to_hub2b.py) gets B.
- When a game stays stuck, its last screen is saved as diag/twin/<W>_stuck_<try>.png for the reference set.
Everything else (tries, Y press, join check by lanlog.joins, TO_MATCH_ONE_PRESS, TO_MATCH_WAIT) is unchanged."""
import os
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from screen import grab, state, press
from tctl import GAMES, call
from lanlog import joins
import to_hub2b_ref as REF


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
        if s == 'hub':
            press(w, 'B')
            time.sleep(1.0)
            press(w, 'Minus')
        else:
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


# run4_retry_notes.md 2: a 'black' game (loading / slow) used to count as a finished try, so the five tries
# went by in about 70 s (run4 08:31:39-08:32:47, D black in all five) and Y was never pressed. Now the menu
# phase has a time budget (TO_MATCH_MENU_SECS, default 300 s) and waits 10 s while any game is black.
MENU_SECS = float(os.environ.get('TO_MATCH_MENU_SECS', '300'))
t_menu = time.time()
attempt = 0
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
        time.sleep(2)
        continue
    j0 = {w: joins(w) for w in GAMES}
    both(lambda w: press(w, 'Y'))
    time.sleep(2)
    for w in ('' if os.environ.get('TO_MATCH_ONE_PRESS') else GAMES):
        if state(grab(w))[0] == 'mmenu':
            print(w, 'Y again', flush=True)
            press(w, 'Y')
    t = time.time()
    while time.time() - t < float(os.environ.get('TO_MATCH_WAIT', '15')):
        if all(joins(w) > j0[w] for w in GAMES):
            print('both joined', time.strftime('%H:%M:%S'), flush=True)
            sys.exit(0)
        time.sleep(1)
    print('no join:', {w: state(grab(w))[0] for w in GAMES}, flush=True)
print('FAILED', flush=True)
sys.exit(1)
