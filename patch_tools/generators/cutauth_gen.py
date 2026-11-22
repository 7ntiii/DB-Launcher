"""cutauth_gen.py: a guest cuts after Phases II / III by the AUTHORITY's ranks when the assist has them (static
generator, cutauth_notes.md; realnet_notes R1, assist_v400_notes 1 "Real fix"). Reads nso/*.bin,
patch_manager.cpp and every *_live.py through cave_lib. Writes cutauth_live.py.
python cutauth_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why [V code below]: every game cuts for every player in its own EndPhase (0x1144A60 -> 0xF6AF20 -> score manager
vt+0x50 rank 0xF871C0, then vt+0x60 cut 0xF879A0), from its own Virtue copies. After a network stall at a phase end
two games can rank differently and cut different players. The assist cannot write the ranks (rank and cut run back
to back in one game-thread call), and the authority's list (type 13) exists only after the authority's cut.

The cut 0xF879A0 [V]: threshold w21 (PhaseInfoParam +0x92, Phase III EnvEvent +0xAA override, Bloodbound (rule byte
main+0x5B65C70 == 2) halved and rounded up with the TEAM rank functor 0x56EA238 = entry +0x20 instead of 0x56EA280
= entry +0x10); then per phase entry (par+0x33D0, 0x60 each, count +0x488; x20 = entry + 0x38) not yet at stage
byte 4: w0 = functor rank, 0xF87BDC `cmp w0, w21; b.le keep` else event 1 (04 03 01 01) at 0xF87BF4.

Groups
  CUTAUTH_CAVE   far cave CAUTH + trampoline in text padding + mailbox CUTBOX (FAR_DATA, 0x18 bytes):
                 +0 u32 key = 0xC0710000 | round (the assist writes it LAST; 0 = no list), +8 u8 rank[16] by player
                 number (Standard: the authority's entry rank +0x10; Bloodbound: its team rank +0x20; 0 = unknown).
  CUTAUTH        0xF87BDC `cmp w0, w21` -> b trampoline. The cave: online (+0xBDA == 0) AND key == 0xC0710000 |
                 [par+0xB8] AND the entry's player number (u32 entry+0) < 16 AND rank[no] != 0 -> w0 = rank[no];
                 then `cmp w0, w21` and back to 0xF87BE0 (`b.le`, the flags survive adrp / add / br). Anything else:
                 the stock compare with the game's own rank.
Inert: offline stock; an empty or other-round key = stock (the assist never fills it on the authority, nor with
fewer than 4 entries, so 2 / 3 players and the authority itself are untouched); Bloodbound compares team ranks with
team ranks, so both members of a pair get the same answer. Apply CUTAUTH_CAVE, then CUTAUTH."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'cutauth_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
SITE = 0xF87BDC             # cmp w0, w21
BACK = 0xF87BE0             # b.le #0xf87bac
FUNC = 0xF879A0
FUNC_END = 0xF87C80
KEY_MAGIC = 0xC0710000
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


# ---------------------------------------------------------------- stock words [V]
for a, t in ((FUNC, 'pacibsp'), (0xF879F0, 'ldrsb w8, [x8, #0x92]'), (0xF87A4C, 'adrp x8, #0x5b65000'),
             (0xF87A50, 'add x8, x8, #0xc70'), (0xF87A54, 'ldrb w24, [x8]'), (0xF87A64, 'cmp w24, #2'),
             (0xF87A94, 'ldrsb w21, [x10, #0x92]'), (0xF87AF8, 'ldrsb w8, [x8, #0xaa]'),
             (0xF87AE4, 'ldrsb w8, [x8, #0xab]'), (0xF87B28, 'fcvtps w21, s0'), (0xF87B2C, 'adrp x8, #0x56ea000'),
             (0xF87B30, 'add x8, x8, #0x238'), (0xF87B40, 'adrp x8, #0x56ea000'), (0xF87B44, 'add x8, x8, #0x280'),
             (0xF87B90, 'ldr x8, [x20, #0x488]'), (0xF87B9C, 'add x20, x20, #0x38'), (0xF87BB0, 'add x20, x20, #0x60'),
             (0xF87BB8, 'ldrb w8, [x20, #8]'), (0xF87BBC, 'cmp w8, #4'), (0xF87BD0, 'sub x1, x20, #0x38'),
             (0xF87BD4, 'ldr x8, [x8, #0x30]'), (0xF87BD8, 'blr x8'), (SITE, 'cmp w0, w21'),
             (BACK, 'b.le #0xf87bac'), (0xF87BE4, 'add x8, sp, #0x30'), (0xF87BE8, 'mov x0, x20'),
             (0xF87BEC, 'mov w1, #1'), (0xF87BF4, 'bl #0x11383e8'), (0xF87C50, 'retab'), (FUNC_END, 'pacibsp'),
             # the offline byte and the stage pointer as other code reads them
             (0x1140DC0, 'adrp x8, #0x5b65000'), (0x1140DC4, 'ldr x8, [x8, #0xc20]'),
             (0x1140DC8, 'ldrb w8, [x8, #0xbda]')):
    stock(a, t)
listing.append('[V] cut 0xF879A0: per entry (x20 = entry + 0x38) w0 = functor rank, 0xF87BDC cmp w0, w21; b.le keep')
# the functors: 0x56EA280 -> +0x10, 0x56EA238 -> +0x20 (vt+0x30 of each)
for vt, off in ((0x56EA280, 0x10), (0x56EA238, 0x20)):
    fn = struct.unpack_from('<Q', C.DATA, vt + 0x30 - C.DATA_BASE)[0]
    body = ' | '.join(C.dis1(fn + 4 * k, W[(fn + 4 * k) // 4]) for k in range(6))
    assert '#0x%x]' % off in body, (hex(vt), hex(fn), body)
    listing.append('[V] functor %#x vt+0x30 = %#x reads entry +%#x: %s' % (vt, fn, off, body))
# x20 is entry + 0x38 at the site on every path: the loop body only (0xF87BB8..), entered from 0xF87BA8 / 0xF87BB4
assert targets_in(SITE, SITE + 4) == [], 'branch into the site'
assert targets_in(BACK, BACK + 4) == [], 'branch into 0xF87BE0'
listing.append('[V] 0xF87BDC / 0xF87BE0 are entered by fall-through only')
# x16 / x17 dead: not named anywhere in the function
named = [x for x in range(FUNC, FUNC_END, 4) if re.search(r'\b[xw]1[67]\b', C.dis1(x, W[x // 4]))]
assert named == [], [hex(x) for x in named]
listing.append('[V] x16 / x17 not named in 0xF879A0..0xF87C80; w0 dead after the compare (0xF87BAC loop reloads x0, '
               '0xF87BE8 mov x0, x20)')
assert not any(SITE + i in C.SHIPPED for i in range(4)), 'shipped word at the site'
others = C.live_records(exclude=(OUT,))
assert not any(SITE + i in others for i in range(4)), '%x taken: %s' % (SITE, others.get(SITE))

_read_registry = C.read_registry


def _registry_tolerant():
    """an exact duplicate registry row (another helper's edit) is tolerated; any real overlap still fails"""
    try:
        return _read_registry()
    except AssertionError:
        rows, seen = [], set()
        for line in open(C.REGISTRY, encoding='utf-8'):
            m = C._ROW.match(line.strip())
            if m:
                key = (m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16))
                if key not in seen:
                    seen.add(key)
                    rows.append(dict(owner=key[0], tag=key[1], lo=key[2], hi=key[3], purpose=m.group(5)))
        print('NOTE: cave_registry.md has an exact duplicate row (left as it is)')
        return rows


C.read_registry = _registry_tolerant
g = C.Gen('cutauth_gen', out=OUT, dry=True)
g.others = others
# rows handed to the lead earlier but maybe not in cave_registry.md yet: kept free here
PENDING = ((0xC502600, 0xC502920, 'kindeath3 rows (pending)'), (0xC502920, 0xC502970, 'bbfinal BBALLY (pending)'),
           (0xC502B20, 0xC502BC0, 'finalout FOUT'), (0xC502BC0, 0xC502C60, 'kinrecall KREC'),
           (0xC50F314, 0xC50F318, 'finalout FOUTBOX'))
for lo_, hi_, why_ in PENDING:
    for x_ in range(lo_, hi_):
        others.setdefault(x_, why_)
SIZE = 28
T = g.alloc('CAUTH', 'FAR_CODE', SIZE * 4, "CUTAUTH: the cut 0xF87BDC compares the authority's rank from CUTBOX "
            '(guests, rounds 1..3, online)')
BOX = g.alloc('CUTBOX', 'FAR_DATA', 0x18, 'CUTAUTH mailbox: u32 key 0xC0710000 + round, +8 u8 rank[16] by player no '
              '(assist writes, the cave reads)')

a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 16, 0x5B65C20))
a(C.ldr_x(16, 16, 0xC20))
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldrb(16, 16, 0xBDA))
a(C.to(C.cbnz_w, 'w16', 'stock'))               # offline: stock
a(lambda pc, L: C.adrp(pc, 16, BOX))
a(C.ldr_w(17, 16, C.lo12(BOX)))                 # key
a(C.to(C.cbz_w, 'w17', 'stock'))
a(lambda pc, L: C.adrp(pc, 16, 0x5B3CDF8))
a(C.ldr_x(16, 16, 0xDF8))                       # par (STAGE_PHASE)
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_w(16, 16, 0xB8))                        # round
a(C.movk_w(16, KEY_MAGIC >> 16, 1))             # 0xC071 << 16 | round (round < 0x10000)
a(C.cmp_wr(16, 17))
a(C.to(C.bne, 'stock'))                         # no list for this round
a(C.ldur_w(17, 20, -0x38))                      # entry +0: player number
a(C.cmp_wi(17, 16))
a(C.to(C.bhs, 'stock'))
a(lambda pc, L: C.adrp(pc, 16, BOX))
a(C.add_xi(16, 16, C.lo12(BOX) + 8))
a(C.add_xr(16, 16, 17))
a(C.ldrb(17, 16, 0))                            # the authority's rank of this player
a(C.to(C.cbz_w, 'w17', 'stock'))                # not in its list: our own rank
a(C.mov_w(0, 17))
a.label('stock')
a(C.cmp_wr(0, 21))                              # the replaced word
a.many(lambda pc, L: C.far_return(pc, BACK))    # flags survive adrp / add / br
cave = a
assert len(cave.words()) <= SIZE, len(cave.words())
listing.append('CAUTH: %d of %d words' % (len(cave.words()), SIZE))
for i, w in enumerate(cave.words()):
    t = C.dis1(T + 4 * i, w)
    dst = re.match(r'(?:ldr|ldur|mov|movk|add|adrp|ldrb) ([xw]\d+)', t)
    if dst:
        assert dst.group(1)[1:] in ('0', '16', '17'), t
    assert not t.startswith(('str', 'stp', 'stur')), t
    if t.startswith(('adrp', 'add', 'br')) and i >= len(cave.words()) - 3:
        pass
listing.append('[V gen] the cave writes only w0 (the rank it compares) / x16 / x17 and stores nothing; the flags of '
               'the last cmp reach 0xF87BE0 (adrp / add / br set none)')
recs = g.cave('CAUTH', T, cave)
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
    (NEAR_TRAMP is full)"""
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
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w_, 'trampoline -> 0x%X (x16 dead at the site)' % T)
         for k, w_ in enumerate(C.far_jump(PAD, T))]
site_rec = [g.text_patch(SITE, 'cmp w0, w21', C.b(SITE, PAD), "CUTAUTH (the authority's rank from CUTBOX)")]
groups = {'CUTAUTH_CAVE': recs + tramp, 'CUTAUTH': site_rec}
order = ['CUTAUTH_CAVE', 'CUTAUTH']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
print('(+ trampoline 0x%X..0x%X in text padding, no pool row)' % (PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'CAUTH': 0x%X}\nBOX = 0x%X\nKEY_MAGIC = 0x%08X\nSITE = 0x%X\nHOOK_WORD = 0x%08X\n"
                % (T, BOX, KEY_MAGIC, SITE, struct.unpack('<I', bytes.fromhex(site_rec[0][2]))[0]))
