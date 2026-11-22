"""Generator + checker for rewards3_live.py (rewards part 3). Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes rewards3_live.py and prints a
capstone listing of every original and new word plus the context checks. No caves, no new code: in-place words only.
python rewards3_gen.py            (run from anywhere; paths are relative to this file)

Groups (design, [V]/[I] marks and live tests: rewards3_notes.md):
  FORGE_APPLY   0xD0078C nop: the weapon-change step 0xD00764 runs in LAN; 0xD0079C nop: no local apply, the B3
                subtype 0x14 message (routing 0x40 = server member only = own self link) comes back once and the
                B3 reader (server-member read only) applies it through 0xD00888 to the player in the message.
  POWER_OFFER2  = rewards_live.py POWER_OFFER (0x100BFC0 b, 0x100BFE4 nop) + 0x100DC34 chr query mask 0x407 -> 1, so
                the offer slots are built for the LOCAL player chr only (no slot, no random apply 0x1015F60 ->
                0xD49460 for copies of other players). Use with rewards_live.py POWER_PICK. Replaces POWER_OFFER.
  POWER_OFFER3  0x100D3EC..0x100D3F8 (4 words): the Power page check 0x100D3C0 (only caller: menu page builder
                0x12C9880) tests map[team] < 12 instead of team < slot count; with POWER_OFFER2's single local slot
                the stock test passes only for team 0. power_offer_notes.md.
  POWER_OFFER4  WITHDRAWN 2026-11-15 (was a guess: every Power weight 1 + roll forced). Not written any more.
  POWER_OFFER5  no word (checks only, replaces POWER_OFFER4): the offline logic run on the shipped data gives NO
                option to anybody at any intermission (all three local sources are empty: lot A weights, lot B
                follow-up lists, PhaseInfoParam round-row ids, also for the bot-match missions). The current build
                (POWER_OFFER2 + 3 + POWER_PICK) already behaves exactly like offline. power_offer2_notes.md.
  BLOOD_AWARD   no word: the pick award 0x159D780 -> 0x15A4924 is a world-item take, broadcast by the shipped ITEMS
                I1 word 0x15A49A0 and served by the item authority; checks only."""
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
    if name not in arrays:
        continue
    for i, bt in enumerate(arrays[name]):
        shipped[a + i] = bt
print('shipped bytes parsed: %d' % len(shipped))
assert len(shipped) > 1000, 'patch_manager.cpp parse failed'

# ---------------------------------------------------------------- every other helper's records (*_live.py)
others = {}
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith('_live.py') or fn == 'rewards3_live.py':
        continue
    body = open(os.path.join(HERE, fn), encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', body):
        a, new = int(m.group(1), 16), m.group(3).upper()
        for i in range(len(new) // 2):
            others.setdefault(a + i, []).append((fn, new))
print('other *_live.py bytes parsed: %d' % len(others))
# Intended overlap: POWER_OFFER2 contains (and replaces) rewards_live.py POWER_OFFER, same words, same new values.
ALLOWED = {0x100BFC0: ('rewards_live.py', '06000014'), 0x100BFE4: ('rewards_live.py', '1F2003D5')}


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def at(addr):
    return dis1(addr, word(addr))


def ctx(addr, expect):
    got = at(addr)
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)
    listing.append('  ctx 0x%x  %s' % (addr, got))


def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)


NOP = 0xD503201F
listing = []
groups = {}


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    baked = shipped_hex(addr) == hexw(new)      # this group's own word, already baked into patch_manager.cpp
    for i in range(4):
        assert baked or addr + i not in shipped, 'collides with a shipped record at %x' % addr
    for i in range(4):
        for fn, nw in others.get(addr + i, []):
            assert ALLOWED.get(addr) == (fn, hexw(new)), 'collides with %s at %x' % (fn, addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def callers(tgt):
    r = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            if o + imm * 4 == tgt:
                r.append(o)
    return r


def shipped_hex(a):
    if not all(a + i in shipped for i in range(4)):
        return None
    return bytes(shipped[a + i] for i in range(4)).hex().upper()


# ================================================================ 1. FORGE_APPLY
listing.append('=== FORGE_APPLY')
# 0xD00764 shape: gate, arg moves done before the local apply, then members >= 1 -> B3 0x14 to vt+0x40
ctx(0xD00788, 'ldrb w8, [x8, #0xbda]')
ctx(0xD00790, 'mov w19, w3')
ctx(0xD00794, 'mov x21, x2')
ctx(0xD00798, 'mov x20, x1')
ctx(0xD007CC, 'cmp w8, #1')
ctx(0xD007D8, 'mov w9, #0x14')
ctx(0xD00838, 'mov w1, #0xb3')
ctx(0xD0083C, 'ldr x8, [x8, #0x40]')
assert callers(0xD00764) == [0xCCE59C], 'callers of 0xD00764 changed'
assert sorted(callers(0xD00888)) == [0xD0079C, 0xD05A70], 'callers of 0xD00888 changed'
# routing of type 0xB3: attribute table main+0x4C4B3AC, byte +4 = 0x40 (server member only), not shipped-patched
assert struct.unpack_from('<Q', DATA, 0x59E41D0 - DATA_BASE)[0] == 0x4C4B3AC
ra = 0x4C4B3AC + 8 * 0xB3
assert RO[ra - RO_BASE:ra - RO_BASE + 8] == bytes([0xB3, 0, 0, 0, 0x40, 0, 0, 0]), 'B3 attribute changed'
assert not any(ra + i in shipped for i in range(8)), 'B3 attribute patched by a shipped record'
for i in range(8):
    assert ra + i not in others, 'B3 attribute patched by %r' % others[ra + i]
ctx(0x1CD7E70, 'ldr x8, [x20, #0x668]')     # routing applies only with a server member
ctx(0x1CD7E88, 'tbnz w8, #6, #0x1cd7ecc')   # bit 6: only members with +0xE0 (server flag)
ctx(0x1CD7ECC, 'ldrb w8, [x22, #0xe0]')
listing.append('  B3 attribute byte = 0x40 (server member only) [V]')
# B3 reader: item-mgr update reads 0xB3 only from the server member id mgr3+0x678 (vt+0x60), then the loopback
ctx(0xCF2B10, 'ldr x9, [x8, #0x678]')
ctx(0xCF2B54, 'mov w1, #0xb3')
ctx(0xCF2B5C, 'ldr x8, [x8, #0x60]')
ctx(0xCF2B90, 'bl #0xd00e40')
ctx(0xCF2C00, 'mov w2, #0xb3')
ctx(0xCF2CB0, 'bl #0xd00e40')
# handler 0xD00E40: x22 = message header + 4 (player no in the message), dispatch by subtype (max 0x14)
ctx(0xD00E94, 'add x22, x20, #4')
ctx(0xD01204, 'cmp w8, #0x14')
jt = 0x4C47BB4 + 0x14 * 2
h = struct.unpack_from('<H', RO, jt - RO_BASE)[0]
assert 0xD0122C + h * 4 == 0xD058B8, 'case 0x14 target %x' % (0xD0122C + h * 4)
listing.append('  jump table case 0x14 -> 0xD058B8 [V]')
ctx(0xD05A60, 'mov x0, x27')
ctx(0xD05A68, 'mov x1, x22')
ctx(0xD05A70, 'bl #0xd00888')
# no use of the sender flag w19 in case 0x14 before it is overwritten at 0xD05980
for a in range(0xD058B8, 0xD05980, 4):
    s = at(a)
    assert 'w19' not in s and 'x19' not in s, 'case 0x14 uses w19 at %x: %s' % (a, s)
ctx(0xD05980, 'ldur w19, [x24, #9]')
# 0xD00888 applies to the chr with the message's player number (0x17F1940 mask 0x407), weapon via 0xE92940
ctx(0xD008D8, 'ldr w8, [x22]')
ctx(0xD00900, 'mov w2, #0x407')
ctx(0xD00920, 'bl #0x17f1940')
ctx(0xD009F8, 'bl #0xe92940')
# player number at the only caller: pgd ([x19+0x710]) +0xD0
ctx(0xCCE450, 'ldr x8, [x19, #0x710]')
ctx(0xCCE454, 'ldr w1, [x8, #0xd0]')
ctx(0xCCE45C, 'str w1, [sp, #0x48]')
ctx(0xCCE59C, 'bl #0xd00764')
groups['FORGE_APPLY'] = [
    text_patch(0xD0078C, 'cbz w8, #0xd00848', word(0xD00790), 'move mov w19, w3 up (keep w8 = +0xBDA)'),
    text_patch(0xD00790, 'mov w19, w3', word(0xD00794), 'move mov x21, x2 up'),
    text_patch(0xD00794, 'mov x21, x2', word(0xD00798), 'move mov x20, x1 up'),
    text_patch(0xD00798, 'mov x20, x1', 0x34000048, 'cbz w8, #0xd007a0: LAN skips local apply and sends; offline calls 0xd00888'),
]

# ================================================================ 2. POWER_OFFER2
listing.append('=== POWER_OFFER2')
assert callers(0x100BD1C) == [0x114F610]
assert callers(0x100C060) == [0x100BFF0]
assert callers(0x100D980) == [0x100C07C], 'slot builder has other callers'
assert callers(0x1015F60) == [0x100C024]
ctx(0x114F610, 'bl #0x100bd1c')
ctx(0x114F88C, 'bl #0x1149160')            # PrepareSecond advances its step after the body: once per entry
ctx(0x100BD5C, 'tbnz w8, #7, #0x100bf90')  # reward-table byte bit 7
ctx(0x100BFBC, 'cmp w8, #0')
ctx(0x100BFE0, 'ldrb w8, [x8, #0xbda]')
ctx(0x100BFF0, 'bl #0x100c060')
ctx(0x100C024, 'b #0x1015f60')             # per-slot random pick applied through 0xD49460 (equip skill)
ctx(0x100C07C, 'bl #0x100d980')
# slot builder: one slot per chr returned by 0x17F1320(WCM, functor 0x56ECBA0, mask, 0)
ctx(0x100DC3C, 'mov w3, wzr')
ctx(0x100DC44, 'bl #0x17f1320')
assert struct.unpack_from('<Q', DATA, 0x56ECBA0 + 0x30 - DATA_BASE)[0] == 0x1012400, 'functor vt+0x30'
ctx(0x1012448, 'ldr x9, [x9, #0x1d0]')
ctx(0x1012450, 'ldrsb w8, [x9, #0x104]')   # slot key = player index of the chr
# 0x17F1320 mask: bit 0 = local player WCM+0x1A8, bit 1 = other players WCM+0x30 list (local skipped)
ctx(0x17F13B8, 'ldr x1, [x20, #0x1a8]')
ctx(0x17F13C8, 'tbnz w21, #0, #0x17f1464')
ctx(0x17F14CC, 'tbz w21, #1, #0x17f1594')
ctx(0x17F152C, 'ldr x8, [x8, #0x1a8]')
assert struct.unpack_from('<5I', RO, 0x4C4D7E0 - RO_BASE) == (0x404, 0x8, 0x20, 0x100, 0x200)
# the pick (POWER_PICK) uses the local player's index
ctx(0x100B050, 'ldr x8, [x8, #0x1a8]')
ctx(0x100B0B8, 'ldrb w8, [x8, #0x104]')
ctx(0x100B0C8, 'bl #0x100b140')
rl = open(os.path.join(HERE, 'rewards_live.py')).read()
for a, o, n in ((0x100B034, 'CD010054', '0E000014'), (0x100B078, '08FEFF34', '1F2003D5')):
    assert '(0x%X, "%s", "%s", True)' % (a, o, n) in rl, 'POWER_PICK record %x missing in rewards_live.py' % a
groups['POWER_OFFER2'] = [
    text_patch(0x100BFC0, 'b.le #0x100bfd8', b(0x100BFC0, 0x100BFD8), 'offers also with session members'),
    text_patch(0x100BFE4, 'cbz w8, #0x100bfc4', NOP, 'offers in LAN (+0xBDA = 0)'),
    text_patch(0x100DC34, 'mov w2, #0x407', 0x528080A2, 'slots for local player + 0x404 group (drops bit 1 copies; mask 0x405)'),
]
assert at(0x100DC34) == 'mov w2, #0x407' and dis1(0x100DC34, 0x528080A2) == 'mov w2, #0x405'

# ================================================================ 2b. POWER_OFFER3 (dialog key check)
# The intermission menu builds the Power of Blood page with 0x12C9880 (callers 0x13A6508 / 0x13AC120): key = the local
# chr's team byte [[chr+0x20]+0x1D0]+0x104 (0..11), then 0x100D3C0(sys, out, &key) must return 1, then the mapped
# slot (+0xE48[key]) must have +0x28 (offered, set by the generator 0x100E980 at 0x100EB78 when +0x29 eligible).
# 0x100D3C0 tests key < +0x1154 (the SLOT COUNT, not the slot of the key). Offline every chr gets a slot (count =
# number of chrs, teams 0..n-1), so it passes; with POWER_OFFER2 (local slot only) count = 1, so every player whose
# team byte is not 0 fails -> no page. Fix: test that the key has a slot (+0xE48[key] < 12) instead.
listing.append('=== POWER_OFFER3')
assert callers(0x100D3C0) == [0x12C991C], 'callers of 0x100D3C0 changed'
assert callers(0x12C9880) == [0x13A6508, 0x13AC120], 'callers of 0x12C9880 changed'
ctx(0x12C990C, 'ldrb w8, [x8, #0x104]')    # key = team byte of the local chr
ctx(0x12C991C, 'bl #0x100d3c0')
ctx(0x12C9920, 'tbz w0, #0, #0x12c9c18')    # 0 -> no Power page
ctx(0x12C997C, 'mov w9, #0x1130')           # par+0x2E8+0xE48 = slot map
ctx(0x12C99D8, 'ldrb w9, [x8, #0x28]')      # slot+0x28 offered
ctx(0x12C99DC, 'cbz w9, #0x12c9a68')
ctx(0x100D3E0, 'ldrb w8, [x2]')
ctx(0x100D3E4, 'cmp w8, #0xb')
ctx(0x100D3FC, 'add x9, x0, #0xe48')
ctx(0x100D404, 'ldrb w8, [x9, x8]')        # slot = map[key], used for the copy
ctx(0x100D564, 'mov w0, wzr')
ctx(0x100EB78, 'strb w9, [x8, #0xe7c]')     # generator: slot+0x28 = 1
ctx(0x1012500, 'strb w8, [x27, #0x29]')     # functor: slot+0x29 eligible
COND_HS = 2
NEW_ADD = 0x91000000 | (0xE48 << 10) | (0 << 5) | 9            # add x9, x0, #0xe48
NEW_LDRB = 0x38600800 | (8 << 16) | (3 << 13) | (9 << 5) | 9     # ldrb w9, [x9, x8]
NEW_CMP = 0x7100001F | (0xC << 10) | (9 << 5)                     # cmp w9, #0xc
NEW_BHS = 0x54000000 | (((0x100D564 - 0x100D3F8) // 4) << 5) | COND_HS
assert dis1(0x100D3EC, NEW_ADD) == 'add x9, x0, #0xe48'
assert dis1(0x100D3F0, NEW_LDRB) == 'ldrb w9, [x9, x8]'
assert dis1(0x100D3F4, NEW_CMP) == 'cmp w9, #0xc'
assert dis1(0x100D3F8, NEW_BHS) == 'b.hs #0x100d564'
groups['POWER_OFFER3'] = [
    text_patch(0x100D3EC, 'mov w9, #0x1154', NEW_ADD, 'x9 = slot map +0xE48'),
    text_patch(0x100D3F0, 'ldrb w9, [x0, x9]', NEW_LDRB, 'w9 = map[key] (x8 = key, zero-extended by ldrb)'),
    text_patch(0x100D3F4, 'cmp w9, w8', NEW_CMP, 'slot index vs 12 (0x0C = no slot)'),
    text_patch(0x100D3F8, 'b.ls #0x100d564', NEW_BHS, 'no slot for the key -> 0 (was: key >= slot count -> 0)'),
]

# ================================================================ 2c. POWER_OFFER4 (local stand-in for server 0x6B)
# Not a LAN gate: a DATA gap. The option ids of a slot come from (a) server message 0x6B (0x100B680, online only),
# (b) the local lot 0x100E980 -> 0x1014940 -> 0x10153A0 (only caller chain), (c) the single-play mission round row
# (0x100F030, needs a mission row: offline missions only). The lot draws candidates from the global table sys+0x198
# (every SkillParam row, bytes +0x1E..+0x22 all 0xFF) weighted by the per-team pool sys+0x10+i*32 built by 0x1019340:
# weight = u16 SkillParam row +0x80 + 2*(clamp(round,2,5)-2). In the shipped regulation (decrypted backup = romfs) all
# 121 rows have weight 0 for every round, so 0x10153A0 drops every candidate (weight*f <= 0) -> ids stay -1. On top,
# the per-slot roll 0x1012618 (slot+0x3D = chance > rand%100, chance by rank tier = first row bytes +0x32C/D/E of the
# param at repo+0x21F0, GameSystemParam [I]: 0/0/30) blocks lot (a) for top/middle ranks.
# Stand-in (lead decides, [I] server choice unknown): every SkillParam row weight 1, roll always passes.
listing.append('=== POWER_OFFER4')
assert callers(0x1019340) == [0x100E18C], 'callers of 0x1019340 changed'
assert callers(0x100E100) == [0x100C088], 'callers of 0x100E100 changed'
assert callers(0x1014940) == [0x100EFBC], 'callers of 0x1014940 changed'
assert callers(0x10153A0) == [0x1014C98], 'callers of 0x10153A0 changed'
ctx(0x1019394, 'sub w22, w9, #2')           # round index clamp(round,2,5)-2
ctx(0x1019460, 'ldp w8, w9, [x9, #0x80]')    # 4 x u16 weights per row
ctx(0x10194A4, 'orr w25, w10, #0x10000')     # new pool entry {id, weight | 0x10000}
ctx(0x10154F0, 'ldr h0, [x8, #4]')           # draw: weight of the candidate
ctx(0x1015524, 'fcmp s0, #0.0')              # weight * f <= 0 -> candidate dropped
ctx(0x1012614, 'cmp w21, w8')                # chance (vt+0x90 by rank) vs rand % 100
ctx(0x101261C, 'strb w8, [x27]')             # slot roll byte (lot 1 filter 0x1012DC0 reads slot+0x3D)
ctx(0x1012DC4, 'ldrb w0, [x8, #0x3d]')
ctx(0x1012618, 'cset w8, hi')                # stock roll word (POWER_OFFER4 withdrawn: no record written)
ctx(0x1019468, 'ldrh w8, [x24, x22, lsl #1]')
ctx(0x10194A0, 'ldrh w10, [x24, x22, lsl #1]')
listing.append('  POWER_OFFER4 withdrawn: no record (the guess is replaced by POWER_OFFER5 = checks only)')

# ================================================================ 2d. POWER_OFFER5 (checks only: what offline does with the shipped data)
# Every local option source of the intermission offer, code + data. If any assert below fails, the regulation or the
# code changed and the conclusion "nobody is offered anything, offline included" must be re-checked.
listing.append('=== POWER_OFFER5 (no word: checks only)')
PRM = os.path.join(HERE, '..', 'scripts_decoded', 'param', 'gameparam', 'gameparam_nt.parambnd')


def prm(name):
    """{row id: row bytes} of a romfs gameparam PARAM (24-byte row table at +0x40, row = file + offset, no shift)."""
    bb = open(os.path.join(PRM, name + '.param'), 'rb').read()
    n = struct.unpack_from('<H', bb, 0xA)[0]
    offs = [struct.unpack_from('<i4xq', bb, 0x40 + i * 24) for i in range(n)]
    out = {}
    for i, (rid, off) in enumerate(offs):
        end = offs[i + 1][1] if i + 1 < n else len(bb)
        out[rid] = bb[off:end]
    return out, struct.unpack_from('<H', bb, 8)[0]


# (a) server 0x6B: online only (0x100B680 from PrepareThird) - unchanged, never arrives in LAN.
ctx(0x114FB7C, 'bl #0x100b680')
# (b) lot A = new Powers: candidates = global table, weight u16 SkillParam +0x80 + 2*idx, roll slot+0x3D
ctx(0x100EBE8, 'mov w2, wzr')                # lot A mode 0, pool = per-team weights sys+0x10
ctx(0x1012DC4, 'ldrb w0, [x8, #0x3d]')       # lot A filter = the rank-tier roll
ctx(0x11768B8, 'mov w0, #0x708')             # tier split k = CalcCorrectGraph 1800 (player count)
ctx(0x1176934, 'ldr w9, [x8, #0x21f0]')      # tier chance param (GameSystemParam row 0 +0x32C/D/E)
# (b') lot B = follow-up Powers: mode 3, pool = per-team list sys+0x228+i*0x80 (+0x20 vector), filled ONLY from the
# owned Power's SkillParam +0x54/+0x58/+0x5C ids (0x100CF7C, from the equip-skill code 0xD4BE44 / 0x101230C);
# uniform weight 1.0 (0x1014034); chance CalcCorrectGraph 1900 + (mode-3 options so far) at x = pool size.
ctx(0x100ED14, 'mov w2, #3')
ctx(0x1013978, 'mov w11, #0x76c')
ctx(0x1014034, 'fmov s0, #1.00000000')
ctx(0x100D074, 'ldur x20, [x8, #0x54]')
ctx(0x100D078, 'ldr w19, [x8, #0x5c]')
assert sorted(callers(0x1018B40)) == [0x100D08C, 0x100D0A0, 0x100D0B4], 'lot B pool marker has other callers'
assert sorted(callers(0x100CF7C)) == [0xD4BE44, 0x101230C], 'callers of the follow-up marker changed'
# (c) mission round row: only with a single-play mission row; ids = PhaseInfoParam row +0xB8..+0xC4 of the round
ctx(0x100F050, 'ldr w1, [x8, #0xb8]')
ctx(0x100F064, 'bl #0x15647a0')
ctx(0x100F0A0, 'ldrh w8, [x8, #0x78]')       # local chr handle vs slot+0x34: local slot only
ctx(0x100F0E8, 'ldr w10, [x9, #0xb8]')
ctx(0x100F0EC, 'tbnz w10, #0x1f, #0x100f0f8')
ctx(0x100F138, 'ldr w8, [x9, #0xc4]')
ctx(0x1175C4C, 'ldr w9, [x8, #0xb8]')        # round row handle = par+0xD0+(round-1)*8
ctx(0x1175C74, 'ldr x8, [x8, #0xd0]')
ctx(0x15603C0, 'ldr w9, [x8, #0x3000]')      # PhaseInfoParam getter
ctx(0x15604C8, 'add x8, x8, x9')             # row = data + offset: NO -4 shift (the old note's -4 was wrong)
# page: shown when slot+0x28; ids with bit 31 skipped
ctx(0x12C99D8, 'ldrb w9, [x8, #0x28]')
ctx(0x12C9A80, 'tbnz w9, #0x1f, #0x12c9ac4')

sk, skv = prm('SkillParam')
assert skv >= 0x10 and len(sk) == 121, 'SkillParam changed (%d rows, version %d)' % (len(sk), skv)
w_nz = [r for r, d in sk.items() if any(struct.unpack_from('<4H', d, 0x80))]
f_ok = [r for r, d in sk.items() if any(x >= 0 for x in struct.unpack_from('<3i', d, 0x54))]
assert not w_nz, 'SkillParam rows with a lot-A weight: %r' % w_nz[:8]
assert not f_ok, 'SkillParam rows with follow-up ids: %r' % f_ok[:8]
ph, _ = prm('PhaseInfoParam')
ph_ids = {r: struct.unpack_from('<4i', d, 0xB8) for r, d in ph.items()}
assert len(ph) == 50 and all(v == (-1, -1, -1, -1) for v in ph_ids.values()), 'PhaseInfoParam round ids changed'
sm, _ = prm('SinglePlayMissionParam')
assert struct.unpack_from('<i', sm[8000], 0x8C)[0] == -1 and struct.unpack_from('<i', sm[8020], 0x8C)[0] == -1
gs, _ = prm('GameSystemParam')
assert tuple(list(gs.values())[0][0x32C:0x32F]) == (0, 0, 30), 'rank-tier chances changed'
cg, _ = prm('CalcCorrectGraph')
assert struct.unpack_from('<10f', cg[1800], 0) == (2, 3, 4, 6, 8, 0, 1, 1, 1, 3), 'graph 1800 changed'
assert struct.unpack_from('<10f', cg[1900], 0) == (1, 2, 3, 4, 5, 20, 35, 50, 70, 90), 'graph 1900 changed'
listing.append('  data: SkillParam %d rows, lot-A weight > 0: 0, follow-up ids: 0 | PhaseInfoParam %d rows, ids '
               '+B8..+C4 all -1 (bot missions 8000/8020 use these rows) | tier chances 0/0/30 %%, split graph 1800 '
               '(2->0, 3->1, 4->1, 6->1, 8->3) -> every source empty, offline included' % (len(sk), len(ph)))
groups['POWER_OFFER5'] = []

# ================================================================ 3. BLOOD_AWARD (checks only)
listing.append('=== BLOOD_AWARD (no word)')
ctx(0xCFF878, 'cbz w8, #0xcff8a8')          # SKILL_LOCAL nop (rewards_live.py)
assert '(0xCFF878, "88010034", "1F2003D5", True)' in rl
ctx(0xCFF888, 'ldr w1, [x21]')               # world-item id of the request
ctx(0xCFF894, 'ldr w4, [x8, #0xd0]')         # own player number
ctx(0xCFF8A4, 'bl #0x159d780')
ctx(0x159D7C4, 'bl #0x15a2320')               # world-item lookup by id; null -> nothing
ctx(0x159D810, 'cbz x20, #0x159da6c')
ctx(0x159D82C, 'tbnz w9, #4, #0x159d8c0')    # networked item
ctx(0x159D8DC, 'cbz w8, #0x159d904')         # LAN -> 0x15A4924
ctx(0x159D914, 'bl #0x15a4924')
ctx(0x15A4978, 'cmp w8, #6')
ctx(0x15A4990, 'mov w1, #0x1e')
assert at(0x15A49A0) == 'ldr x8, [x8, #0x48]'
assert shipped_hex(0x15A49A0) == '082140F9', 'shipped ITEMS I1 at 0x15A49A0 missing'
listing.append('  0x15a49a0 shipped ITEMS I1: ldr x8, [x8, #0x48] -> %s (take request broadcast)' %
               dis1(0x15A49A0, 0xF9402108))
assert RO[0x4C4B3AC + 8 * 0x1E + 4 - RO_BASE] == 0, '0x1E attribute not 0x00'
assert shipped_hex(0x1597400) == '409C0215', 'shipped 0x1E reader cave (0x1597400) missing'
listing.append('  0x1597400 shipped 0x1E reader hook present; 0x1E attribute 0x00 (every member + self link)')
groups['BLOOD_AWARD'] = []

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['FORGE_APPLY', 'POWER_OFFER2', 'POWER_OFFER3', 'POWER_OFFER5', 'BLOOD_AWARD']
notes = {
    'FORGE_APPLY': 'Alchemy Forge weapon change in LAN; needs rewards_live.py FORGE_OWN_CAVE + FORGE_OWN',
    'POWER_OFFER2': 'Power of Blood offers at PrepareSecond for the own player only; REPLACES rewards_live.py '
                    'POWER_OFFER; needs POWER_PICK',
    'POWER_OFFER3': 'Power of Blood page: 0x100D3C0 tests "the key has a slot" instead of "team < slot count"; '
                    'use with POWER_OFFER2 (offline identical when every chr has a slot)',
    'POWER_OFFER5': 'no word (replaces the withdrawn guess POWER_OFFER4): offline logic + shipped data give no '
                    'intermission option to anybody; checks only (power_offer2_notes.md)',
    'BLOOD_AWARD': 'no word needed: crystal pick award = world-item take via shipped ITEMS (checks only)',
}
out = ['"""Rewards part 3: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by rewards3_gen.py (original-word checks, capstone listing, context checks, collision checks against',
       'patch_manager.cpp and every diag/net/*_live.py). No caves, in-place words only. Not live-tested.',
       'Notes: rewards3_notes.md. Apply on EVERY game (no group is host-only).',
       'POWER_OFFER2 replaces rewards_live.py POWER_OFFER (same two words + one): never apply both."""', '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'rewards3_live.py'), 'w').write('\n'.join(out) + '\n')
print('rewards3_live.py written')
