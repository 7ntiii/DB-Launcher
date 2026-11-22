"""credit2_gen: the kill-credit and Collector-once groups of credit_gen.py (credit_notes.md) re-created on the far
cave infrastructure (cave_lib). Static only: reads nso/*.bin, patch_manager.cpp, every *_live.py and
cave_registry.md; claims its ranges in cave_registry.md; writes credit2_live.py; prints a capstone listing and the
patch_manager.cpp rows (cave_lib.cpp_rows).        python credit2_gen.py [--dry]   (from diag/net)

The old KILL_CAVES / KILL_OWNER / COLLECT_CAVE / COLLECT_ONCE of credit_live.py target main+0x6B32000.. (not a
mapped address: patch_manager rejects it). They are SUPERSEDED by:
  KILL2_CAVES     SEND3C  relocated copy of the 0x3B sender 0x14E1334 (type 0x3C, broadcast vt+0x40); its three
                          external bl become far_call (adrp/add/blr x16), internal branches re-targeted
                  GATE    death handler 0x1752400 entry gate (owner decides, others wait for the 0x3C answer)
                  READ    0x3C reader: skip a victim already handled (bit 54)
  KILL2_OWNER     0x175242C `tbnz x9,#52` -> b tramp -> GATE ; 0x1752278 `bl 0x14e1590` -> nop ;
                  0x17E8EE0 `ldr x8,[x8,#0x60]` -> #0x50 ; 0x17E8F2C `cbz x0` -> b tramp -> READ
  COLLECT2_CAVE   Collector add 0x15B52E0 skipped for a copy pgd (wp+0x11 != 0)
  COLLECT2_ONCE   0x15A5544 `b 0x15b52e0` (tail call) -> b tramp -> COLLECT
Design unchanged (credit_notes.md 1-3); only addresses and long branches change."""
import re
import struct
import sys

import cave_lib as C

ENEMY_VT = 0x572B108
MGR3 = 0x5B3CE08                               # *(main+0x5B3CE08) = mgr3, +0x1268 = mode (6 in LAN)
WCM_GOT = 0x59DFE68                            # GOT slot -> WCM pointer variable (0x1752464 / 0x175246C)


def ctx(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)


def func_end(s):
    assert C.text_word(s) == 0xD503237F, 'no pacibsp at %x' % s
    a = s + 4
    while C.text_word(a) != 0xD503237F:
        a += 4
    return a


def no_ip_regs(s, sites):
    """Assert x16/x17 are not named by ANY instruction of the function at s: x16 holds nothing live at any hook
    site or far_return target inside it (and AAPCS64 makes x16/x17 corruptible across calls anyway)."""
    e = func_end(s)
    for a in range(s, e, 4):
        t = C.dis1(a, C.text_word(a))
        assert not re.search(r'\b[xw]1[67]\b', t.split(' ', 1)[-1] if ' ' in t else ''), 'x16/x17 at %x: %s' % (a, t)
    for x in sites:
        assert s <= x < e, '%x not inside function %x..%x' % (x, s, e)
    return 'function 0x%X..0x%X never names x16/x17 (scanned)' % (s, e)


# ================================================================ facts the design depends on [V] (as credit_gen)
for a, t in (
        (0x1752258, 'cmp w10, #6'), (0x175225C, 'b.ne #0x17522b4'), (0x1752260, 'tbnz w9, #0x19, #0x17522f4'),
        (0x1752264, 'ldr w9, [x0, #0x78]'), (0x175227C, 'b #0x17522f4'), (0x14E167C, 'mov w1, #0x3c'),
        (0x14E1680, 'ldr x8, [x8, #0x48]'), (0x14E1620, 'bl #0x14fc3fc'),
        (0x17522E0, 'orr w8, w8, #0x10000'), (0x17522F0, 'bl #0x1752400'),
        (0x175241C, 'mov w8, #0x12bc'), (0x1752420, 'mov x19, x0'), (0x1752424, 'add x8, x0, x8'),
        (0x1752428, 'ldr x9, [x8]'), (0x1752430, 'ldur w10, [x8, #9]'), (0x1752434, 'and x11, x9, #0x60000000000000'),
        (0x1752438, 'mov x12, #0x20000000000000'),                  # x10/x11/x12 written before read at 0x1752430
        (0x1752440, 'and x10, x10, #0x10000'), (0x175244C, 'b #0x1752b84'),
        (0x1752450, 'and x10, x9, #0x60000000000000'), (0x1752454, 'mov x11, #0x20000000000000'),
        (0x1752458, 'cmp x10, x11'), (0x175245C, 'b.ne #0x1752b84'),
        (0x1752460, 'orr x9, x9, #0x40000000000000'), (0x1752468, 'str x9, [x8]'),
        (0x1752470, 'ldr x0, [x22]'), (0x1752478, 'ldr x8, [x19, #0x20]'),
        (0x1752B84, 'ldp x20, x19, [sp, #0x90]'), (0x1752B98, 'retab'),
        (0x1752410, 'stp x22, x21, [sp, #0x80]'), (0x1752408, 'stp x29, x30, [sp, #0x60]'),
        (0x175ED54, 'orr x8, x8, #0x10000000000000'), (0x175ED60, 'bl #0x1752400'),
        (0x174EB30, 'orr x9, x9, #0x20000000000000'), (0x174EB44, 'b #0x1752400'),
        (0x17E8ED8, 'mov w1, #0x3c'), (0x17E8EE4, 'mov x4, xzr'), (0x17E8F18, 'ldrh w8, [sp, #0x4a2]'),
        (0x17E8F28, 'bl #0x17e7828'), (0x17E8F30, 'ldr w8, [x0, x24]'), (0x17E8F38, 'ldrh w1, [sp, #0x4a0]'),
        (0x17E8F3C, 'orr w8, w8, #0x10000'), (0x17E8F48, 'bl #0xe8e67c'), (0x17E8F50, 'bl #0x1752400'),
        (0x17E8F54, 'ldr x8, [x26]'), (0x17E8E94, 'mov w24, #0x12c5'),
        (0x14ECC7C, 'bl #0x19d7b60'), (0x14ECC94, 'bl #0x19d7b60'),
        (0x19D7CBC, 'adrp x8, #0x5b97000'), (0x19D7CC0, 'add x8, x8, #0x2cc'),
        (0x14FC2D8, 'ldr x11, [x11, #0x2a8]'), (0x14FC340, 'ldrh w9, [x20, #2]'),
        (0x17EE548, 'ldr x9, [x20, #0x540]'), (0x17EE5A0, 'ldrsh w8, [x9, x8, lsl #1]'),
        (0x17EE5A8, 'cset w20, ge'),
        (0x15A551C, 'mov x0, x19'), (0x15A5520, 'mov x1, x20'), (0x15A5540, 'autibsp'),
        (0x15B52FC, 'cbz x1, #0x15b53ac'), (0x15B5300, 'adrp x8, #0x5b3c000'),
        (0x15A45D4, 'sub w8, w8, #0x989, lsl #12'), (0x15A45DC, 'sub w8, w8, #0x680'), (0x15A45E4, 'cmp w8, #0x27'),
        (0x15A41E8, 'stur w23, [x29, #-0x34]'), (0x15A3F38, 'mov x23, x2'),
        (0x159D7FC, 'ldr w28, [x8, #0xd0]'), (0x159D80C, 'csel w24, w28, w24, eq')):
    ctx(a, t)
# x9 is not read in the reader loop 0x17E8E9C..0x17E8F5C (READ cave uses it)
for a in range(0x17E8E9C, 0x17E8F5C, 4):
    t = C.dis1(a, C.text_word(a))
    assert not re.search(r'[, \[]x9\b|[, \[]w9\b', ' ' + t.split(' ', 1)[-1]), 'x9 used in reader at %x: %s' % (a, t)
assert struct.unpack_from('<Q', C.DATA, 0x59E92A8 - C.DATA_BASE)[0] == 0x5B972CC, 'handle table GOT'
assert C.RO[0x4C4B3AC - C.RO_BASE + 8 * 0x3C + 4] == 0x00, '0x3C routing byte'
assert not any(a in C.SHIPPED for a in range(0x4C4B3AC + 8 * 0x3C, 0x4C4B3AC + 8 * 0x3D))

WHY_DH = no_ip_regs(0x1752400, [0x175242C, 0x1752430, 0x1752450, 0x1752460, 0x1752B84])   # death handler
WHY_RD = no_ip_regs(0x17E7B60, [0x17E8F2C, 0x17E8F30, 0x17E8F54])                         # 0x3C reader
WHY_AW = no_ip_regs(0x15A5020, [0x15A5544])                                               # award apply
WHY_CA = no_ip_regs(0x15B52E0, [0x15B52E0])                                               # Collector add
WHY_SD = no_ip_regs(0x14E1334, [0x14E1334])                                               # copied sender

# ---------------------------------------------------------------- generator object; superseded old words
DRY = '--dry' in sys.argv
g = C.Gen('credit2_gen', out='credit2_live.py', dry=DRY)
SUPERSEDED = (0x175242C, 0x1752278, 0x17E8EE0, 0x17E8F2C, 0x15A5544)   # old KILL_OWNER / COLLECT_ONCE words
for s in SUPERSEDED:
    for i in range(4):
        assert g.others.get(s + i) in (None, 'credit_live.py'), '%x held by %s' % (s, g.others.get(s + i))
        g.others.pop(s + i, None)

# ================================================================ SEND3C: relocated copy of 0x14E1334
S0, S1 = 0x14E1334, 0x14E1468                    # 0x14E1468 = next pacibsp
assert C.text_word(S0) == 0xD503237F and C.text_word(S1) == 0xD503237F
ctx(0x14E134C, 'strh w1, [x29, #0x1c]')
ctx(0x14E1354, 'strh w2, [x29, #0x1e]')
ctx(0x14E13C0, 'bl #0x14fc280')
ctx(0x14E141C, 'mov w1, #0x3b')
ctx(0x14E1420, 'ldr x8, [x8, #0x48]')
ctx(0x14E1464, 'bl #0x472ca08')


def _sx(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def internal_target(a, w):
    """Target of a b.cond / cbz / cbnz / tbz / tbnz / b / bl at a, or None for other words."""
    if (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:
        return a + _sx((w >> 5) & 0x7FFFF, 19) * 4, 19
    if (w & 0x7E000000) == 0x36000000:
        return a + _sx((w >> 5) & 0x3FFF, 14) * 4, 14
    return None


def send_asm(start):
    a = C.Asm(start)
    for x in range(S0, S1, 4):
        w = C.text_word(x)
        a.label('o%X' % x)
        if x == 0x14E141C:
            a(C.movz_w(1, 0x3C))                                  # type 0x3B -> 0x3C
            continue
        if x == 0x14E1420:
            a(C.ldr_x(8, 8, 0x40))                                # send-to-server vt+0x48 -> broadcast vt+0x40
            continue
        it = internal_target(x, w)
        if it:
            t, bits = it
            assert S0 <= t < S1, 'external conditional branch at %x' % x
            mask = ((1 << bits) - 1) << 5
            a(lambda pc, L, w=w, t=t, bits=bits, mask=mask:
              (w & ~mask) | (C._rel(pc, L['o%X' % t], bits) << 5))
            continue
        if (w & 0x7C000000) == 0x14000000:                        # b / bl: all external here
            imm = w & 0x3FFFFFF
            t = x + _sx(imm, 26) * 4
            assert not (S0 <= t < S1), 'internal b/bl at %x' % x
        a.many(lambda pc, L, x=x: C.relocate(x, pc, 'x16'))      # adrp re-based, bl -> far_call, rest as is
    return a


# ================================================================ GATE (death handler entry)
def gate_asm(start, send):
    a = C.Asm(start)
    a(C.ldr_x(10, 19, 0))                                         # vtable of the dying chr
    a(lambda pc, L: C.adrp(pc, 11, ENEMY_VT))
    a(C.add_xi(11, 11, C.lo12(ENEMY_VT)))
    a(C.cmp_xr(10, 11))
    a(C.to(C.bne, 'ORIG'))                                        # not enemy-class (players, objects): original
    a(lambda pc, L: C.adrp(pc, 10, MGR3))
    a(C.ldr_x(10, 10, C.lo12(MGR3)))
    a(C.to(C.cbz_x, 10, 'ORIG'))                                  # no session manager (offline): original
    a(C.ldr_w(10, 10, 0x1268))
    a(C.cmp_wi(10, 6))
    a(C.to(C.bne, 'ORIG'))                                        # not mode 6: original
    a(C.text_word(0x1752450))                                     # and x10, x9, #0x60000000000000
    a(C.text_word(0x1752454))                                     # mov x11, #0x20000000000000
    a(C.text_word(0x1752458))                                     # cmp x10, x11
    a(C.to(C.bne, 'RETW'))                                        # not dying, or handled already: return, no latch
    a(lambda pc, L: C.adrp(pc, 10, WCM_GOT))
    a(C.ldr_x(10, 10, C.lo12(WCM_GOT)))
    a(C.ldr_x(0, 10, 0))                                          # x0 = WCM
    a(C.to(C.cbz_x, 0, 'NOTOWN'))
    a(C.mov_x(1, 19))
    a.many(lambda pc, L: C.far_call(pc, 0x17EE470, 'x16'))      # owner of this enemy? (x30 saved at 0x1752408)
    a(lambda pc, L: C.tbz(pc, 0, 0, L['NOTOWN']))
    a(C.ldr_x(10, 19, 0x20))                                      # chr data
    a(C.ldr_w(1, 10, 0x114))                                      # killer = this game's last attacker
    a(C.ldr_w(2, 10, 0x78))                                       # victim handle
    a(lambda pc, L: C.bl(pc, send))                               # broadcast 0x3C {killer, victim} (far -> far)
    a(C.to(C.b, 'RELOAD'))
    a.label('NOTOWN')
    a(C.add_xi(8, 19, 1, True))                                   # x8 = chr + 0x12BC
    a(C.add_xi(8, 8, 0x2BC))
    a(C.ldur_w(10, 8, 9))
    a(lambda pc, L: C.tbz(pc, 10, 16, L['RETW']))                 # no answer from the owner yet: wait (no latch)
    a(C.ldr_x(9, 8, 0))
    a.many(lambda pc, L: C.far_return(pc, 0x1752460, 'x16'))    # answered: handle it with the owner's killer
    a.label('RELOAD')                                             # owner, after the calls
    a(C.add_xi(8, 19, 1, True))
    a(C.add_xi(8, 8, 0x2BC))
    a(C.ldr_x(9, 8, 0))
    a.many(lambda pc, L: C.far_return(pc, 0x1752460, 'x16'))
    a.label('ORIG')                                               # the replaced tbnz x9, #52, 0x1752450
    a.many(lambda pc, L: C.relocate(0x175242C, pc, 'x16'))      # tbz x9,#52,+16 ; far_jump 0x1752450
    a.many(lambda pc, L: C.far_return(pc, 0x1752430, 'x16'))    # bit 52 clear: fall through
    a.label('RETW')
    a.many(lambda pc, L: C.far_return(pc, 0x1752B84, 'x16'))    # common return, no latch
    return a


# ================================================================ READ (0x3C reader)
def read_asm(start):
    a = C.Asm(start)
    a(C.to(C.cbz_x, 0, 'next'))                                   # the replaced cbz x0, 0x17E8F54
    a(C.add_xi(16, 0, 1, True))                                   # x16 = chr + 0x1000
    a(C.ldrb(9, 16, 0x2C2))                                       # byte chr+0x12C2: bit 6 = bit 54 of +0x12BC (handled)
    a(lambda pc, L: C.tbnz(pc, 9, 6, L['next']))
    a(C.ldrb(9, 16, 0x2C7))                                       # byte chr+0x12C7: bit 0 = bit 16 of +0x12C5 (answer applied)
    a(lambda pc, L: C.tbnz(pc, 9, 0, L['next']))
    a.many(lambda pc, L: C.far_return(pc, 0x17E8F30, 'x16'))
    a.label('next')
    a.many(lambda pc, L: C.far_return(pc, 0x17E8F54, 'x16'))    # no victim / handled / answered already: next message
    return a


# ================================================================ COLLECT (Collector add, own pgd only)
def collect_asm(start):
    a = C.Asm(start)
    a(C.to(C.cbz_x, 1, 'add'))                                    # null pgd: the add handles it (0x15B52FC)
    a(C.ldr_x(8, 1, 0x46D8))
    a(C.to(C.cbz_x, 8, 'add'))
    a(C.ldrb(8, 8, 0x11))
    a(C.to(C.cbnz_w, 8, 'skip'))                                  # copy pgd: no Collector add
    a.label('add')
    a.many(lambda pc, L: C.far_jump(pc, 0x15B52E0, 'x16'))      # the replaced tail call
    a.label('skip')
    a(C.RET)                                                      # x30 = caller's return (autibsp done)
    return a


def place(tag, build, purpose, *extra):
    n = len(build(C.FAR_LO, *extra).words())                      # lengths do not depend on the start
    start = g.alloc(tag, 'FAR_CODE', (n * 4 + 15) // 16 * 16, purpose)
    return start, g.cave(tag, start, build(start, *extra))


SEND, send_recs = place('SEND3C', send_asm, 'copy of the 0x3B sender 0x14E1334 as 0x3C broadcast (credit_notes 2)')
GATE, gate_recs = place('GATE', gate_asm, 'death handler 0x1752400 entry gate: enemy owner decides (credit_notes 2)',
                        SEND)
READ, read_recs = place('READ', read_asm, '0x3C reader: skip victims already handled (credit_notes 2)')
COLL, coll_recs = place('COLLECT', collect_asm, 'Collector add only into the own pgd (credit_notes 3)')

groups = {'KILL2_CAVES': send_recs + gate_recs + read_recs}
groups['KILL2_OWNER'] = (
    g.far_hook(0x175242C, 'tbnz x9, #0x34, #0x1752450', GATE, 'x16',
               why='function prologue (entry 0x1752400 -> here, no call); ' + WHY_DH,
               note='death handler entry -> owner gate')
    + [g.text_patch(0x1752278, 'bl #0x14e1590', C.NOP, 'no 0x3C request to the server (its self echo was misread)'),
       g.text_patch(0x17E8EE0, 'ldr x8, [x8, #0x60]', C.ldr_x(8, 8, 0x50), '0x3C answer from anyone (the owner)')]
    + g.far_hook(0x17E8F2C, 'cbz x0, #0x17e8f54', READ, 'x16',
                 why='right after `bl 0x17e7828` (0x17E8F28); ' + WHY_RD,
                 note='reader: skip a victim already handled'))
groups['COLLECT2_CAVE'] = coll_recs
groups['COLLECT2_ONCE'] = g.far_hook(
    0x15A5544, 'b #0x15b52e0', COLL, 'x16',
    why='tail call to the function entry 0x15B52E0 (x16/x17 never live at an entry); ' + WHY_AW + '; ' + WHY_CA,
    note='Collector add skipped for copies (wp+0x11 != 0)')

ORDER = ['KILL2_CAVES', 'KILL2_OWNER', 'COLLECT2_CAVE', 'COLLECT2_ONCE']
print('\n'.join(g.listing))
print('SEND3C scratch: ' + WHY_SD)
if DRY:
    sys.exit('dry run: nothing claimed or written')
C.write_live('credit2_live.py', groups, ORDER, """
Kill-credit (enemy owner decides) and Collector-once groups on the far cave region (generated by credit2_gen.py;
design credit_notes.md, port coop2_notes.md). Supersede KILL_CAVES / KILL_OWNER / COLLECT_CAVE / COLLECT_ONCE of
credit_live.py (never apply those). Needs the cave region mapped. Order: KILL2_CAVES, KILL2_OWNER, COLLECT2_CAVE,
COLLECT2_ONCE. Apply on EVERY game (a game without KILL2_OWNER credits its own last hit). Not live-tested.""")
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


notes_section('credit2 cpp rows', '\n'.join(cpp))
