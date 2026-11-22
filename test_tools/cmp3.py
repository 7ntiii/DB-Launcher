"""Enemy ownership across all twin games (2 or 3): python diag/twin/cmp3.py GAMES [REPEAT=1] [EVERY_S=5]
Per pass: enemies per game, how many each drives, how many have 0 / 1 / 2+ owners, and the largest
position gap and HP difference between any game's copy and the owner's (loaded copies only)."""
import math
import sys
import time

sys.path.insert(0, 'diag/twin')
from cmp_lib import snap

games = sys.argv[1]
rep = int(sys.argv[2]) if len(sys.argv) > 2 else 1
every = float(sys.argv[3]) if len(sys.argv) > 3 else 5
for k in range(rep):
    s = {w: snap(w) for w in games}
    ids = set().union(*[set(v) for v in s.values()])
    owners = {h: [w for w in games if h in s[w] and s[w][h][2]] for h in ids}
    hist = {n: sum(1 for h in ids if len(owners[h]) == n) for n in (0, 1, 2, 3)}
    gap, hpd, loaded = 0.0, 0, 0
    for h in ids:
        if len(owners[h]) != 1:
            continue
        o = s[owners[h][0]][h]
        for w in games:
            if w != owners[h][0] and h in s[w] and s[w][h][3] == 5 and o[3] == 5:
                loaded += 1
                gap = max(gap, math.dist(o[0], s[w][h][0]))
                hpd += o[1] != s[w][h][1]
    print(time.strftime('%H:%M:%S'), 'count', {w: len(s[w]) for w in games}, 'drives', {w: sum(v[2] for v in s[w].values()) for w in games},
          'owners 0/1/2/3: %d/%d/%d/%d' % (hist[0], hist[1], hist[2], hist[3]), '| loaded copies %d, max gap %.1f m, hp differs %d' % (loaded, gap, hpd), flush=True)
    if k + 1 < rep:
        time.sleep(every)
