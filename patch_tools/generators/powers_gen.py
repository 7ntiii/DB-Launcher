"""powers_gen.py: Powers of Blood from blood roses and from Trespassers in LAN (static generator).
Reads nso/*.bin, the decoded gameparam (diag/scripts_decoded), patch_manager.cpp and every *_live.py (through
cave_lib). Writes powers_live.py and claims its cave ranges in cave_registry.md (owner `powers_gen`).
python powers_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: powers_notes.md.

Groups
  POWERS_ROSE        EMPTY on purpose. The action-menu rose assets (99260..99271, kind 2, button 4610) have no
                     processor (the manager ctor never fills kind 1 / 2) and no MSB part; the real blood roses of
                     great foes are per-player world items (NpcParam +0x4D4 lot -> 0x15B4B00 -> 0x15B0B40 subkind 4)
                     created on the item authority and pushed by the shipped ITEMS cave_push. Asserted below.
  POWERS_CAVES       far caves TLOT / CREATE / KSKIP (+ FAR_DATA flag byte, no record).
  POWERS_TRESPASSER  three hooks:
     0x10211F0  End `bl 0x15b0b40` (the participant's tier lot)  -> TLOT: offline tail-call (stock); LAN: flag = 1
                around the call (the stack argument byte is re-made: 0), flag = 0 after.
     0x15B12C8  0x15B0B40 `bl 0x159c6c4` (item create)          -> CREATE: flag 0 -> stock create; flag 1 -> run
                0x159C6C4 from a copy of its prologue straight to 0x159C714 (skips the shipped I3 "authority only"
                gate: the participant's own game creates its own Power drop, the shipped cave_push sends it to
                all games) and return the record id (the mode-6 create is deferred, so the stock lookup 0x15A2320
                would return -0x20 and the instance would never get the handle +0x3A8).
     0x1020FF8  End `bl 0x1047420` (kind-2 member send of +0x3A8) -> KSKIP: offline stock; LAN: the send goes out
                with the value -0x20 instead of the own handle (each game sets its own +0x3A8 at 0x1020FCC; a peer
                must never get someone else's handle, but every peer still gets the "no handle" answer, which
                clears its +0x3B8 wait timer at 0x1023B30, as the earlier LAN build did).  [review9 N3]
     0x101DA58  per-frame auto-take step, first word after the +0x378 check -> RETRY: LAN only: if the own
                drop id (+0x3A8) is not yet in the world list (+0x1B8) the step waits (back to 0x101DECC, +0x3A8
                kept) for at most RETRY_N calls, tracked in the 4-entry table RT {id, left} that ages every
                entry on each wait; found / expired / offline -> the stock path runs once.  [review9 S2]
  CREATE also tags the record id (bits 27..30 = own player number & 0xF, cave CTAG) so a Power drop made on one
  game can never share an id with an item another game made.  [review9 S1]
  Review 9 fixes: review9_fix_notes.md."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'powers_live.py'
OFFL = 0x5B65C20
PARAMS = os.path.join(HERE, '..', 'scripts_decoded', 'param', 'gameparam', 'gameparam_nt.parambnd')
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def fn_end(a):
    """first pacibsp after a (end of the function that starts at or before a)"""
    a += 4
    while W[a // 4] != PACIBSP:
        a += 4
    return a


def names_x16_x17(lo, hi):
    hits = []
    for a in range(lo, hi, 4):
        t = C.dis1(a, W[a // 4])
        if re.search(r'\b[xw]1[67]\b', t):
            hits.append('%x %s' % (a, t))
    return hits


def bl_callers(target):
    out = []
    for i, w in enumerate(W):
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == target:
                out.append(4 * i)
    return out


def rows(name):
    b = open(os.path.join(PARAMS, name), 'rb').read()
    n = struct.unpack_from('<H', b, 0xA)[0]
    return b, [struct.unpack_from('<ixxxxq', b, 0x40 + k * 24) for k in range(n)]


def ro_u32(a, n):
    return struct.unpack_from('<%dI' % n, C.RO, a - C.RO_BASE)


# ================================================================ data facts [V]
lb, lr = rows('ItemLotParam.param')
LOT = dict(lr)


def lot_entries(i):
    o = LOT[i]
    ids = struct.unpack_from('<8i', lb, o)
    cats = struct.unpack_from('<8i', lb, o + 0x20)
    w = struct.unpack_from('<8H', lb, o + 0x40)
    return [(ids[k], cats[k], w[k]) for k in range(8) if cats[k] or ids[k] or w[k]]


CAT_TYPE = ro_u32(0x4C4CA28, 20)              # lot category -> item type nibble (0x15B0F44 `ldr w14,[x13,x14,lsl#2]`)
stock(0x15B0F3C, 'adrp x13, #0x4c4c000'); stock(0x15B0F40, 'add x13, x13, #0xa28')
POWER_CATS = [c for c in range(20) if CAT_TYPE[c] == 7]
assert POWER_CATS == [8, 11, 12, 13, 14], POWER_CATS          # type 7 = SkillParam (Power of Blood) [V 0x15B0FFC]
sb, sr = rows('SkillParam.param')
SKILL_IDS = set(r for r, _ in sr)

# Trespasser lots: JointStruggleParam (getter 0x155D5A0, file offset = memory offset) +4/+0x5C/+0x70, counts +8/+9/+0xA
for a, t in ((0x1020F54, 'cmp w28, #2'), (0x1020F5C, 'cmp w28, #1'), (0x1020F68, 'add x9, x8, #4'),
             (0x1020F6C, 'add x8, x8, #8'), (0x1021188, 'add x9, x8, #0x70'), (0x102118C, 'add x8, x8, #0xa'),
             (0x1021194, 'add x9, x8, #0x5c'), (0x1021198, 'add x8, x8, #9'), (0x10211A8, 'ldrsb w5, [x8]'),
             (0x10211E0, 'mov w7, #2'), (0x10211DC, 'mov w6, #1'), (0x10211E4, 'strb wzr, [sp]'),
             (0x10211F0, 'bl #0x15b0b40'), (0x10211F4, 'mov w22, w0'), (0x1020D54, 'ldrb w28, [x8, #4]'),
             (0x1020D58, 'ldrb w23, [x8, #5]'), (0x1020DF8, 'cbz w23, #0x1020ec0')):
    stock(a, t)
jb, jr = rows('JointStruggleParam.param')
n_rows = n_power_lots = 0
missing_powers = set()
for rid, off in jr:
    if rid == 0:
        continue
    n_rows += 1
    for lf, cf in ((4, 8), (0x5C, 9), (0x70, 0xA)):
        lid = struct.unpack_from('<i', jb, off + lf)[0]
        cnt = struct.unpack_from('<b', jb, off + cf)[0]
        assert lid in LOT and cnt == 2, 'JointStruggleParam %d +%x lot %d count %d' % (rid, lf, lid, cnt)
        ent = lot_entries(lid)
        if any(c in POWER_CATS for _, c, _ in ent):
            n_power_lots += 1
        for i, c, w in ent:
            if c == 8 and i not in SKILL_IDS:
                missing_powers.add(i)
listing.append('Trespasser rows %d, tier lots %d, lots with a Power entry %d (category 8 / 11..14 = type 7), count 2'
               % (n_rows, 3 * n_rows, n_power_lots))
listing.append('category-8 Power ids not in the romfs SkillParam copy (regulation may hold them): %s'
               % (sorted(missing_powers) or '-'))
assert n_power_lots >= 3 * n_rows - 12, 'fewer Power lots than expected: re-judge'

# Great-foe roses: NpcParam +0x4D4 lot, count +0x4C9 -> 0x15B0B40 (per player = enemy +0x114 last attacker)
for a, t in ((0x15B4E90, 'ldr w8, [x8, #0x114]'), (0x15B4ED8, 'ldr w2, [x8, #0xd0]'),
             (0x15B4EE4, 'ldr w4, [x8, #0x4d4]'), (0x15B4EE8, 'ldrb w5, [x8, #0x4c9]'), (0x15B4F44, 'mov w7, #2'),
             (0x15B4F4C, 'bl #0x15b0b40')):
    stock(a, t)
assert sorted(bl_callers(0x15B4B00)) == [0x1597CAC, 0x15AAF5C]      # the 0x1E drop request (authority, ITEMS)
nb, nr = rows('NpcParam.param')
roses = [(rid, struct.unpack_from('<i', nb, off + 0x4D4)[0]) for rid, off in nr
         if struct.unpack_from('<i', nb, off + 0x4D4)[0] >= 0]
assert roses and all(v in LOT for _, v in roses)
rose_power = [r for r, v in roses if any(c in POWER_CATS for _, c, _ in lot_entries(v))]
listing.append('great-foe rose lots (NpcParam +0x4D4): %d rows, %d with Power entries: %s' % (
    len(roses), len(rose_power), ', '.join(str(r) for r in rose_power)))

# Action-menu rose assets: kind 2 button 4610, no processor, no MSB part
ab, ar = rows('AssetEnvironmentGeometryParam.param')
rose_assets = [rid for rid, off in ar if ab[off + 0x128] == 2]
assert rose_assets == [99260, 99261, 99262, 99263, 99264, 99265, 99266, 99267, 99270, 99271], rose_assets
for rid, off in ar:
    if rid in rose_assets:
        assert struct.unpack_from('<i', ab, off + 0x124)[0] == 4610
        assert struct.unpack_from('<i', ab, off + 0x188)[0] == -1         # no goods (forges use +0x188)
CTOR, CTOR_END = 0x11A17AC, 0x11A1AA8
stock(CTOR_END, 'retab')
proc_slots = sorted(((W[a // 4] >> 10) & 0xFFF) * 8 for a in range(CTOR, CTOR_END, 4)
                    if (W[a // 4] & 0xFFC003FF) == 0xF9000260)          # str x0, [x19, #imm]
assert proc_slots == [0x20, 0x28, 0x30, 0x38, 0x40, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78], proc_slots
listing.append('action-menu processors (mgr+8+kind*8) set by ctor 0x11A17AC: kinds %s; kinds 0/1/2/8 none -> rose '
               'asset kind 2 has no handler [V]' % [(s - 8) // 8 for s in proc_slots])

# SKILL_LOCAL dialog = local player only: 0x15B05B0 uses the LOCAL chr's player number for 0xCFE9A8
for a, t in ((0x15B05E8, 'ldr x8, [x8, #0x1a8]'), (0x15B0618, 'ldr w8, [x8, #0xd0]'), (0x15B0650, 'bl #0xcfe9a8')):
    stock(a, t)
assert sorted(bl_callers(0xCFE9A8)) == [0x15B0650, 0x15B3888]
listing.append('skill-enhancement lot 0xCFE9A8 callers 0x15B0650 (local chr WCM+0x1A8 player no) and 0x15B3888')

# ================================================================ code facts behind the three hooks [V]
END_LO, END_HI = 0x1020C40, 0x1021380
LOT_LO, LOT_HI = 0x15B0B40, 0x15B1318
CR_LO = 0x159C6C4
CR_HI = fn_end(CR_LO)
stock(LOT_HI, 'udf #0')
for lo, hi in ((END_LO, END_HI), (CR_LO, CR_HI)):
    assert not names_x16_x17(lo, hi), names_x16_x17(lo, hi)
# 0x15B0B40 uses w16/w17 only in its entry-list copy loop 0x15B0F08..0x15B0F6C (w17 saved to [sp+0xC] there); the
# site 0x15B12C8 is a bl (x16/x17 corruptible across it) and nothing after it names them -> dead at the hook
_lot_x16 = names_x16_x17(LOT_LO, LOT_HI)
assert all(0x15B0F08 <= int(h.split()[0], 16) <= 0x15B0F6C for h in _lot_x16), _lot_x16
assert not names_x16_x17(0x15B1110, LOT_HI)
listing.append('x16/x17 never named in End 0x%X..0x%X and 0x159C6C4..0x%X; in 0x15B0B40 only in 0x15B0F08..0x15B0F6C '
               '(before the hook, not live across it)' % (END_LO, END_HI, CR_HI))
assert sorted(bl_callers(0x15B0B40)) == [0xE96EE8, 0x10211F0, 0x15AC364, 0x15B4F4C, 0x15B7C74]
assert sorted(bl_callers(0x1047420)) and 0x1020FF8 in bl_callers(0x1047420)
# 0x15B0B40: stack argument byte read at [x29+0x60] (= caller sp+0), id kept at [x29-0x18], create + lookup
for a, t in ((0x15B0B44, 'str d10, [sp, #-0x80]!'), (0x15B0B50, 'add x29, sp, #0x20'),
             (0x15B0F08, 'ldrb w17, [x29, #0x60]'), (0x15B0E48, 'stur x13, [x29, #-0x18]'),
             (0x15B0E34, 'stp w13, w10, [sp, #0x70]'), (0x15B0E4C, 'strb w26, [sp, #0x19c]'),
             (0x15B0E80, 'mov w8, #4'), (0x15B0E84, 'strb w8, [sp, #0x19d]'),
             (0x15B12C8, 'bl #0x159c6c4'), (0x15B12CC, 'mov x0, x19'), (0x15B12D0, 'ldur x19, [x29, #-0x18]'),
             (0x15B12D8, 'bl #0x15a2320'), (0x15B12E4, 'csel w0, w8, w19, eq'), (0x15B12E8, 'b #0x15b10e8')):
    stock(a, t)
# 0x159C6C4: prologue words that the CREATE copy re-runs, then the shipped I3 gate at 0x159C704..0x159C710
PRO = list(range(0x159C6C4, 0x159C700, 4))
assert C.dis1(0x159C700, W[0x159C700 // 4]) == 'cbz x8, #0x159c778'
for a in range(0x159C704, 0x159C714):
    assert a in C.SHIPPED, 'ITEMS I3 not shipped at %x: re-judge' % a
assert C.dis1(0x159C710, C.shipped_word(0x159C710)) == 'cbnz w8, #0x159ca1c', 'I3 changed'
stock(0x159C714, 'ldrb w8, [x19]'); stock(0x159CA34, 'retab'); stock(0x159CA30, 'ldp x29, x30, [sp], #0x50')
stock(0x159CA38, 'ldrsb w8, [x19, #0x12d]')
for a in PRO:   # only the adrp is PC-relative; everything else is copied verbatim
    t = C.dis1(a, W[a // 4])
    assert not t.startswith(('b ', 'bl ', 'b.', 'cbz', 'cbnz', 'tb', 'adr ', 'ldr x8, #', 'ldr w8, #')), t
# End: +0x3A8 set from 0x15B0B40's result, then the kind-2 member send
for a, t in ((0x1020FCC, 'str w22, [x19, #0x3a8]'), (0x1020FF8, 'bl #0x1047420'), (0x1020FFC, 'ldr x8, [x20]'),
             (0x1020F3C, 'adrp x8, #0x5b65000')):
    stock(a, t)
assert 0x1020F3C in C.SHIPPED, 'COOP2_REWARD_OWN (LOWN) not built in: POWERS_TRESPASSER needs it'
for a in (0x10211F0, 0x1020FF8, 0x15B12C8):
    for i in range(4):
        assert a + i not in C.SHIPPED, '%x shipped' % a

# ---------------------------------------------------------------- review 9 facts [V]
GDM = 0x5B57EB8                        # *(GDM)+0x20 = local pgd, +0xD0 = own player number (1..8 in LAN)
# S1: id = (counter << 5) | 0x19; it lives only at record +0 (sp+0x70 = x1 of the create) and [x29-0x18]
for a, t in ((0x15B0D5C, 'ldr x9, [x9, #0xd48]'), (0x15B0D78, 'ldr w11, [x9, #0x24]'),
             (0x15B0D84, 'orr w8, w8, w11, lsl #5'), (0x15B0DA4, 'orr w13, w8, w10'), (0x15B0DF4, 'str w8, [x9, #0x24]'),
             (0x15B12A8, 'add x1, sp, #0x70')):
    stock(a, t)
_ids = [a for a in range(0x15B0DA8, 0x15B12C8, 4) if re.search(r'\b[xw]13\b', C.dis1(a, W[a // 4]))]
assert _ids == [0x15B0E34, 0x15B0E48, 0x15B0F3C, 0x15B0F40, 0x15B0F4C], [hex(x) for x in _ids]   # +0 / -0x18, then x13 reused
# lookup 0x15A2320 picks a bucket by id & 0xF and compares the FULL 32-bit id (high bits are free for a tag)
for a, t in ((0x15A2330, 'and x16, x1, #0xe'), (0x15A2368, 'and x8, x1, #0xf'), (0x15A2380, 'ldr w8, [x0, #0x30]'),
             (0x15A2384, 'cmp w8, w1')):
    stock(a, t)
# End / step / receiver accept the tagged id: invalid only if id > 0xFFFFFFDF or (id & 0xF) == 0
for a, t in ((0x1020FBC, 'cmn w22, #0x21'), (0x1020FC4, 'and w8, w22, #0xf'), (0x101DA10, 'cmn w8, #0x21'),
             (0x101DA18, 'and w9, w8, #0xf'), (0x102366C, 'cmn w8, #0x21'), (0x1023674, 'and w9, w8, #0xf')):
    stock(a, t)
# S2: the step 0x101DA0C.. (function 0x101BB40..0x101F300, never names x16/x17)
STEP_FN, STEP_END = 0x101BB40, fn_end(0x101BB40)
assert STEP_END == 0x101F300 and not names_x16_x17(STEP_FN, STEP_END)
for a, t in ((0x101DA24, 'ldr x21, [x21, #0xed8]'), (0x101DA28, 'ldr x10, [x21]'), (0x101DA2C, 'cbz x10, #0x101e7d8'),
             (0x101DA3C, 'b.eq #0x101da58'), (0x101DA54, 'b.ne #0x101da40'), (0x101DA58, 'ldr x8, [x28]'),
             (0x101DA5C, 'str wzr, [x19, #0x3b8]'), (0x101DA98, 'bl #0x1182e4c'),
             (0x101DE68, 'ldr x8, [x21]'), (0x101DE70, 'ldr x8, [x8, #0x1b8]'), (0x101DE78, 'ldr w11, [x19, #0x3a8]'),
             (0x101DE80, 'ldr w12, [x8, #0x30]'), (0x101DE8C, 'ldr x8, [x8, #8]'), (0x101DE94, 'b #0x101dec4'),
             (0x101DEC4, 'mov w8, #-0x20'), (0x101DEC8, 'str w8, [x19, #0x3a8]'), (0x101DECC, 'ldr s0, [x19, #0x3b8]'),
             (0x101DEF4, 'bl #0x1028600')):
    stock(a, t)
for a in range(STEP_FN, STEP_END, 4):          # only DA3C (b.eq) and the fallthrough reach 0x101DA58; x21 not rewritten
    t = C.dis1(a, W[a // 4]) if W[a // 4] else ''
    if t.endswith('#0x101da58'):
        assert a == 0x101DA3C, 'other branch to 0x101DA58 at %x' % a
for a in range(0x101DA28, 0x101DA58, 4):     # straight line from the x21 load to the hook (loop DA40..DA54)
    assert not re.match(r'\S+ (x21|w21)\b', C.dis1(a, W[a // 4])), 'x21 written at %x' % a
# N3: the kind-2 send passes the value by pointer [sp+0x1c] (written only at 0x1020FAC); the receiver takes
# -0x20 as "no handle" and only clears +0x3B8 (0x102366C b.hi -> 0x1023B30)
for a, t in ((0x1020FAC, 'str w22, [sp, #0x1c]'), (0x1020FE0, 'add x8, sp, #0x1c'), (0x1020FE8, 'stp x9, x8, [sp, #0x50]'),
             (0x1020FF4, 'add x3, sp, #0x50'), (0x1023670, 'b.hi #0x1023b30'), (0x1023B30, 'str wzr, [x19, #0x3b8]'),
             (0x102367C, 'str w8, [x19, #0x3a8]')):
    stock(a, t)
assert [a for a in range(END_LO, END_HI, 4) if '#0x1c]' in C.dis1(a, W[a // 4])] == [0x1020FAC]


def acc(t, r):
    """'w' / 'r' / None: what instruction text t does FIRST with register number r (or 'nzcv')."""
    mn, _, ops = t.partition(' ')
    if r == 'nzcv':
        if mn.startswith('b.') or mn in ('csel', 'cset', 'csinc', 'csinv', 'csneg', 'cinc', 'ccmp', 'ccmn',
                                         'adc', 'sbc', 'adcs', 'sbcs', 'cneg', 'csetm', 'fccmp', 'fcsel'):
            return 'r'
        return 'w' if mn in ('cmp', 'cmn', 'tst', 'adds', 'subs', 'ands', 'bics', 'negs', 'fcmp', 'fcmpe') else None
    if not re.search(r'\b[xw]%d\b' % r, ops):
        return 'w' if mn in ('bl', 'blr') and r in (9, 10, 11, 12, 16, 17) else None   # caller-saved: dead across a call
    parts = [p.strip() for p in re.split(r',(?![^\[]*\])', ops)]
    nd = 2 if mn in ('ldp', 'ldpsw') else 1
    if (mn in ('b', 'bl', 'br', 'blr', 'ret', 'cmp', 'cmn', 'tst', 'cbz', 'cbnz', 'tbz', 'tbnz', 'ccmp', 'ccmn',
               'bfi', 'bfxil', 'movk') or mn.startswith(('b.', 'st'))):
        return 'r'
    if any(re.fullmatch(r'[xw]%d' % r, d) for d in parts[:nd]) and \
            not any(re.search(r'\b[xw]%d\b' % r, p) for p in parts[nd:]):
        return 'w'
    return 'r'


def dead_on(paths, regs, why):
    """Every path (list of (start, end) inclusive segments, ending at a bl) writes each reg before reading it."""
    for path in paths:
        for r in regs:
            seen = None
            for s, e in path:
                for a in range(s, e + 4, 4):
                    k = acc(C.dis1(a, W[a // 4]), r)
                    if k:
                        seen = k
                        break
                if seen:
                    break
            assert seen in ('w', None), '%s: %s read first on path %s' % (why, r, path)


# RETRY returns: 0x101DA5C (stock, after re-running `ldr x8, [x28]`) and 0x101DECC (wait); 0x101EECC / 0x101EA54
# are assert paths (bl 0x472f1a0)
stock(0x101EECC, 'adrp x0, #0x59df000'); stock(0x101EED4, 'bl #0x472f1a0'); stock(0x101EA5C, 'b #0x101eed4')
dead_on([[(0x101DA5C, 0x101DA98)], [(0x101DA5C, 0x101DA68), (0x101DEC4, 0x101DEF4)],
         [(0x101DA5C, 0x101DA78), (0x101EA54, 0x101EA5C), (0x101EED4, 0x101EED4)]],
        (9, 10, 11, 12, 16, 'nzcv'), 'RETRY stock path')
dead_on([[(0x101DECC, 0x101DEF4)]], (8, 9, 10, 11, 12, 16, 'nzcv'), 'RETRY wait path')
# KSKIP LAN tail-jumps into 0x1047420 (function entry: x9 / x16 free)
stock(0x1047420, 'pacibsp')


def movn_w(rd, imm16):
    return 0x12800000 | (imm16 << 5) | C.R(rd)


def bfi_w(rd, rn, lsb, width):
    return 0x33000000 | (((32 - lsb) % 32) << 16) | ((width - 1) << 10) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, movn_w('w9', 0x1F)) == 'mov w9, #-0x20'
assert C.dis1(0, bfi_w('w9', 'w10', 27, 4)) == 'bfi w9, w10, #0x1b, #4'
TAG_LSB = 27          # id bits 27..30 = player number & 0xF (counter bits 22..25: a game makes < 4M items [I])
RETRY_N = 600         # wait calls before giving up (one per instance update [I: per frame], ~10-20 s)

# ================================================================ caves
g = C.Gen('powers_gen', out=OUT, dry=DRY)
FLAG = g.alloc('FLAG', 'FAR_DATA', 4, 'POWERS_TRESPASSER flag: 1 while End runs the local Power lot (byte)')
SIZES = {'TLOT': 24, 'CREATE': 36, 'KSKIP': 8}     # words claimed (each cave asserts it fits)
T_TLOT = g.alloc('TLOT', 'FAR_CODE', SIZES['TLOT'] * 4, 'End tier lot call: offline stock, LAN flag around 0x15B0B40')
T_CREATE = g.alloc('CREATE', 'FAR_CODE', SIZES['CREATE'] * 4,
                   '0x15B0B40 create: flag -> gateless 0x159C6C4 + return id')
T_KSKIP = g.alloc('KSKIP', 'FAR_CODE', SIZES['KSKIP'] * 4, 'End kind-2 send: offline stock, LAN skip')
# review 9 (new tags; the three old ranges above keep their size)
SIZES.update({'CTAG': 12, 'KS2': 8, 'RETRY': 48})
T_CTAG = g.alloc('CTAG', 'FAR_CODE', SIZES['CTAG'] * 4, 'CREATE: tag the record id with the own player number (S1)')
T_KS2 = g.alloc('KS2', 'FAR_CODE', SIZES['KS2'] * 4, 'KSKIP LAN: send kind 2 with -0x20 (N3)')
T_RETRY = g.alloc('RETRY', 'FAR_CODE', SIZES['RETRY'] * 4, 'auto-take step: wait for the own drop to arrive (S2)')
RT = g.alloc('RT', 'FAR_DATA', 32, 'RETRY table: 4 x {u32 id, u32 calls left} (zero at start)')
assert C.adr(T_RETRY, 'x9', RT)                             # in adr reach
SIZES['RFREE'] = 16
T_RFREE = g.alloc('RFREE', 'FAR_CODE', SIZES['RFREE'] * 4, 'RETRY hit: free the RT entry of the arrived id (review 11)')


def offline_test(a, reg='x16'):
    """3 words: reg = *(main+OFFL); wreg = byte +0xBDA (non-zero = offline)."""
    r = int(reg[1:])
    a(lambda pc, L: C.adrp(pc, r, OFFL))
    a(C.ldr_x(r, r, C.lo12(OFFL)))
    a(C.ldrb(r, r, 0xBDA))


# TLOT: entered by bl from 0x10211F0 (x30 = 0x10211F4), args x0..x7 / s0..s2 / byte [sp] for 0x15B0B40
a = C.Asm(T_TLOT)
offline_test(a)
a(C.to(C.cbz_w, 'w16', 'lan'))
a.many(lambda pc, L: C.far_jump(pc, 0x15B0B40))            # offline: stock call (x30 and [sp] untouched)
a.label('lan')
a(C.sub_xi('sp', 'sp', 0x20))
a(C.stp_x(29, 30, 'sp', 0x10))
a(C.str_x('xzr', 'sp', 0))                                  # stack argument byte = 0 (caller: strb wzr, [sp])
a(lambda pc, L: C.adr(pc, 9, RT))                           # review 11 S1: empty the RETRY table for this lot
a(C.stp_x('xzr', 'xzr', 9, 0))
a(C.stp_x('xzr', 'xzr', 9, 16))
a(lambda pc, L: C.adrp(pc, 9, FLAG))
a(C.movz_w(10, 1))
a(C.strb(10, 9, C.lo12(FLAG)))
a.many(lambda pc, L: C.far_call(pc, 0x15B0B40))
a(lambda pc, L: C.adrp(pc, 9, FLAG))
a(C.strb('wzr', 9, C.lo12(FLAG)))
a(C.ldp_x(29, 30, 'sp', 0x10))
a(C.add_xi('sp', 'sp', 0x20))
a(C.RET)
tlot = a

# CREATE: entered by bl from 0x15B12C8 (x30 = 0x15B12CC); x0..x4 args of 0x159C6C4
a = C.Asm(T_CREATE)
a(lambda pc, L: C.adrp(pc, 16, FLAG))
a(C.ldrb(16, 16, C.lo12(FLAG)))
a(C.to(C.cbnz_w, 'w16', 'local'))
a.many(lambda pc, L: C.far_jump(pc, 0x159C6C4))            # not our lot: stock create (I3 applies)
a.label('local')
a(lambda pc, L: C.bl(pc, T_CTAG))                           # CTAG tags the id, then `b body`; body's retab returns here
a(C.ldur_x(0, 29, -0x18))                                   # w0 = record id (0x15B0B40 frame)
a.many(lambda pc, L: C.far_return(pc, 0x15B12E8))           # `b 0x15b10e8`: 0x15B0B40 epilogue returns w0
a.label('body')
for pa in PRO:
    a.many(lambda pc, L, pa=pa: C.relocate(pa, pc))
a.many(lambda pc, L: C.relocate(0x159C700, pc))             # cbz x8 -> 0x159C778 (no world singleton)
a.many(lambda pc, L: C.far_jump(pc, 0x159C714))             # past the I3 gate
create = a
create.words()
BODY = create.labels['body']

# CTAG: bl from CREATE (x30 = CREATE's return point); x0..x4 = args of 0x159C6C4, x1 = record, x29 = 0x15B0B40 frame.
# id bits 27..30 = own player number & 0xF, in the record (+0) and in [x29-0x18] (the value 0x15B0B40 returns).
a = C.Asm(T_CTAG)
a(lambda pc, L: C.adrp(pc, 10, GDM))
a(C.ldr_x(10, 10, C.lo12(GDM)))
a(C.to(C.cbz_x, 'x10', 'go'))
a(C.ldr_x(10, 10, 0x20))
a(C.to(C.cbz_x, 'x10', 'go'))
a(C.ldr_w(10, 10, 0xD0))                                    # own player number
a(C.ldr_w(9, 1, 0))                                         # record id
a(bfi_w('w9', 'w10', TAG_LSB, 4))
a(C.str_w(9, 1, 0))
a(C.stur_x(9, 29, -0x18))                                   # w9 write zero-extends: same 64-bit form as 0x15B0E48
a.label('go')
a(lambda pc, L: C.b(pc, BODY))                              # x30 untouched: body's pacibsp / retab pair returns to CREATE
ctag = a

# KSKIP: entered by bl from 0x1020FF8 (x30 = 0x1020FFC)
a = C.Asm(T_KSKIP)
offline_test(a)
a(C.to(C.cbz_w, 'w16', 'lan'))
a.many(lambda pc, L: C.far_jump(pc, 0x1047420))            # offline: stock send
a.label('lan')
a(lambda pc, L: C.b(pc, T_KS2))
kskip = a

# KS2: LAN send with the value -0x20 (peers clear their +0x3B8 wait; nobody gets a foreign handle)
a = C.Asm(T_KS2)
a(movn_w('w9', 0x1F))                                       # mov w9, #-0x20
a(C.str_w(9, 'sp', 0x1C))                                   # the send's value slot (End's sp: entered by bl, no frame)
a.many(lambda pc, L: C.far_jump(pc, 0x1047420))            # x30 = 0x1020FFC: returns to End
ks2 = a

# RETRY: hook 0x101DA58 (`ldr x8, [x28]`), w8 = +0x3A8 (valid), x19 = instance, x21 = &item-mgr pointer
a = C.Asm(T_RETRY)
a(lambda pc, L: C.adrp(pc, 16, OFFL))
a(C.ldr_x(16, 16, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldrb(16, 16, 0xBDA))
a(C.to(C.cbnz_w, 'w16', 'stock'))                           # offline: stock (the create there is immediate)
a(C.ldr_w(11, 19, 0x3A8))
a(C.ldr_x(9, 21, 0))
a(C.to(C.cbz_x, 'x9', 'stock'))
a(C.ldr_x(9, 9, 0x1B8))                                     # world list, as 0x101DE70
a.label('search')
a(C.to(C.cbz_x, 'x9', 'miss'))
a(C.ldr_w(10, 9, 0x30))
a(C.cmp_wr('w10', 'w11'))
a(lambda pc, L: C.beq(pc, T_RFREE))                         # arrived: free its RT entry, then the stock path
a(C.ldr_x(9, 9, 8))
a(C.to(C.b, 'search'))
a.label('miss')
a(lambda pc, L: C.adr(pc, 9, RT))
a(C.add_xi(16, 9, 32))                                      # end of table
a(C.movz_x(10, 0))                                          # entry of this id
a(C.movz_x(12, 0))                                          # first free entry
a.label('loop')
a(C.ldr_w(8, 9, 4))
a(C.to(C.cbz_w, 'w8', 'free'))
a(C.sub_wi(8, 8, 1))                                        # age every live entry
a(C.str_w(8, 9, 4))
a(C.ldr_w(8, 9, 0))
a(C.cmp_wr('w8', 'w11'))
a(C.to(C.bne, 'next'))
a(C.mov_x(10, 9))
a(C.to(C.b, 'next'))
a.label('free')
a(C.to(C.cbnz_x, 'x12', 'next'))
a(C.mov_x(12, 9))
a.label('next')
a(C.add_xi(9, 9, 8))
a(C.cmp_xr('x9', 'x16'))
a(C.to(C.bne, 'loop'))
a(C.to(C.cbz_x, 'x10', 'new'))
a(C.ldr_w(8, 10, 4))
a(C.to(C.cbz_w, 'w8', 'stock'))                             # waited RETRY_N calls: stock (miss -> -0x20, as today)
a(C.to(C.b, 'wait'))
a.label('new')
a(C.to(C.cbz_x, 'x12', 'stock'))                            # table full: stock
a(C.str_w(11, 12, 0))
a(C.movz_w(8, RETRY_N))
a(C.str_w(8, 12, 4))
a.label('wait')
a.many(lambda pc, L: C.far_return(pc, 0x101DECC))          # skip this step's take path; +0x3A8 kept
a.label('stock')
a(C.ldr_x(8, 28, 0))                                        # the replaced word
a.many(lambda pc, L: C.far_return(pc, 0x101DA5C))
retry = a
assert C.dis1(0, C.ldr_x(8, 28, 0)) == 'ldr x8, [x28]'

# RFREE: from RETRY's hit (w11 = id): left = 0 for every RT entry with that id, then the stock path (same
# registers as RETRY's stock path: x8..x11, x16, flags)
a = C.Asm(T_RFREE)
a(lambda pc, L: C.adr(pc, 9, RT))
a(C.add_xi(16, 9, 32))
a.label('loop')
a(C.ldr_w(10, 9, 0))
a(C.cmp_wr('w10', 'w11'))
a(C.to(C.bne, 'next'))
a(C.str_w('wzr', 9, 4))
a.label('next')
a(C.add_xi(9, 9, 8))
a(C.cmp_xr('x9', 'x16'))
a(C.to(C.bne, 'loop'))
a(C.ldr_x(8, 28, 0))                                        # the replaced word
a.many(lambda pc, L: C.far_return(pc, 0x101DA5C))
rfree = a

for _name, _asm in (('TLOT', tlot), ('CREATE', create), ('KSKIP', kskip), ('CTAG', ctag), ('KS2', ks2),
                    ('RETRY', retry), ('RFREE', rfree)):
    assert len(_asm.words()) <= SIZES[_name], '%s: %d words > %d claimed' % (_name, len(_asm.words()), SIZES[_name])
caves = (g.cave('TLOT', T_TLOT, tlot) + g.cave('CREATE', T_CREATE, create) + g.cave('KSKIP', T_KSKIP, kskip)
         + g.cave('CTAG', T_CTAG, ctag) + g.cave('KS2', T_KS2, ks2) + g.cave('RFREE', T_RFREE, rfree)
         + g.cave('RETRY', T_RETRY, retry))
RT_WORDS = 8                                                # RT has no record: the far region starts zeroed (as FLAG)
WHY_END = 'site is a bl in End 0x1020C40..0x1021380, which never names x16/x17 (asserted)'
hooks = (g.far_hook(0x10211F0, 'bl #0x15b0b40', T_TLOT, link=True, why=WHY_END) +
         g.far_hook(0x15B12C8, 'bl #0x159c6c4', T_CREATE, link=True,
                    why='site is a bl (x16/x17 corruptible across it); 0x15B0B40 names w16/w17 only in its copy loop '
                        '0x15B0F08..0x15B0F6C before the site and never after it (asserted); 0x159C6C4 never names '
                        'them (the gateless body jumps into it with x16)') +
         g.far_hook(0x1020FF8, 'bl #0x1047420', T_KSKIP, link=True, why=WHY_END) +
         g.far_hook(0x101DA58, 'ldr x8, [x28]', T_RETRY,
                    why='step function 0x%X..0x%X never names x16/x17 (asserted); RETRY returns to 0x101DA5C after '
                        're-running the word, or to 0x101DECC; x8..x12, x16 and the flags are written before read on '
                        'both continuations up to the next bl (asserted)' % (STEP_FN, STEP_END),
                    note='RETRY: wait for the own drop'))

groups = {'POWERS_ROSE': [], 'POWERS_CAVES': caves, 'POWERS_TRESPASSER': hooks}
order = ['POWERS_ROSE', 'POWERS_CAVES', 'POWERS_TRESPASSER']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('FLAG byte at main+0x%X, RT table at main+0x%X (FAR_DATA, no record)' % (FLAG, RT))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0] +
                 'POWERS_ROSE is empty on purpose (see powers_notes.md 1). FLAG = main+0x%X, RT = main+0x%X.'
                 % (FLAG, RT))
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'TLOT': 0x%X, 'CREATE': 0x%X, 'KSKIP': 0x%X, 'CTAG': 0x%X, 'KS2': 0x%X, 'RETRY': 0x%X, 'RFREE': 0x%X, "
                "'FLAG': 0x%X, 'RT': 0x%X}\n" % (T_TLOT, T_CREATE, T_KSKIP, T_CTAG, T_KS2, T_RETRY, T_RFREE, FLAG, RT))
        f.write('TAG_LSB = %d\nRETRY_N = %d\n' % (TAG_LSB, RETRY_N))
    for name in ('POWERS_CAVES', 'POWERS_TRESPASSER'):
        d, r = C.cpp_rows(name, groups[name])
        print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
