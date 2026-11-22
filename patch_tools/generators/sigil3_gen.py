"""Generator + checker for the sigil stage C plain-word groups in sigil3_live.py. Static only (reads
nso/main_text.bin, nso/main_ro.bin, nso/main_data.bin, src/lichii/src/core/file_sys/patch_manager.cpp and the other
diag/net/*_live.py; writes sigil3_live.py; prints a capstone listing and the gate census).
python sigil3_gen.py        (run from diag/net)

Groups (design, [V]/[I] marks and the role of every gate: sigil3_notes.md):
  SIGIL3_P2        0x1195EA0 cbz x8 -> nop: the producer no longer needs a mission row (the row is never read).
  SIGIL3_ACTIVATE  0x117999C nop (start perfume give, row +0x6C x +0x64) and 0x1179F00 ccmp -> cmp w9,#0 (phase
                   perfume give, row +0x70 x +0x65, LAN now behaves as offline). Both end in 0xCF8E2C, whose gate
                   0xCF8F74 still refuses them in LAN: INERT until the item-grant whitelist (notes W1) lets the
                   return addresses 0x1179AB0 / 0x117A17C through for the local player only.
  SIGIL3_PROGRESS  0x1199790..0x1199798: the condition report 0x1199760 runs when the condition is evaluated on
                   THIS game (0x1199840) instead of "offline" -> only the owner's game sends the 0x8B kind-2 report.
                   Needs sigil_nc_live.py SIGIL_NC_EVAL. REPLACES SIGIL_NC_REPORT (never both).
  SIGIL3_COMPLETE  0x117AC08 nop: the alliance-formed hook 0x117ABE4 (Old Friend step + reward type 2) runs in LAN;
                   its only outputs are the owner-gated senders 0x117CAAC / 0x117AF0C.
  SIGIL3_STATE     (optional) 0x117AA1C cbnz -> b: the owner's game may send module state (event 0) in LAN;
                   0x1178DDC cmp w8,#2 -> #0: receivers take event 0 from the module owner without the mask test.
  SIGIL3_REWARD    no word: the award 0x1194E18 has no offline gate; 0x11950CC item lots are all -1 in the data.
  SIGIL3_HERETIC_RECV / _ASSIGN / _SELECT  H2b / H2a / H1 of sigil3_notes 6 (design + checks: sigil4_notes.md).
  SIGIL3_LISTEN    7 factory tails 0x118A5C4.. + 0x119485C cbz w8 -> nop: the class B/C target listener
                   (root+0xA0 = cond+0xC0) exists in LAN as offline, so 0x1180440 pairs the Sworn Enemy / Love /
                   Old Friend targets into the condition list the kill check 0x119B2A0 reads (sigil6_notes.md).
                   Before match load, every game, with SIGIL_NC_EVAL.
  SIGIL3_STEP / _STEP_T / _STATE  far caves (cave_lib), BUILT IN (sigil6_notes 9, sigil7_notes 1 / 3).
  SIGIL3_PAIR      review10 S2 (sigil8_notes.md): designated-target table filled by the apply (0x1195CB0), zeroed at
                   MatchPreprocess (0x1149714), class-B match wrapper (0x1197C70): quests 10/30/240/250 pair only a
                   bearer with its record target in LAN. NEW group, no built-in word, no _LIVE variant.
  SIGIL3_FRIEND    sigil10_notes.md: Old Friend (quest 30, logic vt 0x56F8A28) late pairing at the alliance. Hook
                   0x117AD18 `bl 0x117adb0` (alliance-formed hook 0x117ABE4, partner step) -> cave: in LAN, when the
                   bearer's class-B list is EMPTY and the ally holds the wanted quest (+0xCC) in slot 0 and the
                   ally's own Old Friend list is empty or holds the bearer, add the pair with the stock add
                   0x1197C80 (both directions), then the stock 0x117ADB0 (owner-gated step event 1). NEW group, stock
                   hook word (no _LIVE variant). Pays nothing itself (no type-2 row in quest 30's reward set).
W1 lives in zep3_gen.py (ZEP3_C2 -> C2L)."""
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
RO_B, DATA_B = 0x492B000, 0x563F000
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
OUT = 'sigil3_live.py'
BISECT = 'sigil_bisect_live.py'   # test-only file that puts THIS generator's built-in words back: not a collision
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

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
SHIPPED_ADDRS = {int(x, 16) for x in re.findall(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+)', src)}
DUSK_W = {int(x, 16) for x in re.findall(r'DUSK_W_([0-9A-Fa-f]{5,8})\b', src)}
print('shipped bytes parsed: %d, DUSK_W_ names: %d' % (len(shipped), len(DUSK_W)))

# ---------------------------------------------------------------- other helpers' *_live.py records
others = {}
REC = re.compile(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"\s*,\s*(True|False)\s*\)')
for f in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    fn = os.path.basename(f)
    if fn in (OUT, BISECT):
        continue
    for m in REC.finditer(open(f, encoding='utf-8', errors='ignore').read()):
        a, o, nw = int(m.group(1), 16), m.group(2).upper(), m.group(3).upper()
        for i in range(len(nw) // 2):
            others.setdefault(a + i, []).append((fn, o, nw, a))
print('other *_live.py bytes parsed: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


def bl(pc, target):
    return 0x94000000 | (((target - pc) >> 2) & 0x3FFFFFF)


def b(pc, target):
    return 0x14000000 | (((target - pc) >> 2) & 0x3FFFFFF)


NOP = 0xD503201F
listing = []
groups = {}


def text_patch(addr, expect, new, expect_new, note):
    """Code word in main text: assert original + new instruction, no collision with shipped / other live files."""
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    got_new = dis1(addr, new)
    assert got_new == expect_new, 'new at %x: %s, expected %s' % (addr, got_new, expect_new)
    if any(addr + i in shipped for i in range(4)):
        # already baked into patch_manager.cpp: allowed only as the SAME word (the group is then built in)
        sb = bytes(shipped.get(addr + i, -1) & 0xFF if addr + i in shipped else 0 for i in range(4))
        assert all(addr + i in shipped for i in range(4)), 'partial shipped record at %x' % addr
        if sb == struct.pack('<I', new):
            note += ' [BUILT IN: same word in patch_manager.cpp]'
        else:
            # built in NEUTRALISED (the record's new word = the stock word, e.g. SIGIL3_STATE's hooks in v3.6):
            # this group keeps the STOCK original, so baking it is an UPDATE of that record (update_dusk_records.py)
            assert sb == struct.pack('<I', old), 'collides with a different shipped record at %x' % addr
            note += ' [BUILT IN as the STOCK word (neutralised): baking = UPDATE]'
    else:
        assert not any(a in SHIPPED_ADDRS for a in range(addr - 3, addr + 4)), 'shipped record row at %x' % addr
        assert addr not in DUSK_W, 'DUSK_W_%X already in patch_manager.cpp' % addr
    hits = [h for i in range(4) for h in others.get(addr + i, [])]
    assert not hits, 'collides with %r at %x' % (hits, addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, got_new, note))
    return (addr, hexw(old), hexw(new), True)


# ================================================================ census: every +0xBDA read in 0x1179900..0x11A0100
census = []
for i in md.disasm(TXT[0x1179900:0x11A0100], 0x1179900):
    if i.mnemonic == 'ldrb' and i.op_str.endswith('#0xbda]'):
        census.append(i.address)
print('+0xBDA reads in 0x1179900..0x11A0100: %d (handoff 6 listed 14 + 0x1199840 + 0x1181E60)' % len(census))
print('  ' + ' '.join('%X' % a for a in census))

# ================================================================ SIGIL3_P2
# producer 0x1195E40: 0x15647A0 fills the lookup object sp+0x30..0x47 (row at sp+0x40); 0x1195EA4 reloads x8;
# sp+0x30 is next used as the OUTPUT buffer of the blr at 0x1195EEC (x8 = sp+0x30, 0x1195EE8) [V].
for a, t in ((0x1195E84, 'ldr w1, [x8, #0xb8]'), (0x1195E98, 'bl #0x15647a0'), (0x1195E9C, 'ldr x8, [sp, #0x40]'),
             (0x1195EA4, 'adrp x8, #0x5b57000'), (0x1195EA8, 'add x8, x8, #0xeb8'), (0x1195EAC, 'ldr x8, [x8]'),
             (0x1195EE8, 'add x8, sp, #0x30'), (0x1195EEC, 'blr x9'), (0x1195EF0, 'ldr w8, [sp, #0x30]')):
    ctx(a, t)
for a in range(0x1195EA4, 0x1195EE8, 4):   # no read of sp+0x30..0x47 before it is overwritten
    t = dis1(a, word(a))
    assert not re.search(r'\[sp, #0x(3[0-9a-f]|4[0-7])\]', t), 'row slot read at %x: %s' % (a, t)
listing.append('=== SIGIL3_P2')
groups['SIGIL3_P2'] = [
    text_patch(0x1195EA0, 'cbz x8, #0x11963f0', NOP, 'nop', 'P2: no mission row needed; row never read [V]'),
]
# handoff 6 (3.5 / 4.3) gives the original as "682A00B4": WRONG. That word decodes as cbz x8, #0x11963ec. The real
# word is 882A00B4 (cbz x8, #0x11963f0); a record with 682A00B4 fails the original check and is not applied.
assert groups['SIGIL3_P2'][0][1:3] == ('882A00B4', '1F2003D5'), groups['SIGIL3_P2'][0]
assert dis1(0x1195EA0, 0xB4002A68) == 'cbz x8, #0x11963ec'

# ================================================================ SIGIL3_ACTIVATE
for a, t in ((0x1179998, 'ldrb w8, [x8, #0xbda]'), (0x11799E0, 'ldr w9, [x8, #0x6c]'),
             (0x11799E8, 'ldrsb w3, [x8, #0x64]'), (0x1179AAC, 'bl #0xcf8e2c'),
             (0x1179EF0, 'ldrb w9, [x19, #0x49]'), (0x1179EF8, 'ldrb w8, [x8, #0xbda]'),
             (0x1179EFC, 'cmp w8, #0'), (0x1179F04, 'b.ne #0x117a17c'), (0x117A0AC, 'ldr w9, [x8, #0x70]'),
             (0x117A0B4, 'ldrsb w3, [x8, #0x65]'), (0x117A178, 'bl #0xcf8e2c'),
             (0xCF8F70, 'ldrb w8, [x8, #0xbda]')):
    ctx(a, t)
listing.append('=== SIGIL3_ACTIVATE (inert until the 0xCF8F74 whitelist W1 passes LR 0x1179AB0 / 0x117A17C)')
groups['SIGIL3_ACTIVATE'] = [
    text_patch(0x117999C, 'cbz w8, #0x1179ab0', NOP, 'nop', 'start: give quest row +0x6C goods x +0x64'),
    text_patch(0x1179F00, 'ccmp w9, #0, #0, ne', 0x7100013F, 'cmp w9, #0',
               'phase step: give row +0x70 x +0x65 unless module+0x49 (offline rule in LAN too)'),
]

# ================================================================ SIGIL3_PROGRESS
# 0x1199760: x19 = condition (0x119977C), x30 saved at 0x1199768 / restored 0x119981C, x0 / x8 rewritten before use
# (0x11997E4 / 0x11997AC); 0x1199840(x0 = condition) = "evaluated here" (authority 0: 1; 1: owner chr is ours;
# 2: offline flag) [V].
for a, t in ((0x1199768, 'stp x29, x30, [sp, #0x60]'), (0x119977C, 'mov x19, x0'), (0x1199784, 'blr x8'),
             (0x1199788, 'cmp w0, #1'), (0x119978C, 'b.ne #0x1199818'), (0x119979C, 'cbz w8, #0x1199818'),
             (0x11997A0, 'ldr x9, [x19, #0x58]'), (0x11997AC, 'add x8, x19, #0x10'), (0x11997E4, 'ldr x0, [x19, #8]'),
             (0x119981C, 'ldp x29, x30, [sp, #0x60]'), (0x1199840, 'pacibsp'), (0x1199898, 'ldr x0, [x19, #8]'),
             (0x11998C0, 'ldr x8, [x19, #0x1a8]'), (0x11998F4, 'bl #0x17ee470')):
    ctx(a, t)
for a in range(0x11997A0, 0x1199818, 4):   # the report body never reads x10..x17 before writing them
    t = dis1(a, word(a))
    assert not re.search(r'\b[xw]1[1-7]\b', t) or a in (0x11997C0, 0x11997C4, 0x11997C8, 0x11997D0, 0x11997D4,
                                                       0x11997DC), 'scratch use at %x: %s' % (a, t)
listing.append('=== SIGIL3_PROGRESS (with SIGIL_NC_EVAL; INSTEAD of SIGIL_NC_REPORT)')
groups['SIGIL3_PROGRESS'] = [
    text_patch(0x1199790, 'adrp x8, #0x5b65000', 0xAA1303E0, 'mov x0, x19', 'x0 = condition'),
    text_patch(0x1199794, 'ldr x8, [x8, #0xc20]', bl(0x1199794, 0x1199840), 'bl #0x1199840',
               'evaluated on this game?'),
    text_patch(0x1199798, 'ldrb w8, [x8, #0xbda]', 0x2A0003E8, 'mov w8, w0',
               'stock cbz w8 at 0x119979C now skips when NOT evaluated here'),
]

# ================================================================ SIGIL3_COMPLETE
for a, t in ((0x10ABFD4, 'bl #0x1182880'), (0x11828F4, 'bl #0x117abe4'), (0x117AD18, 'bl #0x117adb0'),
             (0x117AD70, 'bl #0x117af0c'), (0x117AEF0, 'bl #0x117caac'), (0x117AF10, 'cbz w8, #0x117b16c'),
             (0x117CAAC, 'ldrb w8, [x0, #0xa8]')):
    ctx(a, t)
listing.append('=== SIGIL3_COMPLETE')
groups['SIGIL3_COMPLETE'] = [
    text_patch(0x117AC08, 'cbz w8, #0x117ad74', NOP, 'nop',
               'alliance formed (0x1182880): partner step + reward type 2, sent only by the owner game'),
]

# ================================================================ SIGIL3_STATE (optional)
for a, t in ((0x117A9D4, 'ldrb w8, [x0, #0xa8]'), (0x117AA20, 'ldrb w8, [x19, #0xa0]'),
             (0x117AA24, 'tbz w8, #0, #0x117abc4'), (0x117AA28, 'adrp x8, #0x59df000'),
             (0x1178C88, 'ldr x9, [x22]'), (0x1178C8C, 'cmp x8, x9'), (0x1178DE0, 'b.eq #0x1178e00'),
             (0x1178DEC, 'cmn x23, #1'), (0x1178DF0, 'csel x8, x8, x9, eq'), (0x1178DFC, 'tbz w8, #0, #0x1178f54')):
    ctx(a, t)
listing.append('=== SIGIL3_STATE (B1 of review10: sender word + receive cave, offline byte-identical)')
_STATE_SENDER = text_patch(0x117AA1C, 'cbnz w8, #0x117aa28', b(0x117AA1C, 0x117AA28), 'b #0x117aa28',
                           'state sender: no client-mask bit 0 needed (owner test 0x117A9D4 stays); offline OFF != 0 '
                           'took this branch anyway')
groups['SIGIL3_REWARD'] = []

# ================================================================ SIGIL3_HERETIC_* (H1 / H2, sigil4_notes.md)
HOSTB = 0x492AFD8     # byte, 0 = host (zeppelin_nc_live S3..S6, zep3 C3)


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def cbz_w(pc, rt, t):
    o = (t - pc) >> 2
    assert -(1 << 18) <= o < (1 << 18)
    return 0x34000000 | ((o & 0x7FFFF) << 5) | rt


def fn_range(s):
    assert word(s) == 0xD503237F, 'no pacibsp at %x' % s
    e = s + 4
    while word(e) != 0xD503237F:
        e += 4
    return s, e


def branches_into(lo, hi, s, e):
    """Direct branches in [s, e) whose target lies in [lo, hi)."""
    out = []
    for a in range(s, e, 4):
        t = dis1(a, word(a))
        m = re.search(r'#0x([0-9a-f]+)$', t)
        if m and re.match(r'(b|bl|b\.\w+|cbn?z|tbn?z)$', t.split()[0]) and lo <= int(m.group(1), 16) < hi:
            out.append((a, t))
    return out


def no_read_before_write(regs, path, what):
    """Straight-line path (list of addresses): every reg in regs is written before it is read (or never used)."""
    left = set(regs)
    for a in path:
        t = dis1(a, word(a))
        mn, _, ops = t.partition(' ')
        ops = [o.strip() for o in ops.replace('[', ' ').replace(']', ' ').replace('!', ' ').split(',')]
        ops = [o.split()[0] for o in ops if o.split()]
        dst = ops[:1] if not mn.startswith(('st', 'cmp', 'cmn', 'tst', 'cb', 'tb', 'b', 'ret', 'ccmp')) else []
        src = ops[1:] if dst else ops
        for r in list(left):
            if r in src or 'w' + r[1:] in src:
                raise AssertionError('%s: %s read at %x (%s)' % (what, r, a, t))
            if r in dst or 'w' + r[1:] in dst:
                left.discard(r)
        if mn in ('bl', 'blr', 'ret', 'retab', 'br') or not left:
            return


# ---- H1: Heretic selector 0x118F260 (type-11 Eye of Muralis logic vt+0x18 0x118F1D8 at 0x118F210, vt+0x60 tail
# call 0x118F7B8) runs when offline OR on the host. Stock: OFF == 0 -> 0x118F438 (skip). The TLS sequence
# 0x118F290..0x118F2A4 (movz/movk x0 = 0x2C0, 2 nops, mrs, add x21 = tp + x0) is folded into `add x21, x8, #0x2c0`,
# which frees 4 words for the host test. x0 is next read at 0x118F2C0 (written) / inside 0x46FABD0, which sets x0
# itself (0x46FABE0) [V].
H1_FN = fn_range(0x118F260)
for a, t in ((0x118F27C, 'adrp x23, #0x5b65000'), (0x118F284, 'ldr x8, [x23, #0xc20]'),
             (0x118F288, 'ldrb w8, [x8, #0xbda]'), (0x118F2A0, 'mrs x8, tpidr_el0'), (0x118F2A8, 'ldr x20, [x21]'),
             (0x118F2AC, 'cbnz x20, #0x118f2b8'), (0x118F2B0, 'bl #0x46fabd0'), (0x118F2C0, 'mov x0, x20'),
             (0x118F2C4, 'ldr x9, [x8, #0x20]'), (0x118F3F8, 'bl #0x1184020'), (0x118F438, 'ldr x8, [x19, #0x50]'),
             (0x118F210, 'bl #0x118f260'), (0x118F7B8, 'b #0x118f260'),
             (0x46FABD0, 'pacibsp'), (0x46FABD4, 'stp x29, x30, [sp, #-0x20]!'), (0x46FABD8, 'stp x20, x19, [sp, #0x10]'),
             (0x46FABDC, 'mov x29, sp'), (0x46FABE0, 'movz x0, #0, lsl #16'), (0x46FABE4, 'movk x0, #0x2c0')):
    ctx(a, t)
assert not branches_into(0x118F290, 0x118F2A8, *H1_FN), branches_into(0x118F290, 0x118F2A8, *H1_FN)
# x9 + flags dead: proceed path 0x118F2A0..0x118F2C4 (x9 written at 0x118F2C4), skip path 0x118F438.. (blr at 0x118F44C)
no_read_before_write(['x9'], list(range(0x118F2A0, 0x118F2C8, 4)), 'H1 proceed')
no_read_before_write(['x9'], list(range(0x118F438, 0x118F450, 4)), 'H1 skip')
no_read_before_write(['x9'], list(range(0x118F450, 0x118F468, 4)), 'H1 skip (cbz 0x118F440 -> epilogue)')
# flags: proceed path 0x118F2A0..0x118F2C4 and skip path 0x118F438..0x118F464 contain no flag reader
for _a in list(range(0x118F2A0, 0x118F2C8, 4)) + list(range(0x118F438, 0x118F468, 4)):
    assert not re.match(r'(b\.|csel|csinc|csinv|cset|ccmp|adc|sbc)', dis1(_a, word(_a))), 'flags read at %x' % _a
no_read_before_write(['x0'], list(range(0x118F2A8, 0x118F2C4, 4)), 'H1 x0')
listing.append('=== SIGIL3_HERETIC_SELECT (H1: selector runs offline or on the host only)')
groups['SIGIL3_HERETIC_SELECT'] = [
    text_patch(0x118F28C, 'cbz w8, #0x118f438', adrp(0x118F28C, 9, HOSTB), 'adrp x9, #0x492a000', 'host byte page'),
    text_patch(0x118F290, 'movz x0, #0, lsl #16', 0x3940_0129 | ((HOSTB & 0xFFF) << 10), 'ldrb w9, [x9, #0xfd8]',
               'w9 = 0 on the host'),
    text_patch(0x118F294, 'movk x0, #0x2c0', 0x7100013F, 'cmp w9, #0', ''),
    text_patch(0x118F298, 'nop', 0x1A9F1508, 'csinc w8, w8, wzr, ne', 'host: w8 = 1, else w8 = OFF byte'),
    text_patch(0x118F29C, 'nop', cbz_w(0x118F29C, 8, 0x118F438), 'cbz w8, #0x118f438',
               'guest in LAN: skip (stock target)'),
    text_patch(0x118F2A4, 'add x21, x8, x0', 0x91000115 | (0x2C0 << 10), 'add x21, x8, #0x2c0', 'TLS slot tp+0x2C0 (x0 no longer set)'),
]

# ---- H2a: 0x1184020 (only caller 0x118F3F8) assigns slot-2 quest to the chosen player: owner test 0x117BCF4
# (OFF -> 1, LAN: "module chr owned here") at 0x1184128..0x1184130. With H1 it only runs offline (test = 1) or on
# the host, so dropping the test = "host may assign any player's Heretic module". Without H1 it never runs in LAN.
for a, t in ((0x1184110, 'cbz x20, #0x1184180'), (0x1184114, 'cmn w19, #1'), (0x118411C, 'ldr w8, [x20, #0x4c]'),
             (0x1184120, 'cmn w8, #1'), (0x1184124, 'b.ne #0x1184180'), (0x1184128, 'mov x0, x20'),
             (0x1184134, 'mov x0, x20'), (0x1184138, 'mov w1, w19'), (0x118413C, 'bl #0x1179770'),
             (0x1184154, 'mov w1, #1'), (0x118417C, 'bl #0x118afd4'),
             (0x117BD14, 'cbz w9, #0x117bd2c'), (0x117BD18, 'mov w0, #1')):
    ctx(a, t)
listing.append('=== SIGIL3_HERETIC_ASSIGN (H2a: host builds the chosen player\'s slot-2 module and sends 0x8B kind 1)')
groups['SIGIL3_HERETIC_ASSIGN'] = [
    text_patch(0x118412C, 'bl #0x117bcf4', NOP, 'nop', 'owner test not needed (host / offline only, H1)'),
    text_patch(0x1184130, 'tbz w0, #0, #0x1184180', NOP, 'nop', ''),
]

# ---- H2b: receiver 0x1178A50 kind 1 (0x1178CBC: slot-2 key, value 1..1e9, module+0x4C == -1 -> 0x1179770) is
# accepted from any peer, not only from the module player's own connection (pgd+0x46C8). Only kind-1 sender in
# text: 0x118417C (inside 0x1184020) [V census below]; with H1 that runs only on the host in LAN. `tst w21, #0xfe`
# also lets kind 0 through, which 0x1178C98..0x1178CA0 drops anyway (0 - 1 > 7). ldar -> ldr: the value is only
# compared, nothing is loaded through it [I strong].
H2B_FN = fn_range(0x1178A50)
for a, t in ((0x1178A6C, 'ldr x23, [x1]'), (0x1178A74, 'mov w21, w2'), (0x1178A88, 'mov x22, x1'),
             (0x1178C70, 'ldur x8, [x29, #-0x10]'), (0x1178C74, 'cbz x8, #0x1178f54'),
             (0x1178C94, 'and w8, w21, #0xff'), (0x1178C98, 'sub w8, w8, #1'), (0x1178C9C, 'cmp w8, #7'),
             (0x1178CA0, 'b.hi #0x1178f54'), (0x1178CA4, 'adrp x9, #0x4c49000'), (0x1178F48, 'sub w1, w8, #1'),
             (0x1178F50, 'bl #0x1179770'), (0x1178F54, 'ldp x20, x19, [sp, #0xa0]')):
    ctx(a, t)
assert RO[0x4C49BBC - RO_B] == 0, 'kind 1 is not case 0x1178CBC'
assert not branches_into(0x1178C7C, 0x1178C94, *H2B_FN), branches_into(0x1178C7C, 0x1178C94, *H2B_FN)
no_read_before_write(['x9'], list(range(0x1178C94, 0x1178CA8, 4)), 'H2b accept')
no_read_before_write(['x9'], list(range(0x1178F54, 0x1178F6C, 4)), 'H2b drop')
_snd = []
for _i in range(0, 0x492AD90, 4):
    _w = struct.unpack_from('<I', TXT, _i)[0]
    if (_w & 0xFC000000) == 0x94000000:
        _o = _w & 0x3FFFFFF
        if _i + 4 * (_o - (1 << 26) if _o & (1 << 25) else _o) == 0x118AFD4:
            _k = None
            for _b in range(_i - 0x40, _i, 4):
                _t = dis1(_b, word(_b))
                if _t.startswith('mov w1, '):
                    _k = _t[8:]
            _snd.append((_i, _k))
assert [a for a, k in _snd if k == '#1'] == [0x118417C], _snd
assert all(k is not None for a, k in _snd), _snd
listing.append('=== SIGIL3_HERETIC_RECV (H2b: kind 1 accepted from any peer; senders of 0x118AFD4: %s)' %
               ', '.join('%X:%s' % s for s in _snd))
groups['SIGIL3_HERETIC_RECV'] = [
    text_patch(0x1178C78, 'mov w9, #0x46c8', 0x721F1ABF, 'tst w21, #0xfe', 'kind 0 / 1?'),
    text_patch(0x1178C7C, 'add x8, x8, x9', 0x54000000 | (((0x1178C94 - 0x1178C7C) >> 2) << 5),
               'b.eq #0x1178c94', 'kind 1: skip the sender == module player test'),
    text_patch(0x1178C80, 'ldar x8, [x8]', 0xF9400108 | ((0x46C8 // 8) << 10), 'ldr x8, [x8, #0x46c8]',
               'pgd+0x46C8 (module player connection)'),
    text_patch(0x1178C84, 'cbz x8, #0x1178f54', 0xB4000000 | (((0x1178F54 - 0x1178C84) >> 2) << 5) | 8,
               'cbz x8, #0x1178f54', 'stock checks, one word earlier'),
    text_patch(0x1178C88, 'ldr x9, [x22]', 0xF94002C9, 'ldr x9, [x22]', ''),
    text_patch(0x1178C8C, 'cmp x8, x9', 0xEB09011F, 'cmp x8, x9', ''),
    text_patch(0x1178C90, 'b.ne #0x1178f54', 0x54000000 | (((0x1178F54 - 0x1178C90) >> 2) << 5) | 1,
               'b.ne #0x1178f54', ''),
]
# unchanged words carry no record (apply / bake only what changes)
groups['SIGIL3_HERETIC_RECV'] = [r for r in groups['SIGIL3_HERETIC_RECV'] if r[1] != r[2]]

# ================================================================ SIGIL3_LISTEN (sigil6_notes.md)
# Target pairing of class B / C conditions (Sworn Enemy, Love, Old Friend ...): every frame 0x1180440 collects the
# OPEN listeners (0x11843E0: module active holder +0x20 -> participants root +0x18 -> root+0xA0, listener vt+0x20 =
# not done, module+0x79 == 0) and pairs them (0x1180528 / 0x1180604 / 0x11806E8 loops: listener vt+0x10 = match
# 0x11979C0 / 0x1198198, vt+0x18 = add 0x1197C80 / 0x11982E0, which puts the partner's chr handle into the
# condition list +0x10 / +0x58). Unpaired listeners get module+0x79 = 1 (0x1180944). The kill notifier 0x175EBE0
# -> 0x11822E0(SQM, killer no) -> 0x117B5B0 counts only a victim whose handle is in that list (0x119B2A0).
# root+0xA0 = cond+0xC0 is written only when authority is 1/2 AND OFFLINE: factory tails (7) and the participants
# copy 0x1194730. Online the server paired and sent the list. In LAN: no listener -> list empty -> no kill counts.
# Change: drop the OFF test (cbz w8 -> nop) = byte-for-byte the offline wiring. Offline unchanged (OFF != 0 passes).
FAC_FN = fn_range(0x118915C)
LISTEN_GATES = (0x118A5C4, 0x118A6D0, 0x118A7DC, 0x118A8E8, 0x118A9F4, 0x118AB00, 0x118AC0C)
listing.append('=== SIGIL3_LISTEN (target pairing listener wired in LAN as offline; needs SIGIL_NC_EVAL)')
listen_rows = []
for g in LISTEN_GATES:
    for o, t in ((-0x2C, 'ldr x0, [x28, #0x90]'), (-0x24, 'ldr x8, [x0]'), (-0x20, 'ldr x8, [x8, #0x48]'),
                 (-0x1C, 'blr x8'), (-0x18, 'sub w8, w0, #1'), (-0x14, 'cmp w8, #1'), (-0x8, 'ldr x8, [x8, #0xc20]'),
                 (-0x4, 'ldrb w8, [x8, #0xbda]'), (0x4, 'add x8, x22, #0xc0'), (0x8, 'str x8, [x28, #0xa0]')):
        ctx(g + o, t)
    cont = dis1(g + 0xC, word(g + 0xC))
    assert cont.startswith('b #0x'), cont
    stock = 'cbz w8, #' + cont[3:]
    assert dis1(g - 0x10, word(g - 0x10)) == 'b.hi #' + cont[3:], 'auth 1/2 test at %x' % (g - 0x10)
    # tail start = `ldr x9, [x28, #0x90]`; the cond x22 entering it is class C (b from a case that loaded GOT 0x4E0)
    # or class B (fallthrough from the case that loaded GOT 0x4D8): the only objects with a listener at +0xC0
    t0 = g
    while dis1(t0, word(t0)) != 'ldr x9, [x28, #0x90]':
        t0 -= 4
    assert any(dis1(a, word(a)) == 'ldr x10, [x10, #0x4d8]' for a in range(t0 - 0x40, t0, 4)), 'no B case at %x' % t0
    ins = [(a, t) for a, t in branches_into(t0, g + 0x10, *FAC_FN) if not t0 <= a < g + 0x10]
    assert len(ins) == 1 and ins[0][1] == 'b #0x%x' % t0, ('tail %x' % t0, ins)
    assert any(dis1(a, word(a)) == 'ldr x9, [x9, #0x4e0]' for a in range(ins[0][0] - 0x30, ins[0][0], 4)), ins
    listen_rows.append(text_patch(g, stock, NOP, 'nop', 'factory tail %x: listener root+0xA0 = cond+0xC0 in LAN' % t0))
# participants copy 0x1194730: this+0xA0 = source root+0xA0 (x20) only offline
for a, t in ((0x11947FC, 'ldr x20, [x20, #0xa0]'), (0x1194828, 'ldr x8, [x19, #0xa0]'), (0x1194830, 'ldr x0, [x19, #0x90]'),
             (0x1194844, 'sub w8, w0, #1'), (0x1194848, 'cmp w8, #1'), (0x119484C, 'b.hi #0x1194884'),
             (0x1194858, 'ldrb w8, [x8, #0xbda]'), (0x1194860, 'str x20, [x19, #0xa0]'), (0x1194864, 'b #0x1194884')):
    ctx(a, t)
listen_rows.append(text_patch(0x119485C, 'cbz w8, #0x1194884', NOP, 'nop', 'participants copy keeps the listener'))
# the only readers of root+0xA0 in the sub quest code: collector 0x11843E0 (3 loads) and 0x1194730 itself [V scan]
for a in (0x11845A4, 0x11845F0, 0x118463C):
    ctx(a, 'ldr x%d, [x8, #0xa0]' % {0x11845A4: 21, 0x11845F0: 20, 0x118463C: 20}[a])
for a, t in ((0x118050C, 'bl #0x11843e0'), (0x118051C, 'bl #0x11843e0'), (0x1180594, 'ldr x8, [x8, #0x10]'),
             (0x11805C4, 'ldr x8, [x8, #0x18]'), (0x1180944, 'strb w9, [x8, #0x79]'),
             (0x175EFC4, 'bl #0x11822e0'), (0x1186174, 'b #0x117b5b0'), (0x117B744, 'bl #0x119b2a0'),
             (0x117B770, 'bl #0x117b83c'), (0x117B7D4, 'bl #0x117af0c'), (0x1197E14, 'strb w20, [x19, #0xd4]'),
             (0x1197EDC, 'bl #0x1199840'), (0x1197EE8, 'strb w8, [x19, #0x60]')):
    ctx(a, t)
groups['SIGIL3_LISTEN'] = listen_rows

# ================================================================ SIGIL3_STEP (sigil6_notes.md 9)
# module+0x38 (team bit mask) is ORed only by module event 1 (0x11793D8..0x11793E0). The only game-side raiser for a
# PLAYER's targets is 0x1179C40(module, flag): flag 0 = per chr of the condition list send event 1 {team} through
# 0x117CAAC (owner-gated writer+0xA8 && !+0xA9, then OFF or client bit 1, local apply 0x117CC74); flag 1 = local OR.
# Its ONLY caller is module start 0x1179BEC, for BOTS (+0x40D0 == 4) with flag 1 [V census below]. Online the
# server sent event 1 for players. The kill check 0x117B83C (from 0x117B5B0, victim already found in the list by
# 0x119B2A0) refuses a remote victim whose team bit is missing.
# Change: 0x117B770 `bl 0x117b83c` -> bl trampoline -> far cave: if (module+0x38 & 0xFFF) == 0 call
# 0x1179C40(module, 0) (owner game: sends + applies event 1 for every target = what the server sent; other games:
# returns at the owner gate), then the stock 0x117B83C(module, victim). Works for modules built at any time.
import cave_lib as C   # noqa: E402  (registry claims only through cave_lib)
_census = []
for _i in range(0, 0x492AD90, 4):
    _w = struct.unpack_from('<I', TXT, _i)[0]
    if (_w >> 26) in (0x25, 0x05):
        _o = _w & 0x3FFFFFF
        _t = _i + 4 * (_o - (1 << 26) if _o & (1 << 25) else _o)
        if _t in (0x1179C40, 0x1179C48, 0x117B83C):
            _census.append((_i, _t))
assert [a for a, t in _census if t in (0x1179C40, 0x1179C48)] == [0x1179BEC], _census
assert sorted(a for a, t in _census if t == 0x117B83C) == [0x117B770, 0x117BB14], _census
for a, t in ((0x1179BD8, 'ldrb w8, [x8, x9]'), (0x1179BDC, 'cmp w8, #4'), (0x1179BE8, 'mov w1, #1'),
             (0x1179C40, 'ldr x9, [x0, #0x20]'), (0x1179C44, 'cbz x9, #0x1179da8'), (0x1179C48, 'pacibsp'),
             (0x1179C6C, 'ldr x20, [x9, #0x28]'), (0x1179C90, 'mov w21, w1'), (0x1179CAC, 'tbz w21, #0, #0x1179d28'),
             (0x1179D40, 'ldrb w8, [x8, #0x104]'), (0x1179D48, 'mov x0, x20'), (0x1179D54, 'bl #0x117caac'),
             (0x1179DA8, 'ret'), (0x117CAAC, 'ldrb w8, [x0, #0xa8]'), (0x117CAFC, 'tbz w8, #1, #0x117ccb8'),
             (0x117CC74, 'bl #0x11792e0'), (0x11793D8, 'ldr x9, [x19, #0x38]'), (0x11793E0, 'str x8, [x19, #0x38]'),
             (0x117B764, 'bl #0x17e7828'), (0x117B768, 'mov x1, x0'), (0x117B76C, 'mov x0, x19'),
             (0x117B774, 'tbz w0, #0, #0x117b7d8'), (0x117B83C, 'pacibsp'), (0x117B95C, 'lsr x8, x9, x8'),
             (0x117B958, 'ldr x9, [x19, #0x38]')):
    ctx(a, t)
_g = C.Gen('sigil3_gen', out=OUT)
_g.others = C.live_records(exclude=(OUT, BISECT))
# SIGIL3_STEP is BUILT IN: cave_lib's free_bytes refuses shipped bytes. Allow them here and prove afterwards that
# every built-in record is byte-identical (BUILT_SAME) and every new record touches no shipped byte.
_free_orig = _g.free_bytes


def _free_builtin(a, n=4, what='word'):
    for i in range(n):
        assert a + i not in _g.others, '%s %x collides with %s' % (what, a, _g.others[a + i])


_g.free_bytes = _free_builtin


def built_same(recs, what):
    for a, o, nw, c in recs:
        bb = bytes.fromhex(nw)
        assert all(a + i in C.SHIPPED and C.SHIPPED[a + i] == bb[i] for i in range(len(bb))), \
            '%s: record %x is not the built-in word' % (what, a)


def not_shipped(recs, what, allow=()):
    for a, o, nw, c in recs:
        if a in allow:
            continue
        assert not any(a + i in C.SHIPPED for i in range(len(nw) // 2)), '%s: %x is a shipped byte' % (what, a)


_cave = _g.alloc('SIGIL3_STEP', 'FAR_CODE', 0x60, 'kill check: raise step event 1 (team mask) once, then 0x117B83C')
TST_X8_FFF = 0xF2402D1F
assert dis1(0, TST_X8_FFF) == 'tst x8, #0xfff'
_a = C.Asm(_cave)
_a(C.stp_pre('x29', 'x30', 'sp', -0x20))
_a(C.stp_x('x19', 'x20', 'sp', 0x10))
_a(C.mov_sp('x29', 'sp'))
_a(C.mov_x('x19', 'x0'))                       # module
_a(C.mov_x('x20', 'x1'))                       # victim chr
_a(C.ldr_x('x8', 'x19', 0x38))
_a(TST_X8_FFF)                                 # team bits already known (event 1 seen / sent before)?
_a(C.to(C.bne, 'check'))
_a(C.mov_x('x0', 'x19'))
_a(C.movz_w('w1', 0))                          # flag 0: send event 1 per target (owner game only) + apply here
_a.many(lambda pc, L: C.far_call(pc, 0x1179C40))
_a.label('check')
_a(C.mov_x('x0', 'x19'))
_a(C.mov_x('x1', 'x20'))
_a.many(lambda pc, L: C.far_call(pc, 0x117B83C))   # stock check, its w0 is the result
_a(C.ldp_x('x19', 'x20', 'sp', 0x10))
_a(C.ldp_post('x29', 'x30', 'sp', 0x20))
_a(C.RET)
assert len(_a.words()) * 4 <= 0x60
listing.append('=== SIGIL3_STEP (kill check raises the missing step event 1; census of 0x1179C40 / 0x117B83C callers: %s)'
               % ', '.join('%X->%X' % c for c in _census))
_step = _g.cave('SIGIL3_STEP', _cave, _a)
_step += _g.far_hook(0x117B770, 'bl #0x117b83c', _cave, scratch='x16', link=True,
                     why='the site is a bl to a normal function (0x117B83C): x16/x17 are caller-saved, the caller '
                         '0x117B5B0 never reads them after the call',
                     note='kill check -> SIGIL3_STEP cave (returns 0x117B83C result)', replaces_shipped=True)
# The hook word 0x117B770 moved to SIGIL3_STEP_T (S1), which is now BUILT IN too. SIGIL3_STEP keeps its cave +
# trampoline (built in, unreferenced); its hook record is dropped so the full sigil set has ONE writer of 0x117B770.
# _STEP_HOOK_OLD = the word the v3.6-era built-in had (bl old trampoline): orig of SIGIL3_STEP_T_LIVE (old builds).
assert _step[-1][0] == 0x117B770
_STEP_HOOK_OLD = _step[-1][2]
groups['SIGIL3_STEP'] = _step[:-1]
built_same(groups['SIGIL3_STEP'], 'SIGIL3_STEP')

# ================================================================ SIGIL3_STEP_T (review10 S1)
# Same as SIGIL3_STEP, but 0x1179C40(module, 0) only for Sworn Enemy modules: logic [[module+0x20]+0x10] with
# vtable main+0x56F7408 (GOT 0x59E3418) or main+0x56F7858 (GOT 0x59E3430), the two type-3 classes [V data]. The Eye
# (0x56F7FD0, own step 0x118F5E0 needs the Heretic SPOTTED: participant flag +8, kind 3), Love and Old Friend keep their
# own step raisers (client mask bit 1 set in 0x7F / 0x5E -> they already flow in LAN).
VT_SWORN = (0x56F7408, 0x56F7858)
for _got, _vt in ((0x59E3418, 0x56F7408), (0x59E3430, 0x56F7858)):
    assert struct.unpack_from('<Q', DATA, _got - DATA_B)[0] + 0x10 == _vt, hex(_got)
assert VT_SWORN[1] - VT_SWORN[0] == 0x450
for a, t in ((0x1177294, 'ldr x0, [x8, #0x10]'), (0x11772A0, 'ldr x8, [x8, #0x18]')):   # holder+0x10 = logic
    ctx(a, t)
_cave_t = _g.alloc('SIGIL3_STEP_T', 'FAR_CODE', 0x80, 'S1: kill check raises step event 1 for Sworn Enemy modules only')
_a = C.Asm(_cave_t)
_a(C.stp_pre('x29', 'x30', 'sp', -0x20))      # (no `mov x29, sp`: leaf-style frame, x29 restored unchanged)
_a(C.stp_x('x19', 'x20', 'sp', 0x10))
_a(C.mov_x('x19', 'x0'))                     # module
_a(C.mov_x('x20', 'x1'))                       # victim chr
_a(C.ldr_x('x8', 'x19', 0x38))
_a(TST_X8_FFF)                                 # team bits already known?
_a(C.to(C.bne, 'check'))
_a(C.ldr_x('x8', 'x19', 0x20))                 # active holder
_a(C.to(C.cbz_x, 'x8', 'check'))
_a(C.ldr_x('x8', 'x8', 0x10))                  # logic
_a(C.to(C.cbz_x, 'x8', 'check'))
_a(C.ldr_x('x8', 'x8', 0))                     # its vtable
_a(lambda pc, L: C.adrp(pc, 'x9', VT_SWORN[0]))
_a(C.add_xi('x9', 'x9', C.lo12(VT_SWORN[0])))
_a(C.cmp_xr('x8', 'x9'))
_a(C.to(C.beq, 'raise'))
_a(C.add_xi('x9', 'x9', 0x450))
_a(C.cmp_xr('x8', 'x9'))
_a(C.to(C.bne, 'check'))
_a.label('raise')
_a(C.mov_x('x0', 'x19'))
_a(C.movz_w('w1', 0))
_a.many(lambda pc, L: C.far_call(pc, 0x1179C40))
_a.label('check')
_a(C.mov_x('x0', 'x19'))
_a(C.mov_x('x1', 'x20'))
_a.many(lambda pc, L: C.far_call(pc, 0x117B83C))
_a(C.ldp_x('x19', 'x20', 'sp', 0x10))
_a(C.ldp_post('x29', 'x30', 'sp', 0x20))
_a(C.RET)
assert len(_a.words()) * 4 <= 0x80
_step_t = _g.cave('SIGIL3_STEP_T', _cave_t, _a)
_tr = _g.alloc('tramp2_117B770', 'NEAR_TRAMP', 12, 'trampoline 117B770 -> SIGIL3_STEP_T via x16')
_step_t += _g.cave('tramp2_117B770', _tr, [C.adrp(_tr, 'x16', _cave_t), C.add_xi('x16', 'x16', C.lo12(_cave_t)),
                                           C.br('x16')])
_hook_t = _g.text_patch(0x117B770, 'bl #0x117b83c', C.bl(0x117B770, _tr), 'S1 hook (x16 dead after a bl site, as '
                        'SIGIL3_STEP)', replaces_shipped=True)
groups['SIGIL3_STEP_T'] = _step_t + [_hook_t]                                    # stock original (BUILT IN now)
built_same(groups['SIGIL3_STEP_T'], 'SIGIL3_STEP_T')
# LIVE form for an OLD running build whose 0x117B770 still holds SIGIL3_STEP's bl; obsolete on a build with STEP_T.
groups['SIGIL3_STEP_T_LIVE'] = _step_t + [(0x117B770, _STEP_HOOK_OLD, _hook_t[2], True)]

# ================================================================ SIGIL3_STATE receive cave (review10 B1)
# 0x1178DDC `cmp w8, #2` (w8 = event & 0xff, w1 = event, x21 = writer) -> far cave:
#   event 2 -> 0x1178E00 (stock bypass);  event 0 AND OFF == 0 (LAN) -> 0x1178E00 (accept the owner's state);
#   else -> 0x1178DE4 (stock mask test). Offline: identical to stock (event 0 takes the mask test as before).
# The old plain-word form (cmp w8,#0) moved the bypass from event 2 to event 0 in EVERY mode (offline risk): replaced.
OFFL = 0x5B65C20
H2B_LO, H2B_HI = H2B_FN
for _x in range(H2B_LO, H2B_HI, 4):
    assert not re.search(r'\b[xw]1[67]\b', dis1(_x, word(_x))), 'x16/x17 used in 0x1178A50 at %x' % _x
for a, t in ((0x1178DD8, 'and w8, w1, #0xff'), (0x1178DE4, 'add x8, x21, #0x98'), (0x1178DE8, 'add x9, x21, #0xa0'),
             (0x1178E00, 'cmn x23, #1'), (0x1178E0C, 'cset w3, eq'), (0x1178E14, 'bl #0x11792e0')):
    ctx(a, t)
no_read_before_write(['x9'], list(range(0x1178DE4, 0x1178DF0, 4)), 'B1 stock path')
no_read_before_write(['x9'], list(range(0x1178E00, 0x1178E18, 4)), 'B1 accept path')
_rx = _g.alloc('SIGIL3_STATE_RX', 'FAR_CODE', 0x40, 'B1: receive accepts module state (event 0) from the owner in LAN')
_a = C.Asm(_rx)
_a(C.cmp_wi('w8', 2))
_a(C.to(C.beq, 'accept'))
_a(C.to(C.cbnz_w, 'w8', 'stock'))
_a(lambda pc, L: C.adrp(pc, 'x9', OFFL))
_a(C.ldr_x('x9', 'x9', C.lo12(OFFL)))
_a(C.ldrb('w9', 'x9', 0xBDA))
_a(C.to(C.cbnz_w, 'w9', 'stock'))
_a.label('accept')
_a.many(lambda pc, L: C.far_return(pc, 0x1178E00))
_a.label('stock')
_a.many(lambda pc, L: C.far_return(pc, 0x1178DE4))
_state = _g.cave('SIGIL3_STATE_RX', _rx, _a)
_state += _g.far_hook(0x1178DDC, 'cmp w8, #2', _rx, 'x16', link=False,
                      why='x16/x17 never appear in the receiver 0x1178A50 (checked); the cave exits via x16')
groups['SIGIL3_STATE'] = _state + [_STATE_SENDER]          # receive first, sender last
# v3.6 build: caves + trampoline built in as these words, the two hooks 0x1178DDC / 0x117AA1C built in as their STOCK
# words (neutralised, feature_status_v36 33b). Records unchanged; baking the hooks again = UPDATE of those records.
_STATE_HOOKS = (0x1178DDC, 0x117AA1C)
built_same([r for r in groups['SIGIL3_STATE'] if r[0] not in _STATE_HOOKS], 'SIGIL3_STATE')
for _r in groups['SIGIL3_STATE']:
    if _r[0] in _STATE_HOOKS:
        _sb = bytes(C.SHIPPED.get(_r[0] + i, 0) for i in range(4))
        assert all(_r[0] + i in C.SHIPPED for i in range(4)) and _sb.hex().upper() in (_r[1], _r[2]), hex(_r[0])
        listing.append('  SIGIL3_STATE hook 0x%X built in as %s' % (_r[0], 'STOCK (neutralised)' if
                                                                    _sb.hex().upper() == _r[1] else 'the patch word'))

# ================================================================ SIGIL3_PAIR (review10 S2, sigil8_notes.md)
# Pairing 0x1180440 pairs OPEN class-B listeners first-fit (SQM order, slot-1 list shuffled with the per-game RNG),
# mutual, each listener gets ONE frame (0x1180944: module+0x79 = 1). The class-B match 0x11979C0 (listener vt+0x10 =
# thunk 0x1197C6C `sub x0,#0xc0; b 0x11979c0`) only tests "partner's pgd slot (key % 10) == cond+0xCC" and the
# alliance rule, never the record's designated target. The designated targets exist only in the RECORD: own entry
# (last, x28 == 0x14 in the apply) {+0 own no, +4 quest, +8 -1, +0xC t1, +0x10 t2} [V 0x11963CC..0x11963D4]; the
# apply passes them only to the slot-1 module (0x1195DD0 x4 = x19), and slot 1 builds class C (factory: key % 10 == 1
# -> `cmp w8,#1` 0x1189F00), so a class-B (slot 0) condition never sees them [V]. pgd+0x46E0/+0x46E4/+0x46E8 hold
# only the slot QUESTS (0x1197AD4..0x1197B3C, 0x1179880) [V].
# Change (3 hooks, 3 caves, 1 table; no built-in word touched -> no _LIVE variant):
#   FILL  0x1195CB0 `ldur w8,[x19,#-0xc]` (every entry of the apply) -> own entry with a target: table row
#         {valid 1, hunter, t1, t2} (overwrite the hunter's row, else first free row).
#   RESET 0x1149714 `bl 0x1181d80` (MatchPreprocess, its only caller) -> zero the table, tail-jump 0x1181D80.
#   MATCH 0x1197C70 `b 0x11979c0` -> wrapper: r = stock 0x11979C0(cond, entry); if r and LAN and cond+0xCC in
#         {10, 30, 240, 250}: me = cond+0xC8 (class-B owner, factory 0x118A4EC), p = player of the partner key
#         (same decode as 0x11979C0 0x1197A00..0x1197A88); accept iff a row is (me -> p) or (p -> me); refuse if
#         me or p appears anywhere else in the table; neither known -> stock result.
TAB = _g.alloc('SIGIL3_PAIR_TAB', 'FAR_DATA', 0x80, 'S2: 8 x {valid, hunter, t1, t2} designated targets (reset at '
               'MatchPreprocess)', align=16)
assert TAB % 16 == 0
PAIR_Q = (10, 30, 240, 250)        # wanted-partner quests of the target-pairing sigils [V sigil5 role +0, I 250]
VT_B_LISTEN = 0x56F8F08             # class B listener vtable: GOT 0x59E34D8 value + 0x90 (factory 0x118A4E8)
assert struct.unpack_from('<Q', DATA, 0x59E34D8 - DATA_B)[0] + 0x90 == VT_B_LISTEN
assert struct.unpack_from('<Q', DATA, VT_B_LISTEN + 0x10 - DATA_B)[0] == 0x1197C6C      # vt+0x10 = match thunk
assert struct.unpack_from('<Q', DATA, 0x56F8FC0 + 0x10 - DATA_B)[0] == 0x119823C      # class C listener: other thunk
for a, t in ((0x1197C6C, 'sub x0, x0, #0xc0'), (0x1197C70, 'b #0x11979c0'), (0x11979C0, 'pacibsp'),
             (0x11979D8, 'ldr w8, [x1]'), (0x11979DC, 'cmp w8, #9'), (0x11979E0, 'b.eq #0x1197bbc'),
             (0x1197A24, 'lsr x10, x10, #0x23'), (0x1197A50, 'msub w10, w11, w12, w10'), (0x1197A68, 'cmp w10, #0x27'),
             (0x1197A70, 'cmp w8, w9'), (0x1197A7C, 'csel w8, w10, w8, lo'), (0x1197B40, 'ldr w10, [x19, #0xcc]'),
             (0x1197BB4, 'ldr w12, [x19, #0xc8]'), (0x1197BD0, 'retab'),
             (0x118A4D4, 'ldr w11, [sp, #0xc]'), (0x118A4EC, 'stp w11, w9, [x22, #0xc8]'),
             (0x1189F00, 'cmp w8, #1'), (0x11894E4, 'msub w8, w8, w9, w20'),
             (0x118058C, 'mov x1, x23'), (0x1180594, 'ldr x8, [x8, #0x10]'), (0x11805A4, 'mov x1, x22'),
             (0x1180674, 'mov x1, x24'), (0x118067C, 'ldr x8, [x8, #0x10]'), (0x11807CC, 'mov x1, x24'),
             (0x1195CA0, 'b #0x1195cb0'), (0x1195CB0, 'ldur w8, [x19, #-0xc]'), (0x1195CB4, 'str xzr, [sp, #8]'),
             (0x1195CB8, 'stp w8, w8, [sp, #0x28]'), (0x1195CBC, 'cmn w8, #1'), (0x1195CC0, 'b.eq #0x1195ca4'),
             (0x1195DD0, 'mov x4, x19'), (0x1195D48, 'mov x4, xzr'),
             (0x11963CC, 'stur wzr, [x11, #-0x14]'), (0x11963D0, 'stp w20, w12, [x10, #4]'),
             (0x11963D4, 'stp w8, w9, [x10, #0xc]'),
             (0x1149714, 'bl #0x1181d80'), (0x1181D80, 'pacibsp'), (0x1197AD4, 'mov w9, #0x46e0')):
    ctx(a, t)
# census: who reaches the three hook words [V]
_pc = {0x1197C6C: [], 0x1197C70: [], 0x1181D80: [], 0x1195CB0: []}
for _i in range(0, 0x492AD90, 4):
    _w = word(_i)
    _t = None
    if (_w >> 26) in (0x25, 0x05):
        _o = _w & 0x3FFFFFF
        _t = _i + 4 * (_o - (1 << 26) if _o & (1 << 25) else _o)
    elif (_w & 0xFF000010) == 0x54000000 or (_w & 0x7E000000) == 0x34000000:
        _o = (_w >> 5) & 0x7FFFF
        _t = _i + 4 * (_o - (1 << 19) if _o & (1 << 18) else _o)
    elif (_w & 0x7E000000) == 0x36000000:
        _o = (_w >> 5) & 0x3FFF
        _t = _i + 4 * (_o - (1 << 14) if _o & (1 << 13) else _o)
    if _t in _pc:
        _pc[_t].append(_i)
assert _pc == {0x1197C6C: [], 0x1197C70: [], 0x1181D80: [0x1149714], 0x1195CB0: [0x1195CA0]}, _pc
_drefs = [0x563F000 + i for i in range(0, len(DATA) - 7, 8) if struct.unpack_from('<Q', DATA, i)[0] in (0x1197C6C,
                                                                                                         0x1197C70)]
assert _drefs == [VT_B_LISTEN + 0x10], [hex(x) for x in _drefs]
# x16/x17: (a) MATCH 0x1197C70 = 2nd word of a function entered only by blr through the vtable (AAPCS64 IP0/IP1 are
# free at a function entry; 0x1197C6C does not touch them). (b) FILL: x16/x17 appear nowhere in the apply
# 0x1195C40..0x1195DFC; the built-in APPLY2 cave writes x17 / x16 before reading them. (c) RESET: a bl site; x16/x17
# appear nowhere in the caller 0x1149260..0x1149A74 nor in 0x1181D80..0x1181E98.
for lo, hi in ((0x1195C40, 0x1195DFC), (0x1149260, 0x1149A74), (0x1181D80, 0x1181E98), (0x1197C6C, 0x1197C74)):
    for _x in range(lo, hi, 4):
        assert not re.search(r'\b[xw]1[67]\b', dis1(_x, word(_x))), 'x16/x17 at %x' % _x
assert fn_range(0x1149260) == (0x1149260, 0x1149A74)
# FILL also uses x8 (written by the replaced word) and x9: x9 not read on 0x1195CB4..0x1195CE8 (then bl), nor on the
# skip / exit paths 0x1195CA4..0x1195CAC, 0x1195DDC..0x1195DF8; flags rewritten at 0x1195CBC before any reader.
no_read_before_write(['x9'], list(range(0x1195CB4, 0x1195CEC, 4)), 'FILL entry body')
for _x in list(range(0x1195CA4, 0x1195CB0, 4)) + list(range(0x1195DDC, 0x1195DFC, 4)):
    assert not re.search(r'\b[xw]9\b', dis1(_x, word(_x))), 'x9 at %x' % _x
for _x in (0x1195CB4, 0x1195CB8):
    assert not re.match(r'(b\.|csel|csinc|cset|ccmp|adc|sbc)', dis1(_x, word(_x)))


def chk(w, text):
    got = dis1(0, w)
    assert got == text, '%s != %s' % (got, text)
    return w


def ldp_w(rt, rt2, rn, off): return 0x29400000 | (((off // 4) & 0x7F) << 15) | (C.R(rt2) << 10) | (C.R(rn) << 5) | C.R(rt)
def udiv_w(rd, rn, rm): return 0x1AC00800 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
def msub_w(rd, rn, rm, ra): return 0x1B008000 | (C.R(rm) << 16) | (C.R(ra) << 10) | (C.R(rn) << 5) | C.R(rd)
def csel_w(rd, rn, rm, cond): return 0x1A800000 | (C.R(rm) << 16) | (C.COND[cond] << 12) | (C.R(rn) << 5) | C.R(rd)
def orr_w(rd, rn, rm): return 0x2A000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)
def cmn_wi(rn, imm): return 0x3100001F | (imm << 10) | (C.R(rn) << 5)
def cset_w(rd, cond): return 0x1A9F07E0 | ((C.COND[cond] ^ 1) << 12) | C.R(rd)


OFF_ = OFFL
# ---- MATCH wrapper
_m = _g.alloc('SIGIL3_PAIR_MATCH', 'FAR_CODE', 0x160,'S2: class-B match wrapper, designated targets only (LAN)')
_a = C.Asm(_m)
_a(C.stp_pre('x29', 'x30', 'sp', -0x20))
_a(C.stp_x('x19', 'x20', 'sp', 0x10))
_a(C.mov_sp('x29', 'sp'))
_a(C.mov_x('x19', 'x0'))                                   # class-B condition (thunk already did sub #0xc0)
_a(C.mov_x('x20', 'x1'))                                   # partner entry {u32 key, listener}
_a.many(lambda pc, L: C.far_call(pc, 0x11979C0))           # stock match -> w0
_a(C.to(C.cbz_w, 'w0', 'out'))                             # stock refuses: refuse
_a(lambda pc, L: C.adrp(pc, 'x8', OFF_))
_a(C.ldr_x('x8', 'x8', C.lo12(OFF_)))
_a(chk(C.ldrb('w8', 'x8', 0xBDA), 'ldrb w8, [x8, #0xbda]'))
_a(C.to(C.cbnz_w, 'w8', 'out'))                            # offline: stock result
_a(chk(C.ldr_w('w9', 'x19', 0xCC), 'ldr w9, [x19, #0xcc]'))   # wanted partner quest
for _q in PAIR_Q[:-1]:
    _a(C.cmp_wi('w9', _q))
    _a(C.to(C.beq, 'pair'))
_a(C.cmp_wi('w9', PAIR_Q[-1]))
_a(C.to(C.bne, 'out'))                                     # other quests (Eye 205 ...): stock
_a.label('pair')
_a(chk(C.ldr_w('w9', 'x19', 0xC8), 'ldr w9, [x19, #0xc8]'))   # me = owner
_a(chk(cmn_wi('w9', 1), 'cmn w9, #1'))
_a(C.to(C.beq, 'out'))
_a(chk(C.ldr_w('w10', 'x20', 0), 'ldr w10, [x20]'))        # partner key
_a(C.cmp_wi('w10', 9))
_a(C.to(C.beq, 'out'))                                     # key 9: no player (stock decode gives -1)
_a(C.movz_w('w11', 10))
_a(chk(udiv_w('w12', 'w10', 'w11'), 'udiv w12, w10, w11'))   # key / 10
_a(C.movz_w('w13', 10000))
_a(chk(udiv_w('w14', 'w12', 'w13'), 'udiv w14, w12, w13'))
_a(chk(msub_w('w12', 'w14', 'w13', 'w12'), 'msub w12, w14, w13, w12'))   # id = key / 10 % 10000
_a(C.movz_w('w13', 0x86A0))
_a(chk(C.movk_w('w13', 1, 1), 'movk w13, #1, lsl #16'))   # 100000
_a(chk(udiv_w('w14', 'w10', 'w13'), 'udiv w14, w10, w13'))   # key / 100000
_a(chk(udiv_w('w15', 'w14', 'w11'), 'udiv w15, w14, w11'))
_a(chk(msub_w('w15', 'w15', 'w11', 'w14'), 'msub w15, w15, w11, w14'))   # (key / 100000) % 10
_a(C.to(C.cbz_w, 'w15', 'pid'))                            # stock 0x1197A7C: divisible by 10 -> raw id
_a(C.cmp_wi('w12', 0x27))
_a(C.movz_w('w15', 0x27))
_a(chk(csel_w('w12', 'w12', 'w15', 'lt'), 'csel w12, w12, w15, lt'))
_a(C.movz_w('w15', 0x9680))
_a(chk(C.movk_w('w15', 0x98, 1), 'movk w15, #0x98, lsl #16'))
_a(chk(orr_w('w12', 'w12', 'w15'), 'orr w12, w12, w15'))  # min(id, 0x27) | 10000000
_a.label('pid')                                            # w9 = me, w12 = partner
_a(lambda pc, L: C.adrp(pc, 'x11', TAB))
_a(C.add_xi('x11', 'x11', C.lo12(TAB)))
_a(C.add_xi('x13', 'x11', 0x80))
_a(C.movz_w('w14', 0))                                     # known = 0
_a.label('loop')
_a(chk(ldp_w('w15', 'w16', 'x11', 0), 'ldp w15, w16, [x11]'))      # valid, hunter
_a(C.to(C.cbz_w, 'w15', 'next'))
_a(chk(ldp_w('w15', 'w17', 'x11', 8), 'ldp w15, w17, [x11, #8]'))  # t1, t2
_a(C.cmp_wr('w16', 'w9'))
_a(C.to(C.bne, 'hp'))
_a(C.cmp_wr('w15', 'w12'))
_a(C.to(C.beq, 'acc'))                                     # my row names the partner
_a(C.cmp_wr('w17', 'w12'))
_a(C.to(C.beq, 'acc'))
_a(C.movz_w('w14', 1))
_a.label('hp')
_a(C.cmp_wr('w16', 'w12'))
_a(C.to(C.bne, 'tt'))
_a(C.cmp_wr('w15', 'w9'))
_a(C.to(C.beq, 'acc'))                                     # the partner's row names me
_a(C.cmp_wr('w17', 'w9'))
_a(C.to(C.beq, 'acc'))
_a(C.movz_w('w14', 1))
_a.label('tt')
for _r, _lab in (('w9', 'kn'), ('w12', 'kn')):
    _a(C.cmp_wr('w15', _r))
    _a(C.to(C.beq, _lab))
    _a(C.cmp_wr('w17', _r))
    _a(C.to(C.beq, _lab))
_a(C.to(C.b, 'next'))
_a.label('kn')
_a(C.movz_w('w14', 1))                                     # me or partner is someone's target
_a.label('next')
_a(C.add_xi('x11', 'x11', 0x10))
_a(C.cmp_xr('x11', 'x13'))
_a(C.to(C.bne, 'loop'))
_a(C.cmp_wi('w14', 0))
_a(chk(cset_w('w0', 'eq'), 'cset w0, eq'))                 # nobody known: stock (1); known, no pair: 0
_a(C.to(C.b, 'out'))
_a.label('acc')
_a(C.movz_w('w0', 1))
_a.label('out')
_a(C.ldp_x('x19', 'x20', 'sp', 0x10))
_a(C.ldp_post('x29', 'x30', 'sp', 0x20))
_a(C.RET)
assert len(_a.words()) * 4 <= 0x160, len(_a.words())
_pair = _g.cave('SIGIL3_PAIR_MATCH', _m, _a)
# self-check of the decode against the stock arithmetic for a spread of keys
for _k in list(range(10, 2000, 7)) + [100000 * j + 10 * i + s for j in (1, 3, 10, 20, 41) for i in (0, 5, 39, 77)
                                       for s in (0, 1, 2)] + [4294967290]:
    _id = (_k // 10) % 10000
    _r = _k // 100000
    _stock = _id if ((_r * 0xCCCCCCCD & 0xFFFFFFFF) >> 1 | ((_r * 0xCCCCCCCD & 1) << 31)) < 0x1999999A else \
        (min(_id, 0x27) | 10000000)
    _mine = _id if _r % 10 == 0 else (min(_id, 0x27) | 10000000)
    assert _stock == _mine, _k

# ---- FILL (apply, every entry)
_f = _g.alloc('SIGIL3_PAIR_FILL', 'FAR_CODE', 0xA0, 'S2: apply own entry -> designated-target table row')
_a = C.Asm(_f)
_a(C.cmp_xi('x28', 0x14))
_a(C.to(C.bne, 'done'))                                    # only the own entry (last, 0x14 bytes left)
_a(chk(C.ldur_w('w8', 'x19', -0xC), 'ldur w8, [x19, #-0xc]'))     # hunter = entry +0
_a(chk(cmn_wi('w8', 1), 'cmn w8, #1'))
_a(C.to(C.beq, 'done'))
_a(chk(C.ldr_w('w9', 'x19', 0), 'ldr w9, [x19]'))          # t1 = entry +0xC
_a(chk(cmn_wi('w9', 1), 'cmn w9, #1'))
_a(C.to(C.bne, 'ok'))
_a(chk(C.ldr_w('w9', 'x19', 4), 'ldr w9, [x19, #4]'))      # t2 = entry +0x10
_a(chk(cmn_wi('w9', 1), 'cmn w9, #1'))
_a(C.to(C.beq, 'done'))                                    # no target (Eye ...): no row
_a.label('ok')
_a(lambda pc, L: C.adrp(pc, 'x16', TAB))
_a(C.add_xi('x16', 'x16', C.lo12(TAB)))
_a(C.add_xi('x17', 'x16', 0x80))
_a.label('find')
_a(C.ldr_w('w9', 'x16', 0))
_a(C.to(C.cbz_w, 'w9', 'fn'))
_a(C.ldr_w('w9', 'x16', 4))
_a(C.cmp_wr('w9', 'w8'))
_a(C.to(C.beq, 'write'))                                   # the hunter's row: overwrite
_a.label('fn')
_a(C.add_xi('x16', 'x16', 0x10))
_a(C.cmp_xr('x16', 'x17'))
_a(C.to(C.bne, 'find'))
_a(C.sub_xi('x16', 'x16', 0x80))
_a.label('free')
_a(C.ldr_w('w9', 'x16', 0))
_a(C.to(C.cbz_w, 'w9', 'write'))                           # first free row
_a(C.add_xi('x16', 'x16', 0x10))
_a(C.cmp_xr('x16', 'x17'))
_a(C.to(C.bne, 'free'))
_a(C.to(C.b, 'done'))                                      # table full (8 rows): no row
_a.label('write')
_a(C.str_w('w8', 'x16', 4))
_a(C.ldr_w('w9', 'x19', 0))
_a(C.str_w('w9', 'x16', 8))
_a(C.ldr_w('w9', 'x19', 4))
_a(C.str_w('w9', 'x16', 0xC))
_a(C.movz_w('w9', 1))
_a(C.str_w('w9', 'x16', 0))                                # valid last
_a.label('done')
_a(chk(word(0x1195CB0), 'ldur w8, [x19, #-0xc]'))          # replaced word
_a.many(lambda pc, L: C.far_return(pc, 0x1195CB4))
assert len(_a.words()) * 4 <= 0xA0, len(_a.words())
_pair += _g.cave('SIGIL3_PAIR_FILL', _f, _a)

# ---- RESET (MatchPreprocess)
_r0 = _g.alloc('SIGIL3_PAIR_RESET', 'FAR_CODE', 0x40, 'S2: zero the target table, then MatchPreprocess 0x1181D80')
_a = C.Asm(_r0)
_a(lambda pc, L: C.adrp(pc, 'x16', TAB))
_a(C.add_xi('x16', 'x16', C.lo12(TAB)))
for _o in range(0, 0x80, 0x10):
    _a(C.stp_x('xzr', 'xzr', 'x16', _o))
_a.many(lambda pc, L: C.far_jump(pc, 0x1181D80))            # x30 = 0x1149718 from the site's bl
assert len(_a.words()) * 4 <= 0x40, len(_a.words())
_pair += _g.cave('SIGIL3_PAIR_RESET', _r0, _a)

_hooks = []
for _site, _txt, _tgt, _lnk, _why in (
        (0x1149714, 'bl #0x1181d80', _r0, True, 'bl site (x16/x17 corruptible across the call; none in the caller '
                                                '0x1149260..0x1149A74 or in 0x1181D80..0x1181E98, checked)'),
        (0x1195CB0, 'ldur w8, [x19, #-0xc]', _f, False, 'x16/x17 never appear in the apply 0x1195C40..0x1195DFC '
                                                         '(checked); the APPLY2 cave writes them before reading'),
        (0x1197C70, 'b #0x11979c0', _m, False, 'function entered only by blr through vtable 0x56F8F08+0x10 '
                                               '(census): x16/x17 free at a function entry; 0x1197C6C does not use them')):
    _r = _g.far_hook(_site, _txt, _tgt, scratch='x16', link=_lnk, why=_why)
    _pair += _r[:-1]
    _hooks.append(_r[-1])
groups['SIGIL3_PAIR'] = _pair + _hooks                     # caves, trampolines, then the 3 hooks (match last)
not_shipped(groups['SIGIL3_PAIR'], 'SIGIL3_PAIR')
listing.extend(_g.listing)
_n_listed = len(_g.listing)

# ================================================================ SIGIL3_FRIEND (sigil10_notes.md)
# Old Friend (quest 30, type 5, ONE logic class: GOT 0x59E3490 -> vt 0x56F8A28, server mask 1 / client 0x5E).
# Alliance formed: 0x10AB800 (every game, every alliance; HUD + team flags) -> 0x10ABFD4 bl 0x1182880(SQM, &a, &b)
# -> 0x117ABE4(module, &other) for every module of a and of b -> (flags vt+0x38 = 8: bit 6 clear) 0x117AD18
# 0x117ADB0(module, other chr): team bit not yet in module+0x38, vt+0x10 = 0, then 0x1199D00(cond +0x90, &no, 0):
# the ally's chr handle must be in the class-B list (cond+0x10, count +0x58, +2 != 0, +3 != 0xFF) -> writer
# 0x117CAAC (owner +0xA8 && !+0xA9, client bit 1 of 0x5E) -> event 1 {team} -> 0x11793D8 mask |= 1 << team [V].
# Everything but the list is satisfied in LAN; the list is filled only by the one-frame first-fit pairing
# (0x1180440, module+0x79) whose rule (0x11979C0) is "partner's slot quest == +0xCC" [V]. The same list gates the
# completion (vt+0x68 0x1192474 -> vt+0x138 0x11927D4 membership) and the only Virtue, row 301 type 13 (0x117B300,
# struggle end 0x1021BE0: every listed chr that is among the participants) [V].
# Change: 0x117AD18 `bl 0x117adb0` -> bl trampoline -> cave (late pairing at the alliance, LAN, Old Friend only):
#   if OFF == 0 and logic vt == 0x56F8A28 and cond +0x90 is class B (vt 0x56F8E88) and its list is EMPTY and
#   +0xB8 == 0 and the ally's pgd slot 0 (pgd+0x46E0) == +0xCC and ally != +0xC8 (self) and the ally has an SQM
#   entry whose slot-0 module is Old Friend class B wanting this module's quest (+0x4C), and that list is empty or
#   holds my chr handle: stock add 0x1197C80(my cond, &ally slot-0 key = ally logic+0x18) and, if the ally's list
#   was empty, 0x1197C80(ally cond, &my key = my logic+0x18). Always then the stock 0x117ADB0(module, chr).
#   Offline / other classes / any test failing -> exactly the stock call.
VT_FRIEND = 0x56F8A28
VT_COND_B = 0x56F8E88
SQM_G = 0x5B3CE18
_qd =lambda a: struct.unpack_from('<Q', DATA, a - DATA_B)[0]
assert _qd(0x59E3490) + 0x10 == VT_FRIEND
assert _qd(0x59E34D8) + 0x10 == VT_COND_B
assert _qd(VT_FRIEND + 0x38) == 0x11933A4 and _qd(VT_FRIEND + 0x10) == 0x118D168      # flags 8, "skip" = 0
assert _qd(VT_FRIEND + 0x68) == 0x1192474 and _qd(VT_FRIEND + 0x138) == 0x11927D4
assert _qd(VT_COND_B + 0x60) == 0x1197C80                                               # class-B add
# the only factory case that builds the Old Friend logic (type 5) and its class-B condition
for a, t in ((0x11897C0, 'ldr x8, [x8, #0x490]'), (0x11897C8, 'add x8, x8, #0x10'), (0x11897D0, 'stp x8, x9, [x22]'),
             (0x1189F60, 'b.ne #0x118a2c4'), (0x118A2DC, 'cbz x8, #0x118a5d4'), (0x118A5E4, 'ldr x10, [x10, #0x4d8]'),
             (0x118A5F0, 'add x8, x10, #0x10'), (0x118A5F8, 'stp w11, w9, [x22, #0xc8]'), (0x118A694, 'str x22, [x28, #0x90]'),
             (0x11933A4, 'mov w9, #8'), (0x118D168, 'mov w0, wzr'),
             # hook site + the stock partner step
             (0x117AC44, 'tbnz w8, #6, #0x117ad1c'), (0x117AD10, 'mov x0, x19'), (0x117AD14, 'mov x1, x21'),
             (0x117AD1C, 'ldr x8, [x19, #0x20]'), (0x117ADB0, 'cbz x1, #0x117af08'), (0x117ADEC, 'ldr x9, [x20, #0x38]'),
             (0x117AE74, 'ldr x0, [x21, #0x90]'), (0x117AE84, 'bl #0x1199d00'), (0x117AE94, 'ldr x20, [x8, #0x28]'),
             # membership 0x1199D00 and the add 0x1197C80 (same handle field chr+0x20 -> +0x78, same list)
             (0x1199DF0, 'ldr x10, [x21, #0x58]'), (0x1199E00, 'ldrh w9, [x8, #0x78]'), (0x1199E04, 'add x8, x21, #0x10'),
             (0x1197C80, 'pacibsp'), (0x1197CAC, 'ldr w9, [x1]'), (0x1197DE8, 'ldrb w8, [x19, #0xb8]'),
             (0x1197E44, 'ldr x11, [x19, #0x58]'), (0x1197E5C, 'ldr x8, [x21, #0x20]'), (0x1197E64, 'ldrh w9, [x8, #0x78]'),
             (0x1197E68, 'add x8, x19, #0x10'), (0x1197EB4, 'str x11, [x19, #0x58]'),
             # module key = logic+0x18 (0x118C718 reads [x0+0x10] with x0 = logic+8, as vt+0x68 does)
             (0x118C740, 'ldr w9, [x8, #0x10]'), (0x11924A4, 'add x0, x19, #8'), (0x11924A8, 'bl #0x118c718'),
             # SQM entry walk of 0x1182880 (key +0, slot-0 module +8, stride 0x20) and the SQM global
             (0x10ABD3C, 'adrp x21, #0x5b3c000'), (0x10ABD40, 'add x21, x21, #0xe18'), (0x1182898, 'ldp x22, x8, [x0, #8]'),
             (0x11828C0, 'ldr w10, [x23]'), (0x11828CC, 'add x23, x23, #0x20'), (0x11828E8, 'ldr x0, [x23, #8]'),
             (0x1197AD4, 'mov w9, #0x46e0'), (0x1197B3C, 'ldr w9, [x9]')):
    ctx(a, t)
# census: 0x117ADB0 callers (alliance hook + lock-on step 0x11835C0) and 0x1182880 (only the alliance apply)
_fc = {0x117ADB0: [], 0x1182880: [], 0x1197C80: []}
for _i in range(0, 0x492AD90, 4):
    _w = word(_i)
    if (_w >> 26) in (0x25, 0x05):
        _o = _w & 0x3FFFFFF
        _t = _i + 4 * (_o - (1 << 26) if _o & (1 << 25) else _o)
        if _t in _fc:
            _fc[_t].append(_i)
assert _fc == {0x117ADB0: [0x117AD18, 0x11838B4, 0x1183924, 0x1183994], 0x1182880: [0x10ABFD4],
               0x1197C80: [0x1197F34]}, _fc                     # add: only the listener thunk branches to it
assert _qd(VT_COND_B + 0x60) == 0x1197C80 and _qd(0x56F8F08 + 0x18) == 0x1197F30      # add via vt / listener thunk
ctx(0x1197F30, 'sub x0, x0, #0xc0')
# x16/x17 at the bl site: caller-saved; 0x117ABE4 after the call (0x117AD1C..0x117AD84) never reads them
for _x in range(0x117AD1C, 0x117AD88, 4):
    assert not re.search(r'\b[xw]1[67]\b', dis1(_x, word(_x))), 'x16/x17 at %x' % _x
_fr = _g.alloc('SIGIL3_FRIEND', 'FAR_CODE', 0x200, 'Old Friend: late pairing with the designated ally at the '
               'alliance, then the stock partner step 0x117ADB0')
# review13 B1 / S1: never add without the stock class-B match. The listener thunk 0x1197C6C (vt 0x56F8F08+0x10,
# `sub x0, x0, #0xc0 ; b 0x11979c0`) is exactly what the pairing 0x1180440 calls before its add (vt+0x18 0x1197F30),
# so it carries the Bloodbound rule (rule byte 0x5B65C70 == 2: refuse my current ally in AM, 0x1197B54..0x1197C28)
# and, when SIGIL3_PAIR is applied, its designated-target wrapper at 0x1197C70. The match reads only the u32 key at
# [x1] (0x1197AD0) and returns 0/1. Helper (own claim: the main cave is full) entered with bl from the main cave at
# `both`/`mine`; it uses the main cave's callee-saved registers (x21 my cond, x23 ally cond, x24 = 0 -> both ways)
# and keys at main sp+0x40 (mine) / +0x48 (ally) = helper sp+0x50 / +0x58. Both matches pass before ANY add.
ctx(0x1197C6C, 'sub x0, x0, #0xc0')
ctx(0x1197C70, 'b #0x11979c0')
ctx(0x11979D8, 'ldr w8, [x1]')
ctx(0x1197AD0, 'ldr w10, [x20]')
ctx(0x1197B54, 'ldrb w9, [x9]')
ctx(0x1197B58, 'cmp w9, #2')
ctx(0x1197C14, 'mov w0, #1')
ctx(0x1197C28, 'cset w0, ne')
assert _qd(0x56F8F08 + 0x10) == 0x1197C6C, hex(_qd(0x56F8F08 + 0x10))     # listener vt: match thunk
_frm = _g.alloc('SIGIL3_FRIEND_MATCH', 'FAR_CODE', 0x80, 'Old Friend: stock class-B match gate (thunk 0x1197C6C) '
                'before the late-pairing adds (review13 B1/S1)')
_a = C.Asm(_frm)
_a(C.stp_pre('x29', 'x30', 'sp', -0x10))
_a(C.mov_sp('x29', 'sp'))
_a(C.add_xi('x0', 'x21', 0xC0))
_a(C.add_xi('x1', 'sp', 0x58))                             # ally key (main sp+0x48)
_a.many(lambda pc, L: C.far_call(pc, 0x1197C6C))           # stock match: my cond vs ally
_a(C.to(C.tbz, 'w0', 0, 'out'))                            # refused (Bloodbound ally, PAIR, quest): no add
_a(C.to(C.cbnz_x, 'x24', 'addmine'))                       # ally already lists me: only my side
_a(C.add_xi('x0', 'x23', 0xC0))
_a(C.add_xi('x1', 'sp', 0x50))                             # my key (main sp+0x40)
_a.many(lambda pc, L: C.far_call(pc, 0x1197C6C))           # stock match: ally cond vs me
_a(C.to(C.tbz, 'w0', 0, 'out'))
_a(C.mov_x('x0', 'x23'))
_a(C.add_xi('x1', 'sp', 0x50))
_a.many(lambda pc, L: C.far_call(pc, 0x1197C80))           # ally cond += me (stock add)
_a.label('addmine')
_a(C.mov_x('x0', 'x21'))
_a(C.add_xi('x1', 'sp', 0x58))
_a.many(lambda pc, L: C.far_call(pc, 0x1197C80))           # my cond += ally (stock add)
_a.label('out')
_a(C.ldp_post('x29', 'x30', 'sp', 0x10))
_a(C.RET)
assert len(_a.words()) * 4 <= 0x80, len(_a.words())
_friend_m = _g.cave('SIGIL3_FRIEND_MATCH', _frm, _a)
_a = C.Asm(_fr)
_a(C.stp_pre('x29', 'x30', 'sp', -0x50))
_a(C.stp_x('x19', 'x20', 'sp', 0x10))
_a(C.stp_x('x21', 'x22', 'sp', 0x20))
_a(C.stp_x('x23', 'x24', 'sp', 0x30))
_a(C.mov_sp('x29', 'sp'))
_a(C.mov_x('x19', 'x0'))                                   # module
_a(C.mov_x('x20', 'x1'))                                   # ally chr (may be null: 0x117ADB0 returns)
_a(C.to(C.cbz_x, 'x20', 'stock'))
_a(lambda pc, L: C.adrp(pc, 'x8', OFFL))
_a(C.ldr_x('x8', 'x8', C.lo12(OFFL)))
_a(chk(C.ldrb('w8', 'x8', 0xBDA), 'ldrb w8, [x8, #0xbda]'))
_a(C.to(C.cbnz_w, 'w8', 'stock'))                          # offline: stock
_a(C.ldr_x('x8', 'x19', 0x20))                             # active holder
_a(C.to(C.cbz_x, 'x8', 'stock'))
_a(C.ldr_x('x9', 'x8', 0x10))                              # logic
_a(C.to(C.cbz_x, 'x9', 'stock'))
_a(C.ldr_x('x10', 'x9', 0))
_a(lambda pc, L: C.adrp(pc, 'x11', VT_FRIEND))
_a(C.add_xi('x11', 'x11', C.lo12(VT_FRIEND)))
_a(C.cmp_xr('x10', 'x11'))
_a(C.to(C.bne, 'stock'))                                   # not Old Friend: stock
_a(C.ldr_w('w10', 'x9', 0x18))                             # my module key
_a(C.str_w('w10', 'sp', 0x40))
_a(C.ldr_x('x10', 'x8', 0x18))                             # participants root
_a(C.to(C.cbz_x, 'x10', 'stock'))
_a(C.ldr_x('x21', 'x10', 0x90))                            # my condition
_a(C.to(C.cbz_x, 'x21', 'stock'))
_a(C.ldr_x('x10', 'x21', 0))
_a(lambda pc, L: C.adrp(pc, 'x11', VT_COND_B))
_a(C.add_xi('x11', 'x11', C.lo12(VT_COND_B)))
_a(C.cmp_xr('x10', 'x11'))
_a(C.to(C.bne, 'stock'))                                   # class C (slot 1) etc.: stock
_a(C.ldr_x('x10', 'x21', 0x58))
_a(C.to(C.cbnz_x, 'x10', 'stock'))                         # my list already holds a partner: stock only
_a(C.ldrb('w10', 'x21', 0xB8))
_a(C.to(C.cbnz_w, 'w10', 'stock'))                         # the add would be skipped
_a(C.ldr_x('x10', 'x20', 0x20))
_a(C.ldr_x('x10', 'x10', 0x1D0))                           # ally pgd
_a(C.to(C.cbz_x, 'x10', 'stock'))
_a(chk(C.add_xi('x12', 'x10', 4, lsl12=True), 'add x12, x10, #4, lsl #12'))
_a(chk(C.ldr_w('w11', 'x12', 0x6E0), 'ldr w11, [x12, #0x6e0]'))   # ally pgd+0x46E0 (slot 0 quest)
_a(chk(C.ldr_w('w12', 'x21', 0xCC), 'ldr w12, [x21, #0xcc]'))
_a(C.cmp_wr('w11', 'w12'))
_a(C.to(C.bne, 'stock'))                                   # ally does not hold the wanted quest
_a(C.ldr_w('w22', 'x10', 0xD0))                            # ally player no
_a(chk(cmn_wi('w22', 1), 'cmn w22, #1'))
_a(C.to(C.beq, 'stock'))
_a(chk(C.ldr_w('w12', 'x21', 0xC8), 'ldr w12, [x21, #0xc8]'))   # me (class-B owner)
_a(C.cmp_wr('w22', 'w12'))
_a(C.to(C.beq, 'stock'))
_a(lambda pc, L: C.adrp(pc, 'x8', SQM_G))
_a(C.ldr_x('x8', 'x8', C.lo12(SQM_G)))
_a(C.to(C.cbz_x, 'x8', 'stock'))
_a(C.ldp_x('x9', 'x10', 'x8', 8))                          # SQM entries [begin, end)
_a.label('eloop')
_a(C.cmp_xr('x9', 'x10'))
_a(C.to(C.bhs, 'remote'))                                  # ally has no SQM entry on this game (run20): my side only
_a(C.ldr_w('w11', 'x9', 0))
_a(C.cmp_wr('w11', 'w22'))
_a(C.to(C.beq, 'efound'))
_a(C.add_xi('x9', 'x9', 0x20))
_a(C.to(C.b, 'eloop'))
_a.label('efound')
_a(C.ldr_x('x9', 'x9', 8))                                 # ally slot-0 module
_a(C.to(C.cbz_x, 'x9', 'stock'))
_a(C.ldr_x('x9', 'x9', 0x20))                              # its active holder
_a(C.to(C.cbz_x, 'x9', 'stock'))
_a(C.ldr_x('x10', 'x9', 0x10))                             # its logic
_a(C.to(C.cbz_x, 'x10', 'stock'))
_a(C.ldr_x('x11', 'x10', 0))
_a(lambda pc, L: C.adrp(pc, 'x12', VT_FRIEND))
_a(C.add_xi('x12', 'x12', C.lo12(VT_FRIEND)))
_a(C.cmp_xr('x11', 'x12'))
_a(C.to(C.bne, 'stock'))                                   # ally's slot 0 is not Old Friend: stock
_a(C.ldr_w('w11', 'x10', 0x18))                            # ally slot-0 key
_a(C.str_w('w11', 'sp', 0x48))
_a(C.ldr_x('x10', 'x9', 0x18))
_a(C.to(C.cbz_x, 'x10', 'stock'))
_a(C.ldr_x('x23', 'x10', 0x90))                            # ally condition
_a(C.to(C.cbz_x, 'x23', 'stock'))
_a(C.ldr_x('x10', 'x23', 0))
_a(lambda pc, L: C.adrp(pc, 'x11', VT_COND_B))
_a(C.add_xi('x11', 'x11', C.lo12(VT_COND_B)))
_a(C.cmp_xr('x10', 'x11'))
_a(C.to(C.bne, 'stock'))
_a(chk(C.ldr_w('w10', 'x23', 0xCC), 'ldr w10, [x23, #0xcc]'))
_a(chk(C.ldr_w('w11', 'x19', 0x4C), 'ldr w11, [x19, #0x4c]'))   # my module quest
_a(C.cmp_wr('w10', 'w11'))
_a(C.to(C.bne, 'stock'))                                   # ally does not want my quest: stock
_a(C.ldr_x('x24', 'x23', 0x58))
_a(C.to(C.cbz_x, 'x24', 'both'))                           # ally unpaired too: pair both ways
# ally list not empty: accept only if it already holds my chr handle (paired with me on its side)
_a(C.ldr_x('x0', 'x19', 0x20))
_a(C.ldr_x('x0', 'x0', 0x10))
_a(C.add_xi('x0', 'x0', 8))
_a.many(lambda pc, L: C.far_call(pc, 0x118C718))           # my chr (as vt+0x68 does)
_a(C.to(C.cbz_x, 'x0', 'stock'))
_a(C.ldr_x('x8', 'x0', 0x20))
_a(C.ldrh('w12', 'x8', 0x78))                              # my handle
_a(C.ldr_x('x24', 'x23', 0x58))
_a(C.add_xi('x11', 'x23', 0x10))
_a.label('cloop')
_a(C.ldrh('w13', 'x11', 0))
_a(C.cmp_wr('w13', 'w12'))
_a(C.to(C.beq, 'mine'))                                    # ally side already lists me: only my side is missing
_a(C.add_xi('x11', 'x11', 4))
_a(C.sub_xi('x24', 'x24', 1))
_a(C.to(C.cbnz_x, 'x24', 'cloop'))
_a(C.to(C.b, 'stock'))                                     # ally paired with someone else: not the designated pair
# run20: in LAN each game's SQM holds ONLY the local player's entry (5b "key MISSING" for the peer, made once at
# MatchPreprocess 0x1181D80), so the old walk always ended here -> stock. 0x1182880 then visits only the local
# player's 3 modules (key == a, then key == b; 0x11828C0 / 0x1182928) [V]. Each game pairs its OWN module only:
# ally key = ally no * 10 + slot 0 (sigil4: key = id*10 + slot; raw id when key/100000 % 10 == 0, 0x1197D0C), the
# add needs the ally chr (0x17F1940 mode 0x407, 0x1197D78), not its module; the match reads the ally pgd slot 0 via
# mediator 0xCEA240 and keeps the Bloodbound refusal. Quest 30 is mutual (counterpart 30, SubQuestRoleParam 30 +0),
# so "ally holds 30 in slot 0" is the designation; the peer game pairs the mirror for its own module.
_a.label('remote')
_a(chk(C.cmp_wi('w22', 0xFFF), 'cmp w22, #0xfff'))
_a(C.to(C.bhi, 'stock')) if hasattr(C, 'bhi') else _a(lambda pc, L: C.bcond(pc, 'hi', L['stock']))   # no >= 4096
_a(C.movz_w('w11', 10))
_a(chk(0x1B007C00 | (C.R('w11') << 16) | (C.R('w22') << 5) | C.R('w11'), 'mul w11, w22, w11'))
_a(C.str_w('w11', 'sp', 0x48))                             # ally slot-0 key
_a(C.movz_x('x24', 1))                                     # helper: my side only (match + add)
_a(C.to(C.b, 'mine'))
_a.label('both')                                          # x24 = 0: pair both ways
_a.label('mine')                                           # x24 != 0: ally already lists me, only my side
_a(lambda pc, L: C.bl(pc, _frm))                           # review13 B1/S1: stock match gate, then the adds
_a.label('stock')
_a(C.mov_x('x0', 'x19'))
_a(C.mov_x('x1', 'x20'))
_a.many(lambda pc, L: C.far_call(pc, 0x117ADB0))           # stock partner step (owner-gated event 1)
_a(C.ldp_x('x23', 'x24', 'sp', 0x30))
_a(C.ldp_x('x21', 'x22', 'sp', 0x20))
_a(C.ldp_x('x19', 'x20', 'sp', 0x10))
_a(C.ldp_post('x29', 'x30', 'sp', 0x50))
_a(C.RET)
assert len(_a.words()) * 4 <= 0x200, len(_a.words())
_friend = _friend_m + _g.cave('SIGIL3_FRIEND', _fr, _a)   # match helper, main cave, trampoline, hook LAST
_friend += _g.far_hook(0x117AD18, 'bl #0x117adb0', _fr, scratch='x16', link=True,
                       why='bl site of a normal function (0x117ADB0): x16/x17 caller-saved, 0x117ABE4 never reads '
                           'them after the call (0x117AD1C..0x117AD84 checked); the cave returns with ret',
                       note='alliance partner step -> SIGIL3_FRIEND (late Old Friend pairing, then 0x117ADB0)')
groups['SIGIL3_FRIEND'] = _friend                          # cave, trampoline, hook LAST
not_shipped(groups['SIGIL3_FRIEND'], 'SIGIL3_FRIEND')
listing.append('=== SIGIL3_FRIEND (Old Friend: alliance -> late class-B pairing with the designated ally)')
listing.extend(_g.listing[_n_listed:])

# ---------------------------------------------------------------- event masks of the quest logic classes [V data]
q = lambda a: struct.unpack_from('<Q', DATA, a - DATA_B)[0]
listing.append('=== quest logic classes: vt+0x40 -> writer+0x98 (server mask), vt+0x48 -> writer+0xA0 (client mask)')
for got in range(0x59E3408, 0x59E3498, 8):
    vt = q(got) + 0x10
    out = []
    for s in (0x40, 0x48):
        f = q(vt + s)
        ins = []
        for x in md.disasm(TXT[f:f + 12], f):
            ins.append(x)
            if x.mnemonic in ('ret', 'b', 'br'):
                break
        m = [x.op_str for x in ins if x.mnemonic == 'mov' and x.op_str.startswith('w9')]
        out.append(m[0].split('#')[1] if m else ('0' if ins[0].mnemonic == 'str' else 'dyn %x' % f))
    listing.append('  GOT %x vt %x: server %s client %s' % (got, vt, out[0], out[1]))

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    if g.endswith('_LIVE'):
        continue          # live twin of a bake group: same addresses on purpose
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen[a + i])
            seen[a + i] = g
print('\n'.join(listing))

ORDER = ['SIGIL3_P2', 'SIGIL3_LISTEN', 'SIGIL3_STEP', 'SIGIL3_STEP_T', 'SIGIL3_STEP_T_LIVE', 'SIGIL3_PROGRESS', 'SIGIL3_COMPLETE', 'SIGIL3_ACTIVATE', 'SIGIL3_STATE',
         'SIGIL3_REWARD', 'SIGIL3_HERETIC_RECV', 'SIGIL3_HERETIC_ASSIGN', 'SIGIL3_HERETIC_SELECT', 'SIGIL3_PAIR',
         'SIGIL3_FRIEND']
notes = {
    'SIGIL3_FRIEND': 'sigil10_notes.md, all games, NEW (stock hook word, no _LIVE variant; cave + trampoline first, '
                     'hook 0x117AD18 last): Old Friend late class-B pairing with the designated ally when the '
                     'alliance forms (each add only after the stock match thunk 0x1197C6C says 1: Bloodbound / '
                     'SIGIL3_PAIR rules kept, review13 B1/S1; helper cave SIGIL3_FRIEND_MATCH), then the stock '
                     'owner-gated partner step 0x117ADB0; offline = stock',
    'SIGIL3_PAIR': 'review10 S2, all games, NEW (no built-in word): designated-target table (FAR_DATA, filled by '
                   'the apply 0x1195CB0, zeroed at MatchPreprocess 0x1149714) + class-B match wrapper 0x1197C70: '
                   'quests 10/30/240/250 pair only bearer <-> its record target in LAN (sigil8_notes.md)',
    'SIGIL3_STEP': 'BUILT IN (cave + trampoline only; its 0x117B770 hook word moved to SIGIL3_STEP_T): old type-blind '
                   'step cave, unreferenced once SIGIL3_STEP_T is baked',
    'SIGIL3_STEP_T': 'review10 S1, BAKE form (hook orig = stock word; lead: update_dusk_records.py): new cave + '
                     'trampoline, 0x117B770 -> step event 1 only for Sworn Enemy logic (vt 0x56F7408 / 0x56F7858)',
    'SIGIL3_STEP_T_LIVE': 'review10 S1, LIVE form for a running built-in game (hook orig = built-in bl 0x563EEF0); '
                          'never bake this one',
    'SIGIL3_LISTEN': 'all games, BEFORE match load (factory + 0x1194730 read it when the modules are built): '
                     'class B/C target listener root+0xA0 wired in LAN as offline -> 0x1180440 pairs targets [V]',
    'SIGIL3_P2': 'all games, before MatchPreprocess: producer without a mission row (row never read) [V]',
    'SIGIL3_ACTIVATE': 'all games, before PreLoading: perfume gives; INERT until whitelist W1 (sigil3_notes 4)',
    'SIGIL3_PROGRESS': 'all games, with SIGIL_NC_EVAL; INSTEAD of SIGIL_NC_REPORT: owner-only 0x8B report',
    'SIGIL3_COMPLETE': 'all games: Old Friend alliance step/reward hook (senders are owner-gated) [V]',
    'SIGIL3_STATE': 'review10 B1, all games (receive cave + hook first, sender word last): owner sends module state '
                    '(event 0) in LAN, receivers accept event 0 in LAN only; offline byte-identical (sigil7_notes 1)',
    'SIGIL3_REWARD': 'nothing to flip: award 0x1194E18 has no offline gate; item lots of 0x11950CC are -1 [V]',
    'SIGIL3_HERETIC_RECV': 'H2b, all games, before match load: 0x8B kind 1 (Heretic assign) accepted from any peer',
    'SIGIL3_HERETIC_ASSIGN': 'H2a, all games: 0x1184020 drops the owner test (runs offline / on the host only)',
    'SIGIL3_HERETIC_SELECT': 'H1, all games, LAST: Heretic selector 0x118F260 runs offline or on the host only',
}
out = ['"""Sigil stage C plain-word groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian.',
       'Generated by sigil3_gen.py (original-word + context asserts, capstone check of every new word, collision',
       'checks against patch_manager.cpp records / DUSK_W_ names and the other *_live.py). NOT live-tested.',
       'Notes: sigil3_notes.md. No caves. SIGIL3_PROGRESS needs sigil_nc_live.py SIGIL_NC_EVAL and REPLACES',
       'SIGIL_NC_REPORT (0x119979C nop): never apply both. SIGIL3_ACTIVATE does nothing until the item-grant',
       'whitelist (W1) exists. ORDER = test order."""', '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, nw, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
out.append('NEEDS = {"SIGIL3_PROGRESS": "sigil_nc_live.SIGIL_NC_EVAL", "SIGIL3_LISTEN": "sigil_nc_live.SIGIL_NC_EVAL"}')
out.append('EXCLUSIVE = [("SIGIL3_PROGRESS", "sigil_nc_live.SIGIL_NC_REPORT")]   # never both')
open(os.path.join(HERE, OUT), 'w').write('\n'.join(out) + '\n')
print('%s written' % OUT)
