"""Late-guest fault trigger (diag/net/late_notes.md): once game WHO's own LAN assist log shows "match phase 2"
(PrepareSecond / spawn window of the match load), freezes game WHO COUNT times for SECONDS each, 2 s apart.
python diag/twin/phase2_freeze.py WHO [COUNT=14] [SECONDS=1.5]
Run 1 of 2026-11-16 18:27 (freezes from 1 s after B's "match phase 2", 49 s) lost player 1's state word on B; run 2
(freezes ended at "match phase 2") did not. Only a "match phase 2" line written AFTER this script started counts
(the log may still hold the last match's)."""
import json, os, sys, time, psutil
who = sys.argv[1]; count = int(sys.argv[2]) if len(sys.argv) > 2 else 14; secs = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
path = {'A': os.path.join(os.environ['APPDATA'], 'eden', 'log', 'dusk_lan.txt'),
        'B': 'diag/twin/userB/log/dusk_lan.txt'}[who]
MARK = 'match phase 2'


def lines():
    try:
        return open(path, errors='replace').read().splitlines()
    except OSError:
        return []


start = len(lines())          # lines present now belong to an earlier load (a log rewritten at a game start
t0 = time.time()              # is shorter: then every line counts)
while time.time() - t0 < 600:
    now = lines()
    fresh = now[start:] if len(now) >= start else now
    if any(l.rstrip().endswith(MARK) for l in fresh):
        break
    time.sleep(0.25)
else:
    print(time.strftime('%H:%M:%S'), 'no "match phase 2" line from', who, 'within 600 s; nothing frozen', flush=True)
    sys.exit(1)
print(time.strftime('%H:%M:%S'), who, 'logged "match phase 2"; freezing now', flush=True)
pid = json.load(open('diag/twin/session.json'))['pids'][who]
p = psutil.Process(pid)
for i in range(count):
    print(time.strftime('%H:%M:%S'), 'freeze', who, secs, 's', flush=True)
    p.suspend()
    try:
        time.sleep(secs)
    finally:
        p.resume()
    time.sleep(2)
