"""Generator + checker for stake2_live.py (Goldblood Stake refill in LAN, second pass). Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/**/*_live.py, writes stake2_live.py, prints a capstone
listing.   python stake2_gen.py   (run from diag/net)

Design, [V]/[I] marks and the live test: stake2_notes.md.
  STAKE_TOPUP  revive top-up in 0x17BD69C (count < base -> base, local player, was dead, chr+0x2618 == 0) passes its
               own +0xBDA gate 0x17BE63C. Identical to fair_live.py STAKE_TOPUP. Needs the built-in STAKE_REFILL
               (0xCFE2EC nop + 0xCFE318 -> cave 0x563EAE0 "skip pgd type 2"), asserted below.
  STAKE_PHASE  OPTIONAL: STEP_BeginPhase 0x114A4A0 runs its offline per-player reset/refill (0x114A7A0 nop)."""
import glob
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
NOP = 0xD503201F

# ---------------------------------------------------------------- shipped records
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

# ---------------------------------------------------------------- other *_live.py records: addr -> (file, new hex)
others = {}
for f in glob.glob(os.path.join(HERE, '..', '**', '*_live.py'), recursive=True):
    if os.path.basename(f) == 'stake2_live.py':
        continue
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"',
                         open(f, encoding='utf-8', errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3).upper()
        others.setdefault(a, []).append((os.path.basename(f), new))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return struct.unpack('<I', bytes(shipped[a + i] for i in range(4)))[0]


def expect(pairs):
    for a, t in pairs:
        got = dis1(a, word(a))
        assert got == t, 'at %x: %s, expected %s' % (a, got, t)


listing = []


def text_patch(addr, exp, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == exp, 'at %x: %s, expected %s' % (addr, got, exp)
    assert not any(addr + i in shipped for i in range(4)), 'collides with a shipped record at %x' % addr
    for a in range(addr - 3, addr + 4):
        for f, n in others.get(a, []):
            # the same record in fair_live.py (STAKE_TOPUP) is allowed; anything else is a collision
            assert a == addr and n == hexw(new), 'collides with %s at %x (%s)' % (f, a, n)
            listing.append('  note: same record already in %s (identical)' % f)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


# ---------------------------------------------------------------- built-in STAKE_REFILL must be there
assert shipped_word(0xCFE2EC) == NOP, 'STAKE_REFILL gate nop 0xCFE2EC not built in'
assert dis1(0xCFE318, shipped_word(0xCFE318)) == 'b #0x563eae0', 'STAKE_REFILL hook 0xCFE318 not built in'
cave = [shipped_word(0x563EAE0 + 4 * i) for i in range(7)]
assert [dis1(0x563EAE0 + 4 * i, w) for i, w in enumerate(cave)] == [
    'ldr x24, [x20, #0x10]', 'add x8, x24, #4, lsl #12', 'ldrb w8, [x8, #0xd0]', 'cmp w8, #2',
    'b.ne #0x563eaf8', 'b #0xcfe3e4', 'b #0xcfe31c'], 'STAKE_REFILL_CAVE not built in as expected'
listing.append('built-in STAKE_REFILL + STAKE_REFILL_CAVE present (0xCFE2EC nop, 0xCFE318 -> 0x563EAE0, type-2 skip)')

# ---------------------------------------------------------------- 1. STAKE_TOPUP
listing.append('=== STAKE_TOPUP')
# revive virtual 0x17BD69C = data slot 0x572CF88, called from the warp executor 0xDA53BC
assert struct.unpack_from('<Q', DATA, 0x572CF88 - DATA_BASE)[0] == 0x17BD69C, 'vt slot 0x572CF88'
expect([(0xDA55B8, 'ldr x8, [x8, #0x7f8]'), (0xDA55BC, 'blr x8'), (0xDA55F4, 'strb wzr, [x19, #0x2c0]'),
        # only the was-dead, not-out, local-player branch reaches the top-up
        (0x17BDD4C, 'ldrb w9, [x25, #0x28]'), (0x17BDD50, 'tbz w9, #1, #0x17bdd8c'),
        (0x17BDD84, 'cbz w8, #0x17bde3c'), (0x17BDE54, 'strb w8, [x25, #0x28]'),
        (0x17BE114, 'cmp x8, x19'), (0x17BE118, 'b.ne #0x17be4e4'),
        (0x17BE4DC, 'ldrb w8, [x22, #0x30]'), (0x17BE4E0, 'cbz w8, #0x17be58c'),
        # count < base -> commit 0xCFE2C0 with the slot pgd's own level / blood
        (0x17BE614, 'ldrb w8, [x21, x8]'), (0x17BE618, 'cmp w8, w22'), (0x17BE61C, 'b.hs #0x17be4e4'),
        (0x17BE62C, 'cbz x23, #0x17be6b8'), (0x17BE638, 'ldrb w8, [x8, #0xbda]'),
        (0x17BE66C, 'bl #0xcf3f08'), (0x17BE68C, 'ldp w3, w4, [x8, #0x78]'), (0x17BE690, 'bl #0xcfe2c0')])
groups = {'STAKE_TOPUP': [text_patch(0x17BE63C, 'cbz w8, #0x17be4e4', NOP,
                                     'revive top-up -> 0xCFE2C0 in LAN (built-in STAKE_REFILL does the write)')]}

# ---------------------------------------------------------------- 2. STAKE_PHASE (optional)
listing.append('=== STAKE_PHASE (optional)')
assert struct.unpack_from('<Q', DATA, 0x56F4E60 - DATA_BASE)[0] == 0x115D100, 'functor slot 0x56F4E60'
expect([(0x114A658, 'ldr x21, [x21, #0xb28]'), (0x114A794, 'cbz x8, #0x114a7fc'),
        (0x114A79C, 'ldrb w8, [x8, #0xbda]'), (0x114A7AC, 'ldr x8, [x19, #0x3388]'),
        (0x114A7B4, 'add x9, x9, #0xe30'), (0x114A7DC, 'bl #0x17f1320'),
        (0x115D12C, 'cbz w8, #0x115d14c'), (0x115D13C, 'b #0xd1d8b0'), (0x115D158, 'b #0xd1d5f4'),
        (0xD1D7F4, 'bl #0xcfe2c0'), (0xD1D968, 'bl #0xcfe2c0')])
groups['STAKE_PHASE'] = [text_patch(0x114A7A0, 'cbz w8, #0x114a848', NOP,
                                    'BeginPhase: offline per-player reset/refill in LAN (own pgd only via the cave)')]

seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x' % (a + i)
            seen[a + i] = g
print('\n'.join(listing))

notes = {
    'STAKE_TOPUP': '[V code, I live] revive top-up (count < base -> base) runs in LAN; same as fair_live.py STAKE_TOPUP',
    'STAKE_PHASE': '[V code, I rule] OPTIONAL: phase-start reset/refill (StagePhase+0x3388 picks reset) runs in LAN',
}
out = ['"""Goldblood Stake refill groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian.',
       'Generated by stake2_gen.py (original-word checks, built-in STAKE_REFILL asserted, collision checks against',
       'patch_manager.cpp and every *_live.py). Not live-tested. Design + live test: stake2_notes.md.',
       'Needs the built-in STAKE_REFILL + STAKE_REFILL_CAVE. Apply on EVERY game (no group is host-only)."""', '']
for g in ('STAKE_TOPUP', 'STAKE_PHASE'):
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [STAKE_TOPUP]  # STAKE_PHASE optional, only after the STAKE_TOPUP live test and a watched phase change')
open(os.path.join(HERE, 'stake2_live.py'), 'w').write('\n'.join(out) + '\n')
print('stake2_live.py written')
