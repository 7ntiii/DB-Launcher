"""Flame corpses, Alchemy Forges and other action-menu assets (+ MapItemMan pickups) in the world. READ ONLY.
python diag/twin/flames.py GAMES [flame|forge|pick|all] [items] [watch SECONDS]
  GAMES  A, B or AB (each game is listed in turn; compare the 'h' handles and states between games)
  filter flame (default), forge, pick, all (every action-menu kind)
  items  also list MapItemMan world items (lists +0x18 / +0x48 / +0x78, node +0x30 id, +0x40 pos, +0x58 flags)
  watch  re-read only the found assets every 2 s for SECONDS and print a line when a state changes

Static facts (diag/net/flame_items_notes.md) [V = read in code]:
  asset id = [info+0x18] % 10000000, info = [ins+0x10]; kind = u8 info+0x304, else u8 [info+0x20]+0x128 (param row
  AssetEnvironmentGeometryParam) [V 0x11A4648]; 0x74 handle = u32 ins+8 [V press 0x11A2FB0].
  'taken' state [V grant 0x11A36C0, reset 0x11A2BE0]:
    mask  = info+0x468 low 12 bits: bit = player slot [[chr+0x20]+0x1D0]+0x104 that used it (0xFD78C0 @0xFD79C4)
    all   = u8 info+0x470: 1 = used up for everybody (kinds whose processor slot +0x48 is false: large Flame corpses)
    hold  = s32 info+0x460: holder player no (kinds whose slot +0x40 is true; -1 = free)
  The prompt is hidden for player P when mask has P's bit or all != 0 (driver 0x11A22E0).
  enable: u8 ins+0x126 bits 0|1 both set = active (driver step 1); p0D = u8 [info+0x20]+0xD (1 = never usable).
Kinds: 4 = 99280 Flame corpse (Flame Virtue counter 110000, once per player), 5 = 99281 large corpse (counter 110010,
first player only, reset each phase), 13 = 99282 large corpse not reset at the phase change, 7 = 99240..99247
Alchemy Forge (once per player), 3 = 99330, 9 = 315211 / 12 = 99500 'Pick up', 8 = 105211.. (no processor),
1 = 99250, 2 = 99260.. 'Gain Power of Blood' (no processor), 11 = kin circle, 14 = small circle."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, fmt3

FLAME = {99280: 'flame', 99281: 'flameL', 99282: 'flameL*'}
FORGE = {i: 'forge' for i in range(99240, 99248)}
PICK = {99330: 'k3', 315211: 'pick9', 99500: 'pick12', 105211: 'pick8', 115211: 'pick8', 125211: 'pick8',
        99250: 'pick1', 99260: 'rose', 99261: 'rose', 99262: 'rose', 99263: 'rose', 99264: 'rose', 99265: 'rose',
        99266: 'rose', 99267: 'rose', 99270: 'rose', 99271: 'rose'}
OTHER = {99290: 'kin', 99291: 'kin', 99292: 'kin', 99295: 'small'}

args = sys.argv[1:]
if not args:
    print(__doc__)
    sys.exit(1)
games = args[0]
filt = next((a for a in args[1:] if a in ('flame', 'forge', 'pick', 'all')), 'flame')
want = dict(FLAME)
if filt in ('forge', 'all'):
    want.update(FORGE)
if filt in ('pick', 'all'):
    want.update(PICK)
if filt == 'all':
    want.update(OTHER)
if filt == 'forge':
    want = dict(FORGE)
if filt == 'pick':
    want = dict(PICK)
show_items = 'items' in args
watch = 0
if 'watch' in args:
    k = args.index('watch')
    watch = float(args[k + 1]) if k + 1 < len(args) else 60.0


def local_slot(w):
    """(player no, slot) of the local player: [[chr+0x20]+0x1D0] +0xD0 / +0x104 (default object main+0x5B583B0)"""
    chr_, _, _ = w.me()
    if not chr_:
        return None, None
    d = w.q(chr_ + 0x20)
    p = w.q(d + 0x1D0) if d else None
    if not p:
        p = w.base + 0x5B583B0
    return w.i(p + 0xD0), w.b(p + 0x104)


def state(w, ins):
    info = w.q(ins + 0x10)
    if not info:
        return None
    row = w.q(info + 0x20)
    kind = w.b(info + 0x304) or (w.b(row + 0x128) if row else None)
    return {
        'h': w.d(ins + 8),
        'kind': kind,
        'en': (w.b(ins + 0x126) or 0) & 3,
        'p0D': w.b(row + 0xD) if row else None,
        'mask': (w.q(info + 0x468) or 0) & 0xFFF,
        'all': w.b(info + 0x470),
        'hold': w.i(info + 0x460),
    }


def line(game, ins, aid, name, pos, s, slot):
    mine = ''
    if slot is not None and slot < 12 and s['mask'] >> slot & 1:
        mine = ' USED-BY-ME'
    taken = ' TAKEN-ALL' if s['all'] else ''
    off = '' if s['en'] == 3 else ' off'
    return '%s %-7s %6d k%-2s h=%08x %s en=%d p0D=%s mask=%03x all=%s hold=%s%s%s%s  geom 0x%x' % (
        game, name, aid, s['kind'], s['h'] or 0, fmt3(pos), s['en'], s['p0D'], s['mask'], s['all'], s['hold'],
        taken, mine, off, ins)


def world_items(w, game):
    im = w.g(0x5B3CDC0)
    if not im:
        print(game, 'MapItemMan null')
        return
    for off in (0x18, 0x48, 0x78):
        node, n = w.q(im + off), 0
        while node and n < 200:
            iid, pos, fl = w.d(node + 0x30), w.f3(node + 0x40), w.h(node + 0x58)
            print('%s item list+0x%x id %08x%s pos %s flags %04x%s' % (
                game, off, iid or 0, ' net' if iid and iid & 0x10 else '', fmt3(pos), fl or 0,
                ' take-requested' if fl and fl & 0x4000 else ''))
            node, n = w.q(node + 0x10), n + 1
        print('%s item list+0x%x: %d' % (game, off, n))


found = {}
for g in games:
    w = W(g)
    no, slot = local_slot(w)
    print('%s local player no %s slot %s; offline flag +0xBDA = %s' % (
        g, no, slot, w.b((w.g(0x5B65C20) or 0) + 0xBDA)))
    hits, count, n = [], {}, 0
    for blockid, k, ins in w.all_geoms(limit=200000):
        n += 1
        info = w.q(ins + 0x10)
        if not info:
            continue
        aid = w.i(info + 0x18)
        if aid is None:
            continue
        aid %= 10000000
        if aid in want:
            s = state(w, ins)
            if not s:
                continue
            count[want[aid]] = count.get(want[aid], 0) + 1
            pos = w.geom_pos(ins)
            hits.append((ins, aid, pos, s))
            print(line(g, ins, aid, want[aid], pos, s, slot))
    print('%s geoms %d, counts %s, active %d, used-by-me %d, taken-all %d' % (
        g, n, count, sum(1 for h in hits if h[3]['en'] == 3),
        sum(1 for h in hits if slot is not None and slot < 12 and h[3]['mask'] >> slot & 1),
        sum(1 for h in hits if h[3]['all'])))
    if show_items:
        world_items(w, g)
    w.report_missing()
    found[g] = (w, slot, hits)

if watch:
    end = time.time() + watch
    last = {(g, h[0]): h[3] for g, (w, slot, hits) in found.items() for h in hits}
    while time.time() < end:
        time.sleep(2.0)
        for g, (w, slot, hits) in found.items():
            for ins, aid, pos, _ in hits:
                s = state(w, ins)
                if s and s != last.get((g, ins)):
                    print(time.strftime('%H:%M:%S'), 'CHANGE', line(g, ins, aid, want[aid], pos, s, slot))
                    last[(g, ins)] = s
