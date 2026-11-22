"""partsync_gen.py: PARTSYNC - every game holds the same Trespasser (joint struggle) participant list, so the count,
the MultiPlayCorrectionParam SpEffect and the boss's max HP are the same on every screen. Static generator in the
style of diag/net/*_gen.py, Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows).
Writes partsync_live.py NEXT TO THIS FILE (diag/net/zt_faults/partcount/).
    python diag/net/zt_faults/partcount/partsync_gen.py          (from the workspace root, or anywhere)
    ... --box 0xADDR                                              (another 16-byte box; default 0x492AFA0)

Stock facts [V, re-checked by the asserts below] (study: partcount report, d_*.txt in this folder):
  - Per-frame update of an instance (vtable 0x56ECFE0 slot 27 = 0x101BB40): after the participant loop it runs
    `mov x0, x19; bl 0x101B6E0` at 0x101CAD8 / 0x101CADC on EVERY frame in mode 6 (0x101CAC8 cmp w8,#6; b.eq).
  - 0x101B6E0 (count): n = (+0x2B8 - +0x2B0) >> 7; when mode is 0/6, step <= 3, +0x361 set and n != +0x2F0 it
    calls 0x10293C0(ins, functor 0x56ED530, -1) = functor 0x102D900 on the boss chr (0x17E7828 by key): NpcParam
    +0x20C -> MultiPlayCorrectionParam row, case n: add the SpEffect of field 0x24 + 4 (n - 1) (n = 0: remove
    all), then 0x19BDA00(mod, 1). It stores n in +0x2F0 in EVERY case (0x101B7C4), also when it did not apply.
  - Kind-4 apply 0x1023E80(ins, payload) (message 0x59 kind 4, handler 0x1023500 -> 0x10236A8): payload
    {u32 player, u8 accepted +4, u8 activate +5, u8 b +6 (-> entry +0xD), u8 leader-if-none +7, u8 hide +8,
    u8 defeated +9}. Adds the player once (idempotent) only when the boss chr / JointStruggleParam row is found
    on this game AND +4 != 0; always drops the player's pending request (+0x2D0).
  - Kind-6 apply 0x1025260(ins, payload) (handler -> 0x102370C): payload {u32 player, +4, +5, u8 +6 = also put
    the player on the "left by death" list +0x340}. Removes the entry if present, with the game's own cleanup.
  - In LAN every join (kind 3) and leave (kind 5) request goes to the requester's OWN game (0x1046FA4 -> the
    own server link) and is decided there (0x1023BA0 / 0x1024F9C), which broadcasts kind 4 / kind 6 to the
    others; nothing ever repairs a game that missed or reordered one of those broadcasts.

PARTSYNC (this file): the bl at 0x101CADC becomes `bl PAD` (3-word trampoline in text padding) -> FAR cave. The
cave does at most ONE job per frame for the instance whose id (+0xC0) is in PSBOX, then tail-calls 0x101B6E0
exactly as the stock bl did (x0 = ins, x30 = 0x101CAE0), so the new count is applied by the game's own
functor in the same frame:
    op 1 add      -> 0x1023E80(ins, {player, accepted 1, activate 0, b, leader 0, hide 0, defeated 0})
    op 2 remove   -> 0x1025260(ins, {player, 0, 1, 0})           (+5 = 1 as the in-battle leave sends it)
    op 3 reapply  -> ins+0x2F0 = -1, so 0x101B6E0 re-runs the functor with the current count
PSBOX (16 bytes): {u32 armed seq (assist), u32 fed seq (cave), u32 instance id, u8 op, u8 b, u8 player, u8 runs}.
armed == fed = nothing to do (stock behaviour). The assist (assist_partsync.diff) arms a job only for an
instance in step 2..3 and a player whose OWN game reports a different membership than this game's list."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

OUT = 'partsync_live.py'
OUT_REL = os.path.join('zt_faults', 'partcount', OUT)   # write_live joins it to diag/net
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []

SITE, BACK = 0x101CADC, 0x101CAE0
COUNT, ADD4, DEL6 = 0x101B6E0, 0x1023E80, 0x1025260
F_STEP, F_ID, F_STORED = 0x50, 0xC0, 0x2F0


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


# ================================================================ code facts [V]
for a, t in (
        # the hook site in the per-frame update (x19 = ins; every frame in mode 6)
        (0x101CAC4, 'ldr w8, [x8, #0x1268]'), (0x101CAC8, 'cmp w8, #6'), (0x101CACC, 'b.eq #0x101cad8'),
        (0x101CAD8, 'mov x0, x19'), (SITE, 'bl #0x101b6e0'), (BACK, 'ldr x8, [x19]'),
        # after the call every register the update uses is reloaded (no cached list pointer)
        (0x101CAF8, 'ldr x23, [x19, #0x320]'), (0x101CAFC, 'ldr x24, [x19, #0x328]'),
        # the count function
        (COUNT, 'pacibsp'), (0x101B70C, 'ldr x8, [x19, #0x2b8]'), (0x101B710, 'ldr x9, [x19, #0x2b0]'),
        (0x101B71C, 'lsr x20, x22, #7'), (0x101B744, 'ldrb w8, [x19, #0x361]'), (0x101B748, 'cmp w0, #3'),
        (0x101B750, 'ldr w9, [x19, #0x2f0]'), (0x101B788, 'bl #0x10293c0'), (0x101B7C4, 'str w20, [x21]'),
        # kind-4 apply: entry, the payload bytes it reads
        (ADD4, 'pacibsp'), (0x1023EE0, 'bl #0x17e7828'), (0x1023F14, 'bl #0x155d5a0'),
        (0x1023F28, 'ldrb w9, [x20, #4]'), (0x1024044, 'ldrb w8, [x20, #7]'), (0x1024060, 'ldrb w8, [x20, #5]'),
        (0x102407C, 'ldrb w8, [x20, #9]'), (0x102411C, 'ldrb w8, [x20, #8]'), (0x1024364, 'ldrb w8, [x20, #6]'),
        (0x1024368, 'sturb w8, [x24, #-0x73]'),
        # kind-6 apply: entry, player, the +5 / +6 bytes, the removal store
        (DEL6, 'pacibsp'), (0x10252B0, 'ldr w24, [x1]'), (0x10256A0, 'ldrb w8, [x20, #6]'),
        (0x10256C4, 'ldrb w8, [x20, #5]'), (0x102591C, 'str x21, [x19, #0x2b8]'),
        # the message handler's own calls (kinds 4 and 6)
        (0x10236A8, 'bl #0x1023e80'), (0x102370C, 'bl #0x1025260'),
):
    stock(a, t)
listing.append('0x101CADC `bl 0x101B6E0` is a call: x16 / x17 (IP0 / IP1) are dead there; x30 = 0x101CAE0 comes from '
               'the hooked bl itself and is restored before the tail call')

others = C.live_records(exclude=(OUT,))


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
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
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


def find_pad(site, n):
    """n zero words of inter-function padding near site (same rules as lineuphold_gen / levelshare_gen)."""
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


assert targets_in(SITE, SITE + 4) == [], 'a branch lands on the site'
assert not any(x in C.SHIPPED or x in others for x in range(SITE, SITE + 4)), 'site already patched'
PAD = find_pad(SITE, 3)
assert PAD
listing.append('trampoline padding 0x%X..0x%X after `%s`' % (PAD, PAD + 12, dis(PAD - 4)))

g = C.Gen('partsync_gen', out=OUT, dry=True)
# alpha plans not in cave_registry.md (as lineuphold_gen): keep clear of them
for owner, tag, lo, hi in (('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0),
                           ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)):
    if not any(r['lo'] < hi and lo < r['hi'] for r in C.read_registry()):
        g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))

# PSBOX: FAR_DATA is full (LVBOX ends at 0xC510000). In the scratch page after text (0x492AD90..0x492B000) the only
# free 16 bytes are 0x492AFA0..0x492AFB0 (free runs: 0x492AF88..0x492B000 minus GROUP_BOX 0x492AF90..A0, LHBOX
# 0x492AFB0..B8, ENV_BOX 0x492AFC0..D8, role 0x492AFD8, MAILBOX 0x492AFE0, REREQUEST 0x492AFF0, VIRTUE_BOX 0x492AFF8).
# 0x492AFA0 was only an idea for a RULE_BOX (rulesets_notes 118; the rule sets were built with RULE_BYTE
# 0x5B65C70 instead). Alternative: --box 0xC50FF00 once the lead deletes the dead RECVWHO row (alpha 13d
# diagnostic, no record in patch_manager.cpp).
BOX = 0x492AFA0
if '--box' in sys.argv:
    BOX = int(sys.argv[sys.argv.index('--box') + 1], 16)
for x in range(BOX, BOX + 16):
    assert x not in C.SHIPPED and x not in others, 'PSBOX byte %x is taken' % x
assert BOX >= C.TEXT_END or C.is_far(BOX), 'PSBOX must be in the scratch page or the cave region'
_src = ''
for p in (os.path.join(NET, '..', '..', 'src', 'lichii', 'src', 'core', 'dusk_lan.cpp'),
          os.path.join(NET, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')):
    if os.path.exists(p):
        _src += open(p, encoding='utf-8', errors='ignore').read().upper()
for x in range(BOX, BOX + 16, 4):                # no box constant starts inside ours
    assert ('0X%X;' % x) not in _src and ('0X%X ' % x) not in _src, 'a constant 0x%X is in the source' % x
assert ('0X%X;' % (BOX - 0x10)) in _src or BOX != 0x492AFA0, 'GROUP_BOX moved?'   # 0x492AF90 is 16 bytes long
listing.append('PSBOX 0x%X..0x%X (free: no shipped record, no *_live.py, no source constant)' % (BOX, BOX + 16))

SIZE = 56
T = g.alloc('PARTSYNC', 'FAR_CODE', SIZE * 4, 'PARTSYNC 0x101CADC: one participant add / remove / reapply per frame')

a = C.Asm(T)
a(C.stp_pre('x29', 'x30', 'sp', -0x30))
a(C.stp_x('x19', 'x20', 'sp', 0x10))
a(C.mov_x('x19', 'x0'))                                    # x19 = ins (x0 = x19 at the site)
a(lambda pc, L: C.adrp(pc, 'x20', BOX))
a(C.add_xi('x20', 'x20', C.lo12(BOX)))                     # x20 = PSBOX
a(C.ldr_w('w8', 'x20', 0))                                 # armed (assist)
a(C.ldr_w('w9', 'x20', 4))                                 # fed (this cave)
a(C.cmp_wr('w8', 'w9'))
a(C.to(C.beq, 'done'))
a(C.ldr_w('w9', 'x19', F_ID))
a(C.ldr_w('w10', 'x20', 8))
a(C.cmp_wr('w9', 'w10'))
a(C.to(C.bne, 'done'))                                     # another instance: not this one's job
a(C.str_w('w8', 'x20', 4))                                 # fed = armed: one try per job
a(C.ldrb('w9', 'x20', 0xF))
a(C.add_wi('w9', 'w9', 1))
a(C.strb('w9', 'x20', 0xF))                                # runs (wraps at 256)
a(C.stp_x('xzr', 'xzr', 'sp', 0x20))                       # payload {player, bytes 4..15} = 0
a(C.ldrb('w9', 'x20', 0xE))
a(C.str_w('w9', 'sp', 0x20))                               # +0 player
a(C.ldrb('w10', 'x20', 0xC))                               # op
a(C.cmp_wi('w10', 1))
a(C.to(C.beq, 'add'))
a(C.cmp_wi('w10', 2))
a(C.to(C.beq, 'remove'))
a(C.cmp_wi('w10', 3))
a(C.to(C.bne, 'done'))
a(C.movz_w('w9', 0))                                       # reapply: stored count = -1
a(C.sub_wi('w9', 'w9', 1))
a(C.str_w('w9', 'x19', F_STORED))
a(C.to(C.b, 'done'))
a.label('add')
a(C.movz_w('w9', 1))
a(C.strb('w9', 'sp', 0x24))                                # +4 accepted
a(C.ldrb('w9', 'x20', 0xD))
a(C.strb('w9', 'sp', 0x26))                                # +6 b (entry +0xD)
a(C.mov_x('x0', 'x19'))
a(C.add_xi('x1', 'sp', 0x20))
a.many(lambda pc, L: C.far_call(pc, ADD4))                 # 0x1023E80: the game's kind-4 apply
a(C.to(C.b, 'done'))
a.label('remove')
a(C.movz_w('w9', 1))
a(C.strb('w9', 'sp', 0x25))                                # +5 = 1 (as the in-battle leave), +6 = 0
a(C.mov_x('x0', 'x19'))
a(C.add_xi('x1', 'sp', 0x20))
a.many(lambda pc, L: C.far_call(pc, DEL6))                 # 0x1025260: the game's kind-6 apply
a.label('done')
a(C.mov_x('x0', 'x19'))
a(C.ldp_x('x19', 'x20', 'sp', 0x10))
a(C.ldp_post('x29', 'x30', 'sp', 0x30))                   # x30 = 0x101CAE0 again
a.many(lambda pc, L: C.far_jump(pc, COUNT))                # the stock call, as a tail call
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words, 'an encoder is missing in cave_lib'
cave = g.cave('PARTSYNC', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> PARTSYNC 0x%X (x16 dead: a bl site)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
HOOK_WORD = C.bl(SITE, PAD)
hook = [g.text_patch(SITE, 'bl #0x101b6e0', HOOK_WORD, 'PARTSYNC (instance update -> participant job, then count)')]

groups = {'PARTSYNC_CAVE': cave + tramp, 'PARTSYNC': hook}
order = ['PARTSYNC_CAVE', 'PARTSYNC']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('cave %d words (room %d)' % (len(words), SIZE))
print('hook word 0x%08X at 0x%X (assist: PS_SITE / PS_HOOK, read to see the cave is built in)' % (HOOK_WORD, SITE))
print('PSBOX 0x%X..0x%X (assist: PS_BOX)' % (BOX, BOX + 16))
print('registry rows (lead adds):')
print('outside-the-pools line (lead adds to the registry list, not the table): PSBOX 0x%X..0x%X (scratch page '
      'after text): PARTSYNC {u32 armed, u32 fed, u32 instance id, u8 op, u8 b, u8 player, u8 runs}' % (BOX, BOX + 16))
print('| partsync_gen | PARTSYNC | 0x%X..0x%X | PARTSYNC 0x101CADC: one participant add / remove / reapply per frame '
      'with the game\'s kind-4 / kind-6 apply, then the stock count; trampoline 0x%X..0x%X |'
      % (T, T + SIZE * 4, PAD, PAD + 12))
for name, recs in groups.items():
    d, r = C.cpp_rows(name, recs)
    print('--- patch_manager.cpp rows for %s (lead bakes) ---' % name)
    print(d)
    print(r)
C.write_live(OUT_REL, groups, order, __doc__.split('PARTSYNC (this file)')[0].strip())
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write("CAVES = {'PARTSYNC': 0x%X, 'PSBOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_SITE': 0x%X, 'HOOK_WORD': 0x%X}"
            % (T, BOX, PAD, SITE, HOOK_WORD) + chr(10))
