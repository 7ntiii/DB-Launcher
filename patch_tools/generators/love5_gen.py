"""love5_gen.py: Love Ephemeral late pairing at the loved one's prompt test (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes love5_live.py.
python love5_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: love5_notes.md.

REGISTRY: allocated with Gen(dry=True) (task rule: new files only); the lead adds the row when baking:
  love5_gen | LOVE5 | <printed range> | Love: late pairing of the 250 list at the prompt test (LAN)

Groups
  LOVE5_CAVE  far cave LOVE5 + a 3-word trampoline in the zero padding after 0x118E9DC.
  LOVE5       0x118EA34 `bl 0x119b2a0` (the list test of the passive 250 logic's vt+0x148 0x118E9DC, asked by the
     "Accept flowers" button code 0x19C9DCC -> 0x1183E00) -> `bl trampoline`.
  Why: the 250 class-B list is filled only by the stock pairing (match 0x11979C0 + add 0x1197C80), which runs once
  per module (+0x79) near MatchPreprocess. The add needs the partner CHR (0x17F1940 by player number, 0x1197D78);
  when the bearer's copy is not loaded yet on the loved game, the add finds nothing, +0x79 becomes 1 and nothing
  pairs again (SIGIL13 re-arms only when a NEW SQM entry appears). Live 2026-11-17: list False on the real loved
  game in every sample.
  The cave: stock test first (unchanged when it passes). When it fails, LAN only (mgr3 +0x1268 == 6): resolve the
  tested handle to its chr (0x17E7828(WCM, {u16 handle, 0}), as 0x174EBB8 does), player no = [[chr+0x20]+0x1D0]+0xD0
  (< 100: real players only), and for slot 0..2 run the STOCK match 0x11979C0(cond, &key = no*10 + slot); the first
  key that matches (the partner holds quest cond+0xCC = 240 in that slot, the stock rule byte test included) goes
  through the STOCK add 0x1197C80 (dedup by handle, flag 1, slot), then the stock test runs again and its answer is
  returned. Guards: list counts +0x58 / +0xB0 < 8 (the add asserts at 17). Only chrs the button code already asks
  about (a chr in front of the loved one) are ever added; a non-partner never matches. Offline: stock."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'love5_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
FUNC, FEND = 0x118E9DC, 0x118EA60       # passive 250 vt+0x148
SITE = 0x118EA34                        # bl #0x119b2a0
TEST, MATCH, ADD, RESOLVE = 0x119B2A0, 0x11979C0, 0x1197C80, 0x17E7828
MGR3, WCM = 0x5B3CE08, 0x5B3CD88
listing = []


def mul_w(rd, rn, rm):                  # madd wd, wn, wm, wzr
    return 0x1B007C00 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def qwords_to(t):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if x == t:
                out.append(base + 8 * i)
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
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


# ================================================================ code facts [V]
for a, t in (
        (0x118EA10, 'ldr x8, [x20, #0x40]'), (0x118EA14, 'add x0, sp, #8'), (0x118EA18, 'mov x1, x19'),
        (0x118EA1C, 'mov w2, wzr'), (0x118EA24, 'ldp x9, x8, [x8, #0x90]'), (0x118EA30, 'str x8, [sp, #8]'),
        (SITE, 'bl #0x119b2a0'), (0x118EA3C, 'and w0, w0, #1'),
        # the list test: x0 = &cond, x1 = &u16 handle, compares chr+0x20 -> +0x78
        (0x119B2BC, 'ldr x0, [x0]'), (0x119B2E8, 'ldrh w8, [x19]'), (0x119B318, 'ldrh w11, [x11, #0x78]'),
        # match: key u32 [x1] -> pgd slot quest vs cond+0xCC
        (0x11979D8, 'ldr w8, [x1]'), (0x1197AD4, 'mov w9, #0x46e0'), (0x1197B40, 'ldr w10, [x19, #0xcc]'),
        (0x1197B44, 'cmp w9, w10'),
        # add: chr by number (0x17F1940), dedup by handle, count +0x58 (< 0x11), second list +0xB0 (< 0x11)
        (0x1197C9C, 'mov x19, x0'), (0x1197CAC, 'ldr w9, [x1]'), (0x1197D78, 'bl #0x17f1940'),
        (0x1197E44, 'ldr x11, [x19, #0x58]'), (0x1197E9C, 'cmp x11, #0x11'), (0x1197EC4, 'cmp x8, #0x11'),
        (0x1197E84, 'cmp w14, w9'),
        # handle resolver call shape (0x174EBA8..0x174EBBC)
        (0x174EBAC, 'strh wzr, [sp, #0x42]'), (0x174EBB4, 'strh w8, [sp, #0x40]'), (0x174EBB8, 'bl #0x17e7828'),
        (0x174EBBC, 'cbz x0, #0x174edd4'),
        (0x15A55D4, 'adrp x9, #0x5b3c000'), (0x15A55F0, 'cmp w9, #6')):
    stock(a, t)
assert W[FUNC // 4] == PACIBSP and W[FEND // 4] == PACIBSP
assert not targets_in(SITE, SITE + 4), 'branch into the site'
vt_refs = qwords_to(FUNC)
listing.append('0x118E9DC is referenced by %d table word(s): %s' % (len(vt_refs), ' '.join('0x%X' % x for x in vt_refs)))
for a in range(FUNC, FEND, 4):
    assert not re.search(r'\b[xw]1[67]\b', C.dis1(a, C.text_word(a))), hex(a)

PAD = 0x118EA4C
assert all(W[x // 4] == 0 for x in range(PAD, FEND, 4))
assert not targets_in(PAD, FEND), 'padding referenced'
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(PAD, PAD + 12)), 'padding in use'
listing.append('trampoline padding 0x%X..0x%X (zero, before pacibsp 0x%X, unreferenced, free)' % (PAD, PAD + 12, FEND))

g = C.Gen('love5_gen', out=OUT, dry=True)
SIZE = 76
T = g.alloc('LOVE5', 'FAR_CODE', SIZE * 4, 'Love: late pairing of the 250 list at the prompt test (LAN)')
listing.append('cave LOVE5 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)' % (T, T + SIZE * 4))

a = C.Asm(T)
a(C.stp_pre(29, 30, 31, -0x40))
a(C.add_xi(29, 31, 0))
a(C.stp_x(19, 20, 31, 0x10))
a(C.stp_x(21, 22, 31, 0x20))
a(C.str_x(23, 31, 0x30))
a(C.mov_x(19, 0))                                        # x19 = &cond (caller sp+8)
a(C.mov_x(20, 1))                                        # x20 = &u16 handle
a.many(lambda pc, L: C.far_call(pc, TEST))               # stock list test (w2 = 0 from the caller)
a(C.to(C.tbnz, 'w0', 0, 'done'))
a(lambda pc, L: C.adrp(pc, 8, MGR3))
a(C.ldr_x(8, 8, C.lo12(MGR3)))
a(C.to(C.cbz_x, 'x8', 'no'))
a(C.ldr_w(9, 8, 0x1268))
a(C.cmp_wi(9, 6))
a(C.to(C.bne, 'no'))                                     # LAN only
a(C.ldr_x(21, 19, 0))                                    # cond
a(C.to(C.cbz_x, 'x21', 'no'))
a(C.ldr_x(9, 21, 0x58))
a(C.cmp_xi(9, 8))
a(C.to(C.bhs, 'no'))
a(C.ldr_x(9, 21, 0xB0))
a(C.cmp_xi(9, 8))
a(C.to(C.bhs, 'no'))
a(lambda pc, L: C.adrp(pc, 8, WCM))
a(C.ldr_x(0, 8, C.lo12(WCM)))
a(C.to(C.cbz_x, 'x0', 'no'))
a(C.ldrh(9, 20, 0))
a(C.str_w(9, 31, 0x38))                                  # {u16 handle, u16 0} (w9 upper half is 0)
a(C.add_xi(1, 31, 0x38))
a.many(lambda pc, L: C.far_call(pc, RESOLVE))
a(C.to(C.cbz_x, 'x0', 'no'))
a(C.ldr_x(9, 0, 0x20))
a(C.to(C.cbz_x, 'x9', 'no'))
a(C.ldr_x(9, 9, 0x1D0))
a(C.to(C.cbz_x, 'x9', 'no'))
a(C.ldr_w(22, 9, 0xD0))
a(C.cmp_wi(22, 100))
a(C.to(C.bhs, 'no'))                                     # -1 / bots / garbage: no
a(C.movz_w(9, 10))
a(mul_w(22, 22, 9))                                      # key base = no * 10
a(C.movz_w(23, 0))                                       # slot
a.label('loop')
a(C.add_wr(9, 22, 23))
a(C.str_w(9, 31, 0x3C))
a(C.mov_x(0, 21))
a(C.add_xi(1, 31, 0x3C))
a.many(lambda pc, L: C.far_call(pc, MATCH))
a(C.to(C.tbnz, 'w0', 0, 'add'))
a(C.add_wi(23, 23, 1))
a(C.cmp_wi(23, 3))
a(C.to(C.blo, 'loop'))
a(C.to(C.b, 'no'))
a.label('add')
a(C.mov_x(0, 21))
a(C.add_xi(1, 31, 0x3C))
a.many(lambda pc, L: C.far_call(pc, ADD))
a(C.mov_x(0, 19))
a(C.mov_x(1, 20))
a(C.movz_w(2, 0))
a.many(lambda pc, L: C.far_call(pc, TEST))               # stock test again: its answer is returned
a(C.to(C.b, 'done'))
a.label('no')
a(C.movz_w(0, 0))
a.label('done')
a(C.ldr_x(23, 31, 0x30))
a(C.ldp_x(21, 22, 31, 0x20))
a(C.ldp_x(19, 20, 31, 0x10))
a(C.ldp_post(29, 30, 31, 0x40))
a(C.RET)
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
for need in ('stp x29, x30, [sp, #-0x40]!', 'ldp x29, x30, [sp], #0x40', 'ret', 'ldr w9, [x8, #0x1268]',
             'ldr x9, [x21, #0x58]', 'ldr x9, [x21, #0xb0]', 'ldr x9, [x9, #0x1d0]', 'ldr w22, [x9, #0xd0]',
             'mul w22, w22, w9', 'ldrh w9, [x20]', 'str w9, [sp, #0x38]', 'str w9, [sp, #0x3c]'):
    assert need in dis, need
for t in dis:                                            # callee-saved x19..x23 are saved / restored above
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (0, 1, 2, 8, 9, 16, 19, 20, 21, 22, 23, 29, 30), t

caves = g.cave('LOVE5', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LOVE5 0x%X (x16 unused in 0x118E9DC)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'bl #0x119b2a0', C.bl(SITE, PAD), 'passive 250 list test -> LOVE5 (late pairing)')]
groups = {'LOVE5_CAVE': caves + tramp, 'LOVE5': hook}
order = ['LOVE5_CAVE', 'LOVE5']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'LOVE5': 0x%X, 'TRAMP': 0x%X}\n" % (T, PAD))
