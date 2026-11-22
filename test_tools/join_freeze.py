"""Test for the join-time clock sync theory: once both twin games log 'joined a LAN session', freezes
game WHO (A|B) COUNT times for SECONDS each, 2 s apart. python diag/twin/join_freeze.py WHO [COUNT=4] [SECONDS=1.5]"""
import json, os, sys, time, psutil
who = sys.argv[1]; count = int(sys.argv[2]) if len(sys.argv) > 2 else 4; secs = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
paths = [os.path.join(os.environ['APPDATA'], 'eden', 'log', 'dusk_lan.txt'), 'diag/twin/userB/log/dusk_lan.txt']
def joined(p):
    try:
        return 'joined a LAN session' in open(p, errors='replace').read()
    except OSError:
        return False
t0 = time.time()
while time.time() - t0 < 400 and not all(joined(p) for p in paths):
    time.sleep(0.5)
pid = json.load(open('diag/twin/session.json'))['pids'][who]
p = psutil.Process(pid)
for i in range(count):
    print(time.strftime('%H:%M:%S'), 'freeze', who, secs, 's', flush=True)
    p.suspend(); time.sleep(secs); p.resume(); time.sleep(2)
