"""falldeath_gen: FALL_KILL - the enemy owner's death decision kills every other game's copy (deep_audit_F F11,
deep_audit_F_fixes.md). Static only: reads nso/*.bin, patch_manager.cpp, every *_live.py and cave_registry.md;
claims its ranges in cave_registry.md (not with --dry); writes falldeath_live.py; prints a capstone listing and
the patch_manager.cpp rows.        python falldeath_gen.py [--dry]   (from diag/net)

Needs the built-in KILL2_CAVES / KILL2_OWNER (credit2_live.py, shipped since v3.6):
  - the owner's death handler 0x1752400 broadcasts 0x3C {killer, victim} (GATE);
  - the 0x3C reader reads from anyone (0x17E8EE0) and skips victims already handled (READ at 0x17E8F2C);
  - the reader then sets bit 0x10000 of chr+0x12C5 (owner's answer) and calls 0x1752400 at 0x17E8F50.
Gap [V]: 0x1752400 (GATE) only finishes a death whose bits 53-54 of chr+0x12BC are 01 ("dying"). A copy whose own
HP never reached 0 (the owner's HP 0 did not arrive, or the owner's death came from a path without an HP event,
e.g. a fall / kill plane) is not dying: the answer is stored and the copy stays alive.
FALL_KILL: at 0x17E8F50, for an enemy-class victim that is neither dying (bit 53) nor handled (bit 54), call the
game's own kill function 0x174EAE4 (dead-flag check, death decider vt+0x6D0, 0x174EB54, sets bit 53, tail call
0x1752400) instead of 0x1752400. 0x1752400's GATE then finishes it with the owner's killer, exactly as it does for
a copy whose HP reached 0. Everything else (players, kin of other classes, dying / handled chrs) is unchanged.
"""
import sys

import cave_lib as C

DRY = '--dry' in sys.argv
ENEMY_VT = 0x572B108
KILL_FN = 0x174EAE4                           # kill(chr): see the docstring
DEATH = 0x1752400
SITE = 0x17E8F50                              # bl 0x1752400 in the 0x3C reader, x0 = victim chr
BACK = 0x17E8F54                              # next message


def ctx(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)


# ------------------------------------------------------------------ stock context (asserted)
for a, t in [
        # kill function 0x174EAE4: dead check, decider, notify, bit 53, tail call 0x1752400
        (0x174EAE4, 'pacibsp'), (0x174EAF4, 'ldr x8, [x0, #0x18]'), (0x174EAFC, 'ldr x8, [x8, #0x30]'),
        (0x174EB04, 'ldrb w8, [x8, #0x18]'), (0x174EB08, 'tbnz w8, #0, #0x174eb48'),
        (0x174EB14, 'ldr x8, [x8, #0x6d0]'), (0x174EB20, 'bl #0x174eb54'), (0x174EB24, 'mov w8, #0x12bc'),
        (0x174EB30, 'orr x9, x9, #0x20000000000000'), (0x174EB44, 'b #0x1752400'),
        # its other user: the chr update path (0x17BD008) calls it the same way
        (0x17BD008, 'bl #0x174eae4'),
        # 0x3C reader after the victim lookup (READ hook at 0x17E8F2C is built in)
        (0x17E8F30, 'ldr w8, [x0, x24]'), (0x17E8F34, 'mov x20, x0'), (0x17E8F3C, 'orr w8, w8, #0x10000'),
        (0x17E8F40, 'str w8, [x0, x24]'), (0x17E8F48, 'bl #0xe8e67c'), (0x17E8F4C, 'mov x0, x20'),
        (SITE, 'bl #0x1752400'), (BACK, 'ldr x8, [x26]'),
        # decider in mode 6 for a copy: the request (nop'ed by KILL2_OWNER) then out
        (0x1752258, 'cmp w10, #6'), (0x175227C, 'b #0x17522f4')]:
    ctx(a, t)
# built-in KILL2 records this relies on
assert C.dis1(0x17E8EE0, C.shipped_word(0x17E8EE0)) == 'ldr x8, [x8, #0x50]', 'KILL2_OWNER 0x17E8EE0 not built in'
assert C.dis1(0x1752278, C.shipped_word(0x1752278)) == 'nop', 'KILL2_OWNER 0x1752278 not built in'
for a in (0x17E8F2C, 0x175242C):
    assert C.dis1(a, C.shipped_word(a)).startswith('b #'), 'KILL2_OWNER hook %x not built in' % a

g = C.Gen('falldeath_gen', 'falldeath_live.py', dry=DRY)


def kill_asm(start):
    a = C.Asm(start)
    a(C.ldr_x(10, 0, 0))                                          # vtable of the victim (x0 = chr, x20 = chr)
    a(lambda pc, L: C.adrp(pc, 11, ENEMY_VT))
    a(C.add_xi(11, 11, C.lo12(ENEMY_VT)))
    a(C.cmp_xr(10, 11))
    a(C.to(C.bne, 'ORIG'))                                        # not enemy-class: as before
    a(C.add_xi(9, 0, 1, True))                                    # x9 = chr + 0x1000
    a(C.ldrb(9, 9, 0x2C2))                                        # byte chr+0x12C2 = bits 48..55 of chr+0x12BC
    a(lambda pc, L: C.tbnz(pc, 9, 5, L['ORIG']))                 # bit 53 dying: its own death runs, as before
    a(lambda pc, L: C.tbnz(pc, 9, 6, L['ORIG']))                 # bit 54 handled (READ skips these anyway)
    a.many(lambda pc, L: C.far_call(pc, KILL_FN, 'x16'))         # kill the copy: bit 53, then 0x1752400 (GATE)
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    a.label('ORIG')
    a.many(lambda pc, L: C.far_call(pc, DEATH, 'x16'))           # the replaced bl 0x1752400
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    return a


n = len(kill_asm(C.FAR_LO if hasattr(C, 'FAR_LO') else 0xC500000).words())
start = g.alloc('FALLKILL', 'FAR_CODE', (n * 4 + 15) // 16 * 16, 'owner death kills copies (falldeath_notes)')
groups = {'FALL_KILL_CAVE': g.cave('FALLKILL', start, kill_asm(start))}
# The NEAR_TRAMP pool is full (2026-11-17). The trampoline goes into the free ro padding just below it
# (0x563ED3C..0x563EE00 was free: not shipped, in no *_live.py, zero in the image, no registry row). The JIT runs
# ro padding (shipped caves at 0x563EAE0 etc. live there). Checked word by word like a pool claim.
TRAMP = 0x563ED40
for a in range(TRAMP, TRAMP + 12):
    g.free_bytes(a, 1, 'tramp byte')
    assert C.image_is_zero(a, 1), 'tramp %x not zero' % a
    assert not any(r['lo'] <= a < r['hi'] for r in C.read_registry()), 'tramp %x claimed' % a
assert C.reach(SITE, TRAMP), 'b reach'
tw = [C.adrp(TRAMP, 16, start), C.add_xi(16, 16, C.lo12(start)), C.br(16)]
g.listing.append('--- trampoline at 0x%X (ro padding below NEAR_TRAMP; x16: the site is a bl, x16/x17 are '
                 'call-clobbered there, and the cave returns to 0x17E8F54)' % TRAMP)
tramp_recs = []
for i, w in enumerate(tw):
    g.listing.append('  0x%x %s' % (TRAMP + 4 * i, C.dis1(TRAMP + 4 * i, w)))
    tramp_recs.append((TRAMP + 4 * i, '00000000', C.hexw(w), True))
# NOT a cave_registry.md row: read_registry() refuses rows outside the pools (that broke every generator once).
# The words are protected like any record: they are in falldeath_live.py, which every other generator's
# collision check (cave_lib.live_records) reads. Lead: when baking, keep 0x563ED40..0x563ED4B for this.
groups['FALL_KILL'] = tramp_recs + [g.text_patch(SITE, 'bl #0x1752400', C.b(SITE, TRAMP),
                                                 '0x3C reader: a copy that is not dying is killed (owner decided)')]
ORDER = ['FALL_KILL_CAVE', 'FALL_KILL']
print('\n'.join(g.listing))
if DRY:
    sys.exit('dry run: nothing claimed or written')
C.write_live('falldeath_live.py', groups, ORDER, """
FALL_KILL (generated by falldeath_gen.py; deep_audit_F_fixes.md, deep_audit_F F11): the enemy owner's 0x3C death
answer kills every other game's copy that is not dying yet (fall / kill-plane deaths, a lost HP-0 status).
Needs the built-in KILL2_CAVES + KILL2_OWNER and the cave region. Apply on EVERY game. Not live-tested.""")
for name in ORDER:
    d, r = C.cpp_rows(name, groups[name])
    print('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
