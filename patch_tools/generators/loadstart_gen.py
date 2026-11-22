"""loadstart_gen.py: LOADSTART, second candidate for the final-load crash. Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes loadstart_live.py.
python loadstart_gen.py [--dry]      (from diag/net)

Stock: the scheduler 0x3FF9100 picks the next unstarted ring entry (state +0x80 == 0 and cancel bit +0x81.0
clear) UNDER the ring lock (csel x20 at 0x3FF9EC8 / 0x3FFA068 / 0x3FFA208 / 0x3FFA3A8), unlocks, and only then
marks it started (`strb w28 (=1), [x20, #0x80]`) and calls its vt+0x50. A worker pops an entry with the cancel
bit set and state 0 under the same lock and deletes it (0x3FFA9AC). So a Release on another thread (bit 0 set,
the queued path of 0x3FFB860) between that unlock and the mark lets a worker free the entry while the scheduler
starts it: the b_final crash at 0x3FFA0DC. LOADSTART marks the picked entry started while the lock is held (same
limit test w24 < w22 as the stock code after the unlock); the stock mark after the unlock stays (same value)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'loadstart_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []
PLANNED = [
    ('takerace_gen', 'TRBOX', 0xC50F710, 0xC50F8C0), ('takerace_gen', 'TRGRANT', 0xC503AF8, 0xC503CF8),
    ('takerace_gen', 'TRFRAME', 0xC503CF8, 0xC504018),
    ('needdata_gen', 'NDBOX', 0xC50F8C0, 0xC50F8D0), ('needdata_gen', 'NEEDDATA', 0xC504018, 0xC504078),
    ('outhide_gen', 'OHBOX', 0xC50F8D0, 0xC50F8D8), ('outhide_gen', 'OUTHIDE', 0xC504078, 0xC5040C8),
    ('icons1_gen', 'I1BOX', 0xC50F8D8, 0xC50F8E0), ('icons1_gen', 'ICONS1', 0xC5040C8, 0xC504118),
    ('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0), ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8),
    ('loadrel_gen', 'LRBOX', 0xC50F8F0, 0xC50F8F8), ('loadrel_gen', 'LOADREL', 0xC5041A8, 0xC5041F8),
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



SITES = (0x3FF9EC8, 0x3FFA068, 0x3FFA208, 0x3FFA3A8)
for site in SITES:
    stock(site, 'csel x20, x8, xzr, eq')
    stock(site + 4, 'mov x0, x21')
    stock(site + 8, 'bl #0x4927db0')
    stock(site + 12, 'cbz x20, #0x%x' % (C.text_word(site + 12) and int(dis(site + 12).split('#')[1], 16)))
    stock(site + 16, 'cmp w24, w22')
    assert dis(site + 20).startswith('b.ge ')
    stock(site + 24, 'strb w28, [x20, #0x80]')
    assert targets_in(site, site + 4) == []
    assert not any(x in C.SHIPPED for x in range(site, site + 4))
for a in (0x3FF9E14, 0x3FF9FF4, 0x3FFA18C, 0x3FFA32C):
    stock(a, 'mov w28, #1')
listing.append('each site: flags and x16/x17 are dead (the next word after the cave is mov x0, x21, then bl unlock); '
               'w24 / w22 are the loop index and limit, w28 = 1 from the loop head')

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
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


g = C.Gen('loadstart_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 10
taken = [0x3F7BB74]  # LOADREL's trampoline
cave_recs, hook_recs, rows = [], [], []
for k, site in enumerate(SITES):
    pad = find_pad(site, 3, taken)
    assert pad
    taken.append(pad)
    T = g.alloc('LOADSTART%d' % k, 'FAR_CODE', SIZE * 4, 'LOADSTART site 0x%X: mark the picked entry started '
                'under the ring lock' % site)
    a = C.Asm(T)
    a(C.csel_x(20, 8, 'xzr', 'eq') if hasattr(C, 'csel_x') else C.text_word(site))  # the replaced word
    a(C.to(C.cbz_x, 'x20', 'back'))
    a(C.cmp_wr(24, 22))
    a(C.to(C.bcond, 'ge', 'back'))
    a(C.strb(28, 20, 0x80))
    a.label('back')
    a.many(lambda pc, L, s=site: C.far_jump(pc, s + 4))
    assert len(a.words()) <= SIZE, len(a.words())
    assert 0 not in a.words()
    cave_recs += g.cave('LOADSTART%d' % k, T, a)
    cave_recs += [g.text_patch(pad + 4 * j, 'udf #0', w, 'trampoline -> LOADSTART%d 0x%X' % (k, T))
                  for j, w in enumerate(C.far_jump(pad, T))]
    hook_recs.append(g.text_patch(site, 'csel x20, x8, xzr, eq', C.b(site, pad), 'LOADSTART%d' % k))
    listing.append('site 0x%X: trampoline 0x%X..0x%X after `%s`, cave 0x%X' % (site, pad, pad + 12, dis(pad - 4), T))
    rows.append('| loadstart_gen | LOADSTART%d | 0x%X..0x%X | LOADSTART 0x%X: mark the picked load entry started under '
                'the ring lock; trampoline 0x%X..0x%X |' % (k, T, T + SIZE * 4, site, pad, pad + 12))

groups = {'LOADSTART_CAVE': cave_recs, 'LOADSTART': hook_recs}
order = ['LOADSTART_CAVE', 'LOADSTART']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows (lead adds):')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
