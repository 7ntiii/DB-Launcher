"""Generator + checker for credit_live.py. Static only: reads nso/*.bin, patch_manager.cpp and every other
diag/net/*_live.py, writes credit_live.py, prints a capstone listing of every new word.
python credit_gen.py          (run from diag/net or anywhere)

Groups (design, [V]/[I]: credit_notes.md):
  KILL_CAVES     three caves in the helper cave range main+0x6B32000.. (orig "00000000"):
                   SEND3C  0x6B32000  copy of the 0x3B sender 0x14E1334 ({u16 a, u16 b} via the two-handle
                           writer 0x14FC280), type 0x3B -> 0x3C, send-to-server vt+0x48 -> broadcast vt+0x40.
                           Wire = exactly what the 0x3C answer parser 0x14ECC14 reads: {handle killer, handle victim}.
                   GATE    0x6B32200  entry gate of the death handler 0x1752400 for enemy-class chrs (vtable
                           main+0x572B108) in mode 6: the enemy owner's game (0x17EE470(WCM, chr) bit 0) decides
                           (killer = its chrdata+0x114) and broadcasts 0x3C; every other game waits for that answer
                           (bit 0x10000 at chr+0x12C5, set by the 0x3C reader) and ignores its own last hit.
                   READ    0x6B32300  0x3C reader: skip a victim whose death is already handled (bit 54 of the u64
                           at chr+0x12BC = byte +0x12C2 bit 6), so the owner's own echo and duplicates do nothing.
  KILL_OWNER     hooks: 0x175242C -> GATE, 0x1752278 request 0x3C to the server -> nop (its self echo was misread),
                 0x17E8EE0 reader vt+0x60 (from the server) -> vt+0x50 (from anyone), 0x17E8F2C -> READ.
  COLLECT_CAVE / COLLECT_ONCE   Collector add 0x15B52E0 from the award apply 0x15A5020 (tail call 0x15A5544)
                 skipped when the pgd is a copy (wp = pgd+0x46D8, wp+0x11 != 0). Safety net only: the broadcast
                 award (0x15A45D4) is for taker player numbers 10000000..10000039 (bots), not LAN players."""
import os
import re
import struct
import glob

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
CAVE_LO, CAVE_HI = 0x6B32000, 0x6B33000        # this helper's part of the cave region main+0x6B30000..
ENEMY_VT = 0x572B108
MGR3 = 0x5B3CE08                               # *(main+0x5B3CE08) = mgr3, +0x1268 = mode (6 in LAN)
WCM_GOT = 0x59DFE68                            # GOT slot -> WCM pointer variable (0x1752464 / 0x175246C)

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
            shipped[a + i] = bt
print('shipped bytes parsed: %d' % len(shipped))
assert len(shipped) > 1000, 'patch_manager.cpp parse failed'

# ---------------------------------------------------------------- every other helper's records
others = {}
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == 'credit_live.py':
        continue
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)",\s*(True|False)\)',
                         open(f, encoding='utf-8', errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            others.setdefault(a + i, os.path.basename(f))
print('other *_live.py bytes parsed: %d' % len(others))
assert not any(CAVE_LO <= a < CAVE_HI for a in list(shipped) + list(others)), 'cave range 0x6B32000.. used elsewhere'


def word(off):
    assert off + 4 <= len(TXT), 'outside main_text.bin: %x' % off
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


# ---------------------------------------------------------------- tiny assembler (each word re-checked by capstone)
def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bcond(pc, t, cond): return 0x54000000 | (_rel(pc, t, 19) << 5) | cond       # eq 0, ne 1
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt


def tb(pc, rt, bit, t, nz):
    return ((0x37000000 if nz else 0x36000000) | ((bit >> 5) << 31) | ((bit & 31) << 19)
            | (_rel(pc, t, 14) << 5) | rt)


def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb_w(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt
def ldur_w(rt, rn, off): return 0xB8400000 | ((off & 0x1FF) << 12) | (rn << 5) | rt
def add_x(rd, rn, imm, sh=0): return 0x91000000 | (sh << 22) | (imm << 10) | (rn << 5) | rd
def cmp_x(rn, rm): return 0xEB00001F | (rm << 16) | (rn << 5)
def cmp_w_imm(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def mov_x(rd, rm): return 0xAA0003E0 | (rm << 16) | rd


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


NOP, RET = 0xD503201F, 0xD65F03C0
listing = []
groups = {}


def free(addr):
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    free(addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def cave(name, start, ws, expect):
    """ws: words; expect: capstone text per word (None = not checked, e.g. relocated copy words)."""
    assert len(ws) == len(expect)
    out = []
    listing.append('--- %s at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        a = start + i * 4
        assert CAVE_LO <= a < CAVE_HI, 'cave word %x outside 0x6B32000..0x6B32FFF' % a
        free(a)
        txt = dis1(a, w)
        if expect[i] is not None:
            assert txt == expect[i], 'cave %x: %s, expected %s' % (a, txt, expect[i])
        listing.append('  0x%x %s' % (a, txt))
        out.append((a, '00000000', hexw(w), True))
    return out


# ================================================================ facts the design depends on [V]
# death decider 0x1751AA0, mode-6 branch: request 0x3C {handle victim = chrdata+0x78, bool} to the server
ctx(0x1752258, 'cmp w10, #6')
ctx(0x175225C, 'b.ne #0x17522b4')
ctx(0x1752260, 'tbnz w9, #0x19, #0x17522f4')     # a hit went through the damage path -> no request at all
ctx(0x1752264, 'ldr w9, [x0, #0x78]')
ctx(0x175227C, 'b #0x17522f4')
ctx(0x14E167C, 'mov w1, #0x3c')
ctx(0x14E1680, 'ldr x8, [x8, #0x48]')
ctx(0x14E1620, 'bl #0x14fc3fc')                  # request writer: handle + bool (0x48ae748)
# offline branch of the decider: sets bit 0x10000 at +0x12C5, then 0x1752400
ctx(0x17522E0, 'orr w8, w8, #0x10000')
ctx(0x17522F0, 'bl #0x1752400')
# death handler 0x1752400 entry: bit 52 (damage path) or bit 0x10000 (decider / 0x3C answer); state bits 53-54
ctx(0x175241C, 'mov w8, #0x12bc')
ctx(0x1752420, 'mov x19, x0')
ctx(0x1752424, 'add x8, x0, x8')
ctx(0x1752428, 'ldr x9, [x8]')
ctx(0x1752430, 'ldur w10, [x8, #9]')
ctx(0x1752440, 'and x10, x10, #0x10000')
ctx(0x175244C, 'b #0x1752b84')
ctx(0x1752450, 'and x10, x9, #0x60000000000000')
ctx(0x1752454, 'mov x11, #0x20000000000000')
ctx(0x1752458, 'cmp x10, x11')
ctx(0x175245C, 'b.ne #0x1752b84')
ctx(0x1752460, 'orr x9, x9, #0x40000000000000')  # latch: handled once per chr per game
ctx(0x1752468, 'str x9, [x8]')
ctx(0x1752470, 'ldr x0, [x22]')                   # x0 / x22 reloaded after the latch: cave may clobber them
ctx(0x1752478, 'ldr x8, [x19, #0x20]')
ctx(0x1752B84, 'ldp x20, x19, [sp, #0x90]')       # common return
ctx(0x1752B98, 'retab')
ctx(0x1752410, 'stp x22, x21, [sp, #0x80]')       # frame (x30 saved) exists before 0x175242C: bl from the cave ok
ctx(0x1752408, 'stp x29, x30, [sp, #0x60]')
# damage path 0x175EBE0: writes the last attacker, sets bit 52 for a local / locally controlled attacker
ctx(0x175EC3C, 'bl #0xe8e380')
ctx(0x175ED54, 'orr x8, x8, #0x10000000000000')
ctx(0x175ED60, 'bl #0x1752400')
# kill functions set bit 53 then call 0x1752400 (e.g. 0x174EB30 / 0x174EB44)
ctx(0x174EB30, 'orr x9, x9, #0x20000000000000')
ctx(0x174EB44, 'b #0x1752400')
# 0x3C answer reader in 0x17E7B60: from the server (vt+0x60); {u16 killer @sp+0x4A0, u16 victim @sp+0x4A2}
ctx(0x17E8ED8, 'mov w1, #0x3c')
ctx(0x17E8EE4, 'mov x4, xzr')                     # vt+0x50 (0x1CD8E40) ignores x4 (R1 recipe)
ctx(0x17E8F18, 'ldrh w8, [sp, #0x4a2]')
ctx(0x17E8F28, 'bl #0x17e7828')
ctx(0x17E8F30, 'ldr w8, [x0, x24]')
ctx(0x17E8F38, 'ldrh w1, [sp, #0x4a0]')
ctx(0x17E8F3C, 'orr w8, w8, #0x10000')
ctx(0x17E8F48, 'bl #0xe8e67c')
ctx(0x17E8F50, 'bl #0x1752400')
ctx(0x17E8E94, 'mov w24, #0x12c5')
# x9 is not read in the reader loop 0x17E8E9C..0x17E8F5C (READ cave uses it)
for a in range(0x17E8E9C, 0x17E8F5C, 4):
    t = dis1(a, word(a))
    assert not re.search(r'[, \[]x9\b|[, \[]w9\b', ' ' + t.split(' ', 1)[-1]), 'x9 used in reader at %x: %s' % (a, t)
# parser 0x14ECC14 reads two handles with 0x19D7B60 (table 0x5B972CC); writer 0x14FC280 writes two handles
# with the same table (GOT 0x59E92A8 -> 0x5B972CC): wire-compatible
ctx(0x14ECC7C, 'bl #0x19d7b60')
ctx(0x14ECC94, 'bl #0x19d7b60')
ctx(0x19D7CBC, 'adrp x8, #0x5b97000')
ctx(0x19D7CC0, 'add x8, x8, #0x2cc')
ctx(0x14FC2D8, 'ldr x11, [x11, #0x2a8]')
ctx(0x14FC340, 'ldrh w9, [x20, #2]')
assert struct.unpack_from('<Q', DATA, 0x59E92A8 - DATA_BASE)[0] == 0x5B972CC, 'handle table GOT'
# owner test 0x17EE470(x0 = WCM, x1 = chr): owner[] of the chr's sync set >= 0 (WCM+0x540 = SM)
ctx(0x17EE548, 'ldr x9, [x20, #0x540]')
ctx(0x17EE5A0, 'ldrsh w8, [x9, x8, lsl #1]')
ctx(0x17EE5A8, 'cset w20, ge')
# 0x3C attribute (ro 0x4C4B3AC + 8*type, byte 4) = 0x00: broadcast reaches every member incl. the self link
assert RO[0x4C4B3AC - RO_BASE + 8 * 0x3C + 4] == 0x00, '0x3C routing byte'
assert not any(a in shipped or a in others for a in range(0x4C4B3AC + 8 * 0x3C, 0x4C4B3AC + 8 * 0x3D))

# ================================================================ SEND3C: relocated copy of 0x14E1334
S0, S1 = 0x14E1334, 0x14E1468                    # 0x14E1468 = next pacibsp
assert word(S0) == 0xD503237F and word(S1) == 0xD503237F
ctx(0x14E134C, 'strh w1, [x29, #0x1c]')
ctx(0x14E1354, 'strh w2, [x29, #0x1e]')
ctx(0x14E13C0, 'bl #0x14fc280')
ctx(0x14E141C, 'mov w1, #0x3b')
ctx(0x14E1420, 'ldr x8, [x8, #0x48]')
ctx(0x14E1464, 'bl #0x472ca08')
SEND = 0x6B32000
send_words, send_expect = [], []
for a in range(S0, S1, 4):
    w = word(a)
    na = SEND + (a - S0)
    txt = dis1(a, w)
    if (w & 0x9F000000) == 0x90000000:                       # adrp
        imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
        if imm & (1 << 20):
            imm -= 1 << 21
        t = (a & ~0xFFF) + (imm << 12)
        nw = adrp(na, w & 31, t)
        exp = txt
    elif (w & 0x7C000000) == 0x14000000:                     # b / bl
        imm = w & 0x3FFFFFF
        t = a + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        if S0 <= t < S1:
            t = SEND + (t - S0)
        nw = (bl if w & 0x80000000 else b)(na, t)
        exp = '%s #0x%x' % ('bl' if w & 0x80000000 else 'b', t)
    elif ((w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000
          or (w & 0x7E000000) == 0x36000000):                # b.cond / cbz / tbz: must stay inside
        tt = int(txt.rsplit('#0x', 1)[1], 16)
        assert S0 <= tt < S1, 'external cond branch at %x' % a
        nw = w
        exp = txt.rsplit('#0x', 1)[0] + '#0x%x' % (SEND + tt - S0)
    else:
        assert (w & 0x9F000000) != 0x10000000, 'adr at %x' % a
        assert (w & 0x3B000000) != 0x18000000, 'literal load at %x' % a
        nw = w
        exp = txt
    if a == 0x14E141C:
        nw, exp = 0x52800781, 'mov w1, #0x3c'                # type 0x3C
    if a == 0x14E1420:
        nw, exp = ldr_x(8, 8, 0x40), 'ldr x8, [x8, #0x40]'   # broadcast instead of send-to-server
    if exp.startswith('adrp'):
        exp = dis1(na, nw)
        assert exp.split('#')[1] == txt.split('#')[1], 'adrp page changed at %x' % a
    send_words.append(nw)
    send_expect.append(exp)

# ================================================================ GATE at 0x6B32200
G = 0x6B32200
L = {}                                           # labels (word index)
L.update(ORIG=37, NOTOWN=27, RELOAD=33, ORIG2=39, RETW=40)
g = [None] * 41
pc = lambda i: G + 4 * i
g[0] = ldr_x(10, 19, 0)                          # vtable of the dying chr
g[1] = adrp(pc(1), 11, ENEMY_VT)
g[2] = add_x(11, 11, ENEMY_VT & 0xFFF)
g[3] = cmp_x(10, 11)
g[4] = bcond(pc(4), pc(L['ORIG']), 1)            # not an enemy-class chr (players, objects): original code
g[5] = adrp(pc(5), 10, MGR3)
g[6] = ldr_x(10, 10, MGR3 & 0xFFF)
g[7] = cbz_x(pc(7), 10, pc(L['ORIG']))           # no session manager (offline): original code
g[8] = ldr_w(10, 10, 0x1268)
g[9] = cmp_w_imm(10, 6)
g[10] = bcond(pc(10), pc(L['ORIG']), 1)          # not mode 6: original code
g[11] = word(0x1752450)                          # and x10, x9, #0x60000000000000
g[12] = word(0x1752454)                          # mov x11, #0x20000000000000
g[13] = word(0x1752458)                          # cmp x10, x11
g[14] = bcond(pc(14), pc(L['RETW']), 1)            # not dying, or handled already: return (no latch)
g[15] = adrp(pc(15), 10, WCM_GOT)
g[16] = ldr_x(10, 10, WCM_GOT & 0xFFF)
g[17] = ldr_x(0, 10, 0)                          # x0 = WCM
g[18] = cbz_x(pc(18), 0, pc(L['NOTOWN']))
g[19] = mov_x(1, 19)
g[20] = bl(pc(20), 0x17EE470)                    # owner of this enemy?
g[21] = tb(pc(21), 0, 0, pc(L['NOTOWN']), False)
g[22] = ldr_x(10, 19, 0x20)                      # chr data
g[23] = ldr_w(1, 10, 0x114)                      # killer = this game's last attacker (low 16 bits = handle)
g[24] = ldr_w(2, 10, 0x78)                       # victim handle (what the request carried)
g[25] = bl(pc(25), SEND)                         # broadcast 0x3C {killer, victim}
g[26] = b(pc(26), pc(L['RELOAD']))
g[27] = add_x(8, 19, 1, 1)                       # NOTOWN: x8 = chr + 0x12BC
g[28] = add_x(8, 8, 0x2BC)
g[29] = ldur_w(10, 8, 9)
g[30] = tb(pc(30), 10, 16, pc(L['RETW']), False)    # no answer from the owner yet: wait (no latch)
g[31] = ldr_x(9, 8, 0)
g[32] = b(pc(32), 0x1752460)                     # answered: handle it with the owner's killer
g[33] = add_x(8, 19, 1, 1)                       # RELOAD (owner, after the calls)
g[34] = add_x(8, 8, 0x2BC)
g[35] = ldr_x(9, 8, 0)
g[36] = b(pc(36), 0x1752460)
g[37] = tb(pc(37), 9, 52, pc(L['ORIG2']), False)  # ORIG: the replaced tbnz x9, #52, 0x1752450
g[38] = b(pc(38), 0x1752450)
g[39] = b(pc(39), 0x1752430)                     # ORIG2: bit 52 clear
g[40] = b(pc(40), 0x1752B84)                     # RETW: common return, no latch
g_exp = ['ldr x10, [x19]', 'adrp x11, #0x572b000', 'add x11, x11, #0x108', 'cmp x10, x11',
         'b.ne #0x%x' % pc(37), 'adrp x10, #0x5b3c000', 'ldr x10, [x10, #0xe08]', 'cbz x10, #0x%x' % pc(37),
         'ldr w10, [x10, #0x1268]', 'cmp w10, #6', 'b.ne #0x%x' % pc(37),
         'and x10, x9, #0x60000000000000', 'mov x11, #0x20000000000000', 'cmp x10, x11', 'b.ne #0x%x' % pc(40),
         'adrp x10, #0x59df000', 'ldr x10, [x10, #0xe68]', 'ldr x0, [x10]', 'cbz x0, #0x%x' % pc(27),
         'mov x1, x19', 'bl #0x17ee470', 'tbz w0, #0, #0x%x' % pc(27), 'ldr x10, [x19, #0x20]',
         'ldr w1, [x10, #0x114]', 'ldr w2, [x10, #0x78]', 'bl #0x%x' % SEND, 'b #0x%x' % pc(33),
         'add x8, x19, #1, lsl #12', 'add x8, x8, #0x2bc', 'ldur w10, [x8, #9]', 'tbz w10, #0x10, #0x%x' % pc(40),
         'ldr x9, [x8]', 'b #0x1752460', 'add x8, x19, #1, lsl #12', 'add x8, x8, #0x2bc', 'ldr x9, [x8]',
         'b #0x1752460', 'tbz x9, #0x34, #0x%x' % pc(39), 'b #0x1752450', 'b #0x1752430', 'b #0x1752b84']

# ================================================================ READ at 0x6B32300
R = 0x6B32300
r = [cbz_x(R, 0, R + 20),
     add_x(9, 0, 1, 1),
     ldrb_w(9, 9, 0x2C2),                        # byte chr+0x12C2: bit 6 = bit 54 of the u64 at +0x12BC
     tb(R + 12, 9, 6, R + 20, True),
     b(R + 16, 0x17E8F30),
     b(R + 20, 0x17E8F54)]                       # no victim / handled already: next message
r_exp = ['cbz x0, #0x%x' % (R + 20), 'add x9, x0, #1, lsl #12', 'ldrb w9, [x9, #0x2c2]',
         'tbnz w9, #6, #0x%x' % (R + 20), 'b #0x17e8f30', 'b #0x17e8f54']

# ================================================================ COLLECT at 0x6B32340
ctx(0x15A551C, 'mov x0, x19')
ctx(0x15A5520, 'mov x1, x20')                     # x1 = pgd of the award chr (0x15A507C vt+0x298)
ctx(0x15A5540, 'autibsp')
ctx(0x15B52FC, 'cbz x1, #0x15b53ac')              # the add accepts a null pgd: so does the cave
ctx(0x15B5300, 'adrp x8, #0x5b3c000')             # x8 is no input of 0x15B52E0
ctx(0x15A45D4, 'sub w8, w8, #0x989, lsl #12')     # [x29-0x34] - 10000000 ...
ctx(0x15A45DC, 'sub w8, w8, #0x680')
ctx(0x15A45E4, 'cmp w8, #0x27')                   # ... 0..39: broadcast (vt+0x40 at 0x15A4600)
ctx(0x15A41E8, 'stur w23, [x29, #-0x34]')         # = x2 of 0x15A3F00 (0x15A3F38 mov x23, x2) = taker player no
ctx(0x15A3F38, 'mov x23, x2')
ctx(0x159D7FC, 'ldr w28, [x8, #0xd0]')            # take wrapper: x2 = local pgd+0xD0 (player number) when -1
ctx(0x159D80C, 'csel w24, w28, w24, eq')
C = 0x6B32340
c = [cbz_x(C, 1, C + 20),
     ldr_x(8, 1, 0x46D8),
     cbz_x(C + 8, 8, C + 20),
     ldrb_w(8, 8, 0x11),
     cbnz_w(C + 16, 8, C + 24),
     b(C + 20, 0x15B52E0),
     RET]
c_exp = ['cbz x1, #0x%x' % (C + 20), 'ldr x8, [x1, #0x46d8]', 'cbz x8, #0x%x' % (C + 20), 'ldrb w8, [x8, #0x11]',
         'cbnz w8, #0x%x' % (C + 24), 'b #0x15b52e0', 'ret']

groups['KILL_CAVES'] = (cave('SEND3C (copy of 0x14E1334, type 0x3C, broadcast)', SEND, send_words, send_expect)
                        + cave('GATE (death handler 0x1752400 entry)', G, g, g_exp)
                        + cave('READ (0x3C reader: skip handled victims)', R, r, r_exp))
groups['KILL_OWNER'] = [
    text_patch(0x175242C, 'tbnz x9, #0x34, #0x1752450', b(0x175242C, G), 'death handler entry -> owner gate'),
    text_patch(0x1752278, 'bl #0x14e1590', NOP, 'no 0x3C request to the server (its self echo was misread)'),
    text_patch(0x17E8EE0, 'ldr x8, [x8, #0x60]', ldr_x(8, 8, 0x50), '0x3C answer from anyone (the owner)'),
    text_patch(0x17E8F2C, 'cbz x0, #0x17e8f54', b(0x17E8F2C, R), 'reader: skip a victim already handled'),
]
groups['COLLECT_CAVE'] = cave('COLLECT (Collector add only for the own pgd)', C, c, c_exp)
groups['COLLECT_ONCE'] = [
    text_patch(0x15A5544, 'b #0x15b52e0', b(0x15A5544, C), 'Collector add skipped for copies (wp+0x11 != 0)'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for gname, rs in groups.items():
    for a, o, n, cflag in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, gname, seen.get(a + i))
            seen[a + i] = gname
assert max(a for a in seen if a >= CAVE_LO) < CAVE_HI

print('\n'.join(listing))

ORDER = ['KILL_CAVES', 'KILL_OWNER', 'COLLECT_CAVE', 'COLLECT_ONCE']
notes = {
    'KILL_CAVES': 'SEND3C 0x6B32000, GATE 0x6B32200, READ 0x6B32300 (inert until KILL_OWNER)',
    'KILL_OWNER': 'enemy owner decides the killer and broadcasts 0x3C; every game applies that killer once',
    'COLLECT_CAVE': 'Collector add skip-for-copies cave (inert until COLLECT_ONCE)',
    'COLLECT_ONCE': 'Collector counted only into the own pgd (safety net)',
}
out = ['"""Contested-kill credit and Collector-once groups: (offset_from_main, orig_hex, new_hex, is_code).',
       'Bytes little-endian. Generated by credit_gen.py (original-word checks, capstone listing, collision checks',
       'against patch_manager.cpp and every other diag/net/*_live.py). Not live-tested. Notes: credit_notes.md.',
       'Cave records live in main+0x6B32000..0x6B32FFF (cave region main+0x6B30000.., NOT yet verified live) with',
       'orig "00000000". Apply KILL_CAVES before KILL_OWNER and COLLECT_CAVE before COLLECT_ONCE.',
       'No data records. Apply on EVERY game (a game without KILL_OWNER credits its own last hit as before)."""', '']
for gname in ORDER:
    out.append('%s = [  # %s' % (gname, notes[gname]))
    for a, o, n, cflag in groups[gname]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, cflag))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'credit_live.py'), 'w').write('\n'.join(out) + '\n')
print('credit_live.py written: %d records' % sum(len(v) for v in groups.values()))
