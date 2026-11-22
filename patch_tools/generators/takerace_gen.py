"""takerace_gen.py: v3.9.21 OPTION, not in any build. TAKERACE: the authority decides who takes a shared pay-once
action-menu object (large Flame corpse, kin circle), in arrival order, as the server did online (layout_notes 2.4 /
2.5). Static generator, allocated with Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed
rows). Writes takerace_live.py.   python takerace_gen.py [--dry]      (from diag/net)

Today (v3.9.20) every game grants its own player's kind-1 press at once (KIN_PRESS), and TakenShare (type 12) tells
the others afterwards. Two players pressing the same large corpse within one network delay are BOTH granted.
TAKERACE keeps the press path and every log line as it is, and puts one question in front of the grant:
- GRANT (hook 0x11A49A4, the kind-1 server branch's `bl 0x11A36C0`, reached only after all stock checks passed):
    replay byte 3 / 4 (set by FRAME, below)           -> stock grant / stock deny 0x11A3A20
    +0xBDA set (offline / server mode), mode 0        -> stock grant (today)
    per-player kind without holder (vt+0x48 true and
    vt+0x40 false: small corpse, forge, ...)           -> stock grant (today)
    mode 1 (this game is the authority): a claim by ANOTHER player for this handle younger than CLAIM frames
        -> stock deny (own refusal counted for the assist's log); else claim it and stock grant
    mode 2 (a guest with a ready authority): the request (data {kind, player, handle} and the 16 raw message bytes)
        is parked in TRBOX and the grant is skipped; the press itself (prompt, pending entry, the player's action)
        already ran in 0x11A2914 / 0x11A2F60 and is untouched. A busy park slot -> stock grant (today).
- FRAME (hook 0x11A1EE4, the action-menu manager's per-frame update, right after it polled the 0x74 messages):
    frame counter +1; a park answered by the assist (verdict 3 / 4), or one older than BACKSTOP frames, is REPLAYED:
    the receiver 0x11A451C is called with a functor {mgr} and a holder of the stock class 0x56F9D78 holding the
    parked bytes, so the stock kind-1 branch runs again (requester lookup, every stock check) and GRANT does what the
    verdict says. The authority (mode 1) decides the asks the assist put in the ring, in ring (= arrival) order:
    claimed by another player within CLAIM frames -> refused (why 1); info+0x470 used -> refused (2); a holder
    -> refused (3); not found -> granted (4); else claimed and granted (0).
The assist (assist_v436_takerace.diff, side type 25) sets the mode, carries asks / answers, answers 3 itself after
1.5 s without the authority's answer (today's way: the press is granted here), and logs every step "takerace: ...".
With mode 0 (old assist, offline, solo, no authority heard) both caves only add the frame count."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'takerace_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
RET = 0xD65F03C0
OFFL = 0x5B65C20                  # cell: object with +0xBDA (offline / server mode), as the receiver at 0x11A46EC
HVT = 0x56F9D78                   # the 0x74 holder class (+8 data pointer, +0x10 16 raw bytes), 0x11A1E0C
G_ASSET, G_CHR, G_NET, G_MODE = 0x59DFF40, 0x59DFE68, 0x59DFEC8, 0x59DFEF8   # the receiver's four global cells
RECV, GRANT_FN, DENY_FN, DRIVER, LOOKUP = 0x11A451C, 0x11A36C0, 0x11A3A20, 0x11A22E0, 0xFEC6E0
S_GRANT, S_FRAME = 0x11A49A4, 0x11A1EE4
CLAIM = 60                        # frames a claim refuses others (2 s at 30 fps): covers TakenShare's propagation
BACKSTOP = 150                    # frames a park waits when no assist answers at all (5 s at 30 fps)
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


def chk(w, text, pc=0x10000):
    got = C.dis1(pc, w)
    assert got == text, '%08x: %s, expected %s' % (w, got, text)
    return w


# encoders cave_lib lacks (each checked against capstone once)
def add_uxtw4(rd, rn, rm):        # add xd, xn, wm, uxtw #4
    return 0x8B200000 | (C.R(rm) << 16) | (2 << 13) | (4 << 10) | (C.R(rn) << 5) | C.R(rd)


def cmn_m1(rn):                   # cmn wn, #1
    return 0x3100001F | (1 << 10) | (C.R(rn) << 5)


def and7(rd, rn):                 # and wd, wn, #7
    return 0x12000800 | (C.R(rn) << 5) | C.R(rd)


def sub_wr(rd, rn, rm):           # sub wd, wn, wm
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


chk(add_uxtw4(15, 20, 9), 'add x15, x20, w9, uxtw #4')
chk(cmn_m1(10), 'cmn w10, #1')
chk(and7(14, 14), 'and w14, w14, #7')
chk(sub_wr(9, 13, 9), 'sub w9, w13, w9')
chk(RET, 'ret')


def bl_callers(target):
    out = []
    for i, w in enumerate(W):
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if 4 * (i + imm) == target:
                out.append(4 * i)
    return out


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            t = pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000 or (w & 0x3B000000) == 0x18000000:
            imm = (w >> 5) & 0x7FFFF
            t = pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
        elif (w & 0x7E000000) == 0x36000000:
            imm = (w >> 5) & 0x3FFF
            t = pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
        elif (w & 0x9F000000) == 0x10000000:
            d = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
            t = pc + (d - (1 << 21) if d & (1 << 20) else d)
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


def data_q(a):
    return struct.unpack_from('<Q', C.DATA, a - C.DATA_BASE)[0]


# ================================================================ code facts [V]
for a, t in (
        # receiver 0x11A451C: functor +8 = mgr, +0x10 = holder; holder +8 = data {kind, player, handle}; sender x1
        (0x11A4544, 'ldr x9, [x9, #0xf40]'), (0x11A4548, 'ldr x0, [x9]'), (0x11A454C, 'cbz x0, #0x11a49e0'),
        (0x11A4550, 'ldp x20, x21, [x8, #8]'), (0x11A4554, 'mov x24, x1'), (0x11A4558, 'ldr x23, [x21, #8]'),
        (0x11A455C, 'add x1, x23, #8'), (0x11A4560, 'bl #0xfec6e0'), (0x11A4570, 'ldr x8, [x8, #0xe68]'),
        (0x11A4684, 'ldr x10, [x10, #0xec8]'), (0x11A46B8, 'ldr x11, [x24]'), (0x11A46C0, 'cset w10, eq'),
        (0x11A46E4, 'cmp w9, #1'), (0x11A46F0, 'ldr x8, [x8, #0xc20]'), (0x11A46F4, 'ldrb w8, [x8, #0xbda]'),
        # kind-1 server branch: the reply holder at sp is deserialized from the holder's raw bytes (+0x10 / +0x18)
        (0x11A4740, 'ldp x9, x8, [x21, #0x10]'), (0x11A4748, 'bl #0x11a43c0'), (0x11A4750, 'ldr x24, [x24, #0xef8]'),
        (0x11A4970, 'mov x1, x21'), (0x11A4974, 'ldr x8, [x8, #0x28]'),
        # the grant / deny calls (x0 mgr, x1 processor, x2 reply holder, x3 requester chr, x4 asset)
        (0x11A4990, 'mov x2, sp'), (0x11A4994, 'mov x0, x20'), (0x11A4998, 'mov x1, x23'), (0x11A499C, 'mov x3, x22'),
        (0x11A49A0, 'mov x4, x19'), (S_GRANT, 'bl #0x11a36c0'), (0x11A49A8, 'b #0x11a49c4'),
        (0x11A49AC, 'mov x2, sp'), (0x11A49C0, 'bl #0x11a3a20'), (0x11A49C4, 'ldp x20, x19, [sp, #0xe0]'),
        # grant: pending entry {kind, player, handle} matched by data+4 / +8; vt+0x48 / vt+0x40 take x0 only
        (0x11A36E0, 'ldp x24, x8, [x0, #0x80]'), (0x11A3700, 'ldr x10, [x23, #8]'), (0x11A3704, 'ldp w9, w10, [x10, #4]'),
        (0x11A382C, 'mov x0, x20'), (0x11A3830, 'ldr x8, [x8, #0x48]'), (0x11A383C, 'ldr x8, [x19, #0x10]'),
        (0x11A3840, 'strb w23, [x8, #0x470]'), (0x11A3848, 'mov x0, x20'), (0x11A384C, 'ldr x8, [x8, #0x40]'),
        # the press appends its pending entry after sending (prompt and action already ran in the driver)
        (0x11A2FD8, 'bl #0x11a32a8'), (0x11A2FFC, 'str x8, [x22, #0x88]'), (0x11A2914, 'bl #0x11a2f60'),
        # per-frame update 0x11A1D20 (x19 = mgr): the 0x74 poll with functor {0x56F9DB0, mgr} and holder 0x56F9D78
        (0x11A1D3C, 'mov x19, x0'), (0x11A1E0C, 'adrp x8, #0x56f9000'), (0x11A1E10, 'add x8, x8, #0xd78'),
        (0x11A1E2C, 'mov w1, #0x74'), (0x11A1E30, 'mov w3, #0x10'), (0x11A1E50, 'stp x9, x19, [sp]'),
        (0x11A1E70, 'ldr x9, [x9, #0x68]'), (0x11A1EE0, 'mov x0, x19'), (S_FRAME, 'bl #0x11a22e0'),
        (0x11A1EE8, 'mov x0, x19'), (0x11A1F00, 'b #0x11a29e0'),
        # review 2.6 R1: the poll's holder is 0x50 bytes: +0x20 = bit stream {[0x5A09A70] + 0x10, 0, ...}, +0x48 0
        (0x11A1E18, 'adrp x9, #0x5a09000'), (0x11A1E1C, 'ldr x9, [x9, #0xa70]'), (0x11A1E38, 'add x9, x9, #0x10'),
        (0x11A1E44, 'stp x9, xzr, [sp, #0x50]'), (0x11A1E34, 'stp xzr, xzr, [sp, #0x60]'),
        (0x11A1E3C, 'stur xzr, [sp, #0x6d]'), (0x11A1E28, 'str wzr, [sp, #0x78]'), (0x11A1E24, 'add x2, x8, #0x10'),
        # the deserializer (holder vt+0x10): bit stream at +0x20 set up over +0x10, data written to [+8]
        (0x11A43E0, 'ldr x9, [x19, #0x20]!'), (0x11A43F4, 'stp x8, x10, [x19, #8]'), (0x11A43FC, 'ldur x20, [x19, #-0x18]'),
        (0x11A4488, 'str x9, [x20]'), (0x11A448C, 'str w8, [x20, #8]'), (0x11A4480, 'mov w0, #1'),
        # the flame processor's vt+0x28 0x119E3CC reads the holder's bit stream (why a short holder crashed)
        (0x119E3E8, 'ldr x8, [x19, #0x20]!'), (0x119E3F0, 'ldr x8, [x8, #0x78]'),
        # the stage pointer cell (as the grant reads it)
        (0x11A3750, 'adrp x24, #0x5b3c000'), (0x11A3754, 'add x24, x24, #0xdf8'), (0x11A3758, 'ldr x0, [x24]')):
    stock(a, t)
assert data_q(0x56F98C8 + 0x28) == 0x119E3CC                # flame (and 99500 / 315211 / 99330) vt+0x28
assert bl_callers(0x11A1D20) == [0x182F2C0]                # the manager update: one caller, the frame task 0x182E560
assert bl_callers(S_GRANT + 4) == [] and targets_in(S_GRANT, S_GRANT + 4) == []
assert targets_in(S_FRAME, S_FRAME + 4) == []
assert data_q(HVT + 0x10) == 0x11A43C0 and data_q(HVT + 0x18) == 0x11A44AC and data_q(HVT + 0x20) == 0x11A44B4
assert data_q(0x56F9DB0 + 0x30) == RECV                    # the functor's call slot is the receiver
for a in range(0x11A1D20, 0x11A1F20, 4):
    assert a not in C.SHIPPED
for a in (S_GRANT, S_FRAME):
    assert a not in C.SHIPPED
listing.append('receiver 0x11A451C is reached only through the functor 0x56F9DB0 (vt+0x30); the update 0x11A1D20 '
               'polls type 0x74 at 0x11A1E78 and calls the prompt driver at 0x11A1EE4 every frame')

others = C.live_records(exclude=(OUT,))
used_pads = set()


def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others or x in used_pads for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                used_pads.update(range(a, a + 4 * n))
                return a
    return None


PAD_G = find_pad(S_GRANT, 3)
PAD_F = find_pad(S_FRAME, 3)
assert PAD_G and PAD_F
for p in (PAD_G, PAD_F):
    listing.append('trampoline padding 0x%X..0x%X after `%s` (zero, before a pacibsp, unreferenced, free)' % (
        p, p + 12, dis(p - 4)))

g = C.Gen('takerace_gen', out=OUT, dry=True)
BOX_SIZE = 0x1B0
G_WORDS, F_WORDS = 128, 200
BOX = g.alloc('TRBOX', 'FAR_DATA', BOX_SIZE, 'TAKERACE box (layout in takerace_live.py)')
TG = g.alloc('TRGRANT', 'FAR_CODE', G_WORDS * 4, 'TAKERACE grant decision at 0x11A49A4')
TF = g.alloc('TRFRAME', 'FAR_CODE', F_WORDS * 4, 'TAKERACE per-frame replay / authority decisions at 0x11A1EE4')

# TRBOX layout (offsets). a = assist writes, g = game (caves) writes.
# Review 2.6 R1: the replay holder is a FULL stock 0x74 holder (0x50 bytes, as 0x11A1DE8..0x11A1E44 builds it):
# +0 vt 0x56F9D78, +8 data ptr, +0x10 16 raw bytes, +0x20 the bit-stream object {vt [0x5A09A70]+0x10, 0...}; the
# flame processor's vt+0x28 (0x119E3CC) calls [holder+0x20]->vt+0x78, so a 0x20-byte holder crashed there.
M_MODE, M_REPLAY, M_ASK_NEXT, M_CLAIM_NEXT, M_FRAME, M_ZERO = 0x00, 0x01, 0x02, 0x03, 0x04, 0x08
P_STATE, P_VERDICT, P_WHY, P_ID, P_FRAME0, P_HANDLE = 0x10, 0x11, 0x12, 0x14, 0x18, 0x1C
P_HOLDER, P_RAW, P_BITS, P_DATA, P_DONE = 0x20, 0x30, 0x40, 0x70, 0x7C
P_MGR, P_STAGE, P_ROUND, P_DROPPED = 0x80, 0x88, 0x90, 0x94
O_COUNT, O_HANDLE, O_WHO, O_NO = 0x98, 0x9C, 0xA0, 0xA4
CLAIMS, ASKS = 0xB0, 0x130                 # 8 x 16 each
HOLDER_SIZE = 0x50
assert P_HOLDER + HOLDER_SIZE == P_DATA and ASKS + 8 * 16 == BOX_SIZE
STAGE_CELL, P_ROUND_OFF = 0x5B3CDF8, 0xB8   # stage pointer (0x11A3750) and its round (dusk_lan P_ROUND)
BITS_CELL, DESER = 0x5A09A70, 0x11A43C0     # bit-stream class cell (0x11A1E18) and the holder's vt+0x10
LAYOUT = """TRBOX layout (FAR_DATA; a = assist, g = game):
  +0x00 u8 mode a: 0 off (today), 1 authority, 2 guest with a ready authority | +0x01 u8 replay g: 0 / 3 / 4
  +0x02 u8 next ask slot g | +0x03 u8 next claim slot g | +0x04 u32 frame g (+1 per action-menu update)
  +0x08 u64 0: the replay's sender word
  park (guest): +0x10 u8 state (g 1 parked, a 2 answered, g 0 replayed) | +0x11 u8 verdict a (3 grant / 4 refuse)
    | +0x12 u8 why (a 0 the authority answered, a 1 timeout 1.5 s, g 2 backstop, g 3 stage / round changed)
    | +0x14 u32 park id g | +0x18 u32 frame parked g | +0x1C u32 handle g
    | +0x20 holder, 0x50 bytes, the stock 0x74 holder: {u64 vt 0x56F9D78, u64 data ptr, 16 raw bytes, +0x20 bit
      stream {vt, 0..}} g (rebuilt and parsed by the stock 0x11A43C0 before each replay)
    | +0x70 data {u32 kind 1, u32 player no, u32 handle} g | +0x7C u32 replays done g | +0x80 u64 manager g
    | +0x88 u64 stage g | +0x90 u32 round g | +0x94 u32 parks dropped unreplayed (stage changed, bytes bad) g
  own refusals (authority): +0x98 u32 count g (written last) | +0x9C handle | +0xA0 by player | +0xA4 our player
  +0xB0 claims g: 8 x {u32 handle, u32 player no, u32 frame, u32 0}
  +0x130 asks: 8 x {u8 state (a 1 asked, g 2 decided, a 0 answered), u8 verdict g, u8 player no a, u8 why g,
                    u32 handle a, u32 ask id a, u32 who g (the player that has it, why 1 / 3)}"""


def restore_grant(a):
    a(C.ldr_x(20, 'sp', 0x40))
    a(C.ldp_x(4, 19, 'sp', 0x30))
    a(C.ldp_x(2, 3, 'sp', 0x20))
    a(C.ldp_x(0, 1, 'sp', 0x10))
    a(C.ldp_post(29, 30, 'sp', 0x50))


# ---------------------------------------------------------------- TRGRANT
# Entered by `bl` (via PAD_G) from 0x11A49A4: x0 mgr, x1 processor, x2 reply holder (sp of the receiver), x3 requester
# chr, x4 asset; x21 = the received holder (callee-saved in the receiver); x30 = 0x11A49A8 (`b` to the epilogue).
# It ends in a tail jump to the grant or the deny (x16: dead at a function entry), or returns (parked).
a = C.Asm(TG)
a(C.stp_pre(29, 30, 'sp', -0x50))
a(C.add_xi(29, 'sp', 0))
a(C.stp_x(0, 1, 'sp', 0x10))
a(C.stp_x(2, 3, 'sp', 0x20))
a(C.stp_x(4, 19, 'sp', 0x30))
a(C.str_x(20, 'sp', 0x40))
a(lambda pc, L: C.adrp(pc, 20, BOX))
a(C.add_xi(20, 20, C.lo12(BOX)))
a(C.ldrb(9, 20, M_REPLAY))
a(C.to(C.cbnz_w, 'w9', 'replay'))                           # a replay: the verdict decides
a(lambda pc, L: C.adrp(pc, 9, OFFL))
a(C.ldr_x(9, 9, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x9', 'grant'))
a(C.ldrb(9, 9, 0xBDA))
a(C.to(C.cbnz_w, 'w9', 'grant'))                            # offline / server mode: stock
a(C.ldrb(9, 20, M_MODE))
a(C.to(C.cbz_w, 'w9', 'grant'))                             # mode 0: today's way
a(C.ldr_x(0, 'sp', 0x18))
a(C.ldr_x(8, 0, 0))
a(C.ldr_x(8, 8, 0x48))
a(C.blr(8))
a(C.to(C.tbz, 'w0', 0, 'arb'))                              # vt+0x48 false: used up for everyone -> arbitrated
a(C.ldr_x(0, 'sp', 0x18))
a(C.ldr_x(8, 0, 0))
a(C.ldr_x(8, 8, 0x40))
a(C.blr(8))
a(C.to(C.tbz, 'w0', 0, 'grant'))                            # per player, no holder: stock (corpse, forge)
a.label('arb')
a(C.ldrb(9, 20, M_MODE))
a(C.cmp_wi('w9', 1))
a(C.to(C.beq, 'auth'))
a(C.cmp_wi('w9', 2))
a(C.to(C.bne, 'grant'))
# guest: park the request
a(C.ldr_x(10, 21, 8))                                       # the received holder's data {kind, player, handle}
a(C.ldrb(9, 20, P_STATE))
a(C.to(C.cbz_w, 'w9', 'park'))
a(C.ldr_w(9, 20, P_HANDLE))                                 # review 2.6 R4: a second press on the parked object
a(C.ldr_w(11, 10, 8))                                       # is denied (its pending entry goes); another object
a(C.cmp_wr('w9', 'w11'))                                    # while one waits goes today's way
a(C.to(C.beq, 'deny'))
a(C.to(C.b, 'grant'))
a.label('park')
a(C.ldr_x(11, 10, 0))
a(C.str_x(11, 20, P_DATA))
a(C.ldr_w(11, 10, 8))
a(C.str_w(11, 20, P_DATA + 8))
a(C.str_w(11, 20, P_HANDLE))
a(C.ldp_x(11, 12, 21, 0x10))                                # its 16 raw bytes (the replay parses them again)
a(C.stp_x(11, 12, 20, P_RAW))
a(C.ldr_x(11, 'sp', 0x10))
a(C.str_x(11, 20, P_MGR))
a(lambda pc, L: C.adrp(pc, 11, STAGE_CELL))                 # review 2.6 R2: the stage and round of the press
a(C.ldr_x(11, 11, C.lo12(STAGE_CELL)))
a(C.str_x(11, 20, P_STAGE))
a(C.movz_w(12, 0))
a(C.to(C.cbz_x, 'x11', 'nostage'))
a(C.ldr_w(12, 11, P_ROUND_OFF))
a.label('nostage')
a(C.str_w(12, 20, P_ROUND))
a(C.ldr_w(11, 20, M_FRAME))
a(C.str_w(11, 20, P_FRAME0))
a(C.ldr_w(11, 20, P_ID))
a(C.add_wi(11, 11, 1))
a(C.str_w(11, 20, P_ID))
a(C.strb('wzr', 20, P_VERDICT))
a(C.strb('wzr', 20, P_WHY))
a(C.movz_w(11, 1))
a(C.strb(11, 20, P_STATE))                                  # parked (written last)
restore_grant(a)
a(RET)                                                      # no grant now: the receiver goes on to its epilogue
# authority: the claims
a.label('auth')
a(C.ldr_x(10, 'sp', 0x20))
a(C.ldr_x(10, 10, 8))
a(C.ldr_w(11, 10, 4))                                       # requester player no
a(C.ldr_w(12, 10, 8))                                       # handle
a(C.ldr_w(13, 20, M_FRAME))
a(C.mov_x(15, 20))
a(C.movz_w(14, 8))
a.label('cl')
a(C.ldr_w(9, 15, CLAIMS))
a(C.cmp_wr('w9', 'w12'))
a(C.to(C.bne, 'cn'))
a(C.ldr_w(9, 15, CLAIMS + 4))
a(C.cmp_wr('w9', 'w11'))
a(C.to(C.beq, 'cn'))
a(C.ldr_w(9, 15, CLAIMS + 8))
a(sub_wr(9, 13, 9))
a(C.cmp_wi('w9', CLAIM))
a(C.to(C.blo, 'own_refused'))                               # another player was granted it CLAIM frames ago or less
a.label('cn')
a(C.add_xi(15, 15, 0x10))
a(C.sub_wi(14, 14, 1))
a(C.to(C.cbnz_w, 'w14', 'cl'))
a(C.ldrb(9, 20, M_CLAIM_NEXT))
a(C.add_wi(14, 9, 1))
a(and7(14, 14))
a(C.strb(14, 20, M_CLAIM_NEXT))
a(add_uxtw4(15, 20, 9))
a(C.str_w(12, 15, CLAIMS))
a(C.str_w(11, 15, CLAIMS + 4))
a(C.str_w(13, 15, CLAIMS + 8))
a(C.to(C.b, 'grant'))
a.label('own_refused')
a(C.str_w(12, 20, O_HANDLE))
a(C.ldr_w(9, 15, CLAIMS + 4))
a(C.str_w(9, 20, O_WHO))
a(C.str_w(11, 20, O_NO))
a(C.ldr_w(9, 20, O_COUNT))
a(C.add_wi(9, 9, 1))
a(C.str_w(9, 20, O_COUNT))
a(C.to(C.b, 'deny'))
a.label('replay')
a(C.cmp_wi('w9', 4))
a(C.to(C.beq, 'deny'))
a.label('grant')
restore_grant(a)
a.many(lambda pc, L: C.far_jump(pc, GRANT_FN))
a.label('deny')
restore_grant(a)
a.many(lambda pc, L: C.far_jump(pc, DENY_FN))
gw = a.words()
assert len(gw) <= G_WORDS, len(gw)
cave_g = g.cave('TRGRANT', TG, a)


# ---------------------------------------------------------------- TRFRAME
# Entered by `bl` (via PAD_F) from 0x11A1EE4: x0 = x19 = the action-menu manager, x30 = 0x11A1EE8. Ends with a tail
# jump to the prompt driver 0x11A22E0 (x0 = mgr, x30 restored), as the stock `bl` did.
def glob_ok(a, cell, lab):
    a(lambda pc, L, c=cell: C.adrp(pc, 9, c))
    a(C.ldr_x(9, 9, C.lo12(cell)))
    a(C.to(C.cbz_x, 'x9', lab))
    a(C.ldr_x(9, 9, 0))
    a(C.to(C.cbz_x, 'x9', lab))


f = C.Asm(TF)
f(C.stp_pre(29, 30, 'sp', -0x60))
f(C.add_xi(29, 'sp', 0))
f(C.stp_x(19, 20, 'sp', 0x10))
f(C.stp_x(21, 22, 'sp', 0x20))
f(C.mov_x(19, 0))
f(lambda pc, L: C.adrp(pc, 20, BOX))
f(C.add_xi(20, 20, C.lo12(BOX)))
f(C.ldr_w(9, 20, M_FRAME))
f(C.add_wi(9, 9, 1))
f(C.str_w(9, 20, M_FRAME))
# guest park (any mode: a lost authority or a stopped assist never keeps it)
f(C.ldrb(9, 20, P_STATE))
f(C.to(C.cbz_w, 'w9', 'asks'))
f(C.ldr_x(10, 20, P_MGR))
f(C.cmp_xr('x10', 'x19'))
f(C.to(C.bne, 'drop'))                                      # another manager (a new match): forget it
f(C.cmp_wi('w9', 2))
f(C.to(C.beq, 'answered'))
f(C.ldr_w(10, 20, M_FRAME))
f(C.ldr_w(11, 20, P_FRAME0))
f(sub_wr(10, 10, 11))
f(C.cmp_wi('w10', BACKSTOP))
f(C.to(C.blo, 'asks'))                                      # still waiting for the assist
f(C.movz_w(9, 3))
f(C.strb(9, 20, P_VERDICT))
f(C.movz_w(9, 2))
f(C.strb(9, 20, P_WHY))                                     # backstop: granted here, today's way
f.label('answered')
for cell in (G_ASSET, G_CHR, G_NET, G_MODE):                # the receiver aborts on any of them null: wait
    glob_ok(f, cell, 'asks')
# review 2.6 R2: the press belongs to its stage and round. Another stage (map unloaded, a new match): dropped
# without a replay. The same stage, another round (the phase reset ran): replayed as refused, so its pending
# entry goes and nothing is granted for a press of the last round.
f(lambda pc, L: C.adrp(pc, 9, STAGE_CELL))
f(C.ldr_x(9, 9, C.lo12(STAGE_CELL)))
f(C.ldr_x(10, 20, P_STAGE))
f(C.cmp_xr('x9', 'x10'))
f(C.to(C.bne, 'stale'))
f(C.to(C.cbz_x, 'x9', 'stale'))
f(C.ldr_w(10, 9, P_ROUND_OFF))
f(C.ldr_w(11, 20, P_ROUND))
f(C.cmp_wr('w10', 'w11'))
f(C.to(C.beq, 'build'))
f(C.movz_w(9, 4))
f(C.strb(9, 20, P_VERDICT))
f(C.movz_w(9, 3))
f(C.strb(9, 20, P_WHY))                                     # counted in replays done (why 3), not dropped
# review 2.6 R1: a full stock holder, parsed by the stock deserializer as the poll does (0x11A1DE8..0x11A1E78)
f.label('build')
f(lambda pc, L: C.adrp(pc, 9, BITS_CELL))
f(C.ldr_x(9, 9, C.lo12(BITS_CELL)))
f(C.to(C.cbz_x, 'x9', 'stale'))
f(C.add_xi(9, 9, 0x10))
f(C.str_x(9, 20, P_BITS))
for off in range(P_BITS + 8, P_HOLDER + HOLDER_SIZE, 8):
    f(C.str_x('xzr', 20, off))
f(lambda pc, L: C.adrp(pc, 9, HVT))
f(C.add_xi(9, 9, C.lo12(HVT)))
f(C.str_x(9, 20, P_HOLDER))
f(C.add_xi(9, 20, P_DATA))
f(C.str_x(9, 20, P_HOLDER + 8))
f(C.add_xi(0, 20, P_HOLDER))
f(C.movz_w(1, 0x10))
f.many(lambda pc, L: C.far_call(pc, DESER))                 # data {kind, player, handle} from the raw bytes
f(C.to(C.tbz, 'w0', 0, 'stale'))                            # bytes that do not parse: dropped
f(C.ldrb(9, 20, P_VERDICT))
f(C.cmp_wi('w9', 4))
f(C.to(C.beq, 'v4'))
f(C.movz_w(9, 3))
f.label('v4')
f(C.strb(9, 20, M_REPLAY))
f(C.str_x('xzr', 'sp', 0x30))                               # functor {vt unused, +8 mgr, +0x10 holder}
f(C.str_x(19, 'sp', 0x38))
f(C.add_xi(9, 20, P_HOLDER))
f(C.str_x(9, 'sp', 0x40))
f(C.add_xi(0, 'sp', 0x30))
f(C.add_xi(1, 20, M_ZERO))                                  # sender word 0 (read only for kinds 3/4/5)
f.many(lambda pc, L: C.far_call(pc, RECV))                  # the stock kind-1 branch runs again
f(C.strb('wzr', 20, M_REPLAY))
f(C.ldr_w(9, 20, P_DONE))
f(C.add_wi(9, 9, 1))
f(C.str_w(9, 20, P_DONE))
f(C.to(C.b, 'drop'))
f.label('stale')
f(C.ldr_w(9, 20, P_DROPPED))
f(C.add_wi(9, 9, 1))
f(C.str_w(9, 20, P_DROPPED))
f.label('drop')
f(C.strb('wzr', 20, P_STATE))
# authority: the asks, in ring order
f.label('asks')
f(C.ldrb(9, 20, M_MODE))
f(C.cmp_wi('w9', 1))
f(C.to(C.bne, 'out'))
f.label('aloop')
f(C.ldrb(9, 20, M_ASK_NEXT))
f(add_uxtw4(21, 20, 9))
f(C.ldrb(10, 21, ASKS))
f(C.cmp_wi('w10', 1))
f(C.to(C.bne, 'out'))
f(C.add_wi(9, 9, 1))
f(and7(9, 9))
f(C.strb(9, 20, M_ASK_NEXT))
f(C.add_xi(21, 21, ASKS))                                   # x21 = the ask
f(C.ldrb(11, 21, 2))
f(C.ldr_w(12, 21, 4))
f(C.ldr_w(13, 20, M_FRAME))
f(C.mov_x(15, 20))
f(C.movz_w(14, 8))
f.label('cl')
f(C.ldr_w(9, 15, CLAIMS))
f(C.cmp_wr('w9', 'w12'))
f(C.to(C.bne, 'cn'))
f(C.ldr_w(9, 15, CLAIMS + 4))
f(C.cmp_wr('w9', 'w11'))
f(C.to(C.beq, 'cn'))
f(C.ldr_w(9, 15, CLAIMS + 8))
f(sub_wr(9, 13, 9))
f(C.cmp_wi('w9', CLAIM))
f(C.to(C.bhs, 'cn'))
f(C.ldr_w(9, 15, CLAIMS + 4))
f(C.str_w(9, 21, 0xC))
f(C.movz_w(10, 1))
f(C.to(C.b, 'refuse'))                                      # claimed by another player
f.label('cn')
f(C.add_xi(15, 15, 0x10))
f(C.sub_wi(14, 14, 1))
f(C.to(C.cbnz_w, 'w14', 'cl'))
f(lambda pc, L: C.adrp(pc, 9, G_ASSET))
f(C.ldr_x(9, 9, C.lo12(G_ASSET)))
f(C.to(C.cbz_x, 'x9', 'nf'))
f(C.ldr_x(0, 9, 0))
f(C.to(C.cbz_x, 'x0', 'nf'))
f(C.add_xi(1, 21, 4))
f.many(lambda pc, L: C.far_call(pc, LOOKUP))                # the asset of that handle, as the receiver head
f(C.to(C.cbz_x, 'x0', 'nf'))
f(C.ldr_x(9, 0, 0x10))
f(C.to(C.cbz_x, 'x9', 'nf'))
f(C.ldrb(10, 9, 0x470))
f(C.to(C.cbnz_w, 'w10', 'used'))
f(C.ldr_w(10, 9, 0x460))
f(cmn_m1('w10'))
f(C.to(C.bne, 'held'))
f(C.movz_w(10, 0))
f(C.to(C.b, 'give'))
f.label('nf')
f(C.movz_w(10, 4))
f(C.to(C.b, 'give'))
f.label('used')
f(C.str_w('wzr', 21, 0xC))
f(C.movz_w(10, 2))
f(C.to(C.b, 'refuse'))
f.label('held')
f(C.str_w(10, 21, 0xC))
f(C.movz_w(10, 3))
f(C.to(C.b, 'refuse'))
f.label('give')
f(C.strb(10, 21, 3))
f(C.ldrb(11, 21, 2))
f(C.ldr_w(12, 21, 4))
f(C.ldr_w(13, 20, M_FRAME))
f(C.ldrb(9, 20, M_CLAIM_NEXT))
f(C.add_wi(14, 9, 1))
f(and7(14, 14))
f(C.strb(14, 20, M_CLAIM_NEXT))
f(add_uxtw4(15, 20, 9))
f(C.str_w(12, 15, CLAIMS))
f(C.str_w(11, 15, CLAIMS + 4))
f(C.str_w(13, 15, CLAIMS + 8))
f(C.movz_w(9, 3))
f(C.strb(9, 21, 1))
f(C.to(C.b, 'decided'))
f.label('refuse')
f(C.strb(10, 21, 3))
f(C.movz_w(9, 4))
f(C.strb(9, 21, 1))
f.label('decided')
f(C.movz_w(9, 2))
f(C.strb(9, 21, 0))                                         # decided (written last)
f(C.to(C.b, 'aloop'))
f.label('out')
f(C.mov_x(0, 19))
f(C.ldp_x(21, 22, 'sp', 0x20))
f(C.ldp_x(19, 20, 'sp', 0x10))
f(C.ldp_post(29, 30, 'sp', 0x60))
f.many(lambda pc, L: C.far_jump(pc, DRIVER))
fw = f.words()
assert len(fw) <= F_WORDS, len(fw)
cave_f = g.cave('TRFRAME', TF, f)

tramp = [g.text_patch(PAD_G + 4 * k, 'udf #0', w, 'trampoline -> TRGRANT 0x%X (x16: a bl site)' % TG)
         for k, w in enumerate(C.far_jump(PAD_G, TG))]
tramp += [g.text_patch(PAD_F + 4 * k, 'udf #0', w, 'trampoline -> TRFRAME 0x%X (x16: a bl site)' % TF)
          for k, w in enumerate(C.far_jump(PAD_F, TF))]
hooks = [g.text_patch(S_GRANT, 'bl #0x11a36c0', C.bl(S_GRANT, PAD_G), 'TAKERACE grant decision'),
         g.text_patch(S_FRAME, 'bl #0x11a22e0', C.bl(S_FRAME, PAD_F), 'TAKERACE per-frame replay / asks')]

groups = {'TAKERACE_CAVE': cave_g + cave_f + tramp, 'TAKERACE': hooks}
order = ['TAKERACE_CAVE', 'TAKERACE']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('TRGRANT %d / %d words, TRFRAME %d / %d words' % (len(gw), G_WORDS, len(fw), F_WORDS))
print('assist: TR_SITE 0x%X, stock word %08X (`bl #0x11a36c0`), hook word %08X' % (
    S_GRANT, C.text_word(S_GRANT), C.bl(S_GRANT, PAD_G)))
print('registry rows (lead adds):')
print('| takerace_gen | TRBOX | 0x%X..0x%X | TAKERACE box: mode, park, claims, asks (takerace_live.py LAYOUT) (FAR_DATA) |' % (
    BOX, BOX + BOX_SIZE))
print('| takerace_gen | TRGRANT | 0x%X..0x%X | TAKERACE 0x11A49A4: guest parks a pay-once grant, authority claims; '
      'trampoline 0x%X..0x%X |' % (TG, TG + G_WORDS * 4, PAD_G, PAD_G + 12))
print('| takerace_gen | TRFRAME | 0x%X..0x%X | TAKERACE 0x11A1EE4: replay of answered parks, authority decides asks; '
      'trampoline 0x%X..0x%X |' % (TF, TF + F_WORDS * 4, PAD_F, PAD_F + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Today (v3.9.20)')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as fh:
        fh.write('CAVES = {%r: 0x%X, %r: 0x%X, %r: 0x%X, %r: 0x%X, %r: 0x%X}\n' % (
            'TRBOX', BOX, 'TRGRANT', TG, 'TRFRAME', TF, 'PAD_GRANT', PAD_G, 'PAD_FRAME', PAD_F))
        fh.write('LAYOUT = """%s"""\n' % LAYOUT)
