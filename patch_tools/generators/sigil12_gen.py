"""sigil12_gen.py -> sigil12_live.py: group SIGIL12_EYE (Eye of Muralis / Heretic, sigil12_notes.md).
Static only. python sigil12_gen.py   (from diag/net). cave_lib appends its claim rows (owner sigil12_gen) to
cave_registry.md (stable: re-runs reuse them).

SIGIL12_EYE: the Heretic's own game raises step event 1 {Inquisitor's team} on its passive-Heretic (205) module at
the moment the Inquisitor's identification (event 1 {Heretic's team} on the Eye module, sent by the bearer's game)
is applied on the Heretic's game. Hook: module event apply 0x11792E0, event 1 case, the three words after the mask
store (0x11793E4..0x11793EC become an inline `adrp x16 / add x16 / br x16`: the NEAR_TRAMP pool is full). Far cave:
    new = x8 & ~x9 (bits this event raised; x8 = new mask, x9 = old mask at the site)
    if new != 0 and LAN (OFF byte *(main+0x5B65C20)+0xBDA == 0) and the module's logic is the Eye (vt 0x56F7FD0)
       and the LOCAL player's team bit is in `new` (the identified Heretic is this game's player):
         inq = 0x1177B54(eye module)      (stock helper: the module's player chr, used by the module tick)
         if inq and inq != local chr: for each slot of the local player's SQM entry whose logic is the Heretic
             (vt 0x56F7E60): stock 0x117ADB0(heretic module, inq)
    re-run the 3 replaced words (ldr x8, [x19, #0x20]; cbz x8 -> 0x11793FC; ldr x0, [x8, #0x20]) -> 0x11793F0
0x117ADB0 is the stock lock-on / alliance step (bit already set -> nothing; module done -> nothing; Inquisitor not in
the Heretic's condition list -> nothing; else 0x117CAAC event 1 {inq team, flag 0}: owner gate (the Heretic's
game owns his module) + LAN client bit 1 (class 0x59E3450 client mask 0x7F) -> local apply + 0x8B to everyone).
Pays nothing itself. Offline: the cave returns at the OFF test (stock behaviour)."""
import os
import struct

import capstone

import cave_lib as C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = 'sigil12_live.py'
TXT = open(os.path.join(HERE, 'nso', 'main_text.bin'), 'rb').read()
DATA = open(os.path.join(HERE, 'nso', 'main_data.bin'), 'rb').read()
RO = open(os.path.join(HERE, 'nso', 'main_ro.bin'), 'rb').read()
DATA_B, RO_B = 0x563F000, 0x492B000

SITE = 0x11793E4                # event 1 case: word after `str x8, [x19, #0x38]`
FN_LO, FN_HI = 0x11792E0, 0x1179770   # module event apply (next function 0x1179770 starts with pacibsp)
VT_EYE, GOT_EYE = 0x56F7FD0, 0x59E3458
VT_HER, GOT_HER = 0x56F7E60, 0x59E3450
OFFL = 0x5B65C20                # *(main+OFFL)+0xBDA != 0 offline
WCM = 0x5B3CD88                 # *(WCM)+0x1A8 = local player chr
SQM = 0x5B3CE18                 # sub quest manager: [+8, +0x10) entries of 0x20 {u32 player no, 3 module ptrs}
MOD_CHR = 0x1177B54             # module -> its player's chr (pure lookup)
STEP = 0x117ADB0                # stock step: (module, target chr) -> event 1 {target team} if listed and not set
SQM_GOT = 0x59DFF30             # GOT slot the lock-on code uses for the SQM

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
md.detail = True


def q(seg, base, a):
    return struct.unpack_from('<Q', seg, a - base)[0]


def ctx(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %#x: %s != %s' % (a, got, t)


# ------------------------------------------------------------------ context (stock text) [V]
CTX = [
    # event apply: jump table entry for event 1 is 0x1179378
    (0x11792F8, 'and w8, w1, #0xff'), (0x11792FC, 'cmp w8, #5'), (0x1179324, 'br x10'),
    (0x11793C0, 'ldrb w8, [sp, #4]'), (0x11793C4, 'cmp x8, #0xb'), (0x11793CC, 'mov w9, #1'),
    (0x11793D0, 'ldrb w20, [sp, #8]'), (0x11793D4, 'lsl x8, x9, x8'), (0x11793D8, 'ldr x9, [x19, #0x38]'),
    (0x11793DC, 'orr x8, x9, x8'), (0x11793E0, 'str x8, [x19, #0x38]'), (SITE, 'ldr x8, [x19, #0x20]'),
    (0x11793E8, 'cbz x8, #0x11793fc'), (0x11793F8, 'bl #0x1194cd4'), (0x11793FC, 'cbz w20, #0x1179664'),
    (0x1179320, 'mov x19, x0'), (0x11792E4, 'sub sp, sp, #0x60'), (0x11792E8, 'stp x29, x30, [sp, #0x30]'),
    (0x1179664, 'ldp x20, x19, [sp, #0x50]'), (0x1179770, 'pacibsp'),
    # local apply of the sender 0x117CAAC and the receive both end in 0x11792E0
    (0x117CC74, 'bl #0x11792e0'), (0x1178E14, 'bl #0x11792e0'),
    # 0x117ADB0 = the stock step (bit test, logic vt+0x10, cond 0x1199D00, 0x117CAAC)
    (0x117ADB0, 'cbz x1, #0x117af08'), (0x117ADEC, 'ldr x9, [x20, #0x38]'), (0x117AE84, 'bl #0x1199d00'),
    (0x117AEF0, 'bl #0x117caac'),
    # lock-on identification (Inquisitor side): 0x16FF530 -> 0x11835C0 -> 0x117ADB0 for the local modules
    (0x16FF530, 'bl #0x11835c0'), (0x11838A0, 'ldr x8, [x8, #0xe8]'), (0x11838B4, 'bl #0x117adb0'),
    (0x1183888, 'tbnz w8, #5, #0x11838b8'), (0x118380C, 'ldp x21, x8, [x20, #8]'),
    (0x16FF508, 'ldr x8, [x8, #0xf30]'),
    # 0x117CAAC: owner gate, then OFF or writer+0xA0 bit 1
    (0x117CAAC, 'ldrb w8, [x0, #0xa8]'), (0x117CAFC, 'tbz w8, #1, #0x117ccb8'),
    # Heretic logic: vt+0xD0 0x118EF34 needs the other player's team bit in [logic+0x28] = module+0x38
    (0x118F064, 'ldr x9, [x19, #0x28]'), (0x118F08C, 'bl #0x117a9d4'),
    # module -> chr helper
    (MOD_CHR, 'pacibsp'), (0x117786C, 'bl #0x1177b54'),
    # type-15 factory case: the Heretic's condition (lists players holding a type-11 = Eye module, +0xBC = 0xB) is
    # stored at root+0x90 = the only slot 0x117ADB0 reads (0x117AE74 `ldr x0, [x21, #0x90]`)
    (0x1189CA8, 'mov w8, #0xb'), (0x1189CAC, 'strb w8, [x0, #0xbc]'), (0x1189D3C, 'str x21, [x28, #0x90]'),
    (0x1189D68, 'ldr x8, [x8, #0x450]'), (0x1189D90, 'str x28, [x22, #0x40]'), (0x117AE74, 'ldr x0, [x21, #0x90]'),
]
for a, t in CTX:
    ctx(a, t)
assert q(DATA, DATA_B, GOT_EYE) + 0x10 == VT_EYE and q(DATA, DATA_B, GOT_HER) + 0x10 == VT_HER
assert q(DATA, DATA_B, SQM_GOT) == SQM
assert q(DATA, DATA_B, VT_HER + 0xD0) == 0x118EF34 and q(DATA, DATA_B, VT_EYE + 0x20) == 0x118F5E0
assert q(DATA, DATA_B, VT_HER + 0x38) == 0x118F124 and q(DATA, DATA_B, VT_EYE + 0x38) == 0x118FB88
ctx(0x118F124, 'mov w9, #0x860')     # Heretic flags: bit 5 -> the lock-on loop skips it; bit 7 clear -> flag 0
ctx(0x118FB88, 'mov w9, #0x1dc0')    # Eye flags: bit 5 clear (lock-on runs), bit 7 set (notification)
ctx(0x118F130, 'mov w9, #0x60')      # Heretic server mask 0x60: the server could send events 5/6 only
# jump table of the event apply: event 1 -> 0x1179378
jt = RO[0x4C49BC4 - RO_B:0x4C49BC4 - RO_B + 6]
assert 0x1179328 + 4 * jt[1] == 0x1179378, 'event 1 case moved'

# ------------------------------------------------------------------ dead registers after the site [V]
# Every path from SITE+4 to a function exit must WRITE each of x0..x7, x9..x18, x30 before READING it (x8 is
# re-made by the cave). bl / blr clobber x0..x18 + x30; ret / retab read x30; a branch out of the function
# (tail call) counts as reading x0..x7.
TRACK = {'x%d' % i for i in range(0, 19) if i != 8} | {'x30'}
CLOB = {'x%d' % i for i in range(0, 19)} | {'x30'}


def norm(r):
    r = md.reg_name(r)
    r = {'lr': 'x30', 'fp': 'x29', 'ip0': 'x16', 'ip1': 'x17'}.get(r, r)
    if r.startswith('w') and r[1:].isdigit():
        return 'x' + r[1:]
    return r


def succ(i):
    m, a = i.mnemonic, i.address
    if m in ('ret', 'retab', 'br', 'braa', 'brab'):
        return []
    ops = i.operands
    if m == 'b':
        return [ops[0].imm]
    if m.startswith('b.') or m in ('cbz', 'cbnz', 'tbz', 'tbnz'):
        return [ops[-1].imm, a + 4]
    return [a + 4]


def dead_after(start):
    seen, stack, checked = set(), [(start, frozenset())], 0
    while stack:
        pc, wr = stack.pop()
        if (pc, wr) in seen:
            continue
        seen.add((pc, wr))
        if not FN_LO <= pc < FN_HI:          # left the function (tail branch): x0..x7 count as read
            bad = {'x%d' % k for k in range(8)} - wr
            assert not bad, 'tail branch to %x reads %s' % (pc, sorted(bad))
            continue
        ins = next(md.disasm(TXT[pc:pc + 4], pc))
        checked += 1
        rd, wt = ins.regs_access()
        rd = {norm(r) for r in rd}
        wt = {norm(r) for r in wt}
        if ins.mnemonic in ('ret', 'retab'):
            rd |= {'x30'}
        if ins.mnemonic in ('bl', 'blr'):
            wt |= CLOB
            if ins.mnemonic == 'bl' and ins.operands[0].imm in (0x472CA08,):
                continue                   # noreturn abort
        bad = (rd & TRACK) - wr
        assert not bad, '%x %s %s reads %s before any write (not dead after the site)' % (
            pc, ins.mnemonic, ins.op_str, sorted(bad))
        nw = frozenset(wr | (wt & TRACK))
        for s in succ(ins):
            stack.append((s, nw))
    return checked


NCHK = dead_after(SITE + 4)
# x16 / x17 are not read anywhere in the function either (belt and braces for the trampoline scratch)
for a in range(FN_LO, FN_HI, 4):
    ins = next(md.disasm(TXT[a:a + 4], a), None)
    if ins is None:
        continue
    rd, _ = ins.regs_access()
    assert not ({norm(r) for r in rd} & {'x16', 'x17'}), 'x16/x17 read at %x' % a

# ------------------------------------------------------------------ the cave
DRY = os.environ.get('SIGIL12_DRY') == '1'      # 1 = allocate without claiming, write nothing
g = C.Gen('sigil12_gen', out=OUT, dry=DRY)
cave = g.alloc('SIGIL12_EYE', 'FAR_CODE', 0x1C0, 'Heretic game raises step event 1 {Inquisitor team} on its 205 '
               'module when the Eye event 1 for its own team is applied')
a = C.Asm(cave)


def bic_x(rd, rn, rm):
    w = 0x8A200000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
    assert C.dis1(0, w) == 'bic %s, %s, %s' % (rd, rn, rm)
    return w


def lsr_x(rd, rn, rm):
    w = 0x9AC02400 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
    assert C.dis1(0, w) == 'lsr %s, %s, %s' % (rd, rn, rm)
    return w


def hi(lab):
    return lambda pc, L: C.bcond(pc, 'hi', L[lab])


a(C.stp_pre('x29', 'x30', 'sp', -0x30))
a(C.stp_x('x19', 'x20', 'sp', 0x10))
a(C.stp_x('x21', 'x22', 'sp', 0x20))
a(bic_x('x21', 'x8', 'x9'))                      # bits this event raised (0 = already known: nothing new)
a(C.to(C.cbz_x, 'x21', 'out'))
a(lambda pc, L: C.adrp(pc, 'x10', OFFL))
a(C.ldr_x('x10', 'x10', C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldrb('w10', 'x10', 0xBDA))
a(C.to(C.cbnz_w, 'w10', 'out'))                   # offline: stock
a(C.ldr_x('x10', 'x19', 0x20))                   # active holder
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldr_x('x10', 'x10', 0x10))                   # logic
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldr_x('x10', 'x10', 0))
a(lambda pc, L: C.adrp(pc, 'x11', VT_EYE))
a(C.add_xi('x11', 'x11', C.lo12(VT_EYE)))
a(C.cmp_xr('x10', 'x11'))
a(C.to(C.bne, 'out'))                            # only the Eye's identification
a(lambda pc, L: C.adrp(pc, 'x10', WCM))
a(C.ldr_x('x10', 'x10', C.lo12(WCM)))
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldr_x('x22', 'x10', 0x1A8))                  # x22 = local player chr
a(C.to(C.cbz_x, 'x22', 'out'))
a(C.ldr_x('x10', 'x22', 0x20))
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldr_x('x20', 'x10', 0x1D0))                  # x20 = local pgd
a(C.to(C.cbz_x, 'x20', 'out'))
a(C.ldrb('w10', 'x20', 0x104))                   # local team
a(C.cmp_wi('w10', 0xB))
a(hi('out'))
a(lsr_x('x11', 'x21', 'x10'))
a(C.to(C.tbz, 'w11', 0, 'out'))                  # the identified Heretic is not this game's player
a(C.mov_x('x0', 'x19'))
a.many(lambda pc, L: C.far_call(pc, MOD_CHR))    # x0 = the Eye module's player chr (the Inquisitor)
a(C.to(C.cbz_x, 'x0', 'out'))
a(C.cmp_xr('x0', 'x22'))
a(C.to(C.beq, 'out'))                            # never for the local player himself
a(C.mov_x('x21', 'x0'))                          # x21 = Inquisitor chr
a(lambda pc, L: C.adrp(pc, 'x10', SQM))
a(C.ldr_x('x10', 'x10', C.lo12(SQM)))
a(C.to(C.cbz_x, 'x10', 'out'))
a(C.ldp_x('x11', 'x12', 'x10', 8))               # entries [begin, end)
a(C.ldr_w('w13', 'x20', 0xD0))                   # local player no
a.label('find')
a(C.cmp_xr('x11', 'x12'))
a(C.to(C.bhs, 'out'))
a(C.ldr_w('w14', 'x11', 0))
a(C.cmp_wr('w14', 'w13'))
a(C.to(C.beq, 'found'))
a(C.add_xi('x11', 'x11', 0x20))
a(lambda pc, L: C.b(pc, L['find']))
a.label('found')
a(C.mov_x('x20', 'x11'))                         # x20 = local SQM entry (callee-saved across the calls)
for k, off in enumerate((8, 0x10, 0x18)):
    nk = 'next%d' % k
    a(C.ldr_x('x0', 'x20', off))
    a(C.to(C.cbz_x, 'x0', nk))
    a(C.ldr_x('x10', 'x0', 0x20))
    a(C.to(C.cbz_x, 'x10', nk))
    a(C.ldr_x('x10', 'x10', 0x10))
    a(C.to(C.cbz_x, 'x10', nk))
    a(C.ldr_x('x10', 'x10', 0))
    a(lambda pc, L: C.adrp(pc, 'x11', VT_HER))
    a(C.add_xi('x11', 'x11', C.lo12(VT_HER)))
    a(C.cmp_xr('x10', 'x11'))
    a(C.to(C.bne, nk))
    a(C.mov_x('x1', 'x21'))
    a.many(lambda pc, L: C.far_call(pc, STEP))   # stock step on the Heretic module (x0 still = module)
    a.label(nk)
a.label('out')
a(C.ldp_x('x21', 'x22', 'sp', 0x20))
a(C.ldp_x('x19', 'x20', 'sp', 0x10))
a(C.ldp_post('x29', 'x30', 'sp', 0x30))
# the three replaced stock words, then back (x16 = far_return scratch, dead at both targets: walk above)
a(C.ldr_x('x8', 'x19', 0x20))                    # 0x11793E4 ldr x8, [x19, #0x20]
a.many(lambda pc, L: C.relocate(0x11793E8, pc))  # 0x11793E8 cbz x8, #0x11793fc  (cbnz skip + far jump)
a(C.ldr_x('x0', 'x8', 0x20))                     # 0x11793EC ldr x0, [x8, #0x20]
a.many(lambda pc, L: C.far_return(pc, 0x11793F0))
assert len(a.words()) * 4 <= 0x1C0, len(a.words())

# far_call(STEP) needs x0 = module: the slot loop loads x0 from the entry right before; assert no word between the
# `ldr x0, [x20, #off]` and the far_call writes x0 (only x10/x11/x1/x16 are written there).
_w = a.words()
for i, wd in enumerate(_w):
    pc = cave + 4 * i
    t = C.dis1(pc, wd)
    if t.startswith('blr x16'):
        j = i - 1
        while not C.dis1(cave + 4 * j, _w[j]).startswith(('ldr x0, [x20', 'mov x0, x19')):
            ins = next(md.disasm(struct.pack('<I', _w[j]), cave + 4 * j))
            assert 'x0' not in {norm(r) for r in ins.regs_access()[1]}, 'x0 clobbered at %x' % (cave + 4 * j)
            j -= 1

recs = g.cave('SIGIL12_EYE', cave, a)
# The NEAR_TRAMP pool is full (cave_lib alloc: no 12 free bytes), so the trampoline is INLINE: the three stock words
# 0x11793E4..0x11793EC become `adrp x16, cave; add x16, x16, #lo; br x16` and the cave re-runs them (above).
# Needs: x16 dead from 0x11793E4 on (walk: written before read on every path; read nowhere in the function) and
# no branch anywhere in main text into 0x11793E8 / 0x11793EC (scan below).
import array  # noqa: E402
_W = array.array('I')
_W.frombytes(TXT[:len(TXT) // 4 * 4])


def _branch_into(targets):
    hits = []
    for i, w in enumerate(_W):
        pc = 4 * i
        if (w & 0x7C000000) == 0x14000000:                       # b / bl
            imm = w & 0x3FFFFFF
            t = pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:   # b.cond / cbz / cbnz
            imm = (w >> 5) & 0x7FFFF
            t = pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
        elif (w & 0x7E000000) == 0x36000000:                     # tbz / tbnz
            imm = (w >> 5) & 0x3FFF
            t = pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
        else:
            continue
        if t in targets:
            hits.append((pc, t))
    return hits


_hits = _branch_into({0x11793E8, 0x11793EC})
assert not _hits, 'branch into the inline trampoline: %s' % ['%x->%x' % h for h in _hits]
# the event jump table (0x4C49BC4) targets only case starts (asserted above for event 1); adr/br x10 at 0x1179324
for k in range(6):
    assert 0x1179328 + 4 * jt[k] not in (0x11793E8, 0x11793EC)
site_words = [
    g.text_patch(0x11793E4, 'ldr x8, [x19, #0x20]', C.adrp(0x11793E4, 16, cave), 'inline trampoline 1/3'),
    g.text_patch(0x11793E8, 'cbz x8, #0x11793fc', C.add_xi(16, 16, C.lo12(cave)), 'inline trampoline 2/3'),
    g.text_patch(0x11793EC, 'ldr x0, [x8, #0x20]', C.br(16), 'inline trampoline 3/3 -> SIGIL12_EYE'),
]
g.listing.append('  scratch x16 at 0x11793E4: dead-register walk of every path from 0x11793E8 to the exits of '
                 '0x11792E0 (%d words): x0..x7, x9..x18, x30 written before any read; x16/x17 read nowhere in '
                 '0x11792E0..0x1179770; no branch into 0x11793E8 / 0x11793EC (whole-text scan)' % NCHK)
# write order: cave first; the three site words last, in this order (bake-in: all at load; live: hub only)
recs += site_words
GROUPS = {'SIGIL12_EYE': recs}
ORDER = ['SIGIL12_EYE']
if not DRY:
    C.write_live(OUT, GROUPS, ORDER, __doc__ + '\nGenerated by sigil12_gen.py. Inline trampoline (NEAR_TRAMP pool is '
                 'full): the 3 site words 0x11793E4..0x11793EC are not atomic, so LIVE-apply only in the hub (no sigil '
                 'event in flight); caves first, site words last. All games. NOT live-tested.')
print('\n'.join(g.listing))
print('dead-register walk: %d words checked' % NCHK)
decl, rows = C.cpp_rows('SIGIL12_EYE', recs)
print('\n'.join(decl) if isinstance(decl, list) else decl)
print('\n'.join(rows) if isinstance(rows, list) else rows)
