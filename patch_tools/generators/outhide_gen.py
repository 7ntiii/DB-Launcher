"""outhide_gen.py: OUTHIDE, the game-thread half of v4.39 (fire_alpha_notes.md). Static generator, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes outhide_live.py.
python outhide_gen.py [--dry]      (from diag/net)

The out player's own game never runs the stock end of an eliminated chr (v418: no hand-over of our own player), so
its dead body is never put through the tail of 0x17BFDD0 (chr+0x12BC |= 0x4000, chr+0x12C5 |= 0x100, then
0x173DB60), which every other game gives its copy at the hand-over (FINALOUT, without FIREKEEP). OUTHIDE hooks the
player-data pump's per-tick word 0x14DE948 (`ldr x8, [x28]`): when the box OHBOX {u64 chr} holds a chr, it clears
the box and runs exactly that tail on it (no HP event, no pgd or spectator change), then the stock word.
The assist writes the box once, with our own chr, 2 s after our player is out in a final of 3+ finalists."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'outhide_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
SITE, BACK, HIDE = 0x14DE948, 0x14DE94C, 0x173DB60
listing = []
PLANNED = [   # rows the lead has not added yet: treat them as taken
    ('takerace_gen', 'TRBOX', 0xC50F710, 0xC50F8C0), ('takerace_gen', 'TRGRANT', 0xC503AF8, 0xC503CF8),
    ('takerace_gen', 'TRFRAME', 0xC503CF8, 0xC504018),
    ('needdata_gen', 'NDBOX', 0xC50F8C0, 0xC50F8D0), ('needdata_gen', 'NEEDDATA', 0xC504018, 0xC504078),
]


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            t = pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000 or (w & 0x3B000000) == 0x18000000:
            imm = (w >> 5) & 0x7FFFF
            t = pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
        elif (w & 0x7E000000) == 0x36000000:
            imm = (w >> 5) & 0x3FFF
            t = pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
        elif (w & 0x9F000000) == 0x10000000:
            d = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
            t = pc + (d - (1 << 21) if d & (1 << 20) else d)
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


# ================================================================ code facts [V]
for a, t in ((SITE, 'ldr x8, [x28]'), (BACK, 'cbz x8, #0x14df00c'), (0x14DE954, 'mov w19, #3'),
             (0x14DE8B4, 'cbz w19, #0x14de948'), (0x14DE8C0, 'b.eq #0x14de948'), (0x14DE8F4, 'b.eq #0x14de948'),
             # the stock tail in 0x17BFDD0 that OUTHIDE repeats
             (0x17BFEF4, 'mov w8, #0x12bc'), (0x17BFF00, 'ldr x9, [x8]'), (0x17BFF04, 'orr x9, x9, #0x4000'),
             (0x17BFF08, 'str x9, [x8]'), (0x17BFF0C, 'ldr w9, [x8, #9]!'), (0x17BFF10, 'orr w9, w9, #0x100'),
             (0x17BFF14, 'str w9, [x8]'), (0x17BFF18, 'bl #0x173db60'),
             (HIDE, 'pacibsp'), (0x173DB78, 'mov x19, x0')):
    stock(a, t)
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
listing.append('0x14DE948 is entered from 0x14DE8B4 / 0x14DE8C0 / 0x14DE8F4 / fall-through after the drain calls: '
               'no caller-saved register is live there (x8 is loaded by the word itself)')

others = C.live_records(exclude=(OUT,))


def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


PAD = find_pad(SITE, 3)
assert PAD
listing.append('trampoline padding 0x%X..0x%X after `%s`' % (PAD, PAD + 12, dis(PAD - 4)))

g = C.Gen('outhide_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 20
BOX = g.alloc('OHBOX', 'FAR_DATA', 8, 'OUTHIDE {u64 chr}')
T = g.alloc('OUTHIDE', 'FAR_CODE', SIZE * 4, 'OUTHIDE 0x14DE948: stock end of our own out chr')
a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 10, BOX))
a(C.add_xi(10, 10, C.lo12(BOX)))
a(C.ldr_x(0, 10, 0))
a(C.to(C.cbz_x, 'x0', 'back'))
a(C.str_x('xzr', 10, 0))                                   # box = 0 (once)
a(C.movz_w(8, 0x12BC))
a(C.add_xr(8, 0, 8))                                       # x8 = chr + 0x12BC
for site in (0x17BFF00, 0x17BFF04, 0x17BFF08, 0x17BFF0C, 0x17BFF10, 0x17BFF14):
    a(C.text_word(site))                                   # the stock tail words (x8 / x9 only, no pc use)
a.many(lambda pc, L: C.far_call(pc, HIDE))
a.label('back')
a(C.relocate(SITE, 0)[0])                                  # ldr x8, [x28]
a.many(lambda pc, L: C.far_jump(pc, BACK))
assert len(a.words()) <= SIZE, len(a.words())
assert 0 not in a.words(), 'an encoder is missing in cave_lib'
cave = g.cave('OUTHIDE', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> OUTHIDE 0x%X (x16 dead at 0x14DE948)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'ldr x8, [x28]', C.b(SITE, PAD), 'OUTHIDE (stock end of our own out chr)')]

groups = {'OUTHIDE_CAVE': cave + tramp, 'OUTHIDE': hook}
order = ['OUTHIDE_CAVE', 'OUTHIDE']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows (lead adds; TAKERACE and NEEDDATA rows assumed present):')
print('| outhide_gen | OHBOX | 0x%X..0x%X | OUTHIDE {u64 chr} (FAR_DATA) |' % (BOX, BOX + 8))
print('| outhide_gen | OUTHIDE | 0x%X..0x%X | OUTHIDE 0x14DE948: the stock end (0x17BFDD0 tail) of our own out chr; '
      'trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('The out player')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'OUTHIDE': 0x%X, 'OHBOX': 0x%X, 'TRAMP': 0x%X}" % (T, BOX, PAD) + chr(10))
