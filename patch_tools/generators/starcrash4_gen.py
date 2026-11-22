"""starcrash4_gen.py: STARCRASH_DEFER game side that DROPS pending notices outside UpdatePhase (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes starcrash4_live.py.
python starcrash4_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: cosmetic_notes.md section 2. Needs the BUILT-IN STARCRASH_DEFER (v1, starcrash2_live.py): SC_UI and
SC_CNT {u32 REQ, u32 DONE} at 0xC50F30C stay as they are; only the game side changes.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed row.

Groups
  STARCRASH4_CAVE   new far cave SC_GAME4 (23 words). Entered from 0x110B3C8 (game thread, x0..x18 / x30 dead):
        REQ == DONE                          -> nothing
        par slot 0, notice queue [par+0x33A0] 0, or par+0x50 != 6 (not UpdatePhase)
                                             -> DONE = REQ (the read value): every pending notice is DROPPED
        else (UpdatePhase, queue present)    -> DONE += 1 and the stock call 0x110C1B8 (one pair per frame)
        then the relocated `mov x0, x19`, back to 0x110B3CC.
        DONE is still written only here (game thread); a REQ increment that lands after the read stays pending.
  STARCRASH4_HOOK   UPDATE of the built-in trampoline 0x1100090..0x110009B (PAD_GM): adrp/add now point at
        SC_GAME4 (the br x16 word is unchanged = SAME). The hook 0x110B3C8 `b 0x1100090` stays built in.
        The old SC_GAME cave 0xC5023B8.. becomes unreferenced (left as it is; a far UPDATE would be P3)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'starcrash4_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PUSH2 = 0x110C1B8            # Commendation: pushes the two notices through 0xF94A14
GM_SITE, GM_BACK = 0x110B3C8, 0x110B3CC
PAD_GM = 0x1100090           # built-in trampoline of STARCRASH_DEFER (starcrash2_live.py CAVES)
CNT = 0xC50F30C              # built-in SC_CNT {REQ, DONE}
PAR = 0x5B3CDF8              # par singleton slot
listing = []


def shipped_word(a):
    assert all(a + i in C.SHIPPED for i in range(4)), 'no built-in word at %x' % a
    return struct.unpack('<I', bytes(C.SHIPPED[a + i] for i in range(4)))[0]


g = C.Gen('starcrash4_gen', OUT, dry=True)
# the earlier versions of this same feature are exclusive with this one: not a collision
g.others = C.live_records(exclude=(OUT, 'starcrash2_live.py', 'starcrash2b_live.py'))

# ---------------- what must already be built in
assert shipped_word(GM_SITE) == C.b(GM_SITE, PAD_GM), 'hook 0x110B3C8 -> 0x1100090 is not built in'
old_tramp = [shipped_word(PAD_GM + 4 * k) for k in range(3)]
assert old_tramp == C.far_jump(PAD_GM, 0xC5023B8), 'built-in trampoline does not point at SC_GAME 0xC5023B8'
assert C.dis1(GM_SITE, W[GM_SITE // 4]) == 'mov x0, x19', 'stock word at 0x110B3C8 changed'
# 0x110C1B8 writes x0 before reading it (0x110C1E4 `ldr x0, [x20]`), so no argument is loaded (as starcrash2 --v2)
assert C.dis1(0x110C1E4, W[0x110C1E4 // 4]) == 'ldr x0, [x20]'
assert not re.search(r'\bx0\b|\bw0\b', ' '.join(C.dis1(x, W[x // 4]) for x in range(0x110C1BC, 0x110C1E4, 4)))

GM_N = 23
# claims printed by other dry-run generators and not yet in cave_registry.md (their unused tail words count too)
PENDING = [('kindeath3_gen', 'KAUTH3..KPRED3', 0xC502600, 0xC502920), ('bbfinal_gen', 'BBALLY', 0xC502920, 0xC502970)]
for _o, _t, _lo, _hi in PENDING:
    if not any(r['lo'] < _hi and _lo < r['hi'] for r in C.read_registry()):
        g._dry_rows.append(dict(owner=_o, tag=_t, lo=_lo, hi=_hi, purpose='pending claim (not ours)'))
T_GM = g.alloc('SC_GAME4', 'FAR_CODE', GM_N * 4, 'STARCRASH4 game side: drop pending notices outside UpdatePhase')

# ---------------- SC_GAME4
# Flags trick: every branch to 'drop' is taken with NE flags (from cmp REQ, DONE or cmp phase, 6); the fall-through
# into 'drop' from the UpdatePhase path has EQ flags (cmp phase, 6 equal; add / ldr / cbz set no flags).
a = C.Asm(T_GM)
a(lambda pc, L: C.adrp(pc, 9, CNT))
a(C.ldr_w(10, 9, C.lo12(CNT)))                      # w10 = REQ
a(C.ldr_w(11, 9, C.lo12(CNT) + 4))                  # w11 = DONE
a(C.cmp_wr(10, 11))
a(lambda pc, L: C.beq(pc, L['out']))                # nothing pending
a(lambda pc, L: C.adrp(pc, 8, PAR))
a(C.ldr_x(8, 8, C.lo12(PAR)))
a(lambda pc, L: C.cbz_x(pc, 8, L['drop']))          # flags NE (REQ != DONE)
a(C.ldr_x(12, 8, 0x33A0))                           # notice queue Q
a(lambda pc, L: C.cbz_x(pc, 12, L['drop']))         # flags NE
a(C.ldr_w(12, 8, 0x50))                             # par+0x50 phase (6 = UpdatePhase)
a(C.cmp_wi(12, 6))
a(lambda pc, L: C.bne(pc, L['drop']))               # flags NE
a(C.add_wi(10, 11, 1))                              # UpdatePhase: w10 = DONE + 1 (flags stay EQ)
a.label('drop')
a(C.str_w(10, 9, C.lo12(CNT) + 4))                  # DONE = w10 (only writer: this thread)
a(lambda pc, L: C.bne(pc, L['out']))                # dropped: no notice
a.many(lambda pc, L: C.far_call(pc, PUSH2))         # one deferred pair of notices, game thread, UpdatePhase only
a.label('out')
a(W[GM_SITE // 4])                                  # mov x0, x19 (relocated)
a.many(lambda pc, L: C.far_return(pc, GM_BACK))
gm_words = a.words()
assert len(gm_words) <= GM_N, len(gm_words)

caves = g.cave('SC_GAME4', T_GM, gm_words)
tramp = [g.text_patch(PAD_GM + 4 * k, 'udf #0', w, 'trampoline -> SC_GAME4 0x%X' % T_GM, replaces_shipped=True)
         for k, w in enumerate(C.far_jump(PAD_GM, T_GM))]
groups = {'STARCRASH4_CAVE': caves, 'STARCRASH4_HOOK': tramp}
order = ['STARCRASH4_CAVE', 'STARCRASH4_HOOK']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in [r for r in g._dry_rows if r['owner'] == 'starcrash4_gen']:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'SC_GAME4': 0x%X, 'SC_CNT': 0x%X, 'PAD_GM': 0x%X}\n"
                "REQUIRES = ['STARCRASH_DEFER (built in)']\n"
                "EXCLUSIVE_WITH = {'STARCRASH4_HOOK': ['TE_COMMEND_UI', 'STARCRASH_DEFER_V2']}\n" % (T_GM, CNT, PAD_GM))
