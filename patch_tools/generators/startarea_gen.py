"""Generator + checker for START_AREA in startarea_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py; writes startarea_live.py,
prints a capstone listing).
python startarea_gen.py

START_AREA (design A of startarea_zeppelin_notes.md, section A6): one word.
  0x10F1B28 in 0x10F1AFC (the start-point builder's gate). Stock `b.ne #0x10f1b3c` (540000A1) builds only
  when offline (bda) && M+0xBA ("all picks locked"). The SHIPPED record DUSK_ONLINE_GATE2 made it an
  unconditional `b #0x10f1b3c` (14000005), so in LAN every game builds on the first frame of phase 26,
  before anyone picked. New: `cbnz w9, #0x10f1b3c` (350000A9): build once M+0xBA is set (w9 = M+0xBA,
  loaded at 0x10F1B14; nothing between writes w9). Offline is unchanged (bda = 1 already required +0xBA).
  The record's ORIG is the SHIPPED word (what live memory holds), not the stock one.
  The assist (dusk_lan.cpp StartArea) sets M+0xBA on the host when the picks are in, and on a guest
  that heard no 0x51 list 12 s after its own timeout. Keep the shipped GATE1 (0x1150758 nop)."""
import glob
import importlib.util
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}   # byte address -> (shipped byte, record name)
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name not in arrays:
        continue
    for i, bt in enumerate(arrays[name]):
        shipped[a + i] = (bt, name)
print('shipped bytes parsed: %d' % len(shipped))


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return struct.unpack('<I', bytes(shipped[a + i][0] for i in range(4)))[0]


# ---------------------------------------------------------------- every other helper's live groups
ME = 'startarea_live.py'
others = {}    # byte address -> 'file:GROUP'
for path in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    fn = os.path.basename(path)
    if fn == ME:
        continue
    spec = importlib.util.spec_from_file_location(fn[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for g, v in vars(mod).items():
        if not (isinstance(v, list) and v and all(isinstance(r, tuple) and len(r) == 4 for r in v)):
            continue
        for a, o, nw, c in v:
            for i in range(len(nw) // 2):
                others.setdefault(a + i, '%s:%s' % (fn, g))
print('other live-group bytes parsed: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def cbnz_w(pc, rt, t):
    d = t - pc
    assert d % 4 == 0 and -(1 << 20) <= d < (1 << 20)
    return 0x35000000 | (((d // 4) & 0x7FFFF) << 5) | rt


listing = []
groups = {}

# ================================================================ START_AREA
listing.append('=== START_AREA')
GATE2 = 0x10F1B28
BUILD = 0x10F1B3C
# the gate's context, stock words
for a, t in ((0x10F1AFC, 'pacibsp'), (0x10F1B10, 'adrp x8, #0x5b65000'), (0x10F1B14, 'ldrb w9, [x0, #0xba]'),
             (0x10F1B18, 'ldr x8, [x8, #0xc20]'), (0x10F1B1C, 'ldrb w8, [x8, #0xbda]'), (0x10F1B20, 'cmp w8, #0'),
             (0x10F1B24, 'ccmp w9, #0, #4, ne'), (0x10F1B2C, 'ldp x20, x19, [sp, #0x30]'),
             (0x10F1B38, 'retab'), (BUILD, 'add x20, x0, #0x290')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
    listing.append('  context 0x%x  %s' % (a, t))
# w9 is not written between its load and the gate
for a in range(0x10F1B18, GATE2, 4):
    ins = list(md.disasm(struct.pack('<I', word(a)), a))[0]
    writes = ins.mnemonic not in ('cmp', 'ccmp', 'cmn', 'tst')   # compares only read their operands
    assert not (writes and ins.op_str.startswith(('w9', 'x9'))), 'w9 written at %x' % a
assert dis1(GATE2, word(GATE2)) == 'b.ne #0x10f1b3c' and word(GATE2) == 0x540000A1, 'stock GATE2 word changed'
# shipped record DUSK_ONLINE_GATE2 owns this word: live memory holds its word, so that is our orig
assert shipped[GATE2][1] == 'DUSK_ONLINE_GATE2', shipped[GATE2]
old = shipped_word(GATE2)
assert old == 0x14000005 and dis1(GATE2, old) == 'b #0x10f1b3c', hex(old)
new = cbnz_w(GATE2, 9, BUILD)
assert new == 0x350000A9 and dis1(GATE2, new) == 'cbnz w9, #0x10f1b3c', hex(new)
# the shipped GATE1 the design keeps (0x1150758 tbnz -> nop)
assert dis1(0x1150758, word(0x1150758)) == 'tbnz w8, #0, #0x1150784'
assert shipped_word(0x1150758) == 0xD503201F, 'shipped GATE1 is not a nop'
listing.append('  0x%x  %s  ->  %s   (orig = SHIPPED DUSK_ONLINE_GATE2; stock %s)' % (
    GATE2, dis1(GATE2, old), dis1(GATE2, new), dis1(GATE2, word(GATE2))))
groups['START_AREA'] = [(GATE2, hexw(old), hexw(new), True)]

# ================================================================ START_AREA_LIST
# Live 2026-11-14: the host's 0x51 never reached the guest. Sender 0x10F3500 is not gated (0x10F3614..2C:
# [*(main+0x5B3CE08)+0x10] vt+0x40 = send to all; 0x51 attribute byte main+0x4C4B638 = 0x20 players). The
# reader in the mediator pump 0x10EF580 reads 0x51 with vt+0x60 = from the SERVER only (same slot the shipped
# DUSK_KILL_READ_ANY moved to +0x50 for 0x9C at 0x11650F8, same arguments, x4 = 0). Fix: read from anyone.
listing.append('=== START_AREA_LIST')
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
RO_BASE = 0x492B000
r51 = 0x4C4B3B0 + 0x51 * 8 - RO_BASE
assert struct.unpack_from('<I', RO, r51 - 4)[0] == 0x51 and RO[r51] == 0x20, '0x51 attribute is not 0x20'
listing.append('  context 0x4C4B638  0x51 attribute 0x20 (players): routing is fine, not patched')
for a, t in ((0x10F3614, 'ldr x8, [x20, #0x10]!'), (0x10F3620, 'mov w1, #0x51'), (0x10F3624, 'ldr x8, [x8, #0x40]'),
             (0x10F362C, 'blr x8'), (0x10F364C, 'bl #0x10efac0'),
             (0x10EF9CC, 'mov x0, x22'), (0x10EF9D0, 'mov w1, #0x51'), (0x10EF9D4, 'mov x2, x23'),
             (0x10EF9DC, 'mov x4, xzr'), (0x10EF9E0, 'blr x8'), (0x10EFA0C, 'bl #0x10efac0'),
             (0x11650F0, 'mov w1, #0x9c'), (0x11650FC, 'mov x4, xzr')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
    listing.append('  context 0x%x  %s' % (a, t))
assert shipped_word(0x11650F8) == 0xF9402908 and word(0x11650F8) == 0xF9403108, 'DUSK_KILL_READ_ANY precedent changed'
READ51 = 0x10EF9D8
assert dis1(READ51, word(READ51)) == 'ldr x8, [x8, #0x60]' and READ51 not in shipped
listing.append('  0x%x  %s  ->  %s   (0x51 read from anyone, as DUSK_KILL_READ_ANY)' % (
    READ51, dis1(READ51, word(READ51)), dis1(READ51, 0xF9402908)))
groups['START_AREA_LIST'] = [(READ51, hexw(word(READ51)), hexw(0xF9402908), True)]

# ================================================================ FINAL_HOST_LIST (optional)
# With START_AREA_LIST every game also applies the others' 0x51 in the FINAL, where the shipped DUSK_W_11679F8
# (nop) lets every game build its own list (0x11679C0 -> 0x10F3500 at 0x11680A8): last list wins. Optional:
# build the final's list on the host only (host byte main+0x492AFD8 == 0); guests take it from the host.
listing.append('=== FINAL_HOST_LIST (optional, untested)')
for a, t in ((0x11679EC, 'adrp x20, #0x5b65000'), (0x1167ADC, 'ldr x8, [x20, #0xc20]'),   # x20 stays
             (0x1168100, 'add sp, sp, #0x1a0'), (0x11680A8, 'bl #0x10f3500')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
    listing.append('  context 0x%x  %s' % (a, t))
assert shipped[0x11679F8][1] == 'DUSK_W_11679F8' and shipped_word(0x11679F8) == 0xD503201F
assert dis1(0x11679F8, word(0x11679F8)) == 'cbz w8, #0x1168100'
p = (0x492A000 >> 12) - (0x11679F0 >> 12)
adrp_x8 = 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | 8
ldrb_hb = 0x39400000 | (0xFD8 << 10) | (8 << 5) | 8
fin = [(0x11679F0, 'ldr x8, [x20, #0xc20]', adrp_x8, 'HOST page'),
       (0x11679F4, 'ldrb w8, [x8, #0xbda]', ldrb_hb, 'HOST byte'),
       (0x11679F8, None, cbnz_w(0x11679F8, 8, 0x1168100), 'guest: skip the final build (orig = shipped nop)')]
groups['FINAL_HOST_LIST'] = []
for a, t, nw, note in fin:
    o = shipped_word(a) if t is None else word(a)
    if t is not None:
        assert dis1(a, o) == t and a not in shipped, hex(a)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (a, dis1(a, o), dis1(a, nw), note))
    groups['FINAL_HOST_LIST'].append((a, hexw(o), hexw(nw), True))

# ---------------------------------------------------------------- overlaps
seen = {}
for g, rs in groups.items():
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen[a + i])
            seen[a + i] = g
            # the one shipped word we replace on purpose; nothing else may be shipped
            if a + i in shipped:   # only the two shipped words we replace on purpose
                assert a in (GATE2, 0x11679F8), 'collides with shipped %s at %x' % (shipped[a + i][1], a + i)
            assert a + i not in others, 'collides with %s at %x' % (others[a + i], a + i)
listing.append('no overlap with other *_live.py groups; shipped overlaps only GATE2 and (optional) 0x11679F8')

print('\n'.join(listing))

ORDER = ['START_AREA', 'START_AREA_LIST']
out = ['"""Start-area patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by startarea_gen.py (stock + shipped word checks, capstone listing, collision checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). Notes: startarea_fix_notes.md.',
       'START_AREA (live-tested 2026-11-14: the host builds after the picks) replaces the SHIPPED record',
       'DUSK_ONLINE_GATE2 (0x10F1B28 b -> cbnz w9): its orig is the shipped word 05000014 (stock A1000054).',
       'START_AREA_LIST (untested): guests read the host\'s 0x51 list from a player (vt+0x60 -> +0x50). Apply',
       'START_AREA and START_AREA_LIST together on EVERY game, with the dusk_lan.cpp StartArea rule.',
       'FINAL_HOST_LIST (optional, untested, not in ORDER): only the host builds the final\'s list; replaces the',
       'SHIPPED DUSK_W_11679F8 nop at 0x11679F8 (orig = shipped 1F2003D5)."""', '']
notes = {
    'START_AREA': 'start-point builder waits for M+0xBA (all picks locked) instead of building on the first frame',
    'START_AREA_LIST': 'mediator pump reads 0x51 from anyone (was server only): guests apply the host\'s list',
    'FINAL_HOST_LIST': 'OPTIONAL: final start list built on the host only (guests take it via START_AREA_LIST)',
}
for g in ORDER + ['FINAL_HOST_LIST']:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, nw, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, ME), 'w').write('\n'.join(out) + '\n')
print(ME + ' written')
