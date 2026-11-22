"""host_take_gen.py: the LAN host takes its OWN Power drop locally, without the self-link round trip (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes host_take_live.py.
python host_take_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: pickup4_notes.md section 3. Needs PICKUP_ADD2 (pickup_gen2.py) for the inventory add.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Groups
  HOST_TAKE_CAVE  far caves HTAKE / HAWARD, FAR_DATA byte HFLAG (no record), two 3-word trampolines in text padding.
  HOST_TAKE       two words in the take request 0x15A4924:
     0x15A4978 `cmp w8, #6` (w8 = session mode) -> HTAKE:
        mode != 6                                   -> 0x15A49AC (stock non-LAN path)
        role byte != 0, or id & 0xF != 9, or the id's creator tag (bits 27..30, POWERS CREATE CTAG) != the local
        player number & 0xF, or no number           -> 0x15A4980 (stock: subtype 5 to the members)
        else (the host's own per-player Power drop)  -> HFLAG = 1, x24 = taker no (stock word 0x15A49B0), 0x15A49FC:
           the stock local branch: record 0x15B1C80, award 0x15A5020(.., chr by taker no) at 0x15A4CCC,
           local remove 0x159E034, return (mode 6 at 0x15A4D04). No message; the guests' copies stay (not MINE).
     0x15A4B98 `b.eq #0x15a4cd0` (mode-6 skip of that award) -> HAWARD: HFLAG set -> clear it, 0x15A4B9C (award);
        else the stock b.eq. Flags from 0x15A4B94 are kept (adrp / ldrb / strb / cbz only).
  The 0x4000 mark (0x15A4958) is set before the hook; the item is removed on success, so it does not matter."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'host_take_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
ROLE, NETP = 0x492AFD8, 0x5B57EB8
FN = 0x15A4924
S1, S2 = 0x15A4978, 0x15A4B98
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
for a, t in ((0x15A4948, 'ldr w8, [x1, #0x58]'), (0x15A4954, 'ldr w20, [x1, #0x30]'),
             (0x15A4958, 'orr w8, w8, #0x4000'), (0x15A496C, 'ldr w8, [x0, #0x1268]'), (0x15A4970, 'mov w25, w3'),
             (0x15A4974, 'mov x23, x2'), (S1, 'cmp w8, #6'), (0x15A497C, 'b.ne #0x15a49ac'),
             (0x15A4980, 'mov w8, #1'), (0x15A49AC, 'adrp x8, #0x59e1000'), (0x15A49B0, 'and x24, x23, #0xffffffff'),
             (0x15A49BC, 'cbz x8, #0x15a49fc'), (0x15A49FC, 'mov x0, x19'), (0x15A4A00, 'mov x1, x20'),
             (0x15A4A04, 'bl #0x15a2320'), (0x15A4B88, 'ldr x8, [x26]'), (0x15A4B94, 'cmp w8, #6'),
             (S2, 'b.eq #0x15a4cd0'), (0x15A4B9C, 'ldr w8, [sp, #0x48]'), (0x15A4BD8, 'stur w23, [x29, #-0x78]'),
             (0x15A4CCC, 'bl #0x15a5020'), (0x15A4CFC, 'bl #0x159e034'), (0x15A4D00, 'cmp w21, #6'),
             (0x15A4D04, 'b.ne #0x15a4d88'), (0x15A4D08, 'b #0x15a49dc')):
    stock(a, t)
end = FN + 4
while W[end // 4] != PACIBSP:
    end += 4
assert end == 0x15A4DE0, hex(end)
assert not [a for a in range(FN, end, 4) if W[a // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(a, W[a // 4]))]
for a in (S1, S2):
    assert not any(a + i in C.SHIPPED for i in range(4)), '%x shipped' % a
    assert not targets_in(a, a + 4), hex(a)
# only built-in word in 0x15A4924 is the subtype-5 send slot (vt+0x40), on the path HTAKE leaves to the guests
assert sorted(set(x & ~3 for x in range(FN, end) if x in C.SHIPPED)) == [0x15A49A0]
# x24 is first written at 0x15A49B0 on the stock path into 0x15A49FC; HTAKE writes it with that same word
listing.append('0x%X..0x%X: x16/x17 never named; only built-in word 0x15A49A0 (send slot)' % (FN, end))

others = C.live_records(exclude=(OUT,))


def find_pad(near, n):
    for a in range(near - 0x40000, near + 0x40000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(S1, a) and C.reach(S2, a + 12):
                return a
    return None


PAD = find_pad(FN, 6)
assert PAD
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 24))

g = C.Gen('host_take_gen', out=OUT, dry=True)
HFLAG = g.alloc('HFLAG', 'FAR_DATA', 4, 'HOST_TAKE: 1 from HTAKE to the award gate (byte)')
SIZES = {'HTAKE': 36, 'HAWARD': 16}
T1 = g.alloc('HTAKE', 'FAR_CODE', SIZES['HTAKE'] * 4, 'take 0x15A4978: host own Power drop -> local take')
T2 = g.alloc('HAWARD', 'FAR_CODE', SIZES['HAWARD'] * 4, 'take 0x15A4B98: HFLAG -> award in mode 6')

AND_W17_W20_F = 0x12000C00 | (20 << 5) | 17
LSR_W16_W20_27 = 0x53000000 | (27 << 16) | (31 << 10) | (20 << 5) | 16
AND_W17_F = 0x12000C00 | (17 << 5) | 17
AND_W16_F = 0x12000C00 | (16 << 5) | 16
for w, t in ((AND_W17_W20_F, 'and w17, w20, #0xf'), (LSR_W16_W20_27, 'lsr w16, w20, #0x1b'),
             (AND_W17_F, 'and w17, w17, #0xf'), (AND_W16_F, 'and w16, w16, #0xf')):
    assert C.dis1(0, w) == t, (C.dis1(0, w), t)

a = C.Asm(T1)
a(C.cmp_wi('w8', 6))
a(C.to(C.beq, 'lan'))
a.many(lambda pc, L: C.far_jump(pc, 0x15A49AC))            # not mode 6: stock
a.label('lan')
a(lambda pc, L: C.adrp(pc, 16, ROLE))
a(C.ldrb(16, 16, C.lo12(ROLE)))
a(C.to(C.cbnz_w, 'w16', 'send'))                           # guest: stock send
a(AND_W17_W20_F)
a(C.cmp_wi('w17', 9))
a(C.to(C.bne, 'send'))                                     # not a per-player Power drop
a(lambda pc, L: C.adrp(pc, 16, NETP))
a(C.ldr_x(16, 16, C.lo12(NETP)))
a(C.to(C.cbz_x, 'x16', 'send'))
a(C.ldr_x(17, 16, 0x28))
a(C.to(C.cbnz_x, 'x17', 'have'))
a(C.ldr_x(17, 16, 0x20))
a(C.to(C.cbz_x, 'x17', 'send'))
a.label('have')
a(C.ldr_w(17, 17, 0xD0))
a(AND_W17_F)
a(C.to(C.cbz_w, 'w17', 'send'))                            # not numbered (0 / -1 & 0xF = 0xF is a real tag, see notes)
a(LSR_W16_W20_27)
a(AND_W16_F)
a(C.cmp_wr('w16', 'w17'))
a(C.to(C.bne, 'send'))                                     # someone else's drop
a(lambda pc, L: C.adrp(pc, 16, HFLAG))
a(C.movz_w(17, 1))
a(C.strb(17, 16, C.lo12(HFLAG)))
a(W[0x15A49B0 // 4])                                       # and x24, x23, #0xffffffff (taker no)
a.many(lambda pc, L: C.far_jump(pc, 0x15A49FC))            # stock local take branch
a.label('send')
a.many(lambda pc, L: C.far_jump(pc, 0x15A4980))            # stock mode-6 send
htake = a

a = C.Asm(T2)                                              # flags from `cmp w8, #6` at 0x15A4B94 stay live
a(lambda pc, L: C.adrp(pc, 16, HFLAG))
a(C.ldrb(17, 16, C.lo12(HFLAG)))
a(C.to(C.cbz_w, 'w17', 'stock'))
a(C.strb('wzr', 16, C.lo12(HFLAG)))
a.many(lambda pc, L: C.far_jump(pc, 0x15A4B9C))            # HFLAG: award even in mode 6
a.label('stock')
a(C.to(C.bne, 'cont'))
a.many(lambda pc, L: C.far_jump(pc, 0x15A4CD0))            # stock b.eq taken (mode 6)
a.label('cont')
a.many(lambda pc, L: C.far_jump(pc, 0x15A4B9C))
haward = a

for n, x in (('HTAKE', htake), ('HAWARD', haward)):
    assert len(x.words()) <= SIZES[n], (n, len(x.words()))
for base, x in ((T1, htake), (T2, haward)):
    for i, w in enumerate(x.words()):
        t = C.dis1(base + 4 * i, w)
        assert not re.search(r'\b(cmn|adds|subs|ands|tst)\b', t) or base == T1, t
# HAWARD must not change the flags before its b.ne
for i, w in enumerate(haward.words()[:6]):
    t = C.dis1(T2 + 4 * i, w)
    assert t.split()[0] in ('adrp', 'ldrb', 'cbz', 'strb', 'add', 'br', 'b.ne'), t

caves = g.cave('HTAKE', T1, htake) + g.cave('HAWARD', T2, haward)
tramps = []
for t, tgt in ((PAD, T1), (PAD + 12, T2)):
    for k, w in enumerate(C.far_jump(t, tgt)):
        tramps.append(g.text_patch(t + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 never named in 0x15A4924)' % tgt))
hooks = [g.text_patch(S1, 'cmp w8, #6', C.b(S1, PAD), 'HOST_TAKE (own Power drop -> local take)'),
         g.text_patch(S2, 'b.eq #0x15a4cd0', C.b(S2, PAD + 12), 'HOST_TAKE (award in mode 6 while HFLAG)')]
groups = {'HOST_TAKE_CAVE': caves + tramps, 'HOST_TAKE': hooks}
order = ['HOST_TAKE_CAVE', 'HOST_TAKE']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('HFLAG byte at main+0x%X (FAR_DATA, no record)' % HFLAG)
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'HTAKE': 0x%X, 'HAWARD': 0x%X, 'HFLAG': 0x%X, 'TR': 0x%X}\nNEEDS = ['PICKUP_ADD2']\n"
                % (T1, T2, HFLAG, PAD))
