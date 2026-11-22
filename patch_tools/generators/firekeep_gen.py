"""firekeep_gen.py: plan B for the fire at an eliminated finalist's spot (fire_planb_notes.md). Static generator,
allocated with Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes firekeep_live.py.
python firekeep_gen.py [--dry]      (from diag/net)

When a player's pgd stage goes 01 01 00 00 -> 04 05 01 01 (the final's "out", event 7), the pgd apply 0x11454A0
calls 0x17BFDD0(chr) at 0x1145888. That function KILLS THE CHR AGAIN: an HP event, type 0x19, through the predicted
HP path 0xDDEEC0 on prop [[chr+0x2470]+0x18]+0x1F8. Then it disables it: chr+0x12BC |= 0x4000, then 0x173DB60.
On a receiver this hits the out player's COPY, which is already dead (probe: GONE about 2 s after the death), so
the copy's death starts a second time on a chr whose owner never confirms it.
FIREKEEP: in a LAN match, for a chr that is not our own player, and only for the event-7 word (second byte 5),
the call is skipped. The copy keeps its pgd word 04 05 01 01 (ranking, Outcome item, FinalAlign unchanged) and
stays in the world as a dead body, as in the 2-player final, where the block never runs and no fire was seen.
Offline, our own player, and every other word (culls 04 03 01 01, end on points, the winner) run the stock call."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'firekeep_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G = 0x5B65C20, 0x5B3CD88
SITE, BACK, KILL = 0x1145888, 0x114588C, 0x17BFDD0
BLINK = (0xC501870, 0xC5018A0)
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


def bl_callers(target):
    out = []
    for i, w in enumerate(W):
        if (w & 0xFC000000) == 0x94000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == target:
                out.append(4 * i)
    return out


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
assert bl_callers(KILL) == [SITE]                          # the pgd apply is its only caller
for a, t in ((0x114556C, 'add x22, x20, x24'), (0x1145574, 'ldr w8, [x22]'),       # entry = x20 + x24, +0 = player no
             (0x11455EC, 'ldr w21, [x27]'),                                          # w21 = the OLD pgd word
             (0x1145674, 'ldr w8, [x11, #0x40]'), (0x114567C, 'str w8, [x27]'),     # new word = entry +0x40
             (0x11457A0, 'add x8, x20, x24'), (0x11457A4, 'ldrb w8, [x8, #0x42]'), (0x11457A8, 'cbz w8, #0x1145890'),
             (0x11457D8, 'mov w2, #0x407'), (0x1145800, 'bl #0x17f1940'), (0x1145834, 'ldur x22, [x29, #-0x48]'),
             (0x114586C, 'and w8, w21, #0xff0000'), (0x1145870, 'cbnz w8, #0x1145890'), (0x1145874, 'cbz x22, #0x1145890'),
             (0x1145878, 'add x8, x20, x24'), (0x114587C, 'and w1, w23, #1'), (0x1145880, 'ldrb w2, [x8, #5]'),
             (0x1145884, 'mov x0, x22'), (SITE, 'bl #0x17bfdd0'), (BACK, 'ldr x11, [sp, #0x28]'),
             # the killer: HP event 0x19 through the predicted HP path, then the disable
             (0x17BFE08, 'mov w9, #0x19'), (0x17BFE34, 'add x22, x8, #0x1f8'), (0x17BFEB4, 'bl #0xddeec0'),
             (0x17BFF08, 'str x9, [x8]'), (0x17BFF18, 'bl #0x173db60'), (0x173DB84, 'tbz w8, #0xe, #0x173dd5c')):
    stock(a, t)
assert targets_in(SITE, SITE + 8) == []
# the block 0x1140DD0 calls the apply at 0x11411A4; the apply's other callers are the stock online / end paths
assert sorted(bl_callers(0x11454A0)) == [0x11411A4, 0x11414C4, 0x11415E0, 0x1141E88, 0x1145360]
assert not any(x in C.SHIPPED for x in range(0x11457A0, 0x1145890))
listing.append('0x17BFDD0 has one caller (0x1145888); it is reached only on the 3rd-byte 0 -> non-0 change of a pgd '
               'stage word for a chr found by query 0x407')

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
                continue                    # not right after a (noreturn) call: its LR would name the trampoline
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


PAD = find_pad(SITE, 3)
assert PAD
listing.append('trampoline padding 0x%X..0x%X after `%s` (zero, before a pacibsp, unreferenced, free)' % (
    PAD, PAD + 12, dis(PAD - 4)))

g = C.Gen('firekeep_gen', out=OUT, dry=True)
SIZE = 32
BOX = g.alloc('FKBOX', 'FAR_DATA', 8, 'FIREKEEP {u32 skips, u32 last player no}')
T = g.alloc('FKEEP', 'FAR_CODE', SIZE * 4, 'FIREKEEP 0x1145888: no second kill of an out copy')
assert T + SIZE * 4 <= BLINK[0] or T >= BLINK[1]

# FKEEP: entered by `b` from the bl site 0x1145888 (x30 / x9..x17 / NZCV are free there: a call follows on the
# stock path, so nothing after it can rely on them). x0 = chr, w1 / w2 = args, x8 = list entry (+0 player no,
# +0x40 the new word).
a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 9, OFFL))
a(C.ldr_x(9, 9, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x9', 'call'))
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'call'))                             # offline: stock
a(C.ldrb(9, 8, 0x41))
a(C.cmp_wi('w9', 5))
a(C.to(C.bne, 'call'))                                      # not the final's out word (04 05 ..): stock
a(lambda pc, L: C.adrp(pc, 9, WCM_G))
a(C.ldr_x(9, 9, C.lo12(WCM_G)))
a(C.to(C.cbz_x, 'x9', 'call'))
a(C.ldr_x(9, 9, 0x1A8))
a(C.cmp_xr('x9', 'x0'))
a(C.to(C.beq, 'call'))                                      # our own player: stock
a(lambda pc, L: C.adrp(pc, 10, BOX))
a(C.add_xi(10, 10, C.lo12(BOX)))
a(C.ldr_w(9, 10, 0))
a(C.add_wi(9, 9, 1))
a(C.str_w(9, 10, 0))
a(C.ldr_w(9, 8, 0))
a(C.str_w(9, 10, 4))
a.many(lambda pc, L: C.far_jump(pc, BACK))                 # skipped: the copy stays as it is
a.label('call')
a.many(lambda pc, L: C.far_call(pc, KILL))
a.many(lambda pc, L: C.far_jump(pc, BACK))
assert len(a.words()) <= SIZE, len(a.words())
cave = g.cave('FKEEP', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> FKEEP 0x%X (x16: a bl site)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'bl #0x17bfdd0', C.b(SITE, PAD), 'FIREKEEP (no second kill of an out copy in LAN)')]

groups = {'FIREKEEP_CAVE': cave + tramp, 'FIREKEEP': hook}
order = ['FIREKEEP_CAVE', 'FIREKEEP']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows (lead adds):')
print('| firekeep_gen | FKBOX | 0x%X..0x%X | FIREKEEP {u32 skips, u32 last player no} (FAR_DATA) |' % (BOX, BOX + 8))
print('| firekeep_gen | FKEEP | 0x%X..0x%X | FIREKEEP 0x1145888: a LAN out copy is not killed again (0x17BFDD0 skipped); '
      'trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('When a player')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'FKEEP': 0x%X, 'FKBOX': 0x%X, 'TRAMP': 0x%X}\n" % (T, BOX, PAD))
