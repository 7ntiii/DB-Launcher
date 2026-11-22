"""Generator + checker for smallgaps2_live.py (lower part of the census2 open list). Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes smallgaps2_live.py and prints a
capstone listing of every original and new word plus the context checks. No caves: in-place words only.
python smallgaps2_gen.py            (run from anywhere; paths are relative to this file)

Groups (design, [V]/[I] marks, live tests: smallgaps2_notes.md). Apply each group on EVERY game; none is host-only.
  CUTSCENE_SKIP_ALL  shared-cutscene skip ends the cutscene on every game at the same moment (the presser's own
                     game answers its own vote with the game's offline stand-in 0x11BA150, which broadcasts kind 2).
                     Contains the revert of the shipped CUTSCENE record 0x11B932C (same word as fair_live
                     CUTSCENE_REVERT). Never apply together with the shipped CUTSCENE record.
  DEEPSEA_CLEANUP    "Law of the Deep Sea" (Zork skill) link cleanup: 0xE06768 / 0xE06E20 run in LAN on every game;
                     the effect inside 0xE06B9C is applied only to the local player / local chr.
  SPECIAL_INIT       enemy "special init state" (0x82) timer: auto start + timer run on every game; release needs
                     the local timer (state 2 with w2 = 1) exactly as offline."""
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
OUT = 'smallgaps2_live.py'

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
assert len(shipped) > 1000, 'patch_manager.cpp parse failed'

# ---------------------------------------------------------------- every other helper's records (*_live.py)
others = {}
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith('_live.py') or fn == OUT:
        continue
    body = open(os.path.join(HERE, fn), encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', body):
        a, new = int(m.group(1), 16), m.group(3).upper()
        for i in range(len(new) // 2):
            others.setdefault(a + i, []).append((fn, new))
print('other *_live.py bytes parsed: %d' % len(others))
# Intended overlaps at 0x11B932C only: fair_live.py CUTSCENE_REVERT (same word, same new value) and census_live.py
# CUTSCENE (the record that was later shipped; our row undoes it).
ALLOWED = {(0x11B932C, 'fair_live.py', '610C0054'), (0x11B932C, 'census_live.py', '63000014')}


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def at(addr):
    return dis1(addr, word(addr))


listing = []
groups = {}
NOP = 0xD503201F


def ctx(addr, expect):
    got = at(addr)
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)
    listing.append('  ctx 0x%x  %s' % (addr, got))


def shipped_hex(a):
    if not all(a + i in shipped for i in range(4)):
        return None
    return bytes(shipped[a + i] for i in range(4)).hex().upper()


def other_check(addr, new):
    for i in range(4):
        for fn, nw in others.get(addr + i, []):
            assert (addr, fn, nw) in ALLOWED, 'collides with %s at %x' % (fn, addr)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
    other_check(addr, new)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def revert_shipped(addr, expect_stock, note):
    """Record that puts a SHIPPED word back to stock: orig = shipped bytes, new = stock bytes."""
    stock = word(addr)
    assert dis1(addr, stock) == expect_stock, 'stock %x: %s' % (addr, dis1(addr, stock))
    sh = shipped_hex(addr)
    assert sh is not None, 'no shipped record at %x' % addr
    shw = struct.unpack('<I', bytes.fromhex(sh))[0]
    other_check(addr, stock)
    listing.append('  0x%x  shipped %s  ->  stock %s   (%s)' % (addr, dis1(addr, shw), dis1(addr, stock), note))
    return (addr, sh, hexw(stock), True)


def callers(tgt):
    r = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            if o + imm * 4 == tgt:
                r.append(o)
    return r


def attr(t):
    a = 0x4C4B3AC + 8 * t
    return RO[a + 4 - RO_BASE]


# ================================================================ 1. CUTSCENE_SKIP_ALL
listing.append('=== CUTSCENE_SKIP_ALL')
# press 0x11B9280: entry {id, +4 skip, +5 voted}; w2 bit0 = shared cutscene; mode 6 -> vote 0x25 kind 0
ctx(0x11B930C, 'strb w9, [x8, #5]')           # local "voted" flag
ctx(0x11B9310, 'tbz w20, #0, #0x11b94b8')     # solo cutscene -> local skip in every mode
ctx(0x11B9328, 'cmp w10, #6')
assert shipped_hex(0x11B932C) == '63000014', 'shipped CUTSCENE record changed'
ctx(0x11B9334, 'strb wzr, [sp]')              # kind 0
ctx(0x11B946C, 'cmp w8, #1')                  # session members >= 1 -> manager send, else loopback 0x1CD8014
ctx(0x11B94A4, 'mov w1, #0x25')
ctx(0x11B94B8, 'strb w9, [x8, #4]')           # offline local skip
ctx(0x11BA2F8, 'mov w1, #0x25')
ctx(0x11BA2FC, 'ldr x8, [x8, #0x40]')         # the stand-in broadcasts with vt+0x40 (same signature as vt+0x48)
assert attr(0x25) == 0x00, '0x25 attribute not 0x00 (every member + self link)'
listing.append('  0x25 attribute = 0x00 (every member + self link) [V]')
# handler 0x11B9D60: kinds 0..3 via table 0x4C49D80
jt = [0x11B9DC4 + RO[0x4C49D80 - RO_BASE + k] * 4 for k in range(4)]
assert jt == [0x11B9DC4, 0x11B9E70, 0x11B9FB8, 0x11BA020], 'kind table %r' % jt
ctx(0x11B9DF4, 'ldrb w8, [x20, #8]')          # sender slot <= 0xB and slot +0x46B2 == 0
ctx(0x11B9E24, 'cbnz w8, #0x11ba090')
ctx(0x11B9E44, 'b.eq #0x11ba150')             # entry found -> stand-in
# stand-in: count = entry+5 + 0xED79E8(...), kind 1 broadcast; kind 2 only when THIS game's player voted
ctx(0x11BA16C, 'bl #0xed79e8')
ctx(0x11BA180, 'ldrb w9, [x23, #5]')
ctx(0x11BA3A8, 'ldrb w8, [x23, #5]')
ctx(0x11BA3AC, 'cbz w8, #0x11ba090')
ctx(0x11BA3B8, 'strb w8, [x23, #4]')          # local skip on the voter's game
ctx(0x11BA3C0, 'mov w23, #2')                 # kind 2
# kind 2 receiver sets entry+4 = 1 (appends the entry if missing)
ctx(0x11BA088, 'mov w8, #1')
ctx(0x11BA08C, 'strb w8, [x10, #4]')
assert callers(0x11B9280) == [0x1B814E0], 'press has new callers'   # in fn 0x1B813FC
groups['CUTSCENE_SKIP_ALL'] = [
    revert_shipped(0x11B932C, 'b.ne #0x11b94b8', 'drop shipped local-only skip: shared cutscenes vote again'),
    text_patch(0x11B94A8, 'ldr x8, [x8, #0x48]', 0xF9402108, 'vote 0x25 kind 0 to every member + self (vt+0x40)'),
    text_patch(0x11B9DCC, 'b.eq #0x11ba090', NOP, 'kind 0 handled in LAN: the voter\'s own game sends kind 2'),
]
assert dis1(0x11B94A8, 0xF9402108) == 'ldr x8, [x8, #0x40]'

# ================================================================ 2. DEEPSEA_CLEANUP
listing.append('=== DEEPSEA_CLEANUP')
assert callers(0xE06740) == [0x17AEE48] and callers(0xE06E00) == [0x17BFF9C]
assert sorted(callers(0xE06B9C)) == [0xE067E8, 0xE06EA4, 0xE07090, 0xE0757C]
assert sorted(callers(0xE071BC)) == [0xE07064, 0xE07564]
# 0xE06740: own module +0x18 bits j (12 slots); player j's chr gone (0x17EF180 null) -> 0xE06B9C(own chr, 0, own, j)
ctx(0xE06784, 'cmp w8, #0xb')
ctx(0xE067B8, 'ldr x9, [x20, #0x18]')
ctx(0xE067D0, 'bl #0x17ef180')
ctx(0xE067D4, 'cbnz x0, #0xe067a0')
ctx(0xE067E8, 'bl #0xe06b9c')
# 0xE06E00: own module +0x10 bits j; player j present -> 0xE06B9C(chr j, own chr, j, own)
ctx(0xE06E78, 'ldr x9, [x19, #0x10]')
ctx(0xE06E94, 'cbz x0, #0xe06e60')
ctx(0xE06EA4, 'bl #0xe06b9c')
# 0xE06B9C: clears the bit (absolute), effect only for the local player chr or 0x17EF704(chr)
ctx(0xE06BE8, 'bic x8, x10, x8')
ctx(0xE06BEC, 'str x8, [x9, #0x18]')
ctx(0xE06C00, 'ldr x8, [x0, #0x1a8]')
ctx(0xE06C08, 'b.eq #0xe06c18')
ctx(0xE06C10, 'bl #0x17ef704')
ctx(0xE06C14, 'tbz w0, #0, #0xe06ca4')
# kill path 0xE06FA8 (from the kill handler 0xE96C90) sets / clears the links on every game, no +0xBDA gate
ctx(0xE07040, 'bl #0xe070ac')                # killer has the skill (id 0x104411 in the Power lists)
ctx(0xE07064, 'bl #0xe071bc')
ctx(0xE07090, 'bl #0xe06b9c')
ctx(0xE070D8, 'mov w1, #0x4411')
ctx(0xE070E0, 'movk w1, #0x10, lsl #16')
ctx(0xE0720C, 'orr x8, x10, x8')             # setter: module +0x10 |= bit
ctx(0xE07224, 'ldr x8, [x0, #0x1a8]')
assert attr(0xD8) == 0x60, '0xD8 attribute changed'
groups['DEEPSEA_CLEANUP'] = [
    text_patch(0xE06768, 'cbz w8, #0xe067f0', NOP, 'link cleanup for absent players runs in LAN'),
    text_patch(0xE06E20, 'cbz w8, #0xe06eac', NOP, 'reverse cleanup runs in LAN'),
]

# ================================================================ 3. SPECIAL_INIT
listing.append('=== SPECIAL_INIT')
assert sorted(callers(0xE4A374)) == [0xE4A1E4, 0xE4A328, 0xE4A674, 0xED5D38]
assert callers(0xE4A5C4) == [0x173F78C]
assert sorted(callers(0xE4A26C)) == [0xE4A23C, 0x193E730]   # 0x193E730 = script-side start (no mode check)
# update 0xE4A0FC (module vt): offline only today
ctx(0xE4A128, 'cmp w8, #6')
ctx(0xE4A13C, 'cbz w8, #0xe4a1fc')            # not started -> auto start check
ctx(0xE4A15C, 'b.pl #0xe4a1e8')               # timer +0x14 still running
ctx(0xE4A17C, 'mov w8, #2')                   # timer end -> state 2
ctx(0xE4A1C8, 'mov w1, #0x82')
ctx(0xE4A1CC, 'ldr x8, [x8, #0x40]')
ctx(0xE4A1E0, 'mov w2, #1')
ctx(0xE4A1E4, 'bl #0xe4a374')
ctx(0xE4A29C, 'bl #0x17ee470')                # auto start only for chrs that pass 0x17EE470
ctx(0xE4A2A8, 'mov w9, #1')                   # state 1
# apply 0xE4A374: state 1 only if not started; state 2 clears +0x11 only with w2 = 1; state 0 needs +0x10
ctx(0xE4A3A8, 'cbz w8, #0xe4a418')
ctx(0xE4A404, 'tbz w2, #0, #0xe4a418')
ctx(0xE4A408, 'strb wzr, [x19, #0x11]')
ctx(0xE4A414, 'cbz w8, #0xe4a428')
ctx(0xE4A430, 'strh w9, [x19, #0x10]')
ctx(0xE4A454, 'cmp w8, #6')
ctx(0xE4A4EC, 'ldr s0, [x8, #0x20c]')         # timer seconds from the match rule row
ctx(0xE4A4F4, 'str s0, [x19, #0x14]')
# reader: w2 = (sender == server member mgr3+0x678)
ctx(0xED5D24, 'ldr x8, [x8, #0x678]')
ctx(0xED5D34, 'cset w2, eq')
# release 0xE4A5C4 needs +0x10 != 0 and +0x11 == 0
ctx(0xE4A5E8, 'ccmp w9, #0, #0, ne')
ctx(0xE4A5EC, 'b.ne #0xe4a68c')
ctx(0x173F784, 'ldrb w10, [x0, #0x11]')
ctx(0x173F788, 'cbnz w10, #0x173f798')
assert attr(0x82) == 0x00
groups['SPECIAL_INIT'] = [
    text_patch(0xE4A12C, 'b.eq #0xe4a1e8', NOP, 'module update (auto start + timer) runs in LAN'),
    text_patch(0xE4A458, 'b.eq #0xe4a4f8', NOP, 'state 1 sets the timer in LAN'),
]

# ================================================================ checks only: sites left closed on purpose
listing.append('=== LEFT CLOSED (checks only)')
# 0xEA2D04: kind 1 of the 0xAA switch (server role); attr 0x40 = server member only -> own self link in LAN
assert attr(0xAA) == 0x40 and attr(0xA9) == 0x40
jt = [0xEA2C90 + RO[0x4C483A1 - RO_BASE + k] * 4 for k in range(5)]
assert jt == [0xEA2C90, 0xEA2D04, 0xEA2D6C, 0xEA2EAC, 0xEA2F6C], 'AA table %r' % jt
ctx(0xEA2D04, 'cmp w10, #6')
ctx(0xEA2D08, 'b.eq #0xea3a9c')
ctx(0xEA2D1C, 'bl #0xea3c80')
ctx(0xEA2D70, 'b.ne #0xea3a9c')               # kind 2 = the server's answer, online only
# Sun God Lua side: object [[WCM]+0x5B8]+0x50, field +0x10 != -1
ctx(0xAB2BAC, 'ldr x8, [x8, #0x5b8]')
ctx(0xAB2BB8, 'ldr w8, [x8, #0x10]')
# 0xE15A6C: group bring from the AI-sound module; 0xEAEEDC itself broadcasts 0x8F in mode 6
ctx(0xE15A6C, 'b.eq #0xe15aa8')
ctx(0xEAF020, 'cmp w8, #6')
ctx(0xEAF030, 'bl #0x14e6aac')
assert callers(0xE15770) == [0xE1557C]
listing.append('  0xEA2D04 / 0xEA1EC4 / 0xEA2244 / 0xE15A6C / 0xE13C6C / 0xCF8E2C callers: no word (notes)')

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['CUTSCENE_SKIP_ALL', 'DEEPSEA_CLEANUP', 'SPECIAL_INIT']
notes = {
    'CUTSCENE_SKIP_ALL': '[I] shared-cutscene skip ends it on every game together; contains the CUTSCENE revert '
                         '(fair_live CUTSCENE_REVERT): never use with the shipped CUTSCENE record',
    'DEEPSEA_CLEANUP': '[I] Law of the Deep Sea link cleanup in LAN; effect only on the local player',
    'SPECIAL_INIT': '[I] enemy special-init timer and auto start in LAN (state 2 accepted only locally)',
}
out = ['"""Small gaps 2: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by smallgaps2_gen.py (original-word checks, capstone listing, context checks, collision checks against',
       'patch_manager.cpp and every diag/net/*_live.py). No caves, in-place words only. Not live-tested.',
       'Notes: smallgaps2_notes.md. Apply each group on EVERY game (no group is host-only); groups are independent.',
       'CUTSCENE_SKIP_ALL first record reverts the SHIPPED CUTSCENE word (orig = shipped bytes, new = stock); in a',
       'build, delete the CUTSCENE record instead of adding that row."""', '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, OUT), 'w').write('\n'.join(out) + '\n')
print(OUT + ' written')
