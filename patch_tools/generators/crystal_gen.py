"""crystal_gen.py: a guest's Bloodsac kill makes the skill-enhancement offer on the guest's own game (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes crystal_live.py.
python crystal_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: batch39b_notes.md section 2. Replaces the withdrawn CRYSTAL_LOCAL (treasure_live.py; same word).

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed row:
  crystal_gen | CGUEST | <printed range> | guest Bloodsac offer (batch39b 2)

Groups
  CRYSTAL_GUEST_CAVE  far cave CGUEST + a 3-word trampoline in zero padding.
  CRYSTAL_GUEST       hook 0x15B0528 `cbz w8, #0x15b054c` (w8 = offline byte) -> `b trampoline`:
     offline (w8 != 0)      -> 0x15B052C, the stock local call (unchanged)
     LAN, role byte 0 (host) -> 0x15B054C, the stock send (host serves its own subtype 14 over the self link)
     LAN, role byte 1 (guest) -> the stock local call sequence 0x15B052C..0x15B0544 (+ w2 reload from [sp+0x3c]):
        0x15B33A4 on the guest: its crystal give 0x159C6C4 is refused there by I3 (no double give), and
        0xCFE9A8 -> SKILL_LOCAL -> 0xCFEC40 queues the offer for the guest's own pgd;
        then 0x15B054C, the stock send, so the host still runs the give part for the guest as today."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'crystal_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
ROLE = 0x492AFD8
SITE, LOCAL, SEND, AWARD = 0x15B0528, 0x15B052C, 0x15B054C, 0x15B33A4
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
COPY = [(0x15B052C, 'ldp s0, s1, [sp, #0x20]'), (0x15B0530, 'and x3, x20, #0xffffffff'),
        (0x15B0534, 'ldr s2, [sp, #0x28]'), (0x15B0538, 'add x1, sp, #0x18'), (0x15B053C, 'mov x0, x19'),
        (0x15B0540, 'str xzr, [sp, #0x18]')]
for a, t in COPY + [(0x15B0510, 'ldr w2, [sp, #0x3c]'), (0x15B0514, 'stp w2, w20, [sp, #0x44]'),
                    (0x15B0524, 'ldrb w8, [x8, #0xbda]'), (SITE, 'cbz w8, #0x15b054c'),
                    (0x15B0544, 'bl #0x15b33a4'), (0x15B0548, 'b #0x15b0574'),
                    (SEND, 'adrp x8, #0x5b3c000'), (0x15B0560, 'add x2, sp, #0x40'), (0x15B0568, 'mov w3, #0x1c'),
                    (0x15B0574, 'ldp x20, x19, [sp, #0xa0]')]:
    stock(a, t)
# the subtype-14 message lives at sp+0x40..0x5B (built before the gate); the local call writes only sp+0x18
assert C.dis1(0x15B04F8, W[0x15B04F8 // 4]) == 'str w8, [sp, #0x40]'
# the send path reads no caller-saved register set before the gate (it loads x8 / x0 / x2 / w1 / w3 itself)
for a in range(SEND, 0x15B0574, 4):
    t = C.dis1(a, W[a // 4])
    assert not re.search(r'\b[xw](4|5|6|7|9|1[0-8])\b', t), t
fn = SITE
while W[fn // 4] != PACIBSP:
    fn -= 4
assert fn == 0x15B02A8, hex(fn)
e = fn + 4
while W[e // 4] != PACIBSP:
    e += 4
assert not [a for a in range(fn, e, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
assert not targets_in(SITE, SITE + 4)
listing.append('0x15B02A8..0x%X: x16/x17 never named; message at sp+0x40 built before the gate' % e)

others = C.live_records(exclude=(OUT, 'treasure_live.py'))
PAD = None
for a in range(0x15A0000, 0x15C0000, 4):
    if W[a // 4] == 0 and W[a // 4 + 1] == 0 and W[a // 4 + 2] == 0 and W[a // 4 - 1] != 0:
        z = a
        while W[z // 4] == 0:
            z += 4
        if W[z // 4] != PACIBSP:
            continue
        if any(x in C.SHIPPED or x in others for x in range(a, a + 12)):
            continue
        if targets_in(a, z) or qwords_in(a, z):
            continue
        if C.reach(SITE, a):
            PAD = a
            break
assert PAD
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 12))

g = C.Gen('crystal_gen', out=OUT, dry=True)
for i in range(4):          # CRYSTAL_LOCAL (withdrawn, treasure_live.py) held the same word
    g.others.pop(SITE + i, None)
SIZE = 28
T = g.alloc('CGUEST', 'FAR_CODE', SIZE * 4, 'guest Bloodsac offer (batch39b 2)')
listing.append('cave CGUEST 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)' % (T, T + SIZE * 4))

a = C.Asm(T)
a(C.to(C.cbz_w, 'w8', 'lan'))
a.many(lambda pc, L: C.far_jump(pc, LOCAL))             # offline: stock local call
a.label('lan')
a(lambda pc, L: C.adrp(pc, 16, ROLE))
a(C.ldrb(16, 16, C.lo12(ROLE)))
a(C.to(C.cbz_w, 'w16', 'send'))                         # host: stock send only
for addr, _ in COPY:
    a(W[addr // 4])                                     # position-independent stock words
a(W[0x15B0510 // 4])                                    # ldr w2, [sp, #0x3c] (victim handle)
a.many(lambda pc, L: [C.adrp(pc, 16, AWARD), C.add_xi(16, 16, C.lo12(AWARD)), C.blr(16)])
a.label('send')
a.many(lambda pc, L: C.far_jump(pc, SEND))
words = a.words()
assert len(words) <= SIZE, len(words)
caves = g.cave('CGUEST', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> CGUEST 0x%X (x16 never named in 0x15B02A8)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'cbz w8, #0x15b054c', C.b(SITE, PAD), 'CRYSTAL_GUEST gate')]
groups = {'CRYSTAL_GUEST_CAVE': caves + tramp, 'CRYSTAL_GUEST': hook}
order = ['CRYSTAL_GUEST_CAVE', 'CRYSTAL_GUEST']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'CGUEST': 0x%X, 'TRAMP': 0x%X}\nEXCLUSIVE_WITH = {'CRYSTAL_GUEST': ['CRYSTAL_LOCAL']}\n"
                % (T, PAD))
