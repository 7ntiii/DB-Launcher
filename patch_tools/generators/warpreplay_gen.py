"""warpreplay_gen.py: WARPREPLAY (v4.51, on alpha 11 WARPDEFER). Static generator, Gen(dry=True): rows printed,
cave_registry.md not written. Writes warpreplay_live.py. python warpreplay_gen.py [--dry]   (from diag/net)

Stock: see warpdefer_gen.py. WARPDEFER moves only our own warp to the pump (phase 26); the copies of the other players
are still warped at the list apply (0x10F3F00 -> 0x10EFDAC -> chr vt+0x7F0), mid-load. WARPREPLAY makes the deferred
warp re-run the whole placement once, so copies and our player are placed in one frame again (as stock), after load."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'warpreplay_live.py'
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



# WARPREPLAY: at the pump's deferred local warp (0x10EF86C `strb wzr, [x19, #0x6a8]`, reached only when M+0x6A8 and
# the warp-now byte are set), when WDBOX+1 (replay, set by the assist with hold) is set: clear it, count it
# (WDBOX+12) and run the whole stock placement 0x10F3F00(mediator) once - every listed copy warped again
# (0x10EFDAC -> chr vt+0x7F0) and our own player warped in the same frame, as the stock apply did in one frame -
# then skip the pump's own local warp (b 0x10EF8FC). Otherwise the replaced word and back to 0x10EF870.
SITE, BACK, SKIP, PLACE = 0x10EF86C, 0x10EF870, 0x10EF8FC, 0x10F3F00
WDBOX = 0xC50FD90
stock(0x10EF868, 'cbz w8, #0x10ef8fc')
stock(SITE, 'strb wzr, [x19, #0x6a8]')
stock(BACK, 'adrp x8, #0x59df000')
stock(SKIP, 'ldrb w8, [x20, #0x10]')
stock(0x10EFCDC, 'mov x0, x19')
stock(0x10EFCE0, 'bl #0x10f3f00')
others = C.live_records(exclude=(OUT,))
assert not any(x in C.SHIPPED or x in others for x in range(SITE, SITE + 4)), 'site taken'
assert not targets_in(SITE, SITE + 4), 'branches into the site'
assert any(r['tag'] == 'WDBOX' and r['lo'] == WDBOX for r in C.read_registry()), 'WDBOX not registered'
listing.append('x19 = mediator (callee-saved, kept by 0x10F3F00); x0-x17 are dead here (the next words reload x8 / x1); '
               'after the call the pump goes on at 0x10EF8FC as after its own warp')


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


g = C.Gen('warpreplay_gen', out=OUT, dry=True)
SIZE = 20
T = g.alloc('WARPREPLAY', 'FAR_CODE', SIZE * 4, 'WARPREPLAY 0x10EF86C: the deferred local warp re-runs the whole '
            'placement 0x10F3F00 once (copies + our player)')
taken = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C, 0x3F7DC54, 0x10EFF34, 0x19AEE68, 0x1076E0C,
         0x1074EE4, 0x1077814]
pad = find_pad(SITE, 3, taken)
assert pad

a = C.Asm(T)
a(0x3900027F | (0x6A8 << 10))              # strb wzr, [x19, #0x6a8] (the replaced word)
a.many(lambda pc, L: [C.adr(pc, 'x10', WDBOX)])
a(C.ldrb('w11', 'x10', 1))
a(C.to(C.cbz_w, 'w11', 'stock'))
a(C.strb('wzr', 'x10', 1))                 # once per final
a(C.ldr_w('w11', 'x10', 12))
a(C.add_wi('w11', 'w11', 1))
a(C.str_w('w11', 'x10', 12))
a(C.mov_x('x0', 'x19'))
a.many(lambda pc, L: [C.adr(pc, 'x30', L['after'])])
a.many(lambda pc, L: C.far_jump(pc, PLACE))
a.label('after')
a.many(lambda pc, L: C.far_jump(pc, SKIP))
a.label('stock')
a.many(lambda pc, L: C.far_jump(pc, BACK))
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words
assert C.dis1(T, words[0]) == 'strb wzr, [x19, #0x6a8]', C.dis1(T, words[0])
for i, w in enumerate(words):
    listing.append('  %X: %s' % (T + 4 * i, C.dis1(T + 4 * i, w)))
cave_recs = g.cave('WARPREPLAY', T, a)
cave_recs += [g.text_patch(pad + 4 * j, 'udf #0', w, 'trampoline 0x%X -> WARPREPLAY 0x%X' % (SITE, T))
              for j, w in enumerate(C.far_jump(pad, T))]
hook_recs = [g.text_patch(SITE, 'strb wzr, [x19, #0x6a8]', C.b(SITE, pad), 'WARPREPLAY')]
listing.append('site 0x%X -> trampoline 0x%X..0x%X (after `%s`) -> cave 0x%X..0x%X' % (SITE, pad, pad + 12,
                                                                                       dis(pad - 4), T, T + SIZE * 4))
rows = ['| warpreplay_gen | WARPREPLAY | 0x%X..0x%X | WARPREPLAY 0x10EF86C: the deferred local warp re-runs the '
        'placement 0x10F3F00 once (WDBOX+1 replay, +12 count); trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, pad,
                                                                                            pad + 12)]
groups = {'WARPREPLAY_CAVE': cave_recs, 'WARPREPLAY': hook_recs}
order = ['WARPREPLAY_CAVE', 'WARPREPLAY']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows:')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
