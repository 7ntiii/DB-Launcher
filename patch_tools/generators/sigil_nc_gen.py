"""Generator + checker for the no-cave sigil groups in sigil_nc_live.py. Static only (reads nso/main_text.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and the other diag/net/*_live.py, writes sigil_nc_live.py, prints
capstone listings).
python sigil_nc_gen.py

Groups (rows of sigil_stage_notes.md 1.3 / 2.3; design and [V]/[I] marks there; summary: sigil_nc_notes.md):
  SIGIL_NC_TARGET     A1  0x11960B8 mov w1,#0x24 -> #0x26: target query adds the [GDM+0x30] player array.
  SIGIL_NC_TARGET_2C  A2  same word -> #0x2C (bit 3 [GDM+0x58]); ONLY instead of SIGIL_NC_TARGET (sigils.py C8 SELF!).
  SIGIL_NC_EVAL       C2a/C2b  0x1198738 / 0x1198744 mov w0,#2 -> #1: condition classes B / C authority 2 -> 1.
  SIGIL_NC_REPORT     C3  0x119979C nop: condition done reports event 2 over 0x8B online too.
  SIGIL_NC_PHASE      C4a/C4b  0x11820E0 / 0x118228C nop: BeginPhase / EndPhase global key 10000000 broadcast.
No new code, no caves: single-word changes only.
0x11960B8 is the same word as sigil_live.py SIGIL_A_TARGETS_NC / SIGIL_A (identical orig): that one overlap is
allowed and asserted below; at most ONE of SIGIL_A, SIGIL_A_TARGETS_NC, SIGIL_NC_TARGET, SIGIL_NC_TARGET_2C."""
import glob
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
OUT = 'sigil_nc_live.py'
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

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
SHIPPED_ADDRS = {int(x, 16) for x in re.findall(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+)', src)}

# ---------------------------------------------------------------- other helpers' *_live.py records
others = {}    # byte address -> (file, orig_hex, new_hex, record address)
REC = re.compile(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"\s*,\s*(True|False)\s*\)')
for f in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    fn = os.path.basename(f)
    if fn == OUT:
        continue
    for m in REC.finditer(open(f, encoding='utf-8', errors='ignore').read()):
        a, o, nw = int(m.group(1), 16), m.group(2).upper(), m.group(3).upper()
        for i in range(len(nw) // 2):
            others.setdefault(a + i, []).append((fn, o, nw, a))
print('other *_live.py bytes parsed: %d' % len(others))

# The one allowed overlap: the same target-kind word as sigil_live.py (mutually exclusive alternatives).
ALLOWED = {0x11960B8: ('sigil_live.py', '81048052')}


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


NOP = 0xD503201F

listing = []
groups = {}


def text_patch(addr, expect, new, expect_new, note):
    """Code word in main text: assert the original and the new instruction, check collisions, return the record."""
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    got_new = dis1(addr, new)
    assert got_new == expect_new, 'new at %x: %s, expected %s' % (addr, got_new, expect_new)
    assert not any(addr + i in shipped for i in range(4)), 'collides with a shipped record at %x' % addr
    assert not any(a in SHIPPED_ADDRS for a in range(addr - 3, addr + 4)), 'shipped record row at %x' % addr
    hits = [h for i in range(4) for h in others.get(addr + i, [])]
    if hits:
        assert addr in ALLOWED, 'collides with %r at %x' % (hits, addr)
        fn, o = ALLOWED[addr]
        assert all(h[0] == fn and h[3] == addr and h[1] == o == hexw(old) for h in hits), \
            'unexpected overlap at %x: %r' % (addr, hits)
        note += '; same word as %s (alternatives, apply one)' % fn
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, got_new, note))
    return (addr, hexw(old), hexw(new), True)


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


# ================================================================ A1 / A2. SIGIL_NC_TARGET / SIGIL_NC_TARGET_2C
for a, t in ((0x11960B4, 'add x0, sp, #0x30'), (0x11960BC, 'mov w2, wzr'), (0x11960CC, 'bl #0xce9f40')):
    ctx(a, t)
listing.append('=== SIGIL_NC_TARGET')
groups['SIGIL_NC_TARGET'] = [
    text_patch(0x11960B8, 'mov w1, #0x24', 0x528004C1, 'mov w1, #0x26', 'A1: target query kind 0x26, + [GDM+0x30] players'),
]
assert groups['SIGIL_NC_TARGET'][0][1:3] == ('81048052', 'C1048052')
listing.append('=== SIGIL_NC_TARGET_2C (alternative, never with SIGIL_NC_TARGET)')
groups['SIGIL_NC_TARGET_2C'] = [
    text_patch(0x11960B8, 'mov w1, #0x24', 0x52800581, 'mov w1, #0x2c', 'A2: target query kind 0x2C, bit 3 [GDM+0x58]'),
]
assert groups['SIGIL_NC_TARGET_2C'][0][1:3] == ('81048052', '81058052')

# ================================================================ C2a / C2b. SIGIL_NC_EVAL
for a, t in ((0x119873C, 'ret'), (0x1198748, 'ret')):
    ctx(a, t)
listing.append('=== SIGIL_NC_EVAL')
groups['SIGIL_NC_EVAL'] = [
    text_patch(0x1198738, 'mov w0, #2', 0x52800020, 'mov w0, #1', 'C2a: class B authority 2 -> 1 (owner evaluates)'),
    text_patch(0x1198744, 'mov w0, #2', 0x52800020, 'mov w0, #1', 'C2b: class C authority 2 -> 1 (owner evaluates)'),
]
assert all(r[1:3] == ('40008052', '20008052') for r in groups['SIGIL_NC_EVAL'])

# ================================================================ C3. SIGIL_NC_REPORT
ctx(0x1199798, 'ldrb w8, [x8, #0xbda]')
listing.append('=== SIGIL_NC_REPORT')
groups['SIGIL_NC_REPORT'] = [
    text_patch(0x119979C, 'cbz w8, #0x1199818', NOP, 'nop', 'C3: condition done reports event 2 over 0x8B online'),
]
assert groups['SIGIL_NC_REPORT'][0][1] == 'E8030034'

# ================================================================ C4a / C4b. SIGIL_NC_PHASE
for a, t in ((0x11820DC, 'ldrb w8, [x8, #0xbda]'), (0x11820E4, 'mov w8, #0x9680'),
             (0x1182288, 'ldrb w8, [x8, #0xbda]'), (0x1182290, 'mov w9, #0x9680')):
    ctx(a, t)
listing.append('=== SIGIL_NC_PHASE')
groups['SIGIL_NC_PHASE'] = [
    text_patch(0x11820E0, 'cbz w8, #0x1182114', NOP, 'nop', 'C4a: BeginPhase key 10000000 value 1 broadcast'),
    text_patch(0x118228C, 'cbz w8, #0x11822c4', NOP, 'nop', 'C4b: EndPhase SQM+0x38 = 1, key 10000000 value 0'),
]
assert [r[1] for r in groups['SIGIL_NC_PHASE']] == ['A8010034', 'C8010034']

# ---------------------------------------------------------------- no record overlaps another (except the A1/A2 pair)
EXCLUSIVE = {'SIGIL_NC_TARGET', 'SIGIL_NC_TARGET_2C'}
seen = {}
for g, rs in groups.items():
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            if a + i in seen:
                assert {g, seen[a + i]} == EXCLUSIVE, 'overlap %x (%s, %s)' % (a + i, g, seen[a + i])
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['SIGIL_NC_TARGET', 'SIGIL_NC_EVAL', 'SIGIL_NC_REPORT', 'SIGIL_NC_PHASE']
ALL = ['SIGIL_NC_TARGET', 'SIGIL_NC_TARGET_2C', 'SIGIL_NC_EVAL', 'SIGIL_NC_REPORT', 'SIGIL_NC_PHASE']
out = ['"""No-cave sigil patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by sigil_nc_gen.py (original-word checks, capstone check of every new word, collision checks',
       'against patch_manager.cpp and the other *_live.py). Not live-tested. Notes: sigil_nc_notes.md, sigil_stage_notes.md.',
       'No caves, no new code: single-word changes only.',
       'SIGIL_NC_TARGET and SIGIL_NC_TARGET_2C patch the SAME word 0x11960B8: apply exactly one (2C only if sigils.py C8',
       'shows SELF!), and never together with sigil_live.py SIGIL_A or SIGIL_A_TARGETS_NC (same word).',
       'TARGET, EVAL, REPORT: every game. PHASE: host only (all games also works, duplicates harmless [I]).',
       'ORDER below = default apply order (TARGET, EVAL, REPORT first; PHASE after they are verified)."""', '']
notes = {
    'SIGIL_NC_TARGET': 'A1, all games: target query 0x24 -> 0x26 (+ [GDM+0x30] players); = sigil_live.py SIGIL_A_TARGETS_NC',
    'SIGIL_NC_TARGET_2C': 'A2, all games, INSTEAD of SIGIL_NC_TARGET: 0x24 -> 0x2C (bit 3 [GDM+0x58]); only if C8 SELF!',
    'SIGIL_NC_EVAL': 'C2a/C2b, all games: condition classes B/C authority 2 -> 1 (evaluated on the owner game)',
    'SIGIL_NC_REPORT': 'C3, all games: condition done reports event 2 over 0x8B online; watch for a 0x8B echo storm',
    'SIGIL_NC_PHASE': 'C4a/C4b, host only: BeginPhase/EndPhase global key 10000000 broadcasts online',
}
for g in ALL:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, nw, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
out.append('EXCLUSIVE = [SIGIL_NC_TARGET, SIGIL_NC_TARGET_2C]   # never both')
open(os.path.join(HERE, OUT), 'w').write('\n'.join(out) + '\n')
print('%s written' % OUT)
