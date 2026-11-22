"""Generator + checker for the Sigil (sub quest) LAN groups in sigil_live.py. Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes sigil_live.py, prints a
capstone listing of every new word. Design and [V]/[I] marks: sigil_full_notes.md.
python sigil_gen.py

Stage A (assignment, every game holds the same entries):
  SIGIL_A_TARGETS_NC  no-cave variant: 0x11960B8 target kind 0x24 -> 0x26 (adds the [GDM+0x30] player array).
                      Self is NOT filtered (only use if sigils.py shows the local pgd outside [GDM+0x30]).
  SIGIL_A_CAVES       caves in main+0x6B30000..0x6B3013F (inert until SIGIL_A):
                        SELF  0x6B30000  drops the own player number from the producer's target vector
                        PRE   0x6B30040  MatchPreprocess: clear the per-match flag; LAN skips the early producer
                        FRAME 0x6B30060  per frame (shipped reread cave, mode 6): once per match, at the first
                                         UpdatePhase frame (par+0x50 == 6) with own no != -1 and SQM+0x28 set,
                                         run the producer (own entry + targets + 0x88 broadcast), then reread
                        MERGE 0x6B30100  apply 0x1195C40: order-independent merge of own / target entries
  SIGIL_A             hooks (0x26 kind, self filter, PRE, FRAME, MERGE). Apply on EVERY game. Needs the built-in
                      SUBQUEST + SIGIL_OWN (checked below).
  SIGIL_A_KEEP_CAVES / SIGIL_A_KEEP   optional diagnostic: the per-slot setter 0x1179770 ignores value -1
                      (only if the breakpoint test shows a -1 overwrite after the apply; see notes 2.3).
Flag word: main+0x6B30FFC (zero at boot, guest-written once per match; not a record)."""
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

GDM = 0x5B57EB8      # *(GDM)+0x20 = local PlayerGameData; pgd+0xD0 = player no
PAR = 0x5B3CDF8      # stage/phase object; par+0x50 = step (6 = UpdatePhase)
SQM = 0x5B3CE18      # sub quest manager; +0x28 must be non-null (0x1181E3C)
PRODUCER, READER, APPLY = 0x1195E40, 0x1195B00, 0x1195C40
MY_LO, MY_HI = 0x6B30000, 0x6B31000           # this helper's slice of the 64 KB cave region
FLAG = 0x6B30FFC

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

# ---------------------------------------------------------------- other helpers' live files
others = {}
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith('_live.py') or fn == 'sigil_live.py':
        continue
    body = open(os.path.join(HERE, fn), encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', body):
        a = int(m.group(1), 16)
        nb = bytes.fromhex(m.group(3))
        for i in range(len(nb)):
            if shipped.get(a + i) == nb[i]:
                continue        # the same record as the built-in one (e.g. events_live.py SUBQUEST)
            others.setdefault(a + i, fn)
print('bytes claimed by other *_live.py files: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def shipped_word(a):
    assert all(a + i in shipped for i in range(4)), 'no shipped word at %x' % a
    return struct.unpack('<I', bytes(shipped[a + i] for i in range(4)))[0]


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


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bcond(pc, t, c): return 0x54000000 | (_rel(pc, t, 19) << 5) | c
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt


EQ, NE = 0, 1
NOP, RET = 0xD503201F, 0xD65F03C0
listing, groups = [], {}


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def shipped_patch(addr, expect, new, note):
    old = shipped_word(addr)
    got = dis1(addr, old)
    assert got == expect, 'shipped %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        assert addr + i not in others, 'shipped word %x also patched by %s' % (addr, others[addr + i])
    listing.append('  0x%x  %s  ->  %s   (%s, shipped cave word)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


class Cave:
    """Assembler with labels; words are (callable(pc) -> u32) so branches resolve after layout."""

    def __init__(self, name, start):
        self.name, self.start, self.items, self.labels = name, start, [], {}

    def pc(self):
        return self.start + 4 * len(self.items)

    def label(self, n):
        self.labels[n] = self.pc()

    def w(self, f, expect=None):
        self.items.append((f, expect))

    def L(self, n):
        return lambda: self.labels[n]

    def build(self):
        out = []
        for i, (f, expect) in enumerate(self.items):
            pc = self.start + 4 * i
            v = f(pc) if callable(f) else f
            if expect is not None:
                got = dis1(pc, v)
                assert got == expect, '%s %x: %s, expected %s' % (self.name, pc, got, expect)
            out.append(v)
        for i in range(len(out)):
            a = self.start + 4 * i
            assert MY_LO <= a < FLAG, 'cave word %x outside main+0x6B30000..0x6B30FFB' % a
            for j in range(4):
                assert a + j not in shipped, 'cave collides with a shipped record at %x' % a
                assert a + j not in others, 'cave collides with %s at %x' % (others[a + j], a)
        listing.append('--- %s cave at 0x%X (%d words)' % (self.name, self.start, len(out)))
        for i, v in enumerate(out):
            listing.append('  0x%x %s' % (self.start + 4 * i, dis1(self.start + 4 * i, v)))
        self.words = out
        return [(self.start + 4 * i, '00000000', hexw(v), True) for i, v in enumerate(out)]


# ---------------------------------------------------------------- required built-ins
# SUBQUEST: send cave on the producer's apply call, reread cave per frame, gate cave at MatchPreprocess
assert shipped_word(0x1196404) == bl(0x1196404, 0x563EB90), 'SUBQUEST send hook not shipped'
assert shipped_word(0x1140B10) == bl(0x1140B10, 0x563EBE0), 'SUBQUEST reread hook not shipped'
assert shipped_word(0x1181E48) == b(0x1181E48, 0x563EB70), 'SUBQUEST gate hook not shipped'
assert dis1(0x1195BB8, shipped_word(0x1195BB8)) == 'ldr x8, [x8, #0x50]', '0x88 read-from-anyone not shipped'
assert dis1(0x1195BD8, shipped_word(0x1195BD8)) == 'mov w0, #1', '0x88 raw copy not shipped'
# SIGIL_OWN (built in): guests produce, host rereads, own player number into the own entry
assert shipped_word(0x563EB7C) == NOP and shipped_word(0x563EC0C) == NOP, 'SIGIL_OWN nops not shipped'
assert shipped_word(0x11963CC) == bl(0x11963CC, 0x563EAC8), 'SIGIL_OWN own-id hook not shipped'
assert dis1(0x563EAD8, shipped_word(0x563EAD8)) == 'str w11, [x10]'
listing.append('built-ins present: SUBQUEST (gate/send/reread, read-from-anyone, raw copy), SIGIL_OWN')
# kill report to everyone (needed later by stage C kill detection)
assert 0x4C4B930 in shipped and shipped[0x4C4B930] == 0x00, 'SWORD_B0_ALL not shipped'

# ---------------------------------------------------------------- stock context the caves rely on [V]
for a, t in ((0x11960B8, 'mov w1, #0x24'), (0x11960CC, 'bl #0xce9f40'), (0x119610C, 'ldp x25, x23, [sp, #8]'),
             (0x1196110, 'sub x8, x23, x25'), (0x1195EB4, 'cbz x19, #0x11963f0'),
             (0x1181E4C, 'bl #0x1195e40'), (0x1181E58, 'ldr x8, [x20, #0xc20]'),
             (0x1195D24, 'mov w9, #0x46e0'), (0x1195D28, 'add x26, x8, x9'), (0x1195D2C, 'ldur w8, [x19, #-8]'),
             (0x1195D30, 'str w8, [x26]'), (0x1195D54, 'ldur w20, [x19, #-4]'), (0x1195D58, 'add x0, sp, #0x30'),
             (0x1195CA4, 'subs x28, x28, #0x14'), (0x1195C90, 'lsl x28, x8, #2'),
             (0x1179778, 'stp x29, x30, [sp, #0x50]'), (0x1179788, 'ldr w8, [x0, #8]'),
             (0x117978C, 'cmp w8, #9'), (0x1179790, 'b.eq #0x1179944'), (0x1179794, 'mov w9, #0xcccd')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
assert dis1(0x563EB80, shipped_word(0x563EB80)) == 'b #0x1181e4c'
assert dis1(0x563EC10, shipped_word(0x563EC10)) == 'bl #0x1195b00'
assert dis1(0x563EB70, shipped_word(0x563EB70)) == 'cbnz w8, #0x563eb80'   # w8 = offline flag at 0x563EB80
assert dis1(0x563EC14, shipped_word(0x563EC14)) == 'ldp x0, x1, [sp, #0x10]'  # reread cave restores x0/x1

# ================================================================ SIGIL_A_TARGETS_NC (no cave)
listing.append('=== SIGIL_A_TARGETS_NC')
groups['SIGIL_A_TARGETS_NC'] = [
    text_patch(0x11960B8, 'mov w1, #0x24', 0x528004C1, 'target query kind 0x26: + [GDM+0x30] players'),
]

# ================================================================ SIGIL_A caves
listing.append('=== SIGIL_A_CAVES')
# --- SELF: bl from 0x119610C (x8..x12 free, x30 reloaded by the producer epilogue). Vector {u32 no} at
#     [sp+8, sp+0x10) of the producer frame (bl does not move sp).
c = Cave('SIGIL_SELF', 0x6B30000)
c.w(0xA940A7E8, 'ldp x8, x9, [sp, #8]')
c.w(lambda pc: adrp(pc, 10, GDM))
c.w(ldr_x(10, 10, GDM & 0xFFF), 'ldr x10, [x10, #0x%x]' % (GDM & 0xFFF))
c.w(ldr_x(10, 10, 0x20), 'ldr x10, [x10, #0x20]')            # local pgd (non-null: 0x1195EB4)
c.w(ldr_w(10, 10, 0xD0), 'ldr w10, [x10, #0xd0]')            # own player number
c.w(0xAA0803EB, 'mov x11, x8')
c.label('loop')
c.w(0xEB09011F, 'cmp x8, x9')
c.w(lambda pc: bcond(pc, c.labels['done'], EQ))
c.w(0xB840450C, 'ldr w12, [x8], #4')
c.w(0x6B0A019F, 'cmp w12, w10')
c.w(lambda pc: bcond(pc, c.labels['loop'], EQ))
c.w(0xB800456C, 'str w12, [x11], #4')
c.w(lambda pc: b(pc, c.labels['loop']))
c.label('done')
c.w(0xF9000BEB, 'str x11, [sp, #0x10]')                      # new end
c.w(word(0x119610C), 'ldp x25, x23, [sp, #8]')               # the replaced instruction
c.w(RET, 'ret')
SELF = c
self_recs = c.build()

# --- PRE: b from shipped 0x563EB80 (w8 = offline flag, x9 free)
c = Cave('SIGIL_PRE', 0x6B30040)
c.w(lambda pc: adrp(pc, 9, FLAG))
c.w(str_w(31, 9, FLAG & 0xFFF), 'str wzr, [x9, #0x%x]' % (FLAG & 0xFFF))
c.w(lambda pc: cbz_w(pc, 8, c.labels['lan']))
c.w(lambda pc: b(pc, 0x1181E4C), 'b #0x1181e4c')                   # true offline: stock producer
c.label('lan')
c.w(lambda pc: b(pc, 0x1181E58), 'b #0x1181e58')                   # LAN: produce later (FRAME)
PRE = c
pre_recs = c.build()

# --- FRAME: bl from shipped 0x563EC10 (inside the reread cave: mode == 6, x0/x1 saved by it)
c = Cave('SIGIL_FRAME', 0x6B30060)
c.w(0xA9BF7BFD, 'stp x29, x30, [sp, #-0x10]!')
c.w(0x910003FD, 'mov x29, sp')
c.w(lambda pc: adrp(pc, 10, FLAG))
c.w(ldr_w(9, 10, FLAG & 0xFFF), 'ldr w9, [x10, #0x%x]' % (FLAG & 0xFFF))
c.w(lambda pc: cbnz_w(pc, 9, c.labels['out']))
c.w(lambda pc: adrp(pc, 8, PAR))
c.w(ldr_x(8, 8, PAR & 0xFFF))
c.w(lambda pc: cbz_x(pc, 8, c.labels['out']))
c.w(ldr_w(9, 8, 0x50), 'ldr w9, [x8, #0x50]')                # stage step
c.w(0x7100193F, 'cmp w9, #6')                                 # UpdatePhase
c.w(lambda pc: bcond(pc, c.labels['out'], NE))
c.w(lambda pc: adrp(pc, 8, GDM))
c.w(ldr_x(8, 8, GDM & 0xFFF))
c.w(lambda pc: cbz_x(pc, 8, c.labels['out']))
c.w(ldr_x(8, 8, 0x20), 'ldr x8, [x8, #0x20]')
c.w(lambda pc: cbz_x(pc, 8, c.labels['out']))
c.w(ldr_w(9, 8, 0xD0), 'ldr w9, [x8, #0xd0]')
c.w(0x3100053F, 'cmn w9, #1')                                 # own number known
c.w(lambda pc: bcond(pc, c.labels['out'], EQ))
c.w(lambda pc: adrp(pc, 8, SQM))
c.w(ldr_x(8, 8, SQM & 0xFFF))
c.w(lambda pc: cbz_x(pc, 8, c.labels['out']))
c.w(ldr_x(8, 8, 0x28), 'ldr x8, [x8, #0x28]')                # C2
c.w(lambda pc: cbz_x(pc, 8, c.labels['out']))
c.w(0x52800029, 'mov w9, #1')
c.w(str_w(9, 10, FLAG & 0xFFF), 'str w9, [x10, #0x%x]' % (FLAG & 0xFFF))   # once per match
c.w(lambda pc: bl(pc, PRODUCER), 'bl #0x1195e40')            # own entry + targets, apply + 0x88 broadcast
c.label('out')
c.w(0xA8C17BFD, 'ldp x29, x30, [sp], #0x10')
c.w(lambda pc: b(pc, READER), 'b #0x1195b00')                # the shipped reread call
FRAME = c
frame_recs = c.build()

# --- MERGE: b from 0x1195D2C (apply loop; x26 = &pgd+0x46E0, x19 = entry+0xC, x28 = bytes left incl. this
#     entry, so x28 == 0x14 = last entry = the producer's own entry). x8/x9 free here.
c = Cave('SIGIL_MERGE', 0x6B30100)
c.w(word(0x1195D2C), 'ldur w8, [x19, #-8]')                  # entry quest
c.w(ldr_w(9, 26, 0), 'ldr w9, [x26]')                         # current slot 0
c.w(0x7100013F, 'cmp w9, #0')
c.w(0x3A411924, 'ccmn w9, #1, #4, ne')                        # Z: slot 0 unset (0 or -1)
c.w(lambda pc: bcond(pc, c.labels['stock'], EQ))
c.w(0xF100539F, 'cmp x28, #0x14')
c.w(lambda pc: bcond(pc, c.labels['own'], EQ))
c.w(0x2A0803F4, 'mov w20, w8')                                # target entry, slot 0 taken: passive slot 1 only
c.w(lambda pc: b(pc, 0x1195D58), 'b #0x1195d58')
c.label('own')
c.w(0x6B08013F, 'cmp w9, w8')
c.w(lambda pc: bcond(pc, c.labels['stock'], EQ))
c.w(0xB81FC269, 'stur w9, [x19, #-4]')                        # own entry over a counterpart: keep it in slot 1
c.label('stock')
c.w(lambda pc: b(pc, 0x1195D30), 'b #0x1195d30')             # str w8,[x26] ... stock
MERGE = c
merge_recs = c.build()

groups['SIGIL_A_CAVES'] = self_recs + pre_recs + frame_recs + merge_recs
listing.append('=== SIGIL_A')
groups['SIGIL_A'] = [
    text_patch(0x11960B8, 'mov w1, #0x24', 0x528004C1, 'target query kind 0x26: + [GDM+0x30] players'),
    text_patch(0x119610C, 'ldp x25, x23, [sp, #8]', bl(0x119610C, SELF.start), 'drop self from the targets'),
    text_patch(0x1195D2C, 'ldur w8, [x19, #-8]', b(0x1195D2C, MERGE.start), 'order-independent own/target merge'),
    shipped_patch(0x563EB80, 'b #0x1181e4c', b(0x563EB80, PRE.start), 'MatchPreprocess: reset flag, LAN defers'),
    shipped_patch(0x563EC10, 'bl #0x1195b00', bl(0x563EC10, FRAME.start), 'per frame: produce once at UpdatePhase'),
]

# ================================================================ SIGIL_A_KEEP (optional diagnostic)
listing.append('=== SIGIL_A_KEEP_CAVES / SIGIL_A_KEEP')
c = Cave('SIGIL_KEEP', 0x6B30140)
c.w(word(0x1179788), 'ldr w8, [x0, #8]')
c.w(0x3100043F, 'cmn w1, #1')
c.w(0x52800129, 'mov w9, #9')
c.w(0x1A880128, 'csel w8, w9, w8, eq')                        # value -1 -> key 9 -> stock early return
c.w(RET, 'ret')
KEEP = c
groups['SIGIL_A_KEEP_CAVES'] = c.build()
groups['SIGIL_A_KEEP'] = [
    text_patch(0x1179788, 'ldr w8, [x0, #8]', bl(0x1179788, KEEP.start), 'setter: ignore value -1'),
]

# ---------------------------------------------------------------- overlap checks
seen = {}
for g, rs in groups.items():
    if g == 'SIGIL_A_TARGETS_NC':
        continue            # alternative to SIGIL_A (same word), never applied together
    for a, o, n, cflag in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g
assert not any(FLAG <= a < FLAG + 4 for a in seen), 'flag word used by a record'
listing.append('no overlap between groups, with shipped records or with any other *_live.py; flag 0x%X free' % FLAG)

print('\n'.join(listing))

ORDER = ['SIGIL_A_CAVES', 'SIGIL_A', 'SIGIL_A_KEEP_CAVES', 'SIGIL_A_KEEP']
out = ['"""Sigil (sub quest) LAN groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian.',
       'Generated by sigil_gen.py (original-word checks, capstone listing, collision checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). NOT live-tested. Notes: sigil_full_notes.md.',
       'Cave records live in main+0x6B30000..0x6B30FFF (the 64 KB cave region, NOT yet verified live) with orig',
       '"00000000". Two SIGIL_A words patch SHIPPED SUBQUEST cave words: their orig is the shipped word.',
       'Flag word main+0x6B30FFC is guest-written (no record). Apply *_CAVES before its hook group.',
       'Apply on EVERY game. SIGIL_A_TARGETS_NC is the no-cave alternative to SIGIL_A (same word 0x11960B8):',
       'apply one or the other, never both."""', '']
notes = {
    'SIGIL_A_TARGETS_NC': 'NO CAVE: target kind 0x24 -> 0x26 only (self not filtered, producer still at MatchPreprocess)',
    'SIGIL_A_CAVES': 'SELF / PRE / FRAME / MERGE caves (inert until SIGIL_A)',
    'SIGIL_A': 'stage A: targets among real players, produce once at the first UpdatePhase, order-independent merge',
    'SIGIL_A_KEEP_CAVES': 'setter guard cave (inert until SIGIL_A_KEEP)',
    'SIGIL_A_KEEP': 'OPTIONAL: per-slot setter ignores -1 (only if the bp test shows a -1 overwrite)',
}
for g in ['SIGIL_A_TARGETS_NC'] + ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, cflag in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, cflag))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
out.append('FLAG = 0x%X' % FLAG)
open(os.path.join(HERE, 'sigil_live.py'), 'w').write('\n'.join(out) + '\n')
print('sigil_live.py written')
