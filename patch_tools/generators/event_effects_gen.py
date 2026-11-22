"""Generator + checker for event_effects_live.py (environment-event effects). Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every other diag/net/*_live.py, writes event_effects_live.py,
prints capstone listings.   python event_effects_gen.py      (notes: event_effects_notes.md)

Only one event needs a patch group: 1140 storm (CSEnvEventShuffleStep, par+0x2D0, started by PrepareSecond
0x114F690 when the env type is 0x0C). Online the step machine waits for server message 0xC8 (kind 1 = times,
kind 0 = the shuffle record, 0xE0 bytes); nobody sends it in LAN, so the machine hangs in step 1.
  STORM_CAVE  host send stub (broadcast the 0xE0-byte shuffle record as raw 0xC8, then the normal 0xF03FC0).
  STORM       routing 0xC8 -> players; guest reads raw from anyone, no parser; role gates (host / offline ->
              offline producer path, guest -> online path) in WaitIndication, Indication, FinishProcess;
              Indication gate last. PhasePrepare is already local on every game (shipped DUSK_ENV_TIMER_LOCAL).
Cave: main+0x563E820..0x563E867 (18 words) inside the free range given for this task (0x563E820..0x563E8DF).
lives_live.py already uses 0x563E880..0x563E8C7 and closewhy 0x563E8E0, so they are avoided. msgtrace.py's
tracer (0x563E800..0x563E877, diagnostic only) overlaps: never install both at once."""
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
OUT = 'event_effects_live.py'
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

ROLE = 0x492AFD8      # u32 written by dusk_lan.cpp: 0 = this game is the authority (host; also 0 offline), 1 = guest
MGR3 = 0x5B3CE08      # pointer cell holding the session manager mgr3 (+0x10 transport, +0x1268 mode)
MODE_OFF = 0x1268
FREE_LO, FREE_HI = 0x563E820, 0x563E8E0     # range handed to this task
CAVE = 0x563E820
MSGTRACE = (0x563E800, 0x563E878)           # diagnostic tracer of diag/twin/msgtrace.py (warning only)
CLOSEWHY_SLOT = (0x563E8E0, 0x563E8F8)

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

# ---------------------------------------------------------------- bytes claimed by every other *_live.py
claimed = {}
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == OUT:
        continue
    for m in re.finditer(r'\(\s*(0x[0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"', open(f, encoding='utf-8', errors='ignore').read()):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            claimed.setdefault(a + i, os.path.basename(f))
print('bytes claimed by other *_live.py files: %d' % len(claimed))


# ---------------------------------------------------------------- encoders
def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bne(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 1
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldr_x(rt, rn, off): assert off % 8 == 0; return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): assert off % 4 == 0; return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): assert 0 <= off < 0x1000; return 0x39400000 | (off << 10) | (rn << 5) | rt
def add_xi(rd, rn, imm): assert 0 <= imm < 0x1000; return 0x91000000 | (imm << 10) | (rn << 5) | rd
def cmp_wi(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def movz_w(rd, imm): return 0x52800000 | (imm << 5) | rd
def mov_xr(rd, rm): return 0xAA0003E0 | (rm << 16) | rd
def blr(rn): return 0xD63F0000 | (rn << 5)
def _pair(base, rt, rt2, rn, off): return base | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def stp_pre(rt, rt2, rn, off): return _pair(0xA9800000, rt, rt2, rn, off)
def ldp_post(rt, rt2, rn, off): return _pair(0xA8C00000, rt, rt2, rn, off)


NOP = 0xD503201F
SP, FP, LR = 31, 29, 30


def word(a):
    return struct.unpack_from('<I', TXT, a)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


listing = []


def free_byte(a, what):
    assert a not in shipped, '%s collides with a shipped record at %x' % (what, a)
    assert a not in claimed, '%s collides with %s at %x' % (what, claimed[a], a)


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        free_byte(addr + i, 'text patch')
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def ro_byte_patch(addr, old, new, note):
    got = RO[addr - RO_BASE]
    assert got == old, 'ro byte %x is %02x, expected %02x' % (addr, got, old)
    free_byte(addr, 'ro byte')
    listing.append('  0x%x  ro byte %02X -> %02X   (%s)' % (addr, old, new, note))
    return (addr, '%02X' % old, '%02X' % new, False)


def cave_records(name, start, ws, expect):
    assert len(ws) == len(expect)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    out = []
    for i, w in enumerate(ws):
        a = start + i * 4
        assert FREE_LO <= a < FREE_HI, 'cave word %x outside the free range' % a
        o = a - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % a
        for j in range(4):
            free_byte(a + j, 'cave')
            assert not (CLOSEWHY_SLOT[0] <= a + j < CLOSEWHY_SLOT[1]), 'cave hits the closewhy slot'
        got = dis1(a, w)
        assert got == expect[i], 'cave %x: %s, expected %s' % (a, got, expect[i])
        listing.append('  0x%x %s  %s' % (a, hexw(w), got))
        out.append((a, '00000000', hexw(w), True))
    return out


# ---------------------------------------------------------------- the free range is zero and unreferenced
def range_refs(lo, hi):
    hits = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            if lo <= o + imm * 4 < hi:
                hits.append(('branch', o))
    for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 8):
            if lo <= struct.unpack_from('<Q', seg, o)[0] < hi:
                hits.append(('pointer', base + o))
    return hits


refs = range_refs(FREE_LO, FREE_HI)
assert not refs, 'free range referenced: %r' % refs[:5]
listing.append('range 0x%X..0x%X: no branch / pointer in text, ro or data reaches it' % (FREE_LO, FREE_HI))
taken = sorted({a & ~3 for a in claimed if FREE_LO <= a < FREE_HI})
if taken:
    listing.append('  inside it, other *_live.py words already sit at 0x%X..0x%X (%s): avoided'
                   % (taken[0], taken[-1] + 3, claimed[taken[0]]))

# ================================================================ STORM (1140)
listing.append('=== STORM context (original words the design relies on)')
CTX = [
    (0x114F684, 'ldrb w8, [x8, #0xf]'), (0x114F688, 'cmp w8, #0xc'), (0x114F69C, 'ldr x8, [x8, #0x28]'),  # starts par+0x2D0 at step 1
    (0xF03E00, 'cmp w9, #6'), (0xF03E10, 'mov x24, sp'), (0xF03E9C, 'mov w1, #0xc8'), (0xF03EA8, 'mov x4, xzr'),
    (0xF03ECC, 'ldr w8, [sp]'), (0xF03EEC, 'cmp w0, #3'), (0xF03EFC, 'bl #0xf03fc0'), (0xF03F04, 'bl #0xf04a50'),
    (0xF0519C, 'str xzr, [x28, #0x60]'), (0xF0719C, 'add x1, sp, #0x150'), (0xF071A0, 'mov x0, x20'),
    (0xF071A8, 'adrp x8, #0x5b3c000'), (0xF071B8, 'ldr x8, [x28, #0x150]'),
    (0xF04CAC, 'adrp x20, #0x5b65000'), (0xF04D44, 'ldr x8, [x20, #0xc20]'),
    (0xF0508C, 'ldrb w8, [x0, #0x2f9]'), (0xF05190, 'mov x8, #0xbf800000'), (0xF07AB4, 'ldrb w8, [x19, #0x2f9]'),
    (0xF0A838, 'mov w0, #0xe0'),
]
for a, t in CTX:
    got = dis1(a, word(a))
    assert got == t, (hex(a), got, t)
    listing.append('  context 0x%x: %s' % (a, got))

s = CAVE
send_words = [
    stp_pre(FP, LR, SP, -0x10),          # 0
    adrp(s + 4, 8, MGR3),                # 1
    ldr_x(8, 8, MGR3 & 0xFFF),           # 2  x8 = mgr3
    None,                                # 3  cbz x8, skip
    ldr_w(9, 8, MODE_OFF),               # 4
    cmp_wi(9, 6),                        # 5
    None,                                # 6  b.ne skip  (session mode 6 only)
    add_xi(0, 8, 0x10),                  # 7  x0 = transport
    ldr_x(9, 0, 0),                      # 8
    ldr_x(9, 9, 0x40),                   # 9  vt+0x40 = broadcast
    movz_w(1, 0xC8),                     # 10
    add_xi(2, SP, 0x160),                # 11 record = caller sp+0x150 (+0x10 own frame)
    movz_w(3, 0xE0),                     # 12 size the reader expects (0xF0A838)
    blr(9),                              # 13
    ldp_post(FP, LR, SP, 0x10),          # 14 skip:
    mov_xr(0, 20),                       # 15 x0 = step (x20, callee-saved)
    add_xi(1, SP, 0x150),                # 16 x1 = record
    b(s + 17 * 4, 0xF03FC0),             # 17 the original call target
]
skip = s + 14 * 4
send_words[3] = cbz_x(s + 12, 8, skip)
send_words[6] = bne(s + 24, skip)
send_expect = [
    'stp x29, x30, [sp, #-0x10]!', 'adrp x8, #0x5b3c000', 'ldr x8, [x8, #0xe08]', 'cbz x8, #0x%x' % skip,
    'ldr w9, [x8, #0x1268]', 'cmp w9, #6', 'b.ne #0x%x' % skip, 'add x0, x8, #0x10', 'ldr x9, [x0]',
    'ldr x9, [x9, #0x40]', 'mov w1, #0xc8', 'add x2, sp, #0x160', 'mov w3, #0xe0', 'blr x9',
    'ldp x29, x30, [sp], #0x10', 'mov x0, x20', 'add x1, sp, #0x150', 'b #0xf03fc0',
]
STORM_CAVE = cave_records('STORM_SEND', s, send_words, send_expect)


def role_gate(addr, online, note):
    """3 words: adrp x8, ROLE page; ldrb w8, [x8, #lo]; cbnz w8, online (guest -> online path)."""
    return [
        (addr, adrp(addr, 8, ROLE)),
        (addr + 4, ldrb(8, 8, ROLE & 0xFFF)),
        (addr + 8, cbnz_w(addr + 8, 8, online)),
    ]


listing.append('=== STORM')
STORM = [
    ro_byte_patch(0x4C4B3B0 + 8 * 0xC8, 0x60, 0x20, 'routing 0xC8: players only, no self copy'),
    text_patch(0xF03EA0, 'mov x2, x22', mov_xr(2, 24), 'guest: raw 0xC8 straight into the record at sp (x24)'),
    text_patch(0xF03EA4, 'ldr x8, [x8, #0x60]', ldr_x(8, 8, 0x50), 'guest: read from anyone (+0x60 -> +0x50)'),
    text_patch(0xF03EC4, 'blr x8', movz_w(0, 1), 'guest: skip the bit-stream parser, report success'),
    text_patch(0xF071A4, 'bl #0xf03fc0', bl(0xF071A4, CAVE), 'host Indication: broadcast the record, then 0xF03FC0'),
]
# PhasePrepare needs nothing: shipped DUSK_ENV_TIMER_LOCAL already nops its +0xBDA gate, so every game times
# the shuffle itself (+0xD0/+0xD4, +0xD8 = 1) and walks 1 -> 2 -> 3, where it then waits for 0xC8 today.
assert bytes(shipped[0xF04CBC + i] for i in range(4)).hex().upper() == '1F2003D5', 'DUSK_ENV_TIMER_LOCAL not shipped'
listing.append('  context 0xf04cbc: shipped DUSK_ENV_TIMER_LOCAL nop (PhasePrepare offline path on every game)')
# role gates: orig words adrp/ldr/ldrb/cbz -> adrp ROLE / ldrb role / cbnz -> online / nop
G = []
G += [text_patch(0xF0507C, 'adrp x8, #0x5b65000', adrp(0xF0507C, 8, ROLE), 'WaitIndication gate 1/4'),
      text_patch(0xF05080, 'ldr x8, [x8, #0xc20]', ldrb(8, 8, ROLE & 0xFFF), 'WaitIndication gate 2/4'),
      text_patch(0xF05084, 'ldrb w8, [x8, #0xbda]', cbnz_w(0xF05084, 8, 0xF05100), 'WaitIndication gate 3/4: guest waits for 0xC8'),
      text_patch(0xF05088, 'cbz w8, #0xf05100', NOP, 'WaitIndication gate 4/4')]
G += [text_patch(0xF07AA0, 'adrp x8, #0x5b65000', adrp(0xF07AA0, 8, ROLE), 'FinishProcess gate 1/3 (0xF07AA4 mov x19,x0 kept)'),
      text_patch(0xF07AA8, 'ldr x8, [x8, #0xc20]', ldrb(8, 8, ROLE & 0xFFF), 'FinishProcess gate 2/3'),
      text_patch(0xF07AAC, 'ldrb w8, [x8, #0xbda]', cbnz_w(0xF07AAC, 8, 0xF07AC8), 'FinishProcess gate 3/3: guest -> step 3'),
      text_patch(0xF07AB0, 'cbz w8, #0xf07ac8', NOP, 'FinishProcess gate (old cbz)')]
assert dis1(0xF07AA4, word(0xF07AA4)) == 'mov x19, x0'
# Indication gate last: it switches the host's offline producer on
G += [text_patch(0xF05180, 'adrp x8, #0x5b65000', adrp(0xF05180, 8, ROLE), 'Indication gate 1/4'),
      text_patch(0xF05184, 'ldr x8, [x8, #0xc20]', ldrb(8, 8, ROLE & 0xFFF), 'Indication gate 2/4'),
      text_patch(0xF05188, 'ldrb w8, [x8, #0xbda]', cbnz_w(0xF05188, 8, 0xF071B8), 'Indication gate 3/4: guest -> online loop'),
      text_patch(0xF0518C, 'cbz w8, #0xf071b8', NOP, 'Indication gate 4/4')]
STORM += G

# ---------------------------------------------------------------- no record overlaps another, msgtrace warning
groups = {'STORM_CAVE': STORM_CAVE, 'STORM': STORM}
seen = {}
for g, rs in groups.items():
    for addr, o, n, c in rs:
        for i in range(len(n) // 2):
            assert addr + i not in seen, 'overlap %x' % (addr + i)
            seen[addr + i] = g
cave_end = CAVE + 4 * len(send_words)
if cave_end > MSGTRACE[0] and CAVE < MSGTRACE[1]:
    listing.append('WARNING: cave 0x%X..0x%X overlaps msgtrace.py tracer 0x%X..0x%X: do not install msgtrace with it'
                   % (CAVE, cave_end - 1, MSGTRACE[0], MSGTRACE[1] - 1))
print('\n'.join(listing))

L = ['"""Environment-event effect groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
     'Generated by event_effects_gen.py (original-word checks, capstone check of every new word, collision checks',
     'against patch_manager.cpp and every other diag/net/*_live.py, free-range zero/unreferenced check). NOT live-tested.',
     'Notes: event_effects_notes.md. Only 1140 (storm) has a group; 1120/1210/1220/1300 need none or are not cheap.',
     'Apply both groups on EVERY game (the role word main+0x492AFD8 picks host / guest at run time), STORM_CAVE first.',
     'STORM_CAVE sits at 0x563E820..0x563E867: never together with diag/twin/msgtrace.py (its tracer is 0x563E800..0x563E877).',
     'The ro routing byte record has is_code False, like events_live.py."""', '']
notes = {
    'STORM_CAVE': 'host: broadcast the 0xE0-byte shuffle record as raw 0xC8, then 0xF03FC0 (inert until STORM)',
    'STORM': 'routing + guest raw read + guest no-wait + role gates; host producer hook 0xF071A4, Indication gate last',
}
for g in ('STORM_CAVE', 'STORM'):
    L.append('%s = [  # %s' % (g, notes[g]))
    for addr, o, n, c in groups[g]:
        L.append('    (0x%X, "%s", "%s", %s),' % (addr, o, n, c))
    L.append(']')
L.append('')
L.append('ORDER = [STORM_CAVE, STORM]')
open(os.path.join(HERE, OUT), 'w', newline='\n').write('\n'.join(L) + '\n')
print('%s written, %d records' % (OUT, sum(len(v) for v in groups.values())))
