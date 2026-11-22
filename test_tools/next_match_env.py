"""From the Outcome screen: back to the hub, next match, cut Phase I to 5 s, then screenshot both
event cards and print both games' environment-event log lines. python diag/twin/next_match_env.py TAG"""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl
from mem import Mem

tag = sys.argv[1]
LOGS = {'A': r'C:\Users\<user>\AppData\Roaming\eden\log\dusk_lan.txt', 'B': 'diag/twin/userB/log/dusk_lan.txt'}


def phase(w):
    m = Mem(w)
    par = m.u64(m.base + 0x5B3CDF8)
    return m.u32(par + 0x50) if par else -1


for w in 'AB':
    tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['A'], 'frames': 6}, {'frames': 20}]}})
time.sleep(30)
subprocess.run([sys.executable, 'diag/twin/to_match2.py'], timeout=400)
t0 = time.time()
while time.time() - t0 < 300 and not (phase('A') == 6 and phase('B') == 6):
    time.sleep(3)
time.sleep(12)
subprocess.run([sys.executable, 'diag/twin/clock.py', '5', 'AB'])
shot = False
t0 = time.time()
while time.time() - t0 < 200:
    ph = {w: phase(w) for w in 'AB'}
    if all(p == 18 for p in ph.values()) or (not shot and 18 in ph.values()):
        time.sleep(2)
        for w in 'AB':
            subprocess.run([sys.executable, 'diag/twin/tctl.py', w, 'shot', tag], capture_output=True)
        shot = True
        if all(p == 18 for p in ph.values()):
            break
    if all(p in (21, 22, 26, 4, 6) for p in ph.values()) and shot:
        break
    time.sleep(1)
for w, path in LOGS.items():
    lines = [l.rstrip() for l in open(path, errors='replace') if 'environment' in l]
    print(w, lines[-2:])
