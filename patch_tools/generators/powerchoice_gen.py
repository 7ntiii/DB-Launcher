"""powerchoice_gen.py: in a LAN match, do not open the "Select what to receive" dialog for Powers of Blood, because
its OK can give nothing there; the player keeps the Power of his own per-player drop (auto-take + PICKUP_ADD) and sees
only its pick-up popup (static generator, SAFE PARTIAL of powerchoice_notes.md). Reads nso/*.bin, patch_manager.cpp
and every *_live.py (through cave_lib). Writes powerchoice_live.py and claims its far range in cave_registry.md
(owner `powerchoice_gen`).
python powerchoice_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: powerchoice_notes.md.

Groups
  POWERCHOICE_CAVE  far cave HIDE and its 3-word trampoline in the zero padding 0x15A4DD0..0x15A4DDB (4 zero words
                    after `b #0x15a4d98`, right before 0x15A4DE0; NEAR_TRAMP is full). Inert until POWERCHOICE.
  POWERCHOICE       one site word:
     0x15A4E64  select dialog 0x15A4DE0, `b.hi #0x15a4fc4` (entry count > 16 -> plain return before anything is
                built) -> HIDE: the same plain return 0x15A4FC4 ALSO when ALL of
                  - world singleton *(main+0x5B57E90) != 0 and offline byte *(main+0x5B65C20)+0xBDA == 0: exactly the
                    case in which the dialog's OK 0x15B7EC4 takes its subtype-8 send branch 0x15B7F88, which no game
                    answers in LAN (powers3_notes 2, sigil15_notes 3.1): its OK gives nothing;
                  - the record is a Power choice: the dialog's own "Power layout" flag w24 (0x15A4E50: par+0x2E0
                    +0x15E, record type 3, +0x12E < 2) is 1, or the first entry id (record +0x3C) has type nibble 7
                    (SkillParam = Power of Blood, powers4_notes) and the entry count is not 0.
                Else stock 0x15A4E68 (every offline dialog, every non-Power dialog, and any dialog whose OK would
                give locally)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'powerchoice_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
WORLD_G, OFFL_G = 0x5B57E90, 0x5B65C20
FN, SITE, RET_PLAIN, CONT = 0x15A4DE0, 0x15A4E64, 0x15A4FC4, 0x15A4E68
OK_FN = 0x15B7EC4
PAD = 0x15A4DD0
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
END = fn_end(FN)
assert END == 0x15A5020, hex(END)
assert not [a for a in range(FN, END, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
assert not any(a in C.SHIPPED for a in range(FN, END))
listing.append('0x%X..0x%X: no built-in word, x16/x17 never named (asserted)' % (FN, END))
CALLERS = sorted(bl_callers(FN))
assert CALLERS == [0x1598140, 0x159AA60, 0x159D950, 0x15A4664, 0x15A4C5C, 0x15AEDE4, 0x15AF64C], [hex(x) for x in CALLERS]
# every caller only branches on after the call (the dialog is asynchronous: nothing is read from it)
for c, nxt in ((0x1598140, 'b #0x15973a0'), (0x159AA60, 'b #0x159aaa8'), (0x159D950, 'b #0x159d9d4'),
               (0x15A4664, 'b #0x15a4684'), (0x15A4C5C, 'b #0x15a4cd0'), (0x15AEDE4, 'ldr w1, [sp, #0x78]'),
               (0x15AF64C, 'b #0x15af674')):
    stock(c + 4, nxt)
listing.append('callers %s: each continues without reading a result (dialog is asynchronous)' % [hex(x) for x in CALLERS])
# 0x15A4DE0 entry: x23 = record, w24 = Power layout flag, plain-return path, the site
for a, t in ((0x15A4E24, 'mov x23, x1'), (0x15A4E28, 'ldrb w8, [x8, #0x15e]'), (0x15A4E30, 'cbz w8, #0x15a4e58'),
             (0x15A4E34, 'ldr w8, [x23]'), (0x15A4E3C, 'cmp w8, #3'), (0x15A4E44, 'ldrb w8, [x23, #0x12e]'),
             (0x15A4E50, 'mov w24, #1'), (0x15A4E54, 'b #0x15a4e5c'), (0x15A4E58, 'mov w24, wzr'),
             (0x15A4E5C, 'ldr w8, [x23, #0x38]'), (0x15A4E60, 'cmp w8, #0x10'), (SITE, 'b.hi #0x15a4fc4'),
             (CONT, 'adrp x8, #0x5b3c000'),
             # entries: 12 bytes from record +0x3C (the loop reads [x23+0x40-4]) [V]
             (0x15A4EB8, 'add x23, x23, #0x40'), (0x15A4EE0, 'ldp w8, w9, [x23, #-4]'),
             (0x15A4EEC, 'and w10, w8, #0xf0000000'),
             # functor + UI open, then the epilogue
             (0x15A4F40, 'adrp x8, #0x5722000'), (0x15A4F44, 'add x8, x8, #0x220'), (0x15A4F78, 'bl #0x14858a0'),
             (RET_PLAIN, 'ldp x20, x19, [sp, #0xc0]'), (0x15A4FE0, 'retab')):
    stock(a, t)
assert targets_in(0x15A4E60, CONT) == [] and targets_in(0x15A4E5C, 0x15A4E60) == [0x15A4E54]   # only w24's join
# from the site to the plain return nothing has been allocated or pushed: only 0x15A4E04..0x15A4E60 ran (reads)
for a in range(FN + 4, SITE, 4):
    t = C.dis1(a, W[a // 4])
    assert not t.startswith(('bl ', 'blr ', 'str', 'stur')) or t.startswith('stp x'), 'side effect at %x: %s' % (a, t)
listing.append('0x%X..0x%X before the site: prologue + reads only (no call, no store but the register save)' % (FN, SITE))
# x9 dead at both continuations: written before read (up to the first flag/x9 writer), flags dead at CONT
def first_use(a, lim, reg):
    while a < lim:
        t = C.dis1(a, W[a // 4])
        ops = t.split(' ', 1)[1] if ' ' in t else ''
        regs = re.findall(r'\b[xw](\d+)\b', ops)
        if str(reg) in regs:
            dst = regs[0] == str(reg) and not t.startswith(('str', 'stp', 'stur', 'cmp', 'cmn', 'tst', 'cbz', 'cbnz',
                                                             'tbz', 'tbnz'))
            return 'write' if dst and regs.count(str(reg)) == 1 else 'read'
        if t.startswith(('b ', 'ret', 'bl ', 'blr')):
            return 'call/branch'
        a += 4
    return 'none'


assert first_use(CONT, 0x15A4F40, 9) in ('write', 'call/branch'), first_use(CONT, 0x15A4F40, 9)
assert first_use(RET_PLAIN, 0x15A4FE4, 9) in ('none', 'call/branch')     # epilogue: x9 never named before retab
FLAG_READ = ('b.', 'cs', 'cinc', 'cinv', 'cneg', 'ccmp', 'ccmn', 'adc', 'sbc')
# every path from CONT up to its first flag setter / call: straight to 0x15A4EC0 `b 0x15a4ee0`, then 0x15A4EE0..
# 0x15A4EF8 `cmp w8, w26`; the cbz exits go to 0x15A4F38 (to `cmp x0, x19` 0x15A4F80; bl at 0x15A4F3C clobbers
# flags anyway), 0x15A4FF0 (assert, bl) and 0x15A4E8C / 0x15A4EA4 (inside the straight run)
stock(0x15A4EC0, 'b #0x15a4ee0'); stock(0x15A4F3C, 'bl #0x4927730'); stock(0x15A4FF8, 'bl #0x472f1a0')
for a in list(range(CONT, 0x15A4EC4, 4)) + list(range(0x15A4EE0, 0x15A4EF8, 4)) + [0x15A4F38, 0x15A4FF0, 0x15A4FF4]:
    t = C.dis1(a, W[a // 4])
    assert not t.startswith(FLAG_READ), 'flags read at %x: %s' % (a, t)
stock(0x15A4EF8, 'cmp w8, w26')
for a in range(RET_PLAIN, 0x15A4FE4, 4):
    assert not C.dis1(a, W[a // 4]).startswith(FLAG_READ)
listing.append('x9 and NZCV dead at 0x%X and 0x%X (asserted); x16 dead (never named in the function)' % (CONT, RET_PLAIN))
# the OK callback this group bypasses: LAN branch = subtype-8 send, offline / no-world branches = local gives
for a, t in ((0x15B7EF0, 'cbz x8, #0x15b7f30'), (0x15B7F14, 'ldrb w8, [x8, #0xbda]'), (0x15B7F18, 'cbz w8, #0x15b7f88'),
             (0x15B7F28, 'bl #0x15b21a0'), (0x15B7F64, 'bl #0x15b5400'), (0x15B7F88, 'adrp x8, #0x5b3c000')):
    stock(a, t)
assert struct.unpack_from('<Q', C.DATA, 0x5722250 - C.DATA_BASE)[0] == OK_FN     # functor vt slot +0x30 = OK
# the OK reads the same two globals HIDE reads (world singleton via GOT 0x59E1B28, gamedata +0xBDA)
for a, t in ((0x15B7ED8, 'adrp x8, #0x59e1000'), (0x15B7EE8, 'ldr x8, [x8, #0xb28]'), (0x15B7EEC, 'ldr x8, [x8]'),
             (0x15B7F08, 'adrp x8, #0x5b65000'), (0x15B7F10, 'ldr x8, [x8, #0xc20]')):
    stock(a, t)
assert struct.unpack_from('<Q', C.DATA, 0x59E1B28 - C.DATA_BASE)[0] == WORLD_G      # GOT -> main+0x5B57E90
assert 0x15B7F10 and (OFFL_G & 0xFFF) == 0xC20 and (WORLD_G & 0xFFF) == 0xE90
listing.append('OK 0x15B7EC4: world == 0 -> local give 0x15B7F30, offline != 0 -> 0x15B21A0, else subtype-8 send '
               '0x15B7F88 (no answer in LAN): HIDE fires only in that last case')
# trampoline padding
for a in range(PAD, PAD + 16, 4):
    stock(a, 'udf #0')
stock(PAD - 4, 'b #0x15a4d98')
assert W[FN // 4] == PACIBSP
assert not targets_in(PAD, FN) and not qwords_in(PAD, FN)
assert C.reach(SITE, PAD)
listing.append('trampoline padding 0x%X..0x%X: zero words after an unconditional `b`, before 0x15A4DE0; no branch / '
               'adr / literal / data pointer into it (asserted)' % (PAD, PAD + 12))

# ================================================================ cave
g = C.Gen('powerchoice_gen', out=OUT, dry=DRY)
SIZE = 24
T_HIDE = g.alloc('HIDE', 'FAR_CODE', SIZE * 4, 'select dialog 0x15A4E64: no Power dialog in LAN (its OK is dead there)')
LSR_W9_28 = 0x531C7D29
assert C.dis1(0, LSR_W9_28) == 'lsr w9, w9, #0x1c'

a = C.Asm(T_HIDE)
a(C.to(C.bcond, 'hi', 'plain'))                            # the replaced word (flags of `cmp w8, #0x10`)
a(lambda pc, L: C.adrp(pc, 9, WORLD_G))
a(C.ldr_x(9, 9, C.lo12(WORLD_G)))
a(C.to(C.cbz_x, 'x9', 'stock'))                            # no world: OK gives locally -> keep the dialog
a(lambda pc, L: C.adrp(pc, 9, OFFL_G))
a(C.ldr_x(9, 9, C.lo12(OFFL_G)))
a(C.to(C.cbz_x, 'x9', 'stock'))
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'stock'))                           # offline (bot match): stock
a(C.to(C.cbnz_w, 'w24', 'plain'))                          # Power layout dialog in LAN: hide
a(C.to(C.cbz_w, 'w8', 'stock'))                            # no entries: nothing to test
a(C.ldr_w(9, 23, 0x3C))                                    # first entry id
a(LSR_W9_28)
a(C.cmp_wi('w9', 7))
a(C.to(C.bne, 'stock'))                                    # not a Power: stock
a.label('plain')
a.many(lambda pc, L: C.far_return(pc, RET_PLAIN))           # plain return: no functor, no UI, nothing given
a.label('stock')
a.many(lambda pc, L: C.far_return(pc, CONT))
hide = a
assert len(hide.words()) <= SIZE, len(hide.words())
caves = g.cave('HIDE', T_HIDE, hide)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> HIDE 0x%X (x16 never named in 0x15A4DE0)' % T_HIDE)
         for k, w in enumerate(C.far_jump(PAD, T_HIDE))]
hook = [g.text_patch(SITE, 'b.hi #0x15a4fc4', C.b(SITE, PAD), 'POWERCHOICE (no dead Power dialog in LAN)')]

groups = {'POWERCHOICE_CAVE': caves + tramp, 'POWERCHOICE': hook}
order = ['POWERCHOICE_CAVE', 'POWERCHOICE']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0])
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'HIDE': 0x%X, 'TRAMP': 0x%X}\n" % (T_HIDE, PAD))
    for name in order:
        d, r = C.cpp_rows(name, groups[name])
        print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
