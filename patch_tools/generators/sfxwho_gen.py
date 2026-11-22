"""sfxwho_gen.py: SFXWHO + CREATEWHO + RECVWHO (alpha 13d DIAGNOSTIC, on alpha 12). Static generator, Gen(dry=True): rows printed,
cave_registry.md not written. Writes sfxwho_live.py. python sfxwho_gen.py [--dry]   (from diag/net)
Logging only: at the entry of the single-SFX request push 0x1D4A060 (x0 = request pool, x1 -> u32 effect id; it
builds the 0xD8 CSFD4SingleSfxIns wrapper via 0x1D4291C), when the id is 10004 it counts and records x30 and six
frame-chain return addresses in a 4-entry ring. CREATEWHO: at the entry of the authority's attached-item create 0x15A3D08
(its local insert is the built-in cave_push broadcast of subtype 4) keeps x30 + 6 frame returns (2-entry ring).
RECVWHO: in the 0x1E reader right after the receive 0x1CD8260 (0x15973C0), for subtype-4 messages keeps the sender
word [sp+0x340] and the first 0x20 bytes of the message [sp+0x350] (4-entry ring). No other effect.

Stock: 0x1D4A060 pacibsp; sub sp, sp, #0x50; ... 77 callers (bl).
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'sfxwho_live.py'
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




SITE, BACK, ID = 0x1D4A060, 0x1D4A064, 10004
CSITE, CBACK = 0x15A3D08, 0x15A3D0C
RSITE, RBACK = 0x15973C0, 0x15973C4
stock(SITE, 'pacibsp')
stock(BACK, 'sub sp, sp, #0x50')
stock(0x1D4A118, 'ldr w8, [x22]')
stock(CSITE, 'pacibsp')
stock(CBACK, 'sub sp, sp, #0x1e0')
stock(0x15973B8, 'bl #0x1cd8260')
stock(0x15973BC, 'cbz w0, #0x1598a8c')
stock(RSITE, 'ldrh w8, [sp, #0x350]')
stock(RBACK, 'cmp w8, #1')
stock(0x15973D0, 'ldrh w9, [sp, #0x352]')
others = C.live_records(exclude=(OUT,))
for a0 in (SITE, CSITE, RSITE):
    assert not any(x in C.SHIPPED or x in others for x in range(a0, a0 + 4)), 'site taken %x' % a0
for a0 in (SITE, CSITE):
    assert not targets_in(a0 + 4, a0 + 8), 'branches to the word after %x' % a0
assert not targets_in(RSITE, RSITE + 4), 'branches into 0x15973C0'
listing.append('function entries: x9-x17 dead (AAPCS temporaries). 0x15973C0: right after `bl 0x1cd8260` + `cbz w0`; '
               'only x8 (reloaded by the replaced word), x16, x17 are used; w0 (length, read at 0x1597410) kept; '
               'flags are set again by `cmp w8, #1` at 0x15973C4')


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




def and_x_0xf(rd, rn):  # and xd, xn, #0xf
    return 0x92400C00 | (C.R(rn) << 5) | C.R(rd)


def and_w_3(rd, rn):  # and wd, wn, #3
    return 0x12000400 | (C.R(rn) << 5) | C.R(rd)


def and_w_0xf(rd, rn):  # and wd, wn, #0xf
    return 0x12000C00 | (C.R(rn) << 5) | C.R(rd)



g = C.Gen('sfxwho_gen', out=OUT, dry=True)
BOX = g.alloc('SWBOX', 'FAR_DATA', 0xE8, 'SFXWHO ring (alpha 13d)', align=8)
CBOX = g.alloc('CWBOX', 'FAR_DATA', 0x78, 'CREATEWHO ring (alpha 13d)', align=8)
RBOX = g.alloc('RWBOX', 'FAR_DATA', 0xA8, 'RECVWHO ring (alpha 13d)', align=8)
SIZE, CSIZE, RSIZE = 48, 44, 24
T = g.alloc('SFXWHO', 'FAR_CODE', SIZE * 4, 'SFXWHO (alpha 13d)')
CT = g.alloc('CREATEWHO', 'FAR_CODE', CSIZE * 4, 'CREATEWHO (alpha 13d)')
RT = g.alloc('RECVWHO', 'FAR_CODE', RSIZE * 4, 'RECVWHO (alpha 13d)')
taken = [0x3F7BB74, 0x3F7A1F0, 0x3F7A4E4, 0x3F7AB2C, 0x3F7D98C, 0x3F7DC54, 0x10EFF34, 0x19AEE68, 0x1076E0C,
         0x1074EE4, 0x1077814, 0x1077DEC]
pad = find_pad(SITE, 3, taken)
cpad = find_pad(CSITE, 3, taken + [pad])
rpad = find_pad(RSITE, 3, taken + [pad, cpad])
assert pad and cpad and rpad and len({pad, cpad, rpad}) == 3


def chain_cave(at, box, entries, back, id_filter=None):
    a = C.Asm(at)
    if id_filter is not None:
        a(C.ldr_w('w9', 'x1'))
        a(C.movz_w('w10', id_filter))
        a(0x4B000000 | (10 << 16) | (9 << 5) | 9)       # sub w9, w9, w10
        a(C.to(C.cbnz_w, 'w9', 'out'))
    a.many(lambda pc, L: [C.adr(pc, 'x10', box)])
    a(C.ldr_w('w11', 'x10'))
    a(C.add_wi('w12', 'w11', 1))
    a(C.str_w('w12', 'x10'))
    a(and_w_3('w11', 'w11') if entries == 4 else 0x12000000 | (11 << 5) | 11)   # and w11, w11, #3 / #1
    a(C.movz_w('w14', 0x38))
    a(0x9BA00000 | (14 << 16) | (10 << 10) | (11 << 5) | 13)   # umaddl x13, w11, w14, x10
    a(C.str_x('x30', 'x13', 8))
    a(C.mov_x('x14', 'x29'))
    for k in range(6):
        a(C.to(C.cbz_x, 'x14', 'out'))
        a(and_x_0xf('x15', 'x14'))              # a frame pointer is 16-aligned; anything else ends the walk
        a(C.to(C.cbnz_x, 'x15', 'out'))
        a(C.ldp_x('x14', 'x15', 'x14'))         # x14 = next frame, x15 = its return address
        a(C.str_x('x15', 'x13', 16 + 8 * k))
    a.label('out')
    a(PACIBSP)                                  # the replaced word
    a.many(lambda pc, L: C.far_jump(pc, back))
    return a


a = chain_cave(T, BOX, 4, BACK, ID)
c = chain_cave(CT, CBOX, 2, CBACK)
r = C.Asm(RT)
r(C.ldrh('w8', 'sp', 0x352))
r(C.sub_wi('w8', 'w8', 4))
r(C.to(C.cbnz_w, 'w8', 'out'))
r.many(lambda pc, L: [C.adr(pc, 'x16', RBOX)])
r(C.ldr_w('w17', 'x16'))
r(C.add_wi('w8', 'w17', 1))
r(C.str_w('w8', 'x16'))
r(and_w_3('w17', 'w17'))
r(0x8B000000 | (17 << 16) | (5 << 10) | (16 << 5) | 16)    # add x16, x16, x17, lsl #5
r(0x8B000000 | (17 << 16) | (3 << 10) | (16 << 5) | 16)    # add x16, x16, x17, lsl #3   (x16 = box + i * 0x28)
r(C.ldr_x('x8', 'sp', 0x340))
r(C.str_x('x8', 'x16', 8))
for k in range(4):
    r(C.ldr_x('x8', 'sp', 0x350 + 8 * k))
    r(C.str_x('x8', 'x16', 0x10 + 8 * k))
r.label('out')
r(C.ldrh('w8', 'sp', 0x350))                    # the replaced word
r.many(lambda pc, L: C.far_jump(pc, RBACK))
for name, asm, size in (('SFXWHO', a, SIZE), ('CREATEWHO', c, CSIZE), ('RECVWHO', r, RSIZE)):
    w = asm.words()
    assert len(w) <= size, (name, len(w))
    assert 0 not in w

groups, order, rows = {}, [], []
for name, at, asm, site, site_text, p, box, boxsize, boxtag, size, what in (
        ('SFXWHO', T, a, SITE, 'pacibsp', pad, BOX, 0xE8, 'SWBOX', SIZE,
         'who requests single SFX 10004, 7 frames'),
        ('CREATEWHO', CT, c, CSITE, 'pacibsp', cpad, CBOX, 0x78, 'CWBOX', CSIZE,
         'who calls the attached-item create 0x15A3D08 (cave_push sender), 7 frames'),
        ('RECVWHO', RT, r, RSITE, 'ldrh w8, [sp, #0x350]', rpad, RBOX, 0xA8, 'RWBOX', RSIZE,
         'sender + head of each 0x1E subtype-4 message')):
    recs = g.cave(name, at, asm)
    recs += [g.text_patch(p + 4 * j, 'udf #0', w, 'trampoline 0x%X -> %s 0x%X' % (site, name, at))
             for j, w in enumerate(C.far_jump(p, at))]
    groups[name + '_CAVE'] = recs
    groups[name] = [g.text_patch(site, site_text, C.b(site, p), name)]
    order += [name + '_CAVE', name]
    listing.append('%s: site 0x%X -> trampoline 0x%X (after `%s`) -> cave 0x%X (%d words)' % (
        name, site, p, dis(p - 4), at, len(asm.words())))
    rows.append('| sfxwho_gen | %s | 0x%X..0x%X | %s ring (FAR_DATA, alpha 13d diagnostic) |' % (
        boxtag, box, box + boxsize, name))
    rows.append('| sfxwho_gen | %s | 0x%X..0x%X | %s 0x%X (diagnostic, alpha 13d): %s; trampoline 0x%X..0x%X |' % (
        name, at, at + size * 4, name, site, what, p, p + 12))
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows:')
print(chr(10).join(rows))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Stock:')[0].strip())
