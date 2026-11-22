"""READ-ONLY: structural diff of the match-timer window between two games (timer_notes 7, timer_probe2 said "(d)
window visible" on both while only the host shows no timer). Nothing is written.
python diag/twin/timer_probe3.py AB [MAXPTR] [OUT]     (A = the game without the timer, B = the game with it)

Per game: H = the heap object vt main+0x57068B8 with +0x9D0 == D (as timer_probe2). It reads H (0x5830 B) and,
one level down, 0x200 B of every heap object H points to (layout +0x7C0, element +0x2658, children, text /
material blocks...), plus one more level (0x100 B) under the layout [H+0x7C0] and the element [H+0x2658]. Each game
is read TWICE (1.2 s apart): a field that changes inside one game is "volatile" (clock, counters) and dropped.
Field compare, per 4 bytes at the same path ("H+0x7c0>+0x1dc" = offset 0x1DC in the object H+0x7C0 points to):
  - both heap pointers -> only null vs non-null counts; main-image pointers (vtables) compare as main+offset
    (a different vtable = a different element type / state object);
  - else u32 values; floats are printed too (alpha / scale / position / colour live there).
Output: each differing field "path  A=u32 (f32)  B=u32 (f32)", the floats in [0,1] (alpha-like) first, then the
rest, at most 300 lines; with OUT the full list goes to that file. The lines name what A's window has that B's
lacks (alpha 0, scale 0, a child null, a different vtable...)."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

FE, HUD_DATA, H_VT = 0x5B76C30, 0x49BB0, 0x57068B8
H_SIZE, L1, L2 = 0x5830, 0x200, 0x100
MAIN_SPAN = 0x8000000
DEEP = (0x7C0, 0x2658)   # layout, element: one more level under these


class R:
    def __init__(self, who):
        self.m = Mem(who)
        self.base = self.m.base
        self.n = 0

    def rd(self, a, n):
        if not a:
            return None
        try:
            self.n += 1
            return self.m.read(a, n)
        except Exception:
            return None

    def q(self, a):
        b = self.rd(a, 8)
        return struct.unpack('<Q', b)[0] if b else 0

    def kind(self, v):
        if self.base <= v < self.base + MAIN_SPAN and v % 4 == 0:
            return 'main'
        if 0x1000000 <= v < (1 << 40) and v % 8 == 0:
            return 'heap'
        return None


def find_h(r):
    fe = r.q(r.base + FE)
    d = fe + HUD_DATA if fe else 0
    pat = struct.pack('<Q', r.base + H_VT).hex()
    hits, start = [], None
    for _ in range(4000):
        p = {'pattern': pat, 'max_hits': 64, 'budget_ms': 100}
        if start:
            p['start'] = start
        time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
        res = r.m.call('search_memory', p)
        hits += [int(h, 16) if isinstance(h, str) else int(h['address'], 16) for h in res.get('hits', [])]
        start = res.get('next')
        if not start:
            break
    for h in sorted(set(hits)):
        if h % 8 == 0 and d and r.q(h + 0x9D0) == d:
            return h
    return 0


def fields(r, blob, path, out, ptrs):
    """4-byte fields of blob into out[path+off]; qword heap pointers into ptrs[(path, off)]"""
    skip = False
    for off in range(0, len(blob) - 3, 4):
        if skip:            # high half of a pointer taken as one field
            skip = False
            continue
        u, = struct.unpack_from('<I', blob, off)
        if off % 8 == 0 and off + 8 <= len(blob):
            v, = struct.unpack_from('<Q', blob, off)
            k = r.kind(v)
            if k == 'heap':
                out['%s+%#x' % (path, off)] = 'ptr'
                ptrs[(path, off)] = v
                skip = True
                continue
            if k == 'main':
                out['%s+%#x' % (path, off)] = 'main+%#x' % (v - r.base)
                skip = True
                continue
        out['%s+%#x' % (path, off)] = u


def snapshot(r, h, maxptr):
    out = {}
    blob = r.rd(h, H_SIZE)
    if not blob:
        return out
    ptrs = {}
    fields(r, blob, 'H', out, ptrs)
    lvl1 = sorted(ptrs.items(), key=lambda kv: (kv[0][1] not in DEEP, kv[0][1]))[:maxptr]
    for (path, off), v in lvl1:
        b = r.rd(v, L1)
        key = '%s+%#x>' % (path, off)
        if not b:
            out[key] = 'unreadable'
            continue
        p2 = {}
        fields(r, b, key, out, p2)
        if off in DEEP:
            for (path2, off2), v2 in list(p2.items())[:48]:
                b2 = r.rd(v2, L2)
                if b2:
                    fields(r, b2, '%s+%#x>' % (path2, off2), out, {})
    return out


def f32(u):
    return struct.unpack('<f', struct.pack('<I', u))[0]


def show(v):
    if isinstance(v, int):
        f = f32(v)
        if v and abs(f) < 1e7 and (abs(f) > 1e-6):
            return '%#x (%g)' % (v, f)
        return '%#x' % v
    return str(v)


def same_game(args):
    """python diag/twin/timer_probe3.py A snap NAME      save game A's H tree to diag/twin/timer3_NAME.json
    python diag/twin/timer_probe3.py cmp NAME1 NAME2   diff two snapshots of the SAME game (no cross-game heap noise)"""
    import json
    if args[0] == 'cmp':
        a, b = (json.load(open('diag/twin/timer3_%s.json' % n)) for n in args[1:3])
        vol = set(a['vol']) | set(b['vol'])
        keys = sorted(set(a['f']) | set(b['f']), key=lambda k: (k.count('>'), k))
        n = 0
        for k in keys:
            x, y = a['f'].get(k, 'missing'), b['f'].get(k, 'missing')
            if k in vol or x == y:
                continue
            n += 1
            if n <= 400:
                print('%-34s %s=%-24s %s=%s' % (k, args[1], show(x), args[2], show(y)))
        print('%d stable fields differ between %s and %s (%d volatile dropped)' % (n, args[1], args[2], len(vol)))
        return 0
    r = R(args[0])
    h = find_h(r)
    if not h:
        print('%s: H not found' % args[0])
        return 1
    a = snapshot(r, h, 400)
    time.sleep(1.2)
    b = snapshot(r, h, 400)
    vol = sorted(k for k in a if a.get(k) != b.get(k))
    json.dump({'h': h, 'f': b, 'vol': vol}, open('diag/twin/timer3_%s.json' % args[2], 'w'))
    print('%s: H %#x saved as timer3_%s.json (%d fields, %d volatile)' % (args[0], h, args[2], len(b), len(vol)))
    return 0


def main():
    args = sys.argv[1:]
    if len(args) >= 3 and (args[0] == 'cmp' or args[1] == 'snap'):
        return same_game(args)
    if not args or len(args[0]) != 2 or any(c not in 'ABCD' for c in args[0]):
        print(__doc__)
        return 2
    maxptr = int(args[1]) if len(args) > 1 else 400
    outf = args[2] if len(args) > 2 else None
    snaps = {}
    for who in args[0]:
        r = R(who)
        t0 = time.time()
        h = find_h(r)
        if not h:
            print('%s: H not found' % who)
            return 1
        a = snapshot(r, h, maxptr)
        time.sleep(1.2)
        b = snapshot(r, h, maxptr)
        vol = {k for k in a if a.get(k) != b.get(k)}
        snaps[who] = (b, vol)
        print('%s: H %#x, %d fields, %d volatile, %d reads, %.1f s' % (who, h, len(b), len(vol), r.n,
                                                                     time.time() - t0))
    (wa, (sa, va)), (wb, (sb, vb)) = snaps.items()
    vol = va | vb
    keys = sorted(set(sa) | set(sb), key=lambda k: (k.count('>'), k))
    diffs = []
    for k in keys:
        if k in vol:
            continue
        x, y = sa.get(k, 'missing'), sb.get(k, 'missing')
        if x == y:
            continue
        alpha = any(isinstance(z, int) and 1e-6 <= f32(z) <= 1.0 for z in (x, y))
        diffs.append((0 if alpha else 1, k, '%-34s %s=%-24s %s=%s' % (k, wa, show(x), wb, show(y))))
    diffs.sort(key=lambda d: (d[0], d[1].count('>'), d[1]))
    print('%d stable fields differ (%d volatile dropped); float-in-[0,1] fields first' % (len(diffs), len(vol)))
    for _, _, line in diffs[:300]:
        print(line)
    if outf:
        with open(outf, 'w') as f:
            for _, _, line in diffs:
                f.write(line + '\n')
        print('full list: %s' % outf)
    return 0


if __name__ == '__main__':
    sys.exit(main())
