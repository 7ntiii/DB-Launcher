"""Finds which of many functions run when a button is pressed (through hp_watch.py's command file):
sets breakpoints on all, drops the ones that fire without the press (per-frame code) over a few
rounds, then presses the button and lists what fired. python diag/twin/bp_sweep.py WHO BTN OFF OFF ..."""
import re, subprocess, sys, time, collections
who, btn = sys.argv[1], sys.argv[2]
cands = [int(a, 16) for a in sys.argv[3:]]
LOG, CMD = 'diag/twin/hp_watch.log', 'diag/twin/hp_watch.cmd'
def send(lines):
    open(CMD, 'w').write('\n'.join(lines) + '\n')
    while __import__('os').path.exists(CMD): time.sleep(0.2)
def hits_since(mark):
    c = collections.Counter(); bts = {}
    for l in open(LOG).read().splitlines()[mark:]:
        m = re.search(r'hit .*pc=main\+(0x[0-9a-f]+)', l)
        if m:
            c[int(m.group(1), 16)] += 1; bts.setdefault(int(m.group(1), 16), l)
    return c, bts
noisy = set()
for rnd in range(6):
    mark = len(open(LOG).read().splitlines())
    send(['U'] + ['B %x' % a for a in cands if a not in noisy])
    time.sleep(4)
    c, _ = hits_since(mark)
    print('round', rnd, 'noisy:', [hex(a) for a in c], flush=True)
    if not c: break
    noisy |= set(c)
mark = len(open(LOG).read().splitlines())
send(['U'] + ['B %x' % a for a in cands if a not in noisy])
subprocess.run([sys.executable, 'diag/twin/hp.py', who, 'press', btn, '8'], capture_output=True)
c, bts = hits_since(mark)
send(['U'])
for a, n in c.most_common():
    l = bts[a]
    print(hex(a), n, 'first at', l[:8], 'lr', re.search(r'lr=(\S+)', l).group(1), 'bt', re.search(r'bt=(\S+)', l).group(1)[:160])
print('noisy (per-frame):', [hex(a) for a in sorted(noisy)])
