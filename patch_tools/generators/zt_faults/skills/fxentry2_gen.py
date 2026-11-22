"""fxentry2_gen (proposed for alpha 19, NOT BAKED): FX_ENTRY2 - NetChrIns::ApplySpecialEffect 0xE8BBC0 also sends the
SEVEN-digit skill family 1400000..1449999 from every caller, except the three ids that enemies carry.

Why [V data, skills_scan / this folder]:
  - FX_ENTRY (alpha 18, built in) sends only 140000..149999 from every caller. BLINK2 (alpha 17) sends 1400000..1449999
    only from the TAE handler site 0x194B8A8.
  - Seven-digit skill effects applied by OTHER callers stay local:
      Blink 1401000 / 1401001 / 1401002 (VFX 140100, 24 / 32 / 40 s) via BehaviorParam_PC 104010600 / 104011600 /
      104012600 (+0xC) and TribeActionParam 40100000 +0x124..+0x12C; 1401030 (TribeAction +0xB0);
      Darkmoon 1444000 (VFX 144400) via BehaviorParam_PC 104440600 and TribeAction 44400000 +0x10; 1444020 / 030 / 040
      / 041 (TribeAction); Neb-ra 1407000 (TribeAction +0xB0); Saurian 1406030 / 1406031 (TribeAction).
    The behaviour / bullet path applies with `mov w5, #1` (0x18C7B6C is one of the local-only callers).
  - Enemies: of the 306 SpEffectParam2 rows in 1400000..1449999 only 1415090 (NpcParam, EquipParamProtector),
    1425010 (NpcParam) and 1441030 (NpcParam) are referenced outside player params. They stay local.
  - With w5 = 0 the function still sends only for the local player's chr (vt+0x78() == 0, fxentry_gen notes).
FX_ENTRY2: a new far cave; the built-in trampoline 0xE0E4C4..0xE0E4CC is re-pointed at it (3 UPDATEs); the hook word
0xE8BBC0 and the old FXENTRY cave stay (old cave unused). Only x16 / x17 are used (free at a function entry).
    python -I fxentry2_gen.py            dry (default): writes fxentry2_records_DRY.py here
    python -I fxentry2_gen.py --claim    LEAD ONLY: claims the FAR_CODE row, writes fxentry2_live.py here
Bake: tools/add_dusk_records.py <live> FXENTRY2_CAVE, then tools/update_dusk_records.py <live> FXENTRY2_TRAMP."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

CLAIM = '--claim' in sys.argv
OUT = os.path.join(HERE, 'fxentry2_live.py' if CLAIM else 'fxentry2_records_DRY.py')
SITE, BACK, PAD = 0xE8BBC0, 0xE8BBC4, 0xE0E4C4
LO6, SPAN6 = 140000, 10000
LO7, SPAN7 = 1400000, 50000
ENEMY_IDS = (1415090, 1425010, 1441030)
PACIBSP = 0xD503237F


def sub_wr(rd, rn, rm):
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


# the built-in FX_ENTRY this relies on
assert C.dis1(SITE, C.shipped_word(SITE)) == 'b #0x%x' % PAD, 'FX_ENTRY hook is not built in'
assert C.dis1(PAD + 8, C.shipped_word(PAD + 8)) == 'br x16'
assert C.dis1(BACK, C.text_word(BACK)) == 'sub sp, sp, #0x110'
assert C.dis1(SITE, C.text_word(SITE)) == 'pacibsp'


def asm(start):
    a = C.Asm(start)
    a(C.to(C.cbz_x, 'x1', 'skip'))
    a(C.ldr_w(16, 1, 0))                                     # id
    a(C.movz_w(17, LO6 & 0xFFFF))
    a(C.movk_w(17, LO6 >> 16, 1))
    a(sub_wr(16, 16, 17))
    a(C.movz_w(17, SPAN6))
    a(C.cmp_wr(16, 17))
    a(C.to(C.bcond, 'lo', 'send'))                           # 140000..149999 (FX_ENTRY, unchanged)
    a(C.ldr_w(16, 1, 0))
    a(C.movz_w(17, LO7 & 0xFFFF))
    a(C.movk_w(17, LO7 >> 16, 1))
    a(sub_wr(16, 16, 17))
    a(C.movz_w(17, SPAN7))
    a(C.cmp_wr(16, 17))
    a(C.to(C.bcond, 'hs', 'skip'))                           # not 1400000..1449999
    for e in ENEMY_IDS:
        a(C.movz_w(17, e - LO7))
        a(C.cmp_wr(16, 17))
        a(C.to(C.bcond, 'eq', 'skip'))                       # carried by enemies: stays local
    a.label('send')
    a(C.movz_w(5, 0))                                        # w5 = 0: sent to the copies
    a.label('skip')
    a(PACIBSP)                                               # the displaced entry word
    a.many(lambda pc, L: C.far_return(pc, BACK, 'x16'))
    return a


g = C.Gen('fxentry2_gen', out=os.path.basename(OUT), dry=not CLAIM)
rows = C.read_registry()
if not any(r['tag'] == 'GEOMID' for r in rows):     # keep the dry address after the (also dry) GEOMID cave
    g._dry_rows.append(dict(owner='geomid_gen', tag='GEOMID', lo=0xC50498C, hi=0xC5049DC, purpose='dry'))
n = len(asm(0xC500000).words())
start = g.alloc('FXENTRY2', 'FAR_CODE', (n * 4 + 15) // 16 * 16,
                'FX_ENTRY2 0xE8BBC0: skill SpEffects 140000..149999 and 1400000..1449999 (not 1415090 / 1425010 / '
                '1441030) are sent to the copies from every caller; trampoline 0xE0E4C4 re-pointed; old FXENTRY unused')
cave = g.cave('FXENTRY2', start, asm(start))
tramp = []
for k, w in enumerate(C.far_jump(PAD, start)):
    old = C.shipped_word(PAD + 4 * k)
    g.listing.append('  0x%x  %s  ->  %s   (UPDATE of the built-in trampoline)' % (
        PAD + 4 * k, C.dis1(PAD + 4 * k, old), C.dis1(PAD + 4 * k, w)))
    tramp.append((PAD + 4 * k, '00000000', C.hexw(w), True))
groups = {'FXENTRY2_CAVE': cave, 'FXENTRY2_TRAMP': tramp}
ORDER = ['FXENTRY2_CAVE', 'FXENTRY2_TRAMP']
print('\n'.join(g.listing))
C.write_live(OUT, groups, ORDER, """
FX_ENTRY2, proposed alpha 19 (generated by diag/net/zt_faults/skills/fxentry2_gen.py%s): ApplySpecialEffect
0xE8BBC0 sends 140000..149999 and 1400000..1449999 (except 1415090 / 1425010 / 1441030) to the copies from every caller.
New far cave; the built-in trampoline 0xE0E4C4..0xE0E4CC is re-pointed (UPDATE). Apply on EVERY game.
Expected: fx_probe AB: the watcher's copy of Jan shows +fx 1401000 (Blink), of Trang +fx 1444000 (Darkmoon).""" % (
    '' if CLAIM else ', DRY'))
print('cave 0x%X (%d words); %s' % (start, n, 'CLAIMED' if CLAIM else 'DRY'))
print('registry row: | fxentry2_gen | FXENTRY2 | 0x%X..0x%X | ... |' % (start, start + (n * 4 + 15) // 16 * 16))
