"""Checker + (optional) generator for the end-of-match findings (endgame_notes.md). Static only: reads
nso/*.bin, src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py.
python endgame_gen.py            verify every claim below, print the listing (writes nothing)
python endgame_gen.py --write    also write endgame_live.py (group REWARD_LOCAL, one word, no cave)

1. HP from Virtue (no patch): asserts the max-HP recompute 0xDE1C80 adds 0xF61A10(pgd), and that 0xF61A10 has
   no +0xBDA test, needs the final coordinator par+0x3388, the current env event type 0x10, stock pgd+0x42A4 ==
   coordinator vt+0xC0, and reads CalcCorrectGraph 0x2F8 (own Virtue 0xD17780) / 0x2F9 (Duo: team 0xD17880).
2. Post-match rewards: asserts the only offline gate of the reward recorder 0x1048120 (0x1048154 cbz +0xBDA),
   the Outcome consumer 0x1048960 (own entries of par+0x4B48 +0x20) and the inventory grant 0x1048040 (no gate).
   REWARD_LOCAL = 0x1048154 nop. With the stock regulation it grants nothing (no LobbyRewardParam lot is set),
   exactly like the offline Bot Match; it only makes LAN run the offline recorder."""
import glob
import os
import re
import struct
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
NOP = 0xD503201F


def word(a):
    return struct.unpack_from('<I', TXT, a)[0]


def dis1(a, w=None):
    w = word(a) if w is None else w
    ins = list(md.disasm(struct.pack('<I', w), a))
    assert len(ins) == 1, 'undecodable at %x' % a
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def expect(a, text):
    got = dis1(a)
    assert got == text, '%x: %r, expected %r' % (a, got, text)
    return got


def hexw(w):
    return struct.pack('<I', w).hex().upper()


listing = []

# ---------------------------------------------------------------- shipped bytes + every *_live.py
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
taken = {}
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    for i in range(len(arrays.get(name, b''))):
        taken[a + i] = 'patch_manager.cpp ' + name
listing.append('shipped bytes: %d' % len(taken))
for f in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    if os.path.basename(f) == 'endgame_live.py':
        continue
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"', open(f, errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            taken.setdefault(a + i, os.path.basename(f))
listing.append('bytes claimed by shipped records + *_live.py: %d' % len(taken))


def free(a, n=4):
    hit = [taken[a + i] for i in range(n) if a + i in taken]
    assert not hit, '%x already claimed by %s' % (a, hit[0])


def fn_has_bda(lo, hi):
    """Any `ldrb wN, [xM, #0xbda]` in [lo, hi)."""
    return [a for a in range(lo, hi, 4) if dis1(a).startswith('ldrb') and dis1(a).endswith('#0xbda]')]


# ================================================================ 1. HP from Virtue
listing.append('=== 1. HP from Virtue (verification only, no record)')
# max-HP recompute 0xDE1C80: s9 = 0xF61A10(pgd) and s8 = 0xF61B4C(chr) are added to the rate-scaled base
expect(0xDE1D2C, 'ldr x8, [x8, #0x298]')           # chr vt+0x298 -> PlayerGameData
expect(0xDE1D34, 'bl #0xf61a10')
expect(0xDE1D38, 'scvtf s9, w0')
expect(0xDE1D48, 'bl #0xf61b4c')
expect(0xDE1E28, 'ldr s1, [x10, #0x10]')           # SpEffect +0x10 maxHpRate, multiplied
expect(0xDE1F48, 'ldrsh w16, [x16, #0x388]')       # SpEffect flat add, summed
expect(0xDE1FFC, 'fmadd s0, s1, s0, s2')           # base * rate + flat
expect(0xDE2008, 'fadd s0, s9, s0')                # + Virtue bonus
expect(0xDE200C, 'fadd s0, s8, s0')
expect(0xDE2028, 'stp w14, w13, [x21]')            # {HP = min(HP, max), max}
expect(0xDE2004, 'ldr w24, [x21, #8]')
# the adr references that hand 0xDE1C80 to the stat update
assert word(0xDDF568) & 0x9F000000 == 0x10000000
# 0xF61A10: no offline flag, final-only, first life only
assert not fn_has_bda(0xF61A10, 0xF61B4C), 'offline gate inside 0xF61A10'
expect(0xF61A38, 'ldr x8, [x8, #0x3388]')          # final coordinator
expect(0xF61A64, 'ldr x8, [x8, #0x68]')            # GDM+0x68 env event list, current = last id
expect(0xF61A94, 'ldrb w8, [x8, #0xf]')            # EnvEventParam +0xF
expect(0xF61A98, 'cmp w8, #0x10')                  # point-select final (rows 2000/2002/2030)
expect(0xF61AB0, 'mov w8, #0x42a4')
expect(0xF61AB4, 'ldrb w20, [x19, x8]')            # stock (spare lives)
expect(0xF61ABC, 'ldr x8, [x8, #0xc0]')            # coordinator vt+0xC0 = initial stock
expect(0xF61AC4, 'cmp w0, w20')
expect(0xF61ADC, 'cmp w8, #2')                     # rule byte main+0x5B65C70 (GOT 0x59E0A70) == 2: Duo
expect(0xF61AE4, 'bl #0xd17880')                   # team Virtue
expect(0xF61AEC, 'mov w0, #0x2f9')                 # CalcCorrectGraph 761
expect(0xF61B08, 'bl #0xd17780')                   # own Virtue: s16 pgd+0x42C8 + counters
expect(0xF61B10, 'mov w0, #0x2f8')                 # CalcCorrectGraph 760
expect(0xF61B18, 'bl #0xf58358')                   # graph lookup (x 0..4, y +0x14, exponent +0x28)
expect(0xD1779C, 'mov w8, #0x42c8')
# initial stock: point-select vt+0xC0 = 0x11704CC reads EnvEventTypeParam row 0 +0xB (+6 if env +0x6C bit 6)
expect(0x1170544, 'ldrsb w0, [x8, #0xb]')
expect(0x117055C, 'ldrsb w0, [x8, #6]')
# phase 19 (0x116BAB4) sets every pgd+0x42A4 = min(vt+0xC0, TentativePlayerParam +0xE0) without a gate
expect(0x116BB04, 'ldr x8, [x8, #0xc0]')
expect(0x116BB54, 'bl #0x17f1320')
expect(0x116C8EC, 'ldrb w8, [x8, #0xe0]')
expect(0x116C900, 'strb w8, [x19, x9]')
listing.append('  max HP = base * prod(SpEffect +0x10) + sum(SpEffect +0x388) + Graph(760, Virtue) + 0xF61B4C;')
listing.append('  bonus only with coordinator par+0x3388, env type 0x10, pgd+0x42A4 == initial stock; no +0xBDA gate')

# ================================================================ 2. post-match rewards
listing.append('=== 2. post-match rewards')
# recorder 0x1048120 (only caller 0x1145798 in the phase-entry apply 0x11454A0)
expect(0x104814C, 'ldr x8, [x8, #0xc20]')
expect(0x1048150, 'ldrb w8, [x8, #0xbda]')
expect(0x1048154, 'cbz w8, #0x10488d0')            # THE gate: LAN records no reward
expect(0x10488D0, 'ldp x20, x19, [sp, #0x110]')    # epilogue
expect(0x10482B0, 'ldr w1, [x8, #0xe0]')           # EnvEventParam +0xE0 -> LobbyRewardParam row
expect(0x10482C4, 'bl #0x155d8c0')                 # LobbyRewardParam accessor (repo +0x4C70, id 270)
expect(0x155D8EC, 'ldr x8, [x8, #0x4c70]')
expect(0x10485F0, 'cmp w9, #0x10')                 # final env: lots +0x24/+0x28/+0x2C by rank 1..3
expect(0x10485F8, 'ldp w9, w10, [x8, #0x24]')      #   (Duo +0x30/+0x34)
expect(0x1048648, 'ldp w9, w10, [x8, #0x38]')      # other env: +0x38/+0x3C (Duo +0x40/+0x44)
expect(0x1048668, 'tbnz w19, #0x1f, #0x104855c')   # lot -1: nothing
expect(0x104870C, 'stp w26, w28, [x8]')            # push {player key, item | category << 28, count}
expect(0x1048718, 'str x8, [x21, #0x28]')          #   into lobby-reward object +0x20 vector (12 bytes each)
expect(0x1145798, 'bl #0x1048120')
expect(0x11396E8, 'str x22, [x19, #0x4b48]')       # par+0x4B48 = lobby-reward object (0x88 bytes, 0x1047D20)
# Outcome: own entries -> result +0xFE0 (max 21 x 8 bytes), then granted to the LOCAL pgd inventory
expect(0x1132D34, 'bl #0x1048960')
expect(0x1141F90, 'ldr x3, [x28, #0x4b48]')
expect(0x11469E0, 'bl #0x1048040')
assert not fn_has_bda(0x1048040, 0x1048120), 'gate inside the grant'
assert not fn_has_bda(0x1048960, 0x1048AC0), 'gate inside the Outcome filter'
expect(0x1048064, 'ldr x8, [x8, #0x20]')           # GDM+0x20 = local PlayerGameData
expect(0x1048080, 'add x20, x8, #0x2e8')           # its inventory
expect(0x10480C8, 'bl #0xccae80')                  # item add
expect(0x1146924, 'cbnz x8, #0x1146a58')           # applied once per match (par+0x4708)
listing.append('  recorder gate 0x1048154; grant 0x1048040 and Outcome filter 0x1048960 have no gate')

free(0x1048154)
groups = {'REWARD_LOCAL': [(0x1048154, hexw(word(0x1048154)), hexw(NOP), True)]}
listing.append('  0x1048154  %s  ->  %s   (REWARD_LOCAL)' % (dis1(0x1048154), dis1(0x1048154, NOP)))
assert groups['REWARD_LOCAL'][0][1] == 'E83B0034', groups['REWARD_LOCAL'][0][1]

print('\n'.join(listing))

if '--write' in sys.argv:
    out = ['"""End-of-match patch group: (offset_from_main, orig_hex, new_hex, is_code). Generated by endgame_gen.py.',
           'Notes: endgame_notes.md. Not live-tested. Apply on EVERY game. No cave.',
           'REWARD_LOCAL: the post-match reward recorder 0x1048120 runs as offline (Bot Match). With the stock',
           'regulation no LobbyRewardParam lot is set, so nobody gets anything (same as Bot Match)."""', '']
    for g, rs in groups.items():
        out.append('%s = [  # 0x1048154 cbz +0xBDA -> nop' % g)
        for a, o, n, c in rs:
            out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
        out.append(']')
    out += ['', 'ORDER = [REWARD_LOCAL]']
    open(os.path.join(HERE, 'endgame_live.py'), 'w').write('\n'.join(out) + '\n')
    print('endgame_live.py written')
else:
    print('(endgame_live.py not written: no patch is needed with the stock regulation; use --write for parity)')
