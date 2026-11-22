"""fxentry_gen (alpha 18): FX_ENTRY - skill SpEffects 140000..149999 (Vanish Dash: 140070, 140171, 140072, 142643,
measured on the user's game 2026-11-21) are sent to the other games' copies WHOEVER applies them.
BLINK_SHARE / BLINK2 only cover the one TAE handler 0x194B5E0 (site 0x194B8A8); alpha 17 showed the dash is not
applied there (still not seen by the others). NetChrIns::ApplySpecialEffect 0xE8BBC0 has 40+ callers, several with
`mov w5, #1` (local only: 0x1756EB8 0x1758148 0x17583C8 0x17AE6DC 0x18C7B6C 0x19CC17C ...), so the rule moves to
the function's entry:
    0xE8BBC0 pacibsp  ->  b tramp -> cave:
        cbz x1, skip ; ldr w16, [x1] ; w16 -= 140000 ; cmp w16, #10000 ; b.hs skip ; mov w5, wzr
        skip: pacibsp ; far return to 0xE8BBC4
x1 = pointer to the SpEffect id (0xE8BC00 mov x19, x1), w5 = the local-only flag (0xE8BBF0 mov w28, w5). x16 / x17 are
free at a function entry (AAPCS64 IP0 / IP1). With w5 = 0 the function broadcasts only for a chr whose vt+0x78() == 0
(the local player), the receiver applies it on the copy (0xE8C8C0), EFFECT_NO_ECHO stops the echo (blink_gen notes).
Only the six-digit family: bosses carry 1415090 / 1441030 of the seven-digit family from other callers.
    python fxentry_gen.py [--claim]     (from diag/net; writes fxentry_live.py)"""
import struct
import sys

import cave_lib as C

CLAIM = '--claim' in sys.argv
OUT = 'fxentry_live.py'
SITE, BACK = 0xE8BBC0, 0xE8BBC4
LO_ID, SPAN = 140000, 10000
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F


def sub_wr(rd, rn, rm):
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


for a, t in ((SITE, 'pacibsp'), (BACK, 'sub sp, sp, #0x110'), (0xE8BBF0, 'mov w28, w5'), (0xE8BC00, 'mov x19, x1'),
             (0x194B8DC, 'bl #0xe8bbc0')):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(SITE, SITE + 4)), 'site already patched'


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


def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if C.dis1(a - 4, W[a // 4 - 1]).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


# the entry word is only reached by calls (bl / tail b / pointers): fine, they all land on our branch
PAD = find_pad(SITE, 3)
assert PAD, 'no trampoline padding near 0xE8BBC0'


def asm(start):
    a = C.Asm(start)
    a(C.to(C.cbz_x, 'x1', 'skip'))
    a(C.ldr_w(16, 1, 0))                                     # the SpEffect id
    a(C.movz_w(17, LO_ID & 0xFFFF))
    a(C.movk_w(17, LO_ID >> 16, 1))
    a(sub_wr(16, 16, 17))
    a(C.movz_w(17, SPAN))
    a(C.cmp_wr(16, 17))
    a(C.to(C.bcond, 'hs', 'skip'))
    a(C.movz_w(5, 0))                                        # w5 = 0: sent to the copies
    a.label('skip')
    a(PACIBSP)                                               # the displaced entry word
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    return a


g = C.Gen('fxentry_gen', out=OUT, dry=not CLAIM)
n = len(asm(0xC500000).words())
start = g.alloc('FXENTRY', 'FAR_CODE', (n * 4 + 15) // 16 * 16, 'FX_ENTRY (alpha 18) 0xE8BBC0: skill SpEffects '
                '140000..149999 are sent to the copies from every caller (w5 = 0); trampoline 0x%X..0x%X' % (PAD, PAD + 12))
cave = g.cave('FXENTRY', start, asm(start))
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> FXENTRY 0x%X' % start)
         for k, w in enumerate(C.far_jump(PAD, start))]
hook = [g.text_patch(SITE, 'pacibsp', C.b(SITE, PAD), 'ApplySpecialEffect entry: skill ids 140000..149999 are sent')]
groups = {'FXENTRY_CAVE': cave, 'FX_ENTRY': tramp + hook}
ORDER = ['FXENTRY_CAVE', 'FX_ENTRY']
print('\n'.join(g.listing))
for i, w in enumerate(asm(start).words()):
    print('  %X  %s' % (start + 4 * i, C.dis1(start + 4 * i, w)))
C.write_live(OUT, groups, ORDER, """
FX_ENTRY, alpha 18 (generated by fxentry_gen.py): NetChrIns::ApplySpecialEffect 0xE8BBC0 sends skill SpEffects
140000..149999 to the other games' copies whoever applies them (Vanish Dash 140070 / 140171 / 140072 / 142643).
Apply on EVERY game. Expected: fx_probe on a watching game shows +fx 140070 and 140171 on the caster's copy.""")
print('cave 0x%X (%d words), trampoline 0x%X; %s' % (start, n, PAD, 'CLAIMED' if CLAIM else 'DRY'))
