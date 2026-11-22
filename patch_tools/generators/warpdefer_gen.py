"""warpdefer_gen.py: WARPDEFER (v4.50, alpha 11): hold the guest's own start-point warp until the final's world is
loaded. Static generator, Gen(dry=True): cave_registry.md is NOT written (rows printed). Writes warpdefer_live.py.
python warpdefer_gen.py [--dry]      (from diag/net)

Stock: the local player's warp to its start point has two gates, both on the battle flow's "warp now" byte
stage(0x5B3CDF8)+0x4728 (written every frame at 0x182993C):
  - the list apply 0x10F3F00, for our own entry: 0x10F4060 `ldrb w8, [x8, x9]` (x9 = 0x4728); set -> warp at once
    (b 0x10F3F60 -> 0x10EFDAC), clear -> M+0x6A8 = 1 (deferred);
  - the mediator pump: 0x10EF864 `ldrb w8, [x8, x9]`; M+0x6A8 and set -> clear M+0x6A8 and warp (0x10EFDAC).
On a guest in the final the byte is already 1 in phase 21, so the apply warps our player mid-load (alpha 9 log).
WARPDEFER: while WDBOX.hold (u8, set by the assist on a guest in the final from phase 21 until its first
Intermission tick), both loads read 0 instead: the apply defers (M+0x6A8) and the pump waits; once the assist
clears hold, the pump warps on its next frame (phase 26), as in the single-entry finals. WDBOX+4 u32 counts the
apply-gate reads that were held, WDBOX+8 u32 the pump-gate reads that were held. hold 0: stock."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'warpdefer_live.py'
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


APPLY_SITE, PUMP_SITE = 0x10F4060, 0x10EF864
stock(0x10F405C, 'mov w9, #0x4728')
stock(APPLY_SITE, 'ldrb w8, [x8, x9]')
stock(0x10F4064, 'cbnz w8, #0x10f3f60')
stock(0x10F406C, 'strb w8, [x19, #0x6a8]')
stock(0x10EF860, 'mov w9, #0x4728')
stock(PUMP_SITE, 'ldrb w8, [x8, x9]')
stock(0x10EF868, 'cbz w8, #0x10ef8fc')
stock(0x10EF86C, 'strb wzr, [x19, #0x6a8]')
others = C.live_records(exclude=(OUT,))
for site in (APPLY_SITE, PUMP_SITE):
    assert not any(x in C.SHIPPED or x in others for x in range(site, site + 4)), 'site %x taken' % site
    assert not targets_in(site, site + 4), 'branches into %x' % site
listing.append('x10 and x16 are dead at both sites (0x10F3F00: x10 last used at 0x10F3F3C; pump: x10 next written '
               'at 0x10EF8A0); x8/x9 hold stage / 0x4728 as in stock; the flags are set by the next cbz/cbnz')


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


g = C.Gen('warpdefer_gen', out=OUT, dry=True)
PLANNED = [('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0), ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)]
for owner, tag, lo, hi in PLANNED:  # not baked yet: keep them free
    if not any(r['tag'] == tag for r in g._rows()):
        g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
BOX = g.alloc('WDBOX', 'FAR_DATA', 16, 'WARPDEFER {u8 hold, u8[3], u32 apply holds, u32 pump holds, u32} (FAR_DATA)',
              align=8)
SIZE = 2 * 12
T = g.alloc('WARPDEFER', 'FAR_CODE', SIZE * 4, 'WARPDEFER 0x10F4060 / 0x10EF864: the warp-now byte reads 0 while '
            'WDBOX.hold (guest, final load)')
taken = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C, 0x3F7DC54, 0x10EFF34, 0x19AEE68, 0x1076E0C]
pads = []
for site in (APPLY_SITE, PUMP_SITE):
    p = find_pad(site, 3, taken + pads)
    assert p
    pads.append(p)


def gate(a, site, counter):
    """At a: load the box, hold -> w8 = 0 (and count), else the stock ldrb; back to site+4."""
    a.many(lambda pc, L: [C.adr(pc, 'x10', BOX)])
    a(C.ldrb('w16', 'x10', 0))
    a(C.to(C.cbz_w, 'w16', 'real%x' % site))
    a(C.ldr_w('w16', 'x10', counter))
    a(C.add_wi('w16', 'w16', 1))
    a(C.str_w('w16', 'x10', counter))
    a(C.movz_w('w8', 0))
    a(lambda pc, L: C.b(pc, L['back%x' % site]))
    a.label('real%x' % site)
    a(0x38696908)                            # ldrb w8, [x8, x9] (the replaced word)
    a.label('back%x' % site)
    a.many(lambda pc, L: C.far_jump(pc, site + 4))


a = C.Asm(T)
a.label('apply')
gate(a, APPLY_SITE, 4)
a.label('pump')
gate(a, PUMP_SITE, 8)
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words
assert C.dis1(0, 0x38696908) == 'ldrb w8, [x8, x9]'
assert C.text_word(APPLY_SITE) == 0x38696908 and C.text_word(PUMP_SITE) == 0x38696908
for i, w in enumerate(words):
    listing.append('  %X: %s' % (T + 4 * i, C.dis1(T + 4 * i, w)))
entry = {APPLY_SITE: a.labels['apply'], PUMP_SITE: a.labels['pump']}

cave_recs = g.cave('WARPDEFER', T, a)
hook_recs = []
for site, pad in zip((APPLY_SITE, PUMP_SITE), pads):
    cave_recs += [g.text_patch(pad + 4 * j, 'udf #0', w, 'trampoline 0x%X -> WARPDEFER 0x%X' % (site, entry[site]))
                  for j, w in enumerate(C.far_jump(pad, entry[site]))]
    hook_recs.append(g.text_patch(site, 'ldrb w8, [x8, x9]', C.b(site, pad), 'WARPDEFER'))
    listing.append('site 0x%X -> trampoline 0x%X..0x%X (after `%s`) -> cave 0x%X' % (site, pad, pad + 12,
                                                                                      dis(pad - 4), entry[site]))
listing.append('WDBOX 0x%X, cave 0x%X..0x%X' % (BOX, T, T + SIZE * 4))
rows = [
    '| warpdefer_gen | WDBOX | 0x%X..0x%X | WARPDEFER {u8 hold, u8[3], u32 apply holds, u32 pump holds, u32} '
    '(FAR_DATA) |' % (BOX, BOX + 16),
    '| warpdefer_gen | WARPDEFER | 0x%X..0x%X | WARPDEFER 0x10F4060 / 0x10EF864: warp-now byte reads 0 while '
    'WDBOX.hold; trampolines 0x%X..0x%X, 0x%X..0x%X |' % (T, T + SIZE * 4, pads[0], pads[0] + 12, pads[1],
                                                          pads[1] + 12),
]

groups = {'WARPDEFER_CAVE': cave_recs, 'WARPDEFER': hook_recs}
order = ['WARPDEFER_CAVE', 'WARPDEFER']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows:')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
