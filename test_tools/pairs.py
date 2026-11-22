"""Bloodbound pairs checker. READ-ONLY (only Mem.read / u32 / u64, never writes).
python diag/twin/pairs.py [GAMES=AB]          (from the workspace root, like the other twin tools)

Per game:
  rule      byte main+0x5B65C70 (0 Standard, 1 No Alliances, 2 Bloodbound), host byte main+0x492AFD8 (0 = host),
            mode mgr3 *(main+0x5B3CE08)+0x1268 (6 = LAN), own player number *(GDM main+0x5B57EB8)+0x20 -> +0xD0
  patch     hook word 0x10AC510 (stock 54000081 b.ne / BB_PAIRS b tramp), trampoline + first cave word present
  box       BB_BOX main+0xC50F210 (bloodbound_build_notes.md 1): state 0 empty / 2 valid / 3 consumed, k, pairs
  entries   alliance manager AM = *(main+0x5B3CDD0): deque map +0x10, start +0x30, count +0x38, 128 x 32-byte
            entries per block; a +0, b +4, leader +8, u8 +0xC, slot +0x10, SpEffects +0x14/+0x18, u8 +0x1C
            apply-pending, u8 +0x1D phase-start (bloodbound_notes 1c); AM +0x174 phase-start mark
  partner   u32 *(main+0x5B55D30)+0x170 (local partner id, rule 2)
At the end: pairs (a, b, slot) equal on every game read, and equal to the box pairs.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'net'))
from mem import Mem  # noqa: E402

try:
    import bloodbound_live as BBL
    BOX, HOOK, HOOK_WORD, CAVE = BBL.BOX, BBL.HOOK, BBL.HOOK_WORD, BBL.CAVE
    TRAMP = BBL.BB_PAIRS[0][0]
    CAVE_W0 = int.from_bytes(bytes.fromhex(BBL.BB_CAVE[0][2]), 'little')
    TRAMP_W0 = int.from_bytes(bytes.fromhex(BBL.BB_PAIRS[0][2]), 'little')
except Exception:                       # generator output missing: fixed values of bloodbound_gen.py 2026-11-14
    BOX, HOOK, HOOK_WORD, CAVE, TRAMP = 0xC50F210, 0x10AC510, 0x15164A63, 0xC500820, 0x563EE9C
    CAVE_W0, TRAMP_W0 = 0x54000401, 0xD0037610

RULE, HOST, MGR3, GDM, AM_PTR, PARTNER_G = 0x5B65C70, 0x492AFD8, 0x5B3CE08, 0x5B57EB8, 0x5B3CDD0, 0x5B55D30
HOOK_STOCK = 0x54000081
RULES = {0: 'Standard', 1: 'No Alliances', 2: 'Bloodbound'}
STATES = {0: 'empty', 2: 'VALID', 3: 'consumed'}

games = next((a for a in sys.argv[1:] if not a.startswith('-')), 'AB')


def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def rd(m, a, n):
    try:
        return m.read(a, n)
    except Exception:
        return None


def word(m, a):
    b = rd(m, a, 4)
    return None if b is None else u32(b, 0)


def entries(m):
    am = m.u64(m.base + AM_PTR)
    if not am:
        return None, None, []
    h = m.read(am, 0x40)
    mp, start, count = u64(h, 0x10), u64(h, 0x30), u64(h, 0x38)
    out = []
    for i in range(min(count, 16)):
        k = start + i
        blk = m.u64(mp + 8 * (k >> 7))
        e = m.read(blk + (k & 0x7F) * 0x20, 0x20)
        out.append(dict(a=i32(e, 0), b=i32(e, 4), c=i32(e, 8), flag=e[0xC], slot=i32(e, 0x10),
                        sp=(i32(e, 0x14), i32(e, 0x18)), pending=e[0x1C], start=e[0x1D]))
    return am, count, out


sets, boxes = {}, {}
for w in games:
    try:
        m = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)
        continue
    b = m.base
    rule = m.read(b + RULE, 1)[0]
    host = m.read(b + HOST, 1)[0]
    mgr3 = m.u64(b + MGR3)
    mode = m.u32(mgr3 + 0x1268) if mgr3 else None
    g = m.u64(b + GDM)
    pgd = m.u64(g + 0x20) if g else 0
    own = i32(m.read(pgd + 0xD0, 4), 0) if pgd else None
    print('%s %s | rule %d (%s) | mode %s | own player no %s' % (
        w, 'HOST' if host == 0 else 'guest(%d)' % host, rule, RULES.get(rule, '?'), mode, own))
    hk, tw, cw = word(m, b + HOOK), word(m, b + TRAMP), word(m, b + CAVE)
    hks = 'stock b.ne' if hk == HOOK_STOCK else ('BB_PAIRS' if hk == HOOK_WORD else 'OTHER')
    print('  patch: hook 0x%X %s (%s) | tramp 0x%X %s | cave 0x%X %s' % (
        HOOK, '%08x' % hk if hk is not None else '-', hks, TRAMP,
        'ok' if tw == TRAMP_W0 else ('%08x' % tw if tw is not None else 'unreadable'), CAVE,
        'ok' if cw == CAVE_W0 else ('%08x' % cw if cw is not None else 'unreadable')))
    box = rd(m, b + BOX, 12)
    if box is None:
        print('  box main+0x%X unreadable (cave region not mapped?)' % BOX)
    else:
        k = box[1]
        prs = [(box[2 + 2 * i], box[3 + 2 * i]) for i in range(min(k, 4))]
        boxes[w] = (box[0], prs)
        print('  box main+0x%X: %s | state %d (%s) k %d%s pairs %s' % (
            BOX, box.hex(' '), box[0], STATES.get(box[0], 'ignored'), k, ' (>4: ignored)' if k > 4 else '',
            ' '.join('(%d,%d)' % p for p in prs) or '-'))
    pg = m.u64(b + PARTNER_G)
    partner = i32(m.read(pg + 0x170, 4), 0) if pg else None
    am, count, al = entries(m)
    if am is None:
        print('  alliance manager: none')
        continue
    print('  AM %x: count(+0x38) %d, +0x8C %d, phase-start mark(+0x174) %d | local partner(+0x170) %s' % (
        am, count, m.read(am + 0x8C, 1)[0], m.read(am + 0x174, 1)[0], partner))
    for i, e in enumerate(al):
        print('    [%d] %d + %d leader %d slot %d flag(+0xC) %d speffects %d/%d pending %d phase-start %d' % (
            i, e['a'], e['b'], e['c'], e['slot'], e['flag'], e['sp'][0], e['sp'][1], e['pending'], e['start']))
    sets[w] = [(min(e['a'], e['b']), max(e['a'], e['b']), e['slot']) for e in al]

if len(sets) >= 2:
    first = next(iter(sets.values()))
    print('pairs (a, b, slot) equal on all games read: %s' % ('yes' if all(v == first for v in sets.values()) else 'NO'))
for w, v in sets.items():
    want = [(min(a, c), max(a, c), i) for i, (a, c) in enumerate(boxes.get(w, (0, []))[1])]
    print('  %s entries %s | box %s -> %s' % (w, v, want or '-', 'match' if want and v == want else
                                             ('-' if not want else 'DIFFERENT')))
