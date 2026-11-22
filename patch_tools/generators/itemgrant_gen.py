"""itemgrant_gen.py: items the server granted directly (callers of the item add 0xCF8E2C that are refused in LAN).
Static only: reads nso/*.bin, the decoded gameparam (diag/scripts_decoded), optionally the live regulation
(read-only, informational), patch_manager.cpp, every *_live.py and zep3_gen.py (text only, not imported).
Writes itemgrant_live.py. Claims NO registry range and writes no code.      python itemgrant_gen.py   (from diag/net)
Notes: itemgrant_notes.md.

Result: all four groups are EMPTY on purpose. For each feature the generator proves (asserts) that the grant can
never fire in this build, with or without opening its own gate, because the DATA that would trigger or fill it
does not exist (no row of that kind / goods field -1). Opening a gate there would be untestable and would add
risk for nothing. If any of these data facts changes (other regulation), an assertion fails and names the
feature to re-judge (design for each is in itemgrant_notes.md).

  ITEMGRANT_EVENT   0xF0FBBC (ret 0xF0FC44), own gate 0xF0FC18: env-event TYPE 2 only (callers 0xF0E2A8 via the
                    type switch 0xF0DDA0 `cmp w8,#2`, and 0xF0FEDC/0xF10000 from 0xF0E2A8 / 0x8A handler 0xF0FA48
                    `cmp w8,#2`). EnvEventParam has no type-2 row; the goods field EnvEventTypeParam row 0 +0x15C = -1.
  ITEMGRANT_QUEST   0x119112C (ret 0x1191240) / 0x1191F40 (ret 0x11921DC), own gates 0x119114C / 0x1191F6C:
                    vtable of sub-quest logic TYPE 18 (factory case 18 only); no SubQuestParam row has type 18.
  ITEMGRANT_POWER   0xD49460 grant (ret 0xD4A2E8, gate 0xD4A2A8) / removal (ret 0xD4A6E4, gate 0xD4A694): goods
                    lists come only from SkillParam +0x60 (0xD4CA60); every SkillParam row has +0x60 = -1.
  ITEMGRANT_PICKUP  0x119FE54 (ret 0x119FFF4), own gate 0x119FE7C: asset 99500 is created only by the type-18 logic
                    0x119195C (the only two `mov #0x84ac; movk #1` in text) and has no MSB part; type 18 unused."""
import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'itemgrant_live.py'
OFFL = 0x5B65C20
ITEM_ADD = 0xCF8E2C
PARAMS = os.path.join(HERE, '..', 'scripts_decoded', 'param', 'gameparam', 'gameparam_nt.parambnd')
MSB_PARTS = os.path.join(HERE, '..', 'scripts_decoded', 'm10_00_00_00.msb.parts.txt')
listing = []
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def bl_callers(target):
    out = []
    for i, w in enumerate(W):
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == target:
                out.append((4 * i, 'bl' if w >> 31 else 'b'))
    return out


def fn_start(a):
    while W[a // 4] != 0xD503237F:
        a -= 4
    return a


def ptr_refs(target):
    p = struct.pack('<Q', target)
    hits = []
    for base, blob in ((C.RO_BASE, C.RO), (C.DATA_BASE, C.DATA)):
        i = blob.find(p)
        while i != -1:
            if i % 8 == 0:
                hits.append(base + i)
            i = blob.find(p, i + 1)
    return hits


def data_q(a):
    return struct.unpack_from('<Q', C.DATA, a - C.DATA_BASE)[0]


def got_loads(got):
    """Text addresses of `ldr xN, [xM, #lo]` paired with `adrp xM, page(got)` within 8 words before."""
    hits = []
    lo = got & 0xFFF
    for i, w in enumerate(W):
        if (w & 0xFFC00000) == 0xF9400000 and ((w >> 10) & 0xFFF) * 8 == lo:
            rn = (w >> 5) & 31
            for j in range(max(0, i - 8), i):
                x = W[j]
                if (x & 0x9F000000) == 0x90000000 and (x & 31) == rn:
                    imm = (((x >> 5) & 0x7FFFF) << 2) | ((x >> 29) & 3)
                    if imm & (1 << 20):
                        imm -= 1 << 21
                    if ((4 * j) & ~0xFFF) + (imm << 12) == got & ~0xFFF:
                        hits.append(4 * i)
                        break
    return hits


def param_rows(name, folder=PARAMS, blob=None):
    b = blob if blob is not None else open(os.path.join(folder, name), 'rb').read()
    n = struct.unpack_from('<H', b, 0xA)[0]
    return b, [struct.unpack_from('<ixxxxq', b, 0x40 + k * 24) for k in range(n)]


# ---------------------------------------------------------------- census: the six callers in scope [V]
CALLS = {   # call site -> (feature, own gate, stock gate text, function)
    0xF0FC40: ('EVENT', 0xF0FC18, 'cbz w8, #0xf0fe64', 0xF0FBBC),
    0x119123C: ('QUEST', 0x119114C, 'cbz w8, #0x1191240', 0x119112C),
    0x11921D8: ('QUEST', 0x1191F6C, 'cbz w8, #0x1192200', 0x1191F40),
    0xD4A2E4: ('POWER', 0xD4A2A8, 'cbz w9, #0xd4a328', 0xD49460),
    0xD4A6E0: ('POWER', 0xD4A694, 'cbz w9, #0xd4a5a0', 0xD49460),
    0x119FFF0: ('PICKUP', 0x119FE7C, 'cbz w8, #0x119fff4', 0x119FE54),
}
all_callers = [a for a, k in bl_callers(ITEM_ADD)]
assert len(all_callers) == 18 and all(k == 'bl' for a, k in bl_callers(ITEM_ADD)), 'callers of 0xCF8E2C changed'
others = C.live_records(exclude=(OUT,))
for site, (feat, gate, txt, fn) in CALLS.items():
    assert site in all_callers, '%x is no longer a caller' % site
    stock(site, 'bl #0xcf8e2c')
    stock(gate, txt)
    stock(gate - 4, 'ldrb w%s, [x%s, #0xbda]' % (txt.split()[1][1:-1], txt.split()[1][1:-1]))
    assert fn_start(site) == fn and fn_start(gate) == fn, 'gate / call not in %x' % fn
    for b_ in range(gate - 4, gate + 4):   # the gate and its flag load: nobody opens them today
        assert b_ not in C.SHIPPED and b_ not in others, '%s gate %x patched (%s): re-judge' % (
            feat, gate, others.get(b_, 'patch_manager.cpp'))
    listing.append('%-6s call 0x%X (ret 0x%X) in 0x%X, own gate 0x%X `%s` (stock, unpatched)' % (
        feat, site, site + 4, fn, gate, txt))
# none of the eight return offsets is in the ZEP3_C2 tables (nothing granted through 0xCF8F74 for them)
import zep3_live as Z  # noqa: E402  (data file)
_tab = {a: int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in Z.ZEP3_C2}
for tname in ('C2_TABLE', 'C2_LOCAL'):
    a, words = Z.CAVES[tname], []
    while _tab.get(a, 0):
        words.append(_tab[a])
        a += 4
    assert words and not set(words) & set(s + 4 for s in CALLS), 'zep3 %s holds one of these callers' % tname
    listing.append('zep3 %s = %s (none of the callers above)' % (tname, ', '.join('0x%X' % w for w in words)))

# ================================================================ EVENT [V]
# reward goods = 0x30000000 | (row field +0x15C & 0x0FFFFFFF); row = 0x155AC00 (row 0 of repo+0x36C0)
stock(0xF0FBE0, 'bl #0x155ac00'); stock(0xF0FBEC, 'ldr w8, [x8, #0x15c]'); stock(0xF0FBF0, 'and w21, w8, #0xfffffff')
stock(0xF0FC1C, 'orr w8, w21, #0x30000000')
stock(0xF1004C, 'ldr w8, [x8, #0x15c]')
assert sorted(a for a, k in bl_callers(0xF0FBBC)) == [0xF0E314, 0xF10168]
# 0xF0E314 lies in 0xF0E2A8, entered only from the env type switch 0xF0DDA0 on type byte 2
assert fn_start(0xF0E314) == 0xF0E2A8 and bl_callers(0xF0E2A8) == [(0xF0DDFC, 'b')]
for a, t in ((0xF0DDB4, 'ldrsb w8, [x0, #8]'), (0xF0DDC0, 'cmp w8, #2'), (0xF0DDC4, 'b.eq #0xf0ddec'),
             (0xF0DDFC, 'b #0xf0e2a8'), (0xF0DDC8, 'cmp w8, #0x26'), (0xF0DDD0, 'cmp w8, #0x1a')):
    stock(a, t)
assert not ptr_refs(0xF0E2A8) and not ptr_refs(0xF10000) and not ptr_refs(0xF0FEDC)
# 0xF10168 in 0xF10000, only from 0xF0FEDC, only from 0xF0E2A8 (type 2) and the 0x8A handler 0xF0FA48 (type 2)
assert fn_start(0xF10168) == 0xF10000 and bl_callers(0xF10000) == [(0xF0FF34, 'bl')]
assert sorted(bl_callers(0xF0FEDC)) == [(0xF0E418, 'b'), (0xF0FB7C, 'bl')]
assert fn_start(0xF0E418) == 0xF0E2A8 and fn_start(0xF0FB7C) == 0xF0FA48
stock(0xF0FA60, 'ldrb w8, [x0, #8]'); stock(0xF0FA64, 'cmp w8, #2'); stock(0xF0FA68, 'b.ne #0xf0fb80')
b, rs = param_rows('EnvEventParam.param')
env_types = [(rid, b[o + 0xF]) for rid, o in rs]
assert all(t != 2 for _, t in env_types), 'EnvEventParam has a type-2 row: re-judge ITEMGRANT_EVENT %s' % env_types
b, rs = param_rows('EnvEventTypeParam.param')
assert len(rs) == 1 and rs[0][0] == 0
ev_goods = struct.unpack_from('<i', b, rs[0][1] + 0x15C)[0]
assert struct.unpack_from('<i', b, rs[0][1] + 0x114)[0] == 4120     # same row: zeppelin Transmitter (sanity)
assert ev_goods == -1, 'env reward goods +0x15C = %d: re-judge ITEMGRANT_EVENT' % ev_goods
listing.append('EVENT: env types %s (no 2); reward goods EnvEventTypeParam[0]+0x15C = %d -> item 0x3FFFFFFF' % (
    [hex(t) for _, t in env_types], ev_goods))

# ================================================================ QUEST [V]
# factory 0x118915C: type byte = row byte +0 (0x1189264), jump table ro 0x4C49BCA (u16, base 0x11894FC), case 18
stock(0x1189264, 'ldrb w27, [x8]'); stock(0x11894C0, 'cmp w27, #0x14'); stock(0x11894F8, 'br x11')
stock(0x11894D0, 'adrp x10, #0x4c49000'); stock(0x11894D4, 'add x10, x10, #0xbca')
case18 = 0x11894FC + 4 * struct.unpack_from('<H', C.RO, 0x4C49BCA - C.RO_BASE + 2 * 18)[0]
assert case18 == 0x1189E74
stock(0x1189EA0, 'ldr x8, [x8, #0x488]')
assert got_loads(0x59E3488) == [0x1189EA0], 'type-18 class GOT used elsewhere: %s' % got_loads(0x59E3488)
assert data_q(0x59E3488) == 0x56F88A8 and ptr_refs(0x56F88A8) == [0x59E3488]
VT = 0x56F88B8
assert data_q(VT + 0x18) == 0x119112C and data_q(VT + 0xD0) == 0x1191F40 and data_q(VT + 0x70) == 0x119195C
for f, slot in ((0x119112C, VT + 0x18), (0x1191F40, VT + 0xD0), (0x119195C, VT + 0x70)):
    assert ptr_refs(f) == [slot] and not bl_callers(f), '%x reachable other than through type 18' % f
b, rs = param_rows('SubQuestParam.param')
sq_types = sorted(set(b[o] for _, o in rs))
assert 18 not in sq_types, 'SubQuestParam has a type-18 row: re-judge ITEMGRANT_QUEST / ITEMGRANT_PICKUP'
listing.append('QUEST: SubQuestParam types %s (no 18); type-18 class only in factory case 0x%X' % (sq_types, case18))

# ================================================================ PICKUP [V]
m = []
for i in range(len(W) - 6):
    w = W[i]
    if (w & 0x7FE00000) == 0x52800000 and ((w >> 5) & 0xFFFF) == 0x84AC:
        rd = w & 31
        if any((W[j] & 0x7FE00000) == 0x72A00000 and (W[j] & 31) == rd and ((W[j] >> 5) & 0xFFFF) == 1
               for j in range(i + 1, i + 6)):
            m.append(4 * i)
assert m == [0x11919C0, 0x1191C50] and all(fn_start(a) == 0x119195C for a in m), '99500 built elsewhere: %s' % m
assert struct.pack('<i', 99500) not in C.RO
assert ptr_refs(0x119FE54) == [0x56F9B60] and not bl_callers(0x119FE54)
# the award amount is 0x1191E3C(pgd) = the owner's count of the type-18 goods (row 0 +0x10 of 0x156686C)
stock(0x119FFA0, 'bl #0x1191e3c'); stock(0x119FF7C, 'bl #0x156686c'); stock(0x1191E5C, 'bl #0x156686c')
parts = open(MSB_PARTS, encoding='utf-8-sig').read()
assert 'AEG099_500_' not in parts, 'asset 99500 placed in the m10 MSB: re-judge ITEMGRANT_PICKUP'
b, rs = param_rows('SubQuestTypeParam.param')
sqt_goods = struct.unpack_from('<i', b, rs[0][1] + 0x10)[0]
listing.append('PICKUP: 99500 created only at %s (type-18 logic 0x119195C); no AEG099_500 part in m10; '
               'goods = SubQuestTypeParam[0]+0x10 = %d [I: repo slot]' % ([hex(a) for a in m], sqt_goods))

# ================================================================ POWER [V]
# 0xD4CA60 (the only list builder, called twice from 0xD49460) reads SkillParam (0x1D2C9A0 = repo+0x2310) +0x60
assert sorted(a for a, k in bl_callers(0xD4CA60)) == [0xD4A1AC, 0xD4A1B8]
for a, t in ((0xD4CB28, 'bl #0x1d2c9a0'), (0xD4CB34, 'ldr w9, [x8, #0x60]'), (0xD4CB4C, 'ldrb w10, [x8, #0x52]'),
             (0xD4CB74, 'ldrb w26, [x8, #0x3d]'), (0x1D2C9C8, 'ldr x8, [x8, #0x2318]'),
             (0xD4A298, 'b.ne #0xd4a2ec'), (0xD4A688, 'b.ne #0xd4a574')):
    stock(a, t)
b, rs = param_rows('SkillParam.param')
sk = [(rid, struct.unpack_from('<i', b, o + 0x60)[0]) for rid, o in rs]
with_goods = [r for r in sk if r[1] >= 0]
assert not with_goods, 'SkillParam rows with goods: %s: re-judge ITEMGRANT_POWER' % with_goods
listing.append('POWER: %d SkillParam rows, goods field +0x60 >= 0 in none -> both goods lists always empty' % len(sk))

# ---------------------------------------------------------------- optional: the regulation the game really loads
try:
    import zstandard
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    KEY = bytes.fromhex('10B8C2BDAAB0FA1D5EA1CD750CFDBC1368A76603119D56647F4B25069443C64B')
    REG = os.path.join(HERE, '..', '..', 'emulators', 'v30-eglantine', 'user', 'duskbloods_test', 'nand', 'system',
                       'save', 'bcat', '0400D1D02399A000', 'Regulation', 'regulation_nt_1_0.bin')
    blob = open(REG, 'rb').read()
    d = Cipher(algorithms.AES(KEY), modes.CBC(blob[:16])).decryptor()
    plain = d.update(blob[16:]) + d.finalize()
    us, cs = struct.unpack_from('>II', plain, 0x1c)
    bnd = zstandard.ZstdDecompressor().decompress(plain[0x4c:0x4c + cs], max_output_size=us)
    reg = {}
    for i in range(struct.unpack_from('<I', bnd, 0xc)[0]):
        _, _, size, _, off, fid, name_at = struct.unpack_from('<BxxxiqqIiI', bnd, 0x40 + i * 0x24)
        e = name_at
        while bnd[e:e + 2] != b'\0\0':
            e += 2
        reg[bnd[name_at:e].decode('utf-16le').split('\\')[-1]] = bnd[off:off + size]
    b, rs = param_rows('EnvEventParam.param', blob=reg['EnvEventParam.param'])
    assert all(b[o + 0xF] != 2 for _, o in rs), 'regulation: type-2 env event'
    b, rs = param_rows('EnvEventTypeParam.param', blob=reg['EnvEventTypeParam.param'])
    assert struct.unpack_from('<i', b, rs[0][1] + 0x15C)[0] == -1, 'regulation: env reward goods set'
    b, rs = param_rows('SubQuestParam.param', blob=reg['SubQuestParam.param'])
    assert all(b[o] != 18 for _, o in rs), 'regulation: type-18 sub quest'
    b, rs = param_rows('SkillParam.param', blob=reg['SkillParam.param'])
    assert all(struct.unpack_from('<i', b, o + 0x60)[0] < 0 for _, o in rs), 'regulation: SkillParam goods'
    listing.append('regulation_nt_1_0.bin (live BCAT copy): same four facts hold')
except AssertionError:
    raise
except Exception as e:   # informational only (needs zstandard + cryptography)
    listing.append('(regulation not read: %s; gameparam facts above still hold)' % e)

# ---------------------------------------------------------------- four item-authority paths (report only) [V]
SERVER = [0x15A34A8, 0x15AF628, 0x15B2644, 0x15B4A9C]
assert all(a in all_callers for a in SERVER)
assert sorted(a for a, k in bl_callers(0x15A3340)) == [0x159CB44, 0x15A43A0]
# take award 0x15A43A0 is after 0x15A42B0; shipped ITEMS I6b/I6c send mode 6 to the subtype-6 reply 0x15A4510 first
for a, t in ((0x15A42B0, 'b #0x563e520'), (0x15A4484, 'b #0x563e544'), (0x563E534, 'cmp w8, #6'),
             (0x563E538, 'b.eq #0x563e540'), (0x563E540, 'b #0x15a4510'), (0x563E558, 'cmp w8, #6'),
             (0x563E55C, 'b.eq #0x563e564'), (0x563E564, 'b #0x15a4510'), (0x15AF3D8, 'cbnz w8, #0x15af674'),
             (0x159C710, 'cbnz w8, #0x159ca1c'), (0x15A4204, 'nop')):
    got = C.dis1(a, C.shipped_word(a))
    assert got == t, 'shipped %x: %s, expected %s' % (a, got, t)
stock(0x159CB40, 'mov w3, w21'); stock(0x159CB28, 'ldr w20, [x23, #0xd0]'); stock(0x159C72C, 'cmp w8, #2')
stock(0x15B7F18, 'cbz w8, #0x15b7f88'); stock(0x15B4A98, 'neg w3, w8'); stock(0x15B4A50, 'bl #0x159c6c4')
assert bl_callers(0x15AAC68) == [(0x17B4678, 'b')] and ptr_refs(0x17B4600) == [0x572CC50]
assert ptr_refs(0x15B7EC4) == [0x5722250]
listing.append('server paths: take award 0x15A43A0 unreachable in mode 6 (shipped I6b/I6c reply first); '
               'direct give 0x159CB44 / lot give 0x15AF380 / sub 8 0x15B21A0 / sub 0x13 0x15B4320 authority-only')

groups = {'ITEMGRANT_EVENT': [], 'ITEMGRANT_QUEST': [], 'ITEMGRANT_POWER': [], 'ITEMGRANT_PICKUP': []}
ORDER = list(groups)
print('\n'.join(listing))
C.write_live(OUT, groups, ORDER, """Items the server granted directly: (offset_from_main, orig_hex, new_hex, is_code).
Generated by itemgrant_gen.py. ALL FOUR GROUPS ARE EMPTY ON PURPOSE: in this build (gameparam_nt and the live
regulation) none of these grants has a trigger or an item (env type 2 / reward -1, sub-quest type 18 unused,
asset 99500 only from type 18, no SkillParam goods). Nothing to apply, nothing to bake. Notes: itemgrant_notes.md.""")
