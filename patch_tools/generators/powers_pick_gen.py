"""powers_pick_gen.py: the "Select what to receive" dialog gives the chosen entry in a LAN match (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py (through cave_lib). Writes powers_pick_live.py and claims its
far ranges in cave_registry.md (owner `powers_pick_gen`).
python powers_pick_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: powers3_notes.md (sections 1-4 = trace, 8 = this group).

Groups
  POWERS_PICK_CAVE  far caves PICK / GIVE, FAR_DATA byte GFLAG (no record: the region starts zeroed), and the two
                    3-word trampolines in the inter-function zero padding 0x15A1308..0x15A131F (NEAR_TRAMP is full;
                    see the notes). Inert until POWERS_PICK points the two sites at them.
  POWERS_PICK       two site words:
     0x15B7F18  dialog OK callback 0x15B7EC4, `cbz w8, #0x15b7f88` (offline byte +0xBDA; reached only when the
                world singleton *(main+0x5B57E90) is set) -> PICK:
                offline (w8 != 0): stock 0x15B7F1C (local 0x15B21A0, unchanged);
                LAN: the item must still exist (0x15A2320(mgr, handle) != 0, else plain return 0x15B7FB0: nothing given);
                GFLAG = 1; the stock local-path words 0x15B7F30..0x15B7F60 (build {id, count, -1} from the
                highlighted entry, x7 = 0 = local chr) and `bl 0x15B5400`; GFLAG = 0; continue at 0x15B7F68 (stock:
                0x159FD80 removes the world item on this game). No 0x1E subtype-8 message is sent.
     0x15B5560  give 0x15B5400, `cbz x8, #0x15b57fc` (world singleton) -> GIVE: GFLAG set or x8 == 0 -> 0x15B57FC
                (stock inventory add 0x15A2820 / 0xCD76C0 / new mark / popup), else 0x15B5564 (stock: popup queue
                only). Every other give in the game runs with GFLAG = 0, i.e. stock."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'powers_pick_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def fn_end(a):
    a += 4
    while W[a // 4] != PACIBSP:
        a += 4
    return a


def names_x16_x17(lo, hi):
    return ['%x' % a for a in range(lo, hi, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]


def targets_in(lo, hi):
    """every b / bl / b.cond / cbz / tbz / adr / literal-load in text whose target is in [lo, hi)"""
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
OK_FN = 0x15B7EC4                      # vt 0x5722220 slot +0x30 (the functor's invoke; the only action slot)
GIVE_FN = 0x15B5400
assert struct.unpack_from('<Q', C.DATA, 0x5722250 - C.DATA_BASE)[0] == OK_FN
for k in range(0x38, 0x48, 8):
    assert struct.unpack_from('<Q', C.DATA, 0x5722220 + k - C.DATA_BASE)[0] == 0      # no other action slot
OK_END, GIVE_END = fn_end(OK_FN), fn_end(GIVE_FN)
assert OK_END == 0x15B8000 and GIVE_END == 0x15B5C80, (hex(OK_END), hex(GIVE_END))
assert not names_x16_x17(OK_FN, OK_END) and not names_x16_x17(GIVE_FN, GIVE_END)
listing.append('x16/x17 never named in 0x%X..0x%X (OK callback) and 0x%X..0x%X (give)' % (OK_FN, OK_END, GIVE_FN, GIVE_END))
# OK callback: frame 0x40 (sp+0x00..0x0F unused on the LAN / local paths), x19 = mgr, x20 = functor,
# x1 = &id (untouched up to the site), w4 = count, w8 = offline byte
for a, t in ((0x15B7EC8, 'sub sp, sp, #0x40'), (0x15B7ED0, 'stp x20, x19, [sp, #0x30]'), (0x15B7EDC, 'ldr w4, [x2]'),
             (0x15B7EE0, 'mov x20, x0'), (0x15B7EE4, 'ldr x19, [x0, #8]'), (0x15B7EF0, 'cbz x8, #0x15b7f30'),
             (0x15B7EF4, 'ldr w2, [x20, #0x10]'), (0x15B7F00, 'ldr w3, [x1]'), (0x15B7F04, 'stp w8, w2, [sp, #0x10]'),
             (0x15B7F0C, 'stp w3, w4, [sp, #0x18]'), (0x15B7F14, 'ldrb w8, [x8, #0xbda]'),
             (0x15B7F18, 'cbz w8, #0x15b7f88'), (0x15B7F1C, 'add x1, sp, #8'), (0x15B7F24, 'str xzr, [sp, #8]'),
             (0x15B7F28, 'bl #0x15b21a0'),
             (0x15B7F30, 'ldrb w9, [x20, #0x10]'), (0x15B7F3C, 'ldr w8, [x1]'), (0x15B7F40, 'stp w4, w10, [sp, #0x14]'),
             (0x15B7F4C, 'mov x7, xzr'), (0x15B7F60, 'ldrb w6, [x20, #0x31]'), (0x15B7F64, 'bl #0x15b5400'),
             (0x15B7F68, 'ldr w1, [x20, #0x10]'), (0x15B7F80, 'bl #0x159fd80'), (0x15B7F88, 'adrp x8, #0x5b3c000'),
             (0x15B7FB0, 'ldp x20, x19, [sp, #0x30]'), (0x15B7FBC, 'retab')):
    stock(a, t)
COPY = list(range(0x15B7F30, 0x15B7F64, 4))           # 13 words, none PC-relative (asserted)
for a in COPY:      # position independent: relocate() gives back the same single word
    assert C.relocate(a, 0xC500000) == [W[a // 4]], C.dis1(a, W[a // 4])
    assert not re.search(r'\b[xw](1[67]|30)\b', C.dis1(a, W[a // 4]))
# no other entry into the copied words / the stock local path except the cbz at 0x15B7EF0
assert targets_in(0x15B7F30, 0x15B7F64) == [0x15B7EF0], [hex(x) for x in targets_in(0x15B7F30, 0x15B7F64)]
# item lookup used as the "still there" test (same call as 0x15B1354: x0 mgr, x1 handle -> record or 0)
stock(0x15B1348, 'mov x1, x23'); stock(0x15B1354, 'bl #0x15a2320'); stock(0x15B135C, 'cbz x0, #0x15b1388')
# give: world singleton test and both continuations; x9 written before read on both (up to the next bl)
for a, t in ((0x15B555C, 'ldr x8, [x8]'), (0x15B5560, 'cbz x8, #0x15b57fc'), (0x15B5564, 'ldur x11, [x29, #-0x20]'),
             (0x15B5568, 'cbnz x11, #0x15b5578'), (0x15B556C, 'sub x0, x29, #0x48'), (0x15B5570, 'bl #0xcd57c0'),
             (0x15B5578, 'ldur x9, [x29, #-0x40]'), (0x15B57FC, 'ldr w2, [x21, #4]'), (0x15B581C, 'bl #0x15a2820')):
    stock(a, t)
for a in list(range(0x15B5564, 0x15B5578, 4)) + list(range(0x15B57FC, 0x15B581C, 4)):
    assert not re.search(r'\bx9\b|\bw9\b', C.dis1(a, W[a // 4])), 'x9 read at %x' % a
for a in (0x15B7F18, 0x15B5560):
    for i in range(4):
        assert a + i not in C.SHIPPED, '%x shipped' % a
# the only built-in word in the OK callback is the subtype-8 send slot (vt+0x48 -> +0x40); PICK bypasses it in LAN
assert sorted(set(x & ~3 for x in range(OK_FN, OK_END) if x in C.SHIPPED)) == [0x15B7FA8]
assert not any(x in C.SHIPPED for x in range(GIVE_FN, GIVE_END))

# trampolines: inter-function zero padding after `b #0x1d26080` (tail call) and before the next pacibsp
PAD_LO, PAD_HI = 0x15A1308, 0x15A1320
stock(PAD_LO - 4, 'b #0x1d26080')
assert W[PAD_HI // 4] == PACIBSP
for a in range(PAD_LO, PAD_HI, 4):
    stock(a, 'udf #0')
assert not targets_in(PAD_LO, PAD_HI) and not qwords_in(PAD_LO, PAD_HI)
assert C.reach(0x15B7F18, PAD_LO) and C.reach(0x15B5560, PAD_LO + 12)
listing.append('trampoline padding 0x%X..0x%X: 6 zero words after a tail call, no branch / adr / literal / data '
               'pointer into it, no shipped or live record (asserted)' % (PAD_LO, PAD_HI))

# ================================================================ caves
g = C.Gen('powers_pick_gen', out=OUT, dry=DRY)
GFLAG = g.alloc('GFLAG', 'FAR_DATA', 4, 'POWERS_PICK: 1 while the dialog OK runs the local give (byte)')
SIZES = {'PICK': 44, 'GIVE': 12}
T_PICK = g.alloc('PICK', 'FAR_CODE', SIZES['PICK'] * 4, 'dialog OK 0x15B7F18: LAN -> local give 0x15B5400 once')
T_GIVE = g.alloc('GIVE', 'FAR_CODE', SIZES['GIVE'] * 4, 'give 0x15B5560: GFLAG -> inventory add 0x15B57FC')

# PICK: entered by `b` from 0x15B7F18 (no link; x30 is saved in the frame, dead here)
a = C.Asm(T_PICK)
a(C.to(C.cbz_w, 'w8', 'lan'))
a.many(lambda pc, L: C.far_jump(pc, 0x15B7F1C))            # offline: stock 0x15B21A0 path
a.label('lan')
a(C.str_x(1, 'sp', 0))                                      # keep &id and count over the lookup
a(C.str_w(4, 'sp', 8))
a(C.mov_x(0, 19))
a(C.ldr_w(1, 20, 0x10))                                     # world-item handle
a.many(lambda pc, L: C.far_call(pc, 0x15A2320))
a(C.to(C.cbnz_x, 'x0', 'give'))
a.many(lambda pc, L: C.far_jump(pc, 0x15B7FB0))            # item gone (phase end / second OK): return, nothing given
a.label('give')
a(C.ldr_x(1, 'sp', 0))
a(C.ldr_w(4, 'sp', 8))
a(lambda pc, L: C.adrp(pc, 9, GFLAG))
a(C.movz_w(10, 1))
a(C.strb(10, 9, C.lo12(GFLAG)))
for s in COPY:
    a.many(lambda pc, L, s=s: C.relocate(s, pc))
a.many(lambda pc, L: C.far_call(pc, GIVE_FN))
a(lambda pc, L: C.adrp(pc, 9, GFLAG))
a(C.strb('wzr', 9, C.lo12(GFLAG)))
a.many(lambda pc, L: C.far_jump(pc, 0x15B7F68))            # stock: remove the item (0x159FD80), return
pick = a

# GIVE: entered by `b` from 0x15B5560, x8 = world singleton
a = C.Asm(T_GIVE)
a(C.to(C.cbz_x, 'x8', 'add'))                               # stock: no world -> inventory add
a(lambda pc, L: C.adrp(pc, 9, GFLAG))
a(C.ldrb(9, 9, C.lo12(GFLAG)))
a(C.to(C.cbnz_w, 'w9', 'add'))
a.many(lambda pc, L: C.far_jump(pc, 0x15B5564))            # stock online: popup queue only
a.label('add')
a.many(lambda pc, L: C.far_jump(pc, 0x15B57FC))
give = a

for _n, _a in (('PICK', pick), ('GIVE', give)):
    assert len(_a.words()) <= SIZES[_n], '%s: %d words > %d' % (_n, len(_a.words()), SIZES[_n])
caves = g.cave('PICK', T_PICK, pick) + g.cave('GIVE', T_GIVE, give)

# trampolines in text padding (text_patch: stock word asserted, collision-checked like every record)
TR_PICK, TR_GIVE = PAD_LO, PAD_LO + 12
tramps = []
for t, tgt in ((TR_PICK, T_PICK), (TR_GIVE, T_GIVE)):
    for k, w in enumerate(C.far_jump(t, tgt)):
        tramps.append(g.text_patch(t + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16: dead at both sites, '
                                                           'functions never name x16/x17)' % tgt))
hooks = [g.text_patch(0x15B7F18, 'cbz w8, #0x15b7f88', C.b(0x15B7F18, TR_PICK), 'PICK (dialog OK, LAN give)'),
         g.text_patch(0x15B5560, 'cbz x8, #0x15b57fc', C.b(0x15B5560, TR_GIVE), 'GIVE (inventory add while GFLAG)')]

groups = {'POWERS_PICK_CAVE': caves + tramps, 'POWERS_PICK': hooks}
order = ['POWERS_PICK_CAVE', 'POWERS_PICK']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('GFLAG byte at main+0x%X (FAR_DATA, no record)' % GFLAG)
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0] + 'GFLAG = main+0x%X.' % GFLAG)
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'PICK': 0x%X, 'GIVE': 0x%X, 'GFLAG': 0x%X, 'TR_PICK': 0x%X, 'TR_GIVE': 0x%X}\n" % (
            T_PICK, T_GIVE, GFLAG, TR_PICK, TR_GIVE))
    for name in order:
        d, r = C.cpp_rows(name, groups[name])
        print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
