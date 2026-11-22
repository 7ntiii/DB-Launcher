"""Waits until both twin games are in the battle (phase 6 in fresh assist logs), then runs lag.py
both ways N times. python diag/twin/wait_lag.py [N=3] [MAX_WAIT=480]"""
import os, re, subprocess, sys, time
sys.path.insert(0, 'diag/twin')
from tctl import GAMES
from lanlog import LAN
paths = [LAN[w] for w in GAMES]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 480
t0 = time.time()
def ready(p):
    try:
        return os.path.getmtime(p) > t0 - 240 and bool(re.search(r'match phase 6\b', open(p, errors='replace').read()))
    except OSError:
        return False
while time.time() - t0 < limit and not all(ready(p) for p in paths):
    time.sleep(5)
print('waited %.0f s' % (time.time() - t0), [ready(p) for p in paths], flush=True)
time.sleep(6)
for i in range(n):
    for m in 'AB':
        r = subprocess.run([sys.executable, 'diag/twin/lag.py', m, '8'], capture_output=True, text=True)
        keep = [l for l in r.stdout.splitlines() if 'delay' in l or 'phase clock' in l or 'copy at' in l]
        print(time.strftime('%H:%M:%S'), keep or (r.stdout + r.stderr)[-300:], flush=True)
    time.sleep(10)
