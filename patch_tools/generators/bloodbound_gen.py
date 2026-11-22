"""bloodbound_gen.py: Bloodbound Alliances (rule 2) pairs in LAN, plan bloodbound_notes.md 1d, built with cave_lib.
Static only: reads nso/*.bin, patch_manager.cpp, every *_live.py and cave_registry.md; claims its ranges
(owner bloodbound_gen, stable on re-runs); writes bloodbound_live.py; prints a capstone listing and the
patch_manager.cpp rows.        python bloodbound_gen.py [--dry]      (run from diag/net)
Notes (box layout, assist protocol, tests): bloodbound_build_notes.md.

  BB_PAIRS  hook 0x10AC510 `b.ne 0x10AC520` (0x10AC4C0, the phase-start alliance setup, only caller
            MatchPreprocess 0x1149728) -> b tramp -> BB_CAVE (flags of `cmp w8, #6` intact):
              mode != 6 (offline / bots)          -> 0x10AC520 (stock)
              rule byte != 2, box +0 != 2, k > 4  -> 0x10AC514 (stock mode-6 path: drain 0x4B, tail)
              else box +0 = 3 (consumed), then for each pair 0x10AD600(AM, a, b, a, 1, 2, -1) exactly as the
              stock rule-2 Casual path 0x10ACD00..0x10ACD18, then 0x10AC514.
  Needs the shipped ALLY_FORM_GUEST (0x10AD748 nop) and ALLY_NO_4B_WIRE (0x10B07B4 nop): asserted.
BB_BOX (FAR_DATA, 12 bytes, no record): {u8 state 0/2/3, u8 k, k x (u8 a, u8 b), reserved}."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'bloodbound_live.py'
DRY = '--dry' in sys.argv
g = C.Gen('bloodbound_gen', out=OUT, dry=DRY)

SITE = 0x10AC510
FORM = 0x10AD600       # form(AM, a, b, c, w4, w5 kind, w6 slot)
STOCK6 = 0x10AC514     # mode-6 path: mov x0, x19 ; bl 0x10AB5E0 ; b 0x10AD394
OFFL = 0x10AC520       # mode != 6 path
BOX_ADDR = 0xC50F210
RULE = 0x5B65C70

# ---------------------------------------------------------------- stock context [V]
STOCK = [
    (0x10AC4C0, 'pacibsp'), (0x10AC4C4, 'sub sp, sp, #0x120'),
    (0x10AC4C8, 'stp x29, x30, [sp, #0xc0]'),             # x30 saved: our blr may clobber it
    (0x10AC4D0, 'stp x26, x25, [sp, #0xe0]'),             # x25/x26 callee-saved by this function
    (0x10AC4FC, 'adrp x24, #0x59e0000'), (0x10AC504, 'mov x19, x0'),   # x19 = AM
    (0x10AC508, 'ldr x24, [x24, #0xa70]'),                # x24 = GOT -> &rule byte
    (0x10AC50C, 'cmp w8, #6'), (SITE, 'b.ne #0x10ac520'),
    (0x10AC514, 'mov x0, x19'), (0x10AC518, 'bl #0x10ab5e0'), (0x10AC51C, 'b #0x10ad394'),
    (0x10AD394, 'ldrb w8, [x24]'), (0x10AD398, 'strb wzr, [x19, #0x174]'), (0x10AD39C, 'cmp w8, #2'),
    (0x10AD3A0, 'b.eq #0x10ad43c'),
    (0x10AD448, 'ldp x26, x25, [sp, #0xe0]'), (0x10AD450, 'ldp x29, x30, [sp, #0xc0]'),
    (0x10AD454, 'add sp, sp, #0x120'), (0x10AD458, 'retab'),
    # stock rule-2 Casual former call (the arguments we copy)
    (0x10ACD00, 'ldp w1, w2, [x22], #8'), (0x10ACD04, 'mov x0, x19'), (0x10ACD08, 'mov w4, #1'),
    (0x10ACD0C, 'mov w5, #2'), (0x10ACD10, 'mov w6, #-1'), (0x10ACD14, 'mov x3, x1'),
    (0x10ACD18, 'bl #0x10ad600'),
    (FORM, 'pacibsp'), (0x10AD744, 'cmp w10, #6'), (0x10AD748, 'b.eq #0x10ad808'),
]
for a, t in STOCK:
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)
# the GOT slot really points at the rule byte (data image, relocated pointer = main offset)
got = C.DATA[0x59E0A70 - C.DATA_BASE:0x59E0A70 - C.DATA_BASE + 8]
print('GOT 0x59E0A70 image bytes: %s (expected -> 0x%X, relocated at load)' % (got.hex(), RULE))
# shipped prerequisites
assert C.shipped_word(0x10AD748) == C.NOP, 'ALLY_FORM_GUEST (0x10AD748 nop) not shipped'
assert C.shipped_word(0x10B07B4) == C.NOP, 'ALLY_NO_4B_WIRE (0x10B07B4 nop) not shipped'


def ins(lo, hi):
    return [(a, C.dis1(a, C.text_word(a))) for a in range(lo, hi, 4)]


# Register proofs for the mode-6 path after the cave (0x10AC514..0x10AC51C, 0x10AB5E0 = ABI callee, tail
# 0x10AD394..0x10AD458): it reads only x19 / x24 and registers it writes first.
for a, t in ins(0x10AC514, 0x10AC520) + ins(0x10AD394, 0x10AD45C):
    assert not re.search(r'\b[xw](1[67]|[1-7])\b', t) or a == 0x10AC514, 'x1..x7/x16/x17 at %x: %s' % (a, t)
    assert not re.search(r'\b[xw]2[56]\b', t) or a == 0x10AD448, 'x25/x26 at %x: %s' % (a, t)
x9 = [(a, t) for a, t in ins(0x10AD394, 0x10AD45C) if re.search(r'\b[xw]9\b', t)]
assert x9[0] == (0x10AD3E4, 'ldr x9, [x8]'), x9        # first x9 use in the tail is a write
# x16/x17 in the whole function 0x10AC4C0..0x10AD45C: only the block 0x10AC580..0x10AC5F0 (mode != 6 path),
# entered only at 0x10AC580 whose ldp writes both; every branch into it starts inside it (checked).
x1617 = [a for a, t in ins(0x10AC4C0, 0x10AD45C) if re.search(r'\b[xw]1[67]\b', t)]
assert x1617 and min(x1617) == 0x10AC580 and max(x1617) <= 0x10AC5F0, ['%X' % a for a in x1617]
assert C.dis1(0x10AC580, C.text_word(0x10AC580)) == 'ldp x16, x17, [x19, #0x30]'
for a, t in ins(0x10AC4C0, 0x10AD45C):
    m = re.match(r'(b(\.\w+)?|cbn?z|tbn?z) .*#0x([0-9a-f]+)$', t)
    if m:
        tg = int(m.group(3), 16)
        if 0x10AC580 < tg <= 0x10AC5F0:
            assert 0x10AC580 <= a <= 0x10AC5F0, 'branch into the x16 block from %x' % a


# ---------------------------------------------------------------- extra encoders (capstone-checked)
def chk(w, text):
    got_t = C.dis1(0, w)
    assert got_t == text, '%s != %s' % (got_t, text)
    return w


def movn_w(rd, imm): return 0x12800000 | (imm << 5) | C.R(rd)


def L(fn, *args):
    return C.to(fn, *args)


BOX = g.claim('BB_BOX', BOX_ADDR, 12, 'Bloodbound pair box {u8 state 0/2 valid/3 consumed, u8 k, k x (a,b)} (bloodbound_build_notes 1)')


def build(s):
    a = C.Asm(s)
    a(L(C.bne, 'offl'))                                                   # mode != 6: stock
    a(chk(C.ldrb('w9', 'x24'), 'ldrb w9, [x24]'))                         # rule byte
    a(chk(C.cmp_wi('w9', 2), 'cmp w9, #2'))
    a(L(C.bne, 'stock6'))
    a(lambda pc, Lb: C.adrp(pc, 'x25', BOX))
    a(chk(C.add_xi('x25', 'x25', C.lo12(BOX)), 'add x25, x25, #0x%x' % C.lo12(BOX)))
    a(chk(C.ldrb('w9', 'x25'), 'ldrb w9, [x25]'))                         # state
    a(chk(C.cmp_wi('w9', 2), 'cmp w9, #2'))
    a(L(C.bne, 'stock6'))
    a(chk(C.ldrb('w26', 'x25', 1), 'ldrb w26, [x25, #1]'))                # k
    a(chk(C.cmp_wi('w26', 4), 'cmp w26, #4'))
    a(lambda pc, Lb: C.bcond(pc, 'hi', Lb['stock6']))                     # k > 4: ignore, not consumed
    a(chk(C.movz_w('w9', 3), 'mov w9, #3'))
    a(chk(C.strb('w9', 'x25'), 'strb w9, [x25]'))                         # state 3 = consumed
    a(chk(C.add_xi('x25', 'x25', 2), 'add x25, x25, #2'))
    a.label('loop')
    a(L(C.cbz_w, 'w26', 'stock6'))
    a(chk(C.mov_x('x0', 'x19'), 'mov x0, x19'))                           # AM
    a(chk(C.ldrb('w1', 'x25'), 'ldrb w1, [x25]'))                         # a
    a(chk(C.ldrb('w2', 'x25', 1), 'ldrb w2, [x25, #1]'))                  # b
    a(chk(C.mov_w('w3', 'w1'), 'mov w3, w1'))                             # leader = a (stock: mov x3, x1)
    a(chk(C.movz_w('w4', 1), 'mov w4, #1'))
    a(chk(C.movz_w('w5', 2), 'mov w5, #2'))                               # kind 2 = Bloodbound pact
    a(chk(movn_w('w6', 0), 'mov w6, #-1'))                                # first free slot
    a.many(lambda pc, Lb: C.far_call(pc, FORM, 'x16'))                    # x16 + x30 clobbered (x30 saved)
    a(chk(C.add_xi('x25', 'x25', 2), 'add x25, x25, #2'))
    a(chk(C.sub_wi('w26', 'w26', 1), 'sub w26, w26, #1'))
    a(lambda pc, Lb: C.b(pc, Lb['loop']))
    a.label('stock6')
    a.many(lambda pc, Lb: C.far_return(pc, STOCK6, 'x16'))
    a.label('offl')
    a.many(lambda pc, Lb: C.far_return(pc, OFFL, 'x16'))
    return a


n = len(build(C.FAR_LO).words())
CAVE = g.alloc('BB_CAVE', 'FAR_CODE', (n * 4 + 0x10 + 0xF) & ~0xF, 'Bloodbound: form the BB_BOX pairs at MatchPreprocess (LAN)')
groups = {
    'BB_CAVE': g.cave('BB_CAVE', CAVE, build(CAVE)),
    'BB_PAIRS': g.far_hook(SITE, 'b.ne #0x10ac520', CAVE, 'x16', link=False,
                           why='x16/x17 appear in 0x10AC4C0..0x10AD45C only in 0x10AC580..0x10AC5F0 (mode != 6 '
                               'path), first written by ldp x16, x17 at 0x10AC580 (checked); the cave leaves via '
                               'x16 to 0x10AC514 / 0x10AC520'),
}
ORDER = ['BB_CAVE', 'BB_PAIRS']
print('\n'.join(g.listing))
if DRY:
    print('dry run: nothing claimed or written')
    sys.exit(0)
C.write_live(OUT, groups, ORDER, """Bloodbound Alliances pairs in LAN: (offset_from_main, orig_hex, new_hex, is_code), bytes little-endian.
Generated by bloodbound_gen.py (cave_lib checks: stock words, capstone, registry, collisions). NOT live-tested.
Notes: bloodbound_build_notes.md. Apply on EVERY game: BB_CAVE first, then BB_PAIRS (trampoline, then hook 0x10AC510).
Needs shipped ALLY_FORM_GUEST + ALLY_NO_4B_WIRE. Inert unless rule byte == 2 AND BB_BOX state == 2 (mode 6).""")
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write('BOX = 0x%X   # BB_BOX (FAR_DATA, 12 bytes, no record): {u8 state 0/2/3, u8 k, k x (u8 a, u8 b)}\n' % BOX)
    f.write('CAVE = 0x%X\n' % CAVE)
    f.write('HOOK = 0x%X\nHOOK_WORD = 0x%08X   # b tramp (BB_PAIRS in the game)\n' % (
        SITE, int.from_bytes(bytes.fromhex(groups['BB_PAIRS'][-1][2]), 'little')))
print('BOX 0x%X CAVE 0x%X' % (BOX, CAVE))
BEGIN, END = '<!-- CPP_ROWS_BEGIN -->', '<!-- CPP_ROWS_END -->'
parts = [BEGIN, '## 9. patch_manager.cpp rows (generated by bloodbound_gen.py: `cave_lib.cpp_rows`)', '',
         'Declarations with the other `DUSK_W_*` arrays, rows into the built-in table, in this order (cave first).', '']
for gname in ORDER:
    d, r = C.cpp_rows(gname, groups[gname])
    parts += ['### %s' % gname, '```cpp', d, r, '```', '']
parts.append(END)
notes = os.path.join(HERE, 'bloodbound_build_notes.md')
txt = open(notes, encoding='utf-8').read() if os.path.exists(notes) else ''
if BEGIN in txt and END in txt:
    txt = txt[:txt.index(BEGIN)] + txt[txt.index(END) + len(END):].lstrip('\n')
open(notes, 'w', encoding='utf-8').write(txt.rstrip('\n') + '\n\n' + '\n'.join(parts) + '\n')
print('bloodbound_build_notes.md: cpp rows section written')
