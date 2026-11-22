"""loadgrave_gen.py: LOADGRAVE, third candidate for the final-load crash family. Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes loadgrave_live.py.
python loadgrave_gen.py [--dry]      (from diag/net)

Stock: every synchronous delete of a load-process entry by the manager's Release 0x3FFB720 ends at 0x3FFB90C:
`mov x0, x19; bl 0x46F52E0` (the heap that owns x19), the entry's vt+8 (destructor), then that heap's vt+0x70
(free). Paths there: state 3 (done, unlinked from the done list) and every state not taken by the cancel path
(LOADREL already sends states 1 / 2 to the cancel path). The deferred path (bit 1 in ring -> cancel bit, the
worker's pop deletes it) does not come here. The alpha-4/5 crashes show memory written after it was freed
(1.0f / FLT_MAX bounds over a freed Geomhkxbnd entry; allocator 0x1D7CF94; scheduler 0x3FFA0DC; alpha 5 m33: a
chr animation task 0x17B2020 -> 0x17432C0 -> 0x1937760 -> 0x3ACA0A0 reading a pointer 0xFFFFFFFF'2B5C2470).
LOADGRAVE parks each entry Release would delete in a 128-slot ring (GRAVE) and deletes the entry parked 128
deletes earlier instead (the same stock destructor + free, on the same kind of thread). An entry is therefore
freed only after 127 later deletes; a late writer then hits a still-allocated, unused entry, not reused memory.
The slot index is taken with ldaddal and the slot swapped with swpal (Release runs on several threads)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'loadgrave_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
SLOTS = 128
listing = []


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


# LSE atomics and two encodings cave_lib has no helper for (checked with capstone below).
def ldaddal_w(rs, rt, rn): return 0xB8E00000 | (C.R(rs) << 16) | (C.R(rn) << 5) | C.R(rt)
def swpal_x(rs, rt, rn): return 0xF8E08000 | (C.R(rs) << 16) | (C.R(rn) << 5) | C.R(rt)
def and_w_lowbits(rd, rn, nbits): return 0x12000000 | ((nbits - 1) << 10) | (C.R(rn) << 5) | C.R(rd)
def add_x_lsl(rd, rn, rm, sh): return 0x8B000000 | (C.R(rm) << 16) | (sh << 10) | (C.R(rn) << 5) | C.R(rd)


SITE, AFTER, RET1 = 0x3FFB90C, 0x3FFB910, 0x3FFB93C
stock(SITE, 'mov x0, x19')
stock(AFTER, 'bl #0x46f52e0')
stock(0x3FFB920, 'ldr x8, [x8, #8]')
stock(0x3FFB938, 'blr x8')
stock(RET1, 'mov w0, #1')
stock(0x3FFB940, 'b #0x3ffb774')
stock(0x3FFB774, 'ldp x20, x19, [sp, #0x20]')
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
listing.append('0x3FFB90C: x0-x17 and the flags are dead (the next words are mov x0, x19; bl). x19 is callee-saved '
               'and restored by the epilogue 0x3FFB774, so the cave may point it at the evicted entry.')
others = C.live_records(exclude=(OUT,))
into = [p for p in targets_in(SITE, SITE + 4)]
listing.append('branches into 0x3FFB90C (all now reach the cave, as wanted): ' + ', '.join('0x%X' % p for p in into))


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


g = C.Gen('loadgrave_gen', out=OUT, dry=True)
PLANNED = [('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0), ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)]
for owner, tag, lo, hi in PLANNED:  # not baked yet: keep them free
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
BOX = g.alloc('GYBOX', 'FAR_DATA', 8, 'LOADGRAVE {u32 deletes parked so far, u32 pad} (FAR_DATA)', align=8)
GRAVE = g.alloc('GRAVE', 'FAR_DATA', SLOTS * 8, 'LOADGRAVE ring of %d parked load-process entries (u64)' % SLOTS,
                align=8)
SIZE = 20
T = g.alloc('LOADGRAVE', 'FAR_CODE', SIZE * 4, 'LOADGRAVE 0x3FFB90C: park the entry, delete the one parked %d '
            'deletes ago' % SLOTS)
taken = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C]  # LOADREL / LOADSTART trampolines
pad = find_pad(SITE, 3, taken)
assert pad

a = C.Asm(T)
a.many(lambda pc, L: [C.adr(pc, 'x9', BOX)])
a(C.movz_w('w10', 1))
a(ldaddal_w('w10', 'w11', 'x9'))            # w11 = this delete's number
a(and_w_lowbits('w11', 'w11', 7))           # slot = number % 128
a.many(lambda pc, L: [C.adr(pc, 'x9', GRAVE)])
a(add_x_lsl('x9', 'x9', 'x11', 3))
a(swpal_x('x19', 'x12', 'x9'))              # park x19, take the entry parked there before
a(C.mov_x('x19', 'x12'))
a(C.to(C.cbz_x, 'x19', 'none'))
a(C.mov_x('x0', 'x19'))                     # the replaced word, for the evicted entry
a.many(lambda pc, L: C.far_jump(pc, AFTER))
a.label('none')                             # slot was empty: nothing to delete yet; Release returns 1
a.many(lambda pc, L: C.far_jump(pc, RET1))
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words
expect = {2: 'ldaddal w10, w11, [x9]', 3: 'and w11, w11, #0x7f', 5: 'add x9, x9, x11, lsl #3',
          6: 'swpal x19, x12, [x9]'}
for i, t in expect.items():
    got = C.dis1(T + 4 * i, words[i])
    assert got == t, 'word %d: %s, expected %s' % (i, got, t)

cave_recs = g.cave('LOADGRAVE', T, a)
cave_recs += [g.text_patch(pad + 4 * j, 'udf #0', w, 'trampoline -> LOADGRAVE 0x%X' % T)
              for j, w in enumerate(C.far_jump(pad, T))]
hook_recs = [g.text_patch(SITE, 'mov x0, x19', C.b(SITE, pad), 'LOADGRAVE')]
listing.append('trampoline 0x%X..0x%X after `%s`, cave 0x%X, GYBOX 0x%X, GRAVE 0x%X..0x%X' % (
    pad, pad + 12, dis(pad - 4), T, BOX, GRAVE, GRAVE + SLOTS * 8))
rows = [
    '| loadgrave_gen | GYBOX | 0x%X..0x%X | LOADGRAVE {u32 deletes parked, u32 pad} (FAR_DATA) |' % (BOX, BOX + 8),
    '| loadgrave_gen | GRAVE | 0x%X..0x%X | LOADGRAVE ring of %d parked load-process entries (FAR_DATA) |' % (
        GRAVE, GRAVE + SLOTS * 8, SLOTS),
    '| loadgrave_gen | LOADGRAVE | 0x%X..0x%X | LOADGRAVE 0x3FFB90C: park the entry Release deletes, delete the one '
    'parked %d deletes ago; trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, SLOTS, pad, pad + 12),
]

groups = {'LOADGRAVE_CAVE': cave_recs, 'LOADGRAVE': hook_recs}
order = ['LOADGRAVE_CAVE', 'LOADGRAVE']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows (lead adds):')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
