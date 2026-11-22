"""Compare the enemies of both twin games: python diag/twin/cmp_enemies.py [REPEAT=1] [EVERY_S=5]
Per pass: enemy counts, handles only in one game, how many each game drives (and both / neither),
and for enemies loaded (flags 5) in both games: position gap and HP differences."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

ENEMY_VT = 0x572B108


def big(m, a, n):
    return b''.join(m.read(a + o, min(0x2000, n - o)) for o in range(0, n, 0x2000))


def snap(w):
    m = Mem(w)
    wcm = m.u64(m.base + 0x5B3CD88)
    sm = m.u64(wcm + 0x540)
    out = {}
    for si in range(min(m.u32(sm + 8), 16)):
        s = m.u64(sm + 0x10 + 8 * si)
        if not s:
            continue
        n = m.u32(s + 0x10)
        cs = m.u64(s + 8)
        if not n or n > 8192 or not cs:
            continue
        ent = big(m, m.u64(cs + 8), 0x38 * n)
        own = struct.unpack('<%dh' % n, big(m, m.u64(s + 0x18), 2 * n))
        for j in range(n):
            c, _, fl, _, _, ph, _ = struct.unpack_from('<7Q', ent, 0x38 * j)
            if not c or not ph:
                continue
            try:
                if m.u64(c) != m.base + ENEMY_VT:
                    continue
                mod = m.u64(m.u64(c + 0x2470) + 0x18)
                hp = struct.unpack('<i', m.read(mod + 0x290, 4))[0] if mod else -1
                out[(si, j)] = (struct.unpack('<3f', m.read(ph + 0x70, 12)), hp, own[j] >= 0, fl & 0xff)
            except Exception:
                pass
    return out


rep = int(sys.argv[1]) if len(sys.argv) > 1 else 1
every = float(sys.argv[2]) if len(sys.argv) > 2 else 5
for k in range(rep):
    a, b = snap('A'), snap('B')
    both = set(a) & set(b)
    dual = sum(1 for h in both if a[h][2] and b[h][2])
    none = sum(1 for h in both if not a[h][2] and not b[h][2])
    near = [h for h in both if a[h][3] == 5 and b[h][3] == 5]
    gaps = sorted((math.dist(a[h][0], b[h][0]), h) for h in near)
    hpd = [h for h in near if a[h][1] != b[h][1]]
    dead = (sum(1 for h in a if a[h][1] <= 0), sum(1 for h in b if b[h][1] <= 0))
    print(time.strftime('%H:%M:%S'), 'A %d B %d onlyA %d onlyB %d | A drives %d B drives %d both %d neither %d | loaded in both %d: gap>2m %d max %.1f, hp differs %d | dead A %d B %d' % (
        len(a), len(b), len(set(a) - set(b)), len(set(b) - set(a)), sum(v[2] for v in a.values()), sum(v[2] for v in b.values()),
        dual, none, len(near), sum(1 for g, _ in gaps if g > 2), gaps[-1][0] if gaps else 0, len(hpd), *dead), flush=True)
    for h in hpd[:4]:
        print('   hp', h, a[h][1], b[h][1], 'own', a[h][2], b[h][2])
    for g, h in gaps[-3:]:
        if g > 2:
            print('   gap %.1f' % g, h, 'own', a[h][2], b[h][2], tuple(round(x, 1) for x in a[h][0]), tuple(round(x, 1) for x in b[h][0]))
    if k + 1 < rep:
        time.sleep(every)
