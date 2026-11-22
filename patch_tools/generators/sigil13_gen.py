"""sigil13_gen.py -> sigil13_live.py: SIGIL13_JOIN, late sub-quest-manager entries (sigil13_notes.md).
Static only. python sigil13_gen.py   (from diag/net). cave_lib appends its claim rows (owner sigil13_gen) to
cave_registry.md (stable: re-runs reuse them).

Problem (sigil9_notes 3, live 2026-11-15): SQM entries are made only in MatchPreprocess 0x1181D80, from the pgds the
game knows then. A game that runs MatchPreprocess before the peer's player data arrived never gets that peer's entry
-> no module for him on that game -> the bearer's listener gives up (module+0x79 = 1) -> nothing pairs or pays.

SIGIL13_JOIN: the per-frame SQM flush call 0x182F2E8 `bl 0x1180440` goes through a cave first. In LAN only
(offline byte *(0x5B65C20)+0xBDA == 0), with a running session (*(0x5B3CE08)+0x1268 == 6) and a SQM that already has
entries (MatchPreprocess ran), every frame:
  1. re-arm (only on the 3 frames after step 3 created something): every module with +0x79 == 1 (pairing gave up),
     quest +0x4C != -1 and state +0x18 == 0 gets +0x79 = 0 (what the stock rebuild 0x117A500 does at 0x117A8A4);
  2. run the game's OWN entry creation again: enumerator 0xCE9F40(functor vt 0x56F7130 {SQM}, kind 0x27, 0) exactly
     as 0x1181DA0..0x1181DB8 (functor 0x11889E0 skips a key that exists: never an entry twice);
  3. for each entry appended by 2: modules +0x80 = 1 (as 0x1181E0C..0x1181E2C), and if that player's pgd
     ([GDM+0x30][k] with +0xD0 == key) already holds a slot-0 quest pgd+0x46E0 != -1 (an assignment record was
     applied while the entry was missing: 0x1195D30 wrote the slot, 0x11825E0 returned), build the slot-0 module the
     apply's way: 0x11825E0(SQM, &key, &slot 0, quest, targets 0) (same arguments as 0x1195D3C..0x1195D50);
     re-arm counter := 3, debug counter +1 per entry;
  4. tail-jump to 0x1180440 with the caller's x0 / x1 / w2 (x30 = 0x182F2EC, from the hooked bl).
Offline / hub / no session: stock path (only the gate words run).

Cave space: the NEAR_TRAMP pool has 8 bytes left (0x563EFF8..0x563F000). The trampoline is 2 words
`adrp x16, 0xC502000 ; br x16`, so the far cave starts on a 4 KiB page (0xC502000)."""
import os

import cave_lib as C

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = 0x182F2E8           # bl #0x1180440 (per-frame SQM flush, fn 0x182E560)
FLUSH = 0x1180440
ENUM = 0xCE9F40            # pgd enumerator (x0 functor object, w1 kind, w2 flags)
FUNCTOR_VT = 0x56F7130     # SQM entry functor vtable (call slot +0x30 = 0x11889E0, in-place destroy +0x20 = ret)
SLOT_APPLY = 0x11825E0     # module apply (x0 SQM, x1 &player no, x2 &slot byte, w3 quest, x4 targets)
GAMEDATA_G = 0x5B65C20     # +0xBDA offline byte
MGR3_G = 0x5B3CE08         # +0x1268 session mode (6 = in a LAN/online session)
GDM_G = 0x5B57EB8          # [GDM+0x30] inline array 12 x 0x47F0
TRAMP = 0x563EFF8
FAR = 0xC502000

CTX = [  # (addr, capstone text) that the design relies on
    (0x182F2C4, 'adrp x8, #0x59df000'), (0x182F2C8, 'ldr x8, [x8, #0xf30]'), (0x182F2CC, 'ldr x0, [x8]'),
    (0x182F2D0, 'cbz x0, #0x182f610'), (0x182F2E0, 'mov w2, #1'), (SITE, 'bl #0x1180440'),
    # MatchPreprocess entry creation, copied
    (0x1181D94, 'adrp x8, #0x56f7000'), (0x1181D98, 'add x8, x8, #0x130'), (0x1181DA0, 'stp x8, x0, [sp]'),
    (0x1181DAC, 'mov w1, #0x27'), (0x1181DB0, 'str x20, [sp, #0x20]'), (0x1181DB4, 'mov w2, wzr'),
    (0x1181DB8, 'bl #0xce9f40'), (0x1181E14, 'strb w10, [x11, #0x80]'),
    # enumerator calls [obj+0x20] vt+0x30
    (0xCE9FA4, 'ldr x0, [x20, #0x20]'), (0xCE9FB0, 'ldr x8, [x8, #0x30]'),
    # functor: SQM at +8, dedup by key = pgd+0xD0, team byte gate
    (0x1188A04, 'ldrb w8, [x1, #0x104]'), (0x1188A10, 'ldr x23, [x0, #8]'), (0x1188A14, 'ldr w24, [x1, #0xd0]'),
    (0x1188A18, 'ldp x8, x9, [x23, #8]'), (0x1188A28, 'cmp w10, w24'), (0x1188BC8, 'str w24, [x8]'),
    # slot apply call of the record apply
    (0x1195D3C, 'ldur w3, [x19, #-8]'), (0x1195D40, 'add x1, sp, #0x28'), (0x1195D44, 'add x2, sp, #0x30'),
    (0x1195D48, 'mov x4, xzr'), (0x1195D4C, 'strb wzr, [sp, #0x30]'), (0x1195D50, 'bl #0x11825e0'),
    (0x11826C0, 'ldp x10, x11, [x0, #8]'), (0x1182768, 'str w19, [x21, #0x4c]'),
    # +0x79: stock writers (give-up 1, rebuild 0)
    (0x1180944, 'strb w9, [x8, #0x79]'), (0x1180A5C, 'strb w9, [x8, #0x79]'), (0x117A8A4, 'strb wzr, [x19, #0x79]'),
    # gates
    (0x1181E44, 'ldrb w8, [x8, #0xbda]'), (0x114A40C, 'ldr w8, [x8, #0x1268]'),
    (0xCE9DB4, 'umaddl x20, w21, w8, x9'), (0xCE9DAC, 'mov w8, #0x47f0'),
]


def sub_xr(rd, rn, rm):
    return 0xCB000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


def gload(a, reg, g):
    """adrp reg, page(main+g); ldr reg, [reg, #lo]  (reg = *(main+g))"""
    a.many(lambda pc, L: [C.adrp(pc, C.R(reg), g & ~0xFFF), C.ldr_x(reg, reg, g & 0xFFF)])


def main():
    for addr, t in CTX:
        got = C.dis1(addr, C.text_word(addr))
        assert got == t, 'context %#x: %s != %s' % (addr, got, t)
    # functor vtable: +0x20 (in-place destroy) is `ret`, +0x30 is the call 0x11889E0
    vt = lambda o: int.from_bytes(C.DATA[FUNCTOR_VT + o - C.DATA_BASE:FUNCTOR_VT + o - C.DATA_BASE + 8], 'little')
    assert vt(0x30) == 0x11889E0 and vt(0x20) == 0x11889BC, (hex(vt(0x20)), hex(vt(0x30)))
    assert C.dis1(0x11889BC, C.text_word(0x11889BC)) == 'ret'
    # the only builder of this functor is MatchPreprocess (and the functor's own clone methods)
    g = C.Gen('sigil13_gen', out='sigil13_live.py')
    st = g.alloc('SIGIL13_STATE', 'FAR_DATA', 8, 'SIGIL13_JOIN: +0 re-arm frames left, +4 late entries created '
                                                 '(debug, never reset)')
    g.claim('SIGIL13_JOIN', FAR, 0x240, 'late SQM entries for players known after MatchPreprocess + slot-0 build '
                                        '+ pairing re-arm, then 0x1180440 (LAN)')
    g.claim('tramp_182F2E8', TRAMP, 8, 'trampoline 182F2E8 -> C502000 (adrp x16 page + br x16)')

    a = C.Asm(FAR)
    a(C.stp_pre('x29', 'x30', 'sp', -0x80))
    a(C.mov_sp('x29', 'sp'))
    a(C.stp_x('x19', 'x20', 'sp', 0x10))
    a(C.stp_x('x21', 'x22', 'sp', 0x20))
    a(C.stp_x('x0', 'x1', 'sp', 0x30))
    a(C.str_x('x2', 'sp', 0x40))
    a(C.mov_x('x19', 'x0'))                                   # SQM
    gload(a, 'x8', GAMEDATA_G)
    a(C.to(C.cbz_x, 'x8', 'out'))
    a(C.ldrb('w8', 'x8', 0xBDA))
    a(C.to(C.cbnz_w, 'w8', 'out'))                           # offline: stock
    gload(a, 'x8', MGR3_G)
    a(C.to(C.cbz_x, 'x8', 'out'))
    a(C.ldr_w('w8', 'x8', 0x1268))
    a(C.cmp_wi('w8', 6))
    a(C.to(C.bne, 'out'))                                    # no session: stock
    a(C.ldp_x('x9', 'x10', 'x19', 8))
    a(sub_xr('x20', 'x10', 'x9'))                            # bytes of entries before
    a(C.to(C.cbz_x, 'x20', 'out'))                           # MatchPreprocess not run yet: stock
    a.many(lambda pc, L: [C.adrp(pc, 22, st & ~0xFFF), C.add_xi('x22', 'x22', st & 0xFFF)])
    # ---- 1. re-arm (frames after a late entry)
    a(C.ldr_w('w8', 'x22', 0))
    a(C.to(C.cbz_w, 'w8', 'enum'))
    a(C.sub_wi('w8', 'w8', 1))
    a(C.str_w('w8', 'x22', 0))
    a.label('r_loop')
    a(C.cmp_xr('x9', 'x10'))
    a(C.to(C.bhs, 'enum'))
    for k, o in enumerate((8, 0x10, 0x18)):
        sk = 'r_sk%d' % k
        a(C.ldr_x('x11', 'x9', o))
        a(C.to(C.cbz_x, 'x11', sk))
        a(C.ldrb('w12', 'x11', 0x79))
        a(C.to(C.cbz_w, 'w12', sk))                           # not given up
        a(C.ldr_w('w12', 'x11', 0x4C))
        a(C.add_wi('w12', 'w12', 1))
        a(C.to(C.cbz_w, 'w12', sk))                           # quest -1: no objective
        a(C.ldr_w('w12', 'x11', 0x18))
        a(C.to(C.cbnz_w, 'w12', sk))                          # state set: never re-arm
        a(C.strb('wzr', 'x11', 0x79))
        a.label(sk)
    a(C.add_xi('x9', 'x9', 0x20))
    a(C.to(C.b, 'r_loop'))
    # ---- 2. the game's own entry creation (MatchPreprocess 0x1181D94..0x1181DB8)
    a.label('enum')
    a.many(lambda pc, L: [C.adrp(pc, 8, FUNCTOR_VT & ~0xFFF), C.add_xi('x8', 'x8', FUNCTOR_VT & 0xFFF)])
    a(C.add_xi('x0', 'sp', 0x48))
    a(C.stp_x('x8', 'x19', 'x0', 0))
    a(C.str_x('x0', 'x0', 0x20))
    a(C.movz_w('w1', 0x27))
    a(C.mov_w('w2', 'wzr'))
    a.many(lambda pc, L: C.far_call(pc, ENUM))               # in-place destroy (+0x20) is `ret`: nothing to undo
    a(C.ldp_x('x9', 'x10', 'x19', 8))
    a(sub_xr('x21', 'x10', 'x9'))
    a(C.cmp_xr('x21', 'x20'))
    a(C.to(lambda pc, t: C.bcond(pc, 'ls', t), 'out'))       # nothing new
    a(C.add_xr('x20', 'x9', 'x20'))                          # first new entry
    # ---- 3. per new entry
    a.label('n_loop')
    a(C.ldr_x('x8', 'x19', 0x10))
    a(C.cmp_xr('x20', 'x8'))
    a(C.to(C.bhs, 'n_done'))
    a(C.movz_w('w9', 1))
    for k, o in enumerate((8, 0x10, 0x18)):
        a(C.ldr_x('x10', 'x20', o))
        a(C.to(C.cbz_x, 'x10', 'n_s%d' % k))
        a(C.strb('w9', 'x10', 0x80))                          # started, as MatchPreprocess 0x1181E14
        a.label('n_s%d' % k)
    a(C.ldr_w('w9', 'x22', 4))
    a(C.add_wi('w9', 'w9', 1))
    a(C.str_w('w9', 'x22', 4))
    a(C.ldr_w('w21', 'x20', 0))                              # key = player no
    gload(a, 'x8', GDM_G)
    a(C.to(C.cbz_x, 'x8', 'n_next'))
    a(C.ldr_x('x8', 'x8', 0x30))
    a(C.to(C.cbz_x, 'x8', 'n_next'))
    a(C.movz_w('w11', 12))
    a(C.movz_w('w12', 0x47F0))
    a.label('p_loop')
    a(C.ldr_w('w13', 'x8', 0xD0))
    a(C.cmp_wr('w13', 'w21'))
    a(C.to(C.beq, 'p_found'))
    a(C.add_xr('x8', 'x8', 'x12'))
    a(C.sub_wi('w11', 'w11', 1))
    a(C.to(C.cbnz_w, 'w11', 'p_loop'))
    a(C.to(C.b, 'n_next'))
    a.label('p_found')
    a(C.add_xi('x8', 'x8', 4, lsl12=True))                   # pgd + 0x4000
    a(C.ldr_w('w3', 'x8', 0x6E0))                            # pgd+0x46E0 slot-0 quest
    a(C.add_wi('w9', 'w3', 1))
    a(C.to(C.cbz_w, 'w9', 'n_next'))                         # -1: no record applied yet (stock apply will do it)
    a(C.str_w('w21', 'sp', 0x70))
    a(C.strb('wzr', 'sp', 0x74))
    a(C.mov_x('x0', 'x19'))
    a(C.add_xi('x1', 'sp', 0x70))
    a(C.add_xi('x2', 'sp', 0x74))
    a(C.mov_x('x4', 'xzr'))
    a.many(lambda pc, L: C.far_call(pc, SLOT_APPLY))
    a.label('n_next')
    a(C.add_xi('x20', 'x20', 0x20))
    a(C.to(C.b, 'n_loop'))
    a.label('n_done')
    a(C.movz_w('w8', 3))
    a(C.str_w('w8', 'x22', 0))                               # re-arm on the next 3 frames
    # ---- 4. stock flush
    a.label('out')
    a(C.ldp_x('x0', 'x1', 'sp', 0x30))
    a(C.ldr_x('x2', 'sp', 0x40))
    a(C.ldp_x('x19', 'x20', 'sp', 0x10))
    a(C.ldp_x('x21', 'x22', 'sp', 0x20))
    a(C.ldp_post('x29', 'x30', 'sp', 0x80))
    a.many(lambda pc, L: C.far_jump(pc, FLUSH))
    words = a.words()
    assert len(words) * 4 <= 0x240, len(words)
    cave = g.cave('SIGIL13_JOIN_CAVE', FAR, a)
    tw = [C.adrp(TRAMP, 16, FAR), C.br('x16')]
    assert FAR & 0xFFF == 0
    g.listing.append('  scratch x16 at 0x%X: bl site (x16/x17 are IP scratch across a call); x30 = 0x182F2EC '
                     'is the return of the hooked bl, kept for the tail jump' % SITE)
    tramp = g.cave('tramp_182F2E8', TRAMP, tw)
    hook = g.text_patch(SITE, 'bl #0x1180440', C.bl(SITE, TRAMP), 'per-frame SQM flush via SIGIL13_JOIN')
    groups = {'SIGIL13_JOIN': cave + tramp + [hook]}
    print('\n'.join(g.listing))
    C.write_live('sigil13_live.py', groups, ['SIGIL13_JOIN'], __doc__.split('\n\n')[0] +
                 '\nSIGIL13_JOIN: far cave 0xC502000, trampoline 0x563EFF8 (2 words), hook 0x182F2E8 LAST. Every '
                 'game. sigil13_notes.md.')
    d, r = C.cpp_rows('SIGIL13_JOIN', cave + tramp)
    print('cpp rows (far + near cave words): %d' % len(r) if isinstance(r, list) else '')


if __name__ == '__main__':
    main()
