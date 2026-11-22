"""Generator + checker for the reward groups in rewards_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes rewards_live.py, prints a
capstone listing of every original and new word).
python rewards_gen.py            (run from anywhere; paths are relative to this file)

Groups (design, [V]/[I] marks and live tests: rewards_notes.md):
  FORGE_OWN_CAVE / FORGE_OWN  Alchemy Forge reward in LAN, forge only:
      0x11A06D0..0x11A06E4  the forge apply 0x11A06B4: the redundant "item id == -1" test and the +0xBDA gate
                            become "requester chr == local player chr" (WCM+0x1A8), so only the presser's own
                            game grants, and only for its own player (also safe with ACTION_SHARE).
      0xCF8F74              the shared non-flask gate of 0xCF8E2C jumps to a 7-word cave that opens it only when
                            the caller is the forge (saved LR low 32 bits == main+0x11A076C). The 4 ungated callers
                            0xF16130 / 0x15A3340 / 0x15B21A0 / 0x15B4320 stay blocked in LAN.
      cave = text padding 0xCF0E84..0xCF0E9F (7 udf words between retab 0xCF0E80 and pacibsp 0xCF0EA0).
  SKILL_LOCAL   blood crystal -> skill enhancement: the lot request (0xCFE9A8) and the pick (0xCFEFA0) take their
                offline branch (run on the own game, nothing sent to the server member), and the pick award
                0x159D780 runs in LAN (gate 0xCFF878).
  LEVEL         = census_live.py LEVEL (same record, re-verified): blood/EXP from kill SpEffects (+0x3F0) to the local
                player through 0xD173C0. Apply it from ONE file only.
  POWER_PICK    Power of Blood (intermission reward pick, equip-skill apply 0x100B140) applied on the own game
                instead of the 0x8C server sink.
  POWER_OFFER   OPTIONAL, check first: the offer generation 0x100C060 runs in LAN (only if no offer appears)."""
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
DATA = open(os.path.join(N, 'main_data.bin'), 'rb').read()
RO_BASE = 0x492B000
DATA_BASE = 0x563F000
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

NOP = 0xD503201F
WCM = 0x5B3CD88          # *(main+0x5B3CD88) = world chr man; +0x1A8 = local player chr ins
FORGE_RET = 0x11A076C    # return address of the forge's bl 0xCF8E2C (0x11A0768)
CAVE_LO, CAVE_HI = 0xCF0E84, 0xCF0EA0

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name in arrays:
        for i, bt in enumerate(arrays[name]):
            shipped[a + i] = bt
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other helper's records (*_live.py)
others = {}   # byte address -> (file, new hex word)
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith('_live.py') or fn == 'rewards_live.py':
        continue
    body = open(os.path.join(HERE, fn), encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', body):
        a, new = int(m.group(1), 16), m.group(3).upper()
        for i in range(len(new) // 2):
            others.setdefault(a + i, []).append((fn, new))
print('other *_live.py bytes parsed: %d' % len(others))
# Known, intended overlaps: FORGE_OWN replaces flame_live.py FORGE_TEST (never apply both);
# LEVEL is the same record as census_live.py LEVEL.
ALLOWED = {0x11A06E4: 'flame_live.py', 0xCF8F74: 'flame_live.py', 0x17BBD48: 'census_live.py'}


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range %x -> %x' % (pc, t)
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bcond(pc, t, cond): return 0x54000000 | (_rel(pc, t, 19) << 5) | cond
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def add_x(rd, rn, imm): return 0x91000000 | (imm << 10) | (rn << 5) | rd


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


EQ, NE = 0, 1
CMP_W9_W10 = 0x6B0A013F   # subs wzr, w9, w10
CMP_X9_X1 = 0xEB01013F    # subs xzr, x9, x1

listing = []
groups = {}


def check_free(addr):
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
        if addr + i in others:
            assert ALLOWED.get(addr) and all(f == ALLOWED[addr] for f, _ in others[addr + i]), \
                'collides with %r at %x' % (others[addr + i], addr)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    check_free(addr)
    listing.append('  0x%x  %-28s ->  %-28s (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


# ---------------------------------------------------------------- references into a code range
W = struct.unpack('<%dI' % (len(TXT) // 4), TXT[:len(TXT) // 4 * 4])


def refs_into(lo, hi):
    """Every b/bl/b.cond/cbz/cbnz/tbz/tbnz/adr/adrp+add in main text and every u64 in text/ro/data that points into
    [lo, hi)."""
    hits = []
    for i, w in enumerate(W):
        pc = i * 4
        t = None
        if (w & 0x7C000000) == 0x14000000:                       # b / bl
            d = w & 0x3FFFFFF
            t = pc + ((d - (1 << 26)) if d & (1 << 25) else d) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:   # b.cond / cbz / cbnz
            d = (w >> 5) & 0x7FFFF
            t = pc + ((d - (1 << 19)) if d & (1 << 18) else d) * 4
        elif (w & 0x7E000000) == 0x36000000:                     # tbz / tbnz
            d = (w >> 5) & 0x3FFF
            t = pc + ((d - (1 << 14)) if d & (1 << 13) else d) * 4
        elif (w & 0x9F000000) == 0x10000000:                     # adr
            d = ((w >> 5) & 0x7FFFF) << 2 | (w >> 29) & 3
            t = pc + ((d - (1 << 21)) if d & (1 << 20) else d)
        elif (w & 0x9F000000) == 0x90000000:                     # adrp (+ add within 4 words)
            d = ((w >> 5) & 0x7FFFF) << 2 | (w >> 29) & 3
            page = (pc & ~0xFFF) + (((d - (1 << 21)) if d & (1 << 20) else d) << 12)
            if page <= hi and page + 0x1000 > lo:
                rd = w & 31
                for j in range(1, 5):
                    if i + j < len(W):
                        y = W[i + j]
                        if (y & 0xFFC00000) == 0x91000000 and (y >> 5) & 31 == rd:
                            v = page + ((y >> 10) & 0xFFF)
                            if lo <= v < hi:
                                hits.append(('adrp+add', pc))
        if t is not None and lo <= t < hi:
            hits.append(('branch', pc))
    for seg, base in ((TXT, 0), (DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 4):
            v = struct.unpack_from('<Q', seg, o)[0]
            if lo <= v < hi:
                hits.append(('pointer', base + o))
    return hits


# ================================================================ the text cave slot
assert dis1(CAVE_LO - 4, word(CAVE_LO - 4)) == 'retab', 'no terminator before the slot'
assert word(CAVE_HI) == 0xD503237F, 'slot not followed by pacibsp'
for a in range(CAVE_LO, CAVE_HI, 4):
    assert word(a) == 0, 'slot word %x not udf #0' % a
    check_free(a)
r = refs_into(CAVE_LO, CAVE_HI)
assert not r, 'cave slot referenced: %r' % r[:5]
listing.append('text cave slot 0x%X..0x%X: 7 x udf #0 between retab 0x%X and pacibsp 0x%X, no branch / adr / '
               'adrp+add / pointer reaches it, not in patch_manager.cpp or any *_live.py'
               % (CAVE_LO, CAVE_HI - 1, CAVE_LO - 4, CAVE_HI))

# ================================================================ 1. FORGE_OWN
listing.append('=== FORGE_OWN (Alchemy Forge, forge path only)')
# context of the forge apply 0x11A06B4 [V]
for a, t in ((0x11A06CC, 'ldr w8, [x3]'), (0x11A06EC, 'mov w9, #0x3fffffff'), (0x11A0710, 'cmp w8, w9'),
             (0x11A0714, 'b.ne #0x11a076c'), (0x11A0728, 'ldr x9, [x1, #0x20]'), (0x11A0768, 'bl #0xcf8e2c'),
             (0x11A074C, 'mov w4, #7')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
# nothing may branch into the replaced block except its first word
r = refs_into(0x11A06D4, 0x11A06E8)
assert not r, 'reference into the forge block: %r' % r
fo = [
    text_patch(0x11A06D0, 'cmn w8, #1', adrp(0x11A06D0, 9, WCM), 'x9 = page of WCM (the -1 test is redundant: '
               '-1 never equals 0x3fffffff / 0x3xxxxxxx at 0x11A0710)'),
    text_patch(0x11A06D4, 'b.eq #0x11a076c', ldr_x(9, 9, WCM & 0xFFF), 'x9 = WCM'),
    text_patch(0x11A06D8, 'adrp x9, #0x5b65000', cbz_x(0x11A06D8, 9, 0x11A076C), 'no WCM: nothing'),
    text_patch(0x11A06DC, 'ldr x9, [x9, #0xc20]', ldr_x(9, 9, 0x1A8), 'x9 = local player chr'),
    text_patch(0x11A06E0, 'ldrb w9, [x9, #0xbda]', CMP_X9_X1, 'requester chr == local player chr?'),
    text_patch(0x11A06E4, 'cbz w9, #0x11a076c', bcond(0x11A06E4, 0x11A076C, NE), 'other chr: nothing '
               '(was the +0xBDA gate)'),
]
# shared gate of 0xCF8E2C [V]
for a, t in ((0xCF8F68, 'adrp x8, #0x5b65000'), (0xCF8F70, 'ldrb w8, [x8, #0xbda]'), (0xCF8F78, 'add x8, sp, #0x10'),
             (0xCF8FE4, 'mov w25, wzr'), (0xCF8E30, 'stp x29, x30, [sp, #-0x60]!'), (0xCF8E38, 'mov x29, sp'),
             (0xCF8EEC, 'cbz w8, #0xcf8fe4')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
C = CAVE_LO
cave_words = [
    cbnz_w(C, 8, 0xCF8F78),                 # +0xBDA set (offline): unchanged, grant
    ldr_x(9, 29, 8),                        # saved LR of 0xCF8E2C ([x29+8], PAC only in the high bits)
    adrp(C + 8, 10, FORGE_RET),
    add_x(10, 10, FORGE_RET & 0xFFF),       # x10 = main+0x11A076C
    CMP_W9_W10,                             # low 32 bits equal = called from the forge
    bcond(C + 0x14, 0xCF8F78, EQ),          # forge: grant (slot lookup 0xCF3F08, inventory add 0xCF7CC0)
    b(C + 0x18, 0xCF8FE4),                  # everybody else: blocked as before
]
listing.append('--- FORGE cave at 0x%X (%d words)' % (C, len(cave_words)))
for i, w in enumerate(cave_words):
    listing.append('  0x%x %s' % (C + i * 4, dis1(C + i * 4, w)))
groups['FORGE_OWN_CAVE'] = [(C + i * 4, '00000000', hexw(w), True) for i, w in enumerate(cave_words)]
groups['FORGE_OWN'] = fo + [
    text_patch(0xCF8F74, 'cbz w8, #0xcf8fe4', b(0xCF8F74, C), 'non-flask gate -> forge-only cave'),
]

# ================================================================ 2. SKILL_LOCAL
listing.append('=== SKILL_LOCAL (blood crystal -> skill enhancement lot and pick on the own game)')
for a, t in ((0xCFEA00, 'cmp w8, #6'), (0xCFEA64, 'bl #0xcfec40'), (0xCFF1D4, 'cmp w8, #6'),
             (0xCFF2B4, 'bl #0xcff780'), (0xCFF8A4, 'bl #0x159d780'), (0xCFF874, 'ldrb w8, [x8, #0xbda]')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
groups['SKILL_LOCAL'] = [
    text_patch(0xCFEA04, 'b.ne #0xcfea4c', b(0xCFEA04, 0xCFEA4C), 'lot request 0xCFE9A8: run 0xCFEC40 here, '
               'no B3 0x10 to the server member'),
    text_patch(0xCFF1D8, 'b.ne #0xcff2a8', b(0xCFF1D8, 0xCFF2A8), 'pick 0xCFEFA0: run 0xCFF780 here, '
               'no B3 0x12 to the server member'),
    text_patch(0xCFF878, 'cbz w8, #0xcff8a8', NOP, 'pick 0xCFF780: give the chosen option (0x159D780) in LAN'),
]

# ================================================================ 3. LEVEL (census_live.py, re-verified)
listing.append('=== LEVEL (kill blood / EXP to the local player)')
for a, t in ((0x17BBD3C, 'adrp x8, #0x5b57000'), (0x17BBD58, 'cbz w8, #0x17bbeb8'), (0x17BBEA8, 'ldr x8, [x8, #0x1a8]'),
             (0x17BBEAC, 'cmp x8, x19'), (0x17BBEB4, 'bl #0xd173c0')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
groups['LEVEL'] = [
    text_patch(0x17BBD48, 'cbz x8, #0x17bbe1c', b(0x17BBD48, 0x17BBE1C), 'always the local-player award path'),
]
cl = open(os.path.join(HERE, 'census_live.py')).read()
assert '(0x17BBD48, "A80600B4", "35000014", True)' in cl, 'census_live.py LEVEL differs'
assert groups['LEVEL'][0] == (0x17BBD48, 'A80600B4', '35000014', True)

# ================================================================ 4. POWER_PICK / POWER_OFFER
listing.append('=== POWER_PICK (Power of Blood pick applied on the own game)')
for a, t in ((0x100B030, 'cmp w8, #0'), (0x100B074, 'ldrb w8, [x8, #0xbda]'), (0x100B07C, 'ldrb w8, [x19]'),
             (0x100B0C8, 'bl #0x100b140'), (0x100B0E4, 'bl #0x14e2b0c'), (0x100B0E8, 'strb wzr, [x19, #4]'),
             (0x100B0EC, 'str wzr, [x19]'), (0x100B3D4, 'bl #0xd4ddac')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
groups['POWER_PICK'] = [
    text_patch(0x100B034, 'b.le #0x100b06c', b(0x100B034, 0x100B06C), 'members > 0 too: take the local branch'),
    text_patch(0x100B078, 'cbz w8, #0x100b038', NOP, 'apply the pick (0x100B140) in LAN, not the 0x8C send'),
]
listing.append('=== POWER_OFFER (optional)')
for a, t in ((0x100BFBC, 'cmp w8, #0'), (0x100BFE0, 'ldrb w8, [x8, #0xbda]'), (0x100BFF0, 'bl #0x100c060')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
groups['POWER_OFFER'] = [
    text_patch(0x100BFC0, 'b.le #0x100bfd8', b(0x100BFC0, 0x100BFD8), 'members > 0 too'),
    text_patch(0x100BFE4, 'cbz w8, #0x100bfc4', NOP, 'generate the offers (0x100C060) in LAN'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['FORGE_OWN_CAVE', 'FORGE_OWN', 'SKILL_LOCAL', 'LEVEL', 'POWER_PICK']
ALL = ORDER + ['POWER_OFFER']
notes = {
    'FORGE_OWN_CAVE': 'forge-only opening of 0xCF8E2C (text padding 0xCF0E84..0xCF0E9F; inert until FORGE_OWN)',
    'FORGE_OWN': 'Alchemy Forge reward in LAN for the local presser only; REPLACES flame_live.py FORGE_TEST',
    'SKILL_LOCAL': 'skill-enhancement lot + pick run on the own game, pick award in LAN',
    'LEVEL': 'kill blood / EXP / level-up for the local player (same record as census_live.py LEVEL)',
    'POWER_PICK': 'Power of Blood pick (intermission reward) applied locally',
    'POWER_OFFER': 'OPTIONAL: Power of Blood offers generated locally (only if none appear without it)',
}
out = ['"""Reward patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by rewards_gen.py (original-word checks, capstone listing, collision checks against',
       'patch_manager.cpp and every diag/net/*_live.py). Not live-tested. Notes: rewards_notes.md.',
       'FORGE_OWN_CAVE uses text padding main+0xCF0E84..0xCF0E9F (orig "00000000" = udf #0); apply it before FORGE_OWN.',
       'FORGE_OWN replaces flame_live.py FORGE_TEST (same words 0x11A06E4 / 0xCF8F74): never apply both.',
       'LEVEL is the census_live.py LEVEL record: apply it from one file only.',
       'Apply on EVERY game (no group is host-only)."""', '']
for g in ALL:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]  # POWER_OFFER optional, only after its live check' % ', '.join(ORDER))
open(os.path.join(HERE, 'rewards_live.py'), 'w').write('\n'.join(out) + '\n')
print('rewards_live.py written')
