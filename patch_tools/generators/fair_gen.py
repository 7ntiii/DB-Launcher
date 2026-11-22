"""Generator + checker for the fairness groups in fair_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/**/*_live.py, writes fair_live.py, prints a capstone
listing of every new word).  python fair_gen.py   (run from diag/net)

Groups (design, [V]/[I] marks and live tests: fair_notes.md):
  STAKE_REFILL_CAVE / STAKE_REFILL  the stake/level/blood commit 0xCFE2C0 (death refill 0xD1D5F4, match reset
                      0xD1D8B0, top-up 0x17BD69C) runs in LAN like offline, but never for a remote copy
                      (pgd+0x40D0 == 2).  Online the server did this commit and answered B3 subtype 13.
  STAKE_TOPUP         optional: the top-up 0x17BD69C ("below base -> base") also passes its own +0xBDA gate.
  CUTSCENE_REVERT     removes the shipped CUTSCENE record (0x11B932C back to b.ne): everyone watches, as before v3.1.
Cave: main+0x563EAE0..0x563EAFF (ro padding past the ro file end; zero, no branch/pointer reaches it, not used by
any *_live.py, not in patch_manager.cpp)."""
import glob
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

# ---------------------------------------------------------------- every other helper's *_live.py record
others = {}   # byte address -> file
for f in glob.glob(os.path.join(HERE, '..', '**', '*_live.py'), recursive=True):
    if os.path.basename(f) == 'fair_live.py':
        continue
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"', open(f, encoding='utf-8', errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(max(len(new) // 2, 4)):
            others[a + i] = os.path.basename(f)
print('other *_live.py bytes parsed: %d' % len(others))


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return bytes(shipped[a + i] for i in range(4))


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


EQ, NE = 0, 1
NOP = 0xD503201F
CAVE_LO, CAVE_HI = 0x563EAE0, 0x563EB00

listing = []
groups = {}


def free_of_others(addr, n=4):
    for i in range(n):
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    assert not any(addr + i in shipped for i in range(4)), 'collides with a shipped record at %x' % addr
    free_of_others(addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def cave(name, start, ws):
    for i in range(len(ws)):
        a = start + i * 4
        assert CAVE_LO <= a < CAVE_HI, 'cave word %x outside the free slot' % a
        o = a - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % a
        assert not any(a + j in shipped for j in range(4)), 'cave collides with shipped record at %x' % a
        free_of_others(a)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        listing.append('  0x%x %s' % (start + i * 4, dis1(start + i * 4, w)))
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)]


# ---------------------------------------------------------------- the whole free slot is unreferenced
def slot_refs(lo, hi):
    hits = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            if lo <= o + imm * 4 < hi:
                hits.append(('branch', o))
    for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 8):
            v = struct.unpack_from('<Q', seg, o)[0]
            if lo <= v < hi:
                hits.append(('pointer', base + o))
    return hits


refs = slot_refs(CAVE_LO, CAVE_HI)
assert not refs, 'cave slot referenced: %r' % refs[:5]
for a in range(CAVE_LO, CAVE_HI):
    o = a - RO_BASE
    assert o >= len(RO) or RO[o] == 0
    assert a not in shipped and a not in others, 'slot byte %x in use' % a
listing.append('cave slot 0x%X..0x%X: zero, no branch/pointer, not shipped, not in any *_live.py' % (CAVE_LO, CAVE_HI - 1))

# ================================================================ 1. STAKE_REFILL
listing.append('=== STAKE_REFILL')
# 0xCFE2C0(mgr, &playerNo, count, level, blood, w5, w6): offline commit of a stake / level / blood change
for a, t in ((0xCFE2E8, 'ldrb w8, [x8, #0xbda]'), (0xCFE304, 'bl #0xcf3f08'), (0xCFE308, 'ldr x20, [sp, #8]'),
             (0xCFE314, 'cbz x20, #0xcfe40c'), (0xCFE31C, 'mov w1, w25'), (0xCFE320, 'mov x0, x24'),
             (0xCFE324, 'bl #0xd17668'), (0xCFE32C, 'adrp x8, #0x59e0000'), (0xCFE3E0, 'bl #0xcf9d20'),
             (0xCFE3E4, 'ldr x0, [sp, #0x10]'), (0xCFE40C, 'mov w0, w19'),
             # callers that compute the real-game result and hand it to 0xCFE2C0
             (0xD1D7F4, 'bl #0xcfe2c0'), (0xD1D968, 'bl #0xcfe2c0'), (0x17BE690, 'bl #0xcfe2c0'),
             # the server's answer path: B3 subtype 13/15 builder 0xCF9D20 -> loopback 0x1CD8014 -> 0xCFE848 (pgd+0x40D0 == 1)
             (0xCF9DE0, 'bl #0x1cd8014'), (0xCFE888, 'cmp w8, #1'), (0xD051B4, 'bl #0xcfe848')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
ST = 0x563EAE0
st_words = [
    0xF9400A98,                         # ldr x24, [x20, #0x10]      (moved: pgd of the slot)
    0x91401308,                         # add x8, x24, #4, lsl #12   (pgd + 0x4000)
    0x39434108,                         # ldrb w8, [x8, #0xd0]       (pgd + 0x40D0: 1 local, 2 remote copy)
    0x7100091F,                         # cmp w8, #2
    bcond(ST + 0x10, ST + 0x18, NE),    # b.ne -> continue
    b(ST + 0x14, 0xCFE3E4),             # remote copy: release the slot reference and return, nothing written
    b(ST + 0x18, 0xCFE31C),             # back: mov w1, w25 ...
]
assert dis1(ST, st_words[0]) == 'ldr x24, [x20, #0x10]'
assert dis1(ST + 4, st_words[1]) == 'add x8, x24, #4, lsl #12'
assert dis1(ST + 8, st_words[2]) == 'ldrb w8, [x8, #0xd0]'
assert dis1(ST + 12, st_words[3]) == 'cmp w8, #2'
groups['STAKE_REFILL_CAVE'] = cave('STAKE_LOCAL', ST, st_words)
groups['STAKE_REFILL'] = [
    text_patch(0xCFE318, 'ldr x24, [x20, #0x10]', b(0xCFE318, ST), 'slot pgd -> STAKE_LOCAL (skip remote copies)'),
    text_patch(0xCFE2EC, 'cbz w8, #0xcfe408', NOP, 'offline gate: commit runs in LAN'),
]

# ================================================================ 2. STAKE_TOPUP (optional)
listing.append('=== STAKE_TOPUP (optional)')
for a, t in ((0x17BE618, 'cmp w8, w22'), (0x17BE61C, 'b.hs #0x17be4e4'), (0x17BE62C, 'cbz x23, #0x17be6b8'),
             (0x17BE638, 'ldrb w8, [x8, #0xbda]')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
groups['STAKE_TOPUP'] = [
    text_patch(0x17BE63C, 'cbz w8, #0x17be4e4', NOP, 'top-up below base -> 0xCFE2C0 in LAN (needs STAKE_REFILL)'),
]

# ================================================================ 3. CUTSCENE_REVERT
listing.append('=== CUTSCENE_REVERT')
sw = struct.unpack('<I', shipped_word(0x11B932C))[0]
assert dis1(0x11B932C, sw) == 'b #0x11b94b8', 'CUTSCENE not shipped as expected'
assert dis1(0x11B932C, word(0x11B932C)) == 'b.ne #0x11b94b8'
groups['CUTSCENE_REVERT'] = [(0x11B932C, hexw(sw), hexw(word(0x11B932C)), True)]
listing.append('  0x11b932c  %s  ->  %s   (shipped CUTSCENE removed: mode 6 sends the 0x25 vote again)'
               % (dis1(0x11B932C, sw), dis1(0x11B932C, word(0x11B932C))))

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['STAKE_REFILL_CAVE', 'STAKE_REFILL', 'CUTSCENE_REVERT']
notes = {
    'STAKE_REFILL_CAVE': '[V code] own-copy check for 0xCFE2C0 (inert until STAKE_REFILL)',
    'STAKE_REFILL': '[V code, I live] death refill / match reset commit 0xCFE2C0 runs in LAN, local copy only',
    'STAKE_TOPUP': '[I] OPTIONAL, after STAKE_REFILL: top-up 0x17BD69C also passes its own +0xBDA gate',
    'CUTSCENE_REVERT': '[V] remove the shipped CUTSCENE record (orig = shipped word, new = stock word)',
}
out = ['"""Fairness patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by fair_gen.py (original-word checks, capstone listing of every new word, collision checks against',
       'patch_manager.cpp and every *_live.py). Not live-tested. Design + live tests: fair_notes.md.',
       'Cave records have orig "00000000" (zero padding past the ro file end, slot 0x563EAE0..0x563EAFB).',
       'CUTSCENE_REVERT undoes a SHIPPED record: its orig is the shipped word; in the build, delete the CUTSCENE record instead.',
       'Apply STAKE_REFILL_CAVE before STAKE_REFILL; inside STAKE_REFILL the hook comes before the gate nop.',
       'Apply on EVERY game (no group is host-only)."""', '']
for g in ORDER + ['STAKE_TOPUP']:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]  # STAKE_TOPUP optional, after the STAKE_REFILL live test' % ', '.join(ORDER))
open(os.path.join(HERE, 'fair_live.py'), 'w').write('\n'.join(out) + '\n')
print('fair_live.py written')
