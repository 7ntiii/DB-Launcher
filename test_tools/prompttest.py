"""Rig test for OWNER_PROMPT: KILLER kills enemies until a drop (list 2) appears, then the OTHER player stands on it
(screenshot: expect no prompt), then the killer stands on it (screenshot: prompt) and presses Y.
usage: python diag/twin/prompttest.py A|B"""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl
import rewards as R

killer = sys.argv[1]
other = 'B' if killer == 'A' else 'A'
PY = sys.executable
SHOT = '<WORKSPACE>/diag/twin/%s_pt_%s.png'


def run(args, t=110):
    try:
        return subprocess.run([PY] + args, capture_output=True, text=True, timeout=t).stdout
    except subprocess.TimeoutExpired:
        return ''


def drops(w):
    return [l for l in run(['diag/twin/item_sources.py', w], 60).splitlines() if l.startswith('I') and 'list 2' in l]


def inv(w):
    m = R.Mem(w)
    return {(a, b): c for _, a, b, c in R.inventory(m, R.local_pgd(m))}


old = set(l.split()[4] for l in drops(killer))
new = None
for i in range(6):
    es = [l for l in run(['diag/twin/item_sources.py', killer], 60).splitlines()
          if l.startswith('E') and ('hp 192 ' in l or 'hp 144 ' in l) and 'DROPPED' not in l]
    if not es:
        print('no enemy'); break
    run(['diag/twin/item_sources.py', killer, 'goto', es[0].split()[0]], 40)
    out = run(['diag/twin/kill.py', killer, '10'])
    print('kill', out.strip().splitlines()[-1][:60] if out.strip() else '?')
    time.sleep(2)
    cur = [l for l in drops(killer) if l.split()[4] not in old]
    if cur:
        new = cur[0]; break
print('drop', new[:100] if new else None)
if new:
    iid = new.split()[4]
    x, y, z = [float(v) for v in new[new.index('(') + 1:new.index(')')].split()]
    print(run(['diag/twin/itemauth.py', 'AB', 'take'], 60).count('item %s' % iid.lstrip('0')), 'take lines')
    for w, tag in ((other, 'other'), (killer, 'owner')):
        b = {v: inv(v) for v in 'AB'}
        for t in range(3):
            run(['diag/twin/goto.py', w, '%.1f' % x, '%.1f' % (y + 0.3), '%.1f' % z], 30)
            time.sleep(1.5)
            lst = [l for l in drops(w) if iid in l]
            if lst:
                run(['diag/twin/item_sources.py', w, 'goto', lst[0].split()[0], 'nudge'], 40)
            time.sleep(0.6)
            tctl.call(w, {'method': 'screenshot', 'params': {'height': 480}}, SHOT % (w, '%s%d' % (tag, t)))
            tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['Y'], 'frames': 8},
                                                                           {'buttons': [], 'frames': 50}]}})
            time.sleep(3.5)
            a = {v: inv(v) for v in 'AB'}
            if a != b:
                break
        for v in 'AB':
            d = ['%08x x%d->x%d' % (k[0], b[v].get(k, 0), a[v].get(k, 0))
                 for k in set(b[v]) | set(a[v]) if b[v].get(k, 0) != a[v].get(k, 0)]
            print('%s (%s) pressed Y: %s inventory change: %s' % (w, tag, v, d or 'none'))
        for v in 'AB':
            print('   %s still lists %s: %s' % (v, iid, [l[:60] for l in drops(v) if iid in l] or 'no'))
