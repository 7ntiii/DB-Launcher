"""Generator + checker for the rule-set group in rules_live.py. Static only (reads nso/*.bin and
src/lichii/src/core/file_sys/patch_manager.cpp, writes rules_live.py, prints a listing).
python rules_gen.py          (run from diag/net)

Group (design: rulesets_notes.md 2b; what was added: rules_fix_notes.md):
  RULE_KEEP  0x113F380 nop: the stage ctor 0x113EE80 no longer clears the rule byte main+0x5B65C70 at every
             match load, so the value the assist writes (the host's menu choice) is still there when STEP_Init
             (0x11477D0 PhaseInfo) and STEP_MatchPreprocess read it. The assist (dusk_lan.cpp RuleShare)
             only touches the byte when it finds this nop in the game, and writes 0 back when the session ends.

Checks made here:
  - the word at 0x113F380 is `strb wzr, [x8]` with x8 = GOT 0x59E0A70 (loaded at 0x113F378) and the GOT slot
    holds 0x5B65C70;
  - every writer of the byte in main text (GOT loads of 0x59E0A70 and adrp 0x5B65000 + 0xC70) is listed; the
    only ones are the ctor reset, the single-play copy 0x1147608 (STEP_Init, skipped while the session has
    members) and the server message 0x19 apply 0x14DEB88: nothing else clears the byte per match;
  - no collision with a shipped record of patch_manager.cpp."""
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
DATA = open(os.path.join(N, 'main_data.bin'), 'rb').read()
DATA_BASE = 0x563F000
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
md.detail = False

RULE = 0x5B65C70
RULE_GOT = 0x59E0A70
NOP = 0xD503201F

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
shipped = set()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    arrays[m.group(2)] = int(m.group(1))
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    for i in range(arrays.get(name, 4)):
        shipped.add(a + i)
print('shipped bytes parsed: %d' % len(shipped))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def adrp_page(pc, w):
    """Target page of an adrp word, or None."""
    if (w & 0x9F000000) != 0x90000000:
        return None
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12), w & 31


listing = []

# ================================================================ GOT slot
got = struct.unpack_from('<Q', DATA, RULE_GOT - DATA_BASE)[0]
assert got == RULE, 'GOT 0x%X holds 0x%X, expected the rule byte 0x%X' % (RULE_GOT, got, RULE)
listing.append('GOT 0x%X -> 0x%X (rule byte)' % (RULE_GOT, got))

# ================================================================ writers of the rule byte
writers = []
for o in range(0, len(TXT) - 3, 4):
    w = word(o)
    reg = None
    if (w & 0xFFC00000) == 0xF9400000 and ((w >> 10) & 0xFFF) * 8 == (RULE_GOT & 0xFFF):
        # ldr xT, [xN, #0xa70]: xN must come from adrp page 0x59E0000
        rn, rt = (w >> 5) & 31, w & 31
        for back in range(1, 12):
            p = adrp_page(o - back * 4, word(o - back * 4)) if o >= back * 4 else None
            if p and p[1] == rn:
                if p[0] == RULE_GOT & ~0xFFF:
                    reg = rt
                break
    elif (w & 0xFF800000) == 0x91000000 and ((w >> 10) & 0xFFF) == (RULE & 0xFFF) and ((w >> 22) & 1) == 0:
        rn, rd = (w >> 5) & 31, w & 31            # add xD, xN, #0xc70
        for back in range(1, 12):
            p = adrp_page(o - back * 4, word(o - back * 4)) if o >= back * 4 else None
            if p and p[1] == rn:
                if p[0] == RULE & ~0xFFF:
                    reg = rd
                break
    elif (w & 0xFFC00000) == 0x39000000 and ((w >> 10) & 0xFFF) == (RULE & 0xFFF):
        rn = (w >> 5) & 31                        # strb wT, [xN, #0xc70] straight off the page
        for back in range(1, 12):
            p = adrp_page(o - back * 4, word(o - back * 4)) if o >= back * 4 else None
            if p and p[1] == rn:
                if p[0] == RULE & ~0xFFF:
                    writers.append(o)
                break
        continue
    if reg is None:
        continue
    # forward: strb / str / stur to [reg] before reg is redefined
    for fwd in range(1, 16):
        a = o + fwd * 4
        x = word(a)
        if (x & 0xFFC00000) in (0x39000000, 0x79000000, 0xB9000000) and ((x >> 5) & 31) == reg \
                and ((x >> 10) & 0xFFF) == 0:
            writers.append(a)
            break
        if (x & 0xFFE00C00) == 0x38000000 and ((x >> 5) & 31) == reg:     # sturb [reg, #imm9]
            writers.append(a)
            break
        if (x & 31) == reg and (x & 0xFFC00000) not in (0x39400000, 0x39000000, 0xB9000000, 0xB9400000):
            # a write to reg (most data-processing / load forms put Rd/Rt in bits 0..4): stop
            ins = list(md.disasm(struct.pack('<I', x), a))
            if ins and not ins[0].mnemonic.startswith(('st', 'cb', 'tb', 'cmp', 'b')):
                break
        if (x & 0xFC000000) in (0x14000000, 0x94000000) or (x & 0xFFFFFC1F) in (0xD65F0000, 0xD65F0BFF):
            break
writers = sorted(set(writers))
listing.append('writers of main+0x%X:' % RULE)
for a in writers:
    listing.append('  0x%x  %s' % (a, dis1(a, word(a))))
EXPECTED = {0x113F380: 'stage ctor 0x113EE80: per-match reset (RULE_KEEP)',
            0x1147608: 'STEP_Init 0x11474C0: single-play copy of 0x5B65C4C, only when the session has no members',
            0x14DEB88: 'server message 0x19 apply (session pump 0x14DD180; never sent in LAN)'}
assert set(writers) == set(EXPECTED), 'writer set changed: %s' % [hex(a) for a in writers]
for a, why in EXPECTED.items():
    listing.append('    0x%x = %s' % (a, why))

# single-play gate: the copy is skipped while mgr3 has members (b.gt over it)
assert dis1(0x11475D8, word(0x11475D8)) == 'b.gt #0x114761c'
assert dis1(0x11475F8, word(0x11475F8)) == 'ldr x11, [x11, #0xa70]'
# first reader after the ctor: STEP_Init's PhaseInfo build (bl 0x113DEE0); the ctor's own build is before
# the reset (0x113F0A0), so a value written before the ctor is used there too
assert dis1(0x11477D0, word(0x11477D0)) == 'bl #0x113dee0'
assert dis1(0x113F0A0, word(0x113F0A0)) == 'bl #0x113dee0'
# the alliance-request gate (No Alliances): AM+0x8C | rule
assert dis1(0x10B16FC, word(0x10B16FC)) == 'ldrb w8, [x8]'
assert dis1(0x10B1700, word(0x10B1700)) == 'orr w8, w9, w8'
# host menu: room+0xE4 = mask, room = *(*(main+0x5B44248)+0xC0) (confirm functor 0x141F220)
assert dis1(0x141F35C, word(0x141F35C)) == 'add x8, x8, #0x248'
assert dis1(0x141F368, word(0x141F368)) == 'ldr x8, [x8, #0xc0]'
assert dis1(0x141F36C, word(0x141F36C)) == 'str w10, [x8, #0xe4]'
listing.append('readers checked: ctor 0x113F0A0 (before the reset), STEP_Init 0x11477D0, petitions 0x10B16FC; '
               'menu mask store 0x141F36C')

# ================================================================ RULE_KEEP
listing.append('=== RULE_KEEP')
A = 0x113F380
assert dis1(0x113F370, word(0x113F370)) == 'adrp x8, #0x59e0000'
assert dis1(0x113F378, word(0x113F378)) == 'ldr x8, [x8, #0xa70]'
old = word(A)
assert dis1(A, old) == 'strb wzr, [x8]', dis1(A, old)
assert hexw(old) == '1F010039'
assert not any(A + i in shipped for i in range(4)), 'RULE_KEEP collides with a shipped record'
# x8 is reloaded before its next use (0x113F390 mov w8, #0xf): the nop changes nothing else
assert dis1(0x113F390, word(0x113F390)) == 'mov w8, #0xf'
listing.append('  0x%x  %s  ->  %s   (stage ctor keeps the rule byte)' % (A, dis1(A, old), dis1(A, NOP)))
groups = {'RULE_KEEP': [(A, hexw(old), hexw(NOP), True)]}

print('\n'.join(listing))

out = ['"""Rule-set patch group: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by rules_gen.py (original-word check, writer scan of main+0x5B65C70, collision check against',
       'patch_manager.cpp). Not live-tested. Design: rulesets_notes.md; assist side: rules_fix_notes.md.',
       'Apply on EVERY game. The assist (dusk_lan.cpp RuleShare) writes the rule byte only while this word is the nop.',
       'Live: PATCH_FILE=diag/net/rules_live.py python diag/twin/apply_groups.py AB RULE_KEEP"""', '']
out.append('RULE_KEEP = [  # stage ctor 0x113EE80 no longer clears the rule byte main+0x5B65C70 per match load')
for a, o, n, c in groups['RULE_KEEP']:
    out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
out.append(']')
out.append('')
out.append('ORDER = [RULE_KEEP]')
open(os.path.join(HERE, 'rules_live.py'), 'w').write('\n'.join(out) + '\n')
print('rules_live.py written')
