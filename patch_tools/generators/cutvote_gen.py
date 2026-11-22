"""cutvote_gen.py: road_to_100 row 55, cutscene skip by vote (cutscene_vote_notes.md). Static generator: reads
nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes cutvote_live.py.
python cutvote_gen.py [--dry]

Group
  CUTSCENE_VOTE (2 text words, every game, no cave):
    0x11B932C  shipped CUTSCENE `b 0x11B94B8` (skip at once, also online) -> the stock `b.ne 0x11B94B8`:
               offline (mode != 6) a press still skips at once, as stock.
    0x11B9330  `ldr w8, [x19]` (the start of the online send of 0x25 kind 0 to the server) -> `b 0x11B94BC`:
               online the press only records the vote (entry+5 = 1, already stored at 0x11B930C) and returns.
               The assist (assist_v430_cutvote.diff) tells the others, counts the votes and sets entry+4 = 1
               (skip) on every game once all players voted, with entry+6 / +7 = count / total as kind 1 did.
  Solo cutscenes (w2 bit0 = 0) take `tbz w20, #0, 0x11B94B8` before both words: unchanged, skip at once."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'cutvote_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


for a, t in ((0x11B9280, 'pacibsp'), (0x11B930C, 'strb w9, [x8, #5]'), (0x11B9310, 'tbz w20, #0, #0x11b94b8'),
             (0x11B9324, 'ldr w10, [x10, #0x1268]'), (0x11B9328, 'cmp w10, #6'),
             (0x11B932C, 'b.ne #0x11b94b8'), (0x11B9330, 'ldr w8, [x19]'),
             (0x11B94B8, 'strb w9, [x8, #4]'), (0x11B94BC, 'ldp x20, x19, [sp, #0xf0]'), (0x11B94CC, 'retab'),
             (0x1B814E0, 'bl #0x11b9280')):
    stock(a, t)
assert C.shipped_word(0x11B932C) == 0x14000063, 'shipped CUTSCENE word changed'
listing.append('[V] shipped CUTSCENE 0x11B932C = b 0x11B94B8 (skip at once in every mode)')
listing.append('[V] 0x11B94BC.. is the plain epilogue (no stack use between 0x11B9330 and it)')


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            t = pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:
            imm = (w >> 5) & 0x7FFFF
            t = pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
        elif (w & 0x7E000000) == 0x36000000:
            imm = (w >> 5) & 0x3FFF
            t = pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


assert targets_in(0x11B9330, 0x11B9334) == [], 'branch into 0x11B9330'
listing.append('[V] no branch targets 0x11B9330 (reached only from 0x11B932C falling through, mode 6)')

# smallgaps2_live.py CUTSCENE_SKIP_ALL and fair_live.py CUTSCENE_REVERT are unbuilt drafts of the same words
# (superseded by this group: never apply them with it)
# census_live.py CUTSCENE is the source of the shipped record at 0x11B932C (this group updates it)
others = C.live_records(exclude=(OUT, 'smallgaps2_live.py', 'fair_live.py'))
for i in range(4):
    if 'census_live' in str(others.get(0x11B932C + i, '')):
        del others[0x11B932C + i]
for x in (0x11B932C, 0x11B9330):
    assert not any(x + i in others for i in range(4)), '%x taken: %s' % (x, others.get(x))
assert not any(0x11B9330 + i in C.SHIPPED for i in range(4))

g = C.Gen('cutvote_gen', out=OUT, dry=True)
g.others = others
# 0x11B932C: the shipped record goes back to the stock word (orig stock, new stock: bake = UPDATE of CUTSCENE)
rec_mode = (0x11B932C, C.hexw(C.text_word(0x11B932C)), C.hexw(C.text_word(0x11B932C)), True)
listing.append('  0x11b932c  (shipped) b #0x11b94b8  ->  b.ne #0x11b94b8   stock again: offline skips at once')
rec_vote = g.text_patch(0x11B9330, 'ldr w8, [x19]', C.b(0x11B9330, 0x11B94BC),
                        'CUTSCENE_VOTE: online the press records the vote only (assist counts)')
groups = {'CUTSCENE_VOTE': [rec_mode, rec_vote]}
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, ['CUTSCENE_VOTE'], __doc__.split('Group')[0].strip())
