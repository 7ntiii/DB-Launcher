"""owner_prompt_gen.py: no "Pick up" prompt for a per-player world item the local player may not take (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes owner_prompt_live.py.
python owner_prompt_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: batch39_notes.md section 3.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in batch39_notes.md; the lead adds the row when baking:
  owner_prompt_gen | PROMPT | <printed range> | prompt filter for per-player items (batch39 3)

Groups
  OWNER_PROMPT_CAVE  far cave PROMPT + a 3-word trampoline in zero padding near the prompt collector.
  OWNER_PROMPT       two `bl 0x15a1d20` sites of the action-button candidate collector (0x15A5CF0, 0x15A5E6C) ->
     `bl trampoline`. The cave runs the stock can-interact test 0x15A1D20 first; when it says yes, in a LAN match,
     for a networked item of a per-player kind (+0x15C in 1/2/4/5) whose allowed mask (+0x290) lacks the local
     player's slot (pgd+0x104) or whose taken mask (+0x288) has it, it answers 0 = no prompt. That is the host's own
     acceptance rule (0x15A4128..0x15A4164), so a prompt now means the host will accept.
     Offline (offline byte != 0, or no online world): stock answer. Every other caller of 0x15A1D20 (take wrapper,
     insert, award reader, ...) is unchanged."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'owner_prompt_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
CAN = 0x15A1D20
SITES = (0x15A5CF0, 0x15A5E6C)
OFFL, WORLD, WCM = 0x5B65C20, 0x5B57E90, 0x5B3CD88
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


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


# ================================================================ code facts [V]
# the collector: per item node x22 / x21, x0 = node+0x30, then `tbz w0,#0` skip (no prompt)
for a, t in ((0x15A5CE8, 'add x23, x22, #0x30'), (0x15A5CEC, 'mov x0, x23'), (0x15A5CF0, 'bl #0x15a1d20'),
             (0x15A5CF4, 'tbz w0, #0, #0x15a5ce0'), (0x15A5CFC, 'tbnz w8, #0xe, #0x15a5ce0'),
             (0x15A5E68, 'add x0, x21, #0x30'), (0x15A5E6C, 'bl #0x15a1d20'), (0x15A5E70, 'tbz w0, #0, #0x15a5e60'),
             (0x15A5D54, 'mov w23, #0x119e'), (0x15A5D6C, 'mov w23, #0x1072'),
             # 0x15A1D20 reads node+0x58 as [x0+0x28]: x0 = node + 0x30
             (0x15A1D30, 'ldrb w9, [x0, #0x28]'),
             # host acceptance rule (0x15A3F00) the cave mirrors: slot = [[chr+0x20]+0x1D0]+0x104, kinds 0x36 mask
             (0x15A4110, 'ldr x8, [x27, #0x20]'), (0x15A4114, 'ldr x8, [x8, #0x1d0]'), (0x15A411C, 'ldrb w8, [x8, #0x104]'),
             (0x15A4128, 'ldrb w9, [x20, #0x15c]'), (0x15A413C, 'mov w10, #0x36'), (0x15A4150, 'ldr x9, [x20, #0x288]'),
             (0x15A415C, 'ldr x9, [x20, #0x290]')):
    stock(a, t)
for s in SITES:
    assert not targets_in(s, s + 4), 'branch into site %x' % s
assert W[CAN // 4] == PACIBSP

# trampoline: 3 zero words of padding before a function start, nothing points into them, nobody uses them
others = C.live_records(exclude=(OUT,))
PAD = None
for a in range(0x15A0000, 0x15C0000, 4):
    if W[a // 4] == 0 and W[a // 4 + 1] == 0 and W[a // 4 + 2] == 0 and W[a // 4 - 1] != 0:
        end = a
        while W[end // 4] == 0:
            end += 4
        if W[end // 4] != PACIBSP:
            continue
        if any(x in C.SHIPPED or x in others for x in range(a, a + 12)):
            continue
        if targets_in(a, end) or qwords_in(a, end):
            continue
        if all(C.reach(s, a) for s in SITES):
            PAD = a
            break
assert PAD, 'no free padding'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 12))

g = C.Gen('owner_prompt_gen', out=OUT, dry=True)      # dry: never writes cave_registry.md (task rule)
SIZE = 56
T = g.alloc('PROMPT', 'FAR_CODE', SIZE * 4, 'prompt filter for per-player items (batch39 3)')
listing.append('cave PROMPT 0x%X..0x%X (FAR_CODE, NOT claimed in cave_registry.md: lead adds the row)' % (T, T + SIZE * 4))

LSL_W11 = 0x1ACA216B               # lsl w11, w11, w10
LSL_X17 = 0x9ACA2171               # lsl x17, x11, x10
TST_W = 0x6A0C017F                 # tst w11, w12
TST_X = 0xEA0C023F                 # tst x17, x12
assert C.dis1(0, LSL_W11) == 'lsl w11, w11, w10', C.dis1(0, LSL_W11)
assert C.dis1(0, LSL_X17) == 'lsl x17, x11, x10', C.dis1(0, LSL_X17)
assert C.dis1(0, TST_W) == 'tst w11, w12', C.dis1(0, TST_W)
assert C.dis1(0, TST_X) == 'tst x17, x12', C.dis1(0, TST_X)

a = C.Asm(T)
a(C.stp_pre(29, 30, 31, -0x20))
a(C.mov_sp(29, 31))
a(C.str_x(0, 31, 0x10))
a.many(lambda pc, L: [C.adrp(pc, 16, CAN), C.add_xi(16, 16, C.lo12(CAN)), C.blr(16)])
a(C.to(C.tbz, 'w0', 0, 'out'))                          # stock says no: no prompt
a(C.ldr_x(9, 31, 0x10))                                 # x9 = node + 0x30
a(lambda pc, L: C.adrp(pc, 10, WORLD))
a(C.ldr_x(10, 10, C.lo12(WORLD)))
a(C.to(C.cbz_x, 'x10', 'yes'))                          # no online world: stock
a(lambda pc, L: C.adrp(pc, 10, OFFL))
a(C.ldr_x(10, 10, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x10', 'yes'))
a(C.ldrb(10, 10, 0xBDA))
a(C.to(C.cbnz_w, 'w10', 'yes'))                         # offline: stock
a(C.ldrb(10, 9, 0))
a(C.to(C.tbz, 'w10', 4, 'yes'))                         # not a networked item: stock
a(C.ldrb(10, 9, 0x12C))                                 # kind = node+0x15C
a(C.cmp_wi('w10', 5))
a(C.to(C.bcond, 'hi', 'yes'))
a(C.movz_w(11, 1))
a(LSL_W11)                                              # w11 = 1 << kind
a(C.movz_w(12, 0x36))
a(TST_W)                                                # kinds 1/2/4/5
a(C.to(C.beq, 'yes'))                                   # shared kind: stock
a(lambda pc, L: C.adrp(pc, 10, WCM))
a(C.ldr_x(10, 10, C.lo12(WCM)))
a(C.to(C.cbz_x, 'x10', 'yes'))
a(C.ldr_x(10, 10, 0x1A8))
a(C.to(C.cbz_x, 'x10', 'yes'))
a(C.ldr_x(10, 10, 0x20))
a(C.to(C.cbz_x, 'x10', 'yes'))
a(C.ldr_x(10, 10, 0x1D0))
a(C.to(C.cbz_x, 'x10', 'yes'))
a(C.ldrb(10, 10, 0x104))
a(C.cmp_wi('w10', 11))
a(C.to(C.bcond, 'hi', 'yes'))
a(C.movz_x(11, 1))
a(LSL_X17)                                              # x17 = 1 << slot
a(C.ldr_x(12, 9, 0x258))                                # taken  = node+0x288
a(TST_X)
a(C.to(C.bne, 'no'))
a(C.ldr_x(12, 9, 0x260))                                # allowed = node+0x290
a(TST_X)
a(C.to(C.beq, 'no'))
a.label('yes')
a(C.movz_w(0, 1))
a.label('out')
a(C.ldp_post(29, 30, 31, 0x20))
a(C.RET)
a.label('no')
a(C.movz_w(0, 0))
a(C.to(C.b, 'out'))
words = a.words()
assert len(words) <= SIZE, len(words)
dis = [C.dis1(T + 4 * i, w) for i, w in enumerate(words)]
assert 'lsl w11, w11, w10' in dis and 'lsl x17, x11, x10' in dis
# registers: only x0, x9..x12, x16, x17, x29, x30 (all caller-saved or saved here) - the sites are calls
for t in dis:
    for r in re.findall(r'\b[xw](\d+)\b', t):
        assert int(r) in (0, 9, 10, 11, 12, 16, 17, 29, 30), t

caves = g.cave('PROMPT', T, words)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> PROMPT 0x%X (x16: the sites are calls)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hooks = [g.text_patch(s, 'bl #0x15a1d20', C.bl(s, PAD), 'prompt collector can-interact -> PROMPT') for s in SITES]
groups = {'OWNER_PROMPT_CAVE': caves + tramp, 'OWNER_PROMPT': hooks}
order = ['OWNER_PROMPT_CAVE', 'OWNER_PROMPT']
print('\n'.join(listing))
print('\n'.join(g.listing))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'PROMPT': 0x%X, 'TRAMP': 0x%X}\n" % (T, PAD))
