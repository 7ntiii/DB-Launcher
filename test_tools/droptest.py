"""Rig test: WHO kills the nearest enemy, walks to the nearest world item, presses Y, prints both games' state.
usage: python diag/twin/droptest.py A|B [nokill]"""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl

who = sys.argv[1]
PY = sys.executable


def run(args, t=110):
    try:
        return subprocess.run([PY] + args, capture_output=True, text=True, timeout=t).stdout
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'


def items(w):
    out = run(['diag/twin/item_sources.py', w], 60)
    return [l[:110] for l in out.splitlines() if l.startswith('I')]


def counts():
    out = run(['diag/twin/itemauth.py', 'AB', '4260', '8000'], 60)
    return [l.strip()[:120] for l in out.splitlines() if 'goods' in l or 'world items' in l]


print('before', counts())
if 'nokill' not in sys.argv:
    out = run(['diag/twin/kill.py', who, '14'])
    print('kill:', out.strip().splitlines()[-1] if out.strip() else out)
    time.sleep(2)
for w in 'AB':
    print(w, items(w))
out = run(['diag/twin/item_sources.py', who, 'goto', 'I0', 'nudge'], 40)
print('goto:', out.strip().splitlines()[-1] if out.strip() else out)
time.sleep(0.8)
tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}},
          '<WORKSPACE>/diag/twin/%s_dt1.png' % who)
tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['Y'], 'frames': 8},
                                                                 {'buttons': [], 'frames': 50}]}})
time.sleep(4)
print('after', counts())
for w in 'AB':
    print(w, items(w))
