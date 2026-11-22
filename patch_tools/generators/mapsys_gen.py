"""Generator + checker for the MapSystem sharing groups in mapsys_live.py. Static only.
python mapsys_gen.py  -> rewrites mapsys_live.py (keeps MAPSIM) and prints capstone listings of every cave.

Design (handoff 1, section 8.9n "MAP SHARING"):
  MAPSIM_HOST  0x11123E0: only the host (role byte main+0x492AFD8 == 0) or an offline game runs the simulation body.
  MAP_INBOX    0x11108EC: the 0x6A reader, when it has no message, takes one record from the inbox at
               main+0xC50F000 {u32 valid, u32 kind|flags, u32 nbytes, u32 pad, data..} (written by the assist):
               kind 0xFF -> MS+0x20 = 1 (ready to apply); else calls 0x11180E0(MS, kind, {data, data+nbytes}),
               the game's own list setter for received lists. Then valid = 0.
  MAP_APPEND   0x1118184 (inside 0x11180E0): with the inbox flag bit 8 set the list is appended to instead of
               replaced (for lists longer than one inbox record).
  MAP_WAIT     0x114FC48 (PrepareThird): a guest in rounds 1-3 does not apply before the assist has fed this round's
               lists (inbox+0x1F8 = round; the assist also writes it after a time-out). MS+0x20 cannot be used:
               the step-12 responder 0x1114700 sets it on every game.
Caves: ro padding main+0x563E6C0.. (checked zero and unused).
Inbox (2026-11-14, cave_lib_notes.md task 1): moved OUT of the near ro padding (old main+0x563EE00..0x563EFFF, now
the NEAR_TRAMP pool) INTO the far cave region data page: main+0xC50F000..0xC50F1FF, fed-round marker
main+0xC50F1F8 (= inbox+0x1F8, dusk_lan.cpp MAP_INBOX / MAP_FED). The caves stay where they are; only their
adrp/add/ldr operands change (adrp reaches +-4 GB). Needs the cave region mapped (loader log line
"Duskbloods cave region mapped"); the cave's `str wzr, [x21]` is a guest store into a read-only region page: it
works (fastmem fault -> Dynarmic recompiles to the page-table path, cave_region3_notes.md) but is slow once."""
import os
import struct

import capstone

N = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
RO_BASE = 0x492B000
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

ROLE = 0x492AFD8
INBOX = 0xC50F000          # far region data page (was 0x563EE00); registered in cave_registry.md
FED = INBOX + 0x1F8        # fed-round marker (dusk_lan.cpp MAP_FED)
assert 0xC50F000 <= INBOX and FED + 4 <= 0xC510000 and FED == 0xC50F1F8
PAR = 0x5B3CDF8


def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bne(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 1
def beq(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 0
def cmp_wr(rn, rm): return 0x6B00001F | (rm << 16) | (rn << 5)
def bhs(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 2
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def tbz(pc, rt, bit, t): return 0x36000000 | (bit << 19) | (_rel(pc, t, 14) << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def add_xi(rd, rn, imm): return 0x91000000 | (imm << 10) | (rn << 5) | rd
def sub_xi(rd, rn, imm): return 0xD1000000 | (imm << 10) | (rn << 5) | rd
def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def str_w(rt, rn, off): return 0xB9000000 | ((off // 4) << 10) | (rn << 5) | rt
def str_x(rt, rn, off): return 0xF9000000 | ((off // 8) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt
def strb(rt, rn, off): return 0x39000000 | (off << 10) | (rn << 5) | rt
def and_ff(rd, rn): return 0x12001C00 | (rn << 5) | rd          # and wd, wn, #0xff
def cmp_wi(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)  # cmp wn, #imm
def movz_w(rd, imm): return 0x52800000 | (imm << 5) | rd
def add_xr(rd, rn, rm): return 0x8B000000 | (rm << 16) | (rn << 5) | rd
def mov_x(rd, rm): return 0xAA0003E0 | (rm << 16) | rd
def stp_off(rt, rt2, rn, off): return 0xA9000000 | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldp_pre(rt, rt2, rn, off): return 0xA9C00000 | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt


SP = 31


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


recs = {}
listing = []


def cave(name, start, build):
    """build(pc0) -> list of words; checks the padding is zero."""
    ws = build(start)
    for i in range(len(ws)):
        o = start + i * 4 - RO_BASE
        # past the end of the ro file = segment padding (zero in memory)
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % (start + i * 4)
    code = b''.join(struct.pack('<I', w) for w in ws)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    n = 0
    for ins in md.disasm(code, start):
        listing.append('  0x%x %s %s' % (ins.address, ins.mnemonic, ins.op_str))
        n += 1
    assert n == len(ws), 'cave %s: undecodable word' % name
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)], start + len(ws) * 4


def hook(addr, target, expect_text):
    ins = next(md.disasm(TXT[addr:addr + 4], addr))
    assert (ins.mnemonic + ' ' + ins.op_str) == expect_text, 'hook %x is %s %s' % (addr, ins.mnemonic, ins.op_str)
    return (addr, hexw(word(addr)), hexw(b(addr, target)), True)


pc = 0x563E6C0

# ---- MAPSIM_HOST
def c1(p):
    skip = p + 0x2C
    return [cbnz_w(p, 8, p + 0x28),             # 00 offline game: run
            adrp(p + 4, 8, ROLE),               # 04
            ldrb(8, 8, ROLE & 0xFFF),           # 08
            cbnz_w(p + 0xC, 8, skip),           # 0C guest: skip
            adrp(p + 0x10, 8, PAR),             # 10
            ldr_x(8, 8, PAR & 0xFFF),           # 14
            cbz_x(p + 0x18, 8, skip),           # 18
            ldr_w(8, 8, 0xB8),                  # 1C round
            cmp_wi(8, 4),                       # 20
            bhs(p + 0x24, skip),                # 24 the final has no map content (and the run broke the session)
            b(p + 0x28, 0x11123E4),             # 28 run
            b(p + 0x2C, 0x111440C)]             # 2C skip
c1_at = pc
r, pc = cave('MAPSIM_HOST', pc, c1)
recs['MAPSIM_HOST'] = r + [hook(0x11123E0, c1_at, 'cbz w8, #0x111440c')]

# ---- MAP_INBOX
def c3(p):
    L_list, L_done, L_exit, L_parse = p + 0x30, p + 0x5C, p + 0x60, p + 0x64
    return [
        cbnz_w(p, 20, L_parse),                 # 00 a real message was read
        adrp(p + 4, 21, INBOX),                 # 04
        add_xi(21, 21, INBOX & 0xFFF),          # 08
        ldr_w(8, 21, 0),                        # 0C valid
        cbz_w(p + 0x10, 8, L_exit),             # 10
        ldr_w(1, 21, 4),                        # 14 kind | flags
        and_ff(9, 1),                           # 18
        cmp_wi(9, 0xFF),                        # 1C
        bne(p + 0x20, L_list),                  # 20
        movz_w(9, 1),                           # 24
        strb(9, 19, 0x20),                      # 28 MS+0x20 = 1
        b(p + 0x2C, L_done),                    # 2C
        ldr_w(8, 21, 8),                        # 30 nbytes
        add_xi(9, 21, 0x10),                    # 34 begin
        add_xr(10, 9, 8),                       # 38 end
        sub_xi(SP, SP, 0x20),                   # 3C
        stp_off(9, 10, SP, 0),                  # 40
        str_x(10, SP, 0x10),                    # 44
        mov_x(0, 19),                           # 48 MS
        and_ff(1, 1),                           # 4C kind
        add_xi(2, SP, 0),                       # 50 mov x2, sp
        bl(p + 0x54, 0x11180E0),                # 54
        add_xi(SP, SP, 0x20),                   # 58
        str_w(31, 21, 0),                       # 5C valid = 0 (wzr)
        b(p + 0x60, 0x1110A6C),                 # 60
        b(p + 0x64, 0x11108F0),                 # 64
    ]
c3_at = pc
r, pc = cave('MAP_INBOX', pc, c3)
recs['MAP_INBOX'] = r + [hook(0x11108EC, c3_at, 'cbz w20, #0x1110a6c')]

# ---- MAP_APPEND
def c5(p):
    L_repl, L_ret = p + 0x2C, p + 0x30
    return [
        cbnz_w(p, 8, L_ret),                    # 00 offline: return as before
        adrp(p + 4, 9, INBOX),                  # 04
        add_xi(9, 9, INBOX & 0xFFF),            # 08
        ldr_w(10, 9, 0),                        # 0C valid
        cbz_w(p + 0x10, 10, L_repl),            # 10
        ldr_w(10, 9, 4),                        # 14
        tbz(p + 0x18, 10, 8, L_repl),           # 18 bit 8 = append
        word(0x1118198),                        # 1C lsl x8, x1, #0x20
        word(0x111819C),                        # 20 add x20, x0, x8, asr #27
        ldp_pre(8, 9, 20, 0x28),                # 24 x8 = begin, x9 = end
        b(p + 0x28, 0x11181F8),                 # 28 reserve + push
        b(p + 0x2C, 0x1118198),                 # 2C
        b(p + 0x30, 0x1118188),                 # 30
    ]
c5_at = pc
r, pc = cave('MAP_APPEND', pc, c5)
recs['MAP_APPEND'] = r + [hook(0x1118184, c5_at, 'cbz w8, #0x1118198')]

# ---- MAP_WAIT
def c4(p):
    go = p + 0x3C
    return [
        word(0x114FC48),                        # 00 ldr x0, [x19, #0x2d8]
        adrp(p + 4, 8, ROLE),                   # 04
        ldrb(8, 8, ROLE & 0xFFF),               # 08
        cbz_w(p + 0xC, 8, go),                  # 0C host
        adrp(p + 0x10, 8, PAR),                 # 10
        ldr_x(8, 8, PAR & 0xFFF),               # 14
        cbz_x(p + 0x18, 8, go),                 # 18
        ldr_w(8, 8, 0xB8),                      # 1C round
        cmp_wi(8, 4),                           # 20
        bhs(p + 0x24, go),                      # 24 the final: nothing to wait for
        adrp(p + 0x28, 9, INBOX),               # 28
        ldr_w(9, 9, FED & 0xFFF),               # 2C round whose lists the assist has fed
        cmp_wr(8, 9),                           # 30
        beq(p + 0x34, go),                      # 34 fed: apply
        b(p + 0x38, 0x114FDF4),                 # 38 not yet: leave the step for this tick
        b(p + 0x3C, 0x114FC4C),                 # 3C
    ]
c4_at = pc
r, pc = cave('MAP_WAIT', pc, c4)
recs['MAP_WAIT'] = r + [hook(0x114FC48, c4_at, 'ldr x0, [x19, #0x2d8]')]

assert pc <= 0x563E800, hex(pc)
print('\n'.join(listing))
print('caves end at 0x%X' % pc)
for a in (0x1118198, 0x111819C, 0x114FC48):
    i = next(md.disasm(TXT[a:a + 4], a))
    print('copied 0x%x: %s %s' % (a, i.mnemonic, i.op_str))

out = ['"""Live patch groups for the per-round MapSystem simulation: (offset_from_main, orig_hex, new_hex, is_code).',
       'Generated by mapsys_gen.py (design and listings there). MAPSIM = first experiment (every game runs the simulation',
       'itself, no sharing); the sharing set is MAPSIM_HOST + MAP_INBOX + MAP_APPEND + MAP_WAIT (do not combine with MAPSIM)."""',
       '', 'MAPSIM = [  # 0x11123E0  cbz w8(offline flag), 0x111440c  ->  nop',
       '    (0x11123E0, "68010134", "1F2003D5", True),', ']', '']
for g in ('MAPSIM_HOST', 'MAP_INBOX', 'MAP_APPEND', 'MAP_WAIT'):
    out.append('%s = [' % g)
    for off, o, n, c in recs[g]:
        out.append('    (0x%X, "%s", "%s", True),' % (off, o, n))
    out.append(']')
    out.append('')
out.append('ORDER = [MAPSIM_HOST, MAP_INBOX, MAP_APPEND, MAP_WAIT]')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mapsys_live.py'), 'w').write('\n'.join(out) + '\n')
print('mapsys_live.py written')
