"""Generator + checker for the Virtue groups in virtue_live.py. Static only: reads nso/*.bin, patch_manager.cpp,
dusk_lan.cpp and every other diag/net/*_live.py; writes virtue_live.py; prints the capstone listing of every word.
python virtue_gen.py      (run from diag/net)

Groups (design, [V]/[I] marks and the assist half: virtue_notes.md):
  VIRTUE_PUB_CAVE  one cave at main+0x563ECBC (17 words). Inert until VIRTUE_PUB.
  VIRTUE_PUB       0x149062C (exit of the Virtue getter 0x1490460, the HUD's "Virtue of player N"):
                   `mov w0, w19` -> `b cave`. When the getter has just computed the LOCAL player's total
                   (banked pgd+0x42C8 + the 26 counters of pgd+0x46D8), the cave stores it in the text-padding
                   box main+0x492AFF8 (u32 total) and bumps main+0x492AFFC (u32 publish count).
                   The LAN assist reads the box on every game and writes the value into that player's
                   PlayerGameData copy (pgd+0x42C8) on every other game (virtue_notes.md section 5).
  VIRTUE_TIEBREAK  0xF88E78..0xF88E94: the ranking record builder 0xF88D60 stores 0 instead of the 6 category
                   sums and pgd+0x6C. The ranking sort key becomes (total, index of the player number among all
                   player numbers), which is the same on every game when the totals are the same.
Cave slot 0x563ECBC..0x563ECFF: inside the lead's FREE range 0x563EC20..0x563ECFF, past lives_live.py
(0x563EC20..0x563EC37); it overlaps only the unshipped offline_gate_census.md proposals #11/#12
(0x563ECC0 / 0x563ECE0)."""
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
SRC = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core')
PM = os.path.join(SRC, 'file_sys', 'patch_manager.cpp')
LAN = os.path.join(SRC, 'dusk_lan.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

GDM = 0x5B57EB8          # *(main+0x5B57EB8) = game data manager; +0x20 = local PlayerGameData
BOX = 0x492AFF8          # u32 own total (+0), u32 publish count (+4); text padding, guest-writable
CAVE_LO, CAVE_HI = 0x563ECBC, 0x563ED00
FREE_LO, FREE_HI = 0x563EC20, 0x563ED00

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
        for i in range(len(arrays[name])):
            shipped[a + i] = name
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other helper's *_live.py records
others = {}
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == 'virtue_live.py':
        continue
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', open(f).read()):
        a = int(m.group(1), 16)
        for i in range(len(m.group(3)) // 2):
            others[a + i] = os.path.basename(f)
print('other *_live.py bytes parsed: %d' % len(others))


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
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def beq(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 0
def bne(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 1
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt


CMN_W19_1 = 0x3100067F    # cmn w19, #1
CMP_X9_X10 = 0xEB0A013F   # cmp x9, x10
ADD_W9_1 = 0x11000529     # add w9, w9, #1

listing = []
groups = {}


def no_collision(a, n=4):
    for i in range(n):
        assert a + i not in shipped, 'collides with shipped %s at %x' % (shipped[a + i], a)
        assert a + i not in others, 'collides with %s at %x' % (others[a + i], a)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    no_collision(addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def cave(name, start, ws, expect):
    assert len(ws) == len(expect)
    for i, w in enumerate(ws):
        a = start + i * 4
        assert CAVE_LO <= a < CAVE_HI, 'cave word %x outside the slot' % a
        o = a - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % a
        no_collision(a)
        got = dis1(a, w)
        assert got == expect[i], 'cave %x: %s, expected %s' % (a, got, expect[i])
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        listing.append('  0x%x %s' % (start + i * 4, dis1(start + i * 4, w)))
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)]


# ---------------------------------------------------------------- the cave slot and the box are unreferenced
def refs_into(lo, hi):
    hits = []
    w = struct.unpack('<%dI' % (len(TXT) // 4), TXT[:len(TXT) // 4 * 4])
    for i, x in enumerate(w):
        if (x & 0x7C000000) == 0x14000000:                    # b / bl
            imm = x & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            if lo <= i * 4 + imm * 4 < hi:
                hits.append(('branch', i * 4))
        elif (x & 0x9F000000) == 0x90000000:                  # adrp + next use of rd
            rd = x & 31
            imm = (((x >> 5) & 0x7FFFF) << 2) | ((x >> 29) & 3)
            if imm & (1 << 20):
                imm -= 1 << 21
            page = ((i * 4) & ~0xFFF) + (imm << 12)
            if page != lo & ~0xFFF and page != (hi - 1) & ~0xFFF:
                continue
            for j in range(i + 1, min(i + 12, len(w))):
                y = w[j]
                if ((y >> 5) & 31) != rd:
                    continue
                if (y & 0xFF800000) == 0x91000000:
                    off = (y >> 10) & 0xFFF
                elif (y & 0x3B000000) == 0x39000000:
                    off = ((y >> 10) & 0xFFF) << (y >> 30)
                else:
                    break
                if lo <= page + off < hi:
                    hits.append(('adrp', i * 4))
                break
    for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 8):
            v = struct.unpack_from('<Q', seg, o)[0]
            if lo <= v < hi:
                hits.append(('pointer', base + o))
    return hits


r = refs_into(CAVE_LO, CAVE_HI)
assert not r, 'cave slot referenced: %r' % r[:5]
listing.append('cave slot 0x%X..0x%X: zero, no shipped / *_live.py record, no branch / adrp / pointer reaches it'
               % (CAVE_LO, CAVE_HI))
r = refs_into(BOX, BOX + 8)
# our own cave is not in the text yet; anything found here is somebody else's use of the box
assert not r, 'box referenced: %r' % r[:5]
no_collision(BOX, 8)
lan = open(LAN, encoding='utf-8', errors='ignore').read()
for a in range(BOX, BOX + 8, 4):
    assert ('0x%X' % a) not in lan and ('0x%x' % a) not in lan, 'box word %x named in dusk_lan.cpp' % a
assert len(TXT) <= BOX - 0 or TXT[BOX:BOX + 8] in (b'', b'\0' * 8), 'box not zero in main_text.bin'
listing.append('box 0x%X..0x%X: past the text file end 0x492AD90 (NSO header), not named in dusk_lan.cpp, '
               'not referenced, no record' % (BOX, BOX + 8))

# ================================================================ 1. VIRTUE_PUB
listing.append('=== VIRTUE_PUB')
HOOK = 0x149062C
# context of the getter 0x1490460 [V]: x21 = win-point object (pgd+0x46D8) or 0 / non-pointer on the -1 path,
# w19 = result (-1 = no such player); every exit goes through 0x149062C; x9/x10 are dead after it.
for a, t in ((0x1490558, 'ldr x21, [x8, #0x46d8]'), (0x1490564, 'cbz x21, #0x149062c'),
             (0x1490570, 'add w19, w0, w19'), (0x1490574, 'b #0x149062c'), (0x1490578, 'mov w19, #-1'),
             (0x1490580, 'cbz x21, #0x149062c'), (0x1490628, 'add w19, w22, w19'),
             (0x1490630, 'ldp x20, x19, [sp, #0x70]'), (0x1490634, 'ldp x22, x21, [sp, #0x60]'),
             (0x1490638, 'ldp x24, x23, [sp, #0x50]'), (0x149063c, 'ldp x29, x30, [sp, #0x40]'),
             (0x1490640, 'add sp, sp, #0x80'), (0x1490644, 'retab')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
# the win-point object keeps its owner pgd at +8: ctor 0xF709C4 `stp x8, x1, [x0]` [V]
assert dis1(0xF70A0C, word(0xF70A0C)) == 'stp x8, x1, [x0]'
assert dis1(0x1823CBC, word(0x1823CBC)) == 'bl #0xf709c4' and dis1(0x1823CC0, word(0x1823CC0)) == 'str x21, [x20, #0x46d8]'

C = CAVE_LO
OUT = C + 15 * 4
pub = [
    CMN_W19_1,                       # 0  w19 == -1: no player
    beq(C + 4, OUT),                 # 1
    cbz_x(C + 8, 21, OUT),           # 2  no win-point object (x21 == 0)
    ldr_x(9, 21, 8),                 # 3  x9 = owner pgd
    adrp(C + 16, 10, GDM),           # 4
    ldr_x(10, 10, GDM & 0xFFF),      # 5  x10 = game data manager
    cbz_x(C + 24, 10, OUT),          # 6
    ldr_x(10, 10, 0x20),             # 7  x10 = local pgd
    CMP_X9_X10,                      # 8
    bne(C + 36, OUT),                # 9  not the local player
    adrp(C + 40, 10, BOX),           # 10
    str_w(19, 10, BOX & 0xFFF),      # 11 box+0 = own total
    ldr_w(9, 10, (BOX + 4) & 0xFFF), # 12
    ADD_W9_1,                        # 13
    str_w(9, 10, (BOX + 4) & 0xFFF), # 14 box+4 += 1
    word(HOOK),                      # 15 OUT: mov w0, w19 (the hooked word)
    b(C + 64, HOOK + 4),             # 16 back to 0x1490630
]
pub_expect = ['cmn w19, #1', 'b.eq #0x%x' % OUT, 'cbz x21, #0x%x' % OUT, 'ldr x9, [x21, #8]',
              'adrp x10, #0x5b57000', 'ldr x10, [x10, #0xeb8]', 'cbz x10, #0x%x' % OUT, 'ldr x10, [x10, #0x20]',
              'cmp x9, x10', 'b.ne #0x%x' % OUT, 'adrp x10, #0x492a000', 'str w19, [x10, #0xff8]',
              'ldr w9, [x10, #0xffc]', 'add w9, w9, #1', 'str w9, [x10, #0xffc]', 'mov w0, w19', 'b #0x1490630']
assert C + len(pub) * 4 <= CAVE_HI
groups['VIRTUE_PUB_CAVE'] = cave('VIRTUE_PUB', C, pub, pub_expect)
groups['VIRTUE_PUB'] = [text_patch(HOOK, 'mov w0, w19', b(HOOK, C), 'Virtue getter exit -> publish cave')]

# ================================================================ 2. VIRTUE_TIEBREAK
listing.append('=== VIRTUE_TIEBREAK')
# 0xF88D60 = ranking functor (vtable 0x56EA0D0 slot +0x30, used only by the ranking 0xF871C0) [V]
assert dis1(0xF88E74, word(0xF88E74)) == 'strh w21, [x8, #6]'          # total stays
assert dis1(0xF88E98, word(0xF88E98)) == 'strh w0, [x8, #0x16]'        # player-number index stays
tb = []
for a, reg, off, what in ((0xF88E78, 22, 0x8, 'category sum 0'), (0xF88E7C, 24, 0xA, 'category sum 1'),
                          (0xF88E80, 25, 0xC, 'category sum 2'), (0xF88E88, 26, 0xE, 'category sum 3'),
                          (0xF88E8C, 27, 0x10, 'category sum 4'), (0xF88E90, 28, 0x12, 'category sum 5'),
                          (0xF88E94, 20, 0x14, 'pgd+0x6C')):
    old = word(a)
    exp = 'strh w%d, [x8, #%s]' % (reg, hex(off) if off >= 10 else str(off))
    new = (old & ~31) | 31
    assert dis1(a, new) == 'strh wzr, [x8, #%s]' % (hex(off) if off >= 10 else str(off))
    tb.append(text_patch(a, exp, new, what + ' -> 0'))
groups['VIRTUE_TIEBREAK'] = tb

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['VIRTUE_PUB_CAVE', 'VIRTUE_PUB', 'VIRTUE_TIEBREAK']
notes = {
    'VIRTUE_PUB_CAVE': 'publish cave: own total -> box main+0x492AFF8, count +0x492AFFC (inert until VIRTUE_PUB)',
    'VIRTUE_PUB': 'Virtue getter 0x1490460 exit -> publish cave (needs the assist half to have any effect on peers)',
    'VIRTUE_TIEBREAK': 'ranking key = (total, player-number index): categories and pgd+0x6C not compared',
}
out = ['"""Virtue groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by virtue_gen.py (original-word checks, capstone listing of every new word, collision checks against',
       'patch_manager.cpp, every other diag/net/*_live.py, branch / adrp / pointer scans of the cave and the box).',
       'Not live-tested. Notes: virtue_notes.md. Cave records have orig "00000000" (zero padding past the ro file end).',
       'Apply VIRTUE_PUB_CAVE before VIRTUE_PUB. Apply on EVERY game. VIRTUE_PUB alone changes nothing visible:',
       'the LAN assist must copy each game\'s box into the other games\' PlayerGameData copies (virtue_notes.md 5)."""',
       '',
       'BOX = 0x492AFF8          # u32 own total (banked pgd+0x42C8 + counters), u32 publish count at +4',
       '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'virtue_live.py'), 'w').write('\n'.join(out) + '\n')
print('virtue_live.py written')
