"""noecho_cd_gen.py (DRY by default): NOECHO_CD - other players' SpEffects (message 0xCD) reach their copies again.

Cause (diag/net/zt_faults/dash, report in the lead's handoff): EFFECT_NO_ECHO (shipped, 0x14FAC68
`tbz w22,#0,0x14FACE8` -> `b 0x14FACE8`) gives 0xCD the validation of 0x1B. For a target that is not our player
that validation returns NetChrIns vt+0x30 (0x14FAD44..0x14FAD68), and the player class's vt+0x30 (0xE92790) is 0
for every ordinary remote player (u8 data+0x1A5; 1 only for player numbers 10000000..10000039). The receiver
0x17E7520 skips the message on 0 (0x17E7640). So since the heal fix every 0xCD is dropped: the effects the owner
applies with w5 = 0 (TAE event 66: Vanish Dash 142643, Blink 1401010 / 1401020 / 1401021, ...) never reach a copy.
Event-67 effects (w5 = 1) are applied by each copy's own TAE and still show.

Two variants (same goal; pick one, never both):
  A (default) = replaces the shipped EFFECT_NO_ECHO word. 0x14FAC68 -> trampoline -> cave:
        tbz w22, #0, ->0x14FACE8          0x1B: stock path
        ldr x16, [x20, #0x1A8]            x20 = WCM (non-null: checked at 0x14FAC4C), x0 = the target chr (0x17E7828)
        cmp x16, x0 ; b.ne ->0x14FAC6C    0xCD about another chr: the STOCK 0xCD check (sender owns that chr)
        ->0x14FAD88                       0xCD about our own player (our own echo): return 0 = dropped
     Exactly stock except that our own echo is dropped (what EFFECT_NO_ECHO was for).
     The lead removes EFFECT_NO_ECHO (BuiltinPatchRecord{0x14FAC68, ...}) and adds these records instead.
  B (--variant B) = keeps EFFECT_NO_ECHO; 0x14FAD18 `ldr x8, [x19]` (0x1B path, right after the "target is our
     player -> 0" test) -> trampoline -> cave:
        tbz w22, #0, ->stock              0x1B: the stock word, back to 0x14FAD1C
        ->0x14FAD6C                       0xCD about any chr that is not our player: return 1 = accepted
     No sender check (any 0xCD about a remote chr is taken; also an attacker's 0xCD about a victim's copy,
     which stock drops on third games).
x16 / x17 are never used in 0x14FAC20..0x14FADE0 (asserted) and the site follows a bl (A) or is in a
straight block after loads (B); x16 is the far-jump scratch.
    python -I noecho_cd_gen.py [--variant A|B] [--claim]   (from anywhere; dry = writes noecho_cd_<V>_records_DRY.py here)"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import cave_lib as C  # noqa: E402

CLAIM = '--claim' in sys.argv
VAR = sys.argv[sys.argv.index('--variant') + 1].upper() if '--variant' in sys.argv else 'A'
assert VAR in ('A', 'B')
OUT = os.path.join(HERE, ('noecho_cd_%s_live.py' if CLAIM else 'noecho_cd_%s_records_DRY.py') % VAR)
FN_LO, FN_HI = 0x14FAC20, 0x14FADE0

# ---- context (stock text) ----------------------------------------------------------------------------------------
for a, t in ((0x14FAC50, 'mov w22, w1'), (0x14FAC5C, 'bl #0x17e7828'), (0x14FAC60, 'cbz x0, #0x14fad70'),
             (0x14FAC64, 'ldr x20, [x23]'), (0x14FAC68, 'tbz w22, #0, #0x14face8'), (0x14FAC6C, 'cbz x20, #0x14fad90'),
             (0x14FACE8, 'cbz x20, #0x14fad90'), (0x14FAD04, 'ldr x19, [x0, #0x20]'),
             (0x14FAD14, 'b.eq #0x14fad88'), (0x14FAD18, 'ldr x8, [x19]'), (0x14FAD1C, 'mov x0, x19'),
             (0x14FAD6C, 'mov w0, #1'), (0x14FAD88, 'mov w0, wzr'), (0x17E7640, 'tbz w0, #0, #0x17e7760')):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'context %x: %s, expected %s' % (a, got, t)
for a in range(FN_LO, FN_HI, 4):
    txt = C.dis1(a, C.text_word(a))
    assert not re.search(r'\b[wx]1[67]\b', txt.replace('#0x', '#')), 'x16/x17 used at %x: %s' % (a, txt)
    if FN_LO < a < 0x14FAD18 and a != 0x14FAC50:     # w22 = w1 at 0x14FAC50, never written again before B's site
        assert not C.dis1(a, C.text_word(a)).startswith(('mov w22', 'ldr w22', 'ldr x22', 'mov x22')) or \
            a in (0x14FAC84,), 'w22 written at %x' % a
# 0x14FAC84 `mov x22, xzr` is only in the stock 0xCD loop (0x14FAC6C..0x14FACE4), never on the way to 0x14FAD18
assert C.dis1(0x14FAC84, C.text_word(0x14FAC84)) == 'mov x22, xzr'
assert C.shipped_word(0x14FAC68) == 0x14000020, 'EFFECT_NO_ECHO is not the shipped word at 0x14FAC68'

g = C.Gen('noecho_cd_gen', out=os.path.basename(OUT), dry=not CLAIM)
rows = C.read_registry()
for tag, lo, hi in (('GEOMID', 0xC50498C, 0xC5049DC), ('FXENTRY2', 0xC5049DC, 0xC504A5C)):
    if not any(r['tag'] == tag for r in rows):        # planned, keep them free
        g._dry_rows.append(dict(owner='planned', tag=tag, lo=lo, hi=hi, purpose='planned (dry)'))


def asm_a(start):
    a = C.Asm(start)
    a(C.to(C.tbz, 'w22', 0, 'l1b'))
    a(C.ldr_x(16, 20, 0x1A8))
    a(C.cmp_xr(16, 0))
    a(C.to(C.bne, 'cd'))
    a.many(lambda pc, L: C.far_return(pc, 0x14FAD88, 'x16'))   # our own echo: return 0
    a.label('cd')
    a.many(lambda pc, L: C.far_return(pc, 0x14FAC6C, 'x16'))   # stock 0xCD check
    a.label('l1b')
    a.many(lambda pc, L: C.far_return(pc, 0x14FACE8, 'x16'))   # stock 0x1B path
    return a


def asm_b(start):
    a = C.Asm(start)
    a(C.to(C.tbz, 'w22', 0, 'l1b'))
    a.many(lambda pc, L: C.far_return(pc, 0x14FAD6C, 'x16'))   # 0xCD, not our player: accepted
    a.label('l1b')
    a(C.text_word(0x14FAD18))                                   # ldr x8, [x19] (position independent)
    a.many(lambda pc, L: C.far_return(pc, 0x14FAD1C, 'x16'))
    return a


asm = asm_a if VAR == 'A' else asm_b
SITE = 0x14FAC68 if VAR == 'A' else 0x14FAD18
TEXT = 'tbz w22, #0, #0x14face8' if VAR == 'A' else 'ldr x8, [x19]'
n = len(asm(0xC500000).words())
FAR_AT = 0xC504A5C        # the lead's map: FAR_CODE free from here (GEOMID, FXENTRY2 planned below it)
start = g.claim('NOECHO_CD', FAR_AT, (n * 4 + 15) // 16 * 16,
                'NOECHO_CD %s: 0xCD from other players reaches their copies again; own echo dropped' % VAR)
cave = g.cave('NOECHO_CD', start, asm(start))
# NEAR_TRAMP is full: a 3-word trampoline in text padding near the site (fxentry_gen's rules: zero words that end at
# a function's pacibsp, not after a bl, no branch / pointer into the gap, not reserved in cave_registry.md)
import struct  # noqa: E402
TW = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
RESERVED = [(int(m.group(1), 16), int(m.group(2), 16)) for m in
            re.finditer(r'RESERVED 0x([0-9A-Fa-f]+)\.\.0x([0-9A-Fa-f]+)', open(C.REGISTRY, encoding='utf-8').read())]
RESERVED.append((0xE0E4C4, 0xE0E4D0))        # FX_ENTRY / FXENTRY2 trampoline


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(TW):
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
        k = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % k, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if not all(TW[a // 4 + k] == 0 for k in range(n)) or TW[a // 4 - 1] == 0:
            continue
        z = a
        while TW[z // 4] == 0:
            z += 4
        if TW[z // 4] != 0xD503237F or C.dis1(a - 4, TW[a // 4 - 1]).startswith('bl '):
            continue
        if any(x in C.SHIPPED or x in g.others for x in range(a, a + 4 * n)):
            continue
        if any(lo < a + 4 * n and a < hi for lo, hi in RESERVED):
            continue
        if targets_in(a, z) or qwords_in(a, z):
            continue
        if C.reach(site, a):
            return a
    return None


PAD = find_pad(SITE, 3)
assert PAD, 'no trampoline padding near 0x%X' % SITE
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> NOECHO_CD 0x%X' % start)
         for k, w in enumerate(C.far_jump(PAD, start, 'x16'))]
hook = [g.text_patch(SITE, TEXT, C.b(SITE, PAD), 'NOECHO_CD %s via 0x%X (x16 dead: never used in 0x14FAC20..'
                     '0x14FADE0, asserted)' % (VAR, PAD), replaces_shipped=(VAR == 'A'))]
hook = tramp + hook
groups = {'NOECHO_CD_CAVE': cave, 'NOECHO_CD': hook}
ORDER = ['NOECHO_CD_CAVE', 'NOECHO_CD']
print('\n'.join(g.listing))
C.write_live(OUT, groups, ORDER, """
NOECHO_CD variant %s (generated by diag/net/zt_faults/dash/noecho_cd_gen.py): message 0xCD (a player's own SpEffect)
reaches that player's copies on the other games again; a game's own echo stays dropped.%s
Apply on EVERY game. Expected: fx_probe on a watching game shows +fx 142643 on the caster's copy during a
Vanish Dash, +fx 1401010 / 1401020 / 1401021 during Blink; no doubles on the caster.""" % (
    VAR, '\nREPLACES the shipped EFFECT_NO_ECHO record at 0x14FAC68 (remove that BuiltinPatchRecord).' if VAR == 'A'
    else '\nKeeps the shipped EFFECT_NO_ECHO record (0x14FAC68).'))
print('variant %s: cave 0x%X (%d words), site 0x%X; %s -> %s' % (VAR, start, n, SITE, 'CLAIMED' if CLAIM else 'DRY',
                                                                  OUT))
