"""Read-only: per log pair, the skew of 'prepare second: step-7 answer flag set' (= storm object start) and of
'match phase 4' (round start) between two games of one match. Lines are matched by order within the file."""
import glob
import os
import re
import sys

ROOT = r'<WORKSPACE>\diag'


def secs(t):
    h, m, s = map(int, t.split(':'))
    return h * 3600 + m * 60 + s


def events(path):
    prep, ph4, env = [], [], []
    try:
        for line in open(path, encoding='utf-8', errors='replace'):
            t = line[:8]
            if not re.match(r'\d\d:\d\d:\d\d', t):
                continue
            if 'prepare second: step-7 answer flag set' in line and ph4:   # round 2+ (the storm's rounds)
                prep.append(secs(t))
            if re.search(r'match phase 4$', line.rstrip()):
                ph4.append(secs(t))
            elif 'environment event 1140' in line:
                env.append(secs(t))
    except OSError:
        pass
    return prep, ph4, env


worst = {'prep': (0, ''), 'ph4': (0, '')}
pairs = 0
allp = []
for a in glob.glob(os.path.join(ROOT, '**', 'A*dusk_lan*.txt'), recursive=True):
    d, n = os.path.split(a)
    b = os.path.join(d, 'B' + n[1:])
    if not os.path.exists(b):
        continue
    pa, qa, ea = events(a)
    pb, qb, eb = events(b)
    if not pa or not pb:
        continue
    off = qa[0] - qb[0] if qa and qb else 0   # clock offset guess (13 h laptop etc.): align first round start
    if abs(off) > 600:
        pa = [x - off for x in pa]; qa = [x - off for x in qa]
    pairs += 1
    for key, xa, xb in (('prep', pa, pb), ('ph4', qa, qb)):
        for x in xa:
            if not xb:
                break
            lag = min(abs(x - y) for y in xb)   # nearest: the same round on the other game
            if lag > 40:
                continue                         # no counterpart (the other game left / another match)
            if key == 'prep':
                allp.append(lag)
            if lag > worst[key][0]:
                worst[key] = (lag, os.path.relpath(a, ROOT))
print('pairs', pairs)
print('all prepare skews', sorted(allp))
print('worst prepare-second skew %d s (%s)' % worst['prep'])
print('worst round-start (phase 4) skew %d s (%s)' % worst['ph4'])
