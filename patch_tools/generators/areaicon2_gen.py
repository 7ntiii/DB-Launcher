"""areaicon2_gen.py: v3.9.16 candidate fix for the match 5 guest final crash (b_final_crash_notes.md).
Static generator: reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes areaicon2_live.py,
which supersedes areaicon_live.py (new cave ICON2, the same hook, the trampoline re-pointed, plus one new guard).
python areaicon2_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: Gen(dry=True); cave_registry.md is NOT written. ICON / ICONBOX are the existing areaicon_gen rows; the
new rows (LISTBUF, ICONFREE) are printed as a proposal for the lead.

What changes against v3.9.15 (areaicon_live.py):
- v3.9.15 filled the guest's MS+0x538 list with the GAME's allocator (reserve 0x1122FC0, [MS+0x550] vt+0x58).
  On a stock guest that list is never allocated (begin = 0): only the host-only body and the 0x6A reader own it.
  Both v3.9.15 guests crashed 3 s into the final in the stock load-process scheduler with a freed
  CSLoadProcessData_Geomhkxbnd still queued (b_final_crash_notes.md). The game-heap block we created is the one
  guest-side heap change that v3.9.14 did not make.
- v3.9.16: the guest's list never touches the game heap. A new cave ICON2 (the trampoline 0x1090AC8 is
  re-pointed; the baked v3.9.15 ICON body stays in place, unreachable) points MS+0x538 begin / end / capacity at a
  mod buffer LISTBUF (FAR_DATA, 56 entries) and copies the entries there; a list that is the game's own
  (begin != 0 and != LISTBUF) is never touched.
- AREA_ICON_FREE: the MapSystem teardown 0x11103E0 frees begin at 0x1110668..0x1110680. When begin == LISTBUF the
  guard zeroes begin / end / capacity and the teardown skips the free (cbz x1), so the game never frees our buffer.
  The other frees of MS+0x538 (reserve 0x1122FC0 when it grows, the body's 0x112317C / 0x1123368) run only in the
  host-only body and the 0x6A reader, which guests never run; the host's begin is never LISTBUF.

Groups
  AREA_ICON_CAVE  far cave ICON2 (new) + the v3.9.15 trampoline re-pointed to it + mailbox ICONBOX +
                  LISTBUF. The assist writes count + entries, then valid = 1; the cave copies into LISTBUF and
                  clears valid. count 0 = empty the list (the assist sends that at a round change).
                  valid = 2 = detach: a guest that became host (v3.5 hand-over) runs the body, which may grow or
                  free the list with the game allocator, so begin / end / capacity go back to 0 first.
  AREA_ICON_HOOK  0x1110858 `ldr w8, [x0, #0x1268]` -> b trampoline (unchanged from v3.9.15).
  AREA_ICON_FREE  0x1110668 `ldr x1, [x19, #0x538]` -> b trampoline2 -> far ICONFREE (teardown guard).
Inert offline: nothing writes the mailbox, LISTBUF is never pointed at, the guard compares and goes on."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'areaicon2_live.py'
OLD = 'areaicon_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
SITE = 0x1110858            # ldr w8, [x0, #0x1268]  (0x6A reader 0x1110820, x19 = MS)
BACK = 0x111085C
FUNC_END = 0x1110A88
FSITE = 0x1110668           # ldr x1, [x19, #0x538]  (teardown 0x11103E0, x19 = MS)
FBACK = 0x111066C           # cbz x1, #0x1110684
MAX = 56
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


for a, t in ((0x1110820, 'pacibsp'), (0x1110848, 'mov x19, x0'), (0x1110854, 'cbz x0, #0x1110a8c'),
             (SITE, 'ldr w8, [x0, #0x1268]'), (BACK, 'cmp w8, #6'), (FUNC_END, 'retab'),
             # teardown 0x11103E0: x19 = MS from 0x11103F8; the list free
             (0x11103E0, 'pacibsp'), (0x11103F8, 'mov x19, x0'),
             (0x1110650, 'cbz x1, #0x1110668'), (FSITE, 'ldr x1, [x19, #0x538]'), (FBACK, 'cbz x1, #0x1110684'),
             (0x1110670, 'ldr x0, [x19, #0x550]'), (0x1110674, 'str x1, [x19, #0x540]'),
             (0x1110678, 'ldr x8, [x0]'), (0x111067C, 'ldr x8, [x8, #0x70]'), (0x1110680, 'blr x8'),
             (0x1110684, 'add x0, x19, #0x4a0'), (0x1110688, 'bl #0x1129940'),
             # the HUD reader walks begin..end only (no capacity use)
             (0x1481184, 'ldr x8, [x9, #0x538]'), (0x1481188, 'ldr x9, [x9, #0x540]')):
    stock(a, t)
listing.append('[V] x19 = MS at 0x1110858 (0x1110848) and at 0x1110668 (0x11103F8, callee-saved, not written '
               'between)')

# x19 not written in the teardown between 0x11103F8 and the guard site
for pc in range(0x11103FC, FSITE, 4):
    t = C.dis1(pc, W[pc // 4])
    mn, ops = (t.split(' ', 1) + [''])[:2]
    assert not (ops.startswith('x19,') or ops.startswith('w19,')) or mn.startswith('st') or mn == 'cmp', \
        'x19 written at %x: %s' % (pc, t)
    assert not (mn in ('ldp',) and re.match(r'x\d+, x19,', ops)), 'x19 written at %x: %s' % (pc, t)

# guard site: flags and x16/x17 dead after it (straight path to the next call / flag write)
FLAG_SET = ('cmp', 'cmn', 'tst', 'adds', 'subs', 'ands', 'ccmp', 'fcmp')
FLAG_USE = ('b.', 'csel', 'cset', 'csinc', 'csinv', 'csneg', 'cinc', 'ccmp', 'adc', 'sbc')
for pc in range(FBACK, FBACK + 0x400, 4):
    t = C.dis1(pc, W[pc // 4])
    mn = t.split(' ')[0]
    assert not re.search(r'\b[xw]1[67]\b', t), 'x16/x17 read at %x: %s' % (pc, t)
    if any(mn.startswith(u) for u in FLAG_USE) and not mn.startswith('cbz'):
        raise AssertionError('flags read at %x before set: %s' % (pc, t))
    if mn in FLAG_SET or mn.startswith('bl') or mn == 'blr':
        break
# the branch path cbz x1 -> 0x1110684: add / bl (call clobbers x16, x17; callee sets its own flags)
listing.append('[V] after 0x1110668: x16 / x17 and the flags are written (or a call comes) before any read, on '
               'both paths (fall-through to blr 0x1110680, cbz -> 0x1110684 add / bl)')

others = C.live_records(exclude=(OUT, OLD))
assert not any(FSITE + i in C.SHIPPED for i in range(4)), 'shipped word at %x' % FSITE
for x in (SITE, FSITE):
    assert not any(x + i in others for i in range(4)), '%x taken: %s' % (x, others.get(x))

old = {}
exec(open(os.path.join(HERE, OLD)).read(), old)
ICON, BOX, PAD = old['CAVES']['ICON'], old['BOX'], old['PAD']
# v3.9.15 baked areaicon_live.py: every one of its words must be the shipped word now (we replace them in place)
OLD_RECS = {r[0]: r for grp in ('AREA_ICON_CAVE', 'AREA_ICON_HOOK') for r in old[grp]}
for addr, o, n_, code in OLD_RECS.values():
    assert C.shipped_word(addr) == int.from_bytes(bytes.fromhex(n_), 'little'), 'not the baked word at %x' % addr
listing.append('[V] the %d areaicon_live.py records are the shipped (v3.9.15) words' % len(OLD_RECS))


def replace_rec(addr, new, note):
    """a shipped v3.9.15 area-icon word: orig stays its stock bytes, new = the v3.9.16 word"""
    assert addr in OLD_RECS, 'not an areaicon_live word: %x' % addr
    o = OLD_RECS[addr][1]
    listing.append('  0x%x  %s  ->  %s   %s' % (addr, C.dis1(addr, C.shipped_word(addr)), C.dis1(addr, new), note))
    return (addr, o, C.hexw(new), True)

g = C.Gen('areaicon_gen', out=OUT, dry=True)
g.others = others
assert g.alloc('ICON', 'FAR_CODE', 48 * 4, 'x') == ICON
# a NEW cave address (bake_check P3 refuses rewriting baked far words); the v3.9.15 ICON body stays, unreachable
ICON2 = g.alloc('ICON2', 'FAR_CODE', 48 * 4, 'AREA_ICON v3.9.16: guest list in LISTBUF from ICONBOX (no game heap); '
                'the trampoline 0x1090AC8 points here, the old ICON body is unreachable (v3.9.16)')
assert g.alloc('ICONBOX', 'FAR_DATA', 8 + 8 * MAX, 'x', align=8) == BOX
LIST = g.alloc('LISTBUF', 'FAR_DATA', 8 * MAX, 'AREA_ICON guest list storage (MS+0x538 begin/end/cap point here '
               'on a guest; never the game heap; the teardown guard keeps the game from freeing it) (v3.9.16)',
               align=8)
FREE = g.alloc('ICONFREE', 'FAR_CODE', 16 * 4, 'AREA_ICON_FREE: MapSystem teardown guard at 0x1110668 '
               '(begin == LISTBUF -> zero the list, skip the free) (v3.9.16)')

# ------------------------------------------------------------ ICON (new body, same address)
a = C.Asm(ICON2)
a(C.stp_pre(21, 22, 'sp', -0x10))
a(lambda pc, L: C.adrp(pc, 21, BOX))
a(C.add_xi(21, 21, C.lo12(BOX)))
a(C.ldr_w(8, 21, 0))                            # valid: 1 = take the entries, 2 = detach (this game became host)
a(C.to(C.cbz_w, 'w8', 'out'))
a(lambda pc, L: C.adrp(pc, 10, LIST))
a(C.add_xi(10, 10, C.lo12(LIST)))
a(C.cmp_wi(8, 2))
a(lambda pc, L: C.bcond(pc, 'eq', L['detach']))
a(C.ldr_w(22, 21, 4))                           # count
a(C.cmp_wi(22, MAX))
a(lambda pc, L: C.bcond(pc, 'hi', L['clear']))
a(C.ldr_x(8, 19, 0x538))                        # begin
a(C.to(C.cbz_x, 'x8', 'take'))                  # never allocated (a stock guest): take it
a(C.cmp_xr(8, 10))
a(lambda pc, L: C.bcond(pc, 'ne', L['clear']))  # the game's own list: never touched
a.label('take')
a(C.add_xi(13, 19, 0x538))
a(C.stp_x(10, 10, 13, 0))                       # begin = end = LISTBUF in one pair store (empty while filled)
a(C.add_xi(11, 10, 8 * MAX))
a(C.str_x(11, 19, 0x548))                       # capacity = LISTBUF + 56 entries
a(C.to(C.cbz_w, 'w22', 'clear'))                # count 0: the list stays empty
a(C.add_xi(9, 21, 8))
a(C.mov_w(11, 22))
a.label('copy')
a(C.ldr_x(12, 9, 0))
a(C.str_x(12, 10, 0))
a(C.add_xi(9, 9, 8))
a(C.add_xi(10, 10, 8))
a(C.sub_wi(11, 11, 1))
a(C.to(C.cbnz_w, 'w11', 'copy'))
a(C.str_x(10, 19, 0x540))                       # end = LISTBUF + 8 * count
a(lambda pc, L: C.b(pc, L['clear']))            # skip the detach part
a.label('detach')                               # a new host's body owns the list: hand it back empty (begin 0)
a(C.ldr_x(8, 19, 0x538))
a(C.cmp_xr(8, 10))
a(lambda pc, L: C.bcond(pc, 'ne', L['clear']))  # not LISTBUF: the game's own, never touched
a(C.add_xi(13, 19, 0x538))
a(C.stp_x('xzr', 'xzr', 13, 0))
a(C.str_x('xzr', 19, 0x548))
a.label('clear')
a(C.str_w('wzr', 21, 0))                        # taken
a.label('out')
a(C.ldp_post(21, 22, 'sp', 0x10))
a(C.ldr_w(8, 0, 0x1268))                        # the replaced word (x0 untouched)
a.many(lambda pc, L: C.far_return(pc, BACK))
assert len(a.words()) <= 48, len(a.words())
listing.append('ICON2: %d words; no call, uses x8..x13 (dead, areaicon_gen.py check) and x21 / x22 (saved)'
               % len(a.words()))
assert C.text_word(SITE) == C.relocate(SITE, ICON2)[0]
icon_recs = g.cave('ICON2', ICON2, a)

# ------------------------------------------------------------ ICONFREE
f = C.Asm(FREE)
f(C.ldr_x(1, 19, 0x538))                        # the replaced word
f(lambda pc, L: C.adrp(pc, 16, LIST))
f(C.add_xi(16, 16, C.lo12(LIST)))
f(C.cmp_xr(1, 16))
f(lambda pc, L: C.bcond(pc, 'ne', L['back']))
f(C.add_xi(17, 19, 0x538))
f(C.stp_x('xzr', 'xzr', 17, 0))                 # begin = end = 0 in one pair store
f(C.str_x('xzr', 19, 0x548))                    # capacity = 0
f(C.mov_x(1, 'xzr'))                            # the teardown's cbz x1 skips the free
f.label('back')
f.many(lambda pc, L: C.far_return(pc, FBACK))
assert len(f.words()) <= 16
assert C.text_word(FSITE) == C.relocate(FSITE, FREE)[0], 'the replaced word is position independent'
free_recs = g.cave('ICONFREE', FREE, f)
PACIBSP = 0xD503237F


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


def find_pad(near, n, avoid):
    """n zero words in text padding (before a pacibsp, unreferenced, free) in b reach of `near` (as finalout_gen)"""
    for a_ in range(near - 0x80000, near + 0x80000, 4):
        if all(W[a_ // 4 + k] == 0 for k in range(n)) and W[a_ // 4 - 1] != 0:
            z = a_
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others or avoid[0] <= x < avoid[1] for x in range(a_, a_ + 4 * n)):
                continue
            if targets_in(a_, z) or qwords_in(a_, z):
                continue
            if C.reach(near, a_):
                return a_
    return None


# the old trampoline (unchanged words, kept in this file so the group stays whole)
tramp = [replace_rec(PAD + 4 * k, w_, 'trampoline -> ICON2 0x%X (was ICON 0x%X)' % (ICON2, ICON))
         for k, w_ in enumerate(C.far_jump(PAD, ICON2))]
site_rec = [replace_rec(SITE, C.b(SITE, PAD), 'AREA_ICON_HOOK (unchanged)')]
PAD2 = find_pad(FSITE, 3, (PAD, PAD + 12))
assert PAD2, 'no text padding near the teardown site'
listing.append('trampoline2 padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD2, PAD2 + 12))
tramp2 = [g.text_patch(PAD2 + 4 * k, 'udf #0', w_, 'trampoline -> 0x%X (x16 dead at 0x%X)' % (FREE, FSITE))
          for k, w_ in enumerate(C.far_jump(PAD2, FREE))]
fsite_rec = [g.text_patch(FSITE, 'ldr x1, [x19, #0x538]', C.b(FSITE, PAD2),
                          'AREA_ICON_FREE (MapSystem teardown: never free LISTBUF)')]

groups = {'AREA_ICON_CAVE': icon_recs + tramp, 'AREA_ICON_HOOK': site_rec,
          'AREA_ICON_FREE': free_recs + tramp2 + fsite_rec}
order = ['AREA_ICON_CAVE', 'AREA_ICON_HOOK', 'AREA_ICON_FREE']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead (proposal):')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as fh:
        fh.write("CAVES = {'ICON': 0x%X, 'ICONFREE': 0x%X}\nBOX = 0x%X\nLISTBUF = 0x%X\nSITE = 0x%X\nPAD = 0x%X\n"
                 "FSITE = 0x%X\nPAD2 = 0x%X\n" % (ICON2, FREE, BOX, LIST, SITE, PAD, FSITE, PAD2))
