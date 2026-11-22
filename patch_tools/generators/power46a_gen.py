"""power46a_gen.py: POWER46A, alpha reconstruction (alpha_reconstructions.md b). Writes power46a_live.py.
python power46a_gen.py [--dry]      (from diag/net)

RECONSTRUCTED, not the real data: the network test's server sent the intermission Power options (0x6B); the shipped
SkillParam has weight 0 in all 121 rows for every round and the roll passes only for the bottom rank tier at 30 %
(power_offer2_notes 1). This is the withdrawn POWER_OFFER4, revived for alpha: every pool entry weight 1 (uniform
over the SkillParam rows: no weight data exists, so no row is favoured), and the slot roll always passes (every
player is offered up to 3 options at each intermission, as a server-fed list would be). Text words only, the
generator's own functions (callers asserted). Offline (Bot Match) is affected too: alpha only."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'power46a_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def callers(target):
    out = []
    for i, w in enumerate(W):
        if (w & 0xFC000000) == 0x94000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == target:
                out.append(4 * i)
    return out


assert callers(0x1019340) == [0x100E18C]
assert callers(0x100E100) == [0x100C088]
assert callers(0x1014940) == [0x100EFBC]
assert callers(0x10153A0) == [0x1014C98]
for a, t in ((0x1019394, 'sub w22, w9, #2'), (0x1019460, 'ldp w8, w9, [x9, #0x80]'),
             (0x10194A4, 'orr w25, w10, #0x10000'), (0x10154F0, 'ldr h0, [x8, #4]'), (0x1015524, 'fcmp s0, #0.0'),
             (0x1012614, 'cmp w21, w8'), (0x101261C, 'strb w8, [x27]'), (0x1012DC4, 'ldrb w0, [x8, #0x3d]'),
             (0x1012618, 'cset w8, hi'), (0x1019468, 'ldrh w8, [x24, x22, lsl #1]'),
             (0x10194A0, 'ldrh w10, [x24, x22, lsl #1]')):
    stock(a, t)

g = C.Gen('power46a_gen', out=OUT, dry=True)
recs = [g.text_patch(0x1012618, 'cset w8, hi', C.movz_w(8, 1), 'POWER46A: the slot roll always passes (reconstructed)'),
        g.text_patch(0x1019468, 'ldrh w8, [x24, x22, lsl #1]', C.movz_w(8, 1),
                     'POWER46A: existing pool entry weight 1 (reconstructed)'),
        g.text_patch(0x10194A0, 'ldrh w10, [x24, x22, lsl #1]', C.movz_w(10, 1),
                     'POWER46A: new pool entry weight 1 (reconstructed)')]
print(chr(10).join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, {'POWER46A': recs}, ['POWER46A'], __doc__.split('RECONSTRUCTED')[0].strip())
