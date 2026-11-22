"""icons1_gen.py: ICONS1, alpha reconstruction (alpha_reconstructions.md a). Static generator, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes icons1_live.py.
python icons1_gen.py [--dry]      (from diag/net)

RECONSTRUCTED, not the real data: the network test's regulation (server-delivered) evidently gave Phase I a trend-type
list; ours names none (PhaseInfoParam +0xE4 = -1 in every rule set's Phase I row, icons2_notes 6). ICONS1 hooks the
area-icon pick's list read 0x1035374 (`ldr w1, [x8, #0xe4]`): when the row names no list (negative) and the box
I1BOX byte 0 is set, it uses list 100002 (Phase II's JointStruggleAdditionalAppearanceLot rows 20:0, 40:1, 40:2),
the closest existing list, and counts it (+4). Only Phase I rows are negative in the rule sets (Phase IV is 100004
with count 0). The assist sets the box only on the host (GENERATOR_IDLE == 0) in a LAN session; the guests take
the host's list through the v4.27 AREA_ICONS share as in the other rounds. Offline the box is 0: stock."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'icons1_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
SITE, BACK, LIST = 0x1035374, 0x1035378, 100002
listing = []
PLANNED = [
    ('takerace_gen', 'TRBOX', 0xC50F710, 0xC50F8C0), ('takerace_gen', 'TRGRANT', 0xC503AF8, 0xC503CF8),
    ('takerace_gen', 'TRFRAME', 0xC503CF8, 0xC504018),
    ('needdata_gen', 'NDBOX', 0xC50F8C0, 0xC50F8D0), ('needdata_gen', 'NEEDDATA', 0xC504018, 0xC504078),
    ('outhide_gen', 'OHBOX', 0xC50F8D0, 0xC50F8D8), ('outhide_gen', 'OUTHIDE', 0xC504078, 0xC5040C8),
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
for a, t in ((0x1035370, 'cbz x8, #0x10355a0'), (SITE, 'ldr w1, [x8, #0xe4]'), (BACK, 'stur xzr, [x29, #-0x20]'),
             (0x103537C, 'tbnz w1, #0x1f, #0x10355a4'), (0x1035380, 'adrp x8, #0x59df000'),
             (0x10353BC, 'bl #0x1559720'), (0x10353D8, 'sub w16, w8, w14'), (0x10355A8, 'mov w16, wzr')):
    stock(a, t)
assert targets_in(SITE, SITE + 8) == []
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
listing.append('x16 is written before it is read on both continuations (0x10353D8 / 0x10355A8) and x17 is not used '
               'in 0x1035180..0x1035B00; x8 is kept when the row stays negative (the stock no-list path may read it)')

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

g = C.Gen('icons1_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 20
BOX = g.alloc('I1BOX', 'FAR_DATA', 8, 'ICONS1 {u8 on (host, LAN), pad, u32 uses}')
T = g.alloc('ICONS1', 'FAR_CODE', SIZE * 4, 'ICONS1 0x1035374: Phase I area icons from list 100002 (reconstructed)')
a = C.Asm(T)
a(C.text_word(SITE))                                       # ldr w1, [x8, #0xe4]
a(C.to(C.tbz, 'w1', 31, 'back') if hasattr(C, 'tbz') else 0)
a(lambda pc, L: C.adrp(pc, 1, BOX))
a(C.ldrb(1, 1, C.lo12(BOX)))
a(C.to(C.cbz_w, 'w1', 'keep'))
a(lambda pc, L: C.adrp(pc, 8, BOX))                        # x8 is rewritten at 0x1035380 on this path
a(C.add_xi(8, 8, C.lo12(BOX)))
a(C.ldr_w(1, 8, 4))
a(C.add_wi(1, 1, 1))
a(C.str_w(1, 8, 4))
a(C.movz_w(1, LIST & 0xFFFF))
a(C.movk_w(1, LIST >> 16, 1))
a.many(lambda pc, L: C.far_jump(pc, BACK))
a.label('keep')
a(C.text_word(SITE))                                       # the row's own (negative) value again
a.label('back')
a.many(lambda pc, L: C.far_jump(pc, BACK))
assert len(a.words()) <= SIZE, len(a.words())
assert 0 not in a.words(), 'an encoder is missing in cave_lib'
cave = g.cave('ICONS1', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> ICONS1 0x%X (x16 dead at 0x1035374)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'ldr w1, [x8, #0xe4]', C.b(SITE, PAD), 'ICONS1 (Phase I icons, reconstructed)')]
HOOK_WORD = C.b(SITE, PAD)

groups = {'ICONS1_CAVE': cave + tramp, 'ICONS1': hook}
order = ['ICONS1_CAVE', 'ICONS1']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word 0x%08X' % HOOK_WORD)
print('registry rows (lead adds; TAKERACE, NEEDDATA and OUTHIDE rows assumed present):')
print('| icons1_gen | I1BOX | 0x%X..0x%X | ICONS1 {u8 on, pad, u32 uses} (FAR_DATA) |' % (BOX, BOX + 8))
print('| icons1_gen | ICONS1 | 0x%X..0x%X | ICONS1 0x1035374: Phase I area icons from list 100002 (alpha, '
      'reconstructed); trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('RECONSTRUCTED')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'ICONS1': 0x%X, 'I1BOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_WORD': 0x%X}" % (T, BOX, PAD, HOOK_WORD)
                + chr(10))
