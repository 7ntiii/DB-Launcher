"""Nearest map objects of any kind to the local player: geometry/asset instances (every loaded block),
chrs (every chr set), world items, asset-access entries (levers).
python diag/twin/nearest_objects.py A [N=30] [kind=geom|chr|item|all] [radius=R] [eid=ins+0xNN|info+0xNN]
python diag/twin/nearest_objects.py A probe          guess which offset of the geom ins / info holds the entity id
python diag/twin/nearest_objects.py A dump ADDR [N]  hex dump (ADDR absolute hex or main+0x...)
python diag/twin/nearest_objects.py A goto ADDR [nudge]   stand 1.5 m in front of the object at ADDR (geom or chr)
Columns: kind, address, class (vtable as main+offset, or a known name), handle?, entity id?, position, distance.
  geom: ins+0x10 info, ins+0x110 position [V]; ins+8 printed as 'h?' (the handle, if it is 0x6BBIIIII) [I];
        'acc' marks a geom used by an asset-access entry (lever / gate), 'off' = [[ins+0x10]+0x20]+0xD == 1 [V]
  chr:  [[chr+0x20]+0x78] low 16 bits = set<<12|index id [V], position [[chr+0x2470]+0xE8]+0x70 [V]"""
import struct
import sys
from collections import Counter

sys.path.insert(0, 'diag/twin')
from world_lib import W, KNOWN_VT, dist, fmt3


def cls(w, vt):
    if not vt:
        return 'vt null'
    off = vt - w.base
    return KNOWN_VT.get(off) or ('main+0x%X' % off if 0 <= off < 0x7000000 else '0x%x' % vt)


def eid_of(w, ins, spec):
    if not spec:
        return None
    where, off = spec.split('+')
    a = ins if where == 'ins' else w.q(ins + 0x10)
    return w.i(a + int(off, 16)) if a else None


def geoms(w, spec):
    import levers
    acc = set()
    for r in levers.entries(w):
        for g in (r['geom'], r['geom2']):
            if g:
                acc.add(g)
    out = []
    for blockid, k, ins in w.all_geoms():
        b = w.rd(ins, 0x120)
        if not b:
            continue
        vt, h = struct.unpack_from('<QI', b, 0)
        info = struct.unpack_from('<Q', b, 0x10)[0]
        z = w.q(info + 0x20) if info else None
        off = bool(z) and w.b(z + 0xD) == 1
        out.append({'kind': 'geom', 'a': ins, 'cls': cls(w, vt), 'h': h, 'eid': eid_of(w, ins, spec),
                    'pos': struct.unpack_from('<3f', b, 0x110), 'tag': ('acc ' if ins in acc else '') + ('off' if off else ''),
                    'extra': 'blk %08x #%d' % (blockid or 0, k)})
    return out


def chrs(w):
    out = []
    seen = set()
    for si, j, c in w.all_chrs():
        seen.add(c)
        data = w.q(c + 0x20)
        out.append({'kind': 'chr', 'a': c, 'cls': cls(w, w.q(c)), 'h': w.d(c + 8),
                    'eid': ((w.d(data + 0x78) or 0) & 0xFFFF) if data else None, 'pos': w.chr_pos(c),
                    'tag': 'hp %s' % w.chr_hp(c), 'extra': 'set %d #%d' % (si, j)})
    for k, e in enumerate(w.players()):
        if e[0] not in seen:
            out.append({'kind': 'player', 'a': e[0], 'cls': cls(w, w.q(e[0])), 'h': w.d(e[0] + 8), 'eid': None,
                        'pos': w.f3(e[5] + 0x70) if e[5] else None, 'tag': '', 'extra': 'entry %d' % k})
    return out


def items(w):
    import item_sources
    return [{'kind': 'item', 'a': r['a'], 'cls': 'item', 'h': r['id'], 'eid': None, 'pos': r['pos'],
             'tag': 'flags %x' % (r['flags'] or 0), 'extra': 'list %d' % r['list']} for r in item_sources.world_items(w)]


def addr(w, s):
    return w.base + int(s.split('+')[1], 16) if s.startswith('main+') else int(s, 16)


def probe(w):
    gs = w.all_geoms(600)
    print('%d geoms sampled' % len(gs))
    for where in ('ins', 'info'):
        hits, vals = Counter(), {}
        for _, _, ins in gs:
            a = ins if where == 'ins' else w.q(ins + 0x10)
            b = w.rd(a, 0x400) if a else None
            if not b:
                continue
            for o in range(0, 0x400, 4):
                v = struct.unpack_from('<i', b, o)[0]
                if 1000000 <= v < 2000000000:
                    hi = struct.unpack_from('<I', b, o + 4)[0] if o + 4 < 0x400 else 0
                    if o % 8 == 0 and 0x10 <= hi <= 0xFFFFFF:   # low half of a pointer
                        continue
                    hits[o] += 1
                    vals.setdefault(o, set()).add(v)
        best = sorted(hits.items(), key=lambda x: -x[1])[:8]
        print(where, ['+0x%X: %d hits, %d distinct, e.g. %s' % (o, n, len(vals[o]), sorted(vals[o])[:4]) for o, n in best])
    print('use the best offset as eid=ins+0xNN or eid=info+0xNN; -1 is also normal for objects without an entity id')


def main():
    w = W(sys.argv[1][0])
    args = sys.argv[2:]
    if args and args[0] == 'probe':
        probe(w)
        return
    if args and args[0] == 'dump':
        a, n = addr(w, args[1]), int(args[2], 0) if len(args) > 2 else 0x120
        b = w.rd(a, n)
        for o in range(0, n, 16):
            print('%x +%03x: %s' % (a + o, o, b[o:o + 16].hex(' ') if b else 'unreadable'))
        return
    if args and args[0] == 'goto':
        a = addr(w, args[1])
        p = w.chr_pos(a) if w.q(a + 0x2470) else None
        p = p or w.geom_pos(a)
        if p:
            w.goto_front(p, 1.5, 0.3, nudge='nudge' in args)
        else:
            print('no position for', hex(a))
        return
    n = int(next((x for x in args if x.isdigit()), 30))
    kind = next((x.split('=')[1] for x in args if x.startswith('kind=')), 'all')
    radius = float(next((x.split('=')[1] for x in args if x.startswith('radius=')), 1e9))
    spec = next((x.split('=')[1] for x in args if x.startswith('eid=')), None)
    _, _, here = w.me()
    rows = []
    if kind in ('geom', 'all'):
        rows += geoms(w, spec)
    if kind in ('chr', 'all'):
        rows += chrs(w)
    if kind in ('item', 'all'):
        rows += items(w)
    rows = [r for r in rows if dist(here, r['pos']) <= radius]
    rows.sort(key=lambda r: dist(here, r['pos']))
    print('%s: player %s, %d objects (kind %s)' % (w.who, fmt3(here), len(rows), kind))
    for r in rows[:n]:
        print('%-6s %s %-22s h? %08x eid %-10s %s d=%6.1f %s %s' % (
            r['kind'], w.rel(r['a']), r['cls'], r['h'] or 0, r['eid'], fmt3(r['pos']), dist(here, r['pos']), r['tag'], r['extra']))
    w.report_missing()


if __name__ == '__main__':
    main()
