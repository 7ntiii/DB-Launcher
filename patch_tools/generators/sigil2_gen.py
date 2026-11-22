"""sigil2_gen.py: Sigil (SubQuest) stage A re-built on the far cave region (cave_lib). Static only.
Reads nso/*.bin, patch_manager.cpp, every *_live.py and cave_registry.md (via cave_lib); claims its ranges in
cave_registry.md (owner sigil2_gen, stable on re-runs); writes sigil2_live.py; prints a capstone listing and the
patch_manager.cpp rows.    python sigil2_gen.py      (run from diag/net)
Design, register proofs and the live test: sigil2_notes.md. Supersedes sigil_live.py (SIGIL_A*, never together).

Groups (each list = far caves first, then NEAR_TRAMP trampolines, then the text hook LAST):
  SIGIL2_LATE   PRE   hook 0x1181E34 (SQM MatchPreprocess 0x1181D80): flag = 0 every match; LAN (offline byte
                      *(0x5B65C20)+0xBDA == 0) skips the early producer AND the reader (-> 0x1181E58);
                      offline -> stock 0x1181E3C.
                FRAME hook 0x114B9CC (entry of CSStagePhaseImp::STEP_UpdatePhase, runs every UpdatePhase frame):
                      once per match (flag), LAN, mode *(0x5B3CE08)+0x1268 == 6, local pgd with +0xD0 != -1,
                      SQM and SQM+0x28 set -> flag = 1, call the producer 0x1195E40 (own entry + targets, 0x88
                      send to all, local apply). Then the replaced pacibsp, back to 0x114B9D0.
  SIGIL2_SELF   hook 0x119610C: drops the own pgd+0xD0 from the producer's target vector [sp+8, sp+0x10).
  SIGIL2_APPLY  hook 0x1195D2C: order-independent slot 0 / slot 1 in the apply 0x1195C40.
  SIGIL2_KEEP   (optional) hook 0x1179788: the slot setter 0x1179770 ignores value -1.
  SIGIL2_NOPASSIVE (optional, deviates from the game: sigil5_notes.md) hook 0x11962C8: the producer writes no
                target entries (no counterpart quest on the targets), only the own entry with its targets.
Flag word: FAR_DATA (registry tag SIGIL2_FLAG), zero at boot, no record.
Compatible with sigil_nc_live.py SIGIL_NC_TARGET / _2C / EVAL / REPORT / PHASE (no shared word)."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'sigil2_live.py'
DRY = '--dry' in sys.argv          # --dry: check everything, claim nothing, write nothing
g = C.Gen('sigil2_gen', out=OUT, dry=DRY)
# SIGIL2_LATE / SELF / APPLY / KEEP are BUILT IN: cave_lib's free_bytes refuses shipped bytes. Allow them here; every
# group is then proven either byte-identical to the built-in words (BUILT_IN) or free of shipped bytes (end of file).
_free_orig = g.free_bytes


def _free_builtin(a, n=4, what='word'):
    for i in range(n):
        assert a + i not in g.others, '%s %x collides with %s' % (what, a, g.others[a + i])


g.free_bytes = _free_builtin
BUILT_IN = ('SIGIL2_LATE', 'SIGIL2_SELF', 'SIGIL2_APPLY', 'SIGIL2_APPLY2', 'SIGIL2_KEEP')

# sigil_live.py (old SIGIL_A, caves at the non-existent main+0x6B30000) is SUPERSEDED by this file: same hook
# words 0x119610C / 0x1195D2C / 0x1179788. Never apply both; drop it from the collision set (listed).
old = sorted(set(a & ~3 for a, f in g.others.items() if f == 'sigil_live.py' and not C.is_far(a) and a < 0x6B30000))
g.others = {a: f for a, f in g.others.items() if f != 'sigil_live.py'}
print('superseded sigil_live.py words (ignored for collisions): %s' % ', '.join('%X' % a for a in old))

# ---------------------------------------------------------------- globals (offsets from main) [V]
GDM = 0x5B57EB8      # *(GDM)+0x20 = local PlayerGameData (producer 0x1195EA4..0x1195EB0); pgd+0xD0 = player no
SQMG = 0x5B3CE18     # *(SQMG) = sub quest manager (GOT 0x59DFF30 -> 0x5B3CE18, caller 0x1149704..0x114970C)
MGR3 = 0x5B3CE08     # *(MGR3)+0x1268 == 6: LAN session mode (shipped send cave 0x563EB9C..0x563EBB0)
OFFL = 0x5B65C20     # *(OFFL)+0xBDA != 0: true offline (0x1181E38..0x1181E48)
PRODUCER = 0x1195E40

# ---------------------------------------------------------------- stock context [V]
STOCK = [
    (0x1181E34, 'ldr x0, [x19, #0x28]'), (0x1181E38, 'adrp x20, #0x5b65000'), (0x1181E3C, 'cbz x0, #0x1181e58'),
    (0x1181E40, 'ldr x8, [x20, #0xc20]'), (0x1181E44, 'ldrb w8, [x8, #0xbda]'), (0x1181E4C, 'bl #0x1195e40'),
    (0x1181E54, 'bl #0x1195b00'), (0x1181E58, 'ldr x8, [x20, #0xc20]'),
    (0x1149714, 'bl #0x1181d80'),
    (0x114B9CC, 'pacibsp'), (0x114B9D0, 'sub sp, sp, #0x50'), (0x114B9FC, 'mov x20, x1'), (0x114BA00, 'mov x19, x0'),
    (0x1195EB0, 'ldr x19, [x8, #0x20]'), (0x1195EB4, 'cbz x19, #0x11963f0'),
    (0x11960B8, 'mov w1, #0x24'), (0x11960C0, 'stp xzr, xzr, [sp, #8]'), (0x11960CC, 'bl #0xce9f40'),
    (0x119610C, 'ldp x25, x23, [sp, #8]'), (0x1196110, 'sub x8, x23, x25'), (0x1196114, 'ldrsb w9, [x21, #0x50]'),
    (0x1196118, 'asr x10, x8, #2'),
    (0x1195C84, 'mov w21, #3'), (0x1195C90, 'lsl x28, x8, #2'), (0x1195CA4, 'subs x28, x28, #0x14'),
    (0x1195D24, 'mov w9, #0x46e0'), (0x1195D28, 'add x26, x8, x9'), (0x1195D2C, 'ldur w8, [x19, #-8]'),
    (0x1195D30, 'str w8, [x26]'), (0x1195D50, 'bl #0x11825e0'), (0x1195D54, 'ldur w20, [x19, #-4]'),
    (0x1195D58, 'add x0, sp, #0x30'), (0x1195DB0, 'str w20, [x26, #4]'),
    (0x1179770, 'pacibsp'), (0x1179778, 'stp x29, x30, [sp, #0x50]'), (0x1179788, 'ldr w8, [x0, #8]'),
    (0x117978C, 'cmp w8, #9'), (0x1179790, 'b.eq #0x1179944'), (0x1179944, 'ldp x20, x19, [sp, #0x70]'),
]
for a, t in STOCK:
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)


def no_x16_x17(lo, hi):
    """Assert x16/x17 (w16/w17) appear nowhere in stock text lo..hi (register proof for the trampolines)."""
    for a in range(lo, hi, 4):
        t = C.dis1(a, C.text_word(a))
        assert not re.search(r'\b[xw]1[67]\b', t), 'x16/x17 used at %x: %s' % (a, t)


no_x16_x17(0x1181D80, 0x1181E98)   # SQM MatchPreprocess (whole function)
no_x16_x17(0x1195C40, 0x1195DFC)   # apply (whole body)
no_x16_x17(0x1195E40, 0x1196440)   # producer (whole body)
no_x16_x17(0x1179770, 0x1179958)   # slot setter (whole body)
# the step table entry 6 (main+0x5B6C7F8 + 6*0x18, written at 0x115E370/0x115E37C) is STEP_UpdatePhase
assert C.dis1(0x115E370, C.text_word(0x115E370)) == 'adr x9, #0x114b9cc'
assert C.dis1(0x115E37C, C.text_word(0x115E37C)) == 'stp x9, xzr, [x8, #0x90]'
# built-ins this relies on: send cave on the producer's apply call, reread cave per frame, own id (SIGIL_OWN)
assert C.shipped_word(0x1196404) == C.bl(0x1196404, 0x563EB90), 'SUBQUEST send hook not shipped'
assert C.shipped_word(0x1140B10) == C.bl(0x1140B10, 0x563EBE0), 'SUBQUEST reread hook not shipped'
assert C.shipped_word(0x11963CC) == C.bl(0x11963CC, 0x563EAC8), 'SIGIL_OWN own-id hook not shipped'
assert C.shipped_word(0x1181E48) == C.b(0x1181E48, 0x563EB70), 'SUBQUEST gate not shipped'


# ---------------------------------------------------------------- extra encoders (each checked by capstone)
def chk(w, text):
    got = C.dis1(0, w)
    assert got == text, '%s != %s' % (got, text)
    return w


def cmn_wi(rn, imm): return 0x3100001F | (imm << 10) | (C.R(rn) << 5)
def ccmn_wi(rn, imm, nzcv, cond): return 0x3A400800 | (imm << 16) | (C.COND[cond] << 12) | (C.R(rn) << 5) | nzcv
def csel_w(rd, rn, rm, cond): return 0x1A800000 | (C.R(rm) << 16) | (C.COND[cond] << 12) | (C.R(rn) << 5) | C.R(rd)
def ldr_w_post(rt, rn, imm): return 0xB8400400 | ((imm & 0x1FF) << 12) | (C.R(rn) << 5) | C.R(rt)
def str_w_post(rt, rn, imm): return 0xB8000400 | ((imm & 0x1FF) << 12) | (C.R(rn) << 5) | C.R(rt)
def stp_d(t1, t2, rn, off): return 0x6D000000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (C.R(rn) << 5) | t1
def ldp_d(t1, t2, rn, off): return 0x6D400000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (C.R(rn) << 5) | t1


def L(fn, *args):
    return C.to(fn, *args)


def ret_to(t):
    return lambda pc, Lb: C.far_return(pc, t, 'x16')


# ---------------------------------------------------------------- allocation helper
def place(tag, build, purpose, slack=0x10):
    n = len(build(C.FAR_LO).words())
    size = (n * 4 + slack + 0xF) & ~0xF
    start = g.alloc(tag, 'FAR_CODE', size, purpose)
    a = build(start)
    return start, g.cave(tag, start, a)


FLAG = g.alloc('SIGIL2_FLAG', 'FAR_DATA', 4, 'sigil2 per-match flag: 1 = producer ran at UpdatePhase (reset at MatchPreprocess)')
groups = {}

# ================================================================ SIGIL2_LATE
def build_pre(s):
    # at 0x1181E34: x19 = SQM, x20 not yet set, x0/x8 written before read on every path after 0x1181E34
    a = C.Asm(s)
    a(lambda pc, Lb: C.adrp(pc, 'x16', FLAG))
    a(chk(C.str_w('wzr', 'x16', C.lo12(FLAG)), 'str wzr, [x16, #0x%x]' % C.lo12(FLAG)))   # new match: flag 0
    a(chk(C.text_word(0x1181E34), 'ldr x0, [x19, #0x28]'))                                # replaced word
    a.many(lambda pc, Lb: C.relocate(0x1181E38, pc))                                       # adrp x20, 0x5b65000
    a(L(C.cbz_x, 'x0', 'stock'))                                                           # no SQM+0x28: stock skip
    a(chk(C.ldr_x('x8', 'x20', 0xC20), 'ldr x8, [x20, #0xc20]'))
    a(chk(C.ldrb('w8', 'x8', 0xBDA), 'ldrb w8, [x8, #0xbda]'))
    a(L(C.cbnz_w, 'w8', 'stock'))                                                          # true offline: stock
    a.many(ret_to(0x1181E58))                                                              # LAN: no early producer
    a.label('stock')
    a.many(ret_to(0x1181E3C))
    return a


def build_frame(s):
    a = C.Asm(s)
    a(lambda pc, Lb: C.adrp(pc, 'x16', FLAG))
    a(chk(C.ldr_w('w17', 'x16', C.lo12(FLAG)), 'ldr w17, [x16, #0x%x]' % C.lo12(FLAG)))
    a(L(C.cbnz_w, 'w17', 'out'))                                       # already produced this match (fast path)
    for glob, chain in ((OFFL, [('ldrb', 0xBDA, 'cbnz')]),
                        (MGR3, [('ldr_w', 0x1268, 'mode6')]),
                        (GDM, [('ldr_x', 0x20, 'cbz_x'), ('ldr_w', 0xD0, 'own')]),
                        (SQMG, [('ldr_x', 0x28, 'cbz_x')])):
        a(lambda pc, Lb, glob=glob: C.adrp(pc, 'x17', glob))
        a(C.ldr_x('x17', 'x17', C.lo12(glob)))
        if glob != OFFL:
            a(L(C.cbz_x, 'x17', 'out'))
        for kind, off, test in chain:
            if kind == 'ldrb':
                a(chk(C.ldrb('w17', 'x17', off), 'ldrb w17, [x17, #0x%x]' % off))
            elif kind == 'ldr_w':
                a(chk(C.ldr_w('w17', 'x17', off), 'ldr w17, [x17, #0x%x]' % off))
            else:
                a(chk(C.ldr_x('x17', 'x17', off), 'ldr x17, [x17, #0x%x]' % off))
            if test == 'cbnz':
                a(L(C.cbnz_w, 'w17', 'out'))                           # offline: stock producer already ran
            elif test == 'cbz_x':
                a(L(C.cbz_x, 'x17', 'out'))
            elif test == 'mode6':
                a(chk(C.cmp_wi('w17', 6), 'cmp w17, #6'))
                a(L(C.bne, 'out'))
            elif test == 'own':
                a(chk(cmn_wi('w17', 1), 'cmn w17, #1'))
                a(L(C.beq, 'out'))                                     # own player number not known yet
    a(chk(C.movz_w('w17', 1), 'mov w17, #1'))
    a(chk(C.str_w('w17', 'x16', C.lo12(FLAG)), 'str w17, [x16, #0x%x]' % C.lo12(FLAG)))  # once per match
    # save every argument / caller-saved input of STEP_UpdatePhase (x0..x8, d0..d7, x29, x30)
    a(chk(C.stp_pre('x29', 'x30', 'sp', -0xA0), 'stp x29, x30, [sp, #-0xa0]!'))
    a(chk(C.mov_sp('x29', 'sp'), 'mov x29, sp'))
    for i in range(0, 8, 2):
        a(chk(C.stp_x(i, i + 1, 'sp', 0x10 + 8 * i), 'stp x%d, x%d, [sp, #0x%x]' % (i, i + 1, 0x10 + 8 * i)))
    a(chk(C.str_x('x8', 'sp', 0x50), 'str x8, [sp, #0x50]'))
    for i in range(0, 8, 2):
        a(chk(stp_d(i, i + 1, 'sp', 0x60 + 8 * i), 'stp d%d, d%d, [sp, #0x%x]' % (i, i + 1, 0x60 + 8 * i)))
    a.many(lambda pc, Lb: C.far_call(pc, PRODUCER, 'x16'))           # own entry + targets, 0x88 send, apply
    for i in range(0, 8, 2):
        a(chk(ldp_d(i, i + 1, 'sp', 0x60 + 8 * i), 'ldp d%d, d%d, [sp, #0x%x]' % (i, i + 1, 0x60 + 8 * i)))
    a(chk(C.ldr_x('x8', 'sp', 0x50), 'ldr x8, [sp, #0x50]'))
    for i in range(0, 8, 2):
        a(chk(C.ldp_x(i, i + 1, 'sp', 0x10 + 8 * i), 'ldp x%d, x%d, [sp, #0x%x]' % (i, i + 1, 0x10 + 8 * i)))
    a(chk(C.ldp_post('x29', 'x30', 'sp', 0xA0), 'ldp x29, x30, [sp], #0xa0'))
    a.label('out')
    a.many(lambda pc, Lb: C.relocate(0x114B9CC, pc))                  # pacibsp (same x30 and sp as at entry)
    a.many(ret_to(0x114B9D0))
    return a


PRE, pre_recs = place('SIGIL2_PRE', build_pre, 'MatchPreprocess: flag reset, LAN skips the early producer')
FRAME, frame_recs = place('SIGIL2_FRAME', build_frame, 'UpdatePhase entry: produce once per match (LAN)')
groups['SIGIL2_LATE'] = pre_recs + frame_recs + \
    g.far_hook(0x1181E34, 'ldr x0, [x19, #0x28]', PRE, 'x16', link=False,
               why='x16/x17 never appear in 0x1181D80..0x1181E98 (checked); PRE returns via x16 to 0x1181E3C / '
                   '0x1181E58 where it is not read') + \
    g.far_hook(0x114B9CC, 'pacibsp', FRAME, 'x16', link=False,
               why='function entry of STEP_UpdatePhase (called through the step table, blr): x16/x17 are '
                   'intra-procedure scratch, dead at entry; FRAME uses only x16/x17 until it saves x0..x8/d0..d7')


# ================================================================ SIGIL2_SELF
def build_self(s):
    # at 0x119610C: vector {u32 player no} begin [sp+8], end [sp+0x10]; x8/x9/x10 written at 0x1196110..0x1196118
    a = C.Asm(s)
    a(chk(C.ldp_x('x8', 'x9', 'sp', 8), 'ldp x8, x9, [sp, #8]'))
    a(lambda pc, Lb: C.adrp(pc, 'x10', GDM))
    a(C.ldr_x('x10', 'x10', C.lo12(GDM)))
    a(chk(C.ldr_x('x10', 'x10', 0x20), 'ldr x10, [x10, #0x20]'))      # local pgd (non-null: 0x1195EB4)
    a(chk(C.ldr_w('w10', 'x10', 0xD0), 'ldr w10, [x10, #0xd0]'))      # own player number
    a(chk(C.mov_x('x16', 'x8'), 'mov x16, x8'))                        # write pointer
    a.label('loop')
    a(chk(C.cmp_xr('x8', 'x9'), 'cmp x8, x9'))
    a(L(C.beq, 'done'))
    a(chk(ldr_w_post('w17', 'x8', 4), 'ldr w17, [x8], #4'))
    a(chk(C.cmp_wr('w17', 'w10'), 'cmp w17, w10'))
    a(L(C.beq, 'loop'))                                                 # own number: drop
    a(chk(str_w_post('w17', 'x16', 4), 'str w17, [x16], #4'))
    a(lambda pc, Lb: C.b(pc, Lb['loop']))
    a.label('done')
    a(chk(C.str_x('x16', 'sp', 0x10), 'str x16, [sp, #0x10]'))        # new end
    a(chk(C.text_word(0x119610C), 'ldp x25, x23, [sp, #8]'))          # replaced word
    a.many(ret_to(0x1196110))
    return a


SELF, self_recs = place('SIGIL2_SELF', build_self, 'producer: drop own player from the target vector')
groups['SIGIL2_SELF'] = self_recs + g.far_hook(
    0x119610C, 'ldp x25, x23, [sp, #8]', SELF, 'x16', link=False,
    why='x16/x17 never appear in the producer 0x1195E40..0x1196440 (checked); x8..x10 written at 0x1196110..18')


# ================================================================ SIGIL2_APPLY
def build_apply(s):
    # at 0x1195D2C: x26 = &pgd+0x46E0, x19 = entry+0xC, x28 = bytes left incl. this entry (0x14 = last = own
    # entry of the producer record), w21 = 3, w8 written here; x16/x17 unused in the apply.
    a = C.Asm(s)
    a(chk(C.text_word(0x1195D2C), 'ldur w8, [x19, #-8]'))             # entry quest / counterpart (slot 0)
    a(chk(C.ldr_w('w17', 'x26', 0), 'ldr w17, [x26]'))                 # current pgd slot 0
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))         # Z = slot 0 unset (0 or -1)
    a(L(C.beq, 'stock'))
    a(chk(C.cmp_xi('x28', 0x14), 'cmp x28, #0x14'))
    a(L(C.beq, 'own'))
    a(chk(C.mov_w('w20', 'w8'), 'mov w20, w8'))                         # target entry, slot 0 taken: slot 1 only
    a.many(ret_to(0x1195D58))
    a.label('own')
    a(chk(C.cmp_wr('w17', 'w8'), 'cmp w17, w8'))
    a(L(C.beq, 'stock'))
    a(chk(C.stur_w('w17', 'x19', -4), 'stur w17, [x19, #-4]'))         # own entry over a counterpart: -> slot 1
    a.label('stock')
    a.many(ret_to(0x1195D30))                                           # str w8, [x26] ... stock
    return a


APPLY, apply_recs = place('SIGIL2_APPLY', build_apply, 'apply: order-independent own/target slots')
groups['SIGIL2_APPLY'] = apply_recs + g.far_hook(
    0x1195D2C, 'ldur w8, [x19, #-8]', APPLY, 'x16', link=False,
    why='x16/x17 never appear in the apply 0x1195C40..0x1195DFC (checked)')


# ================================================================ SIGIL2_APPLY2 (review10 S3)
# Replaces SIGIL2_APPLY's hook target (built-in cave stays, unreferenced). At 0x1195D2C (same registers as APPLY):
#   offline (OFF != 0)                      -> stock (0x1195D30 with w8 = entry quest): offline byte-identical path
#   slot 0 unset (0 / -1)                   -> stock
#   own entry (x28 == 0x14), same quest     -> SKIP the entry (no rebuild 0x11825E0, no slot-1 write of -1)
#   own entry, other quest                  -> as APPLY: counterpart -> entry slot-1 field, own quest -> slot 0
#   target entry, slot 0 taken, slot 1 unset-> slot 1 only (0x1195D58, w20 = counterpart)
#   target entry, slot 0 and slot 1 taken   -> SKIP (another record's slot 1 is kept)
# Skip = 0x1195CA4 (`subs x28, x28, #0x14; add x19; b.eq end`): next entry, registers as at a normal entry end.
for a, t in ((0x1195CA4, 'subs x28, x28, #0x14'), (0x1195CA8, 'add x19, x19, #0x14'), (0x1195CAC, 'b.eq #0x1195ddc'),
             (0x1195DD8, 'b #0x1195ca4')):
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)


def build_apply2(s):
    a = C.Asm(s)
    a(chk(C.text_word(0x1195D2C), 'ldur w8, [x19, #-8]'))             # entry quest (slot 0)
    a(lambda pc, Lb: C.adrp(pc, 'x17', OFFL))
    a(C.ldr_x('x17', 'x17', C.lo12(OFFL)))
    a(chk(C.ldrb('w17', 'x17', 0xBDA), 'ldrb w17, [x17, #0xbda]'))
    a(L(C.cbnz_w, 'w17', 'stock'))                                     # offline: stock
    a(chk(C.ldr_w('w17', 'x26', 0), 'ldr w17, [x26]'))
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))
    a(L(C.beq, 'stock'))                                               # slot 0 unset: stock
    a(chk(C.cmp_xi('x28', 0x14), 'cmp x28, #0x14'))
    a(L(C.beq, 'own'))
    a(chk(C.ldr_w('w17', 'x26', 4), 'ldr w17, [x26, #4]'))            # target entry: slot 1 set?
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))
    a(L(C.bne, 'skip'))
    a(chk(C.mov_w('w20', 'w8'), 'mov w20, w8'))                        # slot 1 only
    a.many(ret_to(0x1195D58))
    a.label('own')
    a(chk(C.cmp_wr('w17', 'w8'), 'cmp w17, w8'))
    a(L(C.beq, 'skip'))                                                # same quest: nothing to do
    a(chk(C.stur_w('w17', 'x19', -4), 'stur w17, [x19, #-4]'))
    a.label('stock')
    a.many(ret_to(0x1195D30))
    a.label('skip')
    a.many(ret_to(0x1195CA4))
    return a


# SIGIL2_APPLY2 is BUILT IN (cave 0xC501140 + trampoline 0x563EF8C) but REVERTED live (regression, sigil7_notes 4):
# its "skip same-quest own entry" drops the rebuild 0x11825E0 that a re-applied record needs (it resets module+0x79,
# the pairing gives up on the first frame otherwise). Kept here as cave + trampoline only (SAME), no hook.
APPLY2, apply2_recs = place('SIGIL2_APPLY2', build_apply2, 'S3: apply skips same-quest own entries, keeps a set slot 1')
_tr2 = g.alloc('tramp2_1195D2C', 'NEAR_TRAMP', 12, 'trampoline 1195D2C -> SIGIL2_APPLY2 via x16')
apply2_recs += g.cave('tramp2_1195D2C', _tr2, [C.adrp(_tr2, 'x16', APPLY2), C.add_xi('x16', 'x16', C.lo12(APPLY2)),
                                               C.br('x16')])
groups['SIGIL2_APPLY2'] = apply2_recs


# ================================================================ SIGIL2_APPLY3 (review10 S3, minimal)
# Byte-for-byte the OLD SIGIL2_APPLY decisions, except two LAN-only branches that only fire when ANOTHER objective
# already holds slot 1 (slot-1 value set = not 0 / -1):
#   own entry, same quest as slot 0, slot 1 set   -> entry slot-1 field := current slot 1 (old: -1 -> wipes slot 1).
#        The rebuild of slot 0 (0x11825E0) still happens, exactly as old. The slot-1 value is a mapped id
#        (20 / 40 / 250 ...: role row +0x48 = -1), so 0x1195D6C..A8 maps it to itself; slot 1 is rewritten unchanged.
#   target entry, slot 0 set to a DIFFERENT quest than the entry's, slot 1 set -> skip the entry (old: overwrote that
#        slot 1 with mapped(entry quest)).
# Every other case takes the old path: target entry with slot 0 == entry quest always goes to slot 1 (old), own entry
# over a counterpart moves it to slot 1 (old), slot 0 unset -> stock. Offline: all old paths (OFF test in both branches).
def build_apply3(s):
    a = C.Asm(s)
    a(chk(C.text_word(0x1195D2C), 'ldur w8, [x19, #-8]'))             # entry quest (slot 0)
    a(chk(C.ldr_w('w17', 'x26', 0), 'ldr w17, [x26]'))                 # current pgd slot 0
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))
    a(L(C.beq, 'stock'))                                               # slot 0 unset: stock (old)
    a(chk(C.cmp_xi('x28', 0x14), 'cmp x28, #0x14'))
    a(L(C.beq, 'own'))
    # ---- target entry, slot 0 taken
    a(chk(C.cmp_wr('w17', 'w8'), 'cmp w17, w8'))
    a(L(C.beq, 'slot1'))                                               # same objective: old path
    a(chk(C.ldr_w('w17', 'x26', 4), 'ldr w17, [x26, #4]'))
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))
    a(L(C.beq, 'slot1'))                                               # slot 1 free: old path
    a(lambda pc, Lb: C.adrp(pc, 'x16', OFFL))
    a(C.ldr_x('x16', 'x16', C.lo12(OFFL)))
    a(chk(C.ldrb('w16', 'x16', 0xBDA), 'ldrb w16, [x16, #0xbda]'))
    a(L(C.cbnz_w, 'w16', 'slot1'))                                     # offline: old path
    a.many(ret_to(0x1195CA4))                                          # LAN: keep the other objective's slot 1
    a.label('slot1')
    a(chk(C.mov_w('w20', 'w8'), 'mov w20, w8'))                        # target entry: slot 1 only (old)
    a.many(ret_to(0x1195D58))
    # ---- own entry, slot 0 taken
    a.label('own')
    a(chk(C.cmp_wr('w17', 'w8'), 'cmp w17, w8'))
    a(L(C.bne, 'over'))
    a(chk(C.ldr_w('w17', 'x26', 4), 'ldr w17, [x26, #4]'))            # same quest: slot 1 set?
    a(chk(C.cmp_wi('w17', 0), 'cmp w17, #0'))
    a(chk(ccmn_wi('w17', 1, 4, 'ne'), 'ccmn w17, #1, #4, ne'))
    a(L(C.beq, 'stock'))                                               # slot 1 free: old (stock)
    a(lambda pc, Lb: C.adrp(pc, 'x16', OFFL))
    a(C.ldr_x('x16', 'x16', C.lo12(OFFL)))
    a(chk(C.ldrb('w16', 'x16', 0xBDA), 'ldrb w16, [x16, #0xbda]'))
    a(L(C.cbnz_w, 'w16', 'stock'))                                     # offline: old (stock)
    a.label('over')                                                    # (old: counterpart -> slot 1) / keep slot 1
    a(chk(C.stur_w('w17', 'x19', -4), 'stur w17, [x19, #-4]'))
    a.label('stock')
    a.many(ret_to(0x1195D30))
    return a


# slot-1 ids written by the apply are role row +0x48 values; each maps to itself (row +0x48 == -1 or no row) [V data:
# SubQuestRoleParam 20 / 40 / 250 / 200 / 205 +0x48 = -1]. 0x1195D6C..0x1195DA8: second lookup fails -> w20 kept.
for a, t in ((0x1195D84, 'ldr w21, [x8, #0x48]'), (0x1195DA8, 'csel w20, w20, w21, eq')):
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)
APPLY3, apply3_recs = place('SIGIL2_APPLY3', build_apply3, 'S3 minimal: old APPLY + keep another objective\'s slot 1 (LAN)')
_tr3 = g.alloc('tramp3_1195D2C', 'NEAR_TRAMP', 12, 'trampoline 1195D2C -> SIGIL2_APPLY3 via x16')
apply3_recs += g.cave('tramp3_1195D2C', _tr3, [C.adrp(_tr3, 'x16', APPLY3), C.add_xi('x16', 'x16', C.lo12(APPLY3)),
                                               C.br('x16')])
_APPLY_HOOK_BUILTIN = C.hexw(C.shipped_word(0x1195D2C))
assert _APPLY_HOOK_BUILTIN == '50A41215', _APPLY_HOOK_BUILTIN       # old SIGIL2_APPLY hook (b 0x563EE6C), reverted
_hook3 = g.text_patch(0x1195D2C, 'ldur w8, [x19, #-8]', C.b(0x1195D2C, _tr3),
                      'S3 hook (x16/x17 never appear in the apply, checked)', replaces_shipped=True)
groups['SIGIL2_APPLY3'] = apply3_recs + [_hook3]                                       # bake (stock orig)
groups['SIGIL2_APPLY3_LIVE'] = apply3_recs + [(0x1195D2C, _APPLY_HOOK_BUILTIN, _hook3[2], True)]   # running game
# SIGIL2_APPLY keeps cave + trampoline (built in); its hook record moves to SIGIL2_APPLY3.
assert groups['SIGIL2_APPLY'][-1][0] == 0x1195D2C
groups['SIGIL2_APPLY'] = groups['SIGIL2_APPLY'][:-1]


# ================================================================ SIGIL2_KEEP (optional)
def build_keep(s):
    a = C.Asm(s)
    a(chk(C.text_word(0x1179788), 'ldr w8, [x0, #8]'))                # key
    a(chk(cmn_wi('w1', 1), 'cmn w1, #1'))                              # value -1?
    a(chk(C.movz_w('w17', 9), 'mov w17, #9'))
    a(chk(csel_w('w8', 'w17', 'w8', 'eq'), 'csel w8, w17, w8, eq'))   # -> key 9 -> stock early return 0x1179790
    a.many(ret_to(0x117978C))
    return a


KEEP, keep_recs = place('SIGIL2_KEEP', build_keep, 'slot setter ignores value -1 (optional)')
groups['SIGIL2_KEEP'] = keep_recs + g.far_hook(
    0x1179788, 'ldr w8, [x0, #8]', KEEP, 'x16', link=False,
    why='x16/x17 never appear in the setter 0x1179770..0x1179958 (checked); x30 untouched (b, not bl)')


# ================================================================ SIGIL2_NOPASSIVE (optional, NOT game behaviour)
# sigil5_notes.md: the stock producer writes one entry per target {target no, quest row +0 (counterpart), -1, -1,
# other target} BEFORE the own entry (0x11962D0..0x1196394). SubQuestRoleParam +0 [V data]: 10 -> 10, 30 -> 30,
# 240 -> 250, so the target of a Sworn Enemy gets quest 10 itself (mutual). That is the game's own record layout.
# This optional group drops the target entries and keeps the targets in the own entry: then a player without a
# sigil keeps -1 everywhere. Apply only if the lead wants "no objective for non-bearers"; never baked by default.
for a, t in ((0x11962C8, 'cmp w22, #1'), (0x11962CC, 'b.lt #0x1196398'), (0x11962D0, 'ldr x10, [sp, #8]'),
             (0x11962D4, 'ldr w8, [x10]'), (0x1196324, 'mov w9, #-1'), (0x1196334, 'cmp w22, #2'),
             (0x1196338, 'b.lt #0x11963a0'), (0x119633C, 'ldr w9, [x10, #4]'), (0x1196394, 'b #0x11963a0'),
             (0x1196398, 'mov w9, #-1'), (0x119639C, 'mov w8, #-1'), (0x11963A0, 'ldr x10, [sp, #0x140]')):
    assert C.dis1(a, C.text_word(a)) == t, (hex(a), C.dis1(a, C.text_word(a)), t)


def build_nopassive(s):
    # at 0x11962C8: w22 = number of targets (0..2), [sp+8] = target vector begin (x10 is loaded from it at
    # 0x11962D0 in stock). Stock own entry gets w8 = begin[0], w9 = begin[1] (w22 >= 2) or -1 (0x1196324 /
    # 0x1196338), or w8 = w9 = -1 (0x1196398) when w22 < 1. Same values here, without the target entries.
    a = C.Asm(s)
    a(chk(C.text_word(0x11962C8), 'cmp w22, #1'))                      # replaced word
    a(lambda pc, Lb: C.bcond(pc, 'lt', Lb['none']))
    a(chk(C.ldr_x('x17', 'sp', 8), 'ldr x17, [sp, #8]'))
    a(chk(C.ldr_w('w8', 'x17', 0), 'ldr w8, [x17]'))                   # t1
    a(chk(0x12800009, 'mov w9, #-1'))                                   # t2 = -1 unless 2 targets
    a(chk(C.cmp_wi('w22', 2), 'cmp w22, #2'))
    a(lambda pc, Lb: C.bcond(pc, 'lt', Lb['own']))
    a(chk(C.ldr_w('w9', 'x17', 4), 'ldr w9, [x17, #4]'))               # t2
    a.label('own')
    a.many(ret_to(0x11963A0))                                           # own entry only (count +1)
    a.label('none')
    a.many(ret_to(0x1196398))                                           # stock: targets -1, own entry
    return a


NOPASSIVE, nop_recs = place('SIGIL2_NOPASSIVE', build_nopassive, 'producer: no target entries (optional)')
groups['SIGIL2_NOPASSIVE'] = nop_recs + g.far_hook(
    0x11962C8, 'cmp w22, #1', NOPASSIVE, 'x16', link=False,
    why='x16/x17 never appear in the producer 0x1195E40..0x1196440 (checked); flags rewritten in the cave; '
        'x10..x13 are written at 0x11963A0.. before any read')

# ---------------------------------------------------------------- no shared word with sigil_nc_live.py
NC = {0x11960B8, 0x1198738, 0x1198744, 0x119979C, 0x11820E0, 0x118228C}
for gname, rs in groups.items():
    for a, o, n, c in rs:
        assert a not in NC, '%s shares %x with sigil_nc_live.py' % (gname, a)

ORDER = ['SIGIL2_LATE', 'SIGIL2_SELF', 'SIGIL2_APPLY', 'SIGIL2_APPLY2', 'SIGIL2_APPLY3', 'SIGIL2_KEEP', 'SIGIL2_NOPASSIVE']
# built-in groups: every record byte-identical to patch_manager.cpp; new groups: no shipped byte except re-pointed hooks
for gname in BUILT_IN:
    for a, o, n, c in groups[gname]:
        bb = bytes.fromhex(n)
        assert all(C.SHIPPED.get(a + i) == bb[i] for i in range(len(bb))), '%s %x not the built-in word' % (gname, a)
for gname in ('SIGIL2_APPLY3', 'SIGIL2_NOPASSIVE'):
    for a, o, n, c in groups[gname]:
        if a == 0x1195D2C:
            continue
        assert not any(a + i in C.SHIPPED for i in range(len(n) // 2)), '%s %x is shipped' % (gname, a)
print('\n'.join(g.listing))
if DRY:
    print('dry run: nothing claimed or written')
    sys.exit(0)
C.write_live(OUT, groups, ORDER, """Sigil stage A on the far cave region: (offset_from_main, orig_hex, new_hex, is_code), bytes little-endian.
Generated by sigil2_gen.py (cave_lib checks: stock words, capstone, registry, collisions). NOT live-tested.
Notes: sigil2_notes.md. Apply on EVERY game. Each group lists its far caves, then its trampolines, then its hook.
SUPERSEDES sigil_live.py (SIGIL_A*, SIGIL_A_KEEP*): same hook words; never apply both.
Works together with sigil_nc_live.py SIGIL_NC_TARGET (or _2C), EVAL, REPORT, PHASE: no shared word.
SIGIL2_SELF only matters with SIGIL_NC_TARGET (kind 0x26). SIGIL2_KEEP is optional.
SIGIL2_NOPASSIVE is optional and NOT the game's behaviour (targets lose their counterpart quest): sigil5_notes.md.""")
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write('\n# review10 S3, (minimal), LIVE form for a running built-in game (hook orig = old APPLY word 50A41215); never bake it\n')
    f.write('SIGIL2_APPLY3_LIVE = [  # FAR cave records\n')
    for a, o, n, c in groups['SIGIL2_APPLY3_LIVE']:
        f.write('    (0x%X, "%s", "%s", %s),\n' % (a, o, n, c))
    f.write(']\n')
    f.write('# SIGIL2_APPLY above = built-in cave + trampoline only and SIGIL2_APPLY2 (reverted) = built-in cave + trampoline only; the 0x1195D2C hook word is in SIGIL2_APPLY3\n')
    f.write('FLAG = 0x%X   # per-match flag word (FAR_DATA, no record): 1 = producer ran this match\n' % FLAG)
    f.write('CAVES = {%s}\n' % ', '.join("'%s': 0x%X" % kv for kv in
                                         (('PRE', PRE), ('FRAME', FRAME), ('SELF', SELF), ('APPLY', APPLY),
                                          ('APPLY2', APPLY2), ('APPLY3', APPLY3), ('KEEP', KEEP), ('NOPASSIVE', NOPASSIVE))))
print('FLAG 0x%X' % FLAG)
# patch_manager.cpp rows -> section at the end of sigil2_notes.md (between the markers, replaced on re-runs)
BEGIN, END = '<!-- CPP_ROWS_BEGIN -->', '<!-- CPP_ROWS_END -->'
parts = [BEGIN, '## 9. patch_manager.cpp rows (generated by sigil2_gen.py: `cave_lib.cpp_rows`)', '',
         'Declarations go with the other `DUSK_W_*` arrays, rows into the built-in table. Far words use the',
         'accepted `{}, true` form. Per group: caves, trampolines, hook. Take the groups you build in.', '']
for gname in ORDER:
    d, r = C.cpp_rows(gname, groups[gname])
    parts += ['### %s' % gname, '```cpp', d, r, '```', '']
parts.append(END)
notes = os.path.join(HERE, 'sigil2_notes.md')
txt = open(notes, encoding='utf-8').read() if os.path.exists(notes) else ''
if BEGIN in txt and END in txt:
    txt = txt[:txt.index(BEGIN)] + txt[txt.index(END) + len(END):].lstrip('\n')
open(notes, 'w', encoding='utf-8').write(txt.rstrip('\n') + '\n\n' + '\n'.join(parts) + '\n')
print('sigil2_notes.md: cpp rows section written')
