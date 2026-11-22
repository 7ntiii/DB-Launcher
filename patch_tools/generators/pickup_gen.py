"""pickup_gen.py: every world-item pick-up award from the host is added to the LOCAL picker's inventory in a LAN
match, through the game's own (offline) add branch 0x15B57FC (static generator). Reads nso/*.bin, patch_manager.cpp
and every *_live.py (through cave_lib). Writes pickup_live.py and claims its far range in cave_registry.md (owner
`pickup_gen`).
python pickup_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: pickup_notes.md (section 4 = this group).

Groups
  PICKUP_ADD_CAVE  far cave ADD and its 3-word trampoline in the zero padding 0x1597270..0x159727B (after
                   STARFRAG_PICK's 3 words; NEAR_TRAMP is full). Inert until PICKUP_ADD points the site at it.
  PICKUP_ADD       one site word:
     0x15B555C  give 0x15B5400, `ldr x8, [x8]` (online world singleton, tested by 0x15B5560) -> ADD: re-runs the load,
                then sets x8 = 0 (-> the stock add branch 0x15B57FC: inventory add, new mark, the same notice) ONLY when
                  - world set and offline byte +0xBDA == 0 (LAN match);
                  - receiving chr x19 == local player chr *(main+0x5B3CD88)+0x1A8;
                  - 0x15B5400 called by 0x15A5020 (LR 0x15A5184 / 0x15A51DC) and 0x15A5020 by the subtype-6 award
                    reader (LR 0x15981BC);
                  - the award message is NOT an ITEMAUTH_GIVE gift (marker 'IGIV' at reader sp+0x4D8 = reader
                    x29-0x2A8): a gift is added by G7 / 0xCF8E2C and must not be added twice.
                Else x8 stays as loaded (stock).
  REPLACES STARFRAG_PICK (same site word 0x15B555C, superset of its test): apply PICKUP_ADD *or* STARFRAG_PICK, never
  both. Coexists with POWERS_PICK (its GIVE hook 0x15B5560 starts with `cbz x8`, so x8 == 0 -> add as well)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'pickup_live.py'
ALT = 'starfrag_pick_live.py'           # the exclusive alternative on the same site word
SITE = 0x15B555C
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G = 0x5B65C20, 0x5B3CD88
RET_GIVE = (0x15A5184, 0x15A51DC)       # 0x15A5020's two `bl 0x15b5400`, +4
RET_AWARD = 0x15981BC                   # subtype-6 award reader `bl 0x15a5020`, +4
MARKER = 0x56494749                     # 'IGIV' (ITEMAUTH_GIVE G1 message +0x188 = reader sp+0x4D8)
READER, READER_FRAME = 0x1597280, 0x780 # reader x29 = final sp + 0x780
MARK_OFF = READER_FRAME - 0x4D8         # marker at reader x29 - 0x2A8
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def fn_end(a):
    a += 4
    while W[a // 4] != PACIBSP:
        a += 4
    return a


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
GIVE_FN = 0x15B5400
assert fn_end(GIVE_FN) == 0x15B5C80
assert not [a for a in range(GIVE_FN, 0x15B5C80, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
# every caller of 0x15B5400 / 0x15A5020 (the notes say per caller whether it is covered)
GIVE_CALLERS = sorted(bl_callers(GIVE_FN))
assert GIVE_CALLERS == [0x15A5180, 0x15A51D8, 0x15B7F64], [hex(x) for x in GIVE_CALLERS]
AWARD_CALLERS = sorted(bl_callers(0x15A5020))
assert AWARD_CALLERS == [0x15981B8, 0x159AA94, 0x159D9C0, 0x15A44F8, 0x15A4CCC, 0x15AEE18, 0x15AF670], \
    [hex(x) for x in AWARD_CALLERS]
listing.append('0x15B5400 callers %s; 0x15A5020 callers %s (only 0x15981B8 is let through)' % (
    [hex(x) for x in GIVE_CALLERS], [hex(x) for x in AWARD_CALLERS]))
for a, t in ((0x15B5408, 'stp x29, x30, [sp, #0x150]'), (0x15B5420, 'add x29, sp, #0x150'),
             (0x15B5424, 'mov x19, x7'), (0x15B5458, 'cbnz x19, #0x15b5474'), (0x15B546C, 'ldr x19, [x8, #0x1a8]'),
             (0x15A5028, 'stp x29, x30, [sp, #0x70]'), (0x15A5040, 'add x29, sp, #0x70'),
             (0x15A5180, 'bl #0x15b5400'), (0x15A51D8, 'bl #0x15b5400'),
             (0x15981B8, 'bl #0x15a5020'), (0x15981B4, 'mov x5, x26'), (0x159795C, 'bl #0x17f1940'),
             (0x15978D4, 'ldr w8, [sp, #0x398]'), (0x15978F4, 'ldr w8, [sp, #0x4d0]'), (0x1598140, 'bl #0x15a4de0'),
             # reader frame: x29 = entry sp - 0xA0 + 0x40, then sub sp, 0x740 -> x29 = sp + 0x780
             (0x1597284, 'stp d15, d14, [sp, #-0xa0]!'), (0x1597294, 'stp x29, x30, [sp, #0x40]'),
             (0x1597298, 'add x29, sp, #0x40'), (0x15972B0, 'sub sp, sp, #0x740'),
             # site
             (0x15B5550, 'adrp x8, #0x5b57000'), (0x15B5554, 'add x8, x8, #0xe90'), (0x15B5558, 'ldur w27, [x29, #-0x50]'),
             (SITE, 'ldr x8, [x8]'), (0x15B5560, 'cbz x8, #0x15b57fc'), (0x15B5564, 'ldur x11, [x29, #-0x20]'),
             (0x15B5568, 'cbnz x11, #0x15b5578'), (0x15B5570, 'bl #0xcd57c0'), (0x15B5578, 'ldur x9, [x29, #-0x40]'),
             (0x15B5580, 'ands x10, x11, #0x1ff'), (0x15B57FC, 'ldr w2, [x21, #4]'), (0x15B581C, 'bl #0x15a2820')):
    stock(a, t)
assert READER_FRAME == 0x40 + 0x740             # x29 = (entry sp - 0xA0) + 0x40; sp = entry sp - 0xA0 - 0x740
# the reader's sp is not moved again between its prologue and the award call (no other sp arithmetic)
_sp = [a for a in range(0x15972B4, 0x15981BC, 4) if re.match(r'(add|sub) sp, sp', C.dis1(a, W[a // 4]))]
assert not _sp, [hex(x) for x in _sp]
# G1 marker offset: G2 compares [sp+0x4d8] with 'IGIV' at 0x15978D4 time [V itemauth_live G2 words]
try:
    import itemauth_live as IA
    g2 = {a: int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in IA.ITEMAUTH_GIVE}
    assert C.dis1(0xC500BA4, g2[0xC500BA4]) == 'ldr w9, [sp, #0x4d8]'
    assert C.dis1(0xC500BA8, g2[0xC500BA8]) == 'mov w10, #0x4749' and C.dis1(0xC500BAC, g2[0xC500BAC]) == 'movk w10, #0x5649, lsl #16'
    listing.append('ITEMAUTH_GIVE G2 marker test [sp+0x4d8] == 0x%X (asserted): gifts excluded' % MARKER)
except ImportError:
    listing.append('itemauth_live.py not found: marker constant kept as designed')
assert targets_in(SITE, SITE + 4) == []
assert not [a for a in range(0x15B5474, SITE, 4) if re.match(r'\S+ (x19|w19)\b', C.dis1(a, W[a // 4]))
            and not C.dis1(a, W[a // 4]).startswith(('str', 'stp', 'cmp', 'cbz', 'cbnz', 'tbz', 'tbnz'))]
# x9 / x10 / x11 / flags written before read on both continuations of 0x15B5560 (stock word or POWERS GIVE)
for a in list(range(0x15B5564, 0x15B5578, 4)) + list(range(0x15B57FC, 0x15B581C, 4)):
    t = C.dis1(a, W[a // 4])
    assert not re.search(r'\b[xw](9|10)\b', t), 'x9/x10 at %x' % a
    # x11: the 0x15B5564 path writes it first (`ldur x11` at 0x15B5564); the 0x15B57FC path must not name it
    assert a < 0x15B57FC or not re.search(r'\b[xw]11\b', t), 'x11 at %x: %s' % (a, t)
for a in (0x15B5578, 0x15B557C):
    assert not re.search(r'\b[xw]10\b', C.dis1(a, W[a // 4]))
for a in range(SITE, 0x15B5564):
    assert a not in C.SHIPPED
try:
    import powers_pick_live as PP
    gv = PP.CAVES['GIVE']
    gw = [int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in PP.POWERS_PICK_CAVE if a == gv][0]
    assert C.dis1(gv, gw).startswith('cbz x8, ')
    assert not [1 for a, o, n, c in PP.POWERS_PICK_CAVE if a == gv + 4 and 'x11' in C.dis1(a, int.from_bytes(bytes.fromhex(n), 'little'))]
    listing.append('POWERS_PICK GIVE 0x%X starts with `cbz x8`: x8 == 0 -> add (coexists)' % gv)
except ImportError:
    pass

PAD = 0x1597270
for a in range(0x1597264, 0x1597280, 4):
    stock(a, 'udf #0')
assert W[0x1597280 // 4] == PACIBSP
assert not targets_in(PAD, 0x1597280) and not qwords_in(PAD, 0x1597280)
assert C.reach(SITE, PAD)

# ================================================================ cave
g = C.Gen('pickup_gen', out=OUT, dry=DRY)
# PICKUP_ADD and STARFRAG_PICK are exclusive alternatives for the SAME site word: let only that word through the
# collision check (every other byte of the alternative stays protected).
for i in range(4):
    if SITE + i in g.others:
        assert g.others[SITE + i] == ALT, 'site %x held by %s' % (SITE, g.others[SITE + i])
        del g.others[SITE + i]
listing.append('site 0x%X is shared ONLY with %s (exclusive alternative, not both)' % (SITE, ALT))
SIZE = 56
T_ADD = g.alloc('ADD', 'FAR_CODE', SIZE * 4, 'give 0x15B555C: host pick-up award for the local player -> add')


def movw32(a, r, v):
    a(C.movz_w(r, v & 0xFFFF))
    a(C.movk_w(r, v >> 16, 1))


SUB_W9_W10 = 0x4B0A0129
assert C.dis1(0, SUB_W9_W10) == 'sub w9, w9, w10'
a = C.Asm(T_ADD)
a(C.ldr_x(8, 8, 0))                                         # the replaced word
a(C.to(C.cbz_x, 'x8', 'back'))
a(lambda pc, L: C.adrp(pc, 9, OFFL))
a(C.ldr_x(9, 9, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x9', 'back'))
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'back'))                             # offline: stock
a(lambda pc, L: C.adrp(pc, 9, WCM_G))
a(C.ldr_x(9, 9, C.lo12(WCM_G)))
a(C.to(C.cbz_x, 'x9', 'back'))
a(C.ldr_x(9, 9, 0x1A8))
a(C.cmp_xr('x9', 'x19'))
a(C.to(C.bne, 'back'))                                      # award for another chr: stock
a(C.ldr_x(9, 29, 8))                                        # 0x15B5400's LR
a(lambda pc, L: C.adrp(pc, 10, 0))
a(SUB_W9_W10)
movw32(a, 10, RET_GIVE[0])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.beq, 'lvl2'))
movw32(a, 10, RET_GIVE[1])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))                                      # dialog OK (0x15B7F68) / POWERS PICK cave: stock
a.label('lvl2')
a(C.ldr_x(11, 29, 0))                                       # 0x15A5020's x29
a(C.to(C.cbz_x, 'x11', 'back'))
a(C.ldr_x(9, 11, 8))                                        # 0x15A5020's LR
a(lambda pc, L: C.adrp(pc, 10, 0))
a(SUB_W9_W10)
movw32(a, 10, RET_AWARD)
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))                                      # any other 0x15A5020 caller: stock
a(C.ldr_x(11, 11, 0))                                       # reader's x29
a(C.to(C.cbz_x, 'x11', 'back'))
a(C.sub_xi(11, 11, MARK_OFF))
a(C.ldr_w(9, 11, 0))                                        # message +0x188
movw32(a, 10, MARKER)
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.beq, 'back'))                                      # ITEMAUTH_GIVE gift: G7 adds it, stay notice-only
a(C.mov_x(8, 'xzr'))                                        # -> 0x15B5560 takes the add branch 0x15B57FC
a.label('back')
a.many(lambda pc, L: C.far_return(pc, 0x15B5560))
add = a
assert len(add.words()) <= SIZE, len(add.words())
caves = g.cave('ADD', T_ADD, add)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> ADD 0x%X (x16 never named in 0x15B5400)' % T_ADD)
         for k, w in enumerate(C.far_jump(PAD, T_ADD))]
hook = [g.text_patch(SITE, 'ldr x8, [x8]', C.b(SITE, PAD), 'PICKUP_ADD (host pick-up award -> add)')]

groups = {'PICKUP_ADD_CAVE': caves + tramp, 'PICKUP_ADD': hook}
order = ['PICKUP_ADD_CAVE', 'PICKUP_ADD']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0] +
                 'REPLACES STARFRAG_PICK (same site 0x15B555C): apply one of the two, never both.')
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'ADD': 0x%X, 'TRAMP': 0x%X}\nEXCLUSIVE_WITH = ['STARFRAG_PICK']\n" % (T_ADD, PAD))
    for name in order:
        d, r = C.cpp_rows(name, groups[name])
        print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
