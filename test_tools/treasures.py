"""Map treasures and blood crystals per game (READ-ONLY: never writes game memory).
python diag/twin/treasures.py [GAMES=AB] [list] [watch SECONDS]

Per game:
  - role byte main+0x492AFD8 (0 host / offline, 1 guest), offline byte, patch words TREASURE_HOST / CRYSTAL_LOCAL /
    STARFRAG_V2 gate (ON / off / other);
  - MapItemMan *(main+0x5B3CDC0) lists +0x18/+0x48/+0x78: world items, asset-linked ones (node +0x58 bit 3, asset
    handle +0x3C) grouped by the linked asset id: 105210 loot points (195 MSB treasures), 99211 Star Fragment sites
    (12), 99212 (10), other; plus a crc of the sorted id list so the games can be compared;
  - blood crystal state of the local player: skill-enhancement offers pending (item mgr *(main+0x5B57E90) + 0x21D8
    + slot*0x20, u64 count +0x18) and the last kill-reward path words.
  list         also print every asset-linked item (id, asset id, position, shown bits)
  watch S      repeat every 2 s for S seconds, print a game only when its numbers change
Expected: treasure_notes.md section 4 (live test)."""
import os
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from world_lib import W, fmt3  # noqa: E402

MAPITEM_G, ITEM_MGR, GDM, OFFLINE, ROLE = 0x5B3CDC0, 0x5B57E90, 0x5B57EB8, 0x5B65C20, 0x492AFD8
KINDS = {105210: 'loot', 99211: 'starsite', 99212: 'aeg212'}
WORDS = [(0xC2D04C, {'E8E701B0': 'ON', 'C8790290': 'off'}, 'TREASURE_HOST'),
         (0xC2D058, {'C8060034': 'stock cbz'}, '0xC2D058 (STARFRAG_V2 if not stock)'),
         (0x15B0528, {'1F2003D5': 'CRYSTAL_LOCAL (withdrawn)', '71C5FF17': 'CRYSTAL_GUEST ON', '28010034': 'off'},
          'crystal gate')]

args = sys.argv[1:]
games = args[0] if args and args[0].isalpha() and args[0].isupper() else 'AB'
want_list = 'list' in args
watch = float(args[args.index('watch') + 1]) if 'watch' in args and args.index('watch') + 1 < len(args) else 0


def word(w, a, names):
    b = w.rd(w.base + a, 4)
    h = b.hex().upper() if b else '?'
    return names.get(h, 'other %s' % h)


def asset_id(w, handle):
    try:
        ins = w.geom_from_handle(handle)
    except Exception:
        ins = None
    info = w.q(ins + 0x10) if ins else None
    aid = w.i(info + 0x18) if info else None
    return (aid % 10000000 if aid is not None else None), ins


def items(w):
    im = w.g(MAPITEM_G)
    out = []
    if not im:
        return out
    for off in (0x18, 0x48, 0x78):
        node, k = w.q(im + off), 0
        while node and k < 400:
            iid, flags = w.d(node + 0x30), w.d(node + 0x58) or 0
            e = {'id': iid, 'flags': flags, 'pos': w.f3(node + 0x40), 'linked': bool(flags & 8)}
            if e['linked']:
                e['aid'], ins = asset_id(w, w.d(node + 0x3C))
                e['shown'] = (w.b(ins + 0x126) or 0) & 3 if ins else None
            out.append(e)
            node, k = w.q(node + 0x10), k + 1
    return out


def block(who, w):
    off = w.g(OFFLINE)
    L = ['%s role %s offline %s | %s' % (who, w.b(w.base + ROLE), w.b(off + 0xBDA) if off else '?',
                                          ', '.join('%s %s' % (n, word(w, a, d)) for a, d, n in WORDS))]
    it = items(w)
    linked = [e for e in it if e['linked']]
    by = {}
    for e in linked:
        k = KINDS.get(e.get('aid'), 'other')
        by[k] = by.get(k, 0) + 1
    ids = sorted(e['id'] or 0 for e in it)
    L.append('  world items %d (asset-linked %d: %s) | id crc %08x' % (
        len(it), len(linked), ' '.join('%s %d' % kv for kv in sorted(by.items())) or '-',
        zlib.crc32(struct.pack('<%dI' % len(ids), *ids)) if ids else 0))
    if want_list:
        for e in linked:
            L.append('    %08x asset %s %s shown %s flags %08x' % (e['id'] or 0, e.get('aid'), fmt3(e['pos']),
                                                                  e.get('shown'), e['flags']))
    g = w.g(GDM)
    pgd = w.q(g + 0x20) if g else None
    im = w.g(ITEM_MGR)
    slot = w.b(pgd + 0x104) if pgd else None
    if im and slot is not None and slot <= 0xB:
        e = im + 0x21D8 + slot * 0x20
        L.append('  blood crystal: skill-enhancement offers pending %s (player %s slot %d)' % (
            w.q(e + 0x18), w.i(pgd + 0xD0), slot))
    else:
        L.append('  blood crystal: offers unreadable (item mgr %s, slot %s)' % (hex(im or 0), slot))
    # batch39b 2: on the HOST a guest's Bloodsac kill lands as an offer in the host's slot of that guest
    if im:
        nums = {}
        wcm = w.g(0x5B3CD88)
        if wcm:
            arr, n = w.q(wcm + 0x30), w.d(wcm + 0x28) or 0
            for k in range(min(n, 16)):
                c = w.q(arr + 0x38 * k) if arr else None
                p = w.q(w.q(c + 0x20) + 0x1D0) if c and w.q(c + 0x20) else None
                if p and w.b(p + 0x104) is not None:
                    nums[w.b(p + 0x104)] = w.i(p + 0xD0)
        per = ['slot %d (p%s) %s' % (s, nums.get(s, '?'), w.q(im + 0x21D8 + s * 0x20 + 0x18))
               for s in range(12) if (w.q(im + 0x21D8 + s * 0x20 + 0x18) or 0) not in (0, None)]
        L.append('  crystal offers by slot: %s | words: 0x15B0528 %s, 0x15B056C %s, G1 0x159CB44 %s, '
                 'SKILL_LOCAL 0xCFF878 %s' % (
                     ', '.join(per) or 'none',
                     word(w, 0x15B0528, {'28010034': 'stock (LAN sends subtype 14)', '1F2003D5': 'CRYSTAL_LOCAL',
                                         '71C5FF17': 'CRYSTAL_GUEST'}),
                     word(w, 0x15B056C, {'082140F9': 'I1 broadcast', '082540F9': 'stock to-server'}),
                     word(w, 0x159CB44, {'FF190094': 'stock direct give'}),
                     word(w, 0xCFF878, {'1F2003D5': 'built in', '88010034': 'stock'})))
    return L


def main():
    ws = {}
    for who in games:
        try:
            ws[who] = W(who)
        except Exception as e:
            print(who, 'no debug server:', e)
    last = {}
    t0 = time.time()
    while True:
        for who, w in ws.items():
            L = block(who, w)
            s = '\n'.join(L)
            if not watch or last.get(who) != s:
                print(('%6.1f ' % (time.time() - t0) if watch else '') + s, flush=True)
                last[who] = s
        if not watch or time.time() - t0 > watch:
            break
        time.sleep(2.0)


if __name__ == '__main__':
    main()
