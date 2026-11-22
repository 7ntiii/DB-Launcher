"""starfrag_gen.py -> starfrag_live.py: Star Fragment event (EnvEventParam 1210) in LAN. Static only.
python starfrag_gen.py [--dry]      (from diag/net; --dry checks everything, claims nothing, writes nothing)
Design, proofs and the live test: starfrag2_notes.md (section 7 = this version).

Why no fragment appears in LAN [V]:
- A fragment is the MSB Treasure (type 4, ItemLot 52310 = accessory 40000 x1) linked to a crash-site asset
  AEG099_211_0000..0007 (m10_00 parts 2399..2406; 12 treasure events, every one of the 8 parts has >= 1).
- The map's treasures are made per match by the stage step 0x114F2C0 (step table word 0x115E4B8): per loaded block
  0xFB82A0(block, functor vtable 0x56F5220) -> 0x115DC10(geom) -> 0xC2CEE0({geom triple}, 1). 0xC2CEE0 finds the
  treasure (0xF2C2A0: info+0x50 -> +0x80 -> +8 list, type 4), removes an old item of that handle (0xC2CFC0..E4), and
  has the online gate 0xC2D040..0xC2D058 (world set and offline byte 0 -> 0xC2D130, no item). Online the server made
  it. (0xFC30A0, the block-load maker, is not this path: live 2026-11-15 STARFRAG_CREATE made nothing.)

STARFRAG_V2 (one group, self-contained; apply on EVERY game; works when applied after map load):
  One far cave, one trampoline shared by three `bl` hooks; the cave tells them apart by x30 (= hook site + 4,
  written by our own bl, so exact):
  - 0xC2D058 `cbz w8, #0xc2d130` -> bl: GATE. Offline (w8 != 0) -> 0xC2D05C (stock create). LAN: create only while
    the FAR_DATA word SPAWN == 1, else 0xC2D130 (stock skip). x30 is dead there (saved at 0xC2CEE8, the next call
    0xC2D088 overwrites it anyway).
  - 0xF0DF88 / 0xF0E144 `add x0, x0, #0x200` -> bl: CRASH 1 / 2 (x0 = the drawn site's asset ins, reached only when
    MS+0x468[k] resolved and param +0xD != 1, right before 0xF98900 shows the site). Offline or guest: nothing extra.
    LAN host: SPAWN = 1, 0x115DC10(-, asset), SPAWN = 0. Then the replaced word, `ret` to the stock bl 0xF98900.
  The item: 0x15AB6D0 -> 0x159C6C4 (built-in ITEMS I3: host only) -> 0x15A3D08 -> built-in cave_push: one id on
  every game. Only the drawn sites (MS+0x468[0..1]) get an item, once per crash.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'starfrag_live.py'
DRY = '--dry' in sys.argv
OWNER = 'starfrag_gen'

# ---------------------------------------------------------------- registry clean-up (2026-11-15)
# STARFRAG_CREATE (and the dispatcher draft) were removed from the build by the lead: their claims are released.
# cave_lib has no release call; this removes ONLY this owner's obsolete rows from cave_lib.REGISTRY (same file and
# row format cave_lib reads), once. Kept tags (STARFRAG_SPAWN, STARFRAG_V2, tramp_STARFRAG) stay stable.
OBSOLETE = {'STARFRAG_CREATE', 'tramp_FC3168', 'STARFRAG_GATE', 'STARFRAG_CRASH', 'STARFRAG_STOCKC'}
if not DRY and os.path.exists(C.REGISTRY):
    lines = open(C.REGISTRY, encoding='utf-8').read().splitlines(True)
    keep = [ln for ln in lines if not (ln.startswith('| %s | ' % OWNER) and ln.split('|')[2].strip() in OBSOLETE)]
    if len(keep) != len(lines):
        open(C.REGISTRY, 'w', encoding='utf-8', newline='').write(''.join(keep))
        print('cave_registry.md: released %d obsolete %s row(s)' % (len(lines) - len(keep), OWNER))
g = C.Gen(OWNER, out=OUT, dry=DRY)
if DRY:   # dry: pretend the obsolete rows are gone
    _rows = g._rows
    g._rows = lambda: [r for r in _rows() if not (r['owner'] == OWNER and r['tag'] in OBSOLETE)]

ROLE = 0x492AFD8          # 0 = host / offline, 1 = guest (written by dusk_lan.cpp) [V]
OFFL = 0x5B65C20          # *(OFFL)+0xBDA != 0: offline
SPAWNER = 0x115DC10       # the stage step's per-geom treasure functor body: (x0 unused, x1 = geom ins)
GATE_SITE, GATE_RET, GATE_CREATE, GATE_SKIP = 0xC2D058, 0xC2D05C, 0xC2D05C, 0xC2D130
CRASH_SITES = (0xF0DF88, 0xF0E144)

# ---------------------------------------------------------------- stock context [V]
STOCK = [
    (0xC2CEE8, 'stp x29, x30, [sp, #0x80]'), (0xC2CF1C, 'bl #0xf2c2a0'), (0xC2CF94, 'ldr x24, [x24, #0xed8]'),
    (0xC2CFC8, 'bl #0x15a2540'), (0xC2CFE0, 'bl #0x15a57e0'),
    (0xC2D040, 'ldr x8, [x8, #0xb28]'), (0xC2D048, 'cbz x8, #0xc2d05c'), (0xC2D04C, 'adrp x8, #0x5b65000'),
    (0xC2D054, 'ldrb w8, [x8, #0xbda]'), (0xC2D058, 'cbz w8, #0xc2d130'), (0xC2D05C, 'ldr x23, [x24]'),
    (0xC2D088, 'bl #0xf2ab2c'), (0xC2D0A8, 'bl #0x15ab6d0'), (0xC2D130, 'adrp x8, #0x59df000'),
    (0x115DC10, 'pacibsp'), (0x115DC24, 'ldr x8, [x1]'), (0x115DC28, 'mov x0, x1'), (0x115DC84, 'mov w1, #1'),
    (0x115DC88, 'bl #0xc2cee0'),
    (0x114F54C, 'adrp x25, #0x56f5000'), (0x114F598, 'bl #0xfb82a0'), (0x115E4B8, 'adr x11, #0x114f2c0'),
    (0xF0DEC8, 'stp x29, x30, [sp, #0x20]'),
    (0xF0DF68, 'bl #0xfec520'), (0xF0DF80, 'cmp w8, #1'), (0xF0DF88, 'add x0, x0, #0x200'),
    (0xF0DF8C, 'bl #0xf98900'), (0xF0DF90, 'adrp x8, #0x5b57000'),
    (0xF0E124, 'bl #0xfec520'), (0xF0E13C, 'cmp w8, #1'), (0xF0E144, 'add x0, x0, #0x200'),
    (0xF0E148, 'bl #0xf98900'), (0xF0E14C, 'adrp x8, #0x5b57000'),
]
for a, t in STOCK:
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)
# x16 / x17 absent in both functions (trampoline and far_jump scratch)
for lo, hi in ((0xC2CEE0, 0xC2D380), (0xF0DEC0, 0xF0E290)):
    for a in range(lo, hi, 4):
        w = C.text_word(a)
        if w == 0:
            continue
        t = C.dis1(a, w)
        assert not re.search(r'\b[xw]1[67]\b', t), 'x16/x17 used at %x: %s' % (a, t)
# built-in item authority this relies on (ITEMS I3 + cave_push)
assert C.hexw(C.shipped_word(0x159C708)) == '08617F39', 'ITEMS I3 not built in'
assert C.hexw(C.shipped_word(0x15A3E4C)) == 'C7690295', 'ITEMS I4b (cave_push) not built in'
# nothing of the old STARFRAG_CREATE is built in any more
for a in (0xFC3168, 0x563EFD4, 0xC501770):
    assert a not in C.SHIPPED, 'old STARFRAG_CREATE word %x still built in' % a


def chk(w, text):
    got = C.dis1(0, w)
    assert got == text, '%s != %s' % (got, text)
    return w


def L(fn, *args):
    return C.to(fn, *args)


SPAWN = g.alloc('STARFRAG_SPAWN', 'FAR_DATA', 4, 'Star Fragment: 1 while STARFRAG_V2 calls the treasure spawner')


def build(s):
    a = C.Asm(s)
    # ---- dispatch on x30 (= our bl site + 4)
    a(lambda pc, Lb: C.adrp(pc, 'x16', GATE_SITE + 4))
    a(chk(C.add_xi('x16', 'x16', C.lo12(GATE_SITE + 4)), 'add x16, x16, #0x%x' % C.lo12(GATE_SITE + 4)))
    a(chk(C.cmp_xr('x30', 'x16'), 'cmp x30, x16'))
    a(L(C.bne, 'crash'))
    # ---- GATE (from 0xC2D058): w8 = offline byte; exits 0xC2D05C / 0xC2D130 (stock targets; flags not read there
    # before they are set; x16 not read)
    a(L(C.cbnz_w, 'w8', 'create'))                                       # offline: stock create
    a(lambda pc, Lb: C.adrp(pc, 'x16', SPAWN))
    a(chk(C.ldr_w('w16', 'x16', C.lo12(SPAWN)), 'ldr w16, [x16, #0x%x]' % C.lo12(SPAWN)))
    a(L(C.cbz_w, 'w16', 'skip'))                                         # LAN, not our call: stock skip
    a.label('create')
    a.many(lambda pc, Lb: C.far_jump(pc, GATE_CREATE, 'x16'))
    a.label('skip')
    a.many(lambda pc, Lb: C.far_jump(pc, GATE_SKIP, 'x16'))
    # ---- CRASH (from 0xF0DF88 / 0xF0E144): x0 = site asset ins, x30 = site + 4 (stock `bl 0xf98900`).
    # x1..x17 dead (only x0 feeds that bl), x19..x22 callee-saved, the function's x30 saved at 0xF0DEC8.
    a.label('crash')
    a(chk(C.stp_pre('x29', 'x30', 'sp', -0x20), 'stp x29, x30, [sp, #-0x20]!'))
    a(chk(C.str_x('x0', 'sp', 0x10), 'str x0, [sp, #0x10]'))
    a(lambda pc, Lb: C.adrp(pc, 'x16', OFFL))
    a(C.ldr_x('x16', 'x16', C.lo12(OFFL)))
    a(chk(C.ldrb('w16', 'x16', 0xBDA), 'ldrb w16, [x16, #0xbda]'))
    a(L(C.cbnz_w, 'w16', 'out'))                                         # offline: the item exists since load
    a(lambda pc, Lb: C.adrp(pc, 'x16', ROLE))
    a(chk(C.ldrb('w16', 'x16', C.lo12(ROLE)), 'ldrb w16, [x16, #0x%x]' % C.lo12(ROLE)))
    a(L(C.cbnz_w, 'w16', 'out'))                                         # guest: gets the host's item
    a(lambda pc, Lb: C.adrp(pc, 'x16', SPAWN))
    a(chk(C.movz_w('w17', 1), 'mov w17, #1'))
    a(chk(C.str_w('w17', 'x16', C.lo12(SPAWN)), 'str w17, [x16, #0x%x]' % C.lo12(SPAWN)))
    a(chk(C.mov_x('x1', 'x0'), 'mov x1, x0'))
    a.many(lambda pc, Lb: C.far_call(pc, SPAWNER, 'x16'))                # 0x115DC10 -> 0xC2CEE0 -> gate (bl) -> create
    a(lambda pc, Lb: C.adrp(pc, 'x16', SPAWN))
    a(chk(C.str_w('wzr', 'x16', C.lo12(SPAWN)), 'str wzr, [x16, #0x%x]' % C.lo12(SPAWN)))
    a.label('out')
    a(chk(C.ldr_x('x0', 'sp', 0x10), 'ldr x0, [sp, #0x10]'))
    a(chk(C.ldp_post('x29', 'x30', 'sp', 0x20), 'ldp x29, x30, [sp], #0x20'))
    a(chk(C.text_word(CRASH_SITES[0]), 'add x0, x0, #0x200'))           # replaced word (same at both sites)
    a(chk(C.RET, 'ret'))                                                 # -> site + 4
    return a


n = len(build(C.FAR_LO).words())
CAVE = g.alloc('STARFRAG_V2', 'FAR_CODE', (n * 4 + 0x10 + 0xF) & ~0xF,
               'Star Fragment: gate 0xC2D058 + crash spawn 0xF0DF88/0xF0E144 (LAN host)')
cave_recs = g.cave('STARFRAG_V2', CAVE, build(CAVE))
TRAMP = g.alloc('tramp_STARFRAG', 'NEAR_TRAMP', 12, 'trampoline C2D058/F0DF88/F0E144 (bl) -> STARFRAG_V2 via x16')
tramp_recs = g.cave('tramp_STARFRAG', TRAMP, [C.adrp(TRAMP, 'x16', CAVE), C.add_xi('x16', 'x16', C.lo12(CAVE)),
                                              C.br('x16')])
g.listing.append('  scratch x16: absent in 0xC2CEE0..0xC2D380 and 0xF0DEC0..0xF0E290 (checked); x30 dead at all '
                 'three sites (saved at 0xC2CEE8 / 0xF0DEC8, overwritten by the next stock bl)')
hooks = [g.text_patch(GATE_SITE, 'cbz w8, #0xc2d130', C.bl(GATE_SITE, TRAMP), 'gate (bl, x30 = 0xC2D05C)'),
         g.text_patch(0xF0DF88, 'add x0, x0, #0x200', C.bl(0xF0DF88, TRAMP), 'crash 1 (bl)'),
         g.text_patch(0xF0E144, 'add x0, x0, #0x200', C.bl(0xF0E144, TRAMP), 'crash 2 (bl)')]
groups = {'STARFRAG_V2': cave_recs + tramp_recs + hooks}
for a, o, nw, c in groups['STARFRAG_V2']:
    assert not any(a + i in C.SHIPPED for i in range(4)), '%x is shipped' % a
ORDER = ['STARFRAG_V2']
print('\n'.join(g.listing))
if DRY:
    print('dry run: nothing claimed or written')
    sys.exit(0)
C.write_live(OUT, groups, ORDER, """Star Fragment (env event 1210) in LAN: (offset_from_main, orig_hex, new_hex, is_code), little-endian.
Generated by starfrag_gen.py (cave_lib: stock words, capstone, registry, collisions). NOT live-tested.
Notes: starfrag2_notes.md section 7. Apply on EVERY game; order inside the group: far cave, trampoline, then the
three hooks (0xC2D058 gate, 0xF0DF88 / 0xF0E144 crash). Safe to apply after map load (before Phase II): the hooks
only act at a crash or while the cave's own SPAWN flag is set.
The LAN host makes the fragment item of a drawn site when that site's crash happens (30 s / 90 s) through the
game's treasure spawner 0x115DC10 -> 0xC2CEE0; the built-in ITEMS authority pushes it to all games (one id).
Offline and guests: stock. No word is built in: STARFRAG_V2_LIVE == STARFRAG_V2.""")
with open(os.path.join(HERE, OUT), 'a', newline='\n') as f:
    f.write('\n# nothing of this group is built in: the running-game form is the same list\n')
    f.write('STARFRAG_V2_LIVE = list(STARFRAG_V2)\n')
    f.write('CAVE = 0x%X\nTRAMP = 0x%X\n' % (CAVE, TRAMP))
    f.write('SPAWN = 0x%X  # FAR_DATA u32: 1 while the crash cave runs the spawner (no record, zero at boot)\n' % SPAWN)
    f.write('HOOKS = {0xC2D058: "gate", 0xF0DF88: "crash1", 0xF0E144: "crash2"}\n')
    f.write('HOOK_STOCK = {0xC2D058: "%s", 0xF0DF88: "%s", 0xF0E144: "%s"}\n' % tuple(
        C.hexw(C.text_word(a)) for a in (0xC2D058, 0xF0DF88, 0xF0E144)))
print('wrote %s (cave 0x%X, tramp 0x%X, SPAWN 0x%X)' % (OUT, CAVE, TRAMP, SPAWN))
