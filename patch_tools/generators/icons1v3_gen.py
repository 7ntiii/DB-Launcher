"""icons1v3_gen.py: ICONS1 v3 REPICK, alpha RECONSTRUCTION (alpha_reconstructions.md a). Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes icons1v3_live.py.
python icons1v3_gen.py [--dry]      (from diag/net)

Alpha 2 (live 2026-11-19): I1BOX on, hook in place, uses 0 = the pick never reaches 0x1035374 in round 1. The trend
step 0x1120B80(MS) skips the pick when its candidate list is empty (0x1120F18 -> 0x1121340); round 1's PrepareFirst
runs during the match load (state 7), before the groups' inner vectors are filled [I, by elimination: stage+0xC0
bit 2 is clear (0xCA round 2, 0x9EA round 4), so the 0x1033800 pick is not used; Phase I row +0x8F = 2].
REPICK runs that stock trend step once more, later, on the game thread: it hooks the UpdatePhase step 0x114B9CC
after its prologue (0x114B9E8 `adrp x8`, x8..x15 not yet live, x0..x7 saved), and when the box I1RBOX {u64 MS,
u32 runs} holds a MapSystem pointer it clears the box, counts the run and calls 0x1120B80(MS). Every game runs the
hook; only the host's assist ever fills the box (round 1, Phase I, table still empty, groups filled). The ICONS1
cave at 0x1035374 then substitutes list 100002 as before."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'icons1v3_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []
PLANNED = [
    ('takerace_gen', 'TRBOX', 0xC50F710, 0xC50F8C0), ('takerace_gen', 'TRGRANT', 0xC503AF8, 0xC503CF8),
    ('takerace_gen', 'TRFRAME', 0xC503CF8, 0xC504018),
    ('needdata_gen', 'NDBOX', 0xC50F8C0, 0xC50F8D0), ('needdata_gen', 'NEEDDATA', 0xC504018, 0xC504078),
    ('outhide_gen', 'OHBOX', 0xC50F8D0, 0xC50F8D8), ('outhide_gen', 'OUTHIDE', 0xC504078, 0xC5040C8),
]


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


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


SITE, BACK, TREND = 0x114B9E8, 0x114B9EC, 0x1120B80
PLANNED = PLANNED + [('icons1_gen', 'I1BOX', 0xC50F8D8, 0xC50F8E0), ('icons1_gen', 'ICONS1', 0xC5040C8, 0xC504118)]
# ================================================================ code facts [V]
steps = {}
for a, t in ((0x114B9CC, 'pacibsp'), (0x114B9D8, 'str x21, [sp, #0x38]'), (0x114B9DC, 'stp x29, x30, [sp, #0x28]'),
             (0x114B9E0, 'stp x20, x19, [sp, #0x40]'), (0x114B9E4, 'add x29, sp, #0x28'),
             (SITE, 'adrp x8, #0x5b4d000'), (BACK, 'add x8, x8, #0x858'),
             (0x114B9FC, 'mov x20, x1'), (0x114BA00, 'mov x19, x0'),
             # the trend step: x0 = MapSystem only; the pick skip on an empty candidate list
             (TREND, 'pacibsp'), (0x1120BA8, 'mov x25, x0'), (0x1120F0C, 'subs x8, x24, x28'),
             (0x1120F18, 'b.eq #0x1121340'), (0x111434C, 'bl #0x1120b80')):
    stock(a, t)
assert targets_in(SITE, SITE + 8) == []
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
listing.append('0x114B9CC is the UpdatePhase step (step table 0x115E25C entry 6, built at 0x115E250..); 0x114B9E8 '
               'follows the prologue: x8..x17 are not live there (x8 is written by the word itself), x0..x7 are '
               'saved and restored by the cave, x30 is already on the stack')

others = C.live_records(exclude=(OUT,))
def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


PAD = find_pad(SITE, 3)
assert PAD
listing.append('trampoline padding 0x%X..0x%X after `%s`' % (PAD, PAD + 12, dis(PAD - 4)))

g = C.Gen('icons1v3_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 36
BOX = g.alloc('I1RBOX', 'FAR_DATA', 16, 'ICONS1 v3 REPICK {u64 MapSystem request, u32 runs, u32 pad}')
T = g.alloc('I1REPICK', 'FAR_CODE', SIZE * 4, 'ICONS1 v3 0x114B9E8: run the trend step 0x1120B80 again (reconstructed)')
a = C.Asm(T)
a(C.sub_xi('sp', 'sp', 0x40))
a(C.stp_x(0, 1, 'sp', 0))
a(C.stp_x(2, 3, 'sp', 0x10))
a(C.stp_x(4, 5, 'sp', 0x20))
a(C.stp_x(6, 7, 'sp', 0x30))
a(lambda pc, L: C.adrp(pc, 9, BOX))
a(C.add_xi(9, 9, C.lo12(BOX)))
a(C.ldr_x(0, 9, 0))
a(C.to(C.cbz_x, 'x0', 'done'))
a(C.str_x('xzr', 9, 0))                                    # box = 0 (once per request)
a(C.ldr_w(10, 9, 8))
a(C.add_wi(10, 10, 1))
a(C.str_w(10, 9, 8))                                       # runs += 1
a.many(lambda pc, L: C.far_call(pc, TREND))                # 0x1120B80(MS)
a.label('done')
a(C.ldp_x(0, 1, 'sp', 0))
a(C.ldp_x(2, 3, 'sp', 0x10))
a(C.ldp_x(4, 5, 'sp', 0x20))
a(C.ldp_x(6, 7, 'sp', 0x30))
a(C.add_xi('sp', 'sp', 0x40))
a.many(lambda pc, L: C.relocate(SITE, pc))                 # adrp x8, #0x5b4d000
a.many(lambda pc, L: C.far_jump(pc, BACK))
assert len(a.words()) <= SIZE, len(a.words())
assert 0 not in a.words(), 'an encoder is missing in cave_lib'
cave = g.cave('I1REPICK', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> I1REPICK 0x%X (x16 dead at 0x114B9E8)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'adrp x8, #0x5b4d000', C.b(SITE, PAD), 'ICONS1 v3 REPICK (UpdatePhase, reconstructed)')]
HOOK_WORD = C.b(SITE, PAD)

groups = {'I1REPICK_CAVE': cave + tramp, 'I1REPICK': hook}
order = ['I1REPICK_CAVE', 'I1REPICK']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word 0x%08X' % HOOK_WORD)
print('registry rows (lead adds):')
print('| icons1v3_gen | I1RBOX | 0x%X..0x%X | ICONS1 v3 {u64 MS request, u32 runs} (FAR_DATA) |' % (BOX, BOX + 16))
print('| icons1v3_gen | I1REPICK | 0x%X..0x%X | ICONS1 v3 0x114B9E8 (UpdatePhase): trend step 0x1120B80 once more on '
      'request (alpha, reconstructed); trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Alpha 2')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'I1REPICK': 0x%X, 'I1RBOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_WORD': 0x%X}" % (T, BOX, PAD, HOOK_WORD)
                + chr(10))
