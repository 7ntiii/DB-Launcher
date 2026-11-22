"""rewardonce_gen.py: REWARDONCE (alpha 13 fire fix). Static generator. Writes rewardonce_live.py.
python rewardonce_gen.py [--dry]   (from diag/net)
The final coordinator 0x116A6A0 (UpdatePhase of the last phase; host only through the shipped 0x116ACE0 record)
lists every frame the dead players with no respawn whose pgd+0x46B0 stage byte is 1 (collector 0x116C638),
hands them to its death list vt+0x98 and then, per listed player, gives the phase reward 0x15AA020(MapItemMan,
&player_no, vt+0xB8()) at 0x116B810. Stock (server) the death list's deque entry is consumed at once and the
player's stage leaves 1, so the list holds it for one frame and the reward is given once. In LAN the deque is
consumed only when the assist feeds the player (FINALOUT, never for our own player, v418, and never for the
last two), so the host gave the reward every frame (~14/s), and cave_push broadcast each item: the fire.
REWARDONCE: the call at 0x116B810 goes through a cave that gives the reward at most once per player number per
final: RObox u32 mask (bit = player no 0..31; numbers >= 32 are given as stock), u32 gives, u32 skips.
The assist clears the box at every final reset (FinalReset).

Stock: 0x116B810 bl #0x15aa020 (x0 = MapItemMan, x1 -> u32 player no, w2 = reward kind; result unused).
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'rewardonce_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []


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


SITE, GIVE = 0x116B810, 0x15AA020
stock(SITE, 'bl #0x15aa020')
stock(SITE - 8, 'mov x1, x21')
stock(SITE - 4, 'mov w2, w20')
stock(SITE + 4, 'add x21, x21, #4')
stock(GIVE, 'pacibsp')
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(SITE, SITE + 4)), 'site taken'
listing.append('0x116B810 stays a bl (x30 = 0x116B814); the trampoline uses x16 (IP0, dead at a call); the cave '
               'uses x9-x12 (caller-saved at a call) and tail-calls 0x15AA020 with x0/x1/w2/x30 unchanged; '
               'its result is not read (0x116B814 add x21)')


def find_pad(site, n, taken):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if any(t <= a < t + 4 * n or a <= t < a + 4 * n for t in taken):
            continue
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


def lsrv_w(rd, rn, rm): return 0x1AC02400 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
def lslv_w(rd, rn, rm): return 0x1AC02000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
def orr_w(rd, rn, rm): return 0x2A000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


g = C.Gen('rewardonce_gen', out=OUT, dry=DRY)
BOX = g.alloc('ROBOX', 'FAR_DATA', 0x10, 'REWARDONCE {u32 given mask, u32 gives, u32 skips, u32} (alpha 13)', align=8)
SIZE = 22
T = g.alloc('REWARDONCE', 'FAR_CODE', SIZE * 4, 'REWARDONCE (alpha 13 fire fix)')
taken = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C, 0x3F7DC54, 0x10EFF34, 0x19AEE68, 0x1076E0C,
         0x1074EE4, 0x1077814, 0x1077DEC, 0x1CCA130, 0x1524888, 0x15177C4]
pad = find_pad(SITE, 3, taken)
assert pad

a = C.Asm(T)
a(C.ldr_w('w9', 'x1'))                          # player no
a(C.cmp_wi('w9', 32))
a(C.to(C.bhs, 'give'))                          # >= 32 (or -1): stock
a.many(lambda pc, L: [C.adr(pc, 'x10', BOX)])
a(C.ldr_w('w11', 'x10'))
a(lsrv_w('w12', 'w11', 'w9'))
a(C.to(C.tbnz, 'w12', 0, 'skip'))               # already given in this final
a(C.movz_w('w12', 1))
a(lslv_w('w12', 'w12', 'w9'))
a(orr_w('w11', 'w11', 'w12'))
a(C.str_w('w11', 'x10'))
a(C.ldr_w('w12', 'x10', 4))
a(C.add_wi('w12', 'w12', 1))
a(C.str_w('w12', 'x10', 4))
a.label('give')
a.many(lambda pc, L: C.far_jump(pc, GIVE))     # tail call, x30 = 0x116B814
a.label('skip')
a(C.ldr_w('w12', 'x10', 8))
a(C.add_wi('w12', 'w12', 1))
a(C.str_w('w12', 'x10', 8))
a(C.RET)
w = a.words()
assert len(w) <= SIZE, len(w)
assert 0 not in w

recs = g.cave('REWARDONCE', T, a)
recs += [g.text_patch(pad + 4 * j, 'udf #0', x, 'trampoline 0x%X -> REWARDONCE 0x%X' % (SITE, T))
         for j, x in enumerate(C.far_jump(pad, T))]
groups = {'REWARDONCE_CAVE': recs, 'REWARDONCE': [g.text_patch(SITE, 'bl #0x15aa020', C.bl(SITE, pad), 'REWARDONCE')]}
order = ['REWARDONCE_CAVE', 'REWARDONCE']
listing.append('REWARDONCE: site 0x%X -> bl trampoline 0x%X (after `%s`) -> cave 0x%X (%d words), box 0x%X' % (
    SITE, pad, dis(pad - 4), T, len(w), BOX))
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word %08X' % C.bl(SITE, pad))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
