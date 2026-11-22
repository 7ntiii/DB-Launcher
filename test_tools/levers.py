"""Levers / gates / elevators of the asset-access system (message 0x97), nearest to game A's player first.
python diag/twin/levers.py A                     list (read only)
python diag/twin/levers.py A dump N              hex dump of entry N, its trigger geom and the geom info
python diag/twin/levers.py A goto N [press] [nudge]   stand 1.2 m in front of entry N's trigger, facing it;
                                                  'press' then presses A (the action button), 'nudge' taps the stick
python diag/twin/levers.py AB                    both games side by side (holder must match)
Recipe (diag/net/live_enumeration_notes.md section 1):
  mgr = *(main+0x5B59B60); entries = u64 vector [mgr+8, mgr+0x10)            [V 0xD68680, 0xD69AE8]
  entry +8 index, +0xC AssetAccessEventParam id, +0x14 second geom handle, +0x18 geom handle (action target),
        +0x40 sequence object, +0x68 mediated byte                             [V 0xD66F08..0xD6722C]
  geom = handle -> CSWorldGeomIns (0xFEC6E0, copied in world_lib); position geom+0x110      [V]
  info = [geom+0x10]: +0x460 holder (player no, -1 free), +0x468 per-slot busy mask, +0x470 busy byte [V]"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, AAE_G, dist, fmt3

# AssetAccessEventParam row -> ActionButtonParam id (row +0) [V regulation]; button rows: radius, angle, height, bottom [V]
AAE_BUTTON = {9000: 8340, 9001: 8320, 9002: 8330, 9005: 8332, 9006: 8332, 9007: 8334}
BUTTON = {8332: (2.0, 90, 6.0, -3.0), 8333: (2.0, 90, 6.0, -3.0), 8334: (2.0, 90, 6.0, -3.0)}


def entries(w):
    mgr = w.g(AAE_G)
    if not mgr:
        w.null('CSAssetAccessEventMan *(main+0x5B59B60) (no map loaded?)')
        return []
    beg, end = w.q(mgr + 8), w.q(mgr + 0x10)
    if not beg or not end or end < beg or end - beg > 8 * 4096:
        w.null('entry vector mgr+8/+0x10')
        return []
    raw = w.big(beg, end - beg) or b''
    out = []
    for k in range(len(raw) // 8):
        e = struct.unpack_from('<Q', raw, 8 * k)[0]
        if not e:
            continue
        r = {'n': k, 'e': e, 'vt': w.q(e), 'index': w.d(e + 8), 'param': w.d(e + 0xC),
             'h2': w.d(e + 0x14), 'h': w.d(e + 0x18), 'seq': w.q(e + 0x40), 'mediated': w.b(e + 0x68)}
        g = w.geom_from_handle(r['h'])
        g2 = w.geom_from_handle(r['h2'])
        info = w.q(g + 0x10) if g else None
        r.update(geom=g, geom2=g2, info=info, pos=w.geom_pos(g), pos2=w.geom_pos(g2),
                 holder=w.i(info + 0x460) if info else None, mask=w.q(info + 0x468) if info else None,
                 busy=w.b(info + 0x470) if info else None,
                 enabled=(w.b((w.q(info + 0x20) or 0) + 0xD) != 1) if info and w.q(info + 0x20) else None)
        out.append(r)
    return out


def show(w, rows, here):
    for r in sorted(rows, key=lambda r: dist(here, r['pos'])):
        btn = AAE_BUTTON.get(r['param'])
        print('#%-3d idx %-3s param %-5s btn %-5s %s trig %s d=%5.1f  target %s  holder %s mask %s busy %s on %s geom %s' % (
            r['n'], r['index'], r['param'], btn, 'MED' if r['mediated'] else 'plain',
            fmt3(r['pos']), dist(here, r['pos']), fmt3(r['pos2']), r['holder'],
            None if r['mask'] is None else '%x' % (r['mask'] & 0xFFF), r['busy'], r['enabled'], w.rel(r['geom'])))


def main():
    games = sys.argv[1]
    verb = sys.argv[2] if len(sys.argv) > 2 else 'list'
    if verb == 'list' and len(games) > 1:
        rows = {}
        for g in games:
            w = W(g)
            rows[g] = {r['n']: r for r in entries(w)}
            w.report_missing()
        print('entry  ' + '  '.join('%s: holder busy pos' % g for g in games))
        for n in sorted(set().union(*[set(v) for v in rows.values()])):
            cells = []
            for g in games:
                r = rows[g].get(n)
                cells.append('%s: %4s %4s %s' % (g, r['holder'], r['busy'], fmt3(r['pos'])) if r else '%s: -' % g)
            print('#%-4d %s' % (n, '   '.join(cells)))
        return
    w = W(games[0])
    _, _, here = w.me()
    rows = entries(w)
    print('%s: %d asset-access entries, player %s' % (w.who, len(rows), fmt3(here)))
    if verb == 'list':
        show(w, rows, here)
    elif verb == 'dump':
        r = next((r for r in rows if r['n'] == int(sys.argv[3])), None)
        if not r:
            print('no entry', sys.argv[3])
        else:
            for name, a, n in (('entry', r['e'], 0x80), ('geom', r['geom'], 0x40), ('info+0x440', (r['info'] or 0) + 0x440, 0x40)):
                b = w.rd(a, n) if a else None
                print(name, w.rel(a), b.hex(' ') if b else 'null')
    elif verb == 'goto':
        r = next((r for r in rows if r['n'] == int(sys.argv[3])), None)
        if not r or not r['pos']:
            print('entry %s has no resolvable trigger geom' % sys.argv[3])
        else:
            w.goto_front(r['pos'], 1.2, 0.2, nudge='nudge' in sys.argv)
            if 'press' in sys.argv:
                import time
                time.sleep(0.4)
                w.press('A')
                time.sleep(1.5)
                info = r['info']
                print('after A: holder %s busy %s' % (w.i(info + 0x460) if info else None, w.b(info + 0x470) if info else None))
    w.report_missing()


if __name__ == '__main__':
    main()
