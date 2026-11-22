"""Generator + checker for the Trespasser / joint-struggle groups in trespasser_live.py. Static only (reads
nso/*.bin, src/lichii/src/core/file_sys/patch_manager.cpp and every diag/*/*_live.py, writes trespasser_live.py,
prints a capstone listing). python trespasser_gen.py

Groups (design and [V]/[I] marks: trespasser_notes.md). No cave: every record rewrites a stock word in place.
  JS_ISBATTLE_PARK  0x1020078 `cbz w8` -> `b #0x1020220`: the IsBattle body is skipped (what LAN does today) while
                    the next three words change. Live apply only.
  JS_HOST           H1 0x1023564 `cbnz w10` -> `cbz w10`: peer JOINT_STRUGGLE messages pass, own-link echoes are
                    judged by the shipped mask 0x943 (own kind 1/2/7/9/12 echo dropped).
                    H2 0x102006C..0x1020078: the IsBattle body (win / cancel decision, result list, kind 1/0
                    broadcast) runs when the role byte main+0x492AFD8 == 0 (host, or offline: stock behaviour)
                    instead of when the offline flag is set. Its last record's orig is the PARK word.
  JS_HOST_BUILD     the same five words with stock originals (for patch_manager.cpp / a fresh nso).
Apply on EVERY game (guests need H1 to accept the host's kind 1; H2 keeps them idle)."""
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
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

ROLE = 0x492AFD8     # GENERATOR_IDLE role byte: 0 = host / offline, 1 = guest (dusk_lan.cpp)

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


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return bytes(shipped[a + i] for i in range(4))


# ---------------------------------------------------------------- words claimed by other helpers' live files
others = {}
for f in glob.glob(os.path.join(HERE, '..', '*', '*_live.py')):
    if os.path.basename(f) == 'trespasser_live.py':
        continue
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"', open(f, errors='ignore').read()):
        a, n = int(m.group(1), 16), len(m.group(3)) // 2
        for i in range(n):
            others.setdefault(a + i, os.path.basename(f))
print('words claimed by other *_live.py files: %d bytes' % len(others))


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
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def ldrb_w(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


NOP = 0xD503201F
listing = []
groups = {}


def text_patch(addr, expect, new, note, orig=None):
    """Code word in main text: assert the stock instruction, no shipped / other-helper collision."""
    stock = word(addr)
    got = dis1(addr, stock)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)
    old = stock if orig is None else orig
    listing.append('  0x%x  %s  ->  %s   (%s%s)' % (addr, dis1(addr, old), dis1(addr, new), note,
                                                  '' if orig is None else ', orig = park word'))
    return (addr, hexw(old), hexw(new), True)


# ---------------------------------------------------------------- context the groups rely on [V]
# authority filter of the kind handler 0x1023500 (shipped mask 0x943, shipped mode-6 table entries 3/5/8)
for a, t in ((0x1023560, 'ldrb w10, [x21, #0x18]'), (0x1023568, 'sub w10, w8, #1'),
             (0x1023580, 'ldr w9, [x9, #0x1268]')):
    got = dis1(a, word(a))
    listing.append('  context 0x%x: %s%s' % (a, got, '' if got == t else '   (expected %s)' % t))
assert dis1(0x1023574, struct.unpack('<I', shipped_word(0x1023574))[0]) == 'mov w11, #0x943', 'JS mask not shipped'
for a, v in ((0x4C49102, '1701'), (0x4C49106, '2801'), (0x4C4910C, '4601')):
    assert all(a + i in shipped for i in range(2)), 'mode-6 table entry %x not shipped' % a
    assert bytes(shipped[a + i] for i in range(2)).hex().upper() == v, 'mode-6 table entry %x differs' % a
# IsBattle 0x1020054: the skip target of the offline test that H2 replaces
for a in (0x1020054, 0x102007C, 0x1020220):
    listing.append('  context 0x%x: %s' % (a, dis1(a, word(a))))
# the role byte is the GENERATOR_IDLE byte dusk_lan.cpp writes (main+0x492AFD8, just below ro)
assert ROLE < RO_BASE

# ================================================================ JS_ISBATTLE_PARK
listing.append('=== JS_ISBATTLE_PARK')
PARK = b(0x1020078, 0x1020220)
groups['JS_ISBATTLE_PARK'] = [
    text_patch(0x1020078, 'cbz w8, #0x1020220', PARK, 'park: IsBattle body skipped while H2 is written'),
]

# ================================================================ JS_HOST (live) / JS_HOST_BUILD
H1 = ('cbnz w10, #0x1023580', cbz_w(0x1023564, 10, 0x1023580), 'H1: peers pass, own echo judged by the mask')
H2 = [
    (0x102006C, 'adrp x8, #0x5b65000', adrp(0x102006C, 8, ROLE), 'H2: page of the role byte'),
    (0x1020070, 'ldr x8, [x8, #0xc20]', NOP, 'H2: no gamedata load'),
    (0x1020074, 'ldrb w8, [x8, #0xbda]', ldrb_w(8, 8, ROLE & 0xFFF), 'H2: w8 = role byte'),
]
FINAL = (0x1020078, 'cbz w8, #0x1020220', cbnz_w(0x1020078, 8, 0x1020220), 'H2: guests skip, host / offline decide')

listing.append('=== JS_HOST (live: after JS_ISBATTLE_PARK)')
groups['JS_HOST'] = ([text_patch(0x1023564, H1[0], H1[1], H1[2])] +
                     [text_patch(a, t, n, s) for a, t, n, s in H2] +
                     [text_patch(FINAL[0], FINAL[1], FINAL[2], FINAL[3], orig=PARK)])
listing.append('=== JS_HOST_BUILD (stock originals)')
groups['JS_HOST_BUILD'] = ([text_patch(0x1023564, H1[0], H1[1], H1[2])] +
                           [text_patch(a, t, n, s) for a, t, n, s in H2] +
                           [text_patch(*FINAL)])

# ================================================================ co-op completion (cave region, trespasser_notes 6)
# Cave slot of this helper: main+0x6B31000..0x6B317FF (the zeppelin2 groups use 0x6B31800..0x6B31FFF; another
# helper owns 0x6B30000..0x6B30FFF). The region is zero-filled by the loader (cave_region_notes.md), NOT in the nso
# files, so cave records have orig "00000000" and nothing can be read back here.
CAVE_LO, CAVE_HI = 0x6B31000, 0x6B31800
WCM_G = 0x5B3CD88    # *(main+0x5B3CD88) = WCM; +0x1A8 = local player chr [V 0x1020514, 0x1028B68, FORGE_OWN]
GD_G = 0x5B65C20     # *(main+0x5B65C20)+0xBDA = offline flag
INVITE_RADIUS = 150.0   # metres around the Trespasser [I: the server's real "nearby" rule is unknown]
RET = 0xD65F03C0


def pg(a): return a & ~0xFFF


def stp_pre(rt, rt2, rn, imm): return 0xA9800000 | (((imm // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldp_post(rt, rt2, rn, imm): return 0xA8C00000 | (((imm // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def stp_x(rt, rt2, rn, imm): return 0xA9000000 | (((imm // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldp_x(rt, rt2, rn, imm): return 0xA9400000 | (((imm // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldp_s(rt, rt2, rn, imm): return 0x2D400000 | (((imm // 4) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def str_x(rt, rn, off): return 0xF9000000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt
def ldr_s(rt, rn, off): return 0xBD400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrh_w(rt, rn, off): return 0x79400000 | ((off // 2) << 10) | (rn << 5) | rt
def strh_w(rt, rn, off): return 0x79000000 | ((off // 2) << 10) | (rn << 5) | rt
def strb_w(rt, rn, off): return 0x39000000 | (off << 10) | (rn << 5) | rt
def add_imm(rd, rn, imm): return 0x91000000 | (imm << 10) | (rn << 5) | rd
def mov_x(rd, rm): return 0xAA0003E0 | (rm << 16) | rd
def cmp_x(rn, rm): return 0xEB00001F | (rm << 16) | (rn << 5)
def cmp_w(rn, rm): return 0x6B00001F | (rm << 16) | (rn << 5)
def cmp_wi(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def csinv_w(rd, rn, rm, cond): return 0x5A800000 | (rm << 16) | (cond << 12) | (rn << 5) | rd
def fsub_s(rd, rn, rm): return 0x1E203800 | (rm << 16) | (rn << 5) | rd
def fmul_s(rd, rn, rm): return 0x1E200800 | (rm << 16) | (rn << 5) | rd
def fmadd_s(rd, rn, rm, ra): return 0x1F000000 | (rm << 16) | (ra << 10) | (rn << 5) | rd
def fcmp_s(rn, rm): return 0x1E202000 | (rm << 16) | (rn << 5)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bcond(pc, cond, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | cond
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def ldr_s_lit(pc, rt, t): return 0x1C000000 | (_rel(pc, t, 19) << 5) | rt


EQ, NE, HS, LO, HI = 0, 1, 2, 3, 8
XZR = 31
SP = 31


class Cave:
    """Tiny two-pass assembler: items are (expected capstone text or None, encoder(pc) -> word) or label strings."""
    def __init__(self, name, start):
        self.name, self.start, self.items, self.labels = name, start, [], {}

    def L(self, name):
        self.items.append(name)

    def i(self, expect, enc):
        self.items.append((expect, enc))

    def build(self):
        pc = self.start
        for it in self.items:
            if isinstance(it, str):
                self.labels[it] = pc
            else:
                pc += 4
        self.end = pc
        words, pc = [], self.start
        listing.append('--- cave %s at 0x%X' % (self.name, self.start))
        for it in self.items:
            if isinstance(it, str):
                listing.append('   %s:' % it)
                continue
            exp, enc = it
            w = enc(pc) if callable(enc) else enc
            if exp == 'DATA':
                txt = '(data word)'
            else:
                txt = dis1(pc, w)
                assert exp is None or txt == exp, '%s @%x: %s, expected %s' % (self.name, pc, txt, exp)
            listing.append('  0x%x  %08X  %s' % (pc, w, txt))
            words.append(w)
            pc += 4
        assert CAVE_LO <= self.start and self.end <= CAVE_HI, 'cave %s outside 0x%X..0x%X' % (self.name, CAVE_LO, CAVE_HI)
        for a in range(self.start, self.end):
            assert a not in shipped and a not in others, 'cave %s collides at %x' % (self.name, a)
        return [(self.start + k * 4, '00000000', hexw(w), True) for k, w in enumerate(words)]


def lbl(c, name):
    return lambda pc: c.labels[name]


# context for the three hooks [V]
for a, t in ((0x101FF48, 'mov x19, x0'), (0x101FFE0, 'mov x0, x19'), (0x101FFE4, 'bl #0x101fc28'),
             (0x101FF28, 'stp x29, x30, [sp, #-0x20]!'),
             (0x1024070, 'mov w1, #2'),                                  # kind 4 byte 5 -> SetNextStep(2) Activate
             (0x10200B8, 'ldrh w8, [x19, #0xc0]'), (0x10200CC, 'csinv w8, w9, wzr, lo'), (0x10200D4, 'bl #0x17e7828'),
             (0x102598C, 'pacibsp'), (0x10259B0, 'ldrb w23, [x1, #4]'), (0x10259BC, 'ldr w8, [x1]'),
             (0x1020DBC, 'ldur x20, [x29, #-0x48]'), (0x1020F14, 'cbz x0, #0x1020f3c'),
             (0x1020F3C, 'adrp x8, #0x5b65000'), (0x1020F48, 'cbz w8, #0x1020ffc'), (0x1020F4C, 'ldr x8, [sp, #0x40]'),
             (0x1020FFC, 'ldr x8, [x20]'), (0x1021004, 'ldr x8, [x8, #0x298]'), (0x102100C, 'cbz x0, #0x1020d20'),
             (0x1021010, 'ldr x0, [x0, #0x46d8]'), (0x102101C, 'mov w1, #0xfbd0'),
             (0x1020524, 'ldr x8, [x8, #0x1a8]'), (0x102054C, 'ldr w8, [x8, #0xd0]'),
             (0x102CC40, 'ldr w10, [x8]'), (0x102CC4C, 'add x8, x8, #0x80')):   # participants +0x2B0 stride 0x80
    got = dis1(a, word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)
    listing.append('  context 0x%x: %s' % (a, got))
assert dis1(0x1021020, word(0x1021020)) == 'movk w1, #1, lsl #16'     # 0x1FBD0 = 130000

listing.append('=== JS_COOP_CAVES')
# ---- INV: Activate (step 2) epilogue hook 0x101FFE0 -> self-invite of the LOCAL player (kind 7 apply 0x102598C)
c = Cave('JS_INV', 0x6B31000)
c.i('stp x29, x30, [sp, #-0x40]!', stp_pre(29, 30, SP, -0x40))
c.i('mov x29, sp', 0x910003FD)
c.i('stp x20, x21, [sp, #0x10]', stp_x(20, 21, SP, 0x10))
c.i('str x22, [sp, #0x20]', str_x(22, SP, 0x20))
c.i('mov x20, x19', mov_x(20, 19))                                       # instance
c.i(None, lambda pc: adrp(pc, 8, GD_G))
c.i('ldr x8, [x8, #0xc20]', ldr_x(8, 8, GD_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldrb w8, [x8, #0xbda]', ldrb_w(8, 8, 0xBDA))
c.i(None, lambda pc: cbnz_w(pc, 8, c.labels['out']))                     # offline: stock (no invite)
c.i(None, lambda pc: adrp(pc, 8, WCM_G))
c.i('ldr x8, [x8, #0xd88]', ldr_x(8, 8, WCM_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldr x21, [x8, #0x1a8]', ldr_x(21, 8, 0x1A8))                        # local player chr
c.i(None, lambda pc: cbz_x(pc, 21, c.labels['out']))
c.i('ldr x8, [x21, #0x20]', ldr_x(8, 21, 0x20))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldr x8, [x8, #0x1d0]', ldr_x(8, 8, 0x1D0))                          # its PlayerGameData
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldr w22, [x8, #0xd0]', ldr_w(22, 8, 0xD0))                          # local player number
c.i('ldr x8, [x20, #0x2b0]', ldr_x(8, 20, 0x2B0))                       # participants (0x80 each, +0 player no)
c.i('ldr x9, [x20, #0x2b8]', ldr_x(9, 20, 0x2B8))
c.L('part')
c.i('cmp x8, x9', cmp_x(8, 9))
c.i(None, lambda pc: bcond(pc, HS, c.labels['notpart']))
c.i('ldr w10, [x8]', ldr_w(10, 8, 0))
c.i('cmp w10, w22', cmp_w(10, 22))
c.i(None, lambda pc: bcond(pc, EQ, c.labels['out']))                     # already in the battle: no invite
c.i('add x8, x8, #0x80', add_imm(8, 8, 0x80))
c.i(None, lambda pc: b(pc, c.labels['part']))
c.L('notpart')
c.i(None, lambda pc: adrp(pc, 8, WCM_G))
c.i('ldr x0, [x8, #0xd88]', ldr_x(0, 8, WCM_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 0, c.labels['out']))
c.i('ldrh w8, [x20, #0xc0]', ldrh_w(8, 20, 0xC0))                        # enemy key, as IsBattle 0x10200B8..D4
c.i('ldrh w9, [x20, #0xc2]', ldrh_w(9, 20, 0xC2))
c.i('cmp w8, #0x10', cmp_wi(8, 0x10))
c.i('csinv w8, w9, wzr, lo', csinv_w(8, 9, XZR, LO))
c.i('strh w8, [sp, #0x30]', strh_w(8, SP, 0x30))
c.i('strh wzr, [sp, #0x32]', strh_w(XZR, SP, 0x32))
c.i('add x1, sp, #0x30', add_imm(1, SP, 0x30))
c.i(None, lambda pc: bl(pc, 0x17E7828))                                  # Trespasser chr
c.i(None, lambda pc: cbz_x(pc, 0, c.labels['out']))
c.i('ldr x8, [x0, #0x2470]', ldr_x(8, 0, 0x2470))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldr x8, [x8, #0xe8]', ldr_x(8, 8, 0xE8))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldp s0, s1, [x8, #0x70]', ldp_s(0, 1, 8, 0x70))                     # [[chr+0x2470]+0xE8]+0x70 = position
c.i('ldr s2, [x8, #0x78]', ldr_s(2, 8, 0x78))
c.i('ldr x8, [x21, #0x2470]', ldr_x(8, 21, 0x2470))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldr x8, [x8, #0xe8]', ldr_x(8, 8, 0xE8))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['out']))
c.i('ldp s3, s4, [x8, #0x70]', ldp_s(3, 4, 8, 0x70))
c.i('ldr s5, [x8, #0x78]', ldr_s(5, 8, 0x78))
c.i('fsub s0, s0, s3', fsub_s(0, 0, 3))
c.i('fsub s1, s1, s4', fsub_s(1, 1, 4))
c.i('fsub s2, s2, s5', fsub_s(2, 2, 5))
c.i('fmul s0, s0, s0', fmul_s(0, 0, 0))
c.i('fmadd s0, s1, s1, s0', fmadd_s(0, 1, 1, 0))
c.i('fmadd s0, s2, s2, s0', fmadd_s(0, 2, 2, 0))
c.i(None, lambda pc: ldr_s_lit(pc, 1, c.labels['r2']))
c.i('fcmp s0, s1', fcmp_s(0, 1))
c.i(None, lambda pc: bcond(pc, HI, c.labels['out']))                     # farther than the radius (or NaN)
c.i('str w22, [sp, #0x30]', str_w(22, SP, 0x30))                         # kind 7 body {u32 player, u8 type 0}
c.i('strb wzr, [sp, #0x34]', strb_w(XZR, SP, 0x34))
c.i('mov x0, x20', mov_x(0, 20))
c.i('add x1, sp, #0x30', add_imm(1, SP, 0x30))
c.i(None, lambda pc: bl(pc, 0x102598C))                                  # the kind 7 apply, locally
c.L('out')
c.i('ldr x22, [sp, #0x20]', ldr_x(22, SP, 0x20))
c.i('ldp x20, x21, [sp, #0x10]', ldp_x(20, 21, SP, 0x10))
c.i('ldp x29, x30, [sp], #0x40', ldp_post(29, 30, SP, 0x40))
c.i('mov x0, x19', mov_x(0, 19))                                         # the replaced word
c.i('ret', RET)
c.L('r2')
c.i('DATA', struct.unpack('<I', struct.pack('<f', INVITE_RADIUS * INVITE_RADIUS))[0])
INV_RECS = c.build()
INV = c.start

# ---- VOWN: Virtue 130000 push in End only for this game's local player chr (x20 = result chr)
c = Cave('JS_VIRTUE_OWN', 0x6B31140)
c.i(None, lambda pc: cbz_x(pc, 0, c.labels['skip']))                     # stock: no pgd -> next result
c.i(None, lambda pc: adrp(pc, 8, GD_G))
c.i('ldr x8, [x8, #0xc20]', ldr_x(8, 8, GD_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['chk']))
c.i('ldrb w8, [x8, #0xbda]', ldrb_w(8, 8, 0xBDA))
c.i(None, lambda pc: cbnz_w(pc, 8, c.labels['go']))                      # offline: stock (bots too)
c.L('chk')
c.i(None, lambda pc: adrp(pc, 8, WCM_G))
c.i('ldr x8, [x8, #0xd88]', ldr_x(8, 8, WCM_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['skip']))
c.i('ldr x8, [x8, #0x1a8]', ldr_x(8, 8, 0x1A8))
c.i('cmp x8, x20', cmp_x(8, 20))
c.i(None, lambda pc: bcond(pc, NE, c.labels['skip']))                    # a copy: VIRTUE_PUB shows the owner's total
c.L('go')
c.i(None, lambda pc: b(pc, 0x1021010))
c.L('skip')
c.i(None, lambda pc: b(pc, 0x1020D20))
VOWN_RECS = c.build()
VOWN = c.start

# ---- LOWN: the offline-only item lot (Power of Blood, by tier) for this game's local participant only
c = Cave('JS_LOT_OWN', 0x6B31180)
c.i(None, lambda pc: adrp(pc, 8, GD_G))
c.i('ldr x8, [x8, #0xc20]', ldr_x(8, 8, GD_G & 0xFFF))
c.i('ldrb w8, [x8, #0xbda]', ldrb_w(8, 8, 0xBDA))
c.i(None, lambda pc: cbnz_w(pc, 8, c.labels['lot']))                     # offline: stock
c.i(None, lambda pc: adrp(pc, 8, WCM_G))
c.i('ldr x8, [x8, #0xd88]', ldr_x(8, 8, WCM_G & 0xFFF))
c.i(None, lambda pc: cbz_x(pc, 8, c.labels['nolot']))
c.i('ldr x8, [x8, #0x1a8]', ldr_x(8, 8, 0x1A8))
c.i('cmp x8, x20', cmp_x(8, 20))
c.i(None, lambda pc: bcond(pc, NE, c.labels['nolot']))
c.L('lot')
c.i(None, lambda pc: b(pc, 0x1020F4C))
c.L('nolot')
c.i(None, lambda pc: b(pc, 0x1020FFC))
LOWN_RECS = c.build()
LOWN = c.start

# the caves do not overlap
spans = sorted((r[0][0], r[-1][0] + 4) for r in (INV_RECS, VOWN_RECS, LOWN_RECS))
for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
    assert a1 <= b0, 'caves overlap'
groups['JS_COOP_CAVES'] = INV_RECS + VOWN_RECS + LOWN_RECS

listing.append('=== JS_REWARD_OWN')
groups['JS_REWARD_OWN'] = [
    text_patch(0x102100C, 'cbz x0, #0x1020d20', b(0x102100C, VOWN), 'Virtue 130000 only into the local player pgd'),
    text_patch(0x1020F3C, 'adrp x8, #0x5b65000', b(0x1020F3C, LOWN), 'item lot (Power of Blood) for the local participant'),
]
listing.append('=== JS_INVITE')
groups['JS_INVITE'] = [
    text_patch(0x101FFE0, 'mov x0, x19', bl(0x101FFE0, INV), 'Activate: invite the local player if near and not in'),
]

# ---------------------------------------------------------------- inside a group no record overlaps another
for g, rs in groups.items():
    seen = set()
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x in %s' % (a + i, g)
            seen.add(a + i)

print('\n'.join(listing))

ORDER = ['JS_ISBATTLE_PARK', 'JS_HOST', 'JS_COOP_CAVES', 'JS_REWARD_OWN', 'JS_INVITE']
out = ['"""Trespasser / joint-struggle patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian.',
       'Generated by trespasser_gen.py (stock-word checks, capstone listing of every cave word, collision checks against',
       'patch_manager.cpp and every diag/*/*_live.py). Not live-tested. Notes: trespasser_notes.md (section 6).',
       'Live: JS_ISBATTLE_PARK, then JS_HOST (its last record expects the park word), then JS_COOP_CAVES (inert), then',
       'JS_REWARD_OWN and JS_INVITE (hooks). Build: JS_HOST_BUILD + JS_COOP_CAVES + JS_REWARD_OWN + JS_INVITE.',
       'JS_COOP_CAVES lives in the 64 KB cave region main+0x6B31000..0x6B311AF (orig "00000000"; the region must be',
       'mapped by the loader, cave_region_notes.md, NOT verified live). Apply on EVERY game. Needs the shipped',
       'JOINT_STRUGGLE records (mask 0x943, mode-6 entries 3/5/8)."""', '']
notes = {
    'JS_ISBATTLE_PARK': 'IsBattle body skipped while JS_HOST rewrites its gate (live only)',
    'JS_HOST': 'H1 peer JOINT_STRUGGLE pass + H2 host decides the battle (win -> kind 1 -> End -> Virtue 130000)',
    'JS_COOP_CAVES': 'INV (self-invite at Activate), VOWN (Virtue own game), LOWN (item lot own game); inert alone',
    'JS_REWARD_OWN': 'End: Virtue 130000 and the Power of Blood item lot only for the local player chr',
    'JS_INVITE': 'Activate: "Answer co-op battle request?" for the local player if within %.0f m and not a participant'
                 % INVITE_RADIUS,
    'JS_HOST_BUILD': 'same as JS_HOST with stock originals (no park)',
}


def dis_or_data(a, hx):
    try:
        return dis1(a, struct.unpack('<I', bytes.fromhex(hx))[0])
    except AssertionError:
        return 'data'


for g in ORDER + ['JS_HOST_BUILD']:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),  # %s -> %s' % (a, o, n, c, dis_or_data(a, o), dis_or_data(a, n)))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'trespasser_live.py'), 'w').write('\n'.join(out) + '\n')
print('trespasser_live.py written')
