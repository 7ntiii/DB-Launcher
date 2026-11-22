"""levelshare2_gen.py: LEVELSHARE v2 - the cave also UPDATES a key that is already in the guest's map (hp_owner D).
DRY: no registry write, no *_live.py. Prints the changed cave words (replacing the shipped LEVELSHARE_CAVE words in
place, same range 0xC504704..0xC5047E4, same trampoline, same hook word) and the patch_manager.cpp rows.
    python diag/net/zt_faults/hp_owner/levelshare2_gen.py

Why [V code]: 0xEBD6A0 is an emplace. If the key is already in the map it returns the old node (x0 = node,
x1 = 0, 0xEBD7CC..0xEBD7DC) and does not touch its level; only a new node gets the value (0xEBD7F8 strh key +0x10,
0xEBD804 stur w {key, level} +0x12, so the level is at +0x14 = what the lookup reads, 0xEB8EEC ldrsh [x15, #0x14]).
So a key that the guest already has with another level (match 2 round 3: "3 with another level here") keeps the
guest's level. v2 stores the host's level into the returned node after each insert (2 words). Everything else is
the shipped cave word for word (asserted below against patch_manager.cpp)."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

T, SIZE = 0xC504704, 56          # registry row levelshare_gen / LEVELSHARE 0xC504704..0xC5047E4 (shipped)
BOX = 0xC50FFA8                  # LVBOX (shipped, dusk_lan.cpp LEVEL_BOX)
LOOKUP, INSERT = 0xEB8CA0, 0xEBD6A0
STAGE_G, P_ROUND, P_LEVEL = 0x5B3CDF8, 0xB8, 0x3378
LV_MAX = 18
SITE, HOOK_WORD = 0x1773E04, 0x97FE059B


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


for a, t in ((0xEBD7CC, 'mov x1, xzr'), (0xEBD7D0, 'b #0xebd9dc'), (0xEBD9DC, 'mov x0, x20'),
             (0xEBD7F8, 'strh w8, [x0, #0x10]'), (0xEBD7FC, 'ldr w8, [x21]'), (0xEBD804, 'stur w8, [x0, #0x12]'),
             (0xEB8EEC, 'ldrsh w9, [x15, #0x14]'), (0xEBD7EC, 'cbz x0, #0xebd9f8')):
    stock(a, t)
assert C.shipped_word(SITE) == HOOK_WORD, 'LEVELSHARE hook not shipped as expected'


def build(update):
    a = C.Asm(T)
    a(C.sub_xi('sp', 'sp', 0x60))
    a(C.stp_x(0, 1, 'sp', 0))
    a(C.stp_x(2, 3, 'sp', 0x10))
    a(C.stp_x(4, 5, 'sp', 0x20))
    a(C.stp_x(29, 30, 'sp', 0x30))
    a(C.stp_x(19, 20, 'sp', 0x40))
    a(C.stp_x(21, 22, 'sp', 0x50))
    a(lambda pc, L: C.adrp(pc, 19, BOX))
    a(C.add_xi(19, 19, C.lo12(BOX)))
    a(C.ldr_w(9, 19, 0))
    a(C.to(C.cbz_w, 'w9', 'done'))
    a(lambda pc, L: C.adrp(pc, 10, STAGE_G))
    a(C.ldr_x(10, 10, C.lo12(STAGE_G)))
    a(C.to(C.cbz_x, 'x10', 'done'))
    a(C.ldr_w(11, 10, P_ROUND))
    a(C.add_wi(11, 11, 1))
    a(C.cmp_wr(9, 11))
    a(C.to(C.bcond, 'ne', 'done'))
    a(C.ldr_w(12, 19, 4))
    a(C.cmp_wr(12, 11))
    a(C.to(C.bcond, 'eq', 'done'))
    a(C.ldr_w(20, 19, 8))
    a(C.to(C.cbz_w, 'w20', 'done'))
    a(C.cmp_wi(20, LV_MAX))
    a(C.to(C.bcond, 'hi', 'done'))
    a(C.ldr_x(21, 10, P_LEVEL))
    a(C.to(C.cbz_x, 'x21', 'done'))
    a(C.add_xi(21, 21, 0x38))
    a(C.str_w(11, 19, 4))
    a(C.ldr_w(12, 19, 12))
    a(C.add_wi(12, 12, 1))
    a(C.str_w(12, 19, 12))
    a(C.add_xi(22, 19, 16))
    a.label('loop')
    a(C.mov_x(0, 21))
    a(C.mov_x(1, 22))
    a(C.mov_x(2, 22))
    a(C.mov_x(3, 22))
    a.many(lambda pc, L: C.far_call(pc, INSERT))
    if update:
        a(C.ldrh(9, 22, 2))                    # the host's level {u16 key, s16 level}
        a(C.strh(9, 0, 0x14))                  # into the node 0xEBD6A0 returned (new or OLD)
    a(C.add_xi(22, 22, 4))
    a(C.sub_wi(20, 20, 1))
    a(C.to(C.cbnz_w, 'w20', 'loop'))
    a.label('done')
    a(C.ldp_x(0, 1, 'sp', 0))
    a(C.ldp_x(2, 3, 'sp', 0x10))
    a(C.ldp_x(4, 5, 'sp', 0x20))
    a(C.ldp_x(29, 30, 'sp', 0x30))
    a(C.ldp_x(19, 20, 'sp', 0x40))
    a(C.ldp_x(21, 22, 'sp', 0x50))
    a(C.add_xi('sp', 'sp', 0x60))
    a.many(lambda pc, L: C.far_jump(pc, LOOKUP))
    return a.words()


old = build(False)
for i, w in enumerate(old):
    assert C.shipped_word(T + 4 * i) == w, 'shipped LEVELSHARE differs at %x: rebuild does not match' % (T + 4 * i)
new = build(True)
assert len(new) <= SIZE and 0 not in new, len(new)
for i in range(len(new), SIZE):
    a = T + 4 * i
    assert not any(a + k in C.SHIPPED for k in range(4)), 'word %x is shipped by someone else' % a
others = C.live_records()
for i in range(len(old), len(new)):
    a = T + 4 * i
    assert not any(a + k in others for k in range(4)), 'word %x in %s' % (a, others.get(a))

print('old %d words, new %d words (row holds %d)' % (len(old), len(new), SIZE))
recs = []
for i, w in enumerate(new):
    a = T + 4 * i
    was = old[i] if i < len(old) else None
    mark = '' if was == w else ('   <- was %s' % C.dis1(a, was) if was is not None else '   <- new word')
    print('  0x%X %s%s' % (a, C.dis1(a, w), mark))
    if was != w:
        recs.append((a, '00000000', C.hexw(w), True))
print('changed / new records: %d (FAR form, replace the shipped DUSK_W_<addr> arrays in place):' % len(recs))
decl, rows = C.cpp_rows('LEVELSHARE_CAVE', recs)
print(decl)
print(rows)
print('registry: no new row (same range 0xC504704..0xC5047E4). Update the purpose text to mention "updates '
      'existing keys (v2)".')
