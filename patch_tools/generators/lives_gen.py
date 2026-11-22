"""Generator + checker for the final's two-lives groups in lives_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every other diag/net/*_live.py; writes lives_live.py,
prints a capstone listing of every new word).
python lives_gen.py

Groups (design and [V]/[I] marks: lives_notes.md):
  LIVES_D2_CAVE / LIVES_D2_FLAG
      0xD2 apply 0x17FB880 (runs on every game when a peer's {player no, stock} arrives): besides the stock
      write, set the respawn flag chr+0x26E4 bit 16 (= byte +0x26E6 bit 0) on that peer's chr, unless the chr
      is already in a respawn (chrdata+0x2D0 bit 0, set by 0x116C0C0). This is the flag the dying game sets on
      its own chr at 0x17B1FBC; the host's death list 0x116AF3C reads it.
  LIVES_STOCK_CAVE / LIVES_STOCK_FALLBACK
      host death list partition 0x116AF40: a REMOTE dead chr without the flag still goes to the respawn list
      when the host's copy of its stock (pgd+0x42A4) is > 0, and the host consumes one life (0xE96F74(stock-1)),
      as the dying game did. Covers "death seen before the 0xD2 arrived". The local chr keeps the stock rule.
  LIVES_RETRY_CAVE / LIVES_RETRY   (NEW 2026-11-14, lives_stuck_notes.md)
      respawn queue C+0xD0 in 0x116A6A0: the warp call 0x17BEE4C returns 0 for the LOCAL chr when
      pgd+0x46B2 != 0 or [[chr+0x18]+0x30]+0x18 bit 0 is set, and the stock code drops the queue entry
      anyway (0x116ABBC..0x116AAE0) -> the guest stays dead for good with chrdata+0x2D0 bit 0 set (its own
      life step then skips) and the host never re-lists it. Keep the entry and retry next frame while the
      chr is local and chrdata+0x2D0 bit 0 is still set. Remote entries (the host's copies) unchanged.
Caves: 0x563EC20 (6 words, ends 0x563EC38) and 0x563E880 (18 words, ends 0x563E8C8), inside the free ranges
0x563EC20..0x563ECFF and 0x563E820..0x563E8DF; kept clear of msgtrace.py's live tracer (0x563E800..0x563E877),
the census proposals (0x563EC40..) and closewhy's data (0x563E8E0..).
LIVES_RETRY cave: 0x563EC40 (17 words, ends 0x563EC84), inside 0x563EC40..0x563ECBB (the census drafts there were
never shipped; virtue_live.py VIRTUE_PUB_CAVE starts at 0x563ECBC)."""
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
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

STOCK_SET = 0xE96F74   # (chrdata, new): pgd+0x42A4 = min(new, cap) when new <= current; no message

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


# ---------------------------------------------------------------- other helpers' *_live.py records
others = {}   # byte address -> file
for fn in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(fn) == 'lives_live.py':
        continue
    body = open(fn, encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*["\']([0-9A-Fa-f]*)["\']\s*,\s*["\']([0-9A-Fa-f]+)["\']', body):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            others[a + i] = os.path.basename(fn)
print('other *_live.py bytes parsed: %d' % len(others))

FREE = [(0x563E820, 0x563E8E0), (0x563EC20, 0x563ED00)]
RESERVED = [
    (0x563E800, 0x563E878, 'diag/twin/msgtrace.py live tracer (10 + 4*5 words at 0x563E800)'),
    (0x563E8E0, 0x563E900, 'closewhy_live.py data at 0x563E8E0'),
    (0x563ECBC, 0x563ED00, 'virtue_live.py VIRTUE_PUB_CAVE 0x563ECBC..0x563ECFF'),
]


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
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def beq(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5)
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def tbnz0(pc, rt, t): return 0x37000000 | (_rel(pc, t, 14) << 5) | rt     # tbnz wRt, #0
def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt


BLR_X8 = 0xD63F0100
CMP_X8_X19 = 0xEB13011F
MOV_X0_X19 = 0xAA1303E0

listing = []
groups = {}


BUILT = {'LIVES_D2', 'LIVES_STOCK'}   # built into patch_manager.cpp: shipped bytes there must equal ours


def _shipped_ok(a, newword, built):
    nb = struct.pack('<I', newword)
    for i in range(4):
        if a + i in shipped:
            assert built, 'collides with a shipped record at %x' % a
            assert shipped[a + i] == nb[i], 'shipped byte at %x differs from this group' % (a + i)


def text_patch(addr, expect, new, note, built=False):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    _shipped_ok(addr, new, built)
    for i in range(4):
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def cave(name, start, ws, expect):
    assert len(ws) == len(expect)
    for i in range(len(ws)):
        a = start + i * 4
        assert any(lo <= a < hi for lo, hi in FREE), 'cave word %x outside the free ranges' % a
        o = a - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % a
        _shipped_ok(a, ws[i], name in BUILT)
        for j in range(4):
            assert a + j not in others, 'cave collides with %s at %x' % (others[a + j], a)
        for lo, hi, who in RESERVED:
            assert not (lo <= a < hi), 'cave %x in reserved range (%s)' % (a, who)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        got = dis1(start + i * 4, w)
        assert got == expect[i], 'cave %x: %s, expected %s' % (start + i * 4, got, expect[i])
        listing.append('  0x%x %s' % (start + i * 4, got))
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)]


# ---------------------------------------------------------------- the free ranges are zero and unreferenced
def free_unreferenced():
    hits = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            t = o + imm * 4
            if any(lo <= t < hi for lo, hi in FREE):
                hits.append(('branch', o))
    for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 8):
            v = struct.unpack_from('<Q', seg, o)[0]
            if any(lo <= v < hi for lo, hi in FREE):
                hits.append(('pointer', base + o))
    for lo, hi in FREE:
        for a in range(lo, hi, 4):
            o = a - RO_BASE
            assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'free range not zero at %x' % a
    return hits


refs = free_unreferenced()
assert not refs, 'free range referenced: %r' % refs[:5]
listing.append('free ranges %s: zero in the files, no branch/pointer reaches them'
               % ', '.join('0x%X..0x%X' % r for r in FREE))
shipped_in_free = sorted(a for a in shipped if any(lo <= a < hi for lo, hi in FREE))
others_in_free = sorted(set((a, others[a]) for a in others if any(lo <= a < hi for lo, hi in FREE)))
listing.append('shipped bytes in the free ranges: %d; other *_live.py bytes there: %s'
               % (len(shipped_in_free), sorted(set(f for _, f in others_in_free)) or 'none'))

# ---------------------------------------------------------------- context the groups rely on [V]
ctx = [
    # dying game's own decision (0x17B1EC8, chr vt slot 0x572C8D8)
    (0x17B1EEC, 'tbnz w8, #0, #0x17b1f38'),      # flag already set -> nothing
    (0x17B1EF8, 'tbnz w8, #0, #0x17b1f38'),      # chrdata+0x2D0 bit 0 (in respawn) -> nothing
    (0x17B1F98, 'cbz w8, #0x17b1f38'),           # stock 0 -> nothing (eliminated by the host)
    (0x17B1FA4, 'bl #0xe96f74'),                 # stock - 1
    (0x17B1FB0, 'bl #0x14e9ed4'),                # 0xD2 {player no, stock-1}
    (0x17B1FB8, 'orr w8, w8, #0x10000'),         # own respawn flag
    # 0xD2 apply on a peer (functor vtable 0x572E1A8 slot 6, from reader 0x14EA03C called at 0x17DDC74)
    (0x17FBCD8, 'cbz x20, #0x17fbce8'),
    (0x17FBCDC, 'ldr w1, [x19, #4]'),
    (0x17FBCE0, 'ldr x0, [x20, #0x20]'),
    (0x17FBCE8, 'ldp x20, x19, [sp, #0xa0]'),
    # host death list partition (0x116A6A0, offline path; shipped 0x116ACE0 sends only the host there)
    (0x116AE70, 'mov w28, #0x26e6'),
    (0x116AE90, 'ldr x0, [x22]'),
    (0x116AE94, 'cbz x0, #0x116b92c'),
    (0x116AF3C, 'ldrb w8, [x19, x28]'),
    (0x116AF44, 'ldp x8, x9, [sp, #0x148]'),
    (0x116AE80, 'ldur x8, [x29, #-0xf8]'),
    (0x116B68C, 'blr x8'),                       # C9 record stock = chr vt+0x298 -> +0x42A4
    (0x116B698, 'ldrb w8, [x0, x8]'),
    (0x116C1C4, 'bl #0xe96f74'),                 # C9 apply writes the record stock
    (0x116C1B4, 'orr w9, w9, #1'),               # and chrdata+0x2D0 bit 0
]
for a, t in ctx:
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
assert dis1(0x116ACE0, struct.unpack('<I', shipped_word(0x116ACE0))[0]) == 'b #0x563eb00', 'host gate not shipped'
assert dis1(0x563EB0C, struct.unpack('<I', shipped_word(0x563EB0C))[0]) == 'cbnz w9, #0x563eb14'
assert dis1(0x563EB14, struct.unpack('<I', shipped_word(0x563EB14))[0]) == 'b #0x116ae14'
assert dis1(0x116B6B8, struct.unpack('<I', shipped_word(0x116B6B8))[0]) == 'bl #0x563eb20', 'C9 broadcast not shipped'
assert shipped_word(0x11435B0).hex().upper() == '1F2003D5', 'out-on-death record not shipped'
listing.append('context: host-only death list (0x116ACE0 -> 0x563EB00), C9 broadcast (0x116B6B8 -> 0x563EB20), '
               '0x11435B0 nop: all shipped')

# copied words (same encodings as the stock code)
W_ORR = word(0x17B1FB8)        # orr w8, w8, #0x10000
W_MOV42A4 = word(0x17B1F8C)    # mov w8, #0x42a4
W_LDRB_X0X8 = word(0x17B1F94)  # ldrb w8, [x0, x8]
W_SUB1 = word(0x17B1F9C)       # sub w1, w8, #1
assert dis1(0, W_ORR) == 'orr w8, w8, #0x10000'
assert dis1(0, W_MOV42A4) == 'mov w8, #0x42a4'
assert dis1(0, W_LDRB_X0X8) == 'ldrb w8, [x0, x8]'
assert dis1(0, W_SUB1) == 'sub w1, w8, #1'

# ================================================================ LIVES_D2
listing.append('=== LIVES_D2')
D2 = 0x563EC20
d2 = [
    ldrb(8, 0, 0x2D0),                 # w8 = chrdata+0x2D0 (x0 = chr+0x20, loaded at 0x17FBCE0)
    tbnz0(D2 + 4, 8, D2 + 20),         # in a respawn already -> stock write only
    ldr_w(8, 20, 0x26E4),              # x20 = the peer's chr (non-null, 0x17FBCD8)
    W_ORR,
    str_w(8, 20, 0x26E4),              # respawn flag, as the dying game set it on its own chr
    b(D2 + 20, STOCK_SET),             # tail call: x0/w1 untouched, returns to 0x17FBCE8
]
groups['LIVES_D2_CAVE'] = cave('LIVES_D2', D2, d2, [
    'ldrb w8, [x0, #0x2d0]', 'tbnz w8, #0, #0x563ec34', 'ldr w8, [x20, #0x26e4]', 'orr w8, w8, #0x10000',
    'str w8, [x20, #0x26e4]', 'b #0xe96f74'])
groups['LIVES_D2_FLAG'] = [
    text_patch(0x17FBCE4, 'bl #0xe96f74', bl(0x17FBCE4, D2), '0xD2 apply: stock write + peer respawn flag', built=True),
]

# ================================================================ LIVES_STOCK
listing.append('=== LIVES_STOCK')
ST = 0x563E880
L_RESP, L_NO = ST + 16 * 4, ST + 17 * 4
st = [
    tbnz0(ST, 8, L_RESP),              # flag set -> respawn list (stock rule)
    ldr_x(8, 22, 0),                   # x8 = world chr manager (x22 = its GOT slot, checked at 0x116AE94)
    ldr_x(8, 8, 0x1A8),                # local player chr
    CMP_X8_X19,
    beq(ST + 16, L_NO),                # local chr: keep the stock rule (no flag = out)
    ldr_x(8, 19, 0),
    MOV_X0_X19,
    ldr_x(8, 8, 0x298),
    BLR_X8,                            # x0 = this game's PlayerGameData copy of that player (as 0x116B68C)
    cbz_x(ST + 36, 0, L_NO),
    W_MOV42A4,
    W_LDRB_X0X8,                       # w8 = stock this game holds for the player
    cbz_w(ST + 48, 8, L_NO),           # no life left -> out
    W_SUB1,
    ldr_x(0, 19, 0x20),                # chrdata
    bl(ST + 60, STOCK_SET),            # consume the life here too (the late 0xD2 then writes the same value)
    b(L_RESP, 0x116AF44),              # L_RESP: respawn list
    b(L_NO, 0x116AE80),                # L_NO: stays in the dead list (eliminated)
]
groups['LIVES_STOCK_CAVE'] = cave('LIVES_STOCK', ST, st, [
    'tbnz w8, #0, #0x563e8c0', 'ldr x8, [x22]', 'ldr x8, [x8, #0x1a8]', 'cmp x8, x19', 'b.eq #0x563e8c4',
    'ldr x8, [x19]', 'mov x0, x19', 'ldr x8, [x8, #0x298]', 'blr x8', 'cbz x0, #0x563e8c4', 'mov w8, #0x42a4',
    'ldrb w8, [x0, x8]', 'cbz w8, #0x563e8c4', 'sub w1, w8, #1', 'ldr x0, [x19, #0x20]', 'bl #0xe96f74',
    'b #0x116af44', 'b #0x116ae80'])
groups['LIVES_STOCK_FALLBACK'] = [
    text_patch(0x116AF40, 'tbz w8, #0, #0x116ae80', b(0x116AF40, ST), 'host partition: remote with a life left respawns', built=True),
]

# ================================================================ LIVES_RETRY
listing.append('=== LIVES_RETRY')
for a, t in [
    (0x116AB94, 'mov w2, #1'),
    (0x116ABB8, 'bl #0x17bee4c'),                # warp/respawn the queued chr (returns 0 = not done)
    (0x116ABBC, 'sub x0, x29, #0xa0'),           # hook: moved into the cave
    (0x116ABC0, 'bl #0x1d053e0'),                # point-object dtor: moved into the cave
    (0x116ABC4, 'b #0x116aad8'),
    (0x116AAD8, 'adrp x22, #0x59df000'),         # x22 reloaded here: dead between 0x116ABB8 and 0x116AAD8
    (0x116AADC, 'ldr x22, [x22, #0xe68]'),
    (0x116AAE0, 'cmp x24, x27'),                 # remove the entry (stock)
    (0x116A900, 'ldr x8, [x19, #0x138]'),        # keep the entry, next one (as the timer / fade waits)
    (0x116A904, 'add x27, x27, #0xc'),
    (0x116A874, 'cbz x21, #0x116aae0'),          # chr gone -> removed (bounds the retry)
    (0x116A880, 'ldr x9, [x8, #0x1a8]'),         # local chr -> no timer, only the fade wait 0x116A8EC
    (0x17BEEC4, 'mov w8, #0x46b2'),              # 0x17BEE4C: pgd+0x46B2 != 0 -> return 0
    (0x17BEF54, 'ldrb w8, [x8, #0x18]'),         # local: [[chr+0x18]+0x30]+0x18 bit 0 -> return 0
    (0x17BEF58, 'tbnz w8, #0, #0x17beed0'),
]:
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
RT = 0x563EC40
R_KEEP, R_REMOVE, R_DONE = RT + 14 * 4, RT + 15 * 4, RT + 16 * 4


def adrp(pc, rd, target):
    d = (target >> 12) - (pc >> 12)
    assert -(1 << 20) <= d < (1 << 20)
    d &= (1 << 21) - 1
    return 0x90000000 | ((d & 3) << 29) | ((d >> 2) << 5) | rd


def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def bne(pc, t): return 0x54000001 | (_rel(pc, t, 19) << 5)
def tbz0(pc, rt, t): return 0x36000000 | (_rel(pc, t, 14) << 5) | rt


rt = [
    0x2A0003F6,                        # mov w22, w0   (warp result; x22 is reloaded at 0x116AAD8)
    word(0x116ABBC),                   # sub x0, x29, #0xa0
    bl(RT + 8, 0x1D053E0),             # dtor (as 0x116ABC0)
    cbnz_w(RT + 12, 22, R_DONE),       # warp done -> stock removal
    adrp(RT + 16, 22, 0x59DF000),
    word(0x116AADC),                   # ldr x22, [x22, #0xe68]  (WCM GOT slot, as 0x116AAD8/DC)
    ldr_x(8, 22, 0),
    cbz_x(RT + 28, 8, R_REMOVE),
    ldr_x(8, 8, 0x1A8),
    0xEB15011F,                        # cmp x8, x21  (queued chr == local player?)
    bne(RT + 40, R_REMOVE),            # remote copy (host side): stock behaviour
    ldr_x(8, 21, 0x20),
    ldrb(8, 8, 0x2D0),
    tbz0(RT + 52, 8, R_REMOVE),        # no longer in a respawn (revived some other way) -> drop
    b(R_KEEP, 0x116A900),              # keep the entry: retried next frame
    b(R_REMOVE, 0x116AAE0),
    b(R_DONE, 0x116AAD8),
]
groups['LIVES_RETRY_CAVE'] = cave('LIVES_RETRY', RT, rt, [
    'mov w22, w0', 'sub x0, x29, #0xa0', 'bl #0x1d053e0', 'cbnz w22, #0x563ec80', 'adrp x22, #0x59df000',
    'ldr x22, [x22, #0xe68]', 'ldr x8, [x22]', 'cbz x8, #0x563ec7c', 'ldr x8, [x8, #0x1a8]', 'cmp x8, x21',
    'b.ne #0x563ec7c', 'ldr x8, [x21, #0x20]', 'ldrb w8, [x8, #0x2d0]', 'tbz w8, #0, #0x563ec7c',
    'b #0x116a900', 'b #0x116aae0', 'b #0x116aad8'])
assert RT + 4 * len(rt) <= 0x563ECBC
# the new cave range: no shipped byte, no other *_live.py byte, no shipped branch into it
for a in range(0x563EC40, 0x563ECBC):
    assert a not in shipped and a not in others, 'free range 0x563EC40.. used at %x' % a
for a in sorted(set(x & ~3 for x in shipped)):
    if all(a + i in shipped for i in range(4)):
        w = struct.unpack('<I', shipped_word(a))[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            imm -= (1 << 26) if imm & (1 << 25) else 0
            assert not (0x563EC40 <= a + imm * 4 < 0x563ECBC), 'shipped branch %x into the new cave' % a
listing.append('0x563EC40..0x563ECBB: no shipped / *_live.py byte, no shipped branch into it')
groups['LIVES_RETRY'] = [
    text_patch(0x116ABBC, 'sub x0, x29, #0xa0', b(0x116ABBC, RT), 'respawn queue: failed local warp is retried'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['LIVES_D2_CAVE', 'LIVES_D2_FLAG', 'LIVES_STOCK_CAVE', 'LIVES_STOCK_FALLBACK']
NEW = ['LIVES_RETRY_CAVE', 'LIVES_RETRY']   # not built in yet: listed in NEW_ORDER, not in ORDER
out = ['"""Final two-lives groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by lives_gen.py (original-word checks, capstone listing of every new word, collision checks',
       'against patch_manager.cpp, every other diag/net/*_live.py and the reserved cave ranges). Not live-tested.',
       'Notes: lives_notes.md. Cave records have orig "00000000" (zero padding past the ro file end).',
       'Apply each *_CAVE group before its hook group. Apply on EVERY game (only the host runs the death list,',
       'but the 0xD2 apply runs everywhere and is harmless on guests). Do not install diag/twin/msgtrace.py with',
       'a longer recorder than today\'s 30 words: it would reach 0x563E880."""', '']
notes = {
    'LIVES_D2_CAVE': '0xD2 apply tail: set the peer chr respawn flag unless it is already respawning (inert until LIVES_D2_FLAG)',
    'LIVES_D2_FLAG': '0x17FBCE4 bl 0xE96F74 -> bl cave',
    'LIVES_STOCK_CAVE': 'host partition: remote dead chr with stock > 0 -> consume one life, respawn (inert until LIVES_STOCK_FALLBACK)',
    'LIVES_STOCK_FALLBACK': '0x116AF40 tbz -> b cave',
    'LIVES_RETRY_CAVE': 'respawn queue: keep a local entry whose warp 0x17BEE4C failed while chrdata+0x2D0 bit 0 is set (inert until LIVES_RETRY)',
    'LIVES_RETRY': '0x116ABBC sub x0,x29,#0xa0 -> b cave (NEW, not built in; lives_stuck_notes.md)',
}
for g in ORDER + NEW:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
out.append('NEW_ORDER = [%s]  # apply on EVERY game, cave first; independent of ORDER' % ', '.join(NEW))
open(os.path.join(HERE, 'lives_live.py'), 'w').write('\n'.join(out) + '\n')
print('lives_live.py written')
