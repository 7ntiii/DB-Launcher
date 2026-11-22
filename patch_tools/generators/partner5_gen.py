"""partner5_gen.py: late class-B pairing at every other class-B list test (static generator, helper 4).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes partner5_live.py.
python partner5_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: partner5_notes.md. Generalises LOVE5 (love5_gen.py, 0x118EA34) to the six other callers of the list test
0x119B2A0 (deep_audit_A 4b).

REGISTRY: allocated with Gen(dry=True) (task rule: new files only); the lead adds the row when baking:
  partner5_gen | PARTNER5 | <printed range> | late class-B pairing at the other list tests (LAN)

Groups
  PARTNER5_CAVE  far cave PARTNER5 + one 3-word trampoline in zero padding (bl reach from every site).
  PARTNER5       the six `bl 0x119b2a0` sites -> `bl trampoline` (hooks LAST).
  Why: a class-B list (cond vt 0x56F8E88: Sworn Enemy / Old Friend / Love slot-0 pairing) is filled only by the
  stock pairing add 0x1197C80, which needs the partner CHR loaded (0x1197D78); a partner whose chr loads after
  the pairing frame is never added (the module's +0x79 stays 1; SIGIL13 re-arms only for a NEW SQM entry).
  The cave = LOVE5 with two extra guards:
    (G1) only a cond whose vptr is the class-B vtable 0x56F8E88 (else stock answer: class C / D / variable lists
         are filled by events, not by the pairing);
    (G2) only while that class-B list is EMPTY (+0x58 == 0): at most one late partner, never more than the stock
         first-fit pairing would have made; LOVE5 keeps its own < 8 rule at 0x118EA34.
  Flow: stock test (the caller's w2 kept); pass -> returned unchanged. Else LAN only (mgr3+0x1268 == 6), G1, G2,
  +0xB0 < 8, handle -> chr (0x17E7828(WCM, {u16, 0})), player no = [[chr+0x20]+0x1D0]+0xD0 < 100, slot 0..2:
  STOCK match 0x11979C0(cond, &(no*10+slot)); first match -> STOCK add 0x1197C80; the stock test runs again with
  the caller's w2 and its answer is returned. Offline: stock (mode != 6)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'partner5_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
TEST, MATCH, ADD, RESOLVE = 0x119B2A0, 0x11979C0, 0x1197C80, 0x17E7828
MGR3, WCM = 0x5B3CE08, 0x5B3CD88
CLASSB_VT = 0x56F8E88
LOVE5_SITE = 0x118EA34
# site -> (function start, what it is) [V call shapes; quests per partner5_notes.md 1]
SITES = {
    0x117B744: (0x117B5B0, 'kill check of a listener module (0x11822E0 -> functor 0x1186168), cond = participants root +0x90/+0x98'),
    0x1186554: (0x11864D4, 'functor vt 0x56F6E88 +0x30 (built at 0x1183D38 / 0x1186498): is chr in a participant module list'),
    0x118D0D0: (0x118D094, 'logic vt+0xC8 of vtables 0x56F7408 / 0x56F7858: [logic+0x40]+0x90/+0x98 list test, then state 1'),
    0x11902DC: (0x119029C, 'logic slot data 0x56F8230: cond = logic+0x40 itself (variable list, after 0x1199660)'),
    0x11935C8: (0x1193560, 'activation 0x11771A0 helper: every 0x14-byte entry tested against the cond argument'),
    0x1198D88: (0x1198BE0, 'cond slot data 0x56F9090: cond = [x21+0xC8]+0x110 (else +0x50)'),
}
listing = []


def mul_w(rd, rn, rm):                  # madd wd, wn, wm, wzr
    return 0x1B007C00 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def qword(a):
    return struct.unpack_from('<Q', C.DATA, a - C.DATA_BASE)[0]


def qwords_to(t):
    out = []
    n = len(C.DATA) // 8
    for i, x in enumerate(struct.unpack_from('<%dQ' % n, C.DATA, 0)):
        if x == t:
            out.append(C.DATA_BASE + 8 * i)
    return out


def bl_sites_to(t):
    out = []
    for i, w in enumerate(W):
        if (w & 0xFC000000) == 0x94000000:
            imm = w & 0x3FFFFFF
            if 4 * i + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4 == t:
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
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


def fend(f):
    a = f + 4
    while W[a // 4] != PACIBSP:
        a += 4
    return a


# ================================================================ code facts [V]
callers = bl_sites_to(TEST)
assert sorted(callers) == sorted(list(SITES) + [LOVE5_SITE]), [hex(x) for x in callers]
listing.append('0x119B2A0 has %d bl callers: LOVE5 0x%X + the six PARTNER5 sites' % (len(callers), LOVE5_SITE))
assert qword(CLASSB_VT + 0x10) == 0x1199360 and qword(CLASSB_VT - 0x10) == 0, 'class-B vtable layout'
for a, t in (
        # list test: x0 = &{cond0, cond1, cond2}, x1 = &u16 handle, w2 = flag (kept in w20, passed to vt+0x10)
        (0x119B2B8, 'mov x21, x0'), (0x119B2BC, 'ldr x0, [x0]'), (0x119B2C0, 'mov w20, w2'),
        (0x119B2C4, 'mov x19, x1'), (0x119B2E8, 'ldrh w8, [x19]'), (0x119B318, 'ldrh w11, [x11, #0x78]'),
        # class-B list layout: entries u32 at +0x10, count +0x58 (0x1199D00 reads the same list)
        (0x1199DF0, 'ldr x10, [x21, #0x58]'), (0x1199E04, 'add x8, x21, #0x10'),
        # match / add (as asserted by love5_gen)
        (0x11979D8, 'ldr w8, [x1]'), (0x1197B40, 'ldr w10, [x19, #0xcc]'), (0x1197C9C, 'mov x19, x0'),
        (0x1197CAC, 'ldr w9, [x1]'), (0x1197D78, 'bl #0x17f1940'), (0x1197E44, 'ldr x11, [x19, #0x58]'),
        (0x1197E9C, 'cmp x11, #0x11'), (0x1197EC4, 'cmp x8, #0x11'),
        (0x174EBB4, 'strh w8, [sp, #0x40]'), (0x174EBB8, 'bl #0x17e7828')):
    stock(a, t)
for site, (f, what) in SITES.items():
    assert W[f // 4] == PACIBSP, hex(f)
    e = fend(f)
    assert f < site < e, hex(site)
    stock(site, 'bl #0x119b2a0')
    # every caller passes w2 = 0 just before the call (the cave keeps whatever w2 it gets anyway)
    assert any(C.dis1(a, C.text_word(a)) == 'mov w2, wzr' for a in range(site - 0x24, site, 4)), hex(site)
    for a in range(f, e, 4):
        assert not re.search(r'\b[xw]1[67]\b', C.dis1(a, C.text_word(a))), 'x16/x17 used at %x' % a
    listing.append('site 0x%X in 0x%X..0x%X (%s); slot words %s' % (
        site, f, e, what, ' '.join('0x%X' % x for x in qwords_to(f)) or '-'))

# trampoline padding: 3 zero words right before a pacibsp, unreferenced, free, in bl reach of every site
others = C.live_records(exclude=(OUT,))
PAD = None
for e in range(0x1176000, 0x11A0000, 4):
    if W[e // 4] != PACIBSP:
        continue
    p = e - 12
    if all(W[x // 4] == 0 for x in range(p, e, 4)) and not targets_in(p, e) and             not any(x in C.SHIPPED or x in others for x in range(p, e)):
        PAD = p
        break
assert PAD, 'no trampoline padding'
for site in SITES:
    assert C.reach(site, PAD), hex(site)
listing.append('trampoline padding 0x%X..0x%X (zero, before pacibsp 0x%X, unreferenced, free)' % (PAD, PAD + 12, PAD + 12))

g = C.Gen('partner5_gen', out=OUT, dry=True)
SIZE = 88
T = g.alloc('PARTNER5', 'FAR_CODE', SIZE * 4, 'late class-B pairing at the other list tests (LAN)')
listing.append('cave PARTNER5 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)' % (T, T + SIZE * 4))

a = C.Asm(T)
a(C.stp_pre(29, 30, 31, -0x50))
a(C.add_xi(29, 31, 0))
a(C.stp_x(19, 20, 31, 0x10))
a(C.stp_x(21, 22, 31, 0x20))
a(C.stp_x(23, 24, 31, 0x30))
a(C.mov_x(19, 0))                                        # x19 = &{cond0..2}
a(C.mov_x(20, 1))                                        # x20 = &u16 handle
a(C.mov_w(24, 2))                                        # w24 = the caller's flag
a.many(lambda pc, L: C.far_call(pc, TEST))               # stock list test, caller's x0/x1/w2
a(C.to(C.tbnz, 'w0', 0, 'done'))
a(lambda pc, L: C.adrp(pc, 8, MGR3))
a(C.ldr_x(8, 8, C.lo12(MGR3)))
a(C.to(C.cbz_x, 'x8', 'no'))
a(C.ldr_w(9, 8, 0x1268))
a(C.cmp_wi(9, 6))
a(C.to(C.bne, 'no'))                                     # LAN only
a(C.ldr_x(21, 19, 0))                                    # cond0
a(C.to(C.cbz_x, 'x21', 'no'))
a(C.ldr_x(9, 21, 0))                                     # G1: vptr == class-B vtable
a(lambda pc, L: C.adrp(pc, 10, CLASSB_VT))
a(C.add_xi(10, 10, C.lo12(CLASSB_VT)))
a(C.cmp_xr(9, 10))
a(C.to(C.bne, 'no'))
a(C.ldr_x(9, 21, 0x58))                                  # G2: list empty
a(C.to(C.cbnz_x, 'x9', 'no'))
a(C.ldr_x(9, 21, 0xB0))
a(C.cmp_xi(9, 8))
a(C.to(C.bhs, 'no'))
a(lambda pc, L: C.adrp(pc, 8, WCM))
a(C.ldr_x(0, 8, C.lo12(WCM)))
a(C.to(C.cbz_x, 'x0', 'no'))
a(C.ldrh(9, 20, 0))
a(C.str_w(9, 31, 0x40))                                  # {u16 handle, u16 0}
a(C.add_xi(1, 31, 0x40))
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
a(C.str_w(9, 31, 0x44))
a(C.mov_x(0, 21))
a(C.add_xi(1, 31, 0x44))
a.many(lambda pc, L: C.far_call(pc, MATCH))
a(C.to(C.tbnz, 'w0', 0, 'add'))
a(C.add_wi(23, 23, 1))
a(C.cmp_wi(23, 3))
a(C.to(C.blo, 'loop'))
a(C.to(C.b, 'no'))
a.label('add')
a(C.mov_x(0, 21))
a(C.add_xi(1, 31, 0x44))
a.many(lambda pc, L: C.far_call(pc, ADD))
a(C.mov_x(0, 19))
a(C.mov_x(1, 20))
a(C.mov_w(2, 24))
a.many(lambda pc, L: C.far_call(pc, TEST))               # stock test again: its answer is returned
a(C.to(C.b, 'done'))
a.label('no')
a(C.movz_w(0, 0))
a.label('done')
a(C.ldp_x(23, 24, 31, 0x30))
a(C.ldp_x(21, 22, 31, 0x20))
a(C.ldp_x(19, 20, 31, 0x10))
a(C.ldp_post(29, 30, 31, 0x50))
a(C.RET)
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
for need in ('stp x29, x30, [sp, #-0x50]!', 'ldp x29, x30, [sp], #0x50', 'ret', 'ldr w9, [x8, #0x1268]',
             'ldr x9, [x21]', 'cmp x9, x10', 'ldr x9, [x21, #0x58]', 'ldr x9, [x21, #0xb0]',
             'ldr x9, [x9, #0x1d0]', 'ldr w22, [x9, #0xd0]', 'mul w22, w22, w9', 'ldrh w9, [x20]',
             'str w9, [sp, #0x40]', 'str w9, [sp, #0x44]', 'mov w24, w2', 'mov w2, w24'):
    assert need in dis, need
assert dis[-1] == 'ret'
# no stray "movz w0" path returns before restoring; the 0x40/0x44 slots lie inside the 0x50 frame above x29/x30
for t in dis:
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (0, 1, 2, 8, 9, 10, 16, 19, 20, 21, 22, 23, 24, 29, 30), t

caves = g.cave('PARTNER5', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> PARTNER5 0x%X (x16 unused in the hooked functions)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hooks = [g.text_patch(s, 'bl #0x119b2a0', C.bl(s, PAD), 'list test -> PARTNER5 (%s)' % SITES[s][1][:40])
         for s in sorted(SITES)]
groups = {'PARTNER5_CAVE': caves + tramp, 'PARTNER5': hooks}
order = ['PARTNER5_CAVE', 'PARTNER5']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'PARTNER5': 0x%X, 'TRAMP': 0x%X}\n" % (T, PAD))
