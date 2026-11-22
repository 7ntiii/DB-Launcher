"""Where items can come from in a Dusk Battle, nearest to the player first.
python diag/twin/item_sources.py A                list world items (I#) and enemies that carry a drop lot (E#)
python diag/twin/item_sources.py A goto I3|E5 [nudge]   stand 1.5 m from it, facing it
python diag/twin/item_sources.py A force LOT|all  make drop lot LOT always drop (searches the regulation row in
                                                  memory, writes its u16 weights: slot0 0, slot1 1000)
python diag/twin/item_sources.py A unforce LOT|all  restore the stock weights
python diag/twin/item_sources.py A sacs          READ ONLY: Bloodsacs (crystal givers, NpcParam +0x4EE bit 3) nearest first
Recipe (diag/net/live_enumeration_notes.md section 2):
  World items: MapItemMan = *(main+0x5B3CDC0); lists at +0x18/+0x48/+0x78, next = node+0x10; node +0x30 id,
               +0x40 f32 xyz, +0x58 flags (0x4000 = taken)                            [V 0x15A3944..0x15A39DC]
  Enemy drops: chr (vtable main+0x572B108); row = [[[chr+0x20]+0xE8]+8] (NpcParam row in memory);
               lots at row+0x30, +0x34, +0x38 (ItemLotParam); data+0x1A2 bit 3 = already dropped,
               data+0x1A0..0x1A2 bit 13 = no drop                                        [V 0x174EBE0.., 0x15AD07C..]"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, MAPITEM_G, ENEMY_VT, dist, fmt3

# stock ItemLotParam rows used by NpcParam +0x30 / +0x38 [V regulation]: (item id, category, weight slot0, weight slot1)
LOTS = {
    20000000: ('goods 4260', 900, 100), 20000010: ('goods 4260', 0, 1000), 20100000: ('goods 4260', 850, 150),
    20500000: ('goods 4470', 850, 150), 29000000: ('goods 8000', 950, 50), 29100000: ('goods 8000', 850, 150),
    29100090: ('goods 8000', 0, 1000), 9990500: ('cat8 2000210', 1000, 0),
}
# first 0x50 bytes of each row (item ids, categories, weights) for the memory search [V regulation, each unique]
PATTERN = {
    20000000: '00000000a4100000' + '00' * 24 + '0000000001000000' + '00' * 24 + '8403640000000000' + '00' * 8,
    20000010: '00000000a4100000' + '00' * 24 + '0000000001000000' + '00' * 24 + '0000e80300000000' + '00' * 8,
    20100000: '00000000a4100000' + '00' * 24 + '0000000001000000' + '00' * 24 + '5203960000000000' + '00' * 8,
    20500000: '0000000076110000' + '00' * 24 + '0000000001000000' + '00' * 24 + '5203960000000000' + '00' * 8,
    29000000: '00000000401f0000' + '00' * 24 + '0000000001000000' + '00' * 24 + 'b603320000000000' + '00' * 8,
    29100000: '00000000401f0000' + '00' * 24 + '0000000001000000' + '00' * 24 + '5203960000000000' + '00' * 8,
    29100090: '00000000401f0000' + '00' * 24 + '0000000001000000' + '00' * 24 + '0000e80300000000' + '00' * 8,
}


def world_items(w):
    im = w.g(MAPITEM_G)
    if not im:
        w.null('MapItemMan *(main+0x5B3CDC0)')
        return []
    out = []
    for li, off in enumerate((0x18, 0x48, 0x78)):
        node, seen = w.q(im + off), 0
        while node and seen < 300:
            out.append({'kind': 'I', 'list': li, 'a': node, 'id': w.d(node + 0x30), 'pos': w.f3(node + 0x40),
                        'flags': w.d(node + 0x58)})
            node, seen = w.q(node + 0x10), seen + 1
    return out


def enemy_sources(w):
    out = []
    for si, j, c in w.all_chrs():
        if w.q(c) != w.base + ENEMY_VT:
            continue
        data = w.q(c + 0x20)
        holder = w.q(data + 0xE8) if data else None
        row = w.q(holder + 8) if holder else None
        if not row:
            continue
        lots = [w.i(row + o) for o in (0x30, 0x34, 0x38)]
        if all(x in (None, -1) for x in lots):
            continue
        fl = (w.h(data + 0x1A0) or 0) | ((w.b(data + 0x1A2) or 0) << 16)
        out.append({'kind': 'E', 'a': c, 'set': si, 'j': j, 'lots': lots, 'pos': w.chr_pos(c), 'hp': w.chr_hp(c),
                    'dropped': bool(fl & (8 << 16)), 'nodrop': bool(fl & (1 << 13)), 'handle': w.d(c + 8)})
    return out


def sacs(w, here, n=12):
    """READ ONLY: Bloodsacs (blood-crystal givers) nearest to the player. A Bloodsac is an enemy whose NpcParam row
    has +0x4EE bit 3 set (only rows 21300000 / 21300001 / 21309000 / 21309001, c2130; treasure_notes.md 'Who is a
    Bloodsac' [V]). Row = [[[chr+0x20]+0xE8]+8], as enemy_sources. The chr address printed is the absolute one
    fightfoe.py takes; 'dead' = [[chr+0x18]+0x30]+0x18 bit 0 (trespassers.chr_dead)."""
    out = []
    for si, j, c in w.all_chrs():
        if w.q(c) != w.base + ENEMY_VT:
            continue
        data = w.q(c + 0x20)
        holder = w.q(data + 0xE8) if data else None
        row = w.q(holder + 8) if holder else None
        flag = w.b(row + 0x4EE) if row else None
        if flag is None or not flag & 8:
            continue
        m1 = w.q(c + 0x18)
        m2 = w.q(m1 + 0x30) if m1 else None
        dead = (w.b(m2 + 0x18) or 0) & 1 if m2 else None
        pos = w.chr_pos(c)
        out.append((dist(here, pos) if pos else 1e9, c, w.d(c + 8), w.chr_hp(c), pos, dead))
    out.sort(key=lambda r: r[0])
    print('%s: player %s, Bloodsacs loaded %d (row +0x4EE bit 3)' % (w.who, fmt3(here), len(out)))
    for k, (d, c, h, hp, pos, dead) in enumerate(out[:n]):
        print('S%-3d chr 0x%x handle %08x hp %s %s d=%.1f%s' % (k, c, h or 0, hp, fmt3(pos) if pos else '?', d,
                                                            ' DEAD' if dead else ''))


def chance(lot):
    if lot not in LOTS:
        return '?'
    item, w0, w1 = LOTS[lot]
    return '%s %d%%' % (item, (w1 * 100) // max(1, w0 + w1)) if w1 else '%s 100%%' % item


def search(w, hexpat):
    hits, start = [], None
    for _ in range(4000):
        p = {'pattern': hexpat, 'max_hits': 64, 'budget_ms': 100}
        if start:
            p['start'] = start
        time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
        r = w.m.call('search_memory', p)
        hits += [int(h, 16) if isinstance(h, str) else int(h['address'], 16) for h in r.get('hits', [])]
        start = r.get('next')
        if not start:
            break
    return hits


STATE = 'diag/twin/item_force_%s.json'


def force(w, lots, on):
    """A forced row looks like the stock 100% rows, so the addresses are kept in item_force_<game>.json for unforce."""
    import json
    try:
        saved = json.load(open(STATE % w.who))
    except Exception:
        saved = {}
    for lot in lots:
        _, w0, w1 = LOTS[lot]
        if on:
            hits = search(w, PATTERN[lot])
            if len(hits) != 1:
                print(lot, 'found %d copies %s: not writing' % (len(hits), [hex(h) for h in hits[:6]]))
                continue
            a, new = hits[0], struct.pack('<2H', 0, 1000)
            saved[str(lot)] = a
        else:
            a, new = saved.pop(str(lot), None), struct.pack('<2H', w0, w1)
            if not a:
                print(lot, 'not forced by this tool (no address in %s)' % (STATE % w.who))
                continue
        old = w.rd(a + 0x40, 4)
        w.write(a + 0x40, new)
        print('%s lot %d row at %s: weights %s -> %s' % (w.who, lot, hex(a), old.hex() if old else '?', new.hex()))
    json.dump(saved, open(STATE % w.who, 'w'))


def main():
    w = W(sys.argv[1][0])
    verb = sys.argv[2] if len(sys.argv) > 2 else 'list'
    if verb in ('force', 'unforce'):
        which = [l for l in PATTERN if LOTS[l][2] < 1000] if sys.argv[3] == 'all' else [int(sys.argv[3])]
        if verb == 'unforce' and sys.argv[3] == 'all':
            which = list(PATTERN)
        force(w, which, verb == 'force')
        return
    _, _, here = w.me()
    if verb == 'sacs':
        sacs(w, here)
        w.report_missing()
        return
    items = sorted(world_items(w), key=lambda r: dist(here, r['pos']))
    enemies = sorted(enemy_sources(w), key=lambda r: dist(here, r['pos']))
    if verb == 'goto':
        tag = sys.argv[3]
        pool = items if tag[0] in 'Ii' else enemies
        r = pool[int(tag[1:])] if int(tag[1:]) < len(pool) else None
        if not r or not r['pos']:
            print('no position for', tag)
        else:
            w.goto_front(r['pos'], 1.5, 0.3, nudge='nudge' in sys.argv)
        w.report_missing()
        return
    gd = w.g(0x5B65C20)
    print('%s: player %s, world items %d, enemies with drop lots %d, offline flag +0xBDA=%s, drop gate *(main+0x5B57E90)=%s' % (
        w.who, fmt3(here), len(items), len(enemies), w.b(gd + 0xBDA) if gd else None, w.rel(w.g(0x5B57E90))))
    for k, r in enumerate(items[:30]):
        print('I%-3d list %d id %08x flags %08x %s d=%.1f%s' % (k, r['list'], r['id'] or 0, r['flags'] or 0, fmt3(r['pos']),
                                                             dist(here, r['pos']), ' TAKEN' if (r['flags'] or 0) & 0x4000 else ''))
    for k, r in enumerate(enemies[:30]):
        print('E%-3d chr %s handle %08x hp %s %s d=%.1f lots %s -> %s%s%s' % (
            k, w.rel(r['a']), r['handle'] or 0, r['hp'], fmt3(r['pos']), dist(here, r['pos']), r['lots'],
            ' / '.join(chance(x) for x in r['lots'] if x not in (None, -1)),
            ' DROPPED' if r['dropped'] else '', ' NODROP' if r['nodrop'] else ''))
    w.report_missing()


if __name__ == '__main__':
    main()
