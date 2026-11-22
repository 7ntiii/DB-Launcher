"""blink_gen: BLINK_SHARE - skill SpEffects from the TAE event (Blink / Neb-ra Vanishing / Darkmoon vanish and
their VFX) reach the other games' copies (vanish_death_notes.md section 4). Static only: reads nso/*.bin,
patch_manager.cpp, every *_live.py and cave_registry.md; with --dry (default) claims nothing and prints the
proposed registry row; with --claim it claims the far cave in cave_registry.md and writes blink_live.py.
    python blink_gen.py [--claim]     (from diag/net)

Code [V]:
  - TAE SpEffect handler 0x194B5E0 applies through NetChrIns::ApplySpecialEffect 0xE8BBC0 at 0x194B8DC, with the
    id at [x29-8] (x1 = x29-8) and `mov w5, #1` at 0x194B8A8 = "local only" (never broadcast).
  - The caster's game logs 1401010 / 1401020 / 1401021 (VFX 140110 / 140120 / 140121); the copy on the other games
    gets none (match 5, fx_blink_m5.txt). The copy's skill slot is empty in LAN, so its own TAE resolves no id.
  - With w5 = 0, 0xE8BBC0 broadcasts (0xCD for the local player) only when chr vt+0x78() == 0, and the receiver
    applies it on the copy (0xE8C8C0). EFFECT_NO_ECHO (built in) stops the caster applying its own echo.
BLINK_SHARE: at 0x194B8A8, w5 = 0 only for ids 1400000..1449999 (skill effects), else w5 = 1 as before.
    ldur w16, [x29, #-8] ; movz/movk w17, #1400000 ; sub w16, w16, w17 ; movz w17, #50000 ; cmp w16, w17 ;
    cset w5, hs ; far return to 0x194B8AC.
x16 / x17 are dead at 0x194B8A8: no instruction in 0x194B8AC..0x194B8D8 reads them and 0x194B8DC is a bl.
Do NOT flip 0x194B8A8 to `mov w5, #0` for all ids: every TAE SpEffect would be sent AND applied by each copy's
own TAE (doubles). Risk: an id in the range whose copy TAE does resolve it (a skill slot that is not empty on the
copy) would then come twice; refreshes of the same id are harmless.
"""
import os
import struct
import sys

import cave_lib as C

CLAIM = '--claim' in sys.argv
OUT = 'blink_live.py'
SITE = 0x194B8A8
BACK = 0x194B8AC
LO_ID, SPAN = 1400000, 50000
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F

for a, t in [(0x194B890, 'sub x1, x29, #8'), (0x194B8A0, 'mov x0, x20'), (0x194B8A4, 'mov x4, xzr'),
             (SITE, 'mov w5, #1'), (BACK, 'add x8, x8, #0x10'), (0x194B8B0, 'mov w6, wzr'),
             (0x194B8B4, 'mov w7, #1'), (0x194B8B8, 'stp x8, x19, [x29, #-0x28]'), (0x194B8BC, 'adrp x8, #0x5b79000'),
             (0x194B8C0, 'add x8, x8, #0x310'), (0x194B8C4, 'strb w9, [sp]'), (0x194B8C8, 'ldr s0, [x8]'),
             (0x194B8CC, 'sub x8, x29, #4'), (0x194B8D0, 'str x8, [sp, #8]'), (0x194B8D4, 'stur s0, [x29, #-4]'),
             (0x194B8D8, 'fmov s0, #1.00000000'), (0x194B8DC, 'bl #0xe8bbc0')]:
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)
for a in range(BACK, 0x194B8DC, 4):     # x16 / x17 dead at the site
    d = C.dis1(a, C.text_word(a))
    assert 'x16' not in d and 'w16' not in d and 'x17' not in d and 'w17' not in d, d

g = C.Gen('blink_gen', OUT, dry=not CLAIM)
others = C.live_records(exclude=(OUT,))


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


def find_pad(near, n):
    """n zero words in text padding (before a pacibsp, unreferenced, free) in b reach of `near`"""
    for a_ in range(near - 0x80000, near + 0x80000, 4):
        if all(W[a_ // 4 + k] == 0 for k in range(n)) and W[a_ // 4 - 1] != 0:
            z = a_
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a_, a_ + 4 * n)):
                continue
            if targets_in(a_, z) or qwords_in(a_, z):
                continue
            if C.reach(near, a_):
                return a_
    return None


def cset_hs(rd):                        # cset wd, hs = csinc wd, wzr, wzr, lo
    return 0x1A9F37E0 | C.R(rd)


def sub_wr(rd, rn, rm):
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


def blink_asm(start):
    a = C.Asm(start)
    a(C.ldur_w(16, 29, -8))                                  # the SpEffect id (x1 = x29 - 8)
    a(C.movz_w(17, LO_ID & 0xFFFF))
    a(C.movk_w(17, LO_ID >> 16, 1))
    a(sub_wr(16, 16, 17))
    a(C.movz_w(17, SPAN))
    a(C.cmp_wr(16, 17))
    a(cset_hs(5))                                            # w5 = 0 (send) for 1400000..1449999, else 1
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    return a


n = len(blink_asm(0xC500000).words())
start = g.alloc('BLINK', 'FAR_CODE', (n * 4 + 15) // 16 * 16, 'BLINK_SHARE: TAE skill SpEffects 1400000..1449999 '
                'sent to the copies (w5 = 0) at 0x194B8A8 (vanish_death_notes 4)')
cave = g.cave('BLINK', start, blink_asm(start))
assert C.dis1(start + 24, cset_hs(5)) == 'cset w5, hs', 'cset encoding'
PAD = find_pad(SITE, 3)
assert PAD, 'no trampoline padding near 0x194B8A8'
g.listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free; x16 dead at 0x%X)'
                 % (PAD, PAD + 12, SITE))
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> BLINK 0x%X' % start)
         for k, w in enumerate(C.far_jump(PAD, start))]
hook = [g.text_patch(SITE, 'mov w5, #1', C.b(SITE, PAD), 'TAE SpEffect apply: skill ids are sent')]
groups = {'BLINK_CAVE': cave, 'BLINK_SHARE': tramp + hook}
ORDER = ['BLINK_CAVE', 'BLINK_SHARE']
print('\n'.join(g.listing))
for r in g._dry_rows:
    print('proposed registry row: | %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
C.write_live(OUT, groups, ORDER, """
BLINK_SHARE (generated by blink_gen.py; vanish_death_notes.md section 4): the TAE SpEffect apply at 0x194B8A8 sends
skill effects 1400000..1449999 (Blink / Neb-ra / Darkmoon vanish and their VFX) to the other games' copies.
Apply on EVERY game. Not live-tested. Expected: fx_probe on the watching game shows +fx 14010xx on the caster's copy.""")
for name in ORDER:
    d, r = C.cpp_rows(name, groups[name])
    print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
if not CLAIM:
    print('DRY: registry not written; blink_live.py written with the dry address (re-run with --claim when baking)')
