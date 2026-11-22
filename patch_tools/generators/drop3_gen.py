"""drop3_gen.py: a fully taken per-player world item (owner-only enemy drop) is removed on EVERY game (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes drop3_live.py.
python drop3_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: drop3_notes.md.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in drop3_notes.md; the lead adds the row when baking:
  drop3_gen | DROP3 | <printed range> | removal 0x15A55C0: fully taken per-player item -> subtype 2 to every member

Groups
  DROP3_CAVE  far cave DROP3 + a 3-word trampoline in the zero padding 0x15A57CC.. after the removal 0x15A55C0.
  DROP3       the two words of 0x15A55C0 that end the "every allowed slot is taken" test (0x15A5754 tbz bit 11,
     0x15A575C tbnz bit 3 of +0x289) -> the trampoline instead of the local remove 0x15A5780.
  Stock (authority only; callers 0x15A48C0 = server take tail, 0x15B265C, 0x15B2C68, 0x15B3AFC, 0x15B3E68): for the
  per-player kinds 1/2/4/5 the removal message subtype 2 {0x20001, id} goes to the REQUESTER member only (vt+0x38,
  0x15A569C), then the authority removes its own copy once every allowed bit (+0x290) is in the taken mask (+0x288).
  No other game hears of it: with 3+ players the third game keeps the taken owner-only drop. The cave sends the same
  8-byte message (still at [sp+8]) to every member (vt+0x40, as the shared-kind path 0x15A5764 does) when the member
  list holds at least MIN_MEMBERS entries, then continues at the stock local remove 0x15A5780. Removing an id that is
  already gone is a no-op (0x159E034 -> 0x15A2320 null -> return), so the requester's second copy and the
  authority's own self-link copy do nothing. Not fully taken (kind 1, every player once): unchanged."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'drop3_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
FUNC = 0x15A55C0          # removal (authority side)
FEND = 0x15A57E0          # next function
SITE1 = 0x15A5754         # tbz w8, #0xb, #0x15a5780   (allowed bit 11 clear: all checked bits taken)
SITE2 = 0x15A575C         # tbnz w8, #3, #0x15a5780    (bit 11 allowed and taken)
LOCAL = 0x15A5780         # mov x0, x19  (local remove 0x159E034(mgr, w20 = id, 1))
PAD = 0x15A57CC           # zero padding after the assert's udf at 0x15A57C8 (bl 0x472ca08 returns to 0x15A57C8)
MGR3 = 0x5B3CE08          # *(main+0x5B3CE08): session manager (members +0x1248..+0x1250, 0xF8 each, sender +0x10)
ELEM = 0xF8
MIN_MEMBERS = 3           # 2 = also cover a 2-player host-owned drop; 3 = 2-player games exactly as today
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


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
for a, t in (
        (0x15A55D4, 'adrp x9, #0x5b3c000'), (0x15A55D8, 'add x9, x9, #0xe08'), (0x15A55DC, 'ldr x10, [x9]'),
        (0x15A55E0, 'cbz x10, #0x15a57a0'),                         # mgr3 null -> assert (never reaches the sites)
        (0x15A55E8, 'mov x20, x2'), (0x15A55EC, 'mov x19, x0'),
        (0x15A55FC, 'ldr x9, [x10, #0x1250]'), (0x15A5604, 'ldr x1, [x10, #0x1248]'),
        (0x15A5618, 'cmp w11, #1'), (0x15A561C, 'b.lt #0x15a567c'),   # no members: local remove only (not the sites)
        (0x15A5620, 'add x0, x10, #0x10'), (0x15A5624, 'ldr w10, [x20]'),
        (0x15A5628, 'mov w11, #1'), (0x15A562C, 'movk w11, #2, lsl #16'),
        (0x15A5630, 'stp w11, w10, [sp, #8]'),                       # message {0x20001, id} at [sp+8]
        (0x15A5634, 'ldrb w11, [x20, #0x12c]'), (0x15A5648, 'mov w12, #0x36'),   # kinds 1/2/4/5 per player
        (0x15A569C, 'ldr x8, [x0]'), (0x15A56AC, 'ldr x8, [x8, #0x38]'),         # requester only
        (0x15A56B8, 'mov w20, w10'),                                 # w20 = id from here on
        (0x15A56C4, 'bl #0x15a2320'), (0x15A56CC, 'ldr x8, [x0, #0x290]'),
        (SITE1, 'tbz w8, #0xb, #0x15a5780'), (0x15A5758, 'ldrb w8, [x0, #0x289]'),
        (SITE2, 'tbnz w8, #3, #0x15a5780'), (0x15A5760, 'b #0x15a5790'),
        (0x15A5764, 'ldr x8, [x0]'), (0x15A5768, 'add x2, sp, #8'), (0x15A576C, 'mov w1, #0x1e'),
        (0x15A5770, 'mov w3, #8'), (0x15A5774, 'ldr x8, [x8, #0x40]'),           # shared kinds: broadcast
        (0x15A577C, 'ldr w20, [x20]'),
        (LOCAL, 'mov x0, x19'), (0x15A5784, 'mov x1, x20'), (0x15A5788, 'mov w2, #1'), (0x15A578C, 'bl #0x159e034'),
        (0x15A5798, 'add sp, sp, #0x30'), (0x15A579C, 'retab'),
        (0x15A57C4, 'bl #0x472ca08'),
        # the receiver: subtype 2 -> remove with no test; a missing id returns
        (0x1597878, 'ldr w1, [sp, #0x354]'), (0x1597884, 'bl #0x159e034'),
        (0x159E05C, 'bl #0x15a2320'), (0x159E060, 'cbz x0, #0x159e260')):
    stock(a, t)
assert W[FUNC // 4] == PACIBSP and W[FEND // 4] == PACIBSP
assert sorted(targets_in(LOCAL, LOCAL + 4)) == [SITE1, SITE2], [hex(x) for x in targets_in(LOCAL, LOCAL + 4)]
# a branch INTO a site is fine: the new word keeps the same test and only moves the "all taken" target
assert targets_in(SITE1, SITE1 + 4) == [0x15A5748] and not targets_in(SITE2, SITE2 + 4), 'branch into a site'
# x16 / x17 are never used in the function, so x16 is dead at LOCAL; x8..x12 are rewritten or dead there
for a in range(FUNC, FEND, 4):
    assert not re.search(r'\b[xw]1[67]\b', C.dis1(a, C.text_word(a))), hex(a)
# callers of the removal (every one is an authority-side server handler)
callers = [4 * i for i, w in enumerate(W) if (w & 0xFC000000) == 0x94000000 and
           4 * i + (((w & 0x3FFFFFF) - (1 << 26)) if w & (1 << 25) else (w & 0x3FFFFFF)) * 4 == FUNC]
assert callers == [0x15A48C0, 0x15B265C, 0x15B2C68, 0x15B3AFC, 0x15B3E68], [hex(x) for x in callers]
listing.append('callers of 0x15A55C0: ' + ' '.join('0x%X' % x for x in callers))

# trampoline padding: 3 zero words, before the next pacibsp, unreferenced, free
assert all(W[x // 4] == 0 for x in range(0x15A57C8, FEND, 4))
assert not targets_in(PAD, FEND) and not qwords_in(PAD, FEND), 'padding referenced'
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(PAD, PAD + 12)), 'padding in use'
assert C.reach(SITE1, PAD, 14) and C.reach(SITE2, PAD, 14)
listing.append('trampoline padding 0x%X..0x%X (zero, before pacibsp 0x%X, unreferenced, free)' % (PAD, PAD + 12, FEND))

g = C.Gen('drop3_gen', out=OUT, dry=True)      # dry: never writes cave_registry.md (task rule)
SIZE = 20
T = g.alloc('DROP3', 'FAR_CODE', SIZE * 4, 'removal 0x15A55C0: fully taken per-player item -> subtype 2 to every member')
listing.append('cave DROP3 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)'
               % (T, T + SIZE * 4))

a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 9, MGR3))
a(C.ldr_x(9, 9, C.lo12(MGR3)))                           # x9 = mgr3 (non-null: 0x15A55E0 asserted it)
a(C.to(C.cbz_x, 'x9', 'local'))
a(C.ldr_x(10, 9, 0x1248))                                # members begin
a(C.ldr_x(11, 9, 0x1250))                                # members end
a(C.add_xi(10, 10, MIN_MEMBERS * ELEM))
a(C.cmp_xr(11, 10))
a(C.to(C.blo, 'local'))                                  # fewer than MIN_MEMBERS: stock (requester-only)
a(C.add_xi(0, 9, 0x10))                                  # x0 = member manager (as 0x15A5620)
a(C.ldr_x(8, 0, 0))
a(C.ldr_x(8, 8, 0x40))                                   # vt+0x40 = send to every member (as 0x15A5774)
a(C.movz_w(1, 0x1E))                                     # message type 0x1E
a(C.add_xi(2, 31, 8))                                    # x2 = sp + 8: {0x20001, id} written at 0x15A5630
a(C.movz_w(3, 8))
a(C.blr(8))                                              # x19 (MapItemMan) and x20 (id) are callee-saved
a.label('local')
a.many(lambda pc, L: C.far_return(pc, LOCAL))
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
for t in dis:
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (0, 1, 2, 3, 8, 9, 10, 11, 16), t     # all dead or rewritten at LOCAL; never x19 / x20
for need in ('add x2, sp, #8', 'ldr x8, [x8, #0x40]', 'add x0, x9, #0x10', 'mov w1, #0x1e', 'mov w3, #8',
             'ldr x10, [x9, #0x1248]', 'ldr x11, [x9, #0x1250]', 'ldr x9, [x9, #0xe08]'):
    assert need in dis, need
assert 'add x10, x10, #0x%x' % (MIN_MEMBERS * ELEM) in dis

caves = g.cave('DROP3', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> DROP3 0x%X (x16 unused in 0x15A55C0)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE1, 'tbz w8, #0xb, #0x15a5780', C.tbz(SITE1, 'w8', 11, PAD), 'all taken (bit 11 not allowed) -> DROP3'),
        g.text_patch(SITE2, 'tbnz w8, #3, #0x15a5780', C.tbnz(SITE2, 'w8', 3, PAD), 'all taken (bit 11 taken) -> DROP3')]
groups = {'DROP3_CAVE': caves + tramp, 'DROP3': hook}
order = ['DROP3_CAVE', 'DROP3']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'DROP3': 0x%X, 'TRAMP': 0x%X}\nMIN_MEMBERS = %d\n" % (T, PAD, MIN_MEMBERS))
