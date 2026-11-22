"""loveaccept_gen.py: Love Ephemeral "Accept flowers" prompt for the bearer's REMOTE chr (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes loveaccept_live.py.
python loveaccept_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: sigil15_notes.md section 4.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in sigil15_notes.md section 4; the lead adds the rows when baking:
  loveaccept_gen | LOVEACCEPT | <printed range> | Love: accept-prompt key fallback on the bearer's offering bit

Groups
  LOVEACCEPT_CAVE  far cave LOVEACCEPT (15 words) + a 3-word trampoline in zero padding near the chr action-button
     updater 0x19C9AA0.
  LOVEACCEPT       the one word 0x19C9D94 `cbz w8, #0x19c9b64` of the button-100000 block ("Accept flowers") ->
     `b trampoline`. Stock gate there: the OTHER chr's action key (M = [[chr+0x2470]+0x108], key = M+0x5E, else
     M+0x60, else 0xFF) must be 0 or 50 (ro tables 0x4C5141E / 0x4C5138E / 0x4C51440, kind 0x33). The key is set
     only by TAE event 932 (0x193C554), which the TAE dispatcher 0x193A9A0 classes 0 (0x195212C) and so may skip on
     a remote chr, while the offering event 10820 (class 1) runs there. The cave keeps the stock answer when the
     table says yes; when it says no, it lets the block go on ONLY if that chr shows the Love offering bit
     [[chr+0x2470]]+0x144 bit 2 (set by the same emote, event 10820). Every later stock test is unchanged: not the
     local chr (0x172F914), the loved one's own 250 logic lists that chr (0x1183E00 -> vt+0x148 0x118E9DC ->
     0x119B2A0) and not reunited, the box / facing test of ActionButtonParam 100000 (0x19C9F6C). Inert when the key
     is already right (offline, host-side bearer) and for every other button."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'loveaccept_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
FUNC = 0x19C9AA0          # chr action-button updater (other chr's module M in x19)
SITE = 0x19C9D94          # cbz w8, #0x19c9b64 (kind 0x33 table byte == 0 -> skip button 100000)
BACK = 0x19C9D98          # ldr x0, [x19, #8]  (go on with button 100000)
SKIP = 0x19C9B64          # next button block (stock "no")
FEND = 0x19C9F6C          # next function (range test)
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
        # the updater: local chr x21 (WCM+0x1A8), its module x20, the OTHER chr's module x19
        (0x19C9AC8, 'ldr x21, [x8, #0x1a8]'), (0x19C9AD4, 'ldr x20, [x8, #0x108]'), (0x19C9AEC, 'mov x19, x0'),
        (0x19C9ADC, 'ldrh w8, [x0, #0x60]'), (0x19C9AE8, 'ldrh w12, [x0, #0x5e]'),
        (0x19C9AF8, 'add x22, x22, #0x41e'),                       # key table ro 0x4C5141E
        (0x19C9CBC, 'cmp w14, #0x34'), (0x19C9CC4, 'cmp w14, #0x33'), (0x19C9CC8, 'b.eq #0x19c9d74'),
        # the button-100000 block
        (0x19C9D88, 'add x10, x10, #0x440'), (0x19C9D90, 'ldrb w8, [x9, x8]'),
        (SITE, 'cbz w8, #0x19c9b64'), (BACK, 'ldr x0, [x19, #8]'), (0x19C9D9C, 'bl #0x172f914'),
        (0x19C9DCC, 'bl #0x1183e00'), (0x19C9DD8, 'mov w0, #0x86a0'), (0x19C9DE4, 'bl #0x19c9f6c'),
        (0x19C9E14, 'bl #0x19c8d80'), (SKIP, 'ldrh w8, [x19, #0x60]'),
        # the two flags written by the bearer's emote (TAE dispatcher 0x193A9A0)
        (0x193C568, 'strh w9, [x8, #0x5e]'),                       # event 932: action key
        (0x118E780, 'ldrb w9, [x9, #0x144]'), (0x118E784, 'tbz w9, #2, #0x118e86c'),   # 250 reads the offering bit
        (0x118E774, 'ldr x8, [x21, #0x2470]'), (0x118E778, 'ldr x9, [x8]')):
    stock(a, t)
assert W[FUNC // 4] == PACIBSP and W[FEND // 4] == PACIBSP
assert not targets_in(SITE, SITE + 4), 'branch into the site'
# x16 / x17 are never used in 0x19C9AA0..0x19C9F6C, so x16 is dead at BACK and SKIP
for a in range(FUNC, FEND, 4):
    assert not re.search(r'\b[xw]1[67]\b', C.dis1(a, C.text_word(a))), hex(a)
# the kind-0x33 row allows keys 0 and 50 only (column 0 and 5 of the 17-column table)
_keys = struct.unpack_from('<17H', C.RO, 0x4C5141E - C.RO_BASE)
_kinds = C.RO[0x4C5138E - C.RO_BASE:0x4C5138E - C.RO_BASE + 13]
_row = _kinds.index(0x33)
_allow = [_keys[i] for i in range(17) if C.RO[0x4C51440 - C.RO_BASE + _row * 17 + i]]
assert _allow == [0, 50], _allow
listing.append('stock: button 100000 needs the other chr key in %s; 0xFF (no key) is refused' % _allow)

# trampoline: 3 zero words of padding before a function start, nothing points into them, nobody uses them
others = C.live_records(exclude=(OUT,))
PAD = None
for a in range(0x19C0000, 0x19E0000, 4):
    if W[a // 4] == 0 and W[a // 4 + 1] == 0 and W[a // 4 + 2] == 0 and W[a // 4 - 1] != 0:
        end = a
        while W[end // 4] == 0:
            end += 4
        if W[end // 4] != PACIBSP:
            continue
        if any(x in C.SHIPPED or x in others for x in range(a, a + 12)):
            continue
        if targets_in(a, end) or qwords_in(a, end):
            continue
        if C.reach(SITE, a):
            PAD = a
            break
assert PAD, 'no free padding'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 12))

g = C.Gen('loveaccept_gen', out=OUT, dry=True)      # dry: never writes cave_registry.md (task rule)
SIZE = 16
T = g.alloc('LOVEACCEPT', 'FAR_CODE', SIZE * 4, 'Love: accept-prompt key fallback on the bearer offering bit')
listing.append('cave LOVEACCEPT 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)'
               % (T, T + SIZE * 4))

a = C.Asm(T)
a(C.to(C.cbnz_w, 'w8', 'back'))                         # stock table says yes: stock path
a(C.ldr_x(9, 19, 8))                                    # x9 = other chr (M+8)
a(C.to(C.cbz_x, 'x9', 'skip'))
a(C.ldr_x(9, 9, 0x2470))
a(C.to(C.cbz_x, 'x9', 'skip'))
a(C.ldr_x(9, 9, 0))                                     # flag block [[chr+0x2470]]
a(C.to(C.cbz_x, 'x9', 'skip'))
a(C.ldrb(9, 9, 0x144))
a(C.to(C.tbz, 'w9', 2, 'skip'))                         # no Love offering: stock "no"
a.label('back')
a.many(lambda pc, L: C.far_return(pc, BACK))
a.label('skip')
a.many(lambda pc, L: C.far_return(pc, SKIP))
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
for t in dis:
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (8, 9, 16, 19), t              # w8 / x9 are rewritten before use on both exits
assert 'ldrb w9, [x9, #0x144]' in dis and 'ldr x9, [x9, #0x2470]' in dis

caves = g.cave('LOVEACCEPT', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LOVEACCEPT 0x%X (x16 unused in 0x19C9AA0)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'cbz w8, #0x19c9b64', C.b(SITE, PAD), 'button 100000 key gate -> LOVEACCEPT')]
groups = {'LOVEACCEPT_CAVE': caves + tramp, 'LOVEACCEPT': hook}
order = ['LOVEACCEPT_CAVE', 'LOVEACCEPT']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'LOVEACCEPT': 0x%X, 'TRAMP': 0x%X}\n" % (T, PAD))
