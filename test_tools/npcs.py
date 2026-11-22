"""Enemy chrs of a twin game (vtable main+0x572B108, found by a heap search; a live one's chr+0x18
entry points back to it). Entry = {chr, 0, flags (0x500000005 near / 0x200000002 far), module, 0,
physics (+0x70 position), module}.
python diag/twin/npcs.py A [watch SECONDS]   count, the 12 nearest, and how many moved"""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

VT = 0x572B108


def f3(m, a):
    return struct.unpack('<3f', m.read(a, 12))


def player(m):
    return struct.unpack('<7Q', m.read(m.u64(m.u64(m.base + 0x5B3CD88) + 0x30), 56))


def find(m):
    pat = struct.pack('<Q', m.base + VT).hex()
    hits, start = [], None
    for _ in range(4000):
        p = {'pattern': pat, 'max_hits': 256, 'budget_ms': 100}
        if start:
            p['start'] = start
        time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
        r = m.call('search_memory', p)
        hits += [int(h, 16) if isinstance(h, str) else int(h['address'], 16) for h in r.get('hits', [])]
        start = r.get('next')
        if not start:
            break
    out = []
    for v in hits:
        try:
            ent = m.u64(v + 0x18)
            if not ent or m.u64(ent) != v:
                continue
            e = struct.unpack('<7Q', m.read(ent, 56))
            out.append({'chr': v, 'handle': m.u64(v + 8), 'flags': e[2], 'mod': e[3], 'phys': e[5],
                        'pos': f3(m, e[5] + 0x70) if e[5] else (0.0, 0.0, 0.0)})
        except Exception:
            pass
    return out


if __name__ == '__main__':
    m = Mem(sys.argv[1])
    me = f3(m, player(m)[5] + 0x70)
    rows = find(m)
    print('player', ['%.1f' % x for x in me], 'npcs', len(rows),
          'active', sum(1 for r in rows if r['flags'] & 0xff == 5))
    for r in sorted(rows, key=lambda r: math.dist(me, r['pos']))[:12]:
        print('%x handle %x flags %x pos (%.1f %.1f %.1f) dist %.0f' % (
            r['chr'], r['handle'], r['flags'], *r['pos'], math.dist(me, r['pos'])))
    if len(sys.argv) > 3 and sys.argv[2] == 'watch':
        first = {r['chr']: r['pos'] for r in rows if r['flags'] & 0xff == 5}
        time.sleep(float(sys.argv[3]))
        moved = 0
        for c, p in first.items():
            try:
                ent = struct.unpack('<7Q', m.read(m.u64(c + 0x18), 56))
                if math.dist(p, f3(m, ent[5] + 0x70)) > 0.05:
                    moved += 1
            except Exception:
                pass
        print('moved after %s s: %d of %d active' % (sys.argv[3], moved, len(first)))
