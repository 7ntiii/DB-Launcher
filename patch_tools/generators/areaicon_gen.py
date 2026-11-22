"""areaicon_gen.py: guests get the host's area-icon list MS+0x538 (icons4_notes.md). Static generator: reads
nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes areaicon_live.py.
python areaicon_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows (proposal).

Why [V]:
- The HUD's area-name icon lookup 0x1481160 (callers 0x12E95D4 / 0x12E9A90 in the HUD build 0x12E32E0, and
  0x13CEE84) reads [[par+0x2D8]+0x538 .. +0x540]: 8-byte entries {u32 area id, u32 kind}, kind 0..9 -> icon
  0xBB95..0xBBBD. Match 3 round 2: host 72 bytes (9 entries), guest none.
- Its only writers: the constructor (zero), the teardown 0x11103E0 (frees begin through [MS+0x550] vt+0x70), the
  host-only simulation body, and 0x1111260, the 0x6A reader's section (0x1110820 -> 0x11109DC): end = begin,
  reserve 0x1122FC0(&MS+0x538, n), then one entry per record. Guests never get 0x6A, so their list stays empty.
- The list must be the game's own allocation (the teardown frees it): a buffer of ours would be freed by the
  game's allocator. So the cave refills it with the game's own reserve, as 0x1111260 does.

Groups
  AREA_ICON_CAVE  far cave ICON + text-padding trampoline + mailbox ICONBOX (FAR_DATA: u32 valid, u32 count,
                  56 x u64 entries; the assist writes count + entries, then valid = 1; the cave clears valid).
  AREA_ICON_HOOK  0x1110858 `ldr w8, [x0, #0x1268]` (the 0x6A reader, every stage update, x19 = MS, x0 = the
                  session object) -> b trampoline. The cave: mailbox valid and the list's allocator [MS+0x550] set
                  and count <= 56 -> end = begin, 0x1122FC0(&MS+0x538, count), copy the entries, end = begin + 8n;
                  valid = 0; then the replaced ldr and back to 0x111085C.
Inert: the mailbox is written only by the assist, on a guest, with the host's list (type 22). Offline nothing writes
it; the hook then costs one load and one branch."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'areaicon_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
SITE = 0x1110858            # ldr w8, [x0, #0x1268]
BACK = 0x111085C
RESERVE = 0x1122FC0         # vector<u64> reserve(vec, n), game allocator [vec+0x18]
FUNC = 0x1110820
FUNC_END = 0x1110A88        # retab
MAX = 56
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


for a, t in ((FUNC, 'pacibsp'), (0x1110848, 'mov x19, x0'), (0x1110850, 'ldr x0, [x23]'),
             (0x1110854, 'cbz x0, #0x1110a8c'), (SITE, 'ldr w8, [x0, #0x1268]'), (BACK, 'cmp w8, #6'),
             (0x11109D8, 'mov x0, x19'), (0x11109DC, 'bl #0x1111260'), (FUNC_END, 'retab'),
             # 0x1111260 = the stock refill this cave copies
             (0x1111284, 'ldr x8, [x0, #0x538]'), (0x1111290, 'ldr x9, [x0, #0x540]'), (0x11112A0, 'str x8, [x20, #0x540]'),
             (0x11112AC, 'add x22, x20, #0x538'), (0x11112B8, 'bl #0x1122fc0'),
             (0x1111544, 'str x9, [x8], #8'), (0x1111548, 'str x8, [x20, #0x540]'),
             # reserve: cap check, allocator [vec+0x18] vt+0x58, copies the old entries, frees the old block vt+0x70
             (RESERVE, 'pacibsp'), (0x1122FD4, 'ldr x8, [x0, #0x10]'), (0x1123000, 'ldr x0, [x0, #0x18]'),
             (0x112300C, 'ldr x8, [x8, #0x58]'), (0x1123054, 'stp x10, x8, [x19]'), (0x1123058, 'str x9, [x19, #0x10]'),
             # the teardown frees [MS+0x538] with [MS+0x550] vt+0x70 (so the block must be the game's)
             (0x1110668, 'ldr x1, [x19, #0x538]'), (0x1110670, 'ldr x0, [x19, #0x550]'),
             # the HUD reader
             (0x1481180, 'ldr x9, [x8, #0x2d8]'), (0x1481184, 'ldr x8, [x9, #0x538]'), (0x1481188, 'ldr x9, [x9, #0x540]'),
             (0x12E95D4, 'bl #0x1481160'), (0x12E9A90, 'bl #0x1481160')):
    stock(a, t)
listing.append('[V] 0x1110820(x0 = MS: 0x1140A0C / 0x11432E8 load [par+0x2D8]); x19 = MS from 0x1110848')
listing.append('[V] 0x1111260 refills MS+0x538 as: end = begin, reserve 0x1122FC0, append; the cave does the same')


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


# the site is reached only by falling through from 0x1110854 (no branch to 0x1110858)
assert targets_in(SITE, SITE + 4) == [], 'branch into the site'
listing.append('[V] no branch targets 0x1110858 (reached only from 0x1110854)')
# caller-saved x1..x18 are dead at the site: from 0x111085C to the end of the function each is first named as the
# destination of a write (the cave calls reserve, which may clobber all of them); x0 is saved and restored.
DEST_ONLY = ('mov', 'add', 'sub', 'adrp', 'ldr', 'ldrb', 'ldrh', 'ldrsb', 'ldrsh', 'ldur', 'ldurb', 'movk', 'movz',
             'ubfx', 'orr', 'and', 'lsr', 'lsl', 'cset', 'csel', 'sxtw', 'asr')
for r_ in [r for r in range(1, 19) if r != 8]:   # x8 = the replaced ldr's own result (re-run last)
    pat = re.compile(r'\b[xw]%d\b' % r_)
    for pc in range(BACK, FUNC_END, 4):
        t = C.dis1(pc, W[pc // 4])
        if t.startswith('bl ') or t.startswith('blr '):
            break                                   # a call clobbers them anyway
        if not pat.search(t):
            continue
        mn, ops = (t.split(' ', 1) + [''])[:2]
        ops = ops.split(', ')
        assert mn in DEST_ONLY and pat.fullmatch(ops[0]) and not any(pat.search(o) for o in ops[1:]), \
            'x%d read at %x before written: %s' % (r_, pc, t)
        break
listing.append('[V] x1..x18 dead at 0x1110858 (first named as a write, or a call comes first, on the straight path)')
# straight path is enough: every branch from 0x111085C..0x11108BC (b.ne 0x1110a6c = epilogue, b 0x11108bc) leads to
# code that writes before reading (0x11108BC: ldr x20 / ldr w8 / ldr x8 ... ; 0x1110A6C: epilogue loads only)
for pc in range(0x1110A6C, FUNC_END + 4, 4):
    assert C.dis1(pc, W[pc // 4]).split(' ')[0] in ('ldp', 'add', 'retab'), hex(pc)
listing.append('[V] epilogue 0x1110A6C..: ldp / add sp / retab only')

for x in (SITE,):
    assert not any(x + i in C.SHIPPED for i in range(4)), 'shipped word at %x' % x
others = C.live_records(exclude=(OUT,))
assert not any(SITE + i in others for i in range(4)), '%x taken: %s' % (SITE, others.get(SITE))

g = C.Gen('areaicon_gen', out=OUT, dry=True)
g.others = others
SIZE = 48
T = g.alloc('ICON', 'FAR_CODE', SIZE * 4, 'AREA_ICON: guest refills MS+0x538 (area icons) from ICONBOX '
            'with the game\'s reserve 0x1122FC0')
BOX = g.alloc('ICONBOX', 'FAR_DATA', 8 + 8 * MAX, 'AREA_ICON mailbox {u32 valid, u32 count, 56 x u64 '
              '{id, kind}} (assist writes, cave clears valid)', align=8)

a = C.Asm(T)
a(C.stp_pre(0, 30, 'sp', -0x20))
a(C.stp_x(21, 22, 'sp', 0x10))
a(lambda pc, L: C.adrp(pc, 21, BOX))
a(C.add_xi(21, 21, C.lo12(BOX)))
a(C.ldr_w(8, 21, 0))                            # valid
a(C.to(C.cbz_w, 'w8', 'out'))
a(C.ldr_x(8, 19, 0x550))                        # the list's allocator (the teardown and reserve use it)
a(C.to(C.cbz_x, 'x8', 'clear'))
a(C.ldr_w(22, 21, 4))                           # count
a(C.cmp_wi(22, MAX))
a(lambda pc, L: C.bcond(pc, 'hi', L['clear']))
a(C.ldr_x(8, 19, 0x538))                        # end = begin (as 0x1111284..0x11112A0; nothing freed)
a(C.str_x(8, 19, 0x540))
a(C.to(C.cbz_w, 'w22', 'clear'))                # the host's list is empty: ours is now empty too
a(C.add_xi(0, 19, 0x538))
a(C.mov_w(1, 22))
a.many(lambda pc, L: C.far_call(pc, RESERVE))   # capacity >= count, game allocation
a(C.ldr_x(10, 19, 0x538))                       # begin (new block if it grew)
a(C.to(C.cbz_x, 'x10', 'clear'))
a(C.add_xi(9, 21, 8))
a(C.mov_w(11, 22))
a.label('copy')
a(C.ldr_x(12, 9, 0))
a(C.str_x(12, 10, 0))
a(C.add_xi(9, 9, 8))
a(C.add_xi(10, 10, 8))
a(C.sub_wi(11, 11, 1))
a(C.to(C.cbnz_w, 'w11', 'copy'))
a(C.str_x(10, 19, 0x540))                       # end = begin + 8 * count
a.label('clear')
a(C.str_w('wzr', 21, 0))                        # taken
a.label('out')
a(C.ldp_x(21, 22, 'sp', 0x10))
a(C.ldp_post(0, 30, 'sp', 0x20))
a(C.ldr_w(8, 0, 0x1268))                        # the replaced word
a.many(lambda pc, L: C.far_return(pc, BACK))
cave = a
assert len(cave.words()) <= SIZE, len(cave.words())
listing.append('ICON: %d of %d words; ICONBOX 0x%X..0x%X' % (len(cave.words()), SIZE, BOX, BOX + 8 + 8 * MAX))
assert C.text_word(SITE) == C.relocate(SITE, T)[0], 'the replaced word is position independent'
recs = g.cave('ICON', T, cave)
PACIBSP = 0xD503237F


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


def find_pad(near, n):
    """n zero words in text padding (before a pacibsp, unreferenced, free) in b reach of `near`
    (NEAR_TRAMP is full; as finalout_gen)"""
    for a_ in range(near - 0x80000, near + 0x80000, 4):
        if all(W[a_ // 4 + k] == 0 for k in range(n)) and W[a_ // 4 - 1] != 0:
            z = a_
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a_, a_ + 4 * n)):
                continue
            if targets_in(a_, z) or qwords_in(a_, z):
                continue
            if C.reach(near, a_):
                return a_
    return None


PAD = find_pad(SITE, 3)
assert PAD, 'no text padding near the site'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free; NEAR_TRAMP is full)'
               % (PAD, PAD + 12))
listing.append('scratch x16 at 0x%X: dead (x1..x18 checked above; the next call 0x11108A0/0x11108E4 clobbers it)' % SITE)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w_, 'trampoline -> 0x%X (x16 dead at the site)' % T)
         for k, w_ in enumerate(C.far_jump(PAD, T))]
site_rec = [g.text_patch(SITE, 'ldr w8, [x0, #0x1268]', C.b(SITE, PAD), 'AREA_ICON_HOOK (0x6A reader, every update)')]
groups = {'AREA_ICON_CAVE': recs + tramp, 'AREA_ICON_HOOK': site_rec}
order = ['AREA_ICON_CAVE', 'AREA_ICON_HOOK']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead (proposal):')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'ICON': 0x%X}\nBOX = 0x%X\nSITE = 0x%X\nPAD = 0x%X\nHOOK_WORD = 0x%08X\n" % (
            T, BOX, SITE, PAD, struct.unpack('<I', bytes.fromhex(site_rec[0][2]))[0]))
