"""starcrash2_gen.py: move the TextEffect commendation notice push off the UI script thread (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes starcrash2_live.py.
python starcrash2_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: starcrash3_notes.md. Alternative to TE_COMMEND_UI (starcrash_live.py; same word 0x12A8C08: never both).

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Groups
  STARCRASH_DEFER_CAVE  far caves SC_UI + SC_GAME, data SC_CNT {u32 REQ, u32 DONE}, two 3-word trampolines in
                        zero text padding.
  STARCRASH_DEFER       two hooks:
     0x12A8C08 `bl 0x110c1b8` (UI script thread, TextEffect lambda tail 0x12A8B8C) -> b trampoline -> SC_UI:
        offline (+0xBDA byte != 0) or no offline-byte owner -> the stock call 0x110C1B8, back to 0x12A8C0C
        LAN (byte 0) -> REQ += 1 (plain store, only writer), back to 0x12A8C0C (no queue push on this thread)
     0x110B3C8 `mov x0, x19` (Commendation per-frame step 0x110B33C, game thread) -> b trampoline -> SC_GAME:
        if REQ != DONE: DONE += 1 (only writer) and call 0x110C1B8(par[0x2E0]) here, on the game thread
        then the relocated `mov x0, x19`, back to 0x110B3CC (x30 / caller-saved regs are dead there)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
# --v2 (hubbatch_notes.md): same ranges and hooks; SC_GAME only runs the deferred call in UpdatePhase
# (par+0x50 == 6) with the notice queue present ([par+0x33A0] != 0), so it is inert during any load / hub /
# intermission. Writes starcrash2b_live.py (groups ..._V2); never apply it together with starcrash2_live.py.
V2 = '--v2' in sys.argv
OUT = 'starcrash2b_live.py' if V2 else 'starcrash2_live.py'
SFX = '_V2' if V2 else ''
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
PUSH2 = 0x110C1B8            # Commendation: pushes (player, 30000, 0) and (player, 40000, 0) through 0xF94A14
QPUSH = 0xF94A14             # notice queue push (CSDebugPanicLock at Q+0x60)
UI_SITE, UI_BACK = 0x12A8C08, 0x12A8C0C
GM_SITE, GM_BACK = 0x110B3C8, 0x110B3CC
PAR = 0x5B3CDF8              # par singleton slot (GOT 0x59DFEF8 -> 0x5B3CDF8)
OFFP = 0x5B65C20             # *(main+0x5B65C20)+0xBDA = offline byte (!= 0 offline)
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def bl_target(pc, w):
    if (w & 0xFC000000) in (0x94000000, 0x14000000):
        imm = w & 0x3FFFFFF
        return pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
    return None


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            t = bl_target(pc, w)
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


def func_of(a):
    s = a
    while W[s // 4] != PACIBSP:
        s -= 4
    e = a + 4
    while W[e // 4] != PACIBSP:
        e += 4
    return s, e


def no_ip_regs(lo, hi):
    bad = [a for a in range(lo, hi, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
    assert not bad, 'x16/x17 named at %s' % [hex(x) for x in bad]


# ================================================================ code facts [V]
for a, t in [(0x12A8BF4, 'adrp x8, #0x5b3c000'), (0x12A8BF8, 'add x8, x8, #0xdf8'), (0x12A8BFC, 'ldr x8, [x8]'),
             (0x12A8C00, 'cbz x8, #0x12a8c1c'), (0x12A8C04, 'ldr x0, [x8, #0x2e0]'),
             (UI_SITE, 'bl #0x110c1b8'), (0x12A8C0C, 'ldr x19, [sp, #0x30]'), (0x12A8C10, 'ldp x29, x30, [sp, #0x20]'),
             (0x12A8C14, 'add sp, sp, #0x40'), (0x12A8C18, 'retab'),
             (0x110B3C4, 'bl #0x110b410'), (GM_SITE, 'mov x0, x19'), (0x110B3CC, 'ldp x20, x19, [sp, #0x10]'),
             (0x110B3D0, 'ldp x29, x30, [sp], #0x20'), (0x110B3D4, 'autibsp'), (0x110B3D8, 'b #0x110b700'),
             (0x110B340, 'stp x29, x30, [sp, #-0x20]!'), (0x110B360, 'mov x19, x0'),
             (0x110B364, 'ldr x8, [x8, #0xc20]'), (0x110B368, 'ldrb w8, [x8, #0xbda]'),
             (0x110C24C, 'ldr x0, [x8, #0x33a0]'), (0x110C25C, 'bl #0xf94a14'), (0x110C278, 'bl #0xf94a14'),
             (0xF94A78, 'casal x4, x3, [x8]'), (0xF94A84, 'cmp x4, x3'), (0xF94A88, 'b.ne #0xf94c44')]:
    stock(a, t)
assert struct.unpack_from('<Q', C.DATA, 0x59DFEF8 - C.DATA_BASE)[0] == PAR
# 0x110C1B8 has exactly one caller (the UI lambda tail) and no pointer to it: nothing else changes
callers = targets_in(PUSH2, PUSH2 + 4)
assert callers == [UI_SITE], [hex(x) for x in callers]
assert not qwords_in(PUSH2, PUSH2 + 4)
listing.append('0x110C1B8: only caller 0x12A8C08, no data pointer to it')
# hook words are not branch targets of anything but their own fall-through paths we keep
assert not targets_in(UI_SITE, UI_SITE + 4)
listing.append('0x110B3C8 is a branch target of %s (all keep reaching the hook word)'
               % [hex(x) for x in targets_in(GM_SITE, GM_SITE + 4)])
# x16 / x17 never named in either function (trampoline scratch)
for site in (UI_SITE, GM_SITE):
    s, e = func_of(site)
    no_ip_regs(s, e)
    listing.append('%X..%X (function of %X): x16/x17 never named' % (s, e, site))
s, e = func_of(GM_SITE)
assert (s, e) == (0x110B33C, 0x110B410), (hex(s), hex(e))
# who calls the per-frame step, and what 0xF94A14 calls (none of them is 0x110B33C)
listing.append('0x110B33C callers: %s' % [hex(x) for x in targets_in(0x110B33C, 0x110B340)])
s, e = func_of(QPUSH)
qcalls = sorted({bl_target(a, W[a // 4]) for a in range(s, e, 4) if (W[a // 4] & 0xFC000000) == 0x94000000})
assert 0x110B33C not in qcalls and PUSH2 not in qcalls
listing.append('0xF94A14 (%X..%X) bl targets: %s' % (s, e, [hex(x) for x in qcalls]))

# ================================================================ trampoline padding (zero, before pacibsp, free)
g = C.Gen('starcrash2_gen', out=OUT, dry=True)
for i in range(4):          # TE_COMMEND_UI (starcrash_live.py) holds the same word: the two are exclusive
    g.others.pop(UI_SITE + i, None)
for k in [k for k, v in g.others.items() if v in ('starcrash2_live.py', 'starcrash2b_live.py')]:
    del g.others[k]         # v1 / v2 are two versions of the same groups (same ranges): exclusive


def find_pad(site, lo, hi, avoid=()):
    for a in range(lo, hi, 4):
        if W[a // 4] == 0 and W[a // 4 + 1] == 0 and W[a // 4 + 2] == 0 and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP or a in avoid:
                continue
            if any(x in C.SHIPPED or x in g.others for x in range(a, a + 12)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    raise AssertionError('no pad near %x' % site)


PAD_UI = find_pad(UI_SITE, 0x12A0000, 0x12C0000)
PAD_GM = find_pad(GM_SITE, 0x1100000, 0x1120000, avoid=(PAD_UI,))
for p in (PAD_UI, PAD_GM):
    listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (p, p + 12))

# ================================================================ allocation
CNT = g.alloc('SC_CNT', 'FAR_DATA', 8, 'STARCRASH_DEFER {u32 REQ (UI thread only), u32 DONE (game thread only)}')
UI_N, GM_N = 20, 22
T_UI = g.alloc('SC_UI', 'FAR_CODE', UI_N * 4, 'STARCRASH_DEFER UI side (starcrash3_notes)')
T_GM = g.alloc('SC_GAME', 'FAR_CODE', GM_N * 4, 'STARCRASH_DEFER game side (starcrash3_notes)')
listing.append('data SC_CNT 0x%X..0x%X, caves SC_UI 0x%X..0x%X, SC_GAME 0x%X..0x%X (NOT claimed: lead adds rows)'
               % (CNT, CNT + 8, T_UI, T_UI + UI_N * 4, T_GM, T_GM + GM_N * 4))

# ---------------- SC_UI: entered from 0x12A8C08 with x0 = par[0x2E0] (stock arg); x9/x10/x16/x30 are dead
a = C.Asm(T_UI)
a(lambda pc, L: C.adrp(pc, 9, OFFP))
a(C.ldr_x(9, 9, C.lo12(OFFP)))
a(C.to(C.cbz_x, 'x9', 'stock'))                     # no owner object: stock behaviour
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'stock'))                    # offline: stock behaviour
a(lambda pc, L: C.adrp(pc, 9, CNT))
a(C.ldr_w(10, 9, C.lo12(CNT)))
a(C.add_wi(10, 10, 1))
a(C.str_w(10, 9, C.lo12(CNT)))                      # REQ += 1 (this thread is the only writer of REQ)
a.many(lambda pc, L: C.far_return(pc, UI_BACK))
a.label('stock')
a.many(lambda pc, L: C.far_call(pc, PUSH2))         # the stock bl 0x110c1b8 (x0 unchanged)
a.many(lambda pc, L: C.far_return(pc, UI_BACK))
ui_words = a.words()
assert len(ui_words) <= UI_N, len(ui_words)

# ---------------- SC_GAME: entered from 0x110B3C8 (game thread); x19 = this, x20 saved; x0..x18, x30 dead
a = C.Asm(T_GM)
if V2:
    # 0x110C1B8 writes x0 before reading it (0x110C1E4 `ldr x0, [x20]`), so the argument load is dropped
    stock(0x110C1E4, 'ldr x0, [x20]')
    assert not re.search(r'\bx0\b|\bw0\b', ' '.join(C.dis1(x, W[x // 4]) for x in range(0x110C1BC, 0x110C1E4, 4)))
    a(lambda pc, L: C.adrp(pc, 9, CNT))
    a(C.ldr_w(10, 9, C.lo12(CNT)))                  # REQ
    a(C.ldr_w(11, 9, C.lo12(CNT) + 4))              # DONE
    a(C.cmp_wr(10, 11))
    a(C.to(C.beq, 'out'))
    a(lambda pc, L: C.adrp(pc, 8, PAR))
    a(C.ldr_x(8, 8, C.lo12(PAR)))
    a(C.to(C.cbz_x, 'x8', 'out'))
    a(C.ldr_w(12, 8, 0x50))                         # par+0x50 phase (clock.py: 6 = UpdatePhase)
    a(C.cmp_wi(12, 6))
    a(C.to(C.bne, 'out'))                           # not in UpdatePhase: keep it pending
    a(C.ldr_x(12, 8, 0x33A0))                       # notice queue Q
    a(C.to(C.cbz_x, 'x12', 'out'))
    a(C.add_wi(11, 11, 1))
    a(C.str_w(11, 9, C.lo12(CNT) + 4))              # DONE += 1 (only writer)
    a.many(lambda pc, L: C.far_call(pc, PUSH2))
else:
    a(lambda pc, L: C.adrp(pc, 9, CNT))
    a(C.add_xi(9, 9, C.lo12(CNT)))
    a(C.ldr_w(10, 9, 0))                            # REQ
    a(C.ldr_w(11, 9, 4))                            # DONE
    a(C.cmp_wr(10, 11))
    a(C.to(C.beq, 'out'))
    a(C.add_wi(11, 11, 1))
    a(C.str_w(11, 9, 4))                            # DONE += 1 (this thread is the only writer of DONE)
    a(lambda pc, L: C.adrp(pc, 8, PAR))
    a(C.ldr_x(8, 8, C.lo12(PAR)))
    a(C.to(C.cbz_x, 'x8', 'out'))
    a(C.ldr_x(0, 8, 0x2E0))                         # the stock argument (unused by 0x110C1B8)
    a.many(lambda pc, L: C.far_call(pc, PUSH2))     # one deferred pair of notices per frame, game thread
a.label('out')
a(W[GM_SITE // 4])                                  # mov x0, x19 (relocated)
a.many(lambda pc, L: C.far_return(pc, GM_BACK))
gm_words = a.words()
assert len(gm_words) <= GM_N, len(gm_words)

caves = g.cave('SC_UI', T_UI, ui_words) + g.cave('SC_GAME', T_GM, gm_words)
tramp = []
for p, t in ((PAD_UI, T_UI), (PAD_GM, T_GM)):
    tramp += [g.text_patch(p + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 never named in the hooked function)' % t)
              for k, w in enumerate(C.far_jump(p, t))]
hooks = [g.text_patch(UI_SITE, 'bl #0x110c1b8', C.b(UI_SITE, PAD_UI), 'STARCRASH_DEFER UI side'),
         g.text_patch(GM_SITE, 'mov x0, x19', C.b(GM_SITE, PAD_GM), 'STARCRASH_DEFER game side')]
groups = {'STARCRASH_DEFER_CAVE' + SFX: caves + tramp, 'STARCRASH_DEFER' + SFX: hooks}
order = ['STARCRASH_DEFER_CAVE' + SFX, 'STARCRASH_DEFER' + SFX]
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'SC_UI': 0x%X, 'SC_GAME': 0x%X, 'SC_CNT': 0x%X, 'PAD_UI': 0x%X, 'PAD_GM': 0x%X}\n"
                "EXCLUSIVE_WITH = {'STARCRASH_DEFER%s': ['TE_COMMEND_UI', 'STARCRASH_DEFER%s']}\n"
                % (T_UI, T_GM, CNT, PAD_UI, PAD_GM, SFX, '' if V2 else '_V2'))
