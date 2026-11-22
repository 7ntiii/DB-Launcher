"""listguard_gen.py: LISTGUARD, guest-side guard for the final's start list (v4.48). Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes listguard_live.py.
python listguard_gen.py [--dry]      (from diag/net)

Stock: a game takes a start list (message 0x51) only in the mediator pump: 0x10EF9D8 reads it from the net
object (vt+0x60, server only; START_AREA_LIST makes it vt+0x50, anyone), vt+0x10 parses it into the frame at sp
(entries of 0x68 from sp+0, u32 player no at entry+0, u64 count at sp+0x348), and 0x10EFA0C
`bl 0x10EFAC0` applies it (mediator in x0): per entry 0x10F36C0 merges the entry into M+0x290 by player no,
then M+0xB9 = 1 and, when M+0x688, 0x10F3F00 places every listed player (0x10EFDAC: another player's copy is
warped at once via chr vt+0x7F0; our own player gets M+0x6A8 until stage+0x4728). The assist never feeds the
list; it can only read it after the game applied it. So the guard needs this record.

LISTGUARD hooks 0x10EFA0C. While LGBOX.armed (the assist arms it on a guest in round 4 from phase 21):
  - a list after one was taken this final (LGBOX.taken), or while M+0xB9 is already set (the game holds a list,
    e.g. its own build): not applied (one list per final);
  - LGBOX.strict (first ~3 s): a list with fewer than LGBOX.need entries or without LGBOX.local_no: not applied;
  - otherwise applied (stock call) and LGBOX.taken = 1.
Skipped lists are counted (LGBOX.skipped, LGBOX.last_count). Not armed: stock, word for word."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'listguard_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
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


SITE, APPLY, BACK = 0x10EFA0C, 0x10EFAC0, 0x10EFA10
stock(0x10EF9D0, 'mov w1, #0x51')
stock(0x10EF9E0, 'blr x8')
stock(0x10EFA00, 'mov x1, sp')
stock(0x10EFA04, 'add x2, sp, #0x3a0')
stock(0x10EFA08, 'mov x0, x19')
stock(SITE, 'bl #0x10efac0')
stock(BACK, 'ldr x8, [x24]')
stock(0x10EFBC8, 'ldr x8, [x20, #0x348]')   # the apply reads the count from the parsed frame (x20 = x1)
stock(0x10EFC14, 'ldr w8, [x20]')           # and each entry's player no at entry+0, stride 0x68
stock(0x10EFC00, 'add x20, x20, #0x68')
stock(0x10EFCD0, 'strb w8, [x19, #0xb9]')
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
others = C.live_records(exclude=(OUT,))
assert not any(x in others for x in range(SITE, SITE + 4)), 'another record owns 0x10EFA0C'
into = targets_in(SITE, SITE + 4)
assert not into, 'branches into the site: %s' % into
listing.append('0x10EFA0C `bl 0x10EFAC0`: x0 = mediator, x1 = parsed list (sp), x2 = sp+0x3A0; x9-x16 and the '
               'flags are dead across a call, so the cave may use them on both paths')


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


g = C.Gen('listguard_gen', out=OUT, dry=True)
PLANNED = [('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0), ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)]
for owner, tag, lo, hi in PLANNED:  # not baked yet: keep them free
    if not any(r['tag'] == tag for r in g._rows()):
        g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
# LGBOX: +0 u8 armed, +1 u8 strict, +2 u8 taken, +3 pad, +4 u32 local_no, +8 u32 need, +12 u32 skipped,
# +16 u32 taken count, +20 u32 last skipped list's entry count
BOX = g.alloc('LGBOX', 'FAR_DATA', 24, 'LISTGUARD {u8 armed, u8 strict, u8 taken, u8, u32 local_no, u32 need, '
              'u32 skipped, u32 taken, u32 last_count} (FAR_DATA)', align=8)
SIZE = 44
T = g.alloc('LISTGUARD', 'FAR_CODE', SIZE * 4, 'LISTGUARD 0x10EFA0C: one complete start list per final (guest)')
taken_pads = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C, 0x3F7DC54]  # LOADREL/LOADSTART/LOADGRAVE
pad = find_pad(SITE, 5, taken_pads)
assert pad
TAKE_STUB = pad + 12            # pad: far_jump -> cave (3 words), then `bl 0x10EFAC0`, `b 0x10EFA10`

a = C.Asm(T)
a.many(lambda pc, L: [C.adr(pc, 'x9', BOX)])
a(C.ldrb('w10', 'x9', 0))                   # armed?
a(C.to(C.cbz_w, 'w10', 'apply'))
a(C.ldrb('w10', 'x9', 2))                   # one list already taken this final
a(C.to(C.cbnz_w, 'w10', 'skip'))
a(C.ldrb('w10', 'x0', 0xB9))                # the game already holds a list (its own build)
a(C.to(C.cbnz_w, 'w10', 'held'))
a(C.ldrb('w10', 'x9', 1))                   # strict?
a(C.to(C.cbz_w, 'w10', 'take'))
a(C.ldr_x('x10', 'x1', 0x348))              # entry count of this list
a(C.to(C.cbz_x, 'x10', 'skip'))
a(C.cmp_xi('x10', 8))
a(lambda pc, L: C.bcond(pc, 'hi', L['skip']))
a(C.ldr_w('w11', 'x9', 8))   # need (zero-extends into x11)
a(C.cmp_xr('x10', 'x11'))
a(lambda pc, L: C.blo(pc, L['skip']))
a(C.ldr_w('w12', 'x9', 4))                  # local_no
a(C.mov_x('x13', 'x1'))
a.label('loop')
a(C.ldr_w('w14', 'x13', 0))
a(C.cmp_wr('w14', 'w12'))
a(lambda pc, L: C.beq(pc, L['take']))
a(C.add_xi('x13', 'x13', 0x68))
a(C.sub_xi('x10', 'x10', 1))
a(C.to(C.cbnz_x, 'x10', 'loop'))
a(lambda pc, L: C.b(pc, L['skip']))
a.label('take')
a(C.movz_w('w10', 1))
a(C.strb('w10', 'x9', 2))
a(C.ldr_w('w10', 'x9', 16))
a(C.add_wi('w10', 'w10', 1))
a(C.str_w('w10', 'x9', 16))
a.label('apply')
a.many(lambda pc, L: C.far_jump(pc, TAKE_STUB))
a.label('held')                             # a list is held already: this final's one list is that one
a(C.movz_w('w10', 1))
a(C.strb('w10', 'x9', 2))
a.label('skip')
a(C.ldr_w('w10', 'x9', 12))
a(C.add_wi('w10', 'w10', 1))
a(C.str_w('w10', 'x9', 12))
a(C.ldr_x('x10', 'x1', 0x348))
a(C.str_w('w10', 'x9', 20))
a.many(lambda pc, L: C.far_jump(pc, BACK))
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words
for i, w in enumerate(words):
    listing.append('  %X: %s' % (T + 4 * i, C.dis1(T + 4 * i, w)))

cave_recs = g.cave('LISTGUARD', T, a)
tramp = C.far_jump(pad, T) + [C.bl(TAKE_STUB, APPLY), C.b(TAKE_STUB + 4, BACK)]
cave_recs += [g.text_patch(pad + 4 * j, 'udf #0', w, 'trampoline / take stub for LISTGUARD 0x%X' % T)
              for j, w in enumerate(tramp)]
hook_recs = [g.text_patch(SITE, 'bl #0x10efac0', C.b(SITE, pad), 'LISTGUARD')]
listing.append('trampoline 0x%X..0x%X after `%s` (take stub 0x%X: bl 0x10EFAC0; b 0x10EFA10), cave 0x%X, '
               'LGBOX 0x%X' % (pad, pad + 20, dis(pad - 4), TAKE_STUB, T, BOX))
rows = [
    '| listguard_gen | LGBOX | 0x%X..0x%X | LISTGUARD {u8 armed, u8 strict, u8 taken, u8, u32 local_no, u32 need, '
    'u32 skipped, u32 taken, u32 last_count} (FAR_DATA) |' % (BOX, BOX + 24),
    '| listguard_gen | LISTGUARD | 0x%X..0x%X | LISTGUARD 0x10EFA0C: one complete start list per final (guest); '
    'trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, pad, pad + 20),
]

groups = {'LISTGUARD_CAVE': cave_recs, 'LISTGUARD': hook_recs}
order = ['LISTGUARD_CAVE', 'LISTGUARD']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows (lead adds):')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
