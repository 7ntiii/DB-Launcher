"""loadrel_gen.py: LOADREL, the final-load crash root fix. Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes loadrel_live.py.
python loadrel_gen.py [--dry]      (from diag/net)

Stock: the load-process manager's Release 0x3FFB720 (vtable slots 0x56D3418 / 0x599C820 -> 0x3FF6F68) drops the
last reference of a CSLoadProcessData_* entry and then: if +0x81 bit 1 (in the pending ring) is set, sets the
cancel bit 0 and leaves the delete to the worker's pop (0x3FFA9AC, 0x3FFAC94, ..); if the state +0x80 is 3 (done),
unlinks it from the done list and deletes it; otherwise it DELETES IT AT ONCE (0x3FFB90C). A worker pops an
entry in state 2 under the ring lock, clears bit 1 (mask 0xFF0007FD) and runs its vt+0x70 OUTSIDE the lock
(0x3FFA978..0x3FFA9A0); when that returns 1 it pushes the same pointer back into the ring (0x3FFA87C..0x3FFA8B4).
So a Release while a worker holds the entry (state 2, bit 1 clear) frees it under the worker, and the worker
then queues the freed pointer: the scheduler 0x3FF9100 later runs it (crash at 0x3FFA0DC / 0x3FF9994->0x3FEE4E8).
LOADREL: at 0x3FFB864 (the state test of that last branch), state 1 or 2 takes the stock cancel path 0x3FFB8A8
instead (bit 0 set, the file request's vt+0x48 cancel, return 1): the worker's next pop deletes it, as for a
queued entry. A worker that finishes it instead leaves it in the done list (a small leak, never a free in use)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'loadrel_live.py'
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


REL, SITE, BACK, CANCEL = 0x3FFB720, 0x3FFB864, 0x3FFB868, 0x3FFB8A8
# ================================================================ code facts [V]
for a, t in (
        # Release(mgr x0, proc x1): last reference, no lock
        (REL, 'cbz x1, #0x3ffb784'), (0x3FFB738, 'ldur w8, [x1, #0x81]'), (0x3FFB744, 'mov x19, x1'),
        (0x3FFB754, 'ldr w10, [x1, #0x50]'), (0x3FFB758, 'subs w10, w10, #1'), (0x3FFB75C, 'str w10, [x1, #0x50]'),
        (0x3FFB858, 'ldur w8, [x19, #0x81]'),
        (0x3FFB860, 'tbnz w8, #1, #0x3ffb8a8'),                 # in the ring: the stock cancel path
        (SITE, 'ldrb w8, [x19, #0x80]'), (BACK, 'cmp w8, #3'), (0x3FFB86C, 'b.ne #0x3ffb90c'),
        (0x3FFB870, 'ldrb w8, [x19, #0x80]'),
        (CANCEL, 'orr w8, w8, #1'), (0x3FFB8AC, 'stur w8, [x19, #0x81]'), (0x3FFB8B0, 'ldr x8, [x19, #0x70]'),
        (0x3FFB8C4, 'ldr x8, [x8, #0x48]'), (0x3FFB8CC, 'b #0x3ffb93c'), (0x3FFB93C, 'mov w0, #1'),
        (0x3FFB90C, 'mov x0, x19'), (0x3FFB924, 'blr x8'),      # the immediate delete (vt+8, then free)
        (0x3FF6F68, 'ldr x0, [x0, #8]'), (0x3FF6F6C, 'b #0x3ffb720'),
        # the worker: pop state 2 (or bit 0 and state 0), clear bit 1, unlock, vt+0x70, push back on 1
        (0x3FFA938, 'cmp w10, #2'), (0x3FFA958, 'stur w9, [x21, #0x81]'), (0x3FFA974, 'bl #0x4927db0'),
        (0x3FFA97C, 'tbnz w8, #0, #0x3ffa9ac'), (0x3FFA9A0, 'blr x8'), (0x3FFA9A8, 'b #0x3ffa87c'),
        (0x3FFA8A8, 'str x21, [x9, w8, sxtw #3]'), (0x3FFA8B0, 'orr w8, w8, #2'),
        # the scheduler's start of a ring entry (the b_final crash site) and its job poll (B m4)
        (0x3FFA0D8, 'blr x8'), (0x3FF9990, 'bl #0x3fee3e0')):
    stock(a, t)
assert targets_in(SITE, SITE + 4) == []
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
listing.append('0x3FFB864: w8 is rewritten by the word itself; w9/x9 are written before any read on every path '
               'after it (0x3FFB88C ldr x9 / 0x3FFB90C..; the cancel path uses w8, x8, x0); flags are set again '
               'at 0x3FFB868; x16/x17 are dead (no use before the next bl)')

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

g = C.Gen('loadrel_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 20
BOX = g.alloc('LRBOX', 'FAR_DATA', 8, 'LOADREL {u32 in-flight releases turned into cancels, u32 pad}')
T = g.alloc('LOADREL', 'FAR_CODE', SIZE * 4, 'LOADREL 0x3FFB864: Release of an in-flight load process cancels '
            'instead of deleting')
a = C.Asm(T)
a(C.ldrb(9, 19, 0x80))                                     # state
a(C.cmp_wi(9, 1))
a(C.to(C.beq, 'cancel'))
a(C.cmp_wi(9, 2))
a(C.to(C.beq, 'cancel'))
a(C.ldrb(8, 19, 0x80))                                     # the replaced word
a.many(lambda pc, L: C.far_jump(pc, BACK))
a.label('cancel')
a(lambda pc, L: C.adrp(pc, 9, BOX))                        # x9 / w10 are dead on the cancel path too
a(C.add_xi(9, 9, C.lo12(BOX)))
a(C.ldr_w(10, 9, 0))
a(C.add_wi(10, 10, 1))
a(C.str_w(10, 9, 0))                                       # uses += 1 (read by the assist)
a(C.ldur_w(8, 19, 0x81))                                   # fresh flags for the stock cancel path
a.many(lambda pc, L: C.far_jump(pc, CANCEL))
assert len(a.words()) <= SIZE, len(a.words())
assert 0 not in a.words(), 'an encoder is missing in cave_lib'
cave = g.cave('LOADREL', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LOADREL 0x%X (x16 dead at 0x3FFB864)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'ldrb w8, [x19, #0x80]', C.b(SITE, PAD), 'LOADREL (load-process Release)')]
HOOK_WORD = C.b(SITE, PAD)

groups = {'LOADREL_CAVE': cave + tramp, 'LOADREL': hook}
order = ['LOADREL_CAVE', 'LOADREL']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word 0x%08X' % HOOK_WORD)
print('registry rows (lead adds):')
print('| loadrel_gen | LRBOX | 0x%X..0x%X | LOADREL {u32 uses} (FAR_DATA) |' % (BOX, BOX + 8))
print('| loadrel_gen | LOADREL | 0x%X..0x%X | LOADREL 0x3FFB864 (load-process Release): state 1/2 entries are '
      'cancelled, not deleted under a worker; trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'LOADREL': 0x%X, 'LRBOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_WORD': 0x%X}" % (T, BOX, PAD, HOOK_WORD) + chr(10))
