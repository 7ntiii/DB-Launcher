"""Generator + checker for the kin rule groups in kin_rules_live.py. Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every other diag/net/*_live.py, writes kin_rules_live.py,
prints a capstone listing. python kin_rules_gen.py   (run from diag/net)

Groups (reasoning and [V]/[I] marks: kin_rules_notes.md). No cave is used.
  KIN_A4_PLAYERS  ro 0x4C4B8D0 routing of type 0xA4 (kin EXP record): 0x00 -> 0x20 = players only, so the
                  sender's self link no longer echoes the record back (the echo would add the EXP twice).
  KIN_STRENGTHEN  0x119E8C4 nop: small circle "Strengthen kin" (kin EXP processor, vtable 0x56F95F8, execute
                  slot 0xC8 = 0x119E880) grants its EXP in LAN too (was offline only).
  KIN_RELEASE     0x11A481C nop: 0x74 kind 2 (release the circle holder after the contract drama) is applied
                  in LAN too, so the presser's own game frees info+0x460 again.
  KIN_ITEM_EXP    0xE92FA8 nop: goods effect kind 18 (kin EXP item) gives kin EXP in LAN too. Optional:
                  apply only after the live test in kin_rules_notes.md section 7 (who runs 0xD00888)."""
import glob
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
RO_BASE = 0x492B000
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
OUT = os.path.join(HERE, 'kin_rules_live.py')
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
    if name in arrays:
        for i, bt in enumerate(arrays[name]):
            shipped[a + i] = (bt, name)
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- records of every other *_live.py
others = {}
for fn in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    if os.path.abspath(fn) == os.path.abspath(OUT):
        continue
    txt = open(fn, encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"', txt):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            others.setdefault(a + i, os.path.basename(fn))
print('other *_live.py bytes parsed: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)
    listing.append('  context 0x%x  %s' % (addr, got))


NOP = 0xD503201F
listing = []
groups = {}


def free(addr, n, what):
    for i in range(n):
        assert addr + i not in shipped, '%s collides with shipped %s at %x' % (what, shipped[addr + i][1], addr + i)
        assert addr + i not in others, '%s collides with %s at %x' % (what, others[addr + i], addr + i)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    free(addr, 4, 'text patch')
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def ro_byte(addr, expect, new, note):
    old = RO[addr - RO_BASE]
    assert old == expect, 'ro %x: %02x, expected %02x' % (addr, old, expect)
    free(addr, 1, 'ro patch')
    listing.append('  ro 0x%x  %02X -> %02X   (%s)' % (addr, old, new, note))
    return (addr, '%02X' % old, '%02X' % new, False)


# ================================================================ KIN_A4_PLAYERS
listing.append('=== KIN_A4_PLAYERS')
ROUTE = 0x4C4B3AC                        # {u32 type, u32 attribute} per type [V summon_struggle_notes]
a4 = ROUTE + 8 * 0xA4
assert struct.unpack_from('<I', RO, a4 - RO_BASE)[0] == 0xA4, 'routing table row is not type 0xA4'
assert struct.unpack_from('<I', RO, a4 + 4 - RO_BASE)[0] == 0, 'type 0xA4 attribute is not 0'
# same bit as the shipped TYPE36_PLAYERS (0x36: 0x04 -> 0x24): blocks only the send to the server member (self link)
assert shipped.get(ROUTE + 8 * 0x36 + 4, (None,))[0] == 0x24, 'TYPE36_PLAYERS precedent not shipped'
# sender 0x14E7C44 broadcasts with vt+0x40 (0x1CD8008 -> 0x1CD7C80) [V]; reader 0x14E7D70 uses vt+0x68 (every member) [V]
ctx(0x14E7D24, 'mov w1, #0xa4')
ctx(0x14E7D28, 'ldr x8, [x8, #0x40]')
ctx(0x14E7DE0, 'mov w1, #0xa4')
ctx(0x14E7DFC, 'ldr x9, [x9, #0x68]')
groups['KIN_A4_PLAYERS'] = [ro_byte(a4 + 4, 0x00, 0x20, 'type 0xA4 routing: players only, no self echo')]

# ================================================================ KIN_STRENGTHEN
listing.append('=== KIN_STRENGTHEN')
ctx(0x119E8B0, 'bl #0xe95300')                   # "kin exists and level < max" (pgd+0x4758[cur] < BuddyParam+0x4A)
ctx(0x119E8B4, 'tbz w0, #0, #0x119e8fc')         # no -> messages 2200000 / 2200001 (not gated)
ctx(0x119E8C0, 'ldrb w8, [x8, #0xbda]')
ctx(0x119EB5C, 'bl #0xe93f80')                   # EXP add for the presser (local apply + 0xA4 broadcast)
assert struct.unpack_from('<Q', open(os.path.join(N, 'main_data.bin'), 'rb').read(), 0x56F96C0 - 0x563F000)[0] == 0x119E880
groups['KIN_STRENGTHEN'] = [
    text_patch(0x119E8C4, 'cbz w8, #0x119ed08', NOP, 'small circle EXP also when +0xBDA == 0'),
]

# ================================================================ KIN_RELEASE
listing.append('=== KIN_RELEASE')
ctx(0x11A46DC, 'cmp w9, #2')
ctx(0x11A46E0, 'b.eq #0x11a4810')
ctx(0x11A4818, 'ldrb w9, [x9, #0xbda]')
ctx(0x11A4820, 'ldr w9, [x8, #0x460]')
ctx(0x11A48B8, 'str w9, [x8, #0x460]')           # holder = -1 when the requester is the holder (or either is -1)
groups['KIN_RELEASE'] = [
    text_patch(0x11A481C, 'cbz w9, #0x11a49c4', NOP, '0x74 kind 2: free the circle holder in LAN too'),
]

# ================================================================ KIN_ITEM_EXP (optional)
listing.append('=== KIN_ITEM_EXP (optional)')
ctx(0xE92FA4, 'ldrb w8, [x8, #0xbda]')
ctx(0xE93074, 'bl #0xe93f80')
jt = struct.unpack_from('<H', RO, 0x4C482B8 - RO_BASE + 2 * (18 - 2))[0]
assert 0xE92998 + 4 * jt == 0xE92F9C, 'effect kind 18 does not jump to 0xE92F9C'
groups['KIN_ITEM_EXP'] = [
    text_patch(0xE92FA8, 'cbz w8, #0xe92c10', NOP, 'goods effect kind 18: kin EXP also when +0xBDA == 0'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['KIN_A4_PLAYERS', 'KIN_STRENGTHEN', 'KIN_RELEASE']
notes = {
    'KIN_A4_PLAYERS': 'kin EXP record 0xA4 to the players only (no self echo = no double EXP on the sender)',
    'KIN_STRENGTHEN': 'small circle "Strengthen kin": EXP in LAN (presser game, then 0xA4 to the others)',
    'KIN_RELEASE': 'circle holder released after the contract drama in LAN (presser game only)',
    'KIN_ITEM_EXP': 'OPTIONAL, not in ORDER: kin EXP from goods effect kind 18 in LAN (test first)',
}
out = ['"""Kin rule groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by kin_rules_gen.py (original-word checks, capstone listing, overlap checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). No caves. Not live-tested. Notes: kin_rules_notes.md.',
       'Apply on EVERY game (no group is host-only). Needs the shipped KIN_* records and kincircle_live.py',
       '(KIN_PRESS / KIN_EXEC / KIN_CONTRACT) for the press path. KIN_ITEM_EXP is optional (not in ORDER)."""', '']
for g in ['KIN_A4_PLAYERS', 'KIN_STRENGTHEN', 'KIN_RELEASE', 'KIN_ITEM_EXP']:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, nw, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
    out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(OUT, 'w').write('\n'.join(out) + '\n')
print('kin_rules_live.py written')
