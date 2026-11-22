"""Generator + checker for the ritual-site Virtue groups in site_virtue_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes site_virtue_live.py).
python site_virtue_gen.py

No caves (cave space is exhausted): every record is a one-word text change or a one-byte ro routing change.
Design and [V]/[I] marks: site_virtue_notes.md.

  SWORD_B0_ALL       kill report 0xB0 (victim's game -> "server") goes to everyone; routing 0x40 -> 0x00.
                     Every game then runs 0xE96C90 -> 0x10920C0 -> 0xE96320 once, so the KILLER's own game
                     records 10020 (CSShelterInsideKill) on its local pgd and the ALLY's own game records 10040.
                     Same pattern as the shipped DUSK_KILL_SEND_ALL / DUSK_TYPE9C_ALL (0x9C). The reader
                     0x14E8730 already reads from anyone (vt+0x68).
  PLEDGE_B8_ALL      pledge messages 0xB8 (both senders) go to everyone; routing 0x40 -> 0x00.
                     Reader in 0x109EEA0 already reads from anyone (vt+0x68).
  PLEDGE_COMPLETE    0x109F4D0 cmp w8,#0 -> cmp w8,#0x100 (always ne): the swear timer can complete in LAN
                     (stock: offline only), so kind 4 (owner := signer, 100000/100020 records) is sent.
                     Kind 4 is idempotent (needs entry+0x10 == pno, then sets +0x10 = -1) [V].
  PLEDGE_SIGNER_GONE optional: 0x109EFC8 nop, the "signer has no chr / match not in play" kind-6 cancel runs in LAN.
  REDSTONE_TICK      0x109DA80 nop: a team holding a redstone accrues counter 10030 every PhaseInfo+0xB4 s
                     (stock: offline only). Runs per player entry on every game; copies count 0, so each
                     player is credited once on its own game [I: 10030 class name not confirmed].
Apply on EVERY game. Order inside a group: ro routing first, then the senders."""
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
OUT = 'site_virtue_live.py'
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
ROUTING = 0x4C4B3B0       # u32 routing word of message type t at ROUTING + 8*t

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
        shipped[a + i] = (bt, name)
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other helper's *_live.py
others = {}
for fn in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    if os.path.basename(fn) == OUT:
        continue
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"', open(fn, errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(max(1, len(new) // 2)):
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


def free(addr, n):
    for i in range(n):
        assert addr + i not in shipped, 'collides with shipped %s at %x' % (shipped[addr + i][1], addr)
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)


NOP = 0xD503201F
LDR_X8_40 = 0xF9402108    # ldr x8, [x8, #0x40]  (broadcast)
listing = []
groups = {}


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    free(addr, 4)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def route_patch(mtype, old, new, note):
    addr = ROUTING + 8 * mtype
    o = addr - RO_BASE
    assert RO[o] == old, 'routing of 0x%X at %x is %02x, expected %02x' % (mtype, addr, RO[o], old)
    free(addr, 1)
    listing.append('  0x%x  routing 0x%X: %02x -> %02x   (%s)' % (addr, mtype, old, new, note))
    return (addr, '%02X' % old, '%02X' % new, False)


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


# ================================================================ 1. SWORD_B0_ALL
listing.append('=== SWORD_B0_ALL')
ctx(0x14E85DC, 'mov w1, #0xb0')
ctx(0x14E85E8, 'blr x8')
groups['SWORD_B0_ALL'] = [
    route_patch(0xB0, 0x40, 0x00, 'kill report: everyone, self link included'),
    text_patch(0x14E85E4, 'ldr x8, [x8, #0x48]', LDR_X8_40, '0x14E8484 online send: broadcast'),
]
# the reader reads from anyone already
ctx(0x14E879C, 'mov w1, #0xb0')
ctx(0x14E87BC, 'ldr x9, [x9, #0x68]')     # handler from anyone (the server-only 0xAE handler 0x14E81B8 uses #0x60)

# ================================================================ 2. PLEDGE_B8_ALL
listing.append('=== PLEDGE_B8_ALL')
ctx(0x10A0514, 'mov w1, #0xb8')
ctx(0x109FA20, 'mov w1, #0xb8')
groups['PLEDGE_B8_ALL'] = [
    route_patch(0xB8, 0x40, 0x00, 'pledge kinds 0..6: everyone, self link included'),
    text_patch(0x10A051C, 'ldr x8, [x8, #0x48]', LDR_X8_40, 'request sender 0x10A0404: broadcast'),
    text_patch(0x109FA24, 'ldr x8, [x8, #0x48]', LDR_X8_40, 'completion (kind 4) sender: broadcast'),
]

# ================================================================ 3. PLEDGE_COMPLETE
listing.append('=== PLEDGE_COMPLETE')
ctx(0x109F4CC, 'ldrb w8, [x8, #0xbda]')
ctx(0x109F4D4, 'fccmp s0, s9, #8, ne')
ctx(0x109F4D8, 'b.lt #0x109f4a0')
groups['PLEDGE_COMPLETE'] = [
    text_patch(0x109F4D0, 'cmp w8, #0', 0x7104011F, 'byte vs 0x100 is always ne: timer >= need completes in LAN'),
]
assert dis1(0x109F4D0, 0x7104011F) == 'cmp w8, #0x100'
# kind-4 handler idempotency context: needs +0x10 == pno
ctx(0x10A2C00, 'ldr w8, [x19, #0x10]')
ctx(0x10A2C04, 'cmp w8, w23')

# ================================================================ 4. PLEDGE_SIGNER_GONE (optional)
listing.append('=== PLEDGE_SIGNER_GONE')
ctx(0x109EFC4, 'ldrb w8, [x8, #0xbda]')
ctx(0x109F170, 'bl #0x10a0404')
groups['PLEDGE_SIGNER_GONE'] = [
    text_patch(0x109EFC8, 'cbz w8, #0x109f178', NOP, 'kind-6 cancel when the signer has no chr / match not in play'),
]

# ================================================================ 5. REDSTONE_TICK
listing.append('=== REDSTONE_TICK')
ctx(0x109DA7C, 'ldrb w8, [x8, #0xbda]')
groups['REDSTONE_TICK'] = [
    text_patch(0x109DA80, 'cbz w8, #0x109db64', NOP, 'held redstone accrues counter 10030 (0x109E180, id 0x272E)'),
]
ctx(0x109E298, 'mov w1, #0x272e')

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['SWORD_B0_ALL', 'PLEDGE_B8_ALL', 'PLEDGE_COMPLETE', 'REDSTONE_TICK', 'PLEDGE_SIGNER_GONE']
notes = {
    'SWORD_B0_ALL': 'kill report 0xB0 to everyone: Sword (10020) on the killer\'s game, ally share (10040) on the ally\'s game',
    'PLEDGE_B8_ALL': 'pledge 0xB8 kinds to everyone (both senders + routing)',
    'PLEDGE_COMPLETE': 'swear timer completes in LAN (needs PLEDGE_B8_ALL)',
    'REDSTONE_TICK': 'held redstone accrues 10030 over time in LAN',
    'PLEDGE_SIGNER_GONE': 'optional: cancel a sign whose signer is gone (needs PLEDGE_B8_ALL)',
}
out = ['"""Ritual-site Virtue groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by site_virtue_gen.py (original-word checks, capstone listing, collision checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). No caves. Not live-tested. Notes: site_virtue_notes.md.',
       'is_code False = one ro routing byte. Apply on EVERY game; inside a group the routing byte goes first."""', '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, OUT), 'w').write('\n'.join(out) + '\n')
print(OUT + ' written')
