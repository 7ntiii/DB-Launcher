"""powerchoice2_gen.py: row PC, the "Select what to receive" Power choice counts in a LAN match (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py (through cave_lib). Allocated with Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes powerchoice2_live.py.
python powerchoice2_gen.py [--dry]      (from diag/net)
Notes: power_choice_notes.md.

The choice comes first: while a Power dialog is open, the award of the own Power drop only shows its notice and is
HELD (not stored); the dialog's OK then stores the highlighted entry. Every other order keeps today's delivery.
  OPEN  (dialog opener 0x15A4DE0, word 0x15A4F38 `mov w0, #0x38`, after the entry list is built): in a LAN match
        (world singleton set, offline byte +0xBDA == 0) and for a Power dialog (layout flag w24 == 1, or the first
        entry id has type nibble 7) whose handle kind is not 7 / 8: PEND_REC = record + 0x100 (= the functor's
        +0x18, our link from OK to this dialog), PEND_TS = CNTPCT, HELD = 0. Counters for every LAN open.
  ADD3  (give 0x15B5400, word 0x15B555C, replaces the built-in PICKUP_ADD v1 site word, superset of it):
        exactly PICKUP_ADD v1 (award reader chain, local chr, not an 'IGIV' gift -> add), plus:
          - OKGIVE byte set (our OK cave's call) and local chr -> add;
          - v1 would add, the id has type nibble 7 and a Power dialog opened less than 32 s ago (PEND_TS) and is
            not answered -> HELD += 1, HELD_ID = id, x8 stays (stock notice only, nothing stored);
          - v1 would add, other cases -> add (as today), AWARDS_ADDED / LAST_ADD_TS for Power ids.
  OK    (OK functor 0x15B7EC4, word 0x15B7F18 `cbz w8, #0x15b7f88`):
          - offline: stock 0x15B7F1C;
          - LAN, functor +0x18 == PEND_REC and HELD != 0: clear PEND / HELD, GIVEN += 1, GIVEN_ID = the
            highlighted id, OKGIVE = 1, the stock local-give words 0x15B7F30..0x15B7F60 + `bl 0x15B5400`,
            OKGIVE = 0, continue at 0x15B7F68 (stock: 0x159FD80 for a world-item handle). No 0x1E request sent;
          - LAN, functor +0x18 == PEND_REC and HELD == 0 (OK before the award): clear PEND, OK_NOHOLD += 1,
            stock 0x15B7F88 (the late award is then stored as today);
          - else stock 0x15B7F88.
  Decline: nothing (the held Power stays unstored). Exclusive with PICKUP_ADD / PICKUP_ADD2 / STARFRAG_PICK (same
  site word 0x15B555C) and POWERS_PICK / POWERCHOICE (same OK / opener purpose; POWERS_PICK holds 0x15B7F18)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'powerchoice2_live.py'
EXCL = ('pickup_live.py', 'pickup2_live.py', 'starfrag_pick_live.py', 'powers_pick_live.py', 'powerchoice_live.py')
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G, WORLD = 0x5B65C20, 0x5B3CD88, 0x5B57E90
RET_GIVE = (0x15A5184, 0x15A51DC)       # 0x15A5020's two `bl 0x15b5400`, +4
RET_AWARD = 0x15981BC                   # subtype-6 award reader `bl 0x15a5020`, +4
MARKER = 0x56494749                     # 'IGIV'
MARK_OFF = 0x780 - 0x4D8                # marker at reader x29 - 0x2A8 (pickup_gen2 asserts the frame)
SITE_ADD, SITE_OK, SITE_OPEN = 0x15B555C, 0x15B7F18, 0x15A4F38
GIVE_FN, WINDOW_SHIFT = 0x15B5400, 5    # hold window = CNTFRQ << 5 = 32 s
listing = []

# FAR_DATA box layout (the region starts zeroed; no records)
PEND_REC, PEND_TS, HELD, HELD_ID, OPENS_LAN, OPENS_POWER, GIVEN, GIVEN_ID = 0x00, 0x08, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
LAST_FIRST, LAST_HANDLE, LAST_W24, AWARDS_ADDED, OK_NOHOLD, OKGIVE = 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C
LAST_ADD_TS, OPEN_AFTER_AWARD, BOX_SIZE = 0x40, 0x48, 0x50


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


def dis(a):
    return C.dis1(a, W[a // 4])


def names(a, regs):
    return re.search(r'\b[xw](%s)\b' % '|'.join(str(r) for r in regs), dis(a))


# ================================================================ code facts [V]
# --- give 0x15B5400 and the PICKUP_ADD v1 site (everything pickup_gen2 asserts, re-asserted here)
assert fn_end(GIVE_FN) == 0x15B5C80
assert not [a for a in range(GIVE_FN, 0x15B5C80, 4) if W[a // 4] and names(a, (16, 17))]
assert sorted(bl_callers(GIVE_FN)) == [0x15A5180, 0x15A51D8, 0x15B7F64]
assert sorted(bl_callers(0x15A5020)) == [0x15981B8, 0x159AA94, 0x159D9C0, 0x15A44F8, 0x15A4CCC, 0x15AEE18, 0x15AF670]
for a, t in ((0x15B5408, 'stp x29, x30, [sp, #0x150]'), (0x15B5420, 'add x29, sp, #0x150'),
             (0x15B5424, 'mov x19, x7'), (0x15B543C, 'mov x21, x1'), (0x15B5458, 'cbnz x19, #0x15b5474'),
             (0x15B546C, 'ldr x19, [x8, #0x1a8]'), (0x15B54D4, 'ldr w8, [x21]'), (0x15B54DC, 'stp w8, wzr, [x29, #-0x50]'),
             (0x15B54F0, 'and w8, w23, #0xff'), (0x15B54F4, 'cmp w8, #8'), (0x15B54FC, 'cmp w8, #7'),
             (0x15A5028, 'stp x29, x30, [sp, #0x70]'), (0x15A5040, 'add x29, sp, #0x70'),
             (0x15A5180, 'bl #0x15b5400'), (0x15A51D8, 'bl #0x15b5400'), (0x15981B8, 'bl #0x15a5020'),
             (0x1597294, 'stp x29, x30, [sp, #0x40]'), (0x1597298, 'add x29, sp, #0x40'), (0x15972B0, 'sub sp, sp, #0x740'),
             (0x15B5550, 'adrp x8, #0x5b57000'), (0x15B5554, 'add x8, x8, #0xe90'), (0x15B5558, 'ldur w27, [x29, #-0x50]'),
             (SITE_ADD, 'ldr x8, [x8]'), (0x15B5560, 'cbz x8, #0x15b57fc'), (0x15B5564, 'ldur x11, [x29, #-0x20]'),
             (0x15B5578, 'ldur x9, [x29, #-0x40]'), (0x15B57FC, 'ldr w2, [x21, #4]'),
             (0x15B5800, 'and w8, w27, #0xfffffff'), (0x15B5808, 'cmp w8, w24'), (0x15B581C, 'bl #0x15a2820')):
    stock(a, t)
# w27 = the entry id at the site (0x15B54D4 / 0x15B54DC / 0x15B5558); no write to w27 / x19 in between
assert not [a for a in range(0x15B54E0, SITE_ADD, 4) if re.match(r'\S+ (w27|x27|x19|w19)\b', dis(a))
            and not dis(a).startswith(('str', 'stp', 'stur', 'cmp', 'cbz', 'cbnz', 'tbz', 'tbnz'))
            and a != 0x15B5558], 'w27 / x19 written before the site'
assert targets_in(SITE_ADD, SITE_ADD + 4) == []
# x9 / x10 / x11 and NZCV dead on both continuations of 0x15B5560 (first touch is a write / a flag set)
for a in list(range(0x15B5564, 0x15B5578, 4)) + list(range(0x15B57FC, 0x15B581C, 4)):
    assert not names(a, (9, 10)), 'x9/x10 at %x' % a
    assert a < 0x15B57FC or not names(a, (11,)), 'x11 at %x' % a
assert dis(0x15B5808).startswith('cmp')                     # add path: first flag use (0x15B5814 csinv) after a cmp
assert not [a for a in range(0x15B5564, 0x15B5578, 4) if re.match(r'(b\.|csel|csinc|csinv|cset|adc|sbc)', dis(a))]
# the built-in v1 site word (b -> its trampoline) and v1's cave are what ADD3 copies
assert C.dis1(SITE_ADD, C.shipped_word(SITE_ADD)) == 'b #0x1597270'
V1 = 0xC501CB8
v1 = [C.dis1(V1 + 4 * k, C.shipped_word(V1 + 4 * k)) for k in range(45)]
assert v1[0] == 'ldr x8, [x8]' and v1[44] == 'br x16' and v1[41] == 'mov x8, xzr', v1
listing.append('PICKUP_ADD v1 (built in: site b #0x1597270 -> cave 0x%X, 45 words) is copied into ADD3' % V1)

# --- OK functor 0x15B7EC4
OK_FN = 0x15B7EC4
assert struct.unpack_from('<Q', C.DATA if C.DATA_BASE <= 0x5722250 < C.DATA_BASE + len(C.DATA) else C.RO,
                          0x5722250 - (C.DATA_BASE if C.DATA_BASE <= 0x5722250 < C.DATA_BASE + len(C.DATA)
                                       else C.RO_BASE))[0] == OK_FN, 'functor vt 0x5722220 slot +0x30'
OK_END = fn_end(OK_FN)
assert not [a for a in range(OK_FN, OK_END, 4) if W[a // 4] and names(a, (16, 17))]
for a, t in ((0x15B7EC8, 'sub sp, sp, #0x40'), (0x15B7ECC, 'stp x29, x30, [sp, #0x20]'),
             (0x15B7EDC, 'ldr w4, [x2]'), (0x15B7EE0, 'mov x20, x0'), (0x15B7EE4, 'ldr x19, [x0, #8]'),
             (0x15B7EF0, 'cbz x8, #0x15b7f30'), (0x15B7F00, 'ldr w3, [x1]'), (0x15B7F0C, 'stp w3, w4, [sp, #0x18]'),
             (0x15B7F14, 'ldrb w8, [x8, #0xbda]'), (SITE_OK, 'cbz w8, #0x15b7f88'), (0x15B7F1C, 'add x1, sp, #8'),
             (0x15B7F28, 'bl #0x15b21a0'), (0x15B7F30, 'ldrb w9, [x20, #0x10]'), (0x15B7F48, 'ldr x3, [x20, #0x18]'),
             (0x15B7F64, 'bl #0x15b5400'), (0x15B7F68, 'ldr w1, [x20, #0x10]'), (0x15B7F80, 'bl #0x159fd80'),
             (0x15B7F88, 'adrp x8, #0x5b3c000'), (0x15B7FAC, 'blr x8'), (0x15B7FB0, 'ldp x20, x19, [sp, #0x30]')):
    stock(a, t)
COPY = list(range(0x15B7F30, 0x15B7F64, 4))           # 13 stock local-give words, none PC-relative
for a in COPY:
    assert C.relocate(a, 0xC500000) == [W[a // 4]], dis(a)
    assert not names(a, (16, 17, 30))
# x1 (selected entry), x2..x4, x19, x20 untouched from entry to the site; x9..x11 / NZCV dead at both continuations
assert not [a for a in range(0x15B7EE0, SITE_OK, 4) if re.match(r'\S+ (x1|w1|x4|w4|x19|w19|x20|w20)\b', dis(a))
            and not dis(a).startswith(('str', 'stp', 'cbz', 'cbnz')) and a not in (0x15B7EE0, 0x15B7EE4)]
for a in list(range(0x15B7F1C, 0x15B7F28, 4)) + list(range(0x15B7F88, 0x15B7FAC, 4)) + list(range(0x15B7FC0, 0x15B7FE4, 4)):
    assert not names(a, (9, 10, 11)), 'x9-x11 at %x' % a
    assert not re.match(r'(b\.|csel|csinc|csinv|cset|adc|sbc)', dis(a)), 'flags read at %x' % a
assert targets_in(SITE_OK, SITE_OK + 4) == []
# the functor's +0x18 is the opener's x27 = record + 0x100 (0x15A4E90 / 0x15A4F58), +0x10 the handle (0x15A4F48)
for a, t in ((0x15A4E90, 'add x27, x23, #0x100'), (0x15A4F48, 'str w20, [x0, #0x10]'), (0x15A4F58, 'str x27, [x0, #0x18]'),
             (0x15A4F68, 'strb w24, [x0, #0x31]'), (0x15A4F40, 'adrp x8, #0x5722000'), (0x15A4F44, 'add x8, x8, #0x220')):
    stock(a, t)

# --- opener 0x15A4DE0: the hook word after the entry loop
OPEN_FN = 0x15A4DE0
for a, t in ((0x15A4E20, 'mov x20, x2'), (0x15A4E24, 'mov x23, x1'), (0x15A4E50, 'mov w24, #1'), (0x15A4E58, 'mov w24, wzr'),
             (0x15A4E5C, 'ldr w8, [x23, #0x38]'), (0x15A4EB4, 'cbz w28, #0x15a4f38'), (0x15A4EB8, 'add x23, x23, #0x40'),
             (0x15A4EDC, 'b.eq #0x15a4f38'), (0x15A4EE0, 'ldp w8, w9, [x23, #-4]'),
             (SITE_OPEN, 'mov w0, #0x38'), (0x15A4F3C, 'bl #0x4927730'), (0x15A4F78, 'bl #0x14858a0')):
    stock(a, t)
assert bl_callers(0x14858A0) == [0x15A4F78]
# x20 / x24 / x27 not written between their set and the site (x27 only at 0x15A4E90)
assert not [a for a in range(0x15A4E94, SITE_OPEN, 4) if re.match(r'\S+ (x20|w20|x24|w24|x27|w27)\b', dis(a))
            and not dis(a).startswith(('str', 'stp', 'cbz', 'cbnz', 'cmp'))]
assert sorted(targets_in(SITE_OPEN, SITE_OPEN + 8)) == [0x15A4EB4, 0x15A4EDC]   # both enter at the site word
assert not any(x in C.SHIPPED for x in range(OPEN_FN, fn_end(OPEN_FN)))
assert not any(x in C.SHIPPED for x in range(OK_FN, OK_END) if (x & ~3) != 0x15B7FA8)

others = C.live_records(exclude=(OUT,))


def find_pad(site, n, taken):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if any(t <= a < t + 4 * n or a <= t < a + 4 * n for t in taken):
            continue
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


taken = []
PADS = {}
for s in (SITE_ADD, SITE_OK, SITE_OPEN):
    PADS[s] = find_pad(s, 3, taken)
    assert PADS[s], 'no padding for %x' % s
    taken.append(PADS[s])

# ================================================================ caves
g = C.Gen('powerchoice2_gen', out=OUT, dry=True)
for s in (SITE_ADD, SITE_OK, SITE_OPEN):
    for i in range(4):
        if s + i in g.others:
            assert g.others[s + i] in EXCL, 'site %x held by %s' % (s, g.others[s + i])
            del g.others[s + i]
SIZES = {'ADD3': 72, 'PCOK': 56, 'PCOPEN': 56}
BOX = g.alloc('PCBOX', 'FAR_DATA', BOX_SIZE, 'POWER_CHOICE box (pending dialog, held award, counters)', align=8)
T = {n: g.alloc(n, 'FAR_CODE', SIZES[n] * 4, 'POWER_CHOICE %s' % n) for n in SIZES}
BLINK = (0xC501870, 0xC5018A0)        # blink_gen's dry cave (coordinator): keep out
for n, t in T.items():
    assert t + SIZES[n] * 4 <= BLINK[0] or t >= BLINK[1], '%s overlaps the blink cave' % n

MRS_PCT = lambda r: 0xD53BE020 | C.R(r)     # mrs xN, cntpct_el0  (dynarmic: CNTPCT_EL0 / CNTFRQ_EL0 supported)
MRS_FRQ = lambda r: 0xD53BE000 | C.R(r)     # mrs xN, cntfrq_el0
SUB_W9_W10 = 0x4B0A0129
SUB_X11_X11_X9 = 0xCB09016B
LSR_W9_W27_28 = 0x531C7F69
LSR_W9_W11_28 = 0x531C7D69
LSL_X9_X9_5 = 0xD37BE929
CSEL_W11_W11_WZR_NE = 0x1A9F116B
AND_W9_W20_F = 0x12000E89
for w, t in ((MRS_PCT(11), 'mrs x11, cntpct_el0'), (MRS_FRQ(9), 'mrs x9, cntfrq_el0'), (SUB_W9_W10, 'sub w9, w9, w10'),
             (SUB_X11_X11_X9, 'sub x11, x11, x9'), (LSR_W9_W27_28, 'lsr w9, w27, #0x1c'),
             (LSR_W9_W11_28, 'lsr w9, w11, #0x1c'), (LSL_X9_X9_5, 'lsl x9, x9, #%d' % WINDOW_SHIFT),
             (CSEL_W11_W11_WZR_NE, 'csel w11, w11, wzr, ne'), (AND_W9_W20_F, 'and w9, w20, #0xf')):
    assert C.dis1(0, w) == t, (C.dis1(0, w), t)


def movw32(a, r, v):
    a(C.movz_w(r, v & 0xFFFF))
    a(C.movk_w(r, v >> 16, 1))


def box(a, r):
    a(lambda pc, L: C.adrp(pc, r, BOX))
    a(C.add_xi(r, r, C.lo12(BOX)))


def bump(a, rb, off, rt=9):
    a(C.ldr_w(rt, rb, off))
    a(C.add_wi(rt, rt, 1))
    a(C.str_w(rt, rb, off))


def fresh(a, rb, ts_off, stale):
    """x9 = [rb+ts_off]; goes to `stale` unless 0 < now - ts < CNTFRQ << WINDOW_SHIFT. Uses x9, x11."""
    a(C.ldr_x(9, rb, ts_off))
    a(C.to(C.cbz_x, 'x9', stale))
    a(MRS_PCT(11))
    a(SUB_X11_X11_X9)
    a(MRS_FRQ(9))
    a(LSL_X9_X9_5)
    a(C.cmp_xr('x11', 'x9'))
    a(C.to(C.bhs, stale))


# --- ADD3: entered by `b` (trampoline) from 0x15B555C; x8 = &world singleton, w27 = id, x19 = receiving chr
a = C.Asm(T['ADD3'])
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
a(C.to(C.bne, 'back'))                                      # another chr: stock
box(a, 10)
a(C.ldrb(9, 10, OKGIVE))
a(C.to(C.cbnz_w, 'w9', 'add'))                              # our OK cave's give: store it
a(C.ldr_x(9, 29, 8))                                        # 0x15B5400's LR
a(lambda pc, L: C.adrp(pc, 10, 0))
a(SUB_W9_W10)
movw32(a, 10, RET_GIVE[0])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.beq, 'lvl2'))
movw32(a, 10, RET_GIVE[1])
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))
a.label('lvl2')
a(C.ldr_x(11, 29, 0))                                       # 0x15A5020's x29
a(C.to(C.cbz_x, 'x11', 'back'))
a(C.ldr_x(9, 11, 8))                                        # 0x15A5020's LR
a(lambda pc, L: C.adrp(pc, 10, 0))
a(SUB_W9_W10)
movw32(a, 10, RET_AWARD)
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'back'))                                      # other 0x15A5020 callers: stock (as v1)
a(C.ldr_x(11, 11, 0))                                       # reader's x29
a(C.to(C.cbz_x, 'x11', 'back'))
a(C.sub_xi(11, 11, MARK_OFF))
a(C.ldr_w(9, 11, 0))
movw32(a, 10, MARKER)
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.beq, 'back'))                                      # ITEMAUTH_GIVE gift: stock (as v1)
# v1 adds here. New: a Power id while a Power dialog is open -> hold
a(LSR_W9_W27_28)
a(C.cmp_wi('w9', 7))
a(C.to(C.bne, 'add'))
box(a, 10)
fresh(a, 10, PEND_TS, 'award_add')
bump(a, 10, HELD)
a(C.str_w(27, 10, HELD_ID))
a(C.to(C.b, 'back'))                                        # x8 = world: stock notice only, nothing stored
a.label('award_add')
bump(a, 10, AWARDS_ADDED)
a(MRS_PCT(9))
a(C.str_x(9, 10, LAST_ADD_TS))
a.label('add')
a(C.mov_x(8, 'xzr'))                                        # -> 0x15B5560 takes the add branch 0x15B57FC
a.label('back')
a.many(lambda pc, L: C.far_return(pc, 0x15B5560))
add3 = a

# --- PCOK: entered by `b` from 0x15B7F18; w8 = offline byte, x20 = functor, x1 = &selected id, w4 = count
a = C.Asm(T['PCOK'])
a(C.to(C.cbz_w, 'w8', 'lan'))
a.many(lambda pc, L: C.far_jump(pc, 0x15B7F1C))            # offline: stock
a.label('lan')
box(a, 10)
a(C.ldr_x(9, 10, PEND_REC))
a(C.to(C.cbz_x, 'x9', 'stock'))
a(C.ldr_x(11, 20, 0x18))
a(C.cmp_xr('x9', 'x11'))
a(C.to(C.bne, 'stock'))                                     # not the pending Power dialog: stock
a(C.str_x('xzr', 10, PEND_REC))                             # answered: no more holding for it
a(C.str_x('xzr', 10, PEND_TS))
a(C.ldr_w(9, 10, HELD))
a(C.to(C.cbnz_w, 'w9', 'give'))
bump(a, 10, OK_NOHOLD)                                      # OK before the award: the award stores as today
a.label('stock')
a.many(lambda pc, L: C.far_jump(pc, 0x15B7F88))
a.label('give')
a(C.str_w('wzr', 10, HELD))
bump(a, 10, GIVEN)
a(C.ldr_w(9, 1, 0))
a(C.str_w(9, 10, GIVEN_ID))
a(C.movz_w(9, 1))
a(C.strb(9, 10, OKGIVE))
for s in COPY:
    a.many(lambda pc, L, s=s: C.relocate(s, pc))
a.many(lambda pc, L: C.far_call(pc, GIVE_FN))
box(a, 10)
a(C.strb('wzr', 10, OKGIVE))
a.many(lambda pc, L: C.far_jump(pc, 0x15B7F68))            # stock: 0x159FD80 for a world-item handle, return
pcok = a

# --- PCOPEN: entered by `b` from 0x15A4F38; x27 = record + 0x100, w20 = handle, w24 = layout flag
a = C.Asm(T['PCOPEN'])
a(lambda pc, L: C.adrp(pc, 9, WORLD))
a(C.ldr_x(9, 9, C.lo12(WORLD)))
a(C.to(C.cbz_x, 'x9', 'out'))
a(lambda pc, L: C.adrp(pc, 9, OFFL))
a(C.ldr_x(9, 9, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x9', 'out'))
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'out'))                              # offline / no world: stock
box(a, 10)
bump(a, 10, OPENS_LAN)
a(C.ldur_w(11, 27, -0x100 + 0x3C))                          # first entry id (record + 0x3C)
a(C.ldur_w(12, 27, -0x100 + 0x38))                          # entry count (record + 0x38)
a(C.cmp_wi('w12', 0))
a(CSEL_W11_W11_WZR_NE)
a(C.str_w(11, 10, LAST_FIRST))
a(C.str_w(20, 10, LAST_HANDLE))
a(C.str_w(24, 10, LAST_W24))
a(AND_W9_W20_F)
a(C.cmp_wi('w9', 7))
a(C.to(C.beq, 'out'))                                       # handle kind 7 / 8: 0x15B5400 skips the add site
a(C.cmp_wi('w9', 8))
a(C.to(C.beq, 'out'))
a(C.to(C.cbnz_w, 'w24', 'power'))
a(LSR_W9_W11_28)
a(C.cmp_wi('w9', 7))
a(C.to(C.bne, 'out'))                                       # not a Power dialog: stock, nothing pending
a.label('power')
bump(a, 10, OPENS_POWER)
fresh(a, 10, LAST_ADD_TS, 'pend')
bump(a, 10, OPEN_AFTER_AWARD)                               # a Power was stored < 32 s ago: this choice comes late
a.label('pend')
a(C.str_x(27, 10, PEND_REC))
a(MRS_PCT(9))
a(C.str_x(9, 10, PEND_TS))
a(C.str_w('wzr', 10, HELD))
a.label('out')
a(C.movz_w(0, 0x38))                                        # the replaced word
a.many(lambda pc, L: C.far_return(pc, 0x15A4F3C))
pcopen = a

for n, x in (('ADD3', add3), ('PCOK', pcok), ('PCOPEN', pcopen)):
    assert len(x.words()) <= SIZES[n], '%s: %d words > %d' % (n, len(x.words()), SIZES[n])
caves = g.cave('ADD3', T['ADD3'], add3) + g.cave('PCOK', T['PCOK'], pcok) + g.cave('PCOPEN', T['PCOPEN'], pcopen)
# box + 0x3C is the OKGIVE byte; the opener's ldur offsets are in simm9 range (asserted by the encoder)
assert C.dis1(0, C.movz_w(0, 0x38)) == 'mov w0, #0x38'

tramps = []
for s, tgt in ((SITE_ADD, T['ADD3']), (SITE_OK, T['PCOK']), (SITE_OPEN, T['PCOPEN'])):
    p = PADS[s]
    listing.append('trampoline 0x%X..0x%X for 0x%X (zero padding before a pacibsp, unreferenced, free)' % (p, p + 12, s))
    for k, w in enumerate(C.far_jump(p, tgt)):
        tramps.append(g.text_patch(p + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 dead: never named in the '
                                                         'function / a bl follows)' % tgt))
hooks = [g.text_patch(SITE_ADD, 'ldr x8, [x8]', C.b(SITE_ADD, PADS[SITE_ADD]), 'ADD3 (v1 + hold while a Power choice '
                      'is open + OK give)', replaces_shipped=True),
         g.text_patch(SITE_OK, 'cbz w8, #0x15b7f88', C.b(SITE_OK, PADS[SITE_OK]), 'PCOK (LAN OK stores the choice)'),
         g.text_patch(SITE_OPEN, 'mov w0, #0x38', C.b(SITE_OPEN, PADS[SITE_OPEN]), 'PCOPEN (Power dialog pending)')]
# x16 dead at the opener site: next word `bl` (callee-clobbered), nothing between
assert not names(SITE_OPEN + 4, (16, 17))

groups = {'POWER_CHOICE_CAVE': caves + tramps, 'POWER_CHOICE': hooks}
order = ['POWER_CHOICE_CAVE', 'POWER_CHOICE']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('BOX main+0x%X (%#x bytes, FAR_DATA, no records): PEND_REC +0 PEND_TS +8 HELD +10 HELD_ID +14 OPENS_LAN +18 '
      'OPENS_POWER +1C GIVEN +20 GIVEN_ID +24 LAST_FIRST +28 LAST_HANDLE +2C LAST_W24 +30 AWARDS_ADDED +34 '
      'OK_NOHOLD +38 OKGIVE +3C (byte) LAST_ADD_TS +40 OPEN_AFTER_AWARD +48' % (BOX, BOX_SIZE))
print('registry rows (lead adds):')
print('| powerchoice2_gen | PCBOX | 0x%X..0x%X | POWER_CHOICE box: pending Power dialog, held award, counters (FAR_DATA) |'
      % (BOX, BOX + BOX_SIZE))
for n in SIZES:
    print('| powerchoice2_gen | %s | 0x%X..0x%X | POWER_CHOICE %s; trampoline 0x%X..0x%X |' % (
        n, T[n], T[n] + SIZES[n] * 4, {'ADD3': 'give 0x15B555C: PICKUP_ADD v1 + hold + OK give',
                                       'PCOK': 'OK 0x15B7F18: LAN OK stores the highlighted Power',
                                       'PCOPEN': 'opener 0x15A4F38: Power dialog pending'}[n],
        PADS[{'ADD3': SITE_ADD, 'PCOK': SITE_OK, 'PCOPEN': SITE_OPEN}[n]],
        PADS[{'ADD3': SITE_ADD, 'PCOK': SITE_OK, 'PCOPEN': SITE_OPEN}[n]] + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('The choice comes first')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'ADD3': 0x%X, 'PCOK': 0x%X, 'PCOPEN': 0x%X, 'PCBOX': 0x%X, 'PADS': %r}\n" % (
            T['ADD3'], T['PCOK'], T['PCOPEN'], BOX, {hex(k): hex(v) for k, v in PADS.items()}))
        f.write("EXCLUSIVE_WITH = {'POWER_CHOICE': ['PICKUP_ADD', 'PICKUP_ADD2', 'STARFRAG_PICK', 'POWERS_PICK', "
                "'POWERCHOICE']}\n")
