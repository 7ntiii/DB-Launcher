"""itemauth_gen.py: the four item-authority callers of the item add 0xCF8E2C (itemgrant_notes.md section 1),
re-verified instruction by instruction, plus the one fix that is verifiable. Static only: reads nso/*.bin,
gameparam_nt, patch_manager.cpp, every *_live.py and cave_registry.md (claims through cave_lib, owner
itemauth_gen, stable on re-runs); writes itemauth_live.py; prints a capstone listing.
    python itemauth_gen.py [--dry]        (run from diag/net)       Notes: itemauth_notes.md

  ITEMAUTH_DROP     BUILT. Player death during a shooting-star event (1210): the authority drops the dead
                    player's Star Fragments as world items (0x15B4320, 0x1E subtype 0x13) and then removes them
                    from the dropper with 0xCF8E2C (ret 0x15B4AA0), which the +0xBDA gate refuses in LAN:
                    the fragments are on the ground AND still in the inventory = DUPLICATION.
                    D1 hook 0xCF8F70 (the flag load right before the gate 0xCF8F74): offline unchanged; LAN: when
                       0xCF8E2C's return offset is in ITEMAUTH_TABLE and the receiving player [x19] is this game's
                       own player, w8 = 1, so the gate (stock, FORGE_OWN or ZEP3_C2: all `cbnz w8 -> grant`) lets
                       it through. Everything else unchanged.
                    D2 hook 0x15B4430 (after the dropper chr lookup in 0x15B4320): offline unchanged; LAN: a
                       dropper that is not this game's own player is skipped (no world item, no removal) - the
                       authority only holds a copy of that inventory and cannot remove from the real one.
  ITEMAUTH_GIVE     BUILT (itemauth2_notes.md). Placement-2 enemy lots (Fire Flask 4260, Bastard's Heart 4470,
                    Virtue (1) 8000) are rolled on the authority and given to chr(rec+0xC)+0x114's player through
                    0x15A3340 -> 0xCF8E2C = refused in LAN = lost for everybody.
                    G1 hook 0x159CB44 (bl 0x15A3340, authority only by ITEMS I3): offline unchanged; LAN: broadcast a
                       subtype-6 award (0x190 B: the record, the bonus-adjusted list, taker = that player number,
                       marker 'IGIV' at +0x188) instead of the refused add.
                    G2 hook 0x15978D4 (first word of the 0x1E reader's subtype-6 case, every game): offline or no
                       marker -> unchanged; marked: taker == own player -> G7, else next message (no copy is
                       ever touched).
                    G7 (itemauth3_notes.md): the award block 0x15978F4 -> 0x15A5020 -> 0x15B5400 is only the
                       "item got" popup in a match (no inventory add), so G7 first runs the stock give
                       0x15A3340(own player, list, 1, rec+0x28 bit 23, 0) on the taker's own game - D1 passes its
                       0xCF8E2C (ret 0x15A34AC, ITEMAUTH_TABLE) for the own player only - then the popup.
                       GIVE therefore needs ITEMAUTH_DROP (D1 + table) applied too.
  ITEMAUTH_LOT      EMPTY on purpose (notes 2.2, itemauth2_notes.md 4): no caller family is verifiable here; the
                    two death-handler ones have no data.
  ITEMAUTH_PICKONE  EMPTY on purpose (notes 2.3): UNREACHABLE with the shipped ITEMS (cave_m6a answers every mode-6
                    take before the pending list +0x330 is filled)."""
import array
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'itemauth_live.py'
DRY = '--dry' in sys.argv
g = C.Gen('itemauth_gen', out=OUT, dry=DRY)
W = array.array('I')
W.frombytes(C.TXT[:len(C.TXT) // 4 * 4])
PARAMS = os.path.join(HERE, '..', 'scripts_decoded', 'param', 'gameparam', 'gameparam_nt.parambnd')
L = g.listing

# ---------------------------------------------------------------- globals [V, same as zep3_gen / items]
OFFL = 0x5B65C20      # *(OFFL)+0xBDA != 0: offline
GDM = 0x5B57EB8       # *(GDM)+0x20 = local pgd, +0xD0 = player number
ITEM_ADD = 0xCF8E2C
GATE_LOAD, GATE = 0xCF8F70, 0xCF8F74
RET = {'GIVE': 0x15A34AC, 'LOT': 0x15AF62C, 'PICKONE': 0x15B2648, 'DROP': 0x15B4AA0}


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'at %x: %s, expected %s' % (a, got, t)


def fn_start(a):
    while W[a // 4] != 0xD503237F:
        a -= 4
    return a


def fn_end(s):
    a = s + 4
    while W[a // 4] != 0xD503237F:
        a += 4
    return a


def no_ip(s, e):
    """No word in [s, e) names x16/x17/w16/w17."""
    for a in range(s, e, 4):
        t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
        assert not re.search(r'\b[xw]1[67]\b', t), 'x16/x17 used at %x: %s' % (a, t)


def bl_callers(t):
    out = []
    for i, w in enumerate(W):
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == t:
                out.append(4 * i)
    return out


def param_rows(name):
    b = open(os.path.join(PARAMS, name), 'rb').read()
    n = struct.unpack_from('<H', b, 0xA)[0]
    return b, [struct.unpack_from('<ixxxxq', b, 0x40 + k * 24) for k in range(n)]


# ================================================================ common facts [V]
callers = bl_callers(ITEM_ADD)
for k, r in RET.items():
    assert r - 4 in callers, '%s: %x is not a call of 0xCF8E2C' % (k, r - 4)
    stock(r - 4, 'bl #0xcf8e2c')
# the gate block: flag load + gate; x19 = x1 (&player no) of 0xCF8E2C (mov x19, x1 at 0xCF8E70, not rewritten
# before 0xCF8F74 on the only two ways in, 0xCF8ECC / 0xCF8EDC - same proof as zep3_gen W1)
stock(0xCF8F68, 'adrp x8, #0x5b65000'); stock(0xCF8F6C, 'ldr x8, [x8, #0xc20]')
stock(GATE_LOAD, 'ldrb w8, [x8, #0xbda]'); stock(GATE, 'cbz w8, #0xcf8fe4')
stock(0xCF8E70, 'mov x19, x1'); stock(0xCF8E30, 'stp x29, x30, [sp, #-0x60]!'); stock(0xCF8E38, 'mov x29, sp')
FS, FE = ITEM_ADD, fn_end(ITEM_ADD)
no_ip(FS, FE)
for a in list(range(0xCF8E74, 0xCF8EE0, 4)) + list(range(0xCF8F68, GATE, 4)):
    assert not re.search(r'^\w+ (x19|w19),', C.dis1(a, W[a // 4])), 'x19 written at %x' % a
stock(0xCF8ECC, 'cbz x8, #0xcf8f68'); stock(0xCF8EDC, 'b.hi #0xcf8f68'); stock(0xCF8F64, 'b #0xcf92b0')
for a in range(FS, FE, 4):          # the only branches into the gate block are 0xCF8ECC / 0xCF8EDC
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    if re.search(r'#0xcf8f(68|6c|70|74)\b', t):
        assert a in (0xCF8ECC, 0xCF8EDC), 'other branch into the gate block at %x: %s' % (a, t)
# what the gate word holds today: stock / FORGE_OWN / ZEP3_C2 - every version starts `cbnz w8 -> grant`
shipped_gate = C.dis1(GATE, C.shipped_word(GATE))
L.append('gate 0xCF8F74 shipped word: %s (FORGE_OWN / ZEP3_C2 tramp; both caves begin `cbnz w8, grant`)' % shipped_gate)
import zep3_live as Z  # noqa: E402  (data file)
_z = {a: int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in Z.ZEP3_C2}
assert C.dis1(Z.CAVES['C2'], _z[Z.CAVES['C2']]).startswith('cbnz w8, '), 'ZEP3_C2 no longer starts cbnz w8'
assert C.dis1(0xCF0E84, C.shipped_word(0xCF0E84)) == 'cbnz w8, #0xcf8f78', 'FORGE_OWN cave changed'
for tname in ('C2_TABLE', 'C2_LOCAL'):
    a, words = Z.CAVES[tname], []
    while _z.get(a, 0):
        words.append(_z[a])
        a += 4
    assert not set(words) & set(RET.values()), 'zep3 %s already holds an item-authority offset' % tname
    L.append('zep3 %s = %s (none of the four)' % (tname, ', '.join('0x%X' % w for w in words)))
# guests drop c->s subtypes 8 and 0x13 (cave_f: role != 0 -> table byte +4 must be 1): only the authority runs
# 0x15B21A0 / 0x15B4320 in LAN
SUBT = 0x4C4CC18
stock(0x159733C, 'adrp x20, #0x4c4c000'); stock(0x1597340, 'add x20, x20, #0xc18')
stock(0x1597404, 'add x12, x20, x9, lsl #3'); stock(0x1597408, 'ldrb w12, [x12, #4]')
for st, size in ((8, 0x10), (0x13, 0x1C), (6, 0x190), (5, 0x10)):
    w, fl = struct.unpack_from('<IB', C.RO, SUBT + 8 * st - C.RO_BASE)
    assert w == size and fl == (1 if st == 6 else 0), 'subtype %x table %x/%d' % (st, w, fl)
cf = [C.dis1(a, C.shipped_word(a)) for a in range(0x563E500, 0x563E51C, 4)]
assert cf[3] == 'ldrb w12, [x12, #0xfd8]' and cf[4] == 'cbnz w12, #0x563e518' and cf[6] == 'b #0x1597404', cf
L.append('cave_f: guests accept only subtypes with byte +4 = 1; 8 and 0x13 have 0 -> authority only')

# ================================================================ DROP (0x15B4320, ret 0x15B4AA0) [V]
# sender 0x15AAC68 (only from the chr virtual 0x17B4600 = vtable 0x572C790 slot +0x4C0), called by the death
# handler 0x1752400 at 0x17529F0 for every dying chr of that class; message {0x00130001, handle, player no,
# pos, flags}; I1 (shipped) broadcasts it, only the authority keeps it (above)
assert bl_callers(0x15AAC68) == [0x17B4678] and fn_start(0x17B4678) == 0x17B4600
assert struct.unpack_from('<Q', C.DATA, 0x572CC50 - C.DATA_BASE)[0] == 0x17B4600 and 0x572CC50 - 0x4C0 == 0x572C790
stock(0x17529F0, 'ldr x8, [x8, #0x4c0]'); stock(0x17529F4, 'blr x8')
stock(0x15AACA4, 'ldr w8, [x8, #0xd0]'); stock(0x15AACA8, 'str w8, [sp, #0x1c]')   # player no of the dropper
stock(0x15AAD2C, 'cbz w9, #0x15aad4c'); stock(0x15AAD44, 'bl #0x15b4320')           # offline: local call
assert sorted(bl_callers(0x15B4320)) == [0x1597C58, 0x15AAD44]
stock(0x1597C48, 'ldr w2, [sp, #0x358]')                                           # w2 = message player no
DROP_FN = 0x15B4320
DROP_END = fn_end(DROP_FN)
no_ip(DROP_FN, DROP_END)
stock(0x15B435C, 'stur w2, [x29, #-0x28]')          # player no kept at [x29-0x28] = x1 of the removal
stock(0x15B43C4, 'bl #0x17f1940')                   # chr of that player (functor 0x572D7A0)
stock(0x15B4430, 'cbz x24, #0x15b4aa8')             # no chr -> nothing
stock(0x15B44B0, 'blr x8')                          # x25 = chr vt+0x298 (its PlayerGameData; for a remote = copy)
stock(0x15B4608, 'bl #0xe925dc')                    # per inventory slot: droppable?
stock(0x15B4638, 'stp w21, w22, [x9, #4]')          # list {id, count} at x29-0xEC.., count at x29-0xF0 (max 16)
stock(0x15B4A50, 'bl #0x159c6c4')                   # one world item holding the list (I3: authority only)
stock(0x15B4A78, 'sub x1, x29, #0x28'); stock(0x15B4A98, 'neg w3, w8')   # removal: player no, -count
# 0xE925DC = "item is a Star Fragment while a shooting-star env event (type 0x1A) runs": event +0xF == 0x1A and
# item record (0x1D1D100) +0x42 == 1
stock(0xE9264C, 'cmp w8, #0x1a'); stock(0xE9268C, 'ldrb w8, [x8, #0x42]'); stock(0xE92690, 'cmp w8, #1')
b, rs = param_rows('EnvEventParam.param')
assert any(b[o + 0xF] == 0x1A for _, o in rs), 'no shooting-star env event (type 0x1A) any more: re-judge DROP'
L.append('DROP: sender 0x15AAC68 <- 0x17B4600 (vt 0x572C790 +0x4C0) <- death handler 0x1752400 @0x17529F0; '
         'droppable = Star Fragment during env type 0x1A; list from the dropper chr inventory on the authority')
# D2 site registers: x8 / x9 written at 0x15B4434 / 0x15B4438 before any read; exit 0x15B4AA8 = epilogue
stock(0x15B4434, 'mov w8, #-1'); stock(0x15B4438, 'mov x9, #-0x100000000')
for a in range(0x15B4AA8, 0x15B4ACC, 4):
    assert not re.search(r'\b[xw](8|9)\b', C.dis1(a, W[a // 4])), 'epilogue reads x8/x9 at %x' % a
stock(0x15B4AC8, 'retab')
for a in range(0x15B4434, 0x15B44B4, 4):     # D2 leaves flags set: nothing reads them before the blr at 0x15B44B0
    t = C.dis1(a, W[a // 4])
    assert not re.match(r'(b\.|csel|csinc|csinv|cset|ccmp|ccmn|adc|sbc)', t), 'flags read at %x: %s' % (a, t)
stock(0x15B44B0, 'blr x8')

# ================================================================ PICKONE (0x15B21A0, ret 0x15B2648) [V]
# needs a pending {sender, handle} in ItemMan +0x330..+0x338 (0x15B21E4..0x15B2220, none -> return 0x15B2748).
# Writers of +0x338 in the item server: 0x15A4444 / vector grow 0x15B7CE0 (only from 0x15A447C) = 0x15A440C
# block, plus the dtor 0x1596E40 and the exit trim 0x15B2744.
stock(0x15B21C4, 'ldr x27, [x0, #0x330]'); stock(0x15B2220, 'b #0x15b2748'); stock(0x15B2228, 'b.eq #0x15b2748')
stores = []
for i in range(0x1580000 // 4, 0x15C0000 // 4):
    w = W[i]
    if (w & 0xFFC00000) == 0xF9000000 and ((w >> 10) & 0xFFF) * 8 in (0x330, 0x338) and ((w >> 5) & 31) != 31:
        stores.append(4 * i)
assert stores == [0x1593748, 0x159374C, 0x1596E40, 0x15A4444, 0x15B2744], [hex(x) for x in stores]
assert bl_callers(0x15B7CE0) == [0x15A447C]
# 0x15A440C is reached only from 0x15A42D0 (after 0x15A42B0) with count w11 >= 2; the other way in
# (0x15A426C cbz w11 -> 0x15A42C0) has w11 = 0 and leaves at 0x15A4410 `b.lo`.
stock(0x15A426C, 'cbz w11, #0x15a42c0'); stock(0x15A42D0, 'b.hs #0x15a440c')
stock(0x15A440C, 'cmp w11, #2'); stock(0x15A4410, 'b.lo #0x15a42d4')
# shipped I6b: 0x15A42B0 -> cave_m6a: mode 6 -> always the subtype-6 reply 0x15A4510
assert C.dis1(0x15A42B0, C.shipped_word(0x15A42B0)) == 'b #0x563e520'
m6a = [C.dis1(a, C.shipped_word(a)) for a in range(0x563E520, 0x563E544, 4)]
assert m6a[4:9] == ['ldr w8, [x8, #0x1268]', 'cmp w8, #6', 'b.eq #0x563e540', 'b #0x15a42b4', 'b #0x15a4510'], m6a
L.append('PICKONE: pending list +0x330 filled only at 0x15A4438/0x15A447C, behind 0x15A42B0 = cave_m6a, which '
         'answers every mode-6 take with subtype 6 -> list stays empty -> 0x15B21A0 returns at 0x15B2220: UNREACHABLE')

# ================================================================ GIVE (0x15A3340, ret 0x15A34AC) [V code, data]
# callers 0x159CB44 (0x159C6C4 create, kind +0x12C == 2, subkind 1/3 -> chr(rec+0xC) -> its +0x20 +0x114 chr ->
# 0xDA7158 "player-like" -> 0x15A3340(player no)) and 0x15A43A0 (behind cave_m6a: unreachable in mode 6)
assert sorted(bl_callers(0x15A3340)) == [0x159CB44, 0x15A43A0]
stock(0x159C71C, 'ldrb w8, [x19, #0x12c]'); stock(0x159C730, 'b.eq #0x159ca38'); stock(0x159CAA8, 'bl #0xda7158')
stock(0x159CB28, 'ldr w20, [x23, #0xd0]'); stock(0x159CB38, 'mov x0, x20')
stock(0x15ACAF4, 'ldrb w8, [x8, #0x8b]'); stock(0x15ACAF8, 'strb w8, [sp, #0x1ac]')   # rec+0x12C = lot +0x8B
tab = C.RO[0x4C4CBA4 - C.RO_BASE:0x4C4CBA4 - C.RO_BASE + 5]
assert [0x159CA1C + 4 * x for x in tab] == [0x159CB74, 0x159CA5C, 0x159CA1C, 0x159CA5C, 0x159CB9C]
lb, lr = param_rows('ItemLotParam.param')
lot = {rid: o for rid, o in lr}
nb, nr = param_rows('NpcParam.param')
p2 = {}
for rid, o in nr:
    for f in (0x30, 0x34, 0x38):
        lid = struct.unpack_from('<i', nb, o + f)[0]
        if lid in lot and lb[lot[lid] + 0x8B] == 2:
            p2[lid] = sorted(x for x in struct.unpack_from('<8i', lb, lot[lid]) if x)
assert p2, 'no enemy lot with placement 2: GIVE unreachable - re-judge'
goods = sorted(set(x for v in p2.values() for x in v))
L.append('GIVE: %d enemy lots (NpcParam +0x30/+0x38) have ItemLotParam +0x8B == 2, goods %s -> reachable, '
         'LOSS for everybody today (host included)' % (len(p2), goods))

# ================================================================ LOT (0x15AF380, ret 0x15AF62C) [V code, I triggers]
assert sorted(bl_callers(0x15AF380)) == [0x15AF19C, 0x15AF724, 0x17CED14]
lot_callers = sorted(bl_callers(0x15AEF60))
assert len(lot_callers) == 14 and 0x1752598 in lot_callers
stock(0x1752548, 'ldr w1, [x8, #0x348]'); stock(0x175257C, 'mov w1, #0x173e')
assert all(struct.unpack_from('<i', nb, o + 0x348)[0] == -1 for _, o in nr), 'NpcParam +0x348 lot set: re-judge LOT'
assert sorted(struct.unpack_from('<8i', lb, lot[5950])) == [0] * 8, 'player-kill lot 5950 not empty: re-judge LOT'
assert C.dis1(0x15AF3D8, C.shipped_word(0x15AF3D8)) == 'cbnz w8, #0x15af674'     # shipped I8: authority only
assert C.dis1(0x15AF3D0, C.shipped_word(0x15AF3D0)) == 'ldrb w8, [x8, #0xfd8]'
L.append('LOT: callers of 0x15AEF60 %s; the death handler ones (NpcParam +0x348 all -1, player-kill lot 5950 '
         'empty) give nothing; the others not traced' % ', '.join('0x%X' % a for a in lot_callers))

# ================================================================ build: ITEMAUTH_DROP
groups = {'ITEMAUTH_GIVE': [], 'ITEMAUTH_LOT': [], 'ITEMAUTH_PICKONE': []}
# return offsets granted through the gate for the game's own player only. GIVE (itemauth3_notes.md): the receiver's
# G7 runs the stock give 0x15A3340 for its OWN player, so its 0xCF8E2C (ret 0x15A34AC) must pass D1 like the drop.
LOCAL_ONLY = [RET['DROP'], RET['GIVE']]
TAB_WORDS = 4                       # room for GIVE / LOT / PICKONE later + 0 terminator (only used words recorded)
TAB = g.alloc('ITEMAUTH_TABLE', 'FAR_DATA', TAB_WORDS * 4, 'item-authority local-only return offsets (D1)')
assert len(LOCAL_ONLY) < TAB_WORDS


def data_words(name, start, words):
    L.append('--- %s data at 0x%X (%d words) FAR_DATA' % (name, start, len(words)))
    recs = []
    for i, w in enumerate(words):
        a = start + 4 * i
        assert C.pool_of(a, 4) == 'FAR_DATA' and g.owned(a)
        g.free_bytes(a, 4, 'data word')
        L.append('  0x%x .word 0x%08X' % (a, w))
        recs.append((a, '00000000', C.hexw(w), True))
    return recs


def place(tag, build, purpose):
    n = len(build(C.FAR_LO).words())
    start = g.alloc(tag, 'FAR_CODE', (n * 4 + 0xF) & ~0xF, purpose)
    a = build(start)
    return start, g.cave(tag, start, a)


def sub_wr(rd, rn, rm):
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, sub_wr('w9', 'w9', 'w12')) == 'sub w9, w9, w12'


def build_d1(s):
    """At 0xCF8F70 (x8 = *(OFFL)). w8 = flag; LAN + listed return offset + receiver == own player -> w8 = 1."""
    a = C.Asm(s)
    a(C.ldrb('w8', 'x8', 0xBDA))                               # the replaced stock word
    a(C.to(C.cbnz_w, 'w8', 'back'))                            # offline: unchanged
    a(C.ldr_x('x9', 'x29', 8))                                 # 0xCF8E2C's saved LR (low 32 bits = address)
    a(lambda pc, L_: C.adrp(pc, 'x12', 0))                     # main base
    a(sub_wr('w9', 'w9', 'w12'))                               # return offset from main
    a(lambda pc, L_: C.adr(pc, 'x10', TAB))
    a.label('loop')
    a(C.ldr_w('w11', 'x10', 0))
    a(C.to(C.cbz_w, 'w11', 'back'))                            # not listed: w8 stays 0 (refused as today)
    a(C.add_xi('x10', 'x10', 4))
    a(C.cmp_wr('w9', 'w11'))
    a(C.to(C.bne, 'loop'))
    a(lambda pc, L_: C.adrp(pc, 'x10', GDM))
    a(C.ldr_x('x10', 'x10', C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x10', 'back'))
    a(C.ldr_x('x10', 'x10', 0x20))                             # local pgd
    a(C.to(C.cbz_x, 'x10', 'back'))
    a(C.ldr_w('w10', 'x10', 0xD0))                             # own player number
    a(C.ldr_w('w11', 'x19', 0))                                # receiving player number
    a(C.cmp_wr('w10', 'w11'))
    a(C.to(C.bne, 'back'))                                     # another player's copy: refused as today
    a(C.movz_w('w8', 1))                                       # gate passes (cbnz w8 in every gate version)
    a.label('back')
    a.many(lambda pc, L_: C.far_return(pc, GATE, 'x16'))
    return a


def build_d2(s):
    """At 0x15B4430 (x24 = dropper chr). Offline unchanged; LAN: dropper != own player -> leave."""
    a = C.Asm(s)
    a(C.to(C.cbz_x, 'x24', 'out'))                             # the replaced `cbz x24, #0x15b4aa8`
    a(lambda pc, L_: C.adrp(pc, 'x8', OFFL))
    a(C.ldr_x('x8', 'x8', C.lo12(OFFL)))
    a(C.to(C.cbz_x, 'x8', 'keep'))
    a(C.ldrb('w8', 'x8', 0xBDA))
    a(C.to(C.cbnz_w, 'w8', 'keep'))                            # offline: unchanged
    a(lambda pc, L_: C.adrp(pc, 'x8', GDM))
    a(C.ldr_x('x8', 'x8', C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x8', 'keep'))
    a(C.ldr_x('x8', 'x8', 0x20))
    a(C.to(C.cbz_x, 'x8', 'keep'))
    a(C.ldr_w('w8', 'x8', 0xD0))                               # own player number
    a(C.ldur_w('w9', 'x29', -0x28))                            # dropper's player number (message)
    a(C.cmp_wr('w8', 'w9'))
    a(C.to(C.bne, 'out'))                                      # remote dropper: no world item, no removal
    a.label('keep')
    a.many(lambda pc, L_: C.far_return(pc, 0x15B4434, 'x16'))
    a.label('out')
    a.many(lambda pc, L_: C.far_return(pc, 0x15B4AA8, 'x16'))
    return a


WHY_D1 = ('0xCF8E2C 0x%X..0x%X never names x16/x17 (scanned); D1 returns to 0xCF8F74 (gate: stock cbz, or the '
          'FORGE_OWN / ZEP3_C2 trampoline which writes x16 first); x9..x12 + flags are not read on the gate\'s two '
          'continuations (asserted by zep3_gen WHY_C2)' % (FS, FE))
WHY_D2 = ('0x15B4320 0x%X..0x%X never names x16/x17 (scanned); D2 returns to 0x15B4434 (`mov w8` / `mov x9` write '
          'x8/x9 first) or 0x15B4AA8 (epilogue, no x8/x9 read), no flag reader before the next cmp' % (DROP_FN, DROP_END))
# the gate's continuations (zep3 proof, re-asserted here so this file stands alone)
for _a in list(range(0xCF8F78, 0xCF8F88, 4)) + [0xCF8FE4, 0xCF8FE8] + list(range(0xCF92C8, 0xCF92EC, 4)):
    _t = C.dis1(_a, C.text_word(_a))
    assert not re.search(r'\b[xw](9|1[0-2])\b', _t) and not re.match(r'(b\.|csel|csinc|csinv|cset|ccmp)', _t), _t

tab_recs = data_words('ITEMAUTH_TABLE', TAB, LOCAL_ONLY + [0])
D1, d1_recs = place('ITEMAUTH_D1', build_d1, 'D1: 0xCF8E2C gate opens for listed callers when receiver is own player')
D2, d2_recs = place('ITEMAUTH_D2', build_d2, 'D2: 0x15B4320 skips a dropper that is not the own player (LAN)')
groups['ITEMAUTH_DROP'] = (tab_recs + d1_recs + d2_recs
                           + g.far_hook(GATE_LOAD, 'ldrb w8, [x8, #0xbda]', D1, 'x16', why=WHY_D1,
                                        note='D1 item gate: own-player table')
                           + g.far_hook(0x15B4430, 'cbz x24, #0x15b4aa8', D2, 'x16', why=WHY_D2,
                                        note='D2 drop: own player only'))

# ================================================================ build: ITEMAUTH_GIVE (itemauth2_notes.md) [V code]
# Stock decision: the item authority (0x159C6C4, I3 = authority only) gives a kind-2 / subkind-1/3 record to the
# player of chr(rec+0xC)'s chrdata+0x114 (last attacker; KILL2 makes every game agree on it) via 0x15A3340 ->
# 0xCF8E2C, which is refused in LAN. Fix = the authority keeps the decision and the roll and only changes the
# delivery: it broadcasts a subtype-6 award (the message every requester already gets for a pickup) carrying the
# record, taker = that player number and a marker; every game applies it to its OWN player only.
MGR3 = 0x5B3CE08                      # *(main+0x5B3CE08) = net mgr (GOT 0x59DFEC8 -> here)
MAGIC = 0x56494749                    # 'IGIV' at award message +0x188 (stock builder never writes +0x184..+0x18F)
SITE_G1 = 0x159CB44                   # bl 0x15A3340 in 0x159C6C4 (kind-2 per-player give)
SITE_G2 = 0x15978D4                   # first word of the 0x1E reader's subtype-6 case
assert struct.unpack_from('<Q', C.DATA, 0x59DFEC8 - C.DATA_BASE)[0] == MGR3
assert struct.unpack_from('<Q', C.DATA, 0x59E1B28 - C.DATA_BASE)[0] == 0x5B57E90
# the subtype-6 award builder (0x15A4510): header 0x00060001, record copy at +0x10, record +0x120.. at +0x130..,
# taker at +0x180 ([x29-0x34] = taker player no), size 0x190; bot takers are broadcast through mgr3+0x10 vt+0x40
for a, t in ((0x15A4574, 'mov w8, #1'), (0x15A4578, 'movk w8, #6, lsl #16'), (0x15A457C, 'str w8, [sp, #0x340]'),
             (0x15A4534, 'add x0, x8, #0x10'), (0x15A4530, 'add x1, sp, #0x4d0'), (0x15A4548, 'mov w2, #0x110'),
             (0x15A451C, 'add x25, x8, #0x120'), (0x15A45C4, 'ldur w8, [x29, #-0x34]'), (0x15A45D0, 'str w8, [sp, #0x4c0]'),
             (0x15A45D8, 'ldr x9, [x9, #0xec8]'), (0x15A45E0, 'ldr x0, [x9]'), (0x15A45F0, 'ldr x8, [x0, #0x10]!'),
             (0x15A45F8, 'mov w1, #0x1e'), (0x15A45FC, 'mov w3, #0x190'), (0x15A4600, 'ldr x8, [x8, #0x40]'),
             (0x15A4604, 'blr x8')):
    stock(a, t)
# the reader: buffer sp+0x350 (x2 of 0x1CD8260), record = buffer+0x10 (x22); subtype 6 -> case 0x15978D4
stock(0x15973A8, 'add x2, sp, #0x350'); stock(0x1597310, 'add x22, x9, #0x10'); stock(0x15972D8, 'add x9, sp, #0x350')
_jt = C.RO[0x4C4CB5C - C.RO_BASE:0x4C4CB5C - C.RO_BASE + 2 * 0x19]
assert 0x1597430 + 4 * struct.unpack_from('<H', _jt, 2 * 6)[0] == SITE_G2, 'subtype 6 case moved'
assert C.dis1(0x15973E4, C.shipped_word(0x15973E4)) == 'nop', 'DROPS D1 (game-type gate) not shipped'
# subtype-6 case [V]: count rec+0x38 == 3 or type in {7,8} -> award all; else count >= 2 and type != 9 -> choose-one
# 0x15A4DE0; award all = taker [buf+0x180] (-1 -> next) -> 0x17F1940(mask 0x407) chr -> 0x15A5020(rec, chr)
for a, t in ((0x15978D4, 'ldr w8, [sp, #0x398]'), (0x15978D8, 'cmp w8, #3'), (0x15978DC, 'b.eq #0x15978f4'),
             (0x15978E0, 'ldr w2, [sp, #0x360]'), (0x15978E4, 'and w9, w2, #0xf'), (0x15978E8, 'sub w10, w9, #7'),
             (0x15978EC, 'cmp w10, #2'), (0x15978F0, 'b.hs #0x1598120'), (0x15978F4, 'ldr w8, [sp, #0x4d0]'),
             (0x15978F8, 'cmn w8, #1'), (0x15978FC, 'b.eq #0x15973a0'), (0x1597910, 'stur w8, [x29, #-0x88]'),
             (0x1597938, 'mov w2, #0x407'), (0x159795C, 'bl #0x17f1940'), (0x1598120, 'cmp w8, #2'),
             (0x1598124, 'b.lo #0x15978f4'), (0x1598140, 'bl #0x15a4de0'), (0x15981B8, 'bl #0x15a5020'),
             (0x15973A0, 'ldr x0, [x27]'), (0x15973B8, 'bl #0x1cd8260'), (0x159B8AC, 'bl #0x472f1a0')):
    stock(a, t)
# 0x15A5020 awards every entry rec+0x3C.. (count rec+0x38 <= 16) to chr x5 through 0x15B5400 (the pickup path, not
# 0xCF8E2C); a missing world item id only skips the effect; Collector 0x15B52E0 counts type-3 records only
stock(0x15A5044, 'ldr w8, [x1, #0x38]'); stock(0x15A504C, 'b.hi #0x15a54fc'); stock(0x15A51D8, 'bl #0x15b5400')
stock(0x15A5230, 'cbz x0, #0x15a54ec'); stock(0x15B5328, 'cmp w8, #3'); stock(0x15B532C, 'b.ne #0x15b53ac')
# G1 site: 0x159C6C4 kind 2 (rec +0x12C) -> subkind table (+0x12D) 1/3 -> killer chain -> bl 0x15A3340
stock(0x159CA8C, 'ldr x8, [x23, #0x20]'); stock(0x159CA94, 'ldr w8, [x8, #0x114]')
stock(0x159CACC, 'add x1, x19, #0x38'); stock(0x159CAD4, 'mov w2, #0xc8'); stock(0x159CB04, 'bl #0xf672b4')
stock(0x159CB34, 'add x1, sp, #0xe0'); stock(SITE_G1, 'bl #0x15a3340'); stock(0x159CB48, 'b #0x159ca1c')
for a, t in ((0x159CA1C, 'add sp, sp, #0x270'), (0x159CA20, 'ldp x20, x19, [sp, #0x40]'),
             (0x159CA24, 'ldp x22, x21, [sp, #0x30]'), (0x159CA28, 'ldp x24, x23, [sp, #0x20]'),
             (0x159CA2C, 'ldp x28, x25, [sp, #0x10]'), (0x159CA30, 'ldp x29, x30, [sp], #0x50'), (0x159CA34, 'retab')):
    stock(a, t)
assert C.dis1(0x159C710, C.shipped_word(0x159C710)) == 'cbnz w8, #0x159ca1c', 'ITEMS I3 (authority only) changed'
CS, CE = 0x159C6C4, fn_end(0x159C6C4)
no_ip(CS, CE)
for a in range(CS, CE, 4):          # x19 = record (x1) for the whole body: only the entry move and epilogues write it
    t = C.dis1(a, W[a // 4])
    if re.match(r'(mov|ldr|ldp|add|sub|orr|and) (x19|w19)\b|ldp \w+, x19\b', t):
        assert a == 0x159C6F0 or t.startswith('ldp x20, x19, [sp, #0x40]'), 'x19 written at %x: %s' % (a, t)
stock(0x159C6F0, 'mov x19, x1')
# enemy lots reach it with subkind 3: 0x15ACFD8 calls 0x15AC7D4 with w5 = w6 = 0 -> rec+0x12D = 3 (csinc / csel)
for c in (0x15AD0E0, 0x15AD13C, 0x15AD19C):
    stock(c - 0x18, 'mov w5, wzr'); stock(c - 0x14, 'mov w6, wzr'); stock(c, 'bl #0x15ac7d4')
for a, t in ((0x15AC838, 'mov w25, w5'), (0x15AC928, 'mov w21, w6'), (0x15ACA1C, 'str w21, [sp, #0x24]'),
             (0x15ACA78, 'mov w10, #3'), (0x15ACAA4, 'csinc w10, w10, wzr, eq'), (0x15ACAB0, 'csel w10, w11, w10, ne'),
             (0x15ACB34, 'strb w8, [sp, #0x1ad]'), (0x15ACAF8, 'strb w8, [sp, #0x1ac]'), (0x15ACB84, 'bl #0x159c6c4'),
             (0x15ACB08, 'add x1, sp, #0x80'), (0x15ACC84, 'stp w9, w20, [sp, #0x88]'), (0x15AC7F8, 'sub sp, sp, #0x240')):
    stock(a, t)       # record at sp+0x80 of a 0x240 frame: the 0x170-byte copy stays inside it
assert 0x159CA1C + 4 * tab[3] == 0x159CA5C                 # subkind 3 -> the killer chain (table checked above)
# every enemy GIVE lot rolls ONE goods (one non-zero item slot): the award always has count <= 1
for lid, items in p2.items():
    assert len(items) == 1, 'lot %d gives %s: re-check the award count path' % (lid, items)


def acc(t, r):
    """'w' / 'r' / None: what instruction text t does FIRST with register number r (or 'nzcv')."""
    mn, _, ops = t.partition(' ')
    if r == 'nzcv':
        if mn.startswith('b.') or mn in ('csel', 'cset', 'csinc', 'csinv', 'csneg', 'cinc', 'ccmp', 'ccmn',
                                         'adc', 'sbc', 'adcs', 'sbcs', 'cneg', 'csetm'):
            return 'r'
        return 'w' if mn in ('cmp', 'cmn', 'tst', 'adds', 'subs', 'ands', 'bics', 'negs') else None
    if not re.search(r'\b[xw]%d\b' % r, ops):
        return 'w' if mn in ('bl', 'blr') and r in (9, 10, 16, 17) else None     # caller-saved, dead across a call
    parts = [p.strip() for p in re.split(r',(?![^\[]*\])', ops)]
    nd = 2 if mn in ('ldp', 'ldpsw') else 1
    if (mn in ('b', 'bl', 'br', 'blr', 'ret', 'cmp', 'cmn', 'tst', 'cbz', 'cbnz', 'tbz', 'tbnz', 'ccmp', 'ccmn',
               'bfi', 'bfxil', 'movk') or mn.startswith(('b.', 'st'))):
        return 'r'
    dests = parts[:nd]
    if any(re.fullmatch(r'[xw]%d' % r, d) for d in dests) and \
            not any(re.search(r'\b[xw]%d\b' % r, p) for p in parts[nd:]):
        return 'w'
    return 'r'


def dead_on(paths, regs, why):
    """Every path (list of (start, end) inclusive segments) writes each reg before reading it."""
    for path in paths:
        for r in regs:
            seen = None
            for s, e in path:
                for a in range(s, e + 4, 4):
                    k = acc(C.dis1(a, C.text_word(a)), r)
                    if k:
                        seen = k
                        break
                if seen:
                    break
            assert seen in ('w', None), '%s: %s read first on path %s' % (why, r, path)


# G2 returns: 0x15978D8 (stock), 0x15978F4 (award, ours for own player), 0x15973A0 (next message, ours otherwise)
G2_PATHS = [[(0x15978D8, 0x15978DC), (0x15978F4, 0x159795C)],
            [(0x15978D8, 0x15978F0), (0x1598120, 0x1598140)],
            [(0x15978D8, 0x15978F0), (0x15978F4, 0x159795C)],
            [(0x15978F4, 0x15978FC), (0x15973A0, 0x15973B8)],
            [(0x15973A0, 0x15973A4), (0x159B8A4, 0x159B8AC)]]
dead_on(G2_PATHS, (9, 10, 16, 17, 'nzcv'), 'G2')
for a in range(0x1597280, fn_end(0x1597280), 4):            # nothing else branches to the award block
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    if t.endswith('#0x15978f4'):
        assert a in (0x15978DC, 0x1598124, 0x159812C), 'other branch to 0x15978F4 at %x: %s' % (a, t)
stock(0x159812C, 'b.eq #0x15978f4')


def build_g1(s):
    """bl from 0x159CB44 (x30 = 0x159CB48). Offline: tail jump to 0x15A3340 (stock). LAN: broadcast a subtype-6
    award {record (x19, 0x170 B) with the adjusted list (x1, 0xC8 B), taker = w0, marker} and return."""
    a = C.Asm(s)
    a(lambda pc, L_: C.adrp(pc, 'x16', OFFL))
    a(C.ldr_x('x9', 'x16', C.lo12(OFFL)))
    a(C.to(C.cbz_x, 'x9', 'stock'))
    a(C.ldrb('w9', 'x9', 0xBDA))
    a(C.to(C.cbnz_w, 'w9', 'stock'))                           # offline: unchanged
    a(C.mov_w('w13', 'w0'))                                    # receiver = the killer's player number
    a(C.stp_pre('x29', 'x30', 'sp', -0x1A0))
    a(C.mov_sp('x29', 'sp'))
    a(C.add_xi('x10', 'sp', 0x10))                             # message (0x190 B)
    a(C.mov_x('x9', 'x10'))
    a(C.movz_w('w11', 0x19))
    a.label('zero')
    a(C.stp_x('xzr', 'xzr', 'x9', 0))
    a(C.add_xi('x9', 'x9', 16))
    a(C.sub_wi('w11', 'w11', 1))
    a(C.to(C.cbnz_w, 'w11', 'zero'))
    a(C.movz_w('w9', 1))
    a(C.movk_w('w9', 6, 1))
    a(C.str_w('w9', 'x10', 0))                                 # u32 0x00060001 (version 1, subtype 6)
    a(C.mov_x('x9', 'x19'))
    a(C.add_xi('x12', 'x10', 0x10))
    a(C.movz_w('w11', 0x17))
    a.label('rec')
    a(C.ldp_x('x14', 'x15', 'x9', 0))                          # record +0..+0x170 -> message +0x10..+0x180
    a(C.stp_x('x14', 'x15', 'x12', 0))
    a(C.add_xi('x9', 'x9', 16))
    a(C.add_xi('x12', 'x12', 16))
    a(C.sub_wi('w11', 'w11', 1))
    a(C.to(C.cbnz_w, 'w11', 'rec'))
    a(C.add_xi('x12', 'x10', 0x48))                            # record +0x38 list <- the adjusted list (bonus added)
    a(C.movz_w('w11', 25))
    a.label('list')
    a(C.ldr_x('x14', 'x1', 0))
    a(C.str_x('x14', 'x12', 0))
    a(C.add_xi('x1', 'x1', 8))
    a(C.add_xi('x12', 'x12', 8))
    a(C.sub_wi('w11', 'w11', 1))
    a(C.to(C.cbnz_w, 'w11', 'list'))
    a(C.str_w('w13', 'x10', 0x180))                            # taker
    a(C.movz_w('w9', MAGIC & 0xFFFF))
    a(C.movk_w('w9', MAGIC >> 16, 1))
    a(C.str_w('w9', 'x10', 0x188))                             # marker
    a(lambda pc, L_: C.adrp(pc, 'x16', MGR3))
    a(C.ldr_x('x0', 'x16', C.lo12(MGR3)))
    a(C.to(C.cbz_x, 'x0', 'out'))
    a(C.add_xi('x0', 'x0', 0x10))                              # as 0x15A45F0 `ldr x8, [x0, #0x10]!`
    a(C.ldr_x('x8', 'x0', 0))
    a(C.ldr_x('x8', 'x8', 0x40))                               # broadcast (every member + self link)
    a(C.movz_w('w1', 0x1E))
    a(C.mov_x('x2', 'x10'))
    a(C.movz_w('w3', 0x190))
    a(C.blr('x8'))
    a.label('out')
    a(C.ldp_post('x29', 'x30', 'sp', 0x1A0))
    a(C.RET)
    a.label('stock')
    a.many(lambda pc, L_: C.far_jump(pc, 0x15A3340, 'x16'))   # x30 / sp untouched: same as the stock bl
    return a


def build_g2(s):
    """At 0x15978D4 (subtype-6 case). Marked award in LAN: taker == own player -> award block 0x15978F4 (all
    entries, no choose-one), else next message 0x15973A0. Anything else: the stock word, back to 0x15978D8."""
    a = C.Asm(s)
    a(lambda pc, L_: C.adrp(pc, 'x16', OFFL))
    a(C.ldr_x('x9', 'x16', C.lo12(OFFL)))
    a(C.to(C.cbz_x, 'x9', 'stock'))
    a(C.ldrb('w9', 'x9', 0xBDA))
    a(C.to(C.cbnz_w, 'w9', 'stock'))                           # offline: unchanged
    a(C.ldr_w('w9', 'sp', 0x350 + 0x188))
    a(C.movz_w('w10', MAGIC & 0xFFFF))
    a(C.movk_w('w10', MAGIC >> 16, 1))
    a(C.cmp_wr('w9', 'w10'))
    a(C.to(C.bne, 'stock'))                                    # every stock award: unchanged
    a(lambda pc, L_: C.b(pc, G2K))                             # review 9 N1: kind / subkind check, back to 'mine'
    a.label('mine')
    a(lambda pc, L_: C.adrp(pc, 'x16', GDM))
    a(C.ldr_x('x9', 'x16', C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x9', 'skip'))
    a(C.ldr_x('x9', 'x9', 0x20))
    a(C.to(C.cbz_x, 'x9', 'skip'))
    a(C.ldr_w('w9', 'x9', 0xD0))                               # own player number
    a(C.ldr_w('w10', 'sp', 0x350 + 0x180))                     # taker
    a(C.cmp_wr('w9', 'w10'))
    a(C.to(C.bne, 'skip'))
    a(lambda pc, L_: C.b(pc, G7))                              # mine: G7 adds to my inventory, then the popup
    a.label('skip')
    a.many(lambda pc, L_: C.far_return(pc, 0x15973A0, 'x16'))  # someone else's: never touch his copy
    a.label('stock')
    a(C.ldr_w('w8', 'sp', 0x398))                              # the replaced stock word
    a.many(lambda pc, L_: C.far_return(pc, 0x15978D8, 'x16'))
    return a


assert C.dis1(0, C.ldr_w('w8', 'sp', 0x398)) == 'ldr w8, [sp, #0x398]'
WHY_G1 = ('site is a bl (x16/x17 corruptible across a call) and 0x159C6C4 0x%X..0x%X never names x16/x17 '
          '(scanned); G1 ends in ret to 0x159CB48 `b 0x159ca1c` (epilogue reads only sp/callee-saved) or tail-jumps '
          'to the function entry 0x15A3340' % (CS, CE))
WHY_G2 = ('reached by the jump table br x11; on every path from 0x15978D4 / 0x15978F4 / 0x15973A0 x9, x10, x16, x17 '
          'and the flags are written before read up to the next bl (0x159795C, 0x1598140, 0x15973B8, 0x159B8AC) '
          '(asserted per path)')
# ---------------- itemauth3 (live: GIVE delivered nothing): the subtype-6 award is DISPLAY ONLY in a match [V]
# 0x15A5020 -> 0x15B5400: with the world singleton *(0x5B57E90) non-null (always in a match) the online branch only
# queues {id, 1} in a local deque (0x15B5564..0x15B55EC, its only call is the deque grow 0xCD57C0) and fills the
# "item got" popup list (MapItemMan +0x21C/+0x228, +0x2F0 count). The inventory add (0x15A2820 / 0xCD76C0 /
# 0xCD4F94) is in the singleton-null branch 0x15B57FC. The real inventory add is the item server's 0x15A3340 ->
# 0xCF8E2C (G1 replaced exactly that call). So G7: the taker's own game runs 0x15A3340 for its OWN player (what
# offline does on the killer's game), D1 lets ret 0x15A34AC through for the own player only, then the popup.
for a, t in ((0x15B5550, 'adrp x8, #0x5b57000'), (0x15B5554, 'add x8, x8, #0xe90'), (0x15B555C, 'ldr x8, [x8]'),
             (0x15B5560, 'cbz x8, #0x15b57fc'), (0x15B5570, 'bl #0xcd57c0'), (0x15B587C, 'ldr x0, [x20, #0xec0]'),
             (0x15B588C, 'bl #0xcd76c0'), (0x15B591C, 'bl #0xcd4f94'), (0x15B581C, 'bl #0x15a2820'),
             (0x15A51D8, 'bl #0x15b5400'), (0x15A5180, 'bl #0x15b5400')):
    stock(a, t)
for a in range(0x15B5564, 0x15B55F0, 4):
    if C.dis1(a, W[a // 4]).startswith(('bl ', 'blr ')):
        assert a == 0x15B5570, 'online award branch calls something at %x' % a
# 0x15A3340 flags -> 0xCF8E2C x6: bit1 = w3 & 1; goods with +0xCC >= 0 (WinPointObtain id, e.g. 8000 -> 603000000)
# are refused unless bit1 is set (0xCF8FCC..0xCF8FDC); the second gate 0xCF8ED0 (+0x6D in 1..2) is offline-only
for a, t in ((0x15A3368, 'tst w3, #1'), (0x15A336C, 'mov w8, #2'), (0x15A3370, 'csel w8, w8, wzr, ne'),
             (0x15A3494, 'add x6, sp, #0x6c0'), (0x15A34A4, 'str w26, [sp, #0x6c0]'), (0x15A348C, 'add x1, sp, #0x6b8'),
             (0x15A3380, 'str w20, [sp, #0x6b8]'), (0x15A3378, 'mov x20, x0'),
             (0xCF8ED0, 'ldrb w8, [x8, #0x6d]'), (0xCF8FCC, 'ldr w8, [x8, #0xcc]'), (0xCF8FD0, 'tbnz w8, #0x1f, #0xcf8fec'),
             (0xCF8FD4, 'ldrb w8, [x22]'), (0xCF8FD8, 'tbnz w8, #1, #0xcf8fec'), (0xCF8E5C, 'mov x22, x6'),
             # stock arguments at 0x159CB44: w2 = 1 (0x15AC7D4 -> 0x159C6C4), w3 = rec+0x28 bit 23, w4 = 0x15A36AC
             (0x15ACB14, 'mov w2, #1'), (0x159C728, 'mov w22, w2'), (0x159CB3C, 'mov w2, w22'),
             (0x159CB1C, 'ldr w8, [x19, #0x28]'), (0x159CB24, 'ubfx w21, w8, #0x17, #1'), (0x159CB40, 'mov w3, w21'),
             (0x15ACCE4, 'orr w9, w9, #2'), (0x15A36DC, 'mov w0, wzr'), (0x15A36E4, 'and w9, w9, #0xf'),
             (0x15A36E8, 'cmp w9, #3'), (0x15A36EC, 'b.ne #0x15a3758'), (0x15A3758, 'ldp x29, x30, [sp, #0x10]')):
    stock(a, t)
gb, gr = param_rows('EquipParamGoods.param')
grow = {rid: o for rid, o in gr}
for gid in goods:
    assert gb[grow[gid] + 0x6D] not in (1, 2), 'goods %d +0x6D: offline-only gate' % gid
assert struct.unpack_from('<i', gb, grow[8000] + 0xCC)[0] >= 0, 'goods 8000 no longer a WinPointObtain goods'
# the award block up to its first call writes every caller-saved register before reading it; 0x17F1940 (4 args)
# never names x4..x7 -> G7's call of 0x15A3340 (clobbers x0..x17) is invisible to the reader
dead_on([[(0x15978F4, 0x159795C)]], list(range(0, 16)) + [17, 'nzcv'], 'G7')
for a in range(0x17F1940, fn_end(0x17F1940), 4):
    assert not re.search(r'\b[xw][4-7]\b', C.dis1(a, W[a // 4])), '0x17F1940 names x4..x7 at %x' % a
MSG = 0x350                           # reader buffer; record = +0x10, rec+0x28 = +0x38, list rec+0x38 = +0x48


def ubfx_w(rd, rn, lsb, width):
    return 0x53000000 | (lsb << 16) | ((lsb + width - 1) << 10) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, ubfx_w('w3', 'w3', 23, 1)) == 'ubfx w3, w3, #0x17, #1'


def build_g7(s):
    """From G2 'mine' (taker == own player, sp = reader sp). 0x15A3340(own no, list, 1, rec+0x28 bit 23, 0) as the
    stock call at 0x159CB44, then the stock award block 0x15978F4 (popup only)."""
    a = C.Asm(s)
    a(C.stp_pre('x29', 'x30', 'sp', -0x10))
    a(C.mov_sp('x29', 'sp'))
    a(C.ldr_w('w0', 'sp', 0x10 + MSG + 0x180))                # taker (== own player number, G2 checked)
    a(C.add_xi('x1', 'sp', 0x10 + MSG + 0x48))                 # {count, {id, n, .} x count} (bonus-adjusted, G1)
    a(C.movz_w('w2', 1))
    a(C.ldr_w('w3', 'sp', 0x10 + MSG + 0x38))                  # record +0x28
    a(ubfx_w('w3', 'w3', 23, 1))                               # bit 23 = enemy lot -> goods with +0xCC accepted
    a(C.movz_w('w4', 0))
    a.many(lambda pc, L_: C.far_call(pc, 0x15A3340, 'x16'))
    a(C.ldp_post('x29', 'x30', 'sp', 0x10))
    a.many(lambda pc, L_: C.far_return(pc, 0x15978F4, 'x16'))
    return a


G7, g7_recs = place('ITEMAUTH_G7', build_g7, 'G7: GIVE receiver adds to its own inventory (0x15A3340), then popup')
G2K = g.alloc('ITEMAUTH_G2K', 'FAR_CODE', 8 * 4, 'G2: kind 2 / subkind 1 or 3 check next to the marker')
G1, g1_recs = place('ITEMAUTH_G1', build_g1, 'G1: kind-2 give -> subtype-6 award broadcast (LAN)')
G2, g2_recs = place('ITEMAUTH_G2', build_g2, 'G2: subtype-6 award with the GIVE marker -> own player only')
L.append('GIVE: G1 0x%X (hook 0x%X), G2 0x%X (hook 0x%X), marker 0x%08X at +0x188' % (G1, SITE_G1, G2, SITE_G2, MAGIC))

# ================================================================ review 9 (review9_fix_notes.md)
ROLE = 0x492AFD8                      # byte, 0 = host (item authority)
OFFL_TEST_WORDS = 5


def offline_or(a, lab, reg='x16'):
    """5 words: *(OFFL) null or +0xBDA != 0 -> branch to lab."""
    r = int(reg[1:])
    a(lambda pc, L_: C.adrp(pc, r, OFFL))
    a(C.ldr_x(r, r, C.lo12(OFFL)))
    a(C.to(C.cbz_x, reg, lab))
    a(C.ldrb(r, r, 0xBDA))
    a(C.to(C.cbnz_w, 'w%d' % r, lab))


def bfi_w(rd, rn, lsb, width):
    return 0x33000000 | (((32 - lsb) % 32) << 16) | ((width - 1) << 10) | (C.R(rn) << 5) | C.R(rd)


def uxth_w(rd, rn):
    return 0x12003C00 | (C.R(rn) << 5) | C.R(rd)          # and wd, wn, #0xffff


assert C.dis1(0, bfi_w('w9', 'w10', 27, 4)) == 'bfi w9, w10, #0x1b, #4'
assert C.dis1(0, uxth_w('w8', 'w9')) == 'and w8, w9, #0xffff'
TAG_LSB = 27                          # same tag as powers_gen CTAG: id bits 27..30 = player number & 0xF


def callers_to(target, lo, hi):
    out = []
    for a in range(lo, hi, 4):
        t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
        if re.search(r'#0x%x$' % target, t):
            out.append(a)
    return out


# ---------------- S3: every dying player's OWN game drops (and removes) his Star Fragments [V]
# 0x15AAC68: w8 = dropper player no (0x15AACA4), w9 = bda (0x15AAD14); `cbz w9` -> send 0x13, else local 0x15B4320
for a, t in ((0x15AAD14, 'ldrb w9, [x10, #0xbda]'), (0x15AAD2C, 'cbz w9, #0x15aad4c'), (0x15AAD40, 'mov x2, x8'),
             (0x15AAD4C, 'adrp x8, #0x5b3c000'), (0x15AAD70, 'blr x8')):
    stock(a, t)
for a in range(0x15AACA8, 0x15AAD40, 4):
    assert not re.match(r'(?!st)\S+ (x8|w8)\b', C.dis1(a, W[a // 4])), 'w8 rewritten at %x' % a
no_ip(0x15AAC68, fn_end(0x15AAC68))
dead_on([[(0x15AAD30, 0x15AAD44)], [(0x15AAD4C, 0x15AAD70)]], (9, 10, 16, 'nzcv'), 'D3')
assert C.dis1(0x159C700, W[0x159C700 // 4]) == 'cbz x8, #0x159c778'
for a in range(0x159C704, 0x159C714):
    assert a in C.SHIPPED, 'ITEMS I3 not shipped at %x' % a
PRO = list(range(0x159C6C4, 0x159C700, 4))
for a in PRO:
    t = C.dis1(a, W[a // 4])
    assert not t.startswith(('b ', 'bl ', 'b.', 'cbz', 'cbnz', 'tb', 'adr ')), t
stock(0x159C714, 'ldrb w8, [x19]')
# the drop record (x1 = sp+0x80 of 0x15B4320): id at +0 = (counter << 5) | 0x10 | 1, nowhere else
stock(0x15B4780, 'str w9, [sp, #0x80]'); stock(0x15B49F8, 'add x1, sp, #0x80')
assert [a for a in range(0x15B4784, 0x15B4A50, 4) if re.search(r'\[sp, #0x80\]', C.dis1(a, W[a // 4]))] == []


def build_d3(s):
    """At 0x15AAD2C. Offline unchanged. LAN guest whose OWN player died: local 0x15B4320 (as offline), no 0x13
    message. Host and other players' deaths: the message, as today (the host keeps its self-link drop)."""
    a = C.Asm(s)
    a(C.to(C.cbnz_w, 'w9', 'local'))                           # offline: stock local call
    a(lambda pc, L_: C.adrp(pc, 'x10', ROLE))
    a(C.ldrb('w10', 'x10', C.lo12(ROLE)))
    a(C.to(C.cbz_w, 'w10', 'send'))                            # host: unchanged
    a(lambda pc, L_: C.adrp(pc, 'x10', GDM))
    a(C.ldr_x('x10', 'x10', C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x10', 'send'))
    a(C.ldr_x('x10', 'x10', 0x20))
    a(C.to(C.cbz_x, 'x10', 'send'))
    a(C.ldr_w('w10', 'x10', 0xD0))
    a(C.cmp_wr('w10', 'w8'))
    a(C.to(C.bne, 'send'))
    a(lambda pc, L_: C.b(pc, D3B))                              # review 11 N2: also the dying chr == local chr
    a.label('local')
    a.many(lambda pc, L_: C.far_return(pc, 0x15AAD30, 'x16'))
    a.label('send')
    a.many(lambda pc, L_: C.far_return(pc, 0x15AAD4C, 'x16'))
    return a


# review 11 N2: x1 = dying chr for the whole sender up to 0x15AAD2C; the local player chr is
# *(*(GOT 0x59DFE68))+0x1A8 (the value 0x15AACE8 compares with x1)
for a, t in ((0x15AACAC, 'ldr x9, [x9, #0xe68]'), (0x15AACB0, 'ldr x9, [x9]'), (0x15AACBC, 'ldr x9, [x9, #0x1a8]'),
             (0x15AACE8, 'cmp x9, x1')):
    stock(a, t)
for a in range(0x15AAC68, 0x15AAD30, 4):
    assert not re.match(r'(?!st)\S+ (x1|w1)\b', C.dis1(a, W[a // 4])), 'x1 rewritten at %x' % a
WCM_GOT = 0x59DFE68
D3B = g.alloc('ITEMAUTH_D3B', 'FAR_CODE', 16 * 4, 'D3: dying chr must be the local player chr (review 11 N2)')


def build_d3b(s):
    a = C.Asm(s)
    a(lambda pc, L_: C.adrp(pc, 'x10', WCM_GOT))
    a(C.ldr_x('x10', 'x10', C.lo12(WCM_GOT)))
    a(C.ldr_x('x10', 'x10', 0))
    a(C.to(C.cbz_x, 'x10', 'send'))
    a(C.ldr_x('x10', 'x10', 0x1A8))
    a(C.cmp_xr('x10', 'x1'))
    a(C.to(C.bne, 'send'))                                     # a bot / other chr with that number: message only
    a.many(lambda pc, L_: C.far_return(pc, 0x15AAD30, 'x16'))
    a.label('send')
    a.many(lambda pc, L_: C.far_return(pc, 0x15AAD4C, 'x16'))
    return a


d3b = build_d3b(D3B)
assert len(d3b.words()) <= 16
d3b_recs = g.cave('ITEMAUTH_D3B', D3B, d3b)


def build_d4(s):
    """bl from 0x15B4A50 (x30 = 0x15B4A54), x1 = drop record, x29 = 0x15B4320 frame. Offline or host: stock create.
    LAN guest (only its own death reaches here, D2/D3): tag the id with its player number and run 0x159C6C4 past
    the ITEMS I3 gate; the shipped cave_push sends the item to every game (as POWERS CREATE)."""
    a = C.Asm(s)
    offline_or(a, 'stock')
    a(lambda pc, L_: C.adrp(pc, 'x9', ROLE))
    a(C.ldrb('w9', 'x9', C.lo12(ROLE)))
    a(C.to(C.cbz_w, 'w9', 'stock'))                            # host: I3 passes anyway
    a(C.ldr_w('w9', 'x1', 0))
    a(C.ldur_w('w10', 'x29', -0x28))                           # dropper player no (= own, D2)
    a(bfi_w('w9', 'w10', TAG_LSB, 4))
    a(C.str_w('w9', 'x1', 0))
    for pa in PRO:
        a.many(lambda pc, L_, pa=pa: C.relocate(pa, pc))
    a.many(lambda pc, L_: C.relocate(0x159C700, pc))
    a.many(lambda pc, L_: C.far_jump(pc, 0x159C714, 'x16'))    # retab of 0x159C6C4 returns to 0x15B4A54
    a.label('stock')
    a.many(lambda pc, L_: C.far_jump(pc, 0x159C6C4, 'x16'))
    return a


D3, d3_recs = place('ITEMAUTH_D3', build_d3, 'D3: guest own death -> local drop (S3)')
D4, d4_recs = place('ITEMAUTH_D4', build_d4, 'D4: guest own drop create, tagged id, past I3 (S3)')
groups['ITEMAUTH_DROP'] += (d3b_recs + d3_recs + d4_recs
                            + g.far_hook(0x15B4A50, 'bl #0x159c6c4', D4, 'x16', link=True,
                                         why='site is a bl; 0x15B4320 never names x16/x17 (scanned); 0x159C6C4 '
                                             'never names them', note='D4 guest drop create')
                            + g.far_hook(0x15AAD2C, 'cbz w9, #0x15aad4c', D3, 'x16',
                                         why='0x15AAC68 never names x16/x17 (scanned); both continuations write x9, '
                                             'x10, x16, flags before reading them (asserted)',
                                         note='D3 own death -> local drop'))

# ---------------- S4: the enemy owner carries the killer handle in the 0x14 message; the host uses it [V]
# sender 0x15AADE0: x21 = enemy chr for the whole body; message sp+0x84 (0x3C B), bytes +0x39..+0x3B unused
SND, SND_END = 0x15AADE0, fn_end(0x15AADE0)
no_ip(SND, SND_END)
stock(0x15AAE08, 'mov x21, x1'); stock(0x15AAF18, 'cbz w8, #0x15aaf64'); stock(0x15AAF64, 'adrp x8, #0x5b3c000')
stock(0x15AAF78, 'add x2, sp, #0x84'); stock(0x15AAF80, 'mov w3, #0x3c'); stock(0x15AB030, 'strb w22, [sp, #0xbc]')
for a in range(SND, SND_END, 4):
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    assert not re.match(r'\S+ (x21|w21)\b', t) or a == 0x15AAE08, 'x21 written at %x' % a
    assert not re.search(r'\[sp, #0x(bd|be|bf)\]', t), 'message padding written at %x' % a
assert callers_to(0x15AAF64, SND, SND_END) == [0x15AAF18]
dead_on([[(0x15AAF68, 0x15AAF88)]], (9, 16, 'nzcv'), 'G3')
# reader 0x14 case: msg = sp+0x350, reads +0x38 (sp+0x388) only from the tail; 0x15B4B00 (0x15B4B00..0x15B4F6C)
# reads no stack argument and never names x16/x17; its two killer reads are 0x159CA94 (GIVE) and 0x15B4E90 (rose)
stock(0x1597C98, 'ldrb w4, [sp, #0x388]'); stock(0x1597CAC, 'bl #0x15b4b00'); stock(0x1597CB0, 'b #0x15973a0')
_rd = fn_end(0x1597280)
for a in range(0x1597280, _rd, 4):
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    assert not re.search(r'\[sp, #0x38[9ab]\]', t), 'reader reads the padding at %x' % a
assert sorted(bl_callers(0x15B4B00)) == [0x1597CAC, 0x15AAF5C]
B4_END = fn_end(0x15B4B00)
no_ip(0x15B4B00, B4_END)
for a in range(0x15B4B00, B4_END, 4):
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    m = re.search(r'\[x29, #(0x[0-9a-f]+)\]', t)
    assert not (m and int(m.group(1), 16) >= 0x50), 'stack argument read at %x' % a
stock(0x15B4E90, 'ldr w8, [x8, #0x114]'); stock(0x15B4E98, 'bl #0x17e7828')
stock(0x159CA9C, 'bl #0x17e7828')
dead_on([[(0x159CA98, 0x159CA9C)], [(0x15B4E94, 0x15B4E98)]], (9, 16, 'nzcv'), 'G5/G6')
# the chr lookup 0x17E7828 uses only the low u16 of the handle ([x1] ldrh)
stock(0x17E7844, 'ldrh w11, [x1]')
_e = fn_end(0x17E7828)
assert [a for a in range(0x17E7828, _e, 4) if re.search(r'\[x1\b', C.dis1(a, W[a // 4]))] == [0x17E7844]
KMARK = 0x4B                          # 'K' at message +0x39; +0x3A = u16 killer handle
KH = g.alloc('ITEMAUTH_KH', 'FAR_DATA', 4, 'GIVE: 0x10000 + killer handle of the 0x14 being served (0 = none)')


def build_g3(s):
    """At 0x15AAF64 (online send path of the 0x14 drop request, enemy owner). Writes the owner's killer
    (chrdata+0x114, the KILL2 decision) into the message padding."""
    a = C.Asm(s)
    a(C.ldr_x('x9', 'x21', 0x20))
    a(C.to(C.cbz_x, 'x9', 'none'))
    a(C.ldrh('w9', 'x9', 0x114))
    a(C.strh('w9', 'sp', 0xBE))
    a(C.movz_w('w9', KMARK))
    a(C.strb('w9', 'sp', 0xBD))
    a(C.to(C.b, 'out'))
    a.label('none')
    a(C.strb('wzr', 'sp', 0xBD))
    a.label('out')
    a.many(lambda pc, L_: C.relocate(0x15AAF64, pc))
    a.many(lambda pc, L_: C.far_return(pc, 0x15AAF68, 'x16'))
    return a


def build_g4(s):
    """bl from 0x1597CAC (x30 = 0x1597CB0): KH = carried killer for the duration of 0x15B4B00, then 0."""
    a = C.Asm(s)
    a(C.movz_w('w9', 0))
    a(C.ldrb('w10', 'sp', 0x389))
    a(C.cmp_wi('w10', KMARK))
    a(C.to(C.bne, 'set'))
    a(C.ldrh('w9', 'sp', 0x38A))
    a(C.movk_w('w9', 1, 1))                                    # valid bit 16
    a.label('set')
    a(lambda pc, L_: C.adrp(pc, 'x10', KH))
    a(C.str_w('w9', 'x10', C.lo12(KH)))
    a(C.stp_pre('x29', 'x30', 'sp', -0x10))
    a(C.mov_sp('x29', 'sp'))
    a.many(lambda pc, L_: C.far_call(pc, 0x15B4B00, 'x16'))
    a(lambda pc, L_: C.adrp(pc, 'x10', KH))
    a(C.str_w('wzr', 'x10', C.lo12(KH)))
    a(C.ldp_post('x29', 'x30', 'sp', 0x10))
    a(C.RET)
    return a


def build_kread(back, stock_word):
    def build(s):
        """`ldr w8, [x8, #0x114]` replacement: KH valid -> w8 = carried handle, else the stock word."""
        a = C.Asm(s)
        a(lambda pc, L_: C.adrp(pc, 'x9', KH))
        a(C.ldr_w('w9', 'x9', C.lo12(KH)))
        a(C.to(C.tbz, 'w9', 16, 'stock'))
        a(uxth_w('w8', 'w9'))
        a(C.to(C.b, 'back'))
        a.label('stock')
        a(stock_word)
        a.label('back')
        a.many(lambda pc, L_: C.far_return(pc, back, 'x16'))
        return a
    return build


_k114 = C.text_word(0x159CA94)
assert _k114 == C.text_word(0x15B4E90)
G3, g3_recs = place('ITEMAUTH_G3', build_g3, 'G3: owner writes the killer handle into the 0x14 request (S4)')
G4, g4_recs = place('ITEMAUTH_G4', build_g4, 'G4: host serves 0x14 with the carried killer (S4)')
G5, g5_recs = place('ITEMAUTH_G5', build_kread(0x159CA98, _k114), 'G5: GIVE killer read uses the carried killer')
G6, g6_recs = place('ITEMAUTH_G6', build_kread(0x15B4E94, _k114), 'G6: rose killer read uses the carried killer')

# ---------------- N1 hardening: G2 also needs record kind 2 / subkind 1 or 3 (msg +0x13C / +0x13D) [V]
stock(0x159C71C, 'ldrb w8, [x19, #0x12c]'); stock(0x159CA38, 'ldrsb w8, [x19, #0x12d]')
_g2 = build_g2(G2)
_g2.words()


def build_g2k(s):
    """From G2 after the marker matched: record kind (msg +0x13C) == 2 and subkind (+0x13D) in {1, 3}, else the
    stock word (a real world item never has that: 0x159CA38 routes 1/3 to the give)."""
    a = C.Asm(s)
    a(C.ldrh('w9', 'sp', 0x350 + 0x13C))
    a(C.cmp_wi('w9', 0x102))
    a(lambda pc, L_: C.beq(pc, _g2.labels['mine']))
    a(C.cmp_wi('w9', 0x302))
    a(lambda pc, L_: C.bne(pc, _g2.labels['stock']))
    a(lambda pc, L_: C.b(pc, _g2.labels['mine']))
    return a


g2k = build_g2k(G2K)
assert len(g2k.words()) <= 8
g2k_recs = g.cave('ITEMAUTH_G2K', G2K, g2k)
groups['ITEMAUTH_GIVE'] = (g1_recs + g7_recs + g2_recs + g2k_recs + g3_recs + g4_recs + g5_recs + g6_recs
                           + g.far_hook(SITE_G2, 'ldr w8, [sp, #0x398]', G2, 'x16', why=WHY_G2,
                                        note='G2 award filter: own player only')
                           + g.far_hook(SITE_G1, 'bl #0x15a3340', G1, 'x16', why=WHY_G1, link=True,
                                        note='G1 give -> award broadcast')
                           + g.far_hook(0x159CA94, 'ldr w8, [x8, #0x114]', G5, 'x16',
                                        why='0x159C6C4 never names x16/x17 (scanned); x9, x16, flags written before '
                                            'read up to the bl at 0x159CA9C (asserted)', note='G5 GIVE killer')
                           + g.far_hook(0x15B4E90, 'ldr w8, [x8, #0x114]', G6, 'x16',
                                        why='0x15B4B00 never names x16/x17 (scanned); x9, x16, flags written before '
                                            'read up to the bl at 0x15B4E98 (asserted)', note='G6 rose killer')
                           + g.far_hook(0x1597CAC, 'bl #0x15b4b00', G4, 'x16', link=True,
                                        why='site is a bl; the reader never needs x16/x17 across a call',
                                        note='G4 serve 0x14 with carried killer')
                           + g.far_hook(0x15AAF64, 'adrp x8, #0x5b3c000', G3, 'x16',
                                        why='0x15AADE0 never names x16/x17 (scanned); x9, x16, flags written before '
                                            'read up to the blr at 0x15AAF88 (asserted)',
                                        note='G3 owner writes killer into 0x14'))

ORDER = ['ITEMAUTH_DROP', 'ITEMAUTH_GIVE', 'ITEMAUTH_LOT', 'ITEMAUTH_PICKONE']
print('\n'.join(L))
print('D1 0x%X  D2 0x%X  table 0x%X' % (D1, D2, TAB))
if DRY:
    print('dry run: nothing claimed or written')
    sys.exit(0)
C.write_live(OUT, groups, ORDER, """Item-authority fixes (offset_from_main, orig_hex, new_hex, is_code). Generated by itemauth_gen.py
(cave_lib checks: stock words, capstone, registry, collisions). NOT live-tested. Notes: itemauth_notes.md.
ITEMAUTH_DROP: apply on EVERY game (only the authority runs 0x15B4320; D1 is harmless elsewhere). Order: table,
D1 cave, D2 cave, trampolines + hooks (hook words last). Works with the gate 0xCF8F74 in any version (stock,
FORGE_OWN, ZEP3_C2). ITEMAUTH_GIVE: apply on EVERY game (G1 acts on the authority, G2 on every receiver); order:
G1 cave, G2 cave, G2 trampoline + hook, G1 trampoline + hook (hook words last). Notes: itemauth2_notes.md.
ITEMAUTH_LOT / ITEMAUTH_PICKONE are EMPTY on purpose (notes section 2, itemauth2_notes.md 4).""")
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write("CAVES = {'D1': 0x%X, 'D2': 0x%X, 'TABLE': 0x%X, 'G1': 0x%X, 'G2': 0x%X, 'D3': 0x%X, 'D4': 0x%X, "
            "'G2K': 0x%X, 'G3': 0x%X, 'G4': 0x%X, 'G5': 0x%X, 'G6': 0x%X, 'KH': 0x%X, 'G7': 0x%X}\n"
            % (D1, D2, TAB, G1, G2, D3, D4, G2K, G3, G4, G5, G6, KH, G7))
    f.write("KMARK = 0x%X\nTAG_LSB = %d\n" % (KMARK, TAG_LSB))
    f.write("GIVE = {'SITE_G1': 0x%X, 'SITE_G2': 0x%X, 'MAGIC': 0x%X, 'GOODS': %r}\n" % (SITE_G1, SITE_G2, MAGIC, goods))
for gname in ORDER:
    if groups[gname]:
        d, r = C.cpp_rows(gname, groups[gname])
        print('### %s\n%s\n%s' % (gname, d, r))
