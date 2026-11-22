"""READ-ONLY SFX instance list (fire hunt, 2026-11-20). Writes nothing.

  python diag/twin/sfx_list.py A                 instances per effect id (and per wrapper class)
  python diag/twin/sfx_list.py A own [R=15]      ... plus every instance within R m of the game's own player
  python diag/twin/sfx_list.py A X Y Z [R=15]    ... plus every instance within R m of a point
  python diag/twin/sfx_list.py A ... --twice     sample again 5 s later and print what appeared / went

Facts [V static + live read on rig A, alpha 4]:
- CSSfx singleton = [main+0x5B4D3E0] (getter 0x1580CBC), vptr main+0x576CD10.
- FD4 SFX wrappers are heap objects found by vptr (debug server search_memory, as vtcount.py):
  CSFD4SingleSfxIns vptr main+0x576CBD0 (size 0xD8; runtime class [main+0x5BAF6A8], getter 0x1D42870 at vt+0x18),
  CSFD4SfxIns       vptr main+0x576CA60 (runtime class [main+0x5BAF568], getter 0x1D41014 at vt+0x18),
  CSFD4MultiSfxIns  vptr main+0x576C920 (runtime class [main+0x5BAF410]).
- wrapper +0x08 u32 kind, +0x0C u32 effect id (e.g. 810165), +0x18 the framework instance; that instance holds an
  AABB min at +0x50 and max at +0x60 (vec4, w = 1) in world space: its centre is the position used here.
Search cost: about 0.1 s of game-thread search per 0.4 s, as vtcount.py."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

CLASSES = (('Single', 0x576CBD0), ('SfxIns', 0x576CA60), ('Multi', 0x576C920))
SET = 0x5B3CD88


def search(m, vt):
    pattern = struct.pack('<Q', m.base + vt).hex()
    hits, start = [], None
    for _ in range(4000):
        params = {'pattern': pattern, 'max_hits': 256, 'budget_ms': 100}
        if start:
            params['start'] = start
        time.sleep(0.4)
        r = m.call('search_memory', params)
        hits += [int(h, 16) if isinstance(h, str) else int(h.get('address'), 16) for h in r.get('hits', [])]
        start = r.get('next')
        if (r.get('complete') and not start) or not start:
            break
    return [h for h in hits if h % 8 == 0]


def finite(v):
    return all(math.isfinite(x) and abs(x) < 1e6 for x in v)


def sample(m):
    out = []
    for name, vt in CLASSES:
        for obj in search(m, vt):
            try:
                b = m.read(obj, 0x20)
                kind, eid = struct.unpack_from('<II', b, 8)
                ins = struct.unpack_from('<Q', b, 0x18)[0]
                pos = None
                if ins > 0x1000000000:
                    lo = struct.unpack('<4f', m.read(ins + 0x50, 16))
                    hi = struct.unpack('<4f', m.read(ins + 0x60, 16))
                    if finite(lo[:3]) and finite(hi[:3]) and lo[3] == 1.0 and hi[3] == 1.0:
                        pos = tuple((lo[k] + hi[k]) / 2 for k in range(3))
                out.append((name, obj, kind, eid, ins, pos))
            except Exception:
                continue
    return out


def own_pos(m):
    e = m.u64(m.u64(m.base + SET) + 0x30)
    phys = m.u64(e + 0x28)
    return struct.unpack('<3f', m.read(phys + 0x70, 12))


def show(rows, point, radius):
    per = {}
    for name, _, _, eid, _, _ in rows:
        per[(name, eid)] = per.get((name, eid), 0) + 1
    print('%s %d instances, %d ids' % (time.strftime('%T'), len(rows), len(per)))
    for (name, eid), n in sorted(per.items(), key=lambda kv: -kv[1]):
        print('  %-6s id %9d x%d' % (name, eid, n))
    if point:
        near = []
        for name, obj, kind, eid, ins, pos in rows:
            if pos:
                d = math.dist(pos, point)
                if d <= radius:
                    near.append((d, name, eid, kind, obj, pos))
        print('  within %.0f m of (%.1f, %.1f, %.1f): %d' % ((radius,) + tuple(point) + (len(near),)))
        for d, name, eid, kind, obj, pos in sorted(near):
            print('    %5.1f m %-6s id %9d kind %d obj %x at (%.1f, %.1f, %.1f)' % ((d, name, eid, kind, obj) + pos))


def main():
    args = [a for a in sys.argv[1:] if a != '--twice']
    twice = '--twice' in sys.argv
    m = Mem(args[0])
    point, radius = None, 15.0
    if len(args) > 1 and args[1] == 'own':
        point = own_pos(m)
        radius = float(args[2]) if len(args) > 2 else radius
    elif len(args) >= 4:
        point = tuple(float(x) for x in args[1:4])
        radius = float(args[4]) if len(args) > 4 else radius
    first = sample(m)
    show(first, point, radius)
    if twice:
        time.sleep(5)
        second = sample(m)
        show(second, point, radius)
        a = {r[1]: r for r in first}
        b = {r[1]: r for r in second}
        for o in b.keys() - a.keys():
            print('  NEW  %-6s id %9d obj %x pos %s' % (b[o][0], b[o][3], o, b[o][5]))
        for o in a.keys() - b.keys():
            print('  GONE %-6s id %9d obj %x pos %s' % (a[o][0], a[o][3], o, a[o][5]))


if __name__ == '__main__':
    main()
