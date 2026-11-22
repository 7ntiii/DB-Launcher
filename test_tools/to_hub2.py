"""Both twin games: boot -> hub, driven by live screen checks instead of fixed waits."""
import socket, sys, threading, time
sys.path.insert(0, 'diag/twin')
from tctl import PORT, GAMES
from screen import grab, state, press
def wait_server(who, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(('127.0.0.1', PORT[who]), 1).close(); return True
        except OSError:
            time.sleep(1)
    return False
def run(who):
    t0 = time.time()
    if not wait_server(who):
        print(who, 'no debug server', flush=True); return
    if 'D' in GAMES:                     # 4 games: D's server is up ~175 s in; budget from here
        t0 = time.time()
    skips, title_done, last = 0, False, None
    while time.time() - t0 < 300:
        try:
            s, dist = state(grab(who))
        except Exception as ex:          # screenshot not ready yet during boot
            s, dist = 'noshot', 0.0
        if s != last:
            print(f'{who} {time.time() - t0:5.1f}s {s} {dist:.1f}', flush=True); last = s
        if s == 'hub':
            print(f'{who} hub in {time.time() - t0:.0f}s', flush=True); return
        if s in ('black', 'noshot'):
            time.sleep(1.5); continue
        if s == 'menu':
            press(who, 'A'); time.sleep(2.5); continue
        if not title_done:               # first non-black screen = title: any button
            press(who, 'A'); title_done = True; time.sleep(2.5); continue
        if skips < 8:                    # cutscene: Plus (skip prompt) then A (confirm)
            press(who, 'Plus'); time.sleep(0.8); press(who, 'A'); skips += 1
        time.sleep(2)
    print(who, 'TIMEOUT', last, flush=True)
ts = [threading.Thread(target=run, args=(w,)) for w in GAMES]
[t.start() for t in ts]; [t.join() for t in ts]
