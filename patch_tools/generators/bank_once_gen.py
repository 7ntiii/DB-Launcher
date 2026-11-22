"""Generator + checker for bank_once_live.py. Static only: reads nso/*.bin, patch_manager.cpp and every
diag/net/*_live.py, writes bank_once_live.py, prints a capstone listing of every new word.
python bank_once_gen.py          (run from diag/net or anywhere)

Groups (design, [V]/[I]: bank_once_notes.md):
  BANK_ONCE_CAVES / BANK_ONCE  the phase bank 0xF88360 adds entry+0x28 only when the pgd's win-point object
                     has wp+0x11 == 0 (own player); copies (wp+0x11 = 1, set by the assist) bank 0.
                     Both bank loops: loop 1 (w2 bit 0 set, entries at state 4, from 0x113FEC0) and loop 2
                     (w2 = 0, every entry, the EndPhase call 0x1145360). Caves are inter-function udf padding
                     in TEXT (0xF87F8C, 0xF88950), no ro padding used.
  PLEDGE_HOST        pledge swear completion (kind 4 send) only on the role-0 game (host), and every game
                     accepts the host's kind 4 even if its own pending signer differs. Replaces the shipped
                     PLEDGE_COMPLETE word 0x109F4D0 (orig of that record = shipped word)."""
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
ROLE = 0x492AFD8     # u32 written by the LAN assist: 0 = this game is the host (lowest player number)

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
# LIVES_RETRY (0x563EC40.., 0x116ABBC) is not built: confirm, we do not use its range anyway
assert not any(a in shipped for a in range(0x563EC40, 0x563EC84)), 'LIVES_RETRY_CAVE range is shipped'
assert not any(a in shipped for a in range(0x116ABBC, 0x116ABC0)), 'LIVES_RETRY hook is shipped'

# ---------------------------------------------------------------- every other helper's records
others = {}   # byte -> file
other_bytes = {}   # byte -> new byte in that file
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == 'bank_once_live.py':
        continue
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)",\s*(True|False)\)',
                         open(f, encoding='utf-8', errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            others.setdefault(a + i, os.path.basename(f))
            other_bytes.setdefault(a + i, int(new[2 * i:2 * i + 2], 16))
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
def ldrb_w(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def cmp_w_imm(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def csel_w_zr_eq(rd, rn): return 0x1A9F0000 | (0 << 12) | (rn << 5) | rd      # csel wd, wn, wzr, eq


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


NOP = 0xD503201F
listing = []
groups = {}


def free(addr):
    for i in range(4):
        assert addr + i not in shipped, 'collides with a shipped record at %x' % addr
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    free(addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def shipped_patch(addr, expect, new, note):
    old = struct.unpack('<I', bytes(shipped[addr + i] for i in range(4)))[0]
    got = dis1(addr, old)
    assert got == expect, 'shipped %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):   # a *_live.py may hold the source of the shipped record itself (same bytes)
        assert addr + i not in others or other_bytes[addr + i] == shipped[addr + i], \
            'shipped word %x differs in %s' % (addr, others[addr + i])
    srcs = sorted({others[addr + i] for i in range(4) if addr + i in others})
    listing.append('  0x%x  %s  ->  %s   (%s, SHIPPED word replaced; source %s)'
                   % (addr, got, dis1(addr, new), note, ', '.join(srcs) or 'patch_manager.cpp'))
    return (addr, hexw(old), hexw(new), True)


def ctx(addr, expect):
    got = dis1(addr, word(addr))
    assert got == expect, 'context %x: %s, expected %s' % (addr, got, expect)


# ---------------------------------------------------------------- text padding caves
def is_uncond(w):
    return ((w & 0xFC000000) == 0x14000000 or w in (0xD65F03C0, 0xD65F0FFF, 0xD65F0BFF)
            or (w & 0xFFFFFC1F) == 0xD61F0000)


def branch_target(o, w):
    if (w & 0x7C000000) == 0x14000000:                       # b / bl
        imm = w & 0x3FFFFFF
        return o + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
    if (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:   # b.cond / cbz / cbnz
        imm = (w >> 5) & 0x7FFFF
        return o + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
    if (w & 0x7E000000) == 0x36000000:                       # tbz / tbnz
        imm = (w >> 5) & 0x3FFF
        return o + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
    if (w & 0x9F000000) == 0x10000000:                       # adr
        imm = ((w >> 5) & 0x7FFFF) << 2 | ((w >> 29) & 3)
        return o + ((imm - (1 << 21)) if imm & (1 << 20) else imm)
    return None


def check_pad(lo, n):
    """n udf #0 words at lo: after an unconditional end, before a function start, unreferenced."""
    assert is_uncond(word(lo - 4)), 'word before pad %x is not an unconditional end' % lo
    for i in range(n):
        assert word(lo + 4 * i) == 0, 'pad word %x not udf #0' % (lo + 4 * i)
        free(lo + 4 * i)
    hi = lo + 4 * n
    while word(hi) == 0:
        hi += 4
    assert word(hi) == 0xD503237F, 'pad %x not followed by a function start (pacibsp)' % lo
    return lo, hi


PADS = [check_pad(0xF87F8C, 4), check_pad(0xF88950, 4)]
hits = []
for o in range(0, len(TXT) - 3, 4):
    t = branch_target(o, struct.unpack_from('<I', TXT, o)[0])
    if t is not None and any(lo <= t < hi for lo, hi in PADS):
        hits.append(o)
for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
    for o in range(0, len(seg) - 7, 8):
        v = struct.unpack_from('<Q', seg, o)[0]
        if any(lo <= v < hi for lo, hi in PADS):
            hits.append(base + o)
assert not hits, 'pad referenced: %r' % [hex(h) for h in hits[:5]]
listing.append('text pads 0xF87F8C..0xF87F9F, 0xF88950..0xF8895F: udf #0 between functions, '
               'no branch/adr/pointer reaches them, not in patch_manager.cpp or any *_live.py')


def cave(name, start, ws):
    out = []
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        a = start + i * 4
        assert any(lo <= a < hi for lo, hi in PADS), 'cave word %x outside the checked pads' % a
        assert word(a) == 0
        free(a)
        listing.append('  0x%x %s' % (a, dis1(a, w)))
        out.append((a, '00000000', hexw(w), True))
    return out


# ================================================================ 1. BANK_ONCE
listing.append('=== BANK_ONCE (bank 0xF88360)')
# facts the design depends on [V]
ctx(0xF870D8, 'ldr w8, [sp]')                 # points pass: [sp] is the counter-value temp ...
ctx(0xF87128, 'str wzr, [sp]')                # ... so [sp] no longer holds the pgd at 0xF87028 (audit cave bad)
ctx(0xF87028, 'str w23, [x19, #0x28]')
ctx(0xF88E00, 'ldrb w8, [x24, #0x11]')        # rank functor: wp+0x11 -> banked only
ctx(0xF88E04, 'cbz w8, #0xf88ed8')
# loop 1 (w2 bit 0 set): x19 = wp (non-null), w27 = entry+0x28, w9 / flags dead until 0xF884C8
ctx(0xF883A0, 'tbz w8, #0, #0xf88520')
ctx(0xF8844C, 'ldr x19, [x8, #0x46d8]')
ctx(0xF88450, 'cbz x19, #0xf883c8')
ctx(0xF88454, 'ldr w27, [x20, #0x28]')
ctx(0xF88458, 'mov x23, xzr')
ctx(0xF8845C, 'add x24, x19, #0xc18')
ctx(0xF884C8, 'mov w9, #0x42c8')
ctx(0xF884E0, 'add w10, w9, w27')
# loop 2 (w2 = 0, EndPhase): x28 = wp (non-null), w19 = entry+0x28, w9 / flags dead until 0xF88654
ctx(0xF885C0, 'ldr x28, [x8, #0x46d8]')
ctx(0xF885C4, 'cbz x28, #0xf88548')
ctx(0xF885C8, 'ldr w19, [x20, #0x28]')
ctx(0xF885CC, 'mov x23, xzr')
ctx(0xF885D0, 'add x24, x28, #0xc18')
ctx(0xF88654, 'ldrh w9, [x2]')
ctx(0xF88658, 'add w10, w9, w19')
# the EndPhase call passes w2 = 0 (loop 2), 0x113FEC0 passes 1 (loop 1)
ctx(0x114535C, 'mov w2, wzr')
ctx(0x1145360, 'bl #0x11454a0')

C1, C2 = 0xF87F8C, 0xF88950
c1 = [ldrb_w(9, 19, 0x11), cmp_w_imm(9, 0), csel_w_zr_eq(27, 27), b(C1 + 12, 0xF88470)]
c2 = [ldrb_w(9, 28, 0x11), cmp_w_imm(9, 0), csel_w_zr_eq(19, 19), b(C2 + 12, 0xF885EC)]
assert dis1(C1, c1[0]) == 'ldrb w9, [x19, #0x11]' and dis1(C1 + 8, c1[2]) == 'csel w27, w27, wzr, eq'
assert dis1(C2, c2[0]) == 'ldrb w9, [x28, #0x11]' and dis1(C2 + 8, c2[2]) == 'csel w19, w19, wzr, eq'
assert dis1(C1 + 4, c1[1]) == 'cmp w9, #0'
groups['BANK_ONCE_CAVES'] = cave('BANK1 (loop 1)', C1, c1) + cave('BANK2 (loop 2)', C2, c2)
groups['BANK_ONCE'] = [
    text_patch(0xF88460, 'b #0xf88470', b(0xF88460, C1), 'loop 1: points := 0 for a copy (wp+0x11 != 0)'),
    text_patch(0xF885D4, 'b #0xf885ec', b(0xF885D4, C2), 'loop 2: points := 0 for a copy (wp+0x11 != 0)'),
]

# ================================================================ 2. PLEDGE_HOST
listing.append('=== PLEDGE_HOST (swear completion 0x109F4C8, kind 4 apply 0x10A2BF8)')
ctx(0x109F4D8, 'b.lt #0x109f4a0')
ctx(0x109F4DC, 'adrp x8, #0x59df000')          # x8 rewritten right after: our x8 value is dead
ctx(0x109FA24, 'ldr x8, [x8, #0x48]')          # original word here; PLEDGE_B8_ALL ships #0x40
assert bytes(shipped[0x109FA24 + i] for i in range(4)).hex().upper() == '082140F9', 'PLEDGE_B8_ALL not shipped'
ctx(0x10A2C00, 'ldr w8, [x19, #0x10]')
ctx(0x10A2C04, 'cmp w8, w23')
ctx(0x10A2C10, 'cmp w21, w23')                 # owner == pno -> ignore (keeps kind 4 idempotent)
ctx(0x10A2C14, 'b.eq #0x10a2e50')
fcc = word(0x109F4D4)
assert dis1(0x109F4D4, fcc) == 'fccmp s0, s9, #8, ne'
fcc_eq = (fcc & ~0xF000) | (0 << 12)
groups['PLEDGE_HOST'] = [
    text_patch(0x109F4C8, 'ldr x8, [x23, #0xc20]', adrp(0x109F4C8, 8, ROLE), 'role word page'),
    text_patch(0x109F4CC, 'ldrb w8, [x8, #0xbda]', ldr_w(8, 8, ROLE & 0xFFF), 'w8 = role (0 = host)'),
    shipped_patch(0x109F4D0, 'cmp w8, #0x100', cmp_w_imm(8, 0), 'PLEDGE_COMPLETE replaced: test role'),
    text_patch(0x109F4D4, 'fccmp s0, s9, #8, ne', fcc_eq, 'complete only when role == 0 and timer done'),
    text_patch(0x10A2C08, 'b.ne #0x10a2e50', NOP, 'kind 4: accept the host decision even if local signer differs'),
]
assert dis1(0x109F4C8, adrp(0x109F4C8, 8, ROLE)) == 'adrp x8, #0x492a000'
assert dis1(0x109F4CC, ldr_w(8, 8, ROLE & 0xFFF)) == 'ldr w8, [x8, #0xfd8]'

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['BANK_ONCE_CAVES', 'BANK_ONCE', 'PLEDGE_HOST']
notes = {
    'BANK_ONCE_CAVES': 'two 4-word caves in text padding (inert until BANK_ONCE)',
    'BANK_ONCE': 'phase bank: copies (wp+0x11 set) bank 0 points; own player unchanged',
    'PLEDGE_HOST': 'pledge kind 4 sent by the host only, applied on every game (needs shipped PLEDGE_B8_ALL; '
                   'replaces shipped PLEDGE_COMPLETE 0x109F4D0)',
}
out = ['"""Bank-once and pledge-host groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian.',
       'Generated by bank_once_gen.py (original-word checks, capstone listing, collision checks against',
       'patch_manager.cpp and every other diag/net/*_live.py). Not live-tested. Notes: bank_once_notes.md.',
       'Cave records have orig "00000000": udf #0 padding between text functions (0xF87F8C, 0xF88950), no ro',
       'padding used (0x563EC40.. LIVES_RETRY range untouched). Apply BANK_ONCE_CAVES before BANK_ONCE.',
       'PLEDGE_HOST 0x109F4D0: orig is the SHIPPED PLEDGE_COMPLETE word (1F010471), apply on top of it.',
       'Apply on EVERY game."""', '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'bank_once_live.py'), 'w').write('\n'.join(out) + '\n')
print('bank_once_live.py written')
