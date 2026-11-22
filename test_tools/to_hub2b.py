"""to_hub2b.py = to_hub2.py (boot -> hub by live screen checks) made safe against the hub's Travel overlay.
Written 2026-11-17 for go4b.sh (static; not run yet). to_hub2.py and screen.py are unchanged; notes:
diag/net/run4_notes.md section 7.

Why go4b's game C ended in the Travel overlay [I, from the code + the lead's two runs]:
- to_hub2.py treats EVERY non-black, non-title, non-hub screen after the title as a cutscene and sends the skip
  pair Plus, A (up to 8 times). In the hub, Plus opens the Travel overlay ("Travel to House of Night: Hall",
  A OK / B Close), and the A that follows confirms a travel.
- So when C already stands in the hub but the classifier does not yet say 'hub', the skip pair opens the overlay
  (run 1: the overlay stayed open, the classifier still said 'hub' through it, to_match2's Minus did nothing:
  'stuck:hub') or travels to another hub view that never matches the hub reference (run 2: TIMEOUT other).
- Why only with go4b: C's 2048 / 1536 MiB texture cap (plus 0.5x, plus lazy commit's first-touch faults) makes
  its hub frames blurrier / slower to stream in, so the hub distance stays above the threshold for longer while
  C is already idle in the hub. go4_hub.txt shows it: C's 'other' lines just before the hub carry the distance
  (compare with a go4.sh run: values close to 8 = this cause).

What this copy does differently (everything else as to_hub2.py):
1. Moving vs still: before a skip pair, two frames 1 s apart are compared (mean pixel difference of 64x36
   images). A cutscene moves (> STILL = 1.5); the idle hub, the Travel overlay and dialogs do not. Only a moving
   screen gets Plus, A.
2. A still, unknown screen gets B (closes the Travel overlay and most popups; B in the idle hub does nothing
   [I]). After 3 B presses on the same still screen, A once (a dialog that needs OK), then B again.
3. Travel overlay by reference (rule and how to take the reference: to_hub2b_ref.py): state 'travel' -> B.
4. Lenient hub: still for 3 checks in a row and hub distances under 1.5 x the normal thresholds = hub (printed as
   'hub (lenient)'): a blurred, idle hub is accepted instead of being "skipped".
5. On the way out, one B press (closes an overlay opened in the last moment; harmless in the hub [I]) and a
   final check that the state is still hub.
"""
import os
import socket
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from PIL import Image, ImageChops, ImageStat
from tctl import PORT, GAMES
import screen
from screen import grab, state, press
import to_hub2b_ref as REF

STILL = 1.5
# run4_live_notes (2026-11-17): the Travel overlay exists only in the hub. Default: the first 'travel' state = in
# the hub: B once (close it), then 'hub in'; no Plus after that. In run4 C and D lost 6-7 min in a loop of
# moving hub -> Plus, A (opens Travel / travels to the Hall) -> B. TO_HUB2B_OLD_TRAVEL=1 = the old behaviour (B, go on).
OLD_TRAVEL = os.environ.get('TO_HUB2B_OLD_TRAVEL', '0') == '1'


def small(im):
    return im.convert('L').resize((64, 36), Image.BOX)


def diff(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def classify(who, im):
    """screen.state plus 'travel' (by reference) and the hub distances for the lenient test"""
    s, dist = state(im)
    sm = small(im)
    td = REF.travel_dist(im)
    if td is not None and td < REF.T_TRAVEL:     # before 'hub': screen.py can call the open overlay 'hub'
        return 'travel', td, sm
    return s, dist, sm


def near_hub(im):
    """hub distances (full, row) with the thresholds of the check this game uses, x 1.5"""
    w = im.info.get('twin_game')
    if screen.tolerant(w):
        x = im.convert('L').resize((640, 360), Image.BOX) if im.size != (640, 360) else im
        fd = min(screen.d(x.resize((64, 36), Image.BOX), r) for r in screen._full_t['hub'])
        rd = min(screen.d(screen._sig(x), r) for r in screen._row_t['hub'])
        return fd < 1.5 * screen.T_FULL_HUB and rd < 1.5 * screen.T_ROW_HUB
    fd = min(screen.d(im.resize((64, 36)), r) for r in screen._full['hub'])
    rd = min(screen.d(im.crop(screen.ROW), r) for r in screen._row['hub'])
    return fd < 12 and rd < 9


HUB_SECS = float(__import__('os').environ.get('TO_HUB_SECS', '300'))   # go4b: 2x for lazy / capped games


def wait_server(who, timeout=HUB_SECS):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(('127.0.0.1', PORT[who]), 1).close()
            return True
        except OSError:
            time.sleep(1)
    return False


def run(who):
    t0 = time.time()
    if not wait_server(who):
        print(who, 'no debug server', flush=True)
        return
    if 'D' in GAMES:
        t0 = time.time()
    skips, title_done, last, still_n, bpress, prev = 0, False, None, 0, 0, None
    while time.time() - t0 < HUB_SECS:
        try:
            im = grab(who)
            s, dist, sm = classify(who, im)
        except Exception:
            im, s, dist, sm = None, 'noshot', 0.0, None
        if s != last:
            print(f'{who} {time.time() - t0:5.1f}s {s} {dist:.1f}', flush=True)
            last = s
        still = prev is not None and sm is not None and diff(sm, prev) < STILL
        still_n = still_n + 1 if still else 0
        prev = sm
        if s == 'hub' or (s == 'other' and still_n >= 3 and im is not None and near_hub(im)):
            press(who, 'B')                      # close an overlay opened at the last moment
            time.sleep(1.5)
            s2 = state(grab(who))[0]
            if s2 == 'hub' or s == 'other':
                if s == 'other':
                    print(f'{who} hub (lenient: still, near the hub reference; now {s2})', flush=True)
                print(f'{who} hub in {time.time() - t0:.0f}s', flush=True)
                return
            continue
        if s in ('black', 'noshot'):
            time.sleep(1.5)
            continue
        if s == 'travel':
            print(f'{who} Travel overlay: B', flush=True)
            press(who, 'B')
            time.sleep(2)
            if not OLD_TRAVEL:
                try:
                    now = state(grab(who))[0]
                except Exception:
                    now = 'noshot'
                print(f'{who} hub (via the Travel overlay; now {now})', flush=True)
                print(f'{who} hub in {time.time() - t0:.0f}s', flush=True)
                return
            continue
        if s == 'menu':
            press(who, 'A')
            time.sleep(2.5)
            continue
        if not title_done:
            press(who, 'A')
            title_done = True
            time.sleep(2.5)
            continue
        time.sleep(1.0)                          # moving or still? second frame 1 s later
        try:
            sm2 = small(grab(who))
        except Exception:
            sm2 = None
        moving = sm is not None and sm2 is not None and diff(sm, sm2) >= STILL
        prev = sm2
        if moving and skips < 8:                 # cutscene: Plus (skip prompt) then A (confirm)
            press(who, 'Plus')
            time.sleep(0.8)
            press(who, 'A')
            skips += 1
            bpress = 0
        elif not moving:                         # still unknown screen: overlay / popup
            bpress += 1
            btn = 'A' if bpress % 4 == 0 else 'B'
            print(f'{who} still screen ({s} {dist:.1f}): {btn}', flush=True)
            press(who, btn)
        time.sleep(2)
    print(who, 'TIMEOUT', last, flush=True)


ts = [threading.Thread(target=run, args=(w,)) for w in GAMES]
[t.start() for t in ts]
[t.join() for t in ts]
