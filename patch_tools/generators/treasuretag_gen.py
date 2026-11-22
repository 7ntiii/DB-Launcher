"""treasuretag_gen.py: a CTAG-style player tag for map-treasure record ids made by a NEW host (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes treasuretag_live.py.
python treasuretag_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: players8b_notes.md P3, audit_v398_notes.md section 2.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why: a world-item record id is (counter << 5) | kind bits, from a per-game counter. Only the host creates map
treasures (TREASURE_HOST2 + ITEMS I3), so a guest's counters never move. After a host hand-over the new host
counts from its own (low) counters and can repeat ids of items the old host made that are still in the world.
Fix: when the id is formed in the three creators the treasure step 0x15AB6D0 uses (lot kind < 2: 0x15AB840,
kind 2: 0x15AC2A8 -> 0x15B0B40, kind 3: 0x15AC42C), put the own player number into bits 27..30 (as CTAG does for
Power drops) - only online, only on the host (role byte 0) and only when the own number is 2..15.
Player 1 (the first host) never tags: while it stays host nothing changes. CTAG's own Power-drop tag (same
bits, same value) is written after this one, so those ids are unchanged too.

Groups
  TREASURE_TAG_CAVE  far caves TT_A / TT_B / TT_C (23 words each) + three 3-word trampolines in zero text padding.
  TREASURE_TAG       three hooks, each on the id-forming `orr wD, wN, wC, lsl #5`:
     0x15ABC34 `orr w11, w13, w11, lsl #5` (0x15AB840, counter +0xC)
     0x15AC578 `orr w8, w8, w12, lsl #5`  (0x15AC42C, counter +0x20)
     0x15B0D84 `orr w8, w8, w11, lsl #5`  (0x15B0B40, counter +0x24; also every other lot of that creator)
  Each cave: the relocated orr; offline (+0xBDA != 0) or role byte 0x492AFD8 != 0 or own number not in 2..15
  -> back unchanged; else `bfi wD, wNo, #27, #4`; back to site + 4. Uses only x16 / x17 and sets no flags."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'treasuretag_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFP = 0x5B65C20             # *(main+0x5B65C20)+0xBDA = offline byte (!= 0 offline)
ROLE = 0x492AFD8             # u8 role byte (GENERATOR_IDLE): 0 = this game is the host
GDM = 0x5B57EB8              # *(GDM)+0x20 = local pgd, +0xD0 = own player number
SITES = [  # (site, stock text, dest reg, function start, function end, name)
    (0x15ABC34, 'orr w11, w13, w11, lsl #5', 11, 0x15AB840, 0x15AC2A8, 'TT_A'),
    (0x15AC578, 'orr w8, w8, w12, lsl #5', 8, 0x15AC42C, 0x15AC788, 'TT_B'),
    (0x15B0D84, 'orr w8, w8, w11, lsl #5', 8, 0x15B0B40, 0x15B1110, 'TT_C'),
]
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def bl_target(pc, w):
    if (w & 0xFC000000) in (0x94000000, 0x14000000):
        imm = w & 0x3FFFFFF
        return pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
    return None


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            t = bl_target(pc, w)
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


# ---------------- extra encoders (checked with capstone below)
def and_w_fff0(rd, rn):   # and wd, wn, #0xfffffff0  (N=0, immr=28, imms=27)
    return 0x12000000 | (28 << 16) | (27 << 10) | (C.R(rn) << 5) | C.R(rd)


def lsr_w1(rd, rn):       # lsr wd, wn, #1 = ubfm wd, wn, #1, #31
    return 0x53000000 | (1 << 16) | (31 << 10) | (C.R(rn) << 5) | C.R(rd)


def bfi_27_4(rd, rn):     # bfi wd, wn, #27, #4 = bfm wd, wn, #5, #3
    return 0x33000000 | (5 << 16) | (3 << 10) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, and_w_fff0(16, 17)) == 'and w16, w17, #0xfffffff0', C.dis1(0, and_w_fff0(16, 17))
assert C.dis1(0, lsr_w1(16, 17)) == 'lsr w16, w17, #1', C.dis1(0, lsr_w1(16, 17))
assert C.dis1(0, bfi_27_4(8, 17)) == 'bfi w8, w17, #0x1b, #4', C.dis1(0, bfi_27_4(8, 17))

# ================================================================ code facts [V]
# the treasure step calls the three creators by lot kind (+0x40): < 2, == 2, == 3
for a, t in [(0xC2D0A8, 'bl #0x15ab6d0'), (0x15AB7C8, 'bl #0x15ab840'), (0x15AB808, 'bl #0x15ac2a8'),
             (0x15AB7A8, 'bl #0x15ac42c'), (0x15AC364, 'bl #0x15b0b40'),
             # the counters feeding each orr
             (0x15ABC04, 'ldr w11, [x15, #0xc]'), (0x15ABC44, 'str w10, [x15, #0xc]'),
             (0x15AC568, 'ldr w12, [x11, #0x20]'), (0x15AC5B4, 'str w10, [x11, #0x20]'),
             (0x15B0D78, 'ldr w11, [x9, #0x24]'), (0x15B0DF4, 'str w8, [x9, #0x24]')]:
    stock(a, t)
for site, text, rd, f0, f1, name in SITES:
    stock(site, text)
    assert W[f0 // 4] == PACIBSP, hex(f0)
    # x16 / x17 after the site, up to the next function: only the known uses in 0x15B0B40, where w17 is written at
    # 0x15B0F08 and w16 at 0x15B0F54 before their reads in the same straight-line block / loop [V by hand]
    e = site + 4
    while W[e // 4] != PACIBSP:
        e += 4
    named = [(a, C.dis1(a, W[a // 4])) for a in range(site + 4, e, 4)
             if re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
    allowed = {0x15B0F08: 'ldrb w17, [x29, #0x60]', 0x15B0F0C: 'str w17, [sp, #0xc]',
               0x15B0F54: 'ldrh w16, [x9], #0xc', 0x15B0F5C: 'stp w15, w16, [x11, #-8]',
               0x15B0F6C: 'and w8, w17, #0xff'} if name == 'TT_C' else {}
    assert dict(named) == allowed, (name, [(hex(a), d) for a, d in named])
    assert not targets_in(0x15B0F0C, 0x15B0F44) and targets_in(0x15B0F44, 0x15B0F70) == [0x15B0F64]
    listing.append('%s: x16/x17 after the site up to 0x%X: %s' % (name, e, [hex(a) for a, _ in named] or 'none'))
    # flags: the cave sets none, so nothing to prove; the hook word itself is kept as the cave's first word
    listing.append('%s: hook word 0x%X is a branch target of %s' % (name, site, [hex(x) for x in targets_in(site, site + 4)]))

# ================================================================ allocation
g = C.Gen('treasuretag_gen', OUT, dry=True)
PENDING = [('kindeath3_gen', 'KAUTH3..KPRED3', 0xC502600, 0xC502920), ('bbfinal_gen', 'BBALLY', 0xC502920, 0xC502970),
           ('starcrash4_gen', 'SC_GAME4', 0xC502970, 0xC5029CC)]
for _o, _t, _lo, _hi in PENDING:
    if not any(r['lo'] < _hi and _lo < r['hi'] for r in C.read_registry()):
        g._dry_rows.append(dict(owner=_o, tag=_t, lo=_lo, hi=_hi, purpose='pending claim (not ours)'))


def find_pad(site, lo, hi, avoid=()):
    for a in range(lo, hi, 4):
        if W[a // 4] == 0 and W[a // 4 + 1] == 0 and W[a // 4 + 2] == 0 and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP or any(abs(a - v) < 12 for v in avoid):
                continue
            if any(x in C.SHIPPED or x in g.others for x in range(a, a + 12)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    raise AssertionError('no pad near %x' % site)


N = 23
caves, tramps, hooks, used = [], [], [], []
for site, text, rd, f0, f1, name in SITES:
    pad = find_pad(site, site - 0x40000, site + 0x40000, avoid=used)
    used.append(pad)
    T = g.alloc(name, 'FAR_CODE', N * 4, 'TREASURE_TAG %s: tag the id formed at 0x%X with the own player number '
                '(new host only)' % (name, site))
    a = C.Asm(T)
    a(W[site // 4])                                     # the relocated orr (forms the id in wD)
    a(lambda pc, L: C.adrp(pc, 16, OFFP))
    a(C.ldr_x(16, 16, C.lo12(OFFP)))
    a(lambda pc, L: C.cbz_x(pc, 16, L['back']))         # no offline-byte owner: unchanged
    a(C.ldrb(17, 16, 0xBDA))
    a(lambda pc, L: C.cbnz_w(pc, 17, L['back']))        # offline: unchanged
    a(lambda pc, L: C.adrp(pc, 16, ROLE))
    a(C.ldrb(17, 16, C.lo12(ROLE)))
    a(lambda pc, L: C.cbnz_w(pc, 17, L['back']))        # not the host: unchanged
    a(lambda pc, L: C.adrp(pc, 16, GDM))
    a(C.ldr_x(16, 16, C.lo12(GDM)))
    a(lambda pc, L: C.cbz_x(pc, 16, L['back']))
    a(C.ldr_x(16, 16, 0x20))                            # local pgd
    a(lambda pc, L: C.cbz_x(pc, 16, L['back']))
    a(C.ldr_w(17, 16, 0xD0))                            # own player number
    a(and_w_fff0(16, 17))
    a(lambda pc, L: C.cbnz_w(pc, 16, L['back']))        # > 15 or -1: unchanged
    a(lsr_w1(16, 17))
    a(lambda pc, L: C.cbz_w(pc, 16, L['back']))         # 0 or 1 (the first host): unchanged
    a(bfi_27_4(rd, 17))                                 # id bits 27..30 = own number (as CTAG)
    a.label('back')
    a.many(lambda pc, L, s=site: C.far_return(pc, s + 4))
    words = a.words()
    assert len(words) == N, len(words)
    caves += g.cave(name, T, words)
    tramps += [g.text_patch(pad + 4 * k, 'udf #0', w, 'trampoline -> %s 0x%X' % (name, T))
               for k, w in enumerate(C.far_jump(pad, T))]
    hooks.append(g.text_patch(site, text, C.b(site, pad), 'TREASURE_TAG %s' % name))
    listing.append('%s: site 0x%X -> pad 0x%X..0x%X -> cave 0x%X' % (name, site, pad, pad + 12, T))

groups = {'TREASURE_TAG_CAVE': caves + tramps, 'TREASURE_TAG': hooks}
order = ['TREASURE_TAG_CAVE', 'TREASURE_TAG']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in [r for r in g._dry_rows if r['owner'] == 'treasuretag_gen']:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("SITES = %r\nPADS = %r\n" % ([hex(s[0]) for s in SITES], [hex(p) for p in used]))
