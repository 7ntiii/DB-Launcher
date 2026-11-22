"""coop2_gen: the co-op Trespasser groups of trespasser_gen.py (trespasser_notes.md section 6) re-created on the
far cave infrastructure (cave_lib). Static only: reads nso/*.bin, patch_manager.cpp, every *_live.py and
cave_registry.md; claims its ranges in cave_registry.md; writes coop2_live.py; prints a capstone listing and the
patch_manager.cpp rows (cave_lib.cpp_rows).        python coop2_gen.py   (from diag/net)

The old JS_COOP_CAVES / JS_REWARD_OWN / JS_INVITE of trespasser_live.py target main+0x6B31000 (not a mapped
address: patch_manager rejects it). They are SUPERSEDED by:
  COOP2_CAVES       INV / VOWN / LOWN in FAR_CODE (inert alone)
  COOP2_REWARD_OWN  0x102100C `cbz x0` -> b tramp -> VOWN ; 0x1020F3C `adrp x8` -> b tramp -> LOWN
  COOP2_INVITE      0x101FFE0 `mov x0, x19` -> bl tramp -> INV
JS_ISBATTLE_PARK, JS_HOST and JS_HOST_BUILD stay in trespasser_live.py (no cave, unchanged, not regenerated).
Design, unchanged from trespasser_notes 6b/6c; this port only changes addresses and long branches:
  - every text call from far code is far_call (adrp/add/blr x16, x30 saved in the cave frame);
  - every way back to text is far_return (adrp/add/br x16);
  - the radius constant is built with movz/movk/fmov (no data word inside code)."""
import re
import struct
import sys

import cave_lib as C

WCM_G = 0x5B3CD88    # *(main+0x5B3CD88) = WCM; +0x1A8 = local player chr [V 0x1020514, 0x1028B68, FORGE_OWN]
GD_G = 0x5B65C20     # *(main+0x5B65C20)+0xBDA = offline flag
INVITE_RADIUS = 150.0   # metres around the Trespasser [I: the server's real "nearby" rule is unknown]

# ---------------------------------------------------------------- extra encoders (each checked by capstone below)
def ldp_s(rt, rt2, rn, imm): return 0x2D400000 | (((imm // 4) & 0x7F) << 15) | (rt2 << 10) | (C.R(rn) << 5) | rt
def ldr_s(rt, rn, off): return 0xBD400000 | ((off // 4) << 10) | (C.R(rn) << 5) | rt
def fsub_s(rd, rn, rm): return 0x1E203800 | (rm << 16) | (rn << 5) | rd
def fmul_s(rd, rn, rm): return 0x1E200800 | (rm << 16) | (rn << 5) | rd
def fmadd_s(rd, rn, rm, ra): return 0x1F000000 | (rm << 16) | (ra << 10) | (rn << 5) | rd
def fcmp_s(rn, rm): return 0x1E202000 | (rm << 16) | (rn << 5)
def fmov_s_w(rd, rn): return 0x1E270000 | (C.R(rn) << 5) | rd
def csinv_w(rd, rn, rm, cond): return 0x5A800000 | (C.R(rm) << 16) | (C.COND[cond] << 12) | (C.R(rn) << 5) | C.R(rd)


for w, t in ((ldp_s(0, 1, 8, 0x70), 'ldp s0, s1, [x8, #0x70]'), (ldr_s(2, 8, 0x78), 'ldr s2, [x8, #0x78]'),
             (fsub_s(0, 0, 3), 'fsub s0, s0, s3'), (fmul_s(0, 0, 0), 'fmul s0, s0, s0'),
             (fmadd_s(0, 1, 1, 0), 'fmadd s0, s1, s1, s0'), (fcmp_s(0, 1), 'fcmp s0, s1'),
             (fmov_s_w(1, 8), 'fmov s1, w8'), (csinv_w(8, 9, 'wzr', 'lo'), 'csinv w8, w9, wzr, lo')):
    assert C.dis1(0, w) == t, '%s != %s' % (C.dis1(0, w), t)


def ctx(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)


def func_end(s):
    """Next pacibsp after s (the functions used here all start with one)."""
    assert C.text_word(s) == 0xD503237F, 'no pacibsp at %x' % s
    a = s + 4
    while C.text_word(a) != 0xD503237F:
        a += 4
    return a


def no_ip_regs(s, sites):
    """Assert x16/x17 are not named by ANY instruction of the function at s (so x16 holds nothing live at any
    hook site or far_return target inside it; across calls AAPCS64 makes x16/x17 corruptible anyway)."""
    e = func_end(s)
    for a in range(s, e, 4):
        t = C.dis1(a, C.text_word(a))
        assert not re.search(r'\b[xw]1[67]\b', t.split(' ', 1)[-1] if ' ' in t else ''), 'x16/x17 at %x: %s' % (a, t)
    for x in sites:
        assert s <= x < e, '%x not inside function %x..%x' % (x, s, e)
    return 'function 0x%X..0x%X never names x16/x17 (scanned)' % (s, e)


# ---------------------------------------------------------------- context the groups rely on [V] (as trespasser_gen)
for a, t in ((0x101FF48, 'mov x19, x0'), (0x101FFE0, 'mov x0, x19'), (0x101FFE4, 'bl #0x101fc28'),
             (0x101FF28, 'stp x29, x30, [sp, #-0x20]!'),
             (0x1024070, 'mov w1, #2'),
             (0x10200B8, 'ldrh w8, [x19, #0xc0]'), (0x10200CC, 'csinv w8, w9, wzr, lo'), (0x10200D4, 'bl #0x17e7828'),
             (0x102598C, 'pacibsp'), (0x10259B0, 'ldrb w23, [x1, #4]'), (0x10259BC, 'ldr w8, [x1]'),
             (0x1020DBC, 'ldur x20, [x29, #-0x48]'), (0x1020F14, 'cbz x0, #0x1020f3c'),
             (0x1020F3C, 'adrp x8, #0x5b65000'), (0x1020F48, 'cbz w8, #0x1020ffc'), (0x1020F4C, 'ldr x8, [sp, #0x40]'),
             (0x1020FFC, 'ldr x8, [x20]'), (0x1021004, 'ldr x8, [x8, #0x298]'), (0x1021008, 'blr x8'),
             (0x102100C, 'cbz x0, #0x1020d20'), (0x1021010, 'ldr x0, [x0, #0x46d8]'), (0x102101C, 'mov w1, #0xfbd0'),
             (0x1020F38, 'bl #0xdf3920'), (0x1020D20, 'add x24, x24, #0x10'),
             (0x1020524, 'ldr x8, [x8, #0x1a8]'), (0x102054C, 'ldr w8, [x8, #0xd0]'),
             (0x102CC40, 'ldr w10, [x8]'), (0x102CC4C, 'add x8, x8, #0x80')):
    ctx(a, t)
assert C.dis1(0x1021020, C.text_word(0x1021020)) == 'movk w1, #1, lsl #16'     # 0x1FBD0 = 130000
WHY_ACT = no_ip_regs(0x101FF24, [0x101FFE0])                      # Activate step
WHY_END = no_ip_regs(0x1020C40, [0x102100C, 0x1020F3C, 0x1021010, 0x1020D20, 0x1020F4C, 0x1020FFC])   # End

# ---------------------------------------------------------------- generator object; superseded old hook words
DRY = '--dry' in sys.argv          # --dry: allocate without claiming, write nothing
g = C.Gen('coop2_gen', out='coop2_live.py', dry=DRY)
SUPERSEDED = (0x101FFE0, 0x102100C, 0x1020F3C)   # old JS_INVITE / JS_REWARD_OWN sites in trespasser_live.py
for s in SUPERSEDED:
    for i in range(4):
        assert g.others.get(s + i) in (None, 'trespasser_live.py'), '%x held by %s' % (s, g.others.get(s + i))
        g.others.pop(s + i, None)


# ---------------------------------------------------------------- caves (built as functions of their start)
def inv_asm(start):
    """Activate hook (bl): self-invite of the LOCAL player (kind 7 apply 0x102598C, type 0) if it is not a
    participant and within INVITE_RADIUS of the Trespasser. Ends with the replaced `mov x0, x19` and ret."""
    r2 = struct.unpack('<I', struct.pack('<f', INVITE_RADIUS * INVITE_RADIUS))[0]
    a = C.Asm(start)
    a(C.stp_pre(29, 30, 'sp', -0x40))
    a(C.mov_sp(29, 'sp'))
    a(C.stp_x(20, 21, 'sp', 0x10))
    a(C.str_x(22, 'sp', 0x20))
    a(C.mov_x(20, 19))                                        # instance
    a(lambda pc, L: C.adrp(pc, 8, GD_G))
    a(C.ldr_x(8, 8, C.lo12(GD_G)))
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldrb(8, 8, 0xBDA))
    a(C.to(C.cbnz_w, 8, 'out'))                               # offline: stock (no invite)
    a(lambda pc, L: C.adrp(pc, 8, WCM_G))
    a(C.ldr_x(8, 8, C.lo12(WCM_G)))
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldr_x(21, 8, 0x1A8))                                  # local player chr
    a(C.to(C.cbz_x, 21, 'out'))
    a(C.ldr_x(8, 21, 0x20))
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldr_x(8, 8, 0x1D0))                                   # its PlayerGameData
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldr_w(22, 8, 0xD0))                                   # local player number
    a(C.ldr_x(8, 20, 0x2B0))                                  # participants (0x80 each, +0 player no)
    a(C.ldr_x(9, 20, 0x2B8))
    a.label('part')
    a(C.cmp_xr(8, 9))
    a(C.to(C.bhs, 'notpart'))
    a(C.ldr_w(10, 8, 0))
    a(C.cmp_wr(10, 22))
    a(C.to(C.beq, 'out'))                                     # already in the battle: no invite
    a(C.add_xi(8, 8, 0x80))
    a(C.to(C.b, 'part'))
    a.label('notpart')
    a(lambda pc, L: C.adrp(pc, 8, WCM_G))
    a(C.ldr_x(0, 8, C.lo12(WCM_G)))
    a(C.to(C.cbz_x, 0, 'out'))
    a(C.ldrh(8, 20, 0xC0))                                    # enemy key, as IsBattle 0x10200B8..D4
    a(C.ldrh(9, 20, 0xC2))
    a(C.cmp_wi(8, 0x10))
    a(csinv_w(8, 9, 'wzr', 'lo'))
    a(C.strh(8, 'sp', 0x30))
    a(C.strh('wzr', 'sp', 0x32))
    a(C.add_xi(1, 'sp', 0x30))
    a.many(lambda pc, L: C.far_call(pc, 0x17E7828, 'x16'))   # Trespasser chr
    a(C.to(C.cbz_x, 0, 'out'))
    a(C.ldr_x(8, 0, 0x2470))
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldr_x(8, 8, 0xE8))
    a(C.to(C.cbz_x, 8, 'out'))
    a(ldp_s(0, 1, 8, 0x70))                                   # [[chr+0x2470]+0xE8]+0x70 = position
    a(ldr_s(2, 8, 0x78))
    a(C.ldr_x(8, 21, 0x2470))
    a(C.to(C.cbz_x, 8, 'out'))
    a(C.ldr_x(8, 8, 0xE8))
    a(C.to(C.cbz_x, 8, 'out'))
    a(ldp_s(3, 4, 8, 0x70))
    a(ldr_s(5, 8, 0x78))
    a(fsub_s(0, 0, 3))
    a(fsub_s(1, 1, 4))
    a(fsub_s(2, 2, 5))
    a(fmul_s(0, 0, 0))
    a(fmadd_s(0, 1, 1, 0))
    a(fmadd_s(0, 2, 2, 0))
    a(C.movz_w(8, r2 & 0xFFFF))                               # s1 = INVITE_RADIUS^2
    a(C.movk_w(8, r2 >> 16, 1))
    a(fmov_s_w(1, 8))
    a(fcmp_s(0, 1))
    a(C.to(lambda pc, t: C.bcond(pc, 'hi', t), 'out'))        # farther than the radius (or NaN)
    a(C.str_w(22, 'sp', 0x30))                                # kind 7 body {u32 player, u8 type 0}
    a(C.strb('wzr', 'sp', 0x34))
    a(C.mov_x(0, 20))
    a(C.add_xi(1, 'sp', 0x30))
    a.many(lambda pc, L: C.far_call(pc, 0x102598C, 'x16'))   # the kind 7 apply, locally
    a.label('out')
    a(C.ldr_x(22, 'sp', 0x20))
    a(C.ldp_x(20, 21, 'sp', 0x10))
    a(C.ldp_post(29, 30, 'sp', 0x40))
    a(C.mov_x(0, 19))                                         # the replaced word
    a(C.RET)
    return a


def vown_asm(start):
    """End, after pgd = chr vt+0x298 (x0), x20 = result chr: Virtue 130000 only into the local player's pgd."""
    a = C.Asm(start)
    a(C.to(C.cbz_x, 0, 'skip'))                               # stock: no pgd -> next result
    a(lambda pc, L: C.adrp(pc, 8, GD_G))
    a(C.ldr_x(8, 8, C.lo12(GD_G)))
    a(C.to(C.cbz_x, 8, 'chk'))
    a(C.ldrb(8, 8, 0xBDA))
    a(C.to(C.cbnz_w, 8, 'go'))                                # offline: stock (bots too)
    a.label('chk')
    a(lambda pc, L: C.adrp(pc, 8, WCM_G))
    a(C.ldr_x(8, 8, C.lo12(WCM_G)))
    a(C.to(C.cbz_x, 8, 'skip'))
    a(C.ldr_x(8, 8, 0x1A8))
    a(C.cmp_xr(8, 20))
    a(C.to(C.bne, 'skip'))                                    # a copy: VIRTUE_PUB shows the owner's total
    a.label('go')
    a.many(lambda pc, L: C.far_return(pc, 0x1021010, 'x16'))
    a.label('skip')
    a.many(lambda pc, L: C.far_return(pc, 0x1020D20, 'x16'))
    return a


def lown_asm(start):
    """End: the offline-only item lot (Power of Blood, by tier) only for this game's local participant (x20)."""
    a = C.Asm(start)
    a(lambda pc, L: C.adrp(pc, 8, GD_G))                      # the replaced adrp, re-done
    a(C.ldr_x(8, 8, C.lo12(GD_G)))
    a(C.ldrb(8, 8, 0xBDA))
    a(C.to(C.cbnz_w, 8, 'lot'))                               # offline: stock
    a(lambda pc, L: C.adrp(pc, 8, WCM_G))
    a(C.ldr_x(8, 8, C.lo12(WCM_G)))
    a(C.to(C.cbz_x, 8, 'nolot'))
    a(C.ldr_x(8, 8, 0x1A8))
    a(C.cmp_xr(8, 20))
    a(C.to(C.bne, 'nolot'))
    a.label('lot')
    a.many(lambda pc, L: C.far_return(pc, 0x1020F4C, 'x16'))
    a.label('nolot')
    a.many(lambda pc, L: C.far_return(pc, 0x1020FFC, 'x16'))
    return a


def place(tag, build, purpose):
    n = len(build(C.FAR_LO).words())                          # lengths do not depend on the start
    start = g.alloc(tag, 'FAR_CODE', (n * 4 + 15) // 16 * 16, purpose)
    a = build(start)
    return start, g.cave(tag, start, a)


INV, inv_recs = place('INV', inv_asm, 'Trespasser self-invite at Activate (trespasser_notes 6b)')
VOWN, vown_recs = place('VOWN', vown_asm, 'Trespasser Virtue 130000 only for the local player (6c)')
LOWN, lown_recs = place('LOWN', lown_asm, 'Trespasser item lot only for the local player (6c)')

groups = {'COOP2_CAVES': inv_recs + vown_recs + lown_recs}
groups['COOP2_REWARD_OWN'] = (
    g.far_hook(0x102100C, 'cbz x0, #0x1020d20', VOWN, 'x16',
               why='right after `blr x8` (0x1021008); ' + WHY_END, note='Virtue 130000 only into the local pgd')
    + g.far_hook(0x1020F3C, 'adrp x8, #0x5b65000', LOWN, 'x16',
                 why='right after `bl 0xdf3920` (0x1020F38); ' + WHY_END,
                 note='item lot (Power of Blood) for the local participant'))
groups['COOP2_INVITE'] = g.far_hook(
    0x101FFE0, 'mov x0, x19', INV, 'x16', link=True,
    why='next word is `bl 0x101fc28` (x30 and x16 dead: written by that call/veneer); ' + WHY_ACT,
    note='Activate: invite the local player if near and not in')

ORDER = ['COOP2_CAVES', 'COOP2_REWARD_OWN', 'COOP2_INVITE']
print('\n'.join(g.listing))
if DRY:
    sys.exit('dry run: nothing claimed or written')
C.write_live('coop2_live.py', groups, ORDER, """
Co-op Trespasser groups on the far cave region (generated by coop2_gen.py; design trespasser_notes.md 6, port
coop2_notes.md). Supersede JS_COOP_CAVES / JS_REWARD_OWN / JS_INVITE of trespasser_live.py (never apply those).
Needs JS_ISBATTLE_PARK + JS_HOST (live) or JS_HOST_BUILD (build) from trespasser_live.py FIRST, and the cave
region mapped (loader log 'Duskbloods cave region mapped'). Order: COOP2_CAVES, COOP2_REWARD_OWN, COOP2_INVITE.
Apply on EVERY game. Not live-tested.""")
cpp = []
for name in ORDER:
    d, r = C.cpp_rows(name, groups[name])
    cpp.append('// ===== %s declarations\n%s\n// ===== %s rows\n%s' % (name, d, name, r))
print('\n'.join(cpp))


def notes_section(key, body):
    """Replace the text between the BEGIN/END markers of `key` in coop2_notes.md."""
    p = C.os.path.join(C.HERE, 'coop2_notes.md')
    txt = open(p, encoding='utf-8').read()
    b, e = '<!-- BEGIN %s -->' % key, '<!-- END %s -->' % key
    i, j = txt.index(b) + len(b), txt.index(e)
    open(p, 'w', encoding='utf-8').write(txt[:i] + '\n```cpp\n' + body + '\n```\n' + txt[j:])
    print('coop2_notes.md: section "%s" rewritten' % key)


notes_section('coop2 cpp rows', '\n'.join(cpp))
