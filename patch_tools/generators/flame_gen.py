"""Generator + checker for the Flame corpse / action-menu sharing groups in flame_live.py. Static only (reads
nso/*.bin and src/lichii/src/core/file_sys/patch_manager.cpp, writes flame_live.py, prints a capstone listing).
python flame_gen.py      (run from diag/net)

Design (flame_items_notes.md):
  ACTION_SHARE  Every action-menu request (message 0x74 kind 1 {player no, asset handle}: Flame corpses, Alchemy
                Forges, kin circles, small circles, the "Pick up" kinds 3/9/12) goes to EVERY member instead of
                the server member (in LAN = self only), and every game runs the offline server branch of the
                0x74 receiver for every requester (the shipped KIN_PRESS hook, which granted only the local
                player's own request, becomes a nop). Each game then marks the asset exactly as the requester's
                game does (per-player bit info+0x468, "taken" byte info+0x470, holder info+0x460) and runs the
                processor's execute for the requesting chr (Flame: that player's own Virtue counter 110000 / 110010
                on that game's copy; notices/sounds only for the local player).
                No cave. 2 words.
  FORGE_TEST    (test only, NOT in ORDER) the Alchemy Forge reward runs in LAN: 0x11A06E4 (forge apply 0x11A06B4)
                and the non-flask gate 0xCF8F74 of the item grant 0xCF8E2C. 0xCF8F74 is shared by 18 callers;
                read the notes before using it.
No cave is used. No routing-byte change is needed (0x74 routing byte main+0x4C4B750 is already 0x00 = all)."""
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
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

NOP = 0xD503201F
ROUTE_74 = 0x4C4B3B0 + 0x74 * 8      # routing table entry of type 0x74 (first byte = attribute) [V]

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}   # byte address -> shipped byte
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name not in arrays:
        continue
    for i, bt in enumerate(arrays[name]):
        shipped[a + i] = bt
print('shipped bytes parsed: %d' % len(shipped))


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return bytes(shipped[a + i] for i in range(4))


# ---------------------------------------------------------------- words of every other *_live.py (overlap check)
others = {}
for fn in os.listdir(HERE):
    if fn.endswith('_live.py') and fn != 'flame_live.py':
        for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]*)"', open(os.path.join(HERE, fn)).read()):
            a = int(m.group(1), 16)
            for i in range(len(m.group(3)) // 2):
                others.setdefault(a + i, set()).add(fn)


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


listing = []
groups = {}
warn = []


def note_others(addr, allowed=()):
    for i in range(4):
        for fn in others.get(addr + i, ()):
            if fn not in allowed:
                warn.append('0x%x also in %s' % (addr, fn))


def text_patch(addr, expect, new, note):
    """Code word in main text: assert the stock instruction and that no shipped record touches it."""
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    assert not any(addr + i in shipped for i in range(4)), 'collides with a shipped record at %x' % addr
    note_others(addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def shipped_patch(addr, expect_shipped, expect_stock, new, note, allowed=()):
    """Word replaced by a shipped record: orig = the shipped word (what live memory holds)."""
    old = struct.unpack('<I', shipped_word(addr))[0]
    got = dis1(addr, old)
    assert got == expect_shipped, 'shipped %x: %s, expected %s' % (addr, got, expect_shipped)
    assert dis1(addr, word(addr)) == expect_stock, 'stock %x: %s' % (addr, dis1(addr, word(addr)))
    note_others(addr, allowed)
    listing.append('  0x%x  %s  ->  %s   (%s; stock word was "%s")' % (addr, got, dis1(addr, new), note, expect_stock))
    return (addr, hexw(old), hexw(new), True)


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


# ================================================================ ACTION_SHARE
listing.append('=== ACTION_SHARE')
# sender 0x11A32A8 (only caller: press 0x11A2F60): members >= 1 -> tail call transport vt+0x48 (server member)
ctx(0x11A3318, 'ldr x8, [x19, #0x10]!')       # x0 = mgr3+0x10, x8 = transport vtable
ctx(0x11A3330, 'mov w1, #0x74')
ctx(0x11A3340, 'br x4')
# vt+0x40 = 0x1CD8008: 'sub x0,x0,#0x10; mov w4,wzr; b 0x1CD7C80' -> x4 (the jump register) is not an argument
ctx(0x1CD8008, 'sub x0, x0, #0x10')
ctx(0x1CD800C, 'mov w4, wzr')
ctx(0x1CD8010, 'b #0x1cd7c80')
# 0x74 routing attribute: 0x00 (all members, self included), not touched by any shipped record
assert RO[ROUTE_74 - RO_BASE] == 0x00 and RO[ROUTE_74 + 4 - RO_BASE] == 0x75, 'routing entry of 0x74 changed'
assert not any(ROUTE_74 + i in shipped for i in range(8)), 'routing byte of 0x74 is patched by a shipped record'
listing.append('  routing 0x74 at main+0x%X = %02X (all members) [V], not shipped' % (ROUTE_74, RO[ROUTE_74 - RO_BASE]))
# receiver 0x11A451C, kind 1: 'ldrb w8,[gamedata,#0xbda]; cbz w8, exit' (shipped KIN_PRESS hook replaces the cbz)
ctx(0x11A46E4, 'cmp w9, #1')
ctx(0x11A46F4, 'ldrb w8, [x8, #0xbda]')
ctx(0x11A46FC, 'mov x8, #-0x100000000')
ctx(0x11A49A4, 'bl #0x11a36c0')                # grant
ctx(0x11A49C0, 'bl #0x11a3a20')                # deny
# the shipped KIN_PRESS cave (0x563E5C0..0x563E5DC) becomes unreachable; check it is what we think
assert dis1(0x563E5D8, struct.unpack('<I', shipped_word(0x563E5D8))[0]) == 'b #0x11a46fc'
assert dis1(0x563E5DC, struct.unpack('<I', shipped_word(0x563E5DC))[0]) == 'b #0x11a49c4'
groups['ACTION_SHARE'] = [
    text_patch(0x11A3334, 'ldr x4, [x8, #0x48]', 0xF9402104,
               '0x74 request to every member (broadcast 0x1CD8008) instead of the server member'),
    shipped_patch(0x11A46F8, 'b #0x563e5c0', 'cbz w8, #0x11a49c4', NOP,
                  'receiver kind 1: server branch for every requester (replaces shipped KIN_PRESS hook)',
                  allowed=('kincircle_live.py',)),
]

# ================================================================ FORGE_TEST (not in ORDER)
listing.append('=== FORGE_TEST (test only)')
ctx(0x11A06E0, 'ldrb w9, [x9, #0xbda]')
ctx(0x11A0768, 'bl #0xcf8e2c')
ctx(0xCF8F70, 'ldrb w8, [x8, #0xbda]')
ctx(0xCF8EEC, 'cbz w8, #0xcf8fe4')            # the flask gate stays closed
groups['FORGE_TEST'] = [
    text_patch(0x11A06E4, 'cbz w9, #0x11a076c', NOP, 'forge apply 0x11A06B4 runs in LAN'),
    text_patch(0xCF8F74, 'cbz w8, #0xcf8fe4', NOP, 'item grant 0xCF8E2C: non-flask branch runs in LAN (SHARED GATE)'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g
        listing.append('  check %s 0x%X orig %s new %s' % (g, a, o, n))

print('\n'.join(listing))
for x in warn:
    print('WARNING', x)
assert not warn, 'word used by another *_live.py'

ORDER = ['ACTION_SHARE']
out = ['"""Flame corpse / action-menu groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in',
       'memory. Generated by flame_gen.py (original-word checks, capstone listing, overlap checks against',
       'patch_manager.cpp and every *_live.py). Not live-tested. Notes: flame_items_notes.md.',
       'ACTION_SHARE 0x11A46F8 replaces the SHIPPED KIN_PRESS hook: its orig is the shipped word; in the build change',
       'DUSK_W_11A46F8 to 1F2003D5 (the KIN_PRESS cave words 0x563E5C0..0x563E5DC then become dead code).',
       'Apply on EVERY game at the same time (a game without it would drop the others\' requests).',
       'FORGE_TEST is test-only (not in ORDER): it opens a gate shared by 18 callers."""', '']
notes = {
    'ACTION_SHARE': '[V code, I live] 0x74 requests to everyone + every game grants: Flame "taken" and pay-once shared',
    'FORGE_TEST': '[I] TEST ONLY: Alchemy Forge reward in LAN (opens the shared non-flask gate of 0xCF8E2C)',
}
for g in ORDER + ['FORGE_TEST']:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]  # FORGE_TEST only for a live test, see the notes' % ', '.join(ORDER))
open(os.path.join(HERE, 'flame_live.py'), 'w').write('\n'.join(out) + '\n')
print('flame_live.py written')
