"""geomid_gen (proposed for alpha 19, NOT BAKED): GEOMID - skill assets (Mama Natha's serpent AEG099_020, the Neb-ra
Vanishing decoy AEG099_030, Eye-kin / item assets) are created in LAN.

Why they fail today [V, static]:
  bullet 0x18C6B28 reads the asset id at bullet+0xC8 (0x18C6D2C) and calls the 0x71 request 0xFB0680 with w3 = 1
  (0x18C76F4). 0xFB0680 builds the 0xA0 record; record+0 = the new geom id:
      0xFB074C ldr  w8, [x0, #0x18]          x0 = mgr3 (*(main+0x5B3CE08)); +0x18 != 0 = in a session
      0xFB0750 cbnz w8, #0xfb0770            IN A SESSION: skip the local allocation, id stays 0 (the server fills it)
      0xFB0754..0xFB0760 blr [[x23+0x1C0]+0x10]   the block's id allocator (offline only)
      0xFB0764 str  w0, [sp]                 record+0 = id
  The reader 0xFAF120 -> 0xFAFC60 / 0xFAFE7C -> 0xFAF3C0 -> 0xFC25E0 (w2 = id) has
      0xFC2618 cbz  w8, #0xfc2720            id 0 -> return NULL: the asset is never made, not even on the caster.
  LAN has no server, so in a session every 0x71 request carries id 0 and no game creates the serpent.
  (Breakables 0xE30994 pass w3 = 0 and create locally, which is why BREAK_SHARE's chair test passed.)

GEOMID (every game; needs BREAK_SHARE, built in since v3.9.12, so the request reaches every game incl. the self link):
  0xFB0750 cbnz w8, #0xfb0770 -> nop      allocate the id locally in a session too
  0xFB0764 str  w0, [sp]      -> b PAD    PAD = 3-word text-padding trampoline -> far cave GEOMID:
      in a session: id bits 16..19 = own player number (pgd+0xD0, 1..15), so ids made by different games never
      clash in a receiver's geom tree (0xFC9980 insert-or-find keyed by id & 0xFFFFF; a clash would overwrite).
      salted ids are >= 0x10000, so handle decode (idx >> 4 > 0x752) still uses the dynamic tree (0xFEC6E0).
      then the displaced `str w0, [sp]` and a far return to 0xFB0768.
  x16 is dead at 0xFB0764 (right after `blr x8`); x8 / x9 are dead (x0 reloaded at 0xFB0768, x8 rewritten at
  0xFB0770, x9 unused up to the epilogue).

    python -I geomid_gen.py            dry (default): no registry write, writes geomid_records_DRY.py here
    python -I geomid_gen.py --claim    LEAD ONLY: claims the FAR_CODE row in cave_registry.md, writes geomid_live.py here
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

CLAIM = '--claim' in sys.argv
OUT = os.path.join(HERE, 'geomid_live.py' if CLAIM else 'geomid_records_DRY.py')
NOPW, SITE, BACK = 0xFB0750, 0xFB0764, 0xFB0768
GDM = 0x5B57EB8                 # *(GDM)+0x20 = local PlayerGameData, +0xD0 = own player number (powers_gen, sigil_gen)
SALT_LSB = 16
PACIBSP = 0xD503237F
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)

for a, t in ((0xFB0740, 'ldr x19, [x19, #0xec8]'), (0xFB0744, 'ldr x0, [x19]'), (0xFB074C, 'ldr w8, [x0, #0x18]'),
             (NOPW, 'cbnz w8, #0xfb0770'), (0xFB0754, 'ldr x8, [x23, #0x1c0]'), (0xFB0758, 'add x0, x23, #0x1c0'),
             (0xFB075C, 'ldr x8, [x8, #0x10]'), (0xFB0760, 'blr x8'), (SITE, 'str w0, [sp]'), (BACK, 'ldr x0, [x19]'),
             (0xFB076C, 'cbz x0, #0xfb092c'), (0xFB0770, 'ldr x8, [x0, #0x10]!'), (0xFB0778, 'mov w1, #0x71'),
             (0x18C76F4, 'bl #0xfb0680'), (0xFC2618, 'cbz w8, #0xfc2720'), (0xFC2634, 'and w8, w8, #0xfffff')):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)
# BREAK_SHARE must be built in (request broadcast, read from anyone): shipped word or a live record
for a, t in ((0xFB0780, 'ldr x8, [x8, #0x40]'), (0xFAF314, 'ldr x8, [x8, #0x50]')):
    if all(a + i in C.SHIPPED for i in range(4)):
        got = C.dis1(a, C.shipped_word(a))
        assert got == t, 'BREAK_SHARE word %x is %s, expected %s' % (a, got, t)
    else:
        print('NOTE: BREAK_SHARE word 0x%X is not in patch_manager.cpp; GEOMID needs it (breakshare_live.py)' % a)

others = C.live_records(exclude=(os.path.basename(OUT),))
for a in (NOPW, SITE):
    assert not any(x in C.SHIPPED or x in others for x in range(a, a + 4)), 'site %x already patched' % a

# text-padding trampolines named in cave_registry.md text (rows without a *_live.py yet)
REG_TRAMPS = []
for m in re.finditer(r'trampoline 0x([0-9A-Fa-f]+)\.\.0x([0-9A-Fa-f]+)', open(C.REGISTRY, encoding='utf-8').read()):
    REG_TRAMPS.append((int(m.group(1), 16), int(m.group(2), 16)))


def branch_target(pc, w):
    if (w & 0x7C000000) == 0x14000000:
        imm = w & 0x3FFFFFF
        return pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
    if (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000 or (w & 0x3B000000) == 0x18000000:
        imm = (w >> 5) & 0x7FFFF
        return pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
    if (w & 0x7E000000) == 0x36000000:
        imm = (w >> 5) & 0x3FFF
        return pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
    if (w & 0x9F000000) == 0x10000000:
        d = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
        return pc + (d - (1 << 21) if d & (1 << 20) else d)
    return None


def find_pad(site, n):
    """3 zero words before a pacibsp, after a non-bl word, unreferenced (no branch / adr / pointer), in reach."""
    cands = []
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP or C.dis1(a - 4, W[a // 4 - 1]).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if any(lo < a + 4 * n and a < hi for lo, hi in REG_TRAMPS):
                continue
            cands.append((abs(a - site), a, z))
    cands.sort()
    hit = set()
    for _, a, z in cands[:40]:
        hit.add((a, z))
    refd = set()
    for i, w in enumerate(W):            # one pass over text for branch / adr references into the candidates
        t = branch_target(4 * i, w)
        if t is not None:
            for a, z in hit:
                if a <= t < z:
                    refd.add(a)
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        for x in struct.unpack_from('<%dQ' % (len(blob) // 8), blob, 0):
            for a, z in hit:
                if a <= x < z:
                    refd.add(a)
    for _, a, z in cands[:40]:
        if a not in refd and C.reach(site, a):
            return a
    return None


PAD = find_pad(SITE, 3)
assert PAD, 'no trampoline padding near 0x%X' % SITE


def bfi_w(rd, rn, lsb, width):
    return 0x33000000 | (((32 - lsb) % 32) << 16) | ((width - 1) << 10) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, bfi_w('w0', 'w8', SALT_LSB, 4)) == 'bfi w0, w8, #0x10, #4'


def asm(start):
    a = C.Asm(start)
    a(C.ldr_x(8, 19, 0))                                     # mgr3 (x19 = &main+0x5B3CE08, 0xFB0740)
    a(C.to(C.cbz_x, 'x8', 'store'))
    a(C.ldr_w(8, 8, 0x18))
    a(C.to(C.cbz_w, 'w8', 'store'))                          # not in a session: stock id, unsalted
    a(lambda pc, L: C.adrp(pc, 9, GDM))
    a(C.ldr_x(9, 9, C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x9', 'store'))
    a(C.ldr_x(9, 9, 0x20))                                   # local PlayerGameData
    a(C.to(C.cbz_x, 'x9', 'store'))
    a(C.ldr_w(8, 9, 0xD0))                                   # own player number
    a(C.sub_wi(9, 8, 1))
    a(C.cmp_wi(9, 15))
    a(C.to(C.bcond, 'hs', 'store'))                          # only 1..15
    a(bfi_w('w0', 'w8', SALT_LSB, 4))                        # id bits 16..19 = player number
    a.label('store')
    a(C.str_w(0, 'sp', 0))                                   # the displaced `str w0, [sp]`
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    return a


g = C.Gen('geomid_gen', out=os.path.basename(OUT), dry=not CLAIM)
n = len(asm(0xC500000).words())
start = g.alloc('GEOMID', 'FAR_CODE', (n * 4 + 15) // 16 * 16,
                'GEOMID 0xFB0764: skill / item assets (0x71 request) get a local geom id in a session, salted with the '
                'player number (bits 16..19), so the serpent / decoy are created; trampoline 0x%X..0x%X' % (PAD, PAD + 12))
cave = g.cave('GEOMID', start, asm(start))
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> GEOMID 0x%X' % start)
         for k, w in enumerate(C.far_jump(PAD, start))]
hook = [g.text_patch(NOPW, 'cbnz w8, #0xfb0770', C.NOP, '0x71 request: allocate the geom id in a session too'),
        g.text_patch(SITE, 'str w0, [sp]', C.b(SITE, PAD), 'record+0 = salted id (GEOMID cave)')]
groups = {'GEOMID_CAVE': cave, 'GEOMID': tramp + hook}
ORDER = ['GEOMID_CAVE', 'GEOMID']
print('\n'.join(g.listing))
C.write_live(OUT, groups, ORDER, """
GEOMID, proposed alpha 19 (generated by diag/net/zt_faults/skills/geomid_gen.py%s): the 0x71 asset request
0xFB0680 gets a local geom id in a session (0xFB0750 nop), salted with the player number (cave at 0xFB0764), so
bullet-made assets (Mama Natha serpent AEG099_020, Neb-ra decoy AEG099_030) are created on every game.
Apply on EVERY game, with BREAK_SHARE. Expected: geoms_probe.py on A and B shows a dynamic geom AEG099_020 with
id >= 0x10000 after Trang casts Mama Natha.""" % ('' if CLAIM else ', DRY: registry row not claimed'))
for name in ORDER:
    d, r = C.cpp_rows(name, groups[name])
    print('// ---- %s\n%s\n%s' % (name, d, r))
print('cave 0x%X (%d words, %d bytes claimed), trampoline 0x%X; %s' % (
    start, n, (n * 4 + 15) // 16 * 16, PAD, 'CLAIMED' if CLAIM else 'DRY'))
print('registry row: | geomid_gen | GEOMID | 0x%X..0x%X | ... |' % (start, start + (n * 4 + 15) // 16 * 16))
