"""love6_gen.py: Love Ephemeral, the loved one's own "Reunited" (+4 Virtue, row 2501) in LAN (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes love6_live.py.
python love6_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: love6_notes.md.

REGISTRY: allocated with Gen(dry=True) (task rule: new files only); the lead adds the row when baking:
  love6_gen | LOVE6 | <printed range> | Love: loved one mirrors the bearer's reunite (event 4 + reward 2501, LAN)

Groups
  LOVE6_CAVE  far cave LOVE6 + a 3-word trampoline in the zero padding 0x118DC48 (before pacibsp 0x118DC60).
  LOVE6       0x118E3DC `ldr x8, [x19, #0x40]` (passive 250 vt+0x20 0x118E3A8, first word after the own
     "not reunited" test) -> `b trampoline`.
  Why (live 2026-11-17, v3.9.12): the bearer's 240 logic on the loved game had reunited 1 and the bearer got +4,
  but the loved one's 250 stayed reunited 0 with no +4. The stock part (a) (0x118E3DC..0x118E604) that mirrors the
  bearer's flag reads the class-B list through [root+0x90] ONLY (0x118E450, no +0x98 fallback, unlike the
  prompt test 0x118EA24 and the step sender 0x118EA80) and then ONE SQM entry / slot / ACTIVE holder +0x20.
  The cave does the same job without those single points: LAN only (mgr3 +0x1268 == 6); cond = root+0x90, else
  +0x98; for every flagged list entry: handle -> chr (0x17E7828, as LOVE5) -> player no (< 100) -> every SQM entry
  with that id, slots 0..2, holder +0x20 else +0x28, logic vtable == 0x56F7B38 (active 240) with reunited +0x48 set
  -> exactly the stock send block 0x118E5A0..0x118E604: forward event 4 (0x1196938 with the stock functor vt
  0x56F7E18 {logic}: sets our reunited +0x48 and sends to all) + reward type 4 (0x117AF0C: row 2501, +4 once),
  then the function epilogue 0x118E86C. Otherwise the replaced word and the stock code from 0x118E3E0.
  Runs only on the game that owns a 250 module (the update is owner-gated) while it is not reunited; once
  reunited, 0x118E3D8 returns before the hook. Offline: stock."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'love6_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
FUNC, FEND = 0x118E3A8, 0x118E888       # passive 250 vt+0x20
SITE, BACK, EPI = 0x118E3DC, 0x118E3E0, 0x118E86C
PAD = 0x118DC48
RESOLVE, FWD, REWARD = 0x17E7828, 0x1196938, 0x117AF0C
MGR3, WCM, SQMG = 0x5B3CE08, 0x5B3CD88, 0x5B3CE18
VT_ACTIVE, VT_PASSIVE, FUNCTOR = 0x56F7B38, 0x56F7CA8, 0x56F7E18
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def data_q(a):
    return struct.unpack_from('<Q', C.DATA, a - C.DATA_BASE)[0]


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
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


# ================================================================ code facts [V]
for a, t in (
        (0x118E3D0, 'ldr x8, [x8, #0x150]'), (0x118E3D8, 'tbnz w0, #0, #0x118e86c'),
        (SITE, 'ldr x8, [x19, #0x40]'), (BACK, 'ldp x9, x8, [x8, #0x90]'),
        (0x118E450, 'ldr x0, [x8, #0x90]'), (0x118E458, 'cbz x0, #0x118e86c'),      # part (a): +0x90 only
        (0x118EA80, 'ldp x9, x8, [x8, #0x90]'), (0x118EA88, 'csel x0, x8, x9, eq'),  # vt+0x120: +0x90 else +0x98
        # the stock send block this cave repeats
        (0x118E5A0, 'ldr x0, [x19, #0x38]'), (0x118E5A4, 'adrp x8, #0x56f7000'), (0x118E5A8, 'add x8, x8, #0xe18'),
        (0x118E5B4, 'str x26, [sp, #0x30]'), (0x118E5B8, 'mov x1, x19'), (0x118E5BC, 'stp x8, x19, [sp, #0x10]'),
        (0x118E5C0, 'bl #0x1196938'), (0x118E5D8, 'add x8, x8, #0x28'), (0x118E5E8, 'add x8, x8, #0x20'),
        (0x118E5F8, 'mov w8, #4'), (0x118E604, 'bl #0x117af0c'),
        (0x118E594, 'ldr x8, [x8, #0x150]'), (0x118E580, 'ldr x8, [x8, #0x20]'), (0x118E588, 'ldr x0, [x8, #0x10]'),
        (0x1196984, 'ldr x0, [x2, #0x20]'),                                     # functor pointer at struct+0x20
        (0x118ED10, 'ldr x8, [x0, #8]'), (0x118ED18, 'strb w9, [x8, #0x48]'),   # functor: logic+0x48 = 1
        (0x118DDD8, 'ldrb w0, [x0, #0x48]'),                                    # vt+0x150 = reunited
        (EPI, 'ldp x20, x19, [sp, #0xe0]'),
        (0x118E470, 'adrp x23, #0x5b3c000'), (0x118E474, 'add x23, x23, #0xe18'),  # SQM global
        (0x174EBB4, 'strh w8, [sp, #0x40]'), (0x174EBB8, 'bl #0x17e7828'),
        (0x15A55D4, 'adrp x9, #0x5b3c000'), (0x15A55F0, 'cmp w9, #6')):
    stock(a, t)
assert W[FUNC // 4] == PACIBSP and W[FEND // 4 - 1] != 0
assert data_q(VT_PASSIVE + 0x20) == FUNC and data_q(VT_ACTIVE + 0x150) == 0x118DDD8
assert data_q(FUNCTOR + 0x30) == 0x118ED10, 'functor call slot'
assert not targets_in(SITE, SITE + 4), 'branch into the site'
for a in range(FUNC, FEND, 4):
    assert not re.search(r'\b[xw]1[67]\b', C.dis1(a, C.text_word(a))), hex(a)
assert all(W[x // 4] == 0 for x in range(PAD, PAD + 12)) and W[0x118DC60 // 4] == PACIBSP
assert not targets_in(PAD, PAD + 12), 'padding referenced'
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(PAD, PAD + 12)), 'padding in use'
listing.append('trampoline padding 0x%X..0x%X (zero, before pacibsp 0x118DC60, unreferenced, free)' % (PAD, PAD + 12))

g = C.Gen('love6_gen', out=OUT, dry=True)
SIZE = 124
T = g.alloc('LOVE6', 'FAR_CODE', SIZE * 4, 'Love: loved one mirrors the bearer reunite (event 4 + reward 2501, LAN)')
listing.append('cave LOVE6 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)' % (T, T + SIZE * 4))


a = C.Asm(T)
a(C.stp_pre(29, 30, 31, -0x80))
a(C.add_xi(29, 31, 0))
a(C.stp_x(20, 21, 31, 0x10))
a(C.stp_x(22, 23, 31, 0x20))
a(C.stp_x(24, 25, 31, 0x30))
# LAN only
a(lambda pc, L: C.adrp(pc, 8, MGR3))
a(C.ldr_x(8, 8, C.lo12(MGR3)))
a(C.to(C.cbz_x, 'x8', 'stock'))
a(C.ldr_w(9, 8, 0x1268))
a(C.cmp_wi(9, 6))
a(C.to(C.bne, 'stock'))
# cond = root+0x90, else +0x98
a(C.ldr_x(8, 19, 0x40))
a(C.to(C.cbz_x, 'x8', 'stock'))
a(C.ldr_x(20, 8, 0x90))
a(C.to(C.cbnz_x, 'x20', 'havec'))
a(C.ldr_x(20, 8, 0x98))
a(C.to(C.cbz_x, 'x20', 'stock'))
a.label('havec')
a(C.ldr_x(22, 20, 0x58))                                   # entry count
a(C.to(C.cbz_x, 'x22', 'stock'))
a(C.cmp_xi(22, 0x11))
a(C.to(C.bhs, 'stock'))
a(C.add_xi(23, 20, 0x10))                                  # entry pointer (u32: u16 handle, flag +2, slot +3)
a.label('eloop')
a(C.ldrb(9, 23, 2))
a(C.to(C.cbz_w, 'w9', 'enext'))
a(lambda pc, L: C.adrp(pc, 8, WCM))
a(C.ldr_x(0, 8, C.lo12(WCM)))
a(C.to(C.cbz_x, 'x0', 'stock'))
a(C.ldrh(9, 23, 0))
a(C.str_w(9, 31, 0x68))                                    # {u16 handle, u16 0}
a(C.add_xi(1, 31, 0x68))
a.many(lambda pc, L: C.far_call(pc, RESOLVE))
a(C.to(C.cbz_x, 'x0', 'enext'))
a(C.ldr_x(9, 0, 0x20))
a(C.to(C.cbz_x, 'x9', 'enext'))
a(C.ldr_x(9, 9, 0x1D0))
a(C.to(C.cbz_x, 'x9', 'enext'))
a(C.ldr_w(24, 9, 0xD0))
a(C.cmp_wi(24, 100))
a(C.to(C.bhs, 'enext'))                                    # real players only: SQM id == player no
a(lambda pc, L: C.adrp(pc, 8, SQMG))
a(C.ldr_x(9, 8, C.lo12(SQMG)))
a(C.to(C.cbz_x, 'x9', 'enext'))
a(C.ldr_x(10, 9, 0x8))
a(C.ldr_x(11, 9, 0x10))
a.label('qloop')
a(C.cmp_xr(10, 11))
a(C.to(C.bhs, 'enext'))
a(C.ldr_w(12, 10, 0))
a(C.cmp_wr(12, 24))
a(C.to(C.bne, 'qnext'))
a(C.add_xi(14, 10, 8))                                     # module slots 0..2 at entry +8/+0x10/+0x18
a(C.movz_w(15, 3))
a.label('sloop')
a(C.ldr_x(12, 14, 0))
a(C.to(C.cbz_x, 'x12', 'snext'))
a(C.ldr_x(13, 12, 0x20))                                   # active holder
a(C.to(C.cbnz_x, 'x13', 'hav'))
a(C.ldr_x(13, 12, 0x28))                                   # built holder (not activated yet)
a(C.to(C.cbz_x, 'x13', 'snext'))
a.label('hav')
a(C.ldr_x(13, 13, 0x10))                                   # logic
a(C.to(C.cbz_x, 'x13', 'snext'))
a(C.ldr_x(12, 13, 0))
a.many(lambda pc, L: [C.adrp(pc, 9, VT_ACTIVE), C.add_xi(9, 9, C.lo12(VT_ACTIVE))])
a(C.cmp_xr(12, 9))
a(C.to(C.bne, 'snext'))
a(C.ldrb(12, 13, 0x48))                                    # the bearer's reunited
a(C.to(C.cbnz_w, 'w12', 'found'))
a.label('snext')
a(C.add_xi(14, 14, 8))
a(C.sub_wi(15, 15, 1))
a(C.to(C.cbnz_w, 'w15', 'sloop'))
a.label('qnext')
a(C.add_xi(10, 10, 0x20))
a(C.to(C.b, 'qloop'))
a.label('enext')
a(C.add_xi(23, 23, 4))
a(C.sub_xi(22, 22, 1))
a(C.to(C.cbnz_x, 'x22', 'eloop'))
a(C.to(C.b, 'stock'))
# ---- the stock send block 0x118E5A0..0x118E604, with the struct at sp+0x40 (functor ptr at +0x60)
a.label('found')
a(C.ldr_x(0, 19, 0x38))                                    # writer
a(C.to(C.cbz_x, 'x0', 'stock'))
a.many(lambda pc, L: [C.adrp(pc, 8, FUNCTOR), C.add_xi(8, 8, C.lo12(FUNCTOR))])
a(C.stp_x(8, 19, 31, 0x40))
a(C.add_xi(9, 31, 0x40))
a(C.str_x(9, 31, 0x60))
a(C.mov_x(1, 19))
a(C.add_xi(2, 31, 0x40))
a.many(lambda pc, L: C.far_call(pc, FWD))
a(C.ldr_x(0, 31, 0x60))
a(C.add_xi(9, 31, 0x40))
a(C.cmp_xr(0, 9))
a(C.to(C.bne, 'dheap'))
a(C.ldr_x(8, 0, 0))
a(C.ldr_x(8, 8, 0x20))
a(C.blr(8))
a(C.to(C.b, 'dd'))
a.label('dheap')
a(C.to(C.cbz_x, 'x0', 'dd'))
a(C.ldr_x(8, 0, 0))
a(C.ldr_x(8, 8, 0x28))
a(C.blr(8))
a.label('dd')
a(C.ldr_x(0, 19, 0x38))
a(C.movz_w(8, 4))
a(C.strb(8, 31, 0x70))                                     # reward type 4 (row 2501)
a(C.add_xi(1, 31, 0x70))
a.many(lambda pc, L: C.far_call(pc, REWARD))
a(C.ldp_x(24, 25, 31, 0x30))
a(C.ldp_x(22, 23, 31, 0x20))
a(C.ldp_x(20, 21, 31, 0x10))
a(C.ldp_post(29, 30, 31, 0x80))
a.many(lambda pc, L: C.far_jump(pc, EPI))                  # function epilogue (restores its own frame)
a.label('stock')
a(C.ldp_x(24, 25, 31, 0x30))
a(C.ldp_x(22, 23, 31, 0x20))
a(C.ldp_x(20, 21, 31, 0x10))
a(C.ldp_post(29, 30, 31, 0x80))
a(C.ldr_x(8, 19, 0x40))                                    # the replaced word
a.many(lambda pc, L: C.far_jump(pc, BACK))
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
for need in ('stp x29, x30, [sp, #-0x80]!', 'ldp x29, x30, [sp], #0x80', 'ldr w9, [x8, #0x1268]',
             'ldr x20, [x8, #0x90]', 'ldr x20, [x8, #0x98]', 'ldr x22, [x20, #0x58]', 'ldrb w9, [x23, #2]',
             'ldr x9, [x9, #0x1d0]', 'ldr w24, [x9, #0xd0]', 'ldr x13, [x12, #0x20]', 'ldr x13, [x12, #0x28]',
             'ldr x13, [x13, #0x10]', 'ldrb w12, [x13, #0x48]', 'stp x8, x19, [sp, #0x40]', 'str x9, [sp, #0x60]',
             'strb w8, [sp, #0x70]', 'ldr x8, [x19, #0x40]'):
    assert need in dis, need
assert dis.count('ret') == 0
for t in dis:                                              # callee-saved x20..x25 saved / restored above
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (0, 1, 2, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 24, 25, 29, 30), t

caves = g.cave('LOVE6', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LOVE6 0x%X (x16 unused in 0x118E3A8)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'ldr x8, [x19, #0x40]', C.b(SITE, PAD), 'passive 250 update part (a) -> LOVE6')]
groups = {'LOVE6_CAVE': caves + tramp, 'LOVE6': hook}
order = ['LOVE6_CAVE', 'LOVE6']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'LOVE6': 0x%X, 'TRAMP': 0x%X}\n" % (T, PAD))
