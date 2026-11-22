"""treasure_gen.py: map treasures made by the LAN host, and blood crystals awarded on the killer's own game (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. No cave, no registry claim.
python treasure_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: treasure_notes.md.

Groups (plain text words, no caves)
  TREASURE_HOST  three words in the treasure maker 0xC2CEE0 (stage step 0x114F2C0 -> per-block functor 0x115DC10):
     0xC2D04C..0xC2D054 load the ROLE byte main+0x492AFD8 (assist: 0 host, 1 guest; 0 offline) instead of the
     offline byte, and flip it (eor #1), so the stock `cbz w8, #0xc2d130` at 0xC2D058 (left alone: STARFRAG_V2 owns
     that word) skips only on guests. The host (and offline) then runs the stock create: 0x15AB6D0 -> 0x159C6C4
     (built-in I3 host-only) -> I4b push -> one id on every game. 217 MSB treasures (m10_00_00_00), 195 of them
     ordinary consumable loot (AEG105_210), 12 Star Fragment sites (AEG099_211), 10 AEG099_212.
     EXCLUSIVE_WITH STARFRAG_V2 (advisory: bytes do not overlap and its cave reads w8 != 0 as "create", but both
     together would make the drawn fragment twice: once at the step, once at the crash).
  CRYSTAL_LOCAL  WITHDRAWN 2026-11-15 (pickup2_notes.md 3: built-in I1 0x15B056C already broadcasts subtype 14, the
     host serves it; on a guest I3 blocks the crystal item create at 0x15B37E4). Kept only for the record. One word: 0x15B0528 `cbz w8, #0x15b054c` -> nop. The Bloodsac kill award (0x174F164 ->
     0x15B01A8 -> 0x15B02A8, killer's own game only) then calls 0x15B33A4 -> 0xCFE9A8 directly (the offline branch)
     instead of sending 0x1E subtype 14 to the server member, which a guest's reader drops (routing table entry 14
     online byte 0) and the host may run for the wrong pgd."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'treasure_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
ROLE = 0x492AFD8
EOR_W8_1 = 0x52000108


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def fn_start(a):
    while W[a // 4] != PACIBSP:
        a -= 4
    return a


def bl_callers(target):
    out = []
    for i, w in enumerate(W):
        if (w >> 26) in (0x25, 0x05):
            off = w & 0x3FFFFFF
            if off & 0x2000000:
                off -= 0x4000000
            if i * 4 + off * 4 == target:
                out.append(i * 4)
    return out


g = C.Gen('treasure_gen', out=OUT, dry=DRY)
listing = []

# ---------------------------------------------------------------- treasure maker [V]
for a, t in ((0xC2D030, 'tbz w8, #5, #0xc2d35c'), (0xC2D040, 'ldr x8, [x8, #0xb28]'), (0xC2D044, 'ldr x8, [x8]'),
             (0xC2D048, 'cbz x8, #0xc2d05c'), (0xC2D04C, 'adrp x8, #0x5b65000'),
             (0xC2D050, 'ldr x8, [x8, #0xc20]'), (0xC2D054, 'ldrb w8, [x8, #0xbda]'),
             (0xC2D058, 'cbz w8, #0xc2d130'), (0xC2D05C, 'ldr x23, [x24]')):
    stock(a, t)
assert fn_start(0xC2D058) == 0xC2CEE0
assert sorted(bl_callers(0xC2CEE0)) == [0xF27308, 0xF273A4, 0x115DC88, 0x157FD9C, 0x1581254], [
    hex(x) for x in bl_callers(0xC2CEE0)]
# the stage step reaches its per-block walk in LAN: the only offline test there (0x114F420) skips 0x15A1320 only
stock(0x114F41C, 'ldrb w8, [x8, #0xbda]'); stock(0x114F420, 'cbz w8, #0x114f438'); stock(0x114F424, 'bl #0x15a1320')
stock(0x114F598, 'bl #0xfb82a0')
# x8 is dead after the gate on both exits (0xC2D05C reads x24, 0xC2D130 must not read x8 before writing it)
for a in range(0xC2D130, 0xC2D150, 4):
    t = C.dis1(a, W[a // 4])
    if 'x8' in t or 'w8' in t:
        assert t.split()[1].rstrip(',') in ('x8', 'w8'), 'x8 read at %x: %s' % (a, t)
        break
assert C.dis1(0, EOR_W8_1) == 'eor w8, w8, #1'
w_adrp = C.adrp(0xC2D04C, 8, ROLE)
w_ldrb = C.ldrb(8, 8, ROLE & 0xFFF)
assert C.dis1(0xC2D04C, w_adrp) == 'adrp x8, #0x492a000' and C.dis1(0, w_ldrb) == 'ldrb w8, [x8, #0xfd8]'
treasure = [g.text_patch(0xC2D04C, 'adrp x8, #0x5b65000', w_adrp, 'role byte page'),
            g.text_patch(0xC2D050, 'ldr x8, [x8, #0xc20]', w_ldrb, 'w8 = role (0 host / offline, 1 guest)'),
            g.text_patch(0xC2D054, 'ldrb w8, [x8, #0xbda]', EOR_W8_1, 'w8 = 1 on host / offline, 0 on guests')]
others_c2d058 = g.others.get(0xC2D058)
listing.append('0xC2D058 stays `cbz w8` (stock) or STARFRAG_V2 `bl` (%s): both treat w8 != 0 as create' % others_c2d058)

# ---------------------------------------------------------------- Bloodsac crystal award [V]
stock(0x174F164, 'bl #0x15b01a8')
assert bl_callers(0x15B01A8) == [0x174F164] and bl_callers(0x15B02A8) == [0x15B0270]
stock(0x15B0270, 'b #0x15b02a8')
stock(0x15B025C, 'ldrb w8, [x8, #0x4ee]'); stock(0x15B0260, 'tbnz w8, #3, #0x15b0268')   # NpcParam +0x4EE bit 3
stock(0x15B0524, 'ldrb w8, [x8, #0xbda]'); stock(0x15B0528, 'cbz w8, #0x15b054c')
stock(0x15B0544, 'bl #0x15b33a4'); stock(0x15B0548, 'b #0x15b0574')
stock(0x15B0564, 'mov w1, #0x1e'); stock(0x15B0568, 'mov w3, #0x1c')
assert bl_callers(0xCFE9A8) == [0x15B0650, 0x15B3888] or sorted(bl_callers(0xCFE9A8)) == [0x15B0650, 0x15B3888]
# the killer-only gate of the kill reward 0x174EE44 (w1 = 0 path)
for a, t in ((0x17529E0, 'mov w1, wzr'), (0x17529E4, 'bl #0x174ee44'), (0x174EF40, 'cmp x8, x21'),
             (0x174EF44, 'b.eq #0x174efb0'), (0x174EF4C, 'bl #0x17ef704'), (0x174EF54, 'b #0x174f744')):
    stock(a, t)
# reader routing table: subtype 14 = {size 28, online byte 0}
_t = 0x4C4CC18 + 14 * 8
assert struct.unpack_from('<iB', C.RO, _t - C.RO_BASE) == (28, 0)
crystal = [g.text_patch(0x15B0528, 'cbz w8, #0x15b054c', C.NOP, 'crystal award: offline branch on the killer game')]

groups = {'TREASURE_HOST': treasure, 'CRYSTAL_LOCAL': crystal}
order = ['TREASURE_HOST', 'CRYSTAL_LOCAL']
for line in listing + g.listing:
    print(line)
if not DRY:
    doc = __doc__.split('\n\n')[0] + '\n\nGroups: TREASURE_HOST (3 words), CRYSTAL_LOCAL (1 word). Notes treasure_notes.md.'
    C.write_live(OUT, groups, order, doc)
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("EXCLUSIVE_WITH = {'TREASURE_HOST': ['STARFRAG_V2']}\n")
