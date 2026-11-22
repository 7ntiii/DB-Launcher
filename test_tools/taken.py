"""Taken state of the shared action-menu assets, per game, side by side. READ ONLY (nothing is written).
python diag/twin/taken.py GAMES [all]      e.g.  taken.py AB   or   taken.py ABC all
  GAMES  A, B, C ... (each game is read in turn, then one comparison table)
  all    also list objects with no state on any game (default: only rows where some game has state)

What dusk_lan.cpp TakenShare (side-channel type 12, diag/net/taken_share_notes.md) shares [V flames.py, kinstate.py]:
  ins = every geom of every loaded block (world_lib.all_geoms), info = [ins+0x10]
  asset id = s32 [info+0x18] % 10000000, h = u32 ins+8 (0x74 handle: identity of the object on every game)
  bits = info+0x468 low 12 bits (player SLOTS of this game: slot = u8 pgd+0x104, shown also as player numbers)
  used = u8 info+0x470, holder = s32 info+0x460 (-1 free; player numbers are 1..)
Kinds: 99280 flame, 99281 flameL (pay once), 99282 flameL* (pay once, not reset at the phase change),
99290/99291/99292 kin (big circle, holder), 99295 small (single use).
After a take every game should show the same row (used / holder equal, the taker's player in 'players')."""
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W

KIND = {99280: 'flame', 99281: 'flameL', 99282: 'flameL*', 99290: 'kin', 99291: 'kin', 99292: 'kin',
        99295: 'small'}
GEOM_LIMIT = 200000


def slot_map(w):
    """slot -> player no on this game: local pgd (+0x28 first, then +0x20) and the pool [NET+0x30] + i*0x47F0"""
    net = w.g(0x5B57EB8)
    if not net:
        w.null('net player table *(main+0x5B57EB8)')
        return {}
    pgds = [w.q(net + 0x28), w.q(net + 0x20)]
    pool = w.q(net + 0x30)
    if pool:
        pgds += [pool + i * 0x47F0 for i in range(12)]
    out = {}
    for p in pgds:
        if not p:
            continue
        no, slot = w.i(p + 0xD0), w.b(p + 0x104)
        if no is None or slot is None or not 1 <= no <= 32 or slot >= 12 or slot in out:
            continue
        out[slot] = no
    return out


def players_of(bits, slots):
    return sorted(slots[s] for s in range(12) if bits >> s & 1 and s in slots)


def read_game(g):
    w = W(g)
    slots = slot_map(w)
    rows = {}
    for blockid, k, ins in w.all_geoms(limit=GEOM_LIMIT):
        info = w.q(ins + 0x10)
        raw = w.i(info + 0x18) if info else None
        if raw is None or raw <= 0:
            continue
        aid = raw % 10000000
        if aid not in KIND:
            continue
        h = w.d(ins + 8)
        if not h or h == 0xFFFFFFFF or (aid, h) in rows:
            continue
        bits = (w.q(info + 0x468) or 0) & 0xFFF
        rows[(aid, h)] = {'bits': bits, 'players': players_of(bits, slots), 'used': w.b(info + 0x470),
                          'hold': w.i(info + 0x460), 'ins': ins}
    w.report_missing()
    return slots, rows


def has_state(r):
    return r and (r['bits'] or r['used'] or (r['hold'] is not None and r['hold'] >= 1))


def cell(r):
    if r is None:
        return '%-26s' % '(not loaded)'
    return '%-26s' % ('bits=%03x p=%s used=%s hold=%s' % (
        r['bits'], ','.join(map(str, r['players'])) or '-', r['used'], r['hold']))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    games, show_all = args[0], 'all' in args[1:]
    data = {}
    for g in games:
        slots, rows = read_game(g)
        data[g] = rows
        print('%s slot -> player %s; %d shared objects, %d with state' % (
            g, slots, len(rows), sum(1 for r in rows.values() if has_state(r))))
    keys = sorted(set(k for rows in data.values() for k in rows))
    print('%-8s %6s %-8s  %s' % ('kind', 'asset', 'h', '  '.join('%-26s' % ('game ' + g) for g in games)))
    diff = 0
    for aid, h in keys:
        rs = [data[g].get((aid, h)) for g in games]
        if not show_all and not any(has_state(r) for r in rs):
            continue
        seen = [(tuple(r['players']), r['used'], r['hold']) for r in rs if r is not None]
        mark = '' if len(set(seen)) <= 1 else '  DIFF'
        diff += bool(mark)
        print('%-8s %6d %08x  %s%s' % (KIND[aid], aid, h, '  '.join(cell(r) for r in rs), mark))
    print('rows that differ between games: %d' % diff)


if __name__ == '__main__':
    main()
