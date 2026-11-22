"""Generator + checker for the ZEP_S1..ZEP_S7 groups in zeppelin_nc_live.py ("nc" = no code: only words
changed in place, no new code, no cave). Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py; writes zeppelin_nc_live.py,
prints a capstone listing). UNTESTED: nothing here was run in a game.
python zeppelin_nc_gen.py

Source: zeppelin2_notes.md section 3 (word flips S1..S7) for event 1120 (airship support / zeppelin).
HOST byte = main+0x492AFD8 (0 = this game is the host, as in zeppelin_gen.py / dusk_lan.cpp).
  ZEP_S1  0xF0DB88 nop: PrepareSecond's grant loop runs on every game.
  ZEP_S2  0x4C4B8A0 (ro) 0x9E attribute 0x40 (server only) -> 0x20 (players).
  ZEP_S3  0xF107F0..F8 sender: host loops its own request back, guests send 0x9E kind 0.
  ZEP_S4  0xF11EDC..EC receiver: kind 0 stored on the host only.
  ZEP_S5  0xF11174..7C decision 0xF11140 on the host only.
  ZEP_S6  0xF11E98..EA0 receiver: kind 1 (strike answer) accepted on guests only.
  ZEP_S7  0xF11258 optional: skip the requester-has-goods check in 0xF11140.
S8 is left out (only useful with the far C1 variant, which is new code).
ZEP_S1..S5 supersede zeppelin_live.py (same addresses; S1 = ZEPPELIN_GRANT_ALL, S2..S5 = ROUTE / STORE /
DECIDE word for word). zeppelin_live.py is therefore NOT counted as a collision here, but the overlap is
asserted to be exactly those words: apply ZEP_* OR zeppelin_live.py, never both (and never ZEPPELIN_GRANT)."""
import glob
import importlib.util
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

ME = 'zeppelin_nc_live.py'
SUPERSEDED = 'zeppelin_live.py'
HOST_BYTE = 0x492AFD8
HB_PAGE, HB_OFF = HOST_BYTE & ~0xFFF, HOST_BYTE & 0xFFF

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}   # byte address -> record name
shipped_val = {}
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name not in arrays:
        continue
    for i, bt in enumerate(arrays[name]):
        shipped[a + i] = name
        shipped_val[a + i] = bt
print('shipped bytes parsed: %d' % len(shipped))


def load_groups(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = {}
    for g, v in vars(mod).items():
        if isinstance(v, list) and v and all(isinstance(r, tuple) and len(r) == 4 for r in v):
            out[g] = v
    return out


# ---------------------------------------------------------------- every other helper's live groups
others = {}
for path in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    fn = os.path.basename(path)
    if fn in (ME, SUPERSEDED):
        continue
    for g, v in load_groups(path).items():
        for a, o, nw, c in v:
            for i in range(len(nw) // 2):
                others.setdefault(a + i, '%s:%s' % (fn, g))
print('other live-group bytes parsed: %d (without %s and %s)' % (len(others), ME, SUPERSEDED))
old = load_groups(os.path.join(HERE, SUPERSEDED))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldrb_w(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt


def _imm19(pc, t):
    d = t - pc
    assert d % 4 == 0 and -(1 << 20) <= d < (1 << 20)
    return ((d // 4) & 0x7FFFF) << 5


def cbz_w(pc, rt, t): return 0x34000000 | _imm19(pc, t) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | _imm19(pc, t) | rt


def b(pc, t):
    d = (t - pc) // 4
    assert (t - pc) % 4 == 0 and -(1 << 25) <= d < (1 << 25)
    return 0x14000000 | (d & 0x3FFFFFF)


NOP = 0xD503201F

listing = []
groups = {}


def text_patch(addr, expect_old, new, expect_new, note):
    """Assert the original word decodes as the notes say and the new word decodes as intended."""
    o = word(addr)
    got = dis1(addr, o)
    assert got == expect_old, 'at %x: %s, expected %s' % (addr, got, expect_old)
    gn = dis1(addr, new)
    assert gn == expect_new, 'new at %x: %s, expected %s' % (addr, gn, expect_new)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, gn, note))
    return (addr, hexw(o), hexw(new), True)


def context(pairs):
    for a, t in pairs:
        got = dis1(a, word(a))
        assert got == t, (hex(a), got, t)
        listing.append('  context 0x%x  %s' % (a, t))


HB_ADRP = 'adrp x8, #0x%x' % HB_PAGE
HB_LDRB = 'ldrb w8, [x8, #0x%x]' % HB_OFF
if HOST_BYTE < len(TXT):
    listing.append('HOST byte 0x%X in the static image = %02X (offline value; 0 = behaves as host)' % (
        HOST_BYTE, TXT[HOST_BYTE]))

# ================================================================ ZEP_S1 grant gate (all games)
listing.append('=== ZEP_S1')
context(((0xF0DB78, 'cbz x8, #0xf0dc30'), (0xF0DB84, 'ldrb w8, [x8, #0xbda]'), (0xF0DB8C, 'mov x19, x0'),
         (0xF0DC30, 'ldp x20, x19, [sp, #0x50]')))
groups['ZEP_S1'] = [
    text_patch(0xF0DB88, 'cbz w8, #0xf0dc30', NOP, 'nop', 'PrepareSecond bda gate: grant loop runs on every game'),
]

# ================================================================ ZEP_S2 + S3 route + sender
listing.append('=== ZEP_S2')
ROUTE = 0x4C4B8A0                     # 0x4C4B3B0 + 0x9E * 8: the 0x9E attribute byte
ro = ROUTE - RO_BASE
assert struct.unpack_from('<I', RO, ro - 4)[0] == 0x9E, 'table entry before 0x4C4B8A0 is not id 0x9E'
assert struct.unpack_from('<I', RO, ro + 4)[0] == 0x9F, 'table entry after is not id 0x9F'
assert RO[ro] == 0x40, 'route byte is %02x, expected 40' % RO[ro]
listing.append('  0x%X  0x9E attribute: 40 (server only) -> 20 (players)  (data byte)' % ROUTE)
groups['ZEP_S2'] = [(ROUTE, '40', '20', False)]

listing.append('=== ZEP_S3')
context(((0xF107E8, 'ldr x19, [x8]'), (0xF107EC, 'cbz x19, #0xf10a58'), (0xF107FC, 'adrp x8, #0x56e6000'),
         (0xF108D4, 'mov w1, #0x9e'), (0xF108F0, 'adrp x8, #0x56e6000')))
groups['ZEP_S3'] = [
    text_patch(0xF107F0, 'ldr w8, [x19, #0x1268]', adrp(0xF107F0, 8, HB_PAGE), HB_ADRP, 'HOST page'),
    text_patch(0xF107F4, 'cmp w8, #6', ldrb_w(8, 8, HB_OFF), HB_LDRB, 'HOST byte'),
    text_patch(0xF107F8, 'b.ne #0xf108f0', cbz_w(0xF107F8, 8, 0xF108F0), 'cbz w8, #0xf108f0',
               'host: loopback 0x1CD8014; guest: send 0x9E kind 0'),
]

# ================================================================ ZEP_S4 kind 0 stored on the host only
listing.append('=== ZEP_S4')
context(((0xF11E80, 'cbz w8, #0xf11edc'), (0xF11ED8, 'b #0xf1209c'), (0xF11EE0, 'add x23, sp, #0x30'),
         (0xF11EF0, 'ldp x8, x9, [x19, #0x110]'), (0xF122CC, 'ldr x8, [x24]')))
groups['ZEP_S4'] = [
    text_patch(0xF11EDC, 'adrp x8, #0x5b65000', adrp(0xF11EDC, 8, HB_PAGE), HB_ADRP, 'HOST page'),
    text_patch(0xF11EE4, 'ldr x8, [x8, #0xc20]', ldrb_w(8, 8, HB_OFF), HB_LDRB, 'HOST byte (x23 at 0xF11EE0 kept)'),
    text_patch(0xF11EE8, 'ldrb w8, [x8, #0xbda]', NOP, 'nop', 'bda load gone'),
    text_patch(0xF11EEC, 'cbz w8, #0xf122cc', cbnz_w(0xF11EEC, 8, 0xF122CC), 'cbnz w8, #0xf122cc',
               'guest: do not store kind 0'),
]

# ================================================================ ZEP_S5 decision host only
listing.append('=== ZEP_S5')
context(((0xF11170, 'adrp x22, #0x5b65000'), (0xF11180, 'mov x21, x1'), (0xF11188, 'bl #0xf11d20'),
         (0xF11238, 'mov w21, wzr'), (0xF11544, 'ldr x8, [x22, #0xc20]')))   # x22 page kept for later use
groups['ZEP_S5'] = [
    text_patch(0xF11174, 'ldr x8, [x22, #0xc20]', adrp(0xF11174, 8, HB_PAGE), HB_ADRP, 'HOST page'),
    text_patch(0xF11178, 'ldrb w8, [x8, #0xbda]', ldrb_w(8, 8, HB_OFF), HB_LDRB, 'HOST byte'),
    text_patch(0xF1117C, 'cbz w8, #0xf11238', cbnz_w(0xF1117C, 8, 0xF11238), 'cbnz w8, #0xf11238',
               'guest: no decision (returns false)'),
]

# ================================================================ ZEP_S6 kind 1 accepted on guests only
listing.append('=== ZEP_S6')
# x8 = [x24] (net mgr) only feeds the mode load; after the gate x8 is reloaded (0xF11EA4) and the flags
# are reset (0xF11EAC), so replacing the mode test by the HOST byte test changes nothing else.
context(((0xF11E88, 'cmp w8, #1'), (0xF11E8C, 'b.ne #0xf122cc'), (0xF11E90, 'ldr x8, [x24]'),
         (0xF11E94, 'cbz x8, #0xf12364'), (0xF11EA4, 'ldp x9, x8, [x19, #0x130]'), (0xF11EAC, 'cmp x9, x8')))
groups['ZEP_S6'] = [
    text_patch(0xF11E98, 'ldr w8, [x8, #0x1268]', adrp(0xF11E98, 8, HB_PAGE), HB_ADRP, 'HOST page'),
    text_patch(0xF11E9C, 'cmp w8, #6', ldrb_w(8, 8, HB_OFF), HB_LDRB, 'HOST byte'),
    text_patch(0xF11EA0, 'b.ne #0xf122cc', cbz_w(0xF11EA0, 8, 0xF122CC), 'cbz w8, #0xf122cc',
               'host: drop kind 1 (no echo = no second fire); guest: apply the strike'),
]

# ================================================================ ZEP_S7 optional: skip the goods check
listing.append('=== ZEP_S7 (optional)')
# Skipped block 0xF1125C..0xF11374 sets x21/x26/x27/x28/x25 use; each is redefined after 0xF11378 before
# any read: x21 0xF113A0, x26 0xF113C4, x27 0xF113E8, x25 0xF113FC, x28 0xF117A0; [x29-0x40] rewritten 0xF11398.
context(((0xF11254, 'ldur x25, [x29, #-0x40]'), (0xF11374, 'tbz w8, #3, #0xf11280'),
         (0xF11378, 'adrp x8, #0x5b3c000'), (0xF11398, 'stur w8, [x29, #-0x40]'), (0xF113A0, 'mov x21, x0'),
         (0xF113C4, 'ldp x26, x8, [x19, #0xf0]'), (0xF113E8, 'add x27, x9, #0x20'), (0xF113FC, 'mov w25, #0xffff'),
         (0xF117A0, 'ldr x28, [x9, #0x10]')))
groups['ZEP_S7'] = [
    text_patch(0xF11258, 'cbz x25, #0xf11414', b(0xF11258, 0xF11378), 'b #0xf11378',
               'skip the requester-has-goods check (host copy of a guest inventory)'),
]

# ---------------------------------------------------------------- notes' encodings match
NOTES_NEW = {0xF0DB88: 0xD503201F, 0xF107F0: 0xD001D0C8, 0xF107F4: 0x397F6108, 0xF107F8: 0x340007C8,
             0xF11EDC: 0xB001D0C8, 0xF11EE4: 0x397F6108, 0xF11EE8: 0xD503201F, 0xF11EEC: 0x35001F08,
             0xF11174: 0xB001D0C8, 0xF11178: 0x397F6108, 0xF1117C: 0x350005E8,
             0xF11E98: 0xB001D0C8, 0xF11E9C: 0x397F6108, 0xF11EA0: 0x34002168, 0xF11258: 0x14000048}
for g, rs in groups.items():
    for a, o, nw, c in rs:
        if c:
            assert hexw(NOTES_NEW[a]) == nw, 'new word at %x differs from zeppelin2_notes.md' % a
listing.append('every new code word equals zeppelin2_notes.md section 3')

# ---------------------------------------------------------------- overlaps
seen = {}
for gname, rs in groups.items():
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, gname, seen[a + i])
            seen[a + i] = gname
            assert a + i not in shipped, 'collides with shipped %s at %x' % (shipped[a + i], a + i)
            assert a + i not in others, 'collides with %s at %x' % (others[a + i], a + i)
listing.append('no overlap with shipped records or other *_live.py groups (except %s, below)' % SUPERSEDED)

# superseded file: overlap must be exactly ROUTE/STORE/DECIDE/GRANT_ALL word for word (+ GRANT on 0xF0DB88)
mine = {a: nw for rs in groups.values() for a, o, nw, c in rs}
for g, rs in old.items():
    for a, o, nw, c in rs:
        if a in mine:
            same = mine[a] == nw
            assert same or g == 'ZEPPELIN_GRANT', '%s:%s at %x differs' % (SUPERSEDED, g, a)
            listing.append('  %s %s 0x%X: %s' % (SUPERSEDED, g, a, 'same word' if same else 'CONFLICT (alternative)'))
        else:
            assert g == 'ZEPPELIN_GRANT', '%s:%s 0x%X not covered by ZEP_*' % (SUPERSEDED, g, a)

# ---------------------------------------------------------------- what is NOT reachable without code (for the notes)
assert dis1(0xF0C52C, word(0xF0C52C)) == 'bl #0xf11d20'      # C1 hook site: still the plain drain
assert dis1(0xCF8EEC, word(0xCF8EEC)) == 'cbz w8, #0xcf8fe4'  # flask-type gate of 0xCF8E2C, unpatched
fo = bytes(shipped_val[0xCF8F74 + i] for i in range(4))
listing.append('  shipped FORGE_OWN at 0xCF8F74: %s (non-forge callers of 0xCF8E2C stay blocked: C2 still needed)'
               % dis1(0xCF8F74, struct.unpack('<I', fo)[0]))
fo9c = bytes(shipped_val[0xCF0E9C + i] for i in range(4))
listing.append('  shipped FORGE_OWN cave tail 0xCF0E9C: %s' % dis1(0xCF0E9C, struct.unpack('<I', fo9c)[0]))

print('\n'.join(listing))

ORDER = ['ZEP_S1', 'ZEP_S2', 'ZEP_S3', 'ZEP_S4', 'ZEP_S5', 'ZEP_S6']
OPTIONAL = ['ZEP_S7']
out = ['"""UNTESTED zeppelin (airship support, event 1120) in-place groups ZEP_S1..ZEP_S7:',
       '(offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory. Generated by',
       'zeppelin_nc_gen.py (original-word checks, capstone check of every new word, collision checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). NO new code, NO cave. NOT run in any game.',
       'Notes: zeppelin_nc_notes.md, design zeppelin2_notes.md section 3. HOST byte = main+0x492AFD8 (0 = host).',
       'Apply on EVERY game. These SUPERSEDE zeppelin_live.py (same addresses): never apply both.',
       'ALONE THEY GIVE NO VISIBLE FEATURE: the decision needs C1, the Transmitter grant needs C2 (shipped',
       'FORGE_OWN blocks 0xCF8E2C for this caller), guests\' strikes need C3. ZEP_S7 is optional."""', '']
notes = {
    'ZEP_S1': 'S1 PrepareSecond grant loop on every game (0xCF8E2C still blocks it until C2)',
    'ZEP_S2': 'S2 0x9E attribute server -> players (data byte)',
    'ZEP_S3': 'S3 host loops its own request back, guests send 0x9E kind 0',
    'ZEP_S4': 'S4 kind-0 requests stored on the host only',
    'ZEP_S5': 'S5 decision 0xF11140 on the host only (nothing calls it in LAN until C1)',
    'ZEP_S6': 'S6 kind-1 strike answers accepted on guests only (nothing sends one until C3)',
    'ZEP_S7': 'S7 OPTIONAL: skip the requester-has-goods check in 0xF11140',
}
for gname in ORDER + OPTIONAL:
    out.append('%s = [  # UNTESTED: %s' % (gname, notes[gname]))
    for a, o, nw, c in groups[gname]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
out.append('OPTIONAL = [%s]' % ', '.join(OPTIONAL))
open(os.path.join(HERE, ME), 'w').write('\n'.join(out) + '\n')
print(ME + ' written')
