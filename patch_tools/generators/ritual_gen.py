"""Generator + checker for ritual_live.py (Ritual Sites = Shelter, message 0x4D; pledge pillars = NameList,
message 0x4E). Static only.  python ritual_gen.py  -> writes ritual_live.py next to this file and prints
capstone listings of every cave, every hook (original asserted), branch targets and register-liveness checks.

Design (details and reasoning in ritual_patch_notes.md):
  RITUAL_LAYOUT  0x10878D4 (builder, b.eq mode 6 -> return): host (role byte 0) builds the layout as offline;
                 a guest clears its shelter manager (keeps gl+0x77C) and returns.
  RITUAL_PUSH    0x1087994 (bl store into gl+0x548) -> store, then the host sends gl+0x548 as 0x4D to everybody
                 by calling the game's 0x4D sender 0x108A820 with the marker id -2;
                 0x108A950 (inside 0x108A820): id -2 -> transport vt+0x40 (broadcast) instead of the member send.
  RITUAL_READ    0x1087798 reader vt+0x60 (server = self link) -> vt+0x50 (from anyone);
                 0x10877C0: in mode 6 a 0x4D with 0 records is ignored (no clear), gl+0x77C still set.
  RITUAL_HOSTSKIP (optional, not in ORDER) 0x114F36C: the host does not call the reader at all.
  PLEDGE_REQUEST 0x108C240 kind-0 request vt+0x48 -> vt+0x40 (routing 0x4E is 0x00: all incl. self link).
  PLEDGE_DECIDE  0x1094B04 kind 0: offline or host -> decision 0x108C520 (applies + broadcasts kind 3); guest drops.
  PLEDGE_RESULT  0x1094B90 kind 3: mode 6 guests apply; the host drops (its own echo; it applied in 0x108C520).
  PLEDGE_KILL    (optional) 0x10921B4 kill-steal decision 0x108C520: guests in mode 6 skip it (w0 = 0).
Caves: ro padding main+0x563E900..0x563EAFF (zero, past the ro file end 0x563E45C, unused by every *_live.py and
patch_manager.cpp, no text reference)."""
import os
import struct
import array

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
RO_BASE = 0x492B000
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
md.detail = True

CAVE_LO, CAVE_HI = 0x563E900, 0x563EB00
ROLE = 0x492AFD8      # role byte: 0 = host, 1 = guest
MGR3 = 0x5B3CE08      # pointer cell holding mgr3 (session; +0x1268 = mode, 6 = LAN)
MODE_OFF = 0x1268
SP, FP, LR = 31, 29, 30
MARK = -2             # member id that means "broadcast" for the 0x4D sender


# ---------------- encoders ----------------
def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
COND = {'eq': 0, 'ne': 1}
def bcond(pc, t, c): return 0x54000000 | (_rel(pc, t, 19) << 5) | COND[c]
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_x(pc, rt, t): return 0xB5000000 | (_rel(pc, t, 19) << 5) | rt


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldr_x(rt, rn, off): assert off % 8 == 0 and 0 <= off < 0x8000; return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def str_x(rt, rn, off): assert off % 8 == 0 and 0 <= off < 0x8000; return 0xF9000000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): assert off % 4 == 0 and 0 <= off < 0x4000; return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): assert 0 <= off < 0x1000; return 0x39400000 | (off << 10) | (rn << 5) | rt
def strb(rt, rn, off): assert 0 <= off < 0x1000; return 0x39000000 | (off << 10) | (rn << 5) | rt
def stp_pre(rt, rt2, rn, off): return 0xA9800000 | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def ldp_post(rt, rt2, rn, off): return 0xA8C00000 | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def add_xi(rd, rn, imm): assert 0 <= imm < 0x1000; return 0x91000000 | (imm << 10) | (rn << 5) | rd
def cmp_wi(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def cmn_xi(rn, imm): return 0xB100001F | (imm << 10) | (rn << 5)
def movz_w(rd, imm): assert 0 <= imm < 0x10000; return 0x52800000 | (imm << 5) | rd
def movn_x(rd, imm): return 0x92800000 | (imm << 5) | rd
def mov_xr(rd, rm): return 0xAA0003E0 | (rm << 16) | rd
def mov_wr(rd, rm): return 0x2A0003E0 | (rm << 16) | rd
def blr(rn): return 0xD63F0000 | (rn << 5)
RET = 0xD65F03C0


def word(a): return struct.unpack_from('<I', TXT, a)[0]
def hexw(w): return struct.pack('<I', w).hex().upper()


def dis1(w, at):
    i = next(md.disasm(struct.pack('<I', w), at))
    return (i.mnemonic + ' ' + i.op_str).strip()


def dis_at(a): return dis1(word(a), a)


# ---------------- cave / hook helpers (mapsys_gen style) ----------------
listing = []
recs = {}
ranges = []


def cave(name, start, build):
    """build(p) -> list of words; checks the padding is zero and every word decodes."""
    ws = build(start)
    for i in range(len(ws)):
        o = start + i * 4 - RO_BASE
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % (start + i * 4)
    assert CAVE_LO <= start and start + 4 * len(ws) <= CAVE_HI, name
    code = b''.join(struct.pack('<I', w) for w in ws)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    n = 0
    for ins in md.disasm(code, start):
        extra = ''
        if ins.mnemonic in ('b', 'bl', 'cbz', 'cbnz') or ins.mnemonic.startswith('b.'):
            t = ins.operands[-1].imm
            if not (start <= t < start + 4 * len(ws)):
                extra = '      ; -> %x: %s' % (t, dis_at(t))
        listing.append('  0x%x %s %s%s' % (ins.address, ins.mnemonic, ins.op_str, extra))
        n += 1
    assert n == len(ws), 'cave %s: undecodable word' % name
    ranges.append((name, start, start + 4 * len(ws)))
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)], start + len(ws) * 4


def hook(addr, new, expect_text):
    got = dis_at(addr)
    assert got == expect_text, 'hook %x is "%s", expected "%s"' % (addr, got, expect_text)
    listing.append('hook 0x%x: %s "%s" -> %s "%s"' % (addr, hexw(word(addr)), got, hexw(new), dis1(new, addr)))
    return (addr, hexw(word(addr)), hexw(new), True)


def align16(x): return (x + 15) & ~15


def mode6_guest_checks(p, w_mode, not_lan, host):
    """x9 = mgr3; not LAN -> not_lan; host -> host. 7 words. Clobbers x9, x10."""
    return [adrp(p, 9, MGR3), ldr_x(9, 9, MGR3 & 0xFFF), cbz_x(p + 8, 9, not_lan),
            ldr_w(10, 9, MODE_OFF), cmp_wi(10, 6), bcond(p + 0x14, not_lan, 'ne'),
            adrp(p + 0x18, 9, ROLE), ldrb(9, 9, ROLE & 0xFFF)] , host


pc = CAVE_LO

# ---- RITUAL_LAYOUT: 0x10878D4 b.eq #0x1087998 (flags from cmp w8,#6 at 0x10878D0); x0 = gl here
def c_layout(p):
    build, ret_ = 0x10878D8, 0x1087998
    L_build = p + 0x24
    return [bcond(p, L_build, 'ne'),          # 00 not LAN: build as before
            adrp(p + 4, 9, ROLE),             # 04
            ldrb(9, 9, ROLE & 0xFFF),         # 08
            cbz_w(p + 0xC, 9, L_build),       # 0C host: build like offline
            mov_xr(19, 0),                    # 10 guest: x19 = gl (x19/x20 saved by the prologue)
            ldrb(20, 0, 0x77C),               # 14 keep gl+0x77C as it was
            bl(p + 0x18, 0x1089D20),          # 18 clear the shelter manager (as every 0x4D read does)
            strb(20, 19, 0x77C),              # 1C
            b(p + 0x20, ret_),                # 20 return
            b(p + 0x24, build)]               # 24
at_layout = pc
r, pc = cave('RITUAL_LAYOUT', pc, c_layout)
recs['RITUAL_LAYOUT'] = r + [hook(0x10878D4, b(0x10878D4, at_layout), 'b.eq #0x1087998')]
pc = align16(pc)

# ---- RITUAL_PUSH (a): bl target from 0x1087994 (x0 = gl+0x548, x1 = sp+8 of the builder; LR = 0x1087998)
def c_push(p):
    done = p + 0x50
    return [stp_pre(FP, LR, SP, -0x20),       # 00
            add_xi(FP, SP, 0),                # 04 mov x29, sp
            str_x(0, SP, 0x10),               # 08 save &gl+0x548
            bl(p + 0xC, 0x10893E0),           # 0C the original store
            adrp(p + 0x10, 8, MGR3),          # 10
            ldr_x(8, 8, MGR3 & 0xFFF),        # 14
            cbz_x(p + 0x18, 8, done),         # 18
            ldr_w(9, 8, MODE_OFF),            # 1C
            cmp_wi(9, 6),                     # 20
            bcond(p + 0x24, done, 'ne'),      # 24 offline: nothing to send
            adrp(p + 0x28, 9, ROLE),          # 28
            ldrb(9, 9, ROLE & 0xFFF),         # 2C
            cbnz_w(p + 0x30, 9, done),        # 30 guests never get here (RITUAL_LAYOUT), but be sure
            movn_x(9, 1),                     # 34 x9 = -2 (broadcast marker)
            str_x(9, SP, 0x18),               # 38
            add_xi(0, 8, 0x10),               # 3C x0 = mgr3+0x10 (transport)
            add_xi(1, SP, 0x18),              # 40 x1 = &id
            movz_w(2, 0x4D),                  # 44 type 0x4D
            ldr_x(3, SP, 0x10),               # 48 x3 = gl+0x548
            bl(p + 0x4C, 0x108A820),          # 4C the game's own 0x4D sender (serializer)
            ldp_post(FP, LR, SP, 0x20),       # 50
            RET]                              # 54
at_push = pc
r1, pc = cave('RITUAL_PUSH_SEND', pc, c_push)
pc = align16(pc)

# ---- RITUAL_PUSH (b): inside 0x108A820 at 0x108A950 (ldr x1,[x20,#0x1238]); x0 = buffer, w21 = length,
#      w19 = type, x20 = transport, x23 = requested member id
def c_bcast(p):
    orig = p + 0x28
    return [cmn_xi(23, 2),                    # 00 id == -2 ?
            bcond(p + 4, orig, 'ne'),         # 04
            ldr_x(8, 20, 0),                  # 08 transport vtable
            mov_xr(2, 0),                     # 0C x2 = buffer
            mov_xr(0, 20),                    # 10 x0 = transport
            mov_wr(1, 19),                    # 14 w1 = type
            mov_wr(3, 21),                    # 18 w3 = length
            ldr_x(8, 8, 0x40),                # 1C vt+0x40 = send to all (routing byte)
            blr(8),                           # 20
            b(p + 0x24, 0x108A998),           # 24 epilogue of 0x108A820
            word(0x108A950),                  # 28 ldr x1, [x20, #0x1238]
            b(p + 0x2C, 0x108A954)]           # 2C
at_bcast = pc
r2, pc = cave('RITUAL_PUSH_BCAST', pc, c_bcast)
recs['RITUAL_PUSH'] = r1 + r2 + [hook(0x108A950, b(0x108A950, at_bcast), 'ldr x1, [x20, #0x1238]'),
                                 hook(0x1087994, bl(0x1087994, at_push), 'bl #0x10893e0')]
pc = align16(pc)

# ---- RITUAL_READ: 0x1087798 vt+0x60 -> vt+0x50; 0x10877C0 mov x0, x19 -> b cave (empty 0x4D ignored in LAN)
def c_empty(p):
    do = p + 0x20
    return [ldr_x(8, SP, 0x208),              # 00 record count of this message
            cbnz_x(p + 4, 8, do),             # 04
            ldr_x(9, 23, 0),                  # 08 x23 = &mgr3 cell (0x1087708)
            cbz_x(p + 0xC, 9, do),            # 0C
            ldr_w(9, 9, MODE_OFF),            # 10
            cmp_wi(9, 6),                     # 14
            bcond(p + 0x18, do, 'ne'),        # 18
            b(p + 0x1C, 0x108783C),           # 1C LAN + empty: skip clear/add/+0x780, set +0x77C, next message
            word(0x10877C0),                  # 20 mov x0, x19
            b(p + 0x24, 0x10877C4)]           # 24 bl 0x1089d20 (clear) and rebuild
at_empty = pc
r, pc = cave('RITUAL_READ_EMPTY', pc, c_empty)
recs['RITUAL_READ'] = r + [hook(0x1087798, ldr_x(8, 8, 0x50), 'ldr x8, [x8, #0x60]'),
                           hook(0x10877C0, b(0x10877C0, at_empty), 'mov x0, x19')]
pc = align16(pc)

# ---- RITUAL_HOSTSKIP (optional): bl target from 0x114F36C; host in LAN returns without reading
def c_hostskip(p):
    call = p + 0x28
    pre, _ = mode6_guest_checks(p, 10, call, None)
    return pre + [cbnz_w(p + 0x20, 9, call),  # 20 guest: read
                  RET,                        # 24 host: skip the read (builder already set +0x77C)
                  b(p + 0x28, 0x10876E0)]     # 28 tail call (LR still 0x114F370)
at_hostskip = pc
r, pc = cave('RITUAL_HOSTSKIP', pc, c_hostskip)
recs['RITUAL_HOSTSKIP'] = r + [hook(0x114F36C, bl(0x114F36C, at_hostskip), 'bl #0x10876e0')]
pc = align16(pc)

# ---- PLEDGE_REQUEST: 0x108C240 ldr x8,[x8,#0x48] -> #0x40
recs['PLEDGE_REQUEST'] = [hook(0x108C240, ldr_x(8, 8, 0x40), 'ldr x8, [x8, #0x48]')]

# ---- PLEDGE_DECIDE: 0x1094B04 cbz w8 (offline flag), #0x1094e00 -> gate
def c_decide(p):
    prod, drop = 0x1094B08, 0x1094E00
    return [cbnz_w(p, 8, p + 0x10),           # 00 offline: decide
            adrp(p + 4, 9, ROLE),             # 04
            ldrb(9, 9, ROLE & 0xFFF),         # 08
            cbnz_w(p + 0xC, 9, p + 0x14),     # 0C guest: drop
            b(p + 0x10, prod),                # 10 host / offline: 0x108C520
            b(p + 0x14, drop)]                # 14
at_decide = pc
r, pc = cave('PLEDGE_DECIDE', pc, c_decide)
recs['PLEDGE_DECIDE'] = r + [hook(0x1094B04, b(0x1094B04, at_decide), 'cbz w8, #0x1094e00')]
pc = align16(pc)

# ---- PLEDGE_RESULT: 0x1094B90 b.ne #0x1094e00 (kind 3, flags from cmp w8,#6) -> host drops its own echo
def c_result(p):
    apply_, drop = 0x1094B94, 0x1094E00
    L_drop = p + 0x14
    return [bcond(p, L_drop, 'ne'),           # 00 not LAN: drop as before
            adrp(p + 4, 9, ROLE),             # 04
            ldrb(9, 9, ROLE & 0xFFF),         # 08
            cbz_w(p + 0xC, 9, L_drop),        # 0C host: already applied in 0x108C520
            b(p + 0x10, apply_),              # 10 guest: apply
            b(p + 0x14, drop)]                # 14
at_result = pc
r, pc = cave('PLEDGE_RESULT', pc, c_result)
recs['PLEDGE_RESULT'] = r + [hook(0x1094B90, b(0x1094B90, at_result), 'b.ne #0x1094e00')]
pc = align16(pc)

# ---- PLEDGE_KILL (optional): bl target from 0x10921B4 (kill-steal decision); guests in LAN return 0
def c_kill(p):
    call = p + 0x2C
    pre, _ = mode6_guest_checks(p, 10, call, None)
    return pre + [cbz_w(p + 0x20, 9, call),   # 20 host: decide
                  movz_w(0, 0),               # 24 guest: "not decided"
                  RET,                        # 28
                  b(p + 0x2C, 0x108C520)]     # 2C tail call (LR still 0x10921B8)
at_kill = pc
r, pc = cave('PLEDGE_KILL', pc, c_kill)
recs['PLEDGE_KILL'] = r + [hook(0x10921B4, bl(0x10921B4, at_kill), 'bl #0x108c520')]
pc = align16(pc)


# ---- PLEDGE_SELF (optional, only if the host's own broadcast request never reaches its handler 0x1094AD8):
#      0x108C24C `b #0x108c28c` right after the vt+0x40 send; host in LAN also pushes the same request into its own
#      loopback queue (0x1CD8014(mgr3, 0x4E, buf, len, 0), the members == 0 path at 0x108C274..0x108C288).
#      x20 = mgr3+0x10 here (writeback at 0x108C230), w21 = length, writer object at sp+8.
def sub_xi(rd, rn, imm): return 0xD1000000 | (imm << 10) | (rn << 5) | rd


def c_self(p):
    out = p + 0x44
    return [adrp(p, 9, ROLE),                 # 00
            ldrb(9, 9, ROLE & 0xFFF),         # 04
            cbnz_w(p + 8, 9, out),            # 08 guest: nothing
            ldr_w(9, 20, MODE_OFF - 0x10),    # 0C mode (x20 = mgr3+0x10)
            cmp_wi(9, 6),                     # 10
            bcond(p + 0x14, out, 'ne'),       # 14
            ldr_x(8, SP, 8),                  # 18 writer vtable
            add_xi(0, SP, 8),                 # 1C
            ldr_x(8, 8, 0x18),                # 20 vt+0x18 = buffer
            blr(8),                           # 24
            mov_xr(2, 0),                     # 28 x2 = buffer
            sub_xi(0, 20, 0x10),              # 2C x0 = mgr3
            movz_w(1, 0x4E),                  # 30
            mov_wr(3, 21),                    # 34 w3 = length
            movz_w(4, 0),                     # 38 w4 = 0
            bl(p + 0x3C, 0x1CD8014),          # 3C loopback push
            b(p + 0x40, out),                 # 40
            b(p + 0x44, 0x108C28C)]           # 44
at_self = pc
r, pc = cave('PLEDGE_SELF', pc, c_self)
recs['PLEDGE_SELF'] = r + [hook(0x108C24C, b(0x108C24C, at_self), 'b #0x108c28c')]
pc = align16(pc)

assert pc <= CAVE_HI, hex(pc)

# ---------------- checks ----------------
errs = []
# 1. data words that must hold
ROUTE = {0x4D: (0x4C4B3B0 + 8 * 0x4D, 0x02), 0x4E: (0x4C4B3B0 + 8 * 0x4E, 0x00)}
for t, (a, want) in ROUTE.items():
    got = RO[a - RO_BASE]
    print('routing byte type 0x%X at 0x%X = 0x%02X' % (t, a, got))
    if got != want: errs.append('routing %x' % t)
for a, exp in [(0x10878D0, 'cmp w8, #6'), (0x1094B8C, 'cmp w8, #6'), (0x1094B00, 'ldrb w8, [x8, #0xbda]'),
               (0x1087708, 'adrp x23, #0x5b3c000'), (0x108770C, 'add x23, x23, #0xe08'),
               (0x1087700, 'sub sp, sp, #0x430'), (0x10877C8, 'ldr x8, [sp, #0x208]'),
               (0x108783C, 'ldr x8, [x23]'), (0x1087840, 'strb w25, [x19, #0x77c]'), (0x1087724, 'mov w25, #1'),
               (0x10878DC, 'mov x19, x0'), (0x10878B4, 'stp x20, x19, [sp, #0x30]'),
               (0x108798C, 'add x0, x19, #0x548'), (0x1087998, 'add sp, sp, #0x210'),
               (0x108A848, 'mov w19, w2'), (0x108A85C, 'mov x20, x0'), (0x108A888, 'ldr x23, [x23]'),
               (0x108A94C, 'blr x8'), (0x108A960, 'mov x3, x0'), (0x108A968, 'cmp x9, x23'),
               (0x108A998, 'add sp, sp, #0x2d0'), (0x11448E0, 'add x0, x9, #0x10'), (0x11448F4, 'bl #0x108a820'),
               (0x1097EB8, 'ldr x4, [x8, #0x40]'), (0x108CA5C, 'mov w8, #3'), (0x108CA7C, 'bl #0x1097e50'),
               (0x1085BBC, 'ldr x8, [x8, #0x68]'), (0x1094B6C, 'bl #0x108c520'), (0x1094D70, 'bl #0x108cb00'),
               (0x10921B8, 'mov w25, w0'), (0x108C230, 'ldr x8, [x20, #0x10]!'), (0x108C220, 'mov w21, w0'),
               (0x108C278, 'mov x0, x20'), (0x108C284, 'mov w4, wzr'), (0x108C288, 'bl #0x1cd8014'), (0x108C248, 'blr x8'), (0x114F370, 'ldr x8, [x20]'), (0x108C1CC, 'sturb wzr, [x29, #-0x30]')]:
    if dis_at(a) != exp: errs.append('%x: "%s" != "%s"' % (a, dis_at(a), exp))
# 2. no text reference to the cave range (adrp page 0x563E000 + add/ldr into 0x563E980..0x563EAFF)
w = array.array('I'); w.frombytes(TXT[:len(TXT) // 4 * 4])
hits = []
for i, x in enumerate(w):
    if (x & 0x9F000000) == 0x90000000:
        imm = (((x >> 5) & 0x7FFFF) << 2) | ((x >> 29) & 3)
        if imm & (1 << 20): imm -= 1 << 21
        if ((i * 4) >> 12 << 12) + (imm << 12) == 0x563E000:
            hits.append(i * 4)
refd = []
for a in hits:
    for j in range(1, 6):
        y = w[a // 4 + j]
        if ((y >> 5) & 31) != (w[a // 4] & 31): continue
        off = None
        if (y & 0xFF800000) == 0x91000000: off = (y >> 10) & 0xFFF
        elif (y & 0xFFC00000) in (0xF9400000, 0xF9000000): off = ((y >> 10) & 0xFFF) * 8
        elif (y & 0xFFC00000) in (0xB9400000, 0xB9000000): off = ((y >> 10) & 0xFFF) * 4
        elif (y & 0xFFC00000) in (0x39400000, 0x39000000): off = (y >> 10) & 0xFFF
        if off is not None:
            if 0x563E000 + off >= CAVE_LO and 0x563E000 + off < CAVE_HI: refd.append((a, off))
            break
print('text adrp to page 0x563E000: %d sites; into 0x%X..0x%X: %s' % (len(hits), CAVE_LO, CAVE_HI - 1, refd or 'none'))
if refd: errs.append('cave range referenced')


# 3. scratch registers dead at every branch target (written / clobbered before read)
def canon(r): return ('x' if r[0] in 'xw' else r[0]) + r[1:]


def first_use(a, reg, n=60):
    seen = set()
    for _ in range(n):
        if a in seen: return 'loop'
        seen.add(a)
        i = next(md.disasm(TXT[a:a + 4], a))
        rd, wt = i.regs_access()
        if reg in {canon(i.reg_name(r)) for r in rd}: return 'READ at %x (%s %s)' % (a, i.mnemonic, i.op_str)
        if reg in {canon(i.reg_name(r)) for r in wt}: return 'written at %x' % a
        if i.mnemonic in ('bl', 'blr'): return 'clobbered by call at %x' % a
        if i.mnemonic in ('ret', 'retab'): return 'return at %x' % a
        if i.mnemonic == 'b': a = i.operands[0].imm; continue
        a += 4
    return 'undecided'


for t, regs in [(0x10878D8, 'x9'), (0x1087998, 'x9'), (0x108A998, 'x8'), (0x108A954, 'x8'),
                (0x108783C, 'x9'), (0x10877C4, 'x8 x9'), (0x1094B08, 'x9'), (0x1094E00, 'x9'),
                (0x1094B94, 'x9'), (0x108C28C, 'x8 x9')]:
    for reg in regs.split():
        r = first_use(t, reg)
        print('%s after 0x%x: %s' % (reg, t, r))
        if r.startswith('READ') or r == 'undecided': errs.append('%s live at %x' % (reg, t))
# x0 at 0x10878D4 is still gl (nothing writes x0 between the entry and the hook)
for a in range(0x10878A0, 0x10878D4, 4):
    i = next(md.disasm(TXT[a:a + 4], a))
    if 'x0' in {canon(i.reg_name(r)) for r in i.regs_access()[1]}: errs.append('x0 written at %x' % a)

print('\n'.join(listing))
print('caves 0x%X..0x%X (%d bytes incl. alignment)' % (CAVE_LO, pc, pc - CAVE_LO))
for n_, s, e in ranges: print('  %-18s 0x%X..0x%X' % (n_, s, e - 1))
if errs:
    print('ERRORS:\n' + '\n'.join(errs))
    raise SystemExit(1)
print('all originals and context words match the binary')

# ---------------- write ritual_live.py ----------------
GROUPS = [
    ('RITUAL_LAYOUT', 'host builds the layout (offline path), guests clear their manager (gl+0x77C kept)'),
    ('RITUAL_PUSH', 'host broadcasts gl+0x548 as 0x4D right after building (0x108A820 with id -2 -> vt+0x40)'),
    ('RITUAL_READ', '0x4D read from anyone; in LAN a 0x4D with 0 records does not wipe the layout'),
    ('PLEDGE_REQUEST', 'kind-0 pledge request to everybody (incl. own self link)'),
    ('PLEDGE_DECIDE', 'kind 0 decided by offline or host (0x108C520 applies + broadcasts kind 3); guests drop'),
    ('PLEDGE_RESULT', 'kind 3 applied by guests; host drops its own echo'),
    ('PLEDGE_KILL', 'OPTIONAL: kill-steal decision 0x108C520 only on the host in LAN'),
    ('PLEDGE_SELF', 'OPTIONAL: host also loops its own 0x4E request back (only if 0x1094AD8 never sees it)'),
    ('RITUAL_HOSTSKIP', 'OPTIONAL alternative to the empty filter: host never reads 0x4D (queue not drained)'),
]
out = ['"""Live patch groups for Ritual Sites (Shelter, message 0x4D) and pledge pillars (NameList, message 0x4E):',
       '(offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory. Cave records have orig',
       '"00000000" (zero padding past the ro file end); this file uses main+0x%X..0x%X.' % (CAVE_LO, pc - 1),
       'Generated by ritual_gen.py (design, capstone listings, original-word and liveness checks there; reasoning in',
       'ritual_patch_notes.md). Within a group the caves come first and the hook that makes it live comes last.',
       'Not live-tested."""', '']
for g, title in GROUPS:
    out.append('%s = [  # %s' % (g, title))
    for off, o, nw, c in recs[g]:
        out.append('    (0x%X, "%s", "%s", %s),' % (off, o, nw, c))
    out.append(']')
    out.append('')
out.append('# Recommended order. RITUAL_* work alone; PLEDGE_* need the layout (RITUAL_*) on every game.')
out.append('ORDER = [RITUAL_LAYOUT, RITUAL_PUSH, RITUAL_READ, PLEDGE_REQUEST, PLEDGE_DECIDE, PLEDGE_RESULT]')
out.append('OPTIONAL = [PLEDGE_KILL, PLEDGE_SELF, RITUAL_HOSTSKIP]')
open(os.path.join(HERE, 'ritual_live.py'), 'w', newline='\n').write('\n'.join(out) + '\n')
print('ritual_live.py written,', sum(len(recs[g]) for g, _ in GROUPS), 'records')
