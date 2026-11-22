"""needdata_gen.py: NEEDDATA, the game-thread half of v4.37 (b_loadhang_notes.md 5). Static generator,
allocated with Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes needdata_live.py.
python needdata_gen.py [--dry]      (from diag/net)

The pump 0x14DD180 answers the type-7 requests queued in P+0x88 (a std::vector<u64> of member ids) at 0x14DE8B4..
0x14DE944 when it can answer (w19 bit 0). A game that loaded first never queued anything, so its vector has no
storage and the assist cannot append to it safely from its own thread. NEEDDATA hooks 0x14DE8B4 (`cbz w19`): when
the game can answer and the box NDBOX {u32 valid, u32 answered, u64 id} holds a request (valid != 0), it copies the
id to the stock slot [sp+0x6F8], clears valid, counts it, and calls the stub 0x1CD9D88 (shipped, the same call the
stock drain makes at 0x14DE8D8) with x0 = P (x24), x1 = sp+0x6F8. Then it runs the stock drain from 0x14DE8B8.
The assist (dusk_lan.cpp NeedDataHeard) writes id, then valid = 1, only while valid == 0: one owner per state, so
neither side ever writes a word the other is writing. NEEDDATA does nothing when the box is empty or the game
cannot answer yet (the box waits for the next tick that can)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'needdata_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
SITE, BACK, SKIP, STUB, ANSWER = 0x14DE8B4, 0x14DE8B8, 0x14DE948, 0x1CD9D88, 0x14DC040
SLOT = 0x6F8
listing = []

# TAKERACE (v4.36, takerace_gen.py) rows the lead has not added yet: treat them as taken.
TAKERACE_ROWS = [
    ('TRBOX', 0xC50F710, 0xC50F8C0, 'TAKERACE box (FAR_DATA)'),
    ('TRGRANT', 0xC503AF8, 0xC503CF8, 'TAKERACE 0x11A49A4; trampoline 0x1126D8C..0x1126D98'),
    ('TRFRAME', 0xC503CF8, 0xC504018, 'TAKERACE 0x11A1EE4; trampoline 0x1122BB0..0x1122BBC'),
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


# ================================================================ code facts [V]
for a, t in ((0x14DE7D0, 'add x20, x24, #0x88'),              # x20 = &vector (begin/end/cap at x24+0x88/0x90/0x98)
             (0x14DE7D8, 'tbz w19, #0, #0x14de840'),           # w19 bit 0 = can answer
             (0x14DE818, 'b.eq #0x14de8b4'),                   # receive loop empty (can answer)
             (0x14DE87C, 'b.ne #0x14de8b4'),                   # receive loop empty (cannot answer: queued)
             (0x14DE880, 'ldp x8, x9, [x24, #0x90]'), (0x14DE890, 'str x9, [x8], #8'),
             (SITE, 'cbz w19, #0x14de948'),
             (BACK, 'ldp x19, x8, [x24, #0x88]'),               # x19 / x8 reloaded: both free in the cave
             (0x14DE8C8, 'ldr x8, [x19], #8'), (0x14DE8CC, 'add x1, sp, #0x6f8'), (0x14DE8D0, 'mov x0, x24'),
             (0x14DE8D4, 'str x8, [sp, #0x6f8]'), (0x14DE8D8, 'bl #0x14dc040'),      # stock text (shipped: bl stub)
             (0x14DE944, 'str x10, [x24, #0x90]'),
             (SKIP, 'ldr x8, [x28]'), (0x14DE954, 'mov w19, #3')):
    stock(a, t)
assert sorted(targets_in(SITE, SITE + 4)) == [0x14DE818, 0x14DE87C], targets_in(SITE, SITE + 4)
assert targets_in(SITE + 4, SITE + 8) == []
assert not any(x in C.SHIPPED for x in range(SITE, SITE + 4))
assert all(x in C.SHIPPED for x in range(0x14DE8D8, 0x14DE8DC))        # DUSK_TYPE7_CALL2 (bl stub)
assert all(x in C.SHIPPED for x in range(STUB, STUB + 4))               # DUSK_TYPE7_STUB
listing.append('0x14DE8B4 is reached only from the two "receive loop empty" branches 0x14DE818 / 0x14DE87C, '
               'each right after the blr x8 of the receive call: x0..x17 hold nothing the code below reads '
               '(0x14DE8B8 reloads x19/x8; 0x14DE948 is also entered after the drain calls)')

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
listing.append('trampoline padding 0x%X..0x%X after `%s` (zero, before a pacibsp, unreferenced, free)' % (
    PAD, PAD + 12, dis(PAD - 4)))

g = C.Gen('needdata_gen', out=OUT, dry=True)
for tag, lo, hi, why in TAKERACE_ROWS:
    g._dry_rows.append(dict(owner='takerace_gen', tag=tag, lo=lo, hi=hi, purpose=why))
SIZE = 24
BOX = g.alloc('NDBOX', 'FAR_DATA', 16, 'NEEDDATA {u32 valid, u32 answered, u64 requester id}')
T = g.alloc('NEEDDATA', 'FAR_CODE', SIZE * 4, 'NEEDDATA 0x14DE8B4: answer a side-channel type-7 request')
for tag, lo, hi, _ in TAKERACE_ROWS:
    assert BOX + 16 <= lo or BOX >= hi
    assert T + SIZE * 4 <= lo or T >= hi

# NEEDDATA: entered by `b` (via the trampoline, x16) from 0x14DE8B4. x9/x10/x0/x1/x16/x30 are free (see listing;
# x30 is saved by the pump's prologue, which makes calls). sp is the pump's frame; [sp+0x6F8] is the stock id slot.
a = C.Asm(T)
a(C.to(C.cbz_w, 'w19', 'skip'))                            # cannot answer: stock path (box waits)
a(lambda pc, L: C.adrp(pc, 9, BOX))
a(C.add_xi(9, 9, C.lo12(BOX)))
a(C.ldr_w(10, 9, 0))
a(C.to(C.cbz_w, 'w10', 'back'))                            # box empty: stock drain
a(C.ldr_x(10, 9, 8))
a(C.str_x(10, 'sp', SLOT))                                 # id -> the stock slot
a(C.ldr_w(10, 9, 4))
a(C.add_wi(10, 10, 1))
a(C.str_w(10, 9, 4))                                       # answered += 1
a(C.str_w('wzr', 9, 0))                                    # valid = 0 (the assist may refill it now)
a(C.add_xi(1, 'sp', SLOT))
a(C.mov_x(0, 24))                                          # x0 = P
a.many(lambda pc, L: C.far_call(pc, STUB))                 # the stock answer path (stub v1 -> 0x14DC040)
a.label('back')
a.many(lambda pc, L: C.far_jump(pc, BACK))                 # stock drain of the queued ids
a.label('skip')
a.many(lambda pc, L: C.far_jump(pc, SKIP))
assert len(a.words()) <= SIZE, len(a.words())
cave = g.cave('NEEDDATA', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> NEEDDATA 0x%X (x16 dead at 0x14DE8B4)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'cbz w19, #0x14de948', C.b(SITE, PAD), 'NEEDDATA (side-channel type-7 answer)')]

groups = {'NEEDDATA_CAVE': cave + tramp, 'NEEDDATA': hook}
order = ['NEEDDATA_CAVE', 'NEEDDATA']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows (lead adds; TAKERACE rows assumed present):')
print('| needdata_gen | NDBOX | 0x%X..0x%X | NEEDDATA {u32 valid, u32 answered, u64 requester id} (FAR_DATA) |' % (
    BOX, BOX + 16))
print('| needdata_gen | NEEDDATA | 0x%X..0x%X | NEEDDATA 0x14DE8B4: answer a side-channel type-7 request through the '
      'stub; trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('The pump')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'NEEDDATA': 0x%X, 'NDBOX': 0x%X, 'TRAMP': 0x%X}\n" % (T, BOX, PAD))
