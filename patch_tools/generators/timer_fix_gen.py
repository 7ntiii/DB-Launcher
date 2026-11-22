"""timer_fix_gen: TIMER_RESYNC, the prepared fix for "the host's timer panel is missing in the final"
(timer_notes.md section 7). Helper 4, 2026-11-17. Static. Nothing is built or applied by this script.

    python diag/net/timer_fix_gen.py               dry run: allocates without writing cave_registry.md,
                                                   writes timer_fix_live.py and prints the listing
    python diag/net/timer_fix_gen.py --all-rounds  variant A2: the same repair in every round (no final gate)
    python diag/net/timer_fix_gen.py --claim       the lead only: claim the cave rows in cave_registry.md
                                                   (needed before baking; the dry addresses are first-fit
                                                   and can move if someone claims FAR_CODE in between)

What it does (the HUD window H = x27 of the HUD update 0x12E32E0, panel state P = H+0x2630, x24):
  The panel's state machine 0x12E3390..0x12E35D8 remembers its own last action in P+0 (1 = it hid the window,
  0 = it showed it) and acts only when P+0 differs from the wanted state w21. A fade-out of H by anything else
  (vt+0x90 FadeOutInstance, which ends with layout+0x1DC = 0) leaves P+0 = 0, so the window stays hidden for good
  while w21 = 0. TIMER_RESYNC replaces the load of P+0 at 0x12E339C (`ldrb w8, [x24]`) with:
      w8 = P+0
      if P+0 == 0 and layout = [H+0x7C0] != 0 and layout+0x1DC == 0 (not visible)
         and H+0x7C8 == 0 (no fade-out running) and H+0x7C9 == 0 (no fade-in running)
         [variant A: and stage round == 4 and stage+0x3388 != 0 (the final)]
      then w8 = 1  -> the game's own show edge (0x12E34A0: FadeIn + area text) runs once
  and goes back to 0x12E33A0 (`cmp w8, w21`). Nothing else changes; the game decides to show (w21 == 0).
Registers: x9 is written before it is read on every path from 0x12E33A0 (0x12E34D8 / 0x12E35E4 / 0x12E3600 or
across a blr) [V]; x16 is not read in 0x12E32E0..0x12E9330 [V] (the first use, 0x12E9334, writes it)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cave_lib as C  # noqa: E402

SITE = 0x12E339C            # ldrb w8, [x24]   (P+0, x24 = H+0x2630)
BACK = 0x12E33A0            # cmp w8, w21
STAGE = 0x5B3CDF8           # stage (par): +0xB8 round, +0x3388 final coordinator
H_LAYOUT, LAYOUT_VISIBLE, H_FADE_OUT, H_FADE_IN = 0x7C0, 0x1DC, 0x7C8, 0x7C9

all_rounds = '--all-rounds' in sys.argv
claim = '--claim' in sys.argv
tag = 'TIMER_RESYNC_ALL' if all_rounds else 'TIMER_RESYNC'
g = C.Gen('timer_fix_gen', out='timer_fix_live.py', dry=not claim)
size = (14 if all_rounds else 22) * 4
far = g.alloc(tag, 'FAR_CODE', size, 'final: re-show the HUD timer window hidden behind the panel state '
              '(timer_notes 7)')
a = C.Asm(far)
a(C.ldrb(8, 24, 0))                                  # the replaced word: w8 = P+0
a(C.to(C.cbnz_w, 'w8', 'back'))                      # the state machine already counts it hidden
a(C.ldr_x(9, 27, H_LAYOUT))                          # layout of H
a(C.to(C.cbz_x, 'x9', 'back'))                       # not loaded: leave it to the game (H+0x7CA path)
a(C.ldrb(9, 9, LAYOUT_VISIBLE))
a(C.to(C.cbnz_w, 'w9', 'back'))                      # visible: nothing to repair
a(C.ldrb(9, 27, H_FADE_OUT))
a(C.to(C.cbnz_w, 'w9', 'back'))                      # a fade-out is running: let it finish
a(C.ldrb(9, 27, H_FADE_IN))
a(C.to(C.cbnz_w, 'w9', 'back'))                      # a fade-in is running
if not all_rounds:
    a(lambda pc, L: C.adrp(pc, 9, STAGE))
    a(C.ldr_x(9, 9, C.lo12(STAGE)))                  # stage
    a(C.to(C.cbz_x, 'x9', 'back'))
    a(C.ldr_w(16, 9, 0xB8))                          # round
    a(C.cmp_wi(16, 4))
    a(C.to(C.bne, 'back'))                           # only the final
    a(C.ldr_x(16, 9, 0x3388))                        # the final's coordinator
    a(C.to(C.cbz_x, 'x16', 'back'))
a(C.movz_w(8, 1))                                    # hidden for the state machine: its show edge runs
a.label('back')
a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
words = a.words()
assert len(words) * 4 == size, (len(words), size)

# The NEAR_TRAMP pool is full (cave_lib: "pool NEAR_TRAMP has no 0xc free bytes"), so the 3-word trampoline goes
# into inter-function padding of main text: 0x12E2424..0x12E243F is 7 x `udf #0` after the `ret` of 0x12E2208's
# neighbour and before 0x12E2440 (a vt+0x120 entry); nothing branches into it [V scan], no shipped / *_live.py
# record touches it (text_patch checks). The registry does not track text padding: noted in timer_notes 7.
TRAMP = 0x12E2424
tramp = [C.adrp(TRAMP, 16, far), C.add_xi(16, 16, C.lo12(far)), C.br(16)]
tramp_recs = [g.text_patch(TRAMP + 4 * i, 'udf #0', w, 'trampoline to the cave (x16)') for i, w in enumerate(tramp)]
g.listing.append('  scratch x16 at 0x%X: not read in 0x12E32E0..0x12E9330 (first use 0x12E9334 writes it)' % SITE)
groups = {
    tag + '_CAVE': g.cave(tag, far, a) + tramp_recs,
    tag + '_HOOK': [g.text_patch(SITE, 'ldrb w8, [x24]', C.b(SITE, TRAMP), 'to the trampoline 0x%X' % TRAMP)],
}
order = [tag + '_CAVE', tag + '_HOOK']
doc = """TIMER_RESYNC (timer_fix_gen.py, timer_notes.md section 7): re-show the HUD window whose fade-out the
panel state machine did not do. Variant %s. NOT built, NOT applied. Apply the CAVE group before the HOOK group.
Undo = the HOOK group's original word (0x12E339C ldrb w8, [x24]).""" % ('A2 (every round)' if all_rounds
                                                                     else 'A (the final only)')
C.write_live('timer_fix_live.py', groups, order, doc)
print('\n'.join(g.listing))
for name in order:
    decl, rows = C.cpp_rows(name, groups[name])
    print(decl)
    print(rows)
if not claim:
    print('DRY RUN: nothing claimed in cave_registry.md; the lead runs --claim before baking')
