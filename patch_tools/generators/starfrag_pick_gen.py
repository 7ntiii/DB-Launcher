"""starfrag_pick_gen.py: a picked-up Star Fragment is added to the LOCAL picker's inventory in a LAN match (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py (through cave_lib). Writes starfrag_pick_live.py
and claims its far range in cave_registry.md (owner `starfrag_pick_gen`).
python starfrag_pick_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: starfrag3_notes.md.

Groups
  STARFRAG_PICK_CAVE  far cave FRAG and its 3-word trampoline in the inter-function zero padding 0x1597264..0x159726F
                      (NEAR_TRAMP is full). Inert until STARFRAG_PICK points the site at it.
  STARFRAG_PICK       one site word:
     0x15B555C  give 0x15B5400, `ldr x8, [x8]` (x8 = *(main+0x5B57E90), the online world singleton, tested by the
                next word 0x15B5560 `cbz x8, #0x15b57fc`) -> FRAG: re-runs the load, then sets x8 = 0 (so the next
                word takes the stock inventory-add branch 0x15B57FC instead of the popup-only branch 0x15B5564) ONLY
                when ALL of these hold, else x8 is left as loaded (stock):
                  - world singleton set (a match) and offline byte +0xBDA == 0 (LAN);
                  - the entry id (w27, loaded at 0x15B5558) == 0x20009C40 (accessory 40000, Star Fragment);
                  - the receiving chr (x19) == the local player chr *(main+0x5B3CD88)+0x1A8;
                  - 0x15B5400 was called by 0x15A5020 (return 0x15A5184 / 0x15A51DC) and 0x15A5020 by the subtype-6
                    award reader (return 0x15981BC): an award the item authority (host) sent for a take.
                Works with or without POWERS_PICK: its GIVE hook at 0x15B5560 also sends x8 == 0 to 0x15B57FC.
  SUPERSEDED BY PICKUP_ADD (pickup_live.py, pickup_notes.md 4): same site word 0x15B555C, every item kind.
  Apply STARFRAG_PICK *or* PICKUP_ADD, never both (the second apply would find the other's word at the site)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'starfrag_pick_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G = 0x5B65C20, 0x5B3CD88
FRAG_ID = 0x20009C40                    # accessory 40000 (type nibble 2) [V starfrag notes / starfrag.py]
RET_GIVE = (0x15A5184, 0x15A51DC)       # 0x15A5020's two `bl 0x15b5400`, +4
RET_AWARD = 0x15981BC                   # subtype-6 award reader `bl 0x15a5020`, +4
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
# frames: 0x15B5400 x29 = sp+0x150 holding {x29, x30}; 0x15A5020 x29 = sp+0x70 holding {x29, x30}
for a, t in ((0x15B5408, 'stp x29, x30, [sp, #0x150]'), (0x15B5420, 'add x29, sp, #0x150'),
             (0x15B5424, 'mov x19, x7'), (0x15B5458, 'cbnz x19, #0x15b5474'), (0x15B546C, 'ldr x19, [x8, #0x1a8]'),
             (0x15A5028, 'stp x29, x30, [sp, #0x70]'), (0x15A5040, 'add x29, sp, #0x70'),
             (0x15A5180, 'bl #0x15b5400'), (0x15A51D8, 'bl #0x15b5400'),
             (0x15981B8, 'bl #0x15a5020'), (0x15981B4, 'mov x5, x26'), (0x159795C, 'bl #0x17f1940'),
             (0x15978D4, 'ldr w8, [sp, #0x398]'), (0x1598120, 'cmp w8, #2'), (0x1598140, 'bl #0x15a4de0'),
             # the site and its neighbourhood
             (0x15B5550, 'adrp x8, #0x5b57000'), (0x15B5554, 'add x8, x8, #0xe90'), (0x15B5558, 'ldur w27, [x29, #-0x50]'),
             (0x15B555C, 'ldr x8, [x8]'), (0x15B5560, 'cbz x8, #0x15b57fc'), (0x15B5564, 'ldur x11, [x29, #-0x20]'),
             (0x15B5568, 'cbnz x11, #0x15b5578'), (0x15B5570, 'bl #0xcd57c0'), (0x15B5578, 'ldur x9, [x29, #-0x40]'),
             (0x15B5580, 'ands x10, x11, #0x1ff'), (0x15B57FC, 'ldr w2, [x21, #4]'), (0x15B5800, 'and w8, w27, #0xfffffff'),
             (0x15B581C, 'bl #0x15a2820')):
    stock(a, t)
assert sorted(bl_callers(GIVE_FN)) and set(r - 4 for r in RET_GIVE) <= set(bl_callers(GIVE_FN))
assert targets_in(0x15B555C, 0x15B5560) == []          # nothing branches to the site word itself
# x19 (receiving chr) is not rewritten between its last set (0x15B5424 / 0x15B546C) and the site
assert not [a for a in range(0x15B5474, 0x15B555C, 4) if re.match(r'\S+ (x19|w19)\b', C.dis1(a, W[a // 4]))
            and not C.dis1(a, W[a // 4]).startswith(('str', 'stp', 'cmp', 'cbz', 'cbnz', 'tbz', 'tbnz'))]
# x9 / x10 / flags written before read on every continuation of 0x15B5560 (stock word or POWERS_PICK GIVE) up to a bl
for a in list(range(0x15B5564, 0x15B5578, 4)) + list(range(0x15B57FC, 0x15B581C, 4)):
    assert not re.search(r'\b[xw](9|10)\b', C.dis1(a, W[a // 4])), 'x9/x10 at %x' % a
for a in (0x15B5578, 0x15B557C):
    assert not re.search(r'\b[xw]10\b', C.dis1(a, W[a // 4]))
for a in range(0x15B555C, 0x15B5560 + 4):
    assert a not in C.SHIPPED, 'site shipped'
# POWERS_PICK's GIVE (if applied) starts with `cbz x8, add`: x8 == 0 goes to 0x15B57FC there too [V powers_pick_live]
try:
    import powers_pick_live as PP
    gv = PP.CAVES['GIVE']
    gw = [int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in PP.POWERS_PICK_CAVE if a == gv][0]
    assert C.dis1(gv, gw).startswith('cbz x8, '), C.dis1(gv, gw)
    listing.append('POWERS_PICK GIVE 0x%X starts with `%s`: x8 == 0 -> inventory add, same as stock' % (gv, C.dis1(gv, gw)))
except ImportError:
    listing.append('powers_pick_live.py not found: only the stock word at 0x15B5560 checked')

# trampoline: zero padding after `b #0x49276b0` (tail call) before the next pacibsp (0x1597280 = award reader)
PAD = 0x1597264
stock(PAD - 4, 'b #0x49276b0')
assert W[0x1597280 // 4] == PACIBSP
for a in range(PAD, 0x1597280, 4):
    stock(a, 'udf #0')
assert not targets_in(PAD, 0x1597280) and not qwords_in(PAD, 0x1597280)
assert C.reach(0x15B555C, PAD)
listing.append('trampoline padding 0x%X..0x%X (3 of 7 zero words): no branch / adr / literal / data pointer into '
               'it, no shipped or live record (asserted)' % (PAD, PAD + 12))

# ================================================================ cave
g = C.Gen('starfrag_pick_gen', out=OUT, dry=DRY)
# PICKUP_ADD (pickup_live.py) is the exclusive alternative on the same site word: only that word may be shared
for _i in range(4):
    if 0x15B555C + _i in g.others:
        assert g.others[0x15B555C + _i] == 'pickup_live.py', g.others[0x15B555C + _i]
        del g.others[0x15B555C + _i]
SIZE = 44
T_FRAG = g.alloc('FRAG', 'FAR_CODE', SIZE * 4, 'give 0x15B555C: Star Fragment award for the local player -> add')


def movw32(a, r, v):
    a(C.movz_w(r, v & 0xFFFF))
    a(C.movk_w(r, v >> 16, 1))


def ret_off(a, src_reg):
    """w9 = low 32 bits of the saved LR at [src_reg + 8] minus main base (PAC signs only the high bits)."""
    a(C.ldr_x(9, src_reg, 8))
    a(lambda pc, L: C.adrp(pc, 10, 0))
    a(0x4B0A0129)                                           # sub w9, w9, w10


assert C.dis1(0, 0x4B0A0129) == 'sub w9, w9, w10'
a = C.Asm(T_FRAG)
a(C.ldr_x(8, 8, 0))                                         # the replaced word
a(C.to(C.cbz_x, 'x8', 'back'))                              # no world: stock (offline add follows anyway)
movw32(a, 9, FRAG_ID)
a(C.cmp_wr('w27', 'w9'))
a(C.to(C.bne, 'back'))
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
a(C.to(C.bne, 'back'))                                      # not the local player: stock
ret_off(a, 29)                                              # 0x15B5400's caller
movw32(a, 10, RET_GIVE[0])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.beq, 'lvl2'))
movw32(a, 10, RET_GIVE[1])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))
a.label('lvl2')
a(C.ldr_x(9, 29, 0))                                        # 0x15A5020's frame
a(C.to(C.cbz_x, 'x9', 'back'))
a(C.mov_x(10, 9))
a(C.ldr_x(9, 10, 8))
a(lambda pc, L: C.adrp(pc, 10, 0))
a(0x4B0A0129)
movw32(a, 10, RET_AWARD)
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))
a(C.mov_x(8, 'xzr'))                                        # -> 0x15B5560 takes the inventory-add branch
a.label('back')
a.many(lambda pc, L: C.far_return(pc, 0x15B5560))
frag = a
assert len(frag.words()) <= SIZE, len(frag.words())
caves = g.cave('FRAG', T_FRAG, frag)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> FRAG 0x%X (x16 never named in 0x15B5400)' % T_FRAG)
         for k, w in enumerate(C.far_jump(PAD, T_FRAG))]
hook = [g.text_patch(0x15B555C, 'ldr x8, [x8]', C.b(0x15B555C, PAD), 'STARFRAG_PICK (fragment award -> add)')]

groups = {'STARFRAG_PICK_CAVE': caves + tramp, 'STARFRAG_PICK': hook}
order = ['STARFRAG_PICK_CAVE', 'STARFRAG_PICK']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0])
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'FRAG': 0x%X, 'TRAMP': 0x%X}\nFRAG_ID = 0x%X\n" % (T_FRAG, PAD, FRAG_ID))
    for name in order:
        d, r = C.cpp_rows(name, groups[name])
        print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
