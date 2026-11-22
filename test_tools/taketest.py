"""Rig test: WHO teleports to the nearest shown world item, presses Y (up to 3 tries), prints the inventory
difference on both games.  usage: python diag/twin/taketest.py A|B"""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl
import rewards as R

who = sys.argv[1]
PY = sys.executable
SHOT = '<WORKSPACE>/diag/twin/%s_tt%d.png'


def run(args, t=60):
    try:
        return subprocess.run([PY] + args, capture_output=True, text=True, timeout=t).stdout
    except subprocess.TimeoutExpired:
        return ''


def inv(w):
    m = R.Mem(w)
    return {(a, b): c for _, a, b, c in R.inventory(m, R.local_pgd(m))}


def nearest():
    for l in run(['diag/twin/item_sources.py', who]).splitlines():
        if len(sys.argv) > 2 and not (l.startswith('I') and sys.argv[2] in l.split()[4]):
            continue
        if l.startswith('I') and ('flags 00000008' in l or 'flags 00880009' in l or 'flags 00100008' in l):
            p = l[l.index('(') + 1:l.index(')')].split()
            return l.split()[0], l.split()[4], [float(x) for x in p]
    return None


before = {w: inv(w) for w in 'AB'}
tgt = nearest()
print('target', tgt)
if tgt:
    name, iid, (x, y, z) = tgt
    for t in range(3):
        run(['diag/twin/goto.py', who, '%.1f' % x, '%.1f' % (y + 0.3), '%.1f' % z], 30)
        time.sleep(1.5)
        run(['diag/twin/item_sources.py', who, 'goto', name, 'nudge'], 40)
        time.sleep(0.6)
        tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}}, SHOT % (who, t))
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['Y'], 'frames': 8},
                                                                         {'buttons': [], 'frames': 50}]}})
        time.sleep(3.5)
        after = {w: inv(w) for w in 'AB'}
        if after != before:
            break
    for w in 'AB':
        d = ['%08x %08x x%d->x%d' % (k[0], k[1], before[w].get(k, 0), after[w].get(k, 0))
             for k in set(before[w]) | set(after[w]) if before[w].get(k, 0) != after[w].get(k, 0)]
        print(w, 'inventory change:', d or 'none')
    for w in 'AB':
        left = [l for l in run(['diag/twin/item_sources.py', w]).splitlines() if l.startswith('I') and iid in l]
        print(w, 'item %s still listed: %s' % (iid, [l[:70] for l in left] or 'no'))
