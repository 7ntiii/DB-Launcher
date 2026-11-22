"""Generator + checker for the small-gap groups in smallgaps_live.py. Static only (reads nso/*.bin and
src/lichii/src/core/file_sys/patch_manager.cpp, writes smallgaps_live.py, prints capstone listings).
python smallgaps_gen.py

Groups (design and [V]/[I] marks: smallgaps_notes.md):
  ALLIANCE_FINAL_END  0x116BAF4 nop: the final's phase-19 step calls the reason-9 dissolve 0x10B0500 in LAN too.
  ALLIANCE_DISCARD    = alliance_live.py DISCARD, re-verified, no cave, no collision with shipped records.
  SIGIL_OWN_CAVES / SIGIL_OWN   every game runs the 0x88 producer for its own player, writes its own player
                      number into its own entry, broadcasts it (shipped send_88), and every game re-reads 0x88.
  POWERS_COPY_CAVES / POWERS_COPY  social_live.py EQUIP_SKILL (0x5B broadcast + read from anyone) moved out of
                      the shipped cave6 range 0x563E600..0x563E68C.
Caves: main+0x563EA90..0x563EADF (ro padding past the ro file end; free in every file of the workspace, see the
reserved list below; no branch or pointer in text/data reaches it)."""
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

GDM = 0x5B57EB8      # *(main+0x5B57EB8) = game data manager; +0x20 = local PlayerGameData; pgd+0xD0 = player no

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}   # byte address -> shipped byte
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


# Ranges claimed by shipped records, other helpers' *_live.py files or notes (diag/net, diag/twin):
RESERVED = [
    (0x563E45C, 0x563E7E0, 'shipped caves 4/6, items, MAPSIM set'),
    (0x563E7E0, 0x563E800, 'closewhy_live.py'),
    (0x563E800, 0x563EA8C, 'msgtrace.py tracer 0x563E800, rec7.py 0x563E900, re-request cave 0x563EA00 (140 B)'),
    (0x563EB00, 0x563EC20, 'C9 / SUBQUEST caves (shipped)'),
    (0x563EC20, 0x563ED00, 'offline_gate_census.md proposals 0x563EC40..0x563ECFF'),
    (0x563ED00, 0x563F000, 'BC caves, closewhy, drops, MAP inbox'),
]
CAVE_LO, CAVE_HI = 0x563EA90, 0x563EAE0


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


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt


NOP = 0xD503201F
RET = 0xD65F03C0

listing = []
groups = {}


def text_patch(addr, expect, new, note):
    """Code word in main text: assert the original instruction, return the record."""
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    assert not any(addr + i in shipped for i in range(4)), 'collides with a shipped record at %x' % addr
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def shipped_patch(addr, expect, new, note):
    """Word inside a shipped cave: the original is the shipped word (what live memory holds)."""
    old = struct.unpack('<I', shipped_word(addr))[0]
    got = dis1(addr, old)
    assert got == expect, 'shipped %x: %s, expected %s' % (addr, got, expect)
    listing.append('  0x%x  %s  ->  %s   (%s, shipped cave word)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def cave(name, start, ws):
    for i in range(len(ws)):
        a = start + i * 4
        assert CAVE_LO <= a < CAVE_HI, 'cave word %x outside the reserved slot' % a
        o = a - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % a
        for j in range(4):
            assert a + j not in shipped, 'cave collides with shipped record at %x' % a
        for lo, hi, who in RESERVED:
            assert not (lo <= a < hi), 'cave %x in reserved range (%s)' % (a, who)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    for i, w in enumerate(ws):
        listing.append('  0x%x %s' % (start + i * 4, dis1(start + i * 4, w)))
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)]


# ---------------------------------------------------------------- the slot is unreferenced
def slot_unreferenced():
    hits = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        if (w & 0x7C000000) == 0x14000000:          # b / bl
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            t = o + imm * 4
            if CAVE_LO <= t < CAVE_HI:
                hits.append(('branch', o))
    for seg, base in ((DATA, DATA_BASE), (RO, RO_BASE)):
        for o in range(0, len(seg) - 7, 8):
            v = struct.unpack_from('<Q', seg, o)[0]
            if CAVE_LO <= v < CAVE_HI:
                hits.append(('pointer', base + o))
    return hits


refs = slot_unreferenced()
assert not refs, 'cave slot referenced: %r' % refs[:5]
listing.append('cave slot 0x%X..0x%X: zero, outside every reserved range, no branch/pointer reaches it' % (CAVE_LO, CAVE_HI))

# ================================================================ 1. ALLIANCE_FINAL_END
listing.append('=== ALLIANCE_FINAL_END')
assert dis1(0x116BAF8, word(0x116BAF8)) == 'bl #0x10b0500'
assert dis1(0x116BAF0, word(0x116BAF0)) == 'ldrb w8, [x8, #0xbda]'
groups['ALLIANCE_FINAL_END'] = [
    text_patch(0x116BAF4, 'cbz w8, #0x116bafc', NOP, 'phase-19 step 0x116BAB4: call the reason-9 dissolve in LAN'),
]
# the dissolve itself is opened by the shipped MATCH_END (0x10B0534 cmp #6 -> #0xff)
assert shipped_word(0x10B0534).hex().upper() == '1FFD0371', 'MATCH_END not shipped'
# and its 0x4B result is applied locally (ALLY_NO_4B_WIRE 0x10B07B4 nop)
assert shipped_word(0x10B07B4).hex().upper() == '1F2003D5', 'NO_4B_WIRE not shipped'

# ================================================================ 2. ALLIANCE_DISCARD
listing.append('=== ALLIANCE_DISCARD')
groups['ALLIANCE_DISCARD'] = [
    text_patch(0x10B036C, 'ldr x8, [x8, #0x48]', 0xF9402108, 'KEEP_SEND_ALL: kind 4 to everyone'),
    text_patch(0x10B5E34, 'cbz w9, #0x10b5b98', NOP, 'DISCARD_LOCAL: kind 3 handler runs'),
    text_patch(0x10B5ED4, 'cbz w9, #0x10b5b98', NOP, 'KEEP_LOCAL: kind 4 handler runs'),
    text_patch(0x10ADDE4, 'cbz w8, #0x10ade48', NOP, 'WINDOW_LOCAL: 60 s discard window opens at the phase change'),
    text_patch(0x10AB380, 'b.eq #0x10ab260', NOP, 'DISSOLVE_GUEST: queued discards dissolve (reason 1)'),
]
assert hexw(0xF9402108) == '082140F9'

# ================================================================ 3. SIGIL_OWN
listing.append('=== SIGIL_OWN')
# producer tail: x10 = own entry (x11 - 0x14), x11/x30 free (x1 loaded at 0x11963C4 is kept)
for a, t in ((0x11963BC, 'madd x11, x11, x12, x13'), (0x11963C0, 'madd x10, x10, x12, x13'),
             (0x11963C4, 'ldr x1, [sp, #8]'), (0x11963C8, 'mov w12, #-1'),
             (0x11963D0, 'stp w20, w12, [x10, #4]'), (0x1196404, 'bl #0x1195c40')):
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
SIG = 0x563EAC8
sig_words = [
    adrp(SIG, 11, GDM),                 # adrp x11, GDM page
    ldr_x(11, 11, GDM & 0xFFF),         # x11 = game data manager
    ldr_x(11, 11, 0x20),                # x11 = local PlayerGameData (non-null: checked at 0x1195EB4)
    ldr_w(11, 11, 0xD0),                # w11 = own player number
    str_w(11, 10, 0),                   # entry +0 = own player number (was wzr)
    RET,
]
groups['SIGIL_OWN_CAVES'] = cave('SIGIL_OWN_ID', SIG, sig_words)
groups['SIGIL_OWN'] = [
    shipped_patch(0x563EB7C, 'cbnz w9, #0x563eb84', NOP, 'gate_88: guests run the producer too'),
    shipped_patch(0x563EC0C, 'cbz w9, #0x563ec14', NOP, 'reread_88: the host re-reads 0x88 per frame too'),
    text_patch(0x11963CC, 'stur wzr, [x11, #-0x14]', bl(0x11963CC, SIG), 'own entry: own player number, not 0'),
]
# shipped context the group relies on
for a, t in ((0x563EB80, 'b #0x1181e4c'), (0x563EC10, 'bl #0x1195b00')):
    got = dis1(a, struct.unpack('<I', shipped_word(a))[0])
    listing.append('  context 0x%x: %s' % (a, got))

# ================================================================ 6. POWERS_COPY (EQUIP_SKILL relocated)
listing.append('=== POWERS_COPY')
ES_SEND, ES_READ = 0x563EA90, 0x563EAA8
assert dis1(0x14E4E90, word(0x14E4E90)) == 'ldr x8, [x0, #0x10]!'
assert dis1(0x14E4EAC, word(0x14E4EAC)) == 'add x2, sp, #0xac'      # stock loopback branch copied below
assert dis1(0x14E4EBC, word(0x14E4EBC)) == 'bl #0x1cd8014'
assert dis1(0x14E4F50, word(0x14E4F50)) == 'add x3, sp, #0x8c'
assert dis1(0x14E4F6C, word(0x14E4F6C)) == 'mov w20, w0'
send_words = [
    word(0x14E4EAC),                    # add x2, sp, #0xac
    word(0x14E4EB0),                    # mov w1, #0x5b
    word(0x14E4EB4),                    # mov w3, w4
    word(0x14E4EB8),                    # mov w4, wzr
    bl(ES_SEND + 0x10, 0x1CD7C80),      # broadcast (instead of loopback 0x1CD8014); x0 = mgr3
    b(ES_SEND + 0x14, 0x14E4EC0),
]
read_words = [
    0x910233E2,                         # add x2, sp, #0x8c
    0x52800B61,                         # mov w1, #0x5b
    0x52804C83,                         # mov w3, #0x264
    0xF9402908,                         # ldr x8, [x8, #0x50]  (read from anyone)
    0xAA1F03E4,                         # mov x4, xzr
    0xD63F0100,                         # blr x8
    b(ES_READ + 0x18, 0x14E4F6C),
]
groups['POWERS_COPY_CAVES'] = cave('ES_SEND', ES_SEND, send_words) + cave('ES_READ', ES_READ, read_words)
groups['POWERS_COPY'] = [
    text_patch(0x14E4F50, 'add x3, sp, #0x8c', b(0x14E4F50, ES_READ), 'connected 0x5B read -> ES_READ'),
    text_patch(0x14E4E90, 'ldr x8, [x0, #0x10]!', b(0x14E4E90, ES_SEND), 'connected 0x5B send -> ES_SEND'),
]
# same words as social_live.py EQUIP_SKILL apart from the PC-relative ones
sl = open(os.path.join(HERE, 'social_live.py')).read()
for w in send_words[:4] + read_words[:6]:
    assert hexw(w) in sl, 'word %s not in social_live.py EQUIP_SKILL' % hexw(w)

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g

print('\n'.join(listing))

ORDER = ['ALLIANCE_FINAL_END', 'ALLIANCE_DISCARD', 'SIGIL_OWN_CAVES', 'SIGIL_OWN', 'POWERS_COPY_CAVES', 'POWERS_COPY']
out = ['"""Small-gap patch groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by smallgaps_gen.py (original-word checks, capstone listing of every new word, collision checks',
       'against patch_manager.cpp and the reserved cave ranges). Not live-tested. Notes: smallgaps_notes.md.',
       'Cave records have orig "00000000" (zero padding past the ro file end, slot 0x563EA90..0x563EADF).',
       'SIGIL_OWN patches two words of the SHIPPED SUBQUEST caves: their orig is the shipped word.',
       'Apply each *_CAVES group before its hook group; inside a group the hook is last.',
       'Apply on EVERY game (no group is host-only)."""', '']
notes = {
    'ALLIANCE_FINAL_END': 'final phase 19: dissolve every alliance (reason 9) on each game; needs shipped MATCH_END + NO_4B_WIRE',
    'ALLIANCE_DISCARD': 'alliance_live.py DISCARD, re-verified; discard window + kind 3/4 votes + local dissolve',
    'SIGIL_OWN_CAVES': 'own player number into the own 0x88 entry (inert until SIGIL_OWN)',
    'SIGIL_OWN': 'every game produces + broadcasts its own sigil entry, every game re-reads 0x88 (needs shipped SUBQUEST)',
    'POWERS_COPY_CAVES': 'EQUIP_SKILL caves moved to 0x563EA90 (inert until POWERS_COPY)',
    'POWERS_COPY': 'equip-skill / Power of Blood record 0x5B broadcast + read from anyone (hooks)',
}
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'smallgaps_live.py'), 'w').write('\n'.join(out) + '\n')
print('smallgaps_live.py written')
