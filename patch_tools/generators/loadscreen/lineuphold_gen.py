"""lineuphold_gen.py: LINEUPHOLD - the match loading screen waits (capped) until every member's player data is in,
so the game's own line-up shows every player. Static generator in the style of diag/net/*_gen.py, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes lineuphold_live.py NEXT TO THIS FILE.
    python diag/net/loadscreen/lineuphold_gen.py        (from the workspace root, or anywhere)

Stock facts [V, re-checked by the asserts below]:
  - CSMatchLoadingOverwrapStep (step table built at 0x1131C60 into main+0x5B6BE60; names UTF-16 in ro):
    Init 0x112FFC4, MenuInit 0x112FFC8, WaitMatchPreProcess 0x112FFE8, BeginMatchStartPlayerRend 0x1130068,
    MatchStartPlayerRend 0x11300A0, IsLoadingOverwrap 0x1130188, Finish 0x113018C.
  - WaitMatchPreProcess: par = *(main+0x5B3CDF8); w0 = par vt+0x60 (the stage step = "match phase");
    0x1130018 `cmp w0, #2`; 0x113001C `b.lt 0x1130034` (return, polled again next frame) else 0x1130020 -> advance
    (tail call 0x112FED8). So the screen moves on in the first frame of stage step 2 (MatchLoading).
  - MatchStartPlayerRend 0x11300A0: when the figure map [[main+0x5B76C30]]+0x519E8 is empty or every node is
    loaded (+0x38), it calls 0x1AFAE80 at 0x11300E4. 0x1AFAE80 -> std::function 0x5750BF0 (op 0x1B01360) ->
    layout 0x1AA5F18 -> factory 0x574AA98 (op 0x1AAE490: new 0x14F0) -> view ctor 0x1313D20.
  - The ctor builds the line-up ONCE: 0x1314100 refreshes the figure map (0x149E040: one figure per pgd with
    +0xD0 != -1 and +0x104 <= 0xB, iterator 0xCE9F40 flags 0x27 = local pgd + pool copies), then 0x13144FC runs
    the functor 0x1315840 (vtable 0x5708888) over the same pgds: skip +0xD0 == -1 or a duplicate, skip
    +0x46A0 == 0, else add the figure (0x1315A80, map lookup by number). 0x1315840 / 0x1315A80 have no other
    caller, so a copy bound after this frame never appears on that screen.
  - A remote pool copy gets +0xD0 / +0x46A0 / +0x104 only from that member's type-5 record (0x14DD180; member
    +0xE8 = 1 at 0x14DE294 marks it), lineup_notes 2, remote_player_hang_notes 5b.

LINEUPHOLD (this file): the b.lt word 0x113001C becomes a branch (via a 3-word trampoline in text padding) to a
FAR cave: still before stage step 2 -> the stock wait (0x1130034); step >= 2 and LHBOX.hold == 0 -> the stock
advance (0x1130020); hold != 0 -> count the held frame (LHBOX+4) and wait (0x1130034), i.e. the step is simply
polled again next frame, as in the stock wait. The assist (lineuphold_assist.diff) sets hold only while a
non-server member has no type 5 yet (member +0xE8 == 0), our session state is 5..7, the stage is in step 1..2,
and for at most 10 s; it also re-asks the missing player data early (NEEDDATA) in that window.
LHBOX {u32 hold (assist), u32 held frames (cave)}.  hold 0 = stock behaviour."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

OUT = 'lineuphold_live.py'
OUT_REL = os.path.join('loadscreen', OUT)   # write_live joins it to diag/net
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []

FN, SITE = 0x112FFE8, 0x113001C
WAIT, ADVANCE = 0x1130034, 0x1130020


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


def u16(addr):
    o = addr - C.RO_BASE
    e = o
    while C.RO[e:e + 2] != b'\0\0':
        e += 2
    return C.RO[o:e].decode('utf-16le')


# ================================================================ code facts [V]
for a, t in (
        # WaitMatchPreProcess (the whole function: only x0, x8, x19 are used -> x16 / x17 dead)
        (FN, 'pacibsp'), (0x112FFF8, 'adrp x8, #0x59df000'), (0x1130000, 'ldr x8, [x8, #0xef8]'),
        (0x1130004, 'ldr x0, [x8]'), (0x1130008, 'cbz x0, #0x1130040'), (0x1130010, 'ldr x8, [x8, #0x60]'),
        (0x1130014, 'blr x8'), (0x1130018, 'cmp w0, #2'), (SITE, 'b.lt #0x1130034'),
        (ADVANCE, 'mov x0, x19'), (0x1130024, 'ldr x19, [sp, #0x10]'), (0x1130028, 'ldp x29, x30, [sp], #0x20'),
        (0x113002C, 'autibsp'), (0x1130030, 'b #0x112fed8'),
        (WAIT, 'ldr x19, [sp, #0x10]'), (0x1130038, 'ldp x29, x30, [sp], #0x20'), (0x113003C, 'retab'),
        # the step table entries (adr) and the MatchStartPlayerRend -> view open call
        (0x1131CB8, 'adr x10, #0x112ffe8'), (0x1131BD4, 'adr x11, #0x1130068'), (0x1131CE4, 'adr x9, #0x11300a0'),
        (0x11300E4, 'bl #0x1afae80'), (0x1AFAEBC, 'adrp x10, #0x5750000'), (0x1AFAEC0, 'add x10, x10, #0xbf0'),
        (0x1B01384, 'bl #0x1aa5f18'), (0x1AAE4CC, 'bl #0x1313d20'),
        # the ctor: figure refresh, then the line-up functor (vtable 0x5708888) over pgds with flags 0x27
        (0x1314100, 'bl #0x149e040'), (0x13144D0, 'adrp x8, #0x5708000'), (0x13144D4, 'add x8, x8, #0x888'),
        (0x13144E8, 'mov w1, #0x27'), (0x13144FC, 'bl #0xce9f40'),
        # the functor: number, duplicate, take-part byte, add
        (0x1315864, 'ldr w9, [x1, #0xd0]'), (0x13158A8, 'mov w8, #0x46a0'), (0x13158AC, 'ldrb w8, [x21, x8]'),
        (0x13158B0, 'cbz w8, #0x1315a30'), (0x13158C0, 'bl #0x1315a80'),
        # the figure refresh's per-pgd filter
        (0x149F264, 'ldr w20, [x1, #0xd0]'), (0x149F270, 'ldrb w8, [x1, #0x104]'), (0x149F278, 'cmp w8, #0xb'),
):
    stock(a, t)
assert struct.unpack_from('<Q', C.DATA, 0x57088B8 - C.DATA_BASE)[0] == 0x1315840, 'functor vtable slot +0x30'
assert struct.unpack_from('<Q', C.DATA, 0x574AAC8 - C.DATA_BASE)[0] == 0x1AAE490, 'view factory op'
assert struct.unpack_from('<Q', C.DATA, 0x5750C20 - C.DATA_BASE)[0] == 0x1B01360, 'menu layout op'
for a, s in ((0x4BB630C, 'CSMatchLoadingOverwrapStep::STEP_WaitMatchPreProcess'),
             (0x4B2E93C, 'CSMatchLoadingOverwrapStep::STEP_BeginMatchStartPlayerRend'),
             (0x4BA0972, 'CSMatchLoadingOverwrapStep::STEP_MatchStartPlayerRend')):
    assert u16(a) == s, (hex(a), u16(a))
listing.append('WaitMatchPreProcess 0x112FFE8..0x113003C uses only x0, x8, x19 (x16 / x17 dead at the site, at '
               '0x1130034 (epilogue) and at 0x1130020 (tail call to the function entry 0x112FED8)); the flags of '
               '`cmp w0, #2` reach the cave unchanged (b / br do not set flags)')

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
    """n zero words of inter-function padding near site (same rules as levelshare_gen / warpdefer_gen)."""
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

g = C.Gen('lineuphold_gen', out=OUT, dry=True)
# alpha plans not in cave_registry.md (see icons1v3_gen PLANNED): keep clear of them
for owner, tag, lo, hi in (('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0),
                           ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)):
    if not any(r['lo'] < hi and lo < r['hi'] for r in C.read_registry()):
        g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
# LHBOX: FAR_DATA is full (2026-11-21: LVBOX ends at 0xC510000). Default = the scratch page after the end of text
# (0x492AD90..0x492B000), where the assist's other boxes live (GROUP_BOX 0x492AF90, ENV_BOX 0x492AFC0, MAILBOX
# 0x492AFE0, REREQUEST 0x492AFF0; cave 6 stores to REREQUEST, so guest stores there work). 0x492AFA0..0x492AFBF
# is free (rulesets_notes 118-120 [I]; re-checked below against every shipped record, every *_live.py and every
# 0x492AFxx constant in dusk_lan.cpp / patch_manager.cpp). 0x492AFA0 stays for the RULE_BOX idea; we take 0x492AFB0.
# Not a pool: no registry row is possible (read_registry asserts pools); the lead adds a line to the registry's
# "outside the pools" list. Override: --box 0xADDR
BOX = 0x492AFB0
if '--box' in sys.argv:
    BOX = int(sys.argv[sys.argv.index('--box') + 1], 16)
for x in range(BOX, BOX + 8):
    assert x not in C.SHIPPED and x not in others, 'LHBOX byte %x is taken' % x
assert BOX >= C.TEXT_END or C.image_is_zero(BOX, 8), 'LHBOX not zero in the image'
_src = ''
for p in (os.path.join(NET, '..', '..', 'src', 'lichii', 'src', 'core', 'dusk_lan.cpp'),
          os.path.join(NET, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')):
    if os.path.exists(p):
        _src += open(p, encoding='utf-8', errors='ignore').read().upper()
for x in range(BOX - 0x10, BOX + 8, 4):          # no box constant starts within 16 bytes below or inside ours
    assert ('0X%X;' % x) not in _src and ('0X%X ' % x) not in _src, 'a constant 0x%X is in the source' % x
listing.append('LHBOX 0x%X..0x%X (scratch page after text; free: no shipped record, no *_live.py, no source constant)'
               % (BOX, BOX + 8))
SIZE = 18
T = g.alloc('LINEUPHOLD', 'FAR_CODE', SIZE * 4, 'LINEUPHOLD 0x113001C: WaitMatchPreProcess waits while LHBOX.hold')

a = C.Asm(T)
a(C.to(C.bcond, 'lt', 'wait'))                              # the replaced word: stage step < 2 -> stock wait
a(lambda pc, L: C.adrp(pc, 'x16', BOX))
a(C.add_xi('x16', 'x16', C.lo12(BOX)))                      # x16 = LHBOX
a(C.ldr_w('w17', 'x16', 0))                                 # hold (written by the assist only)
a(C.to(C.cbz_w, 'w17', 'go'))
a(C.ldr_w('w17', 'x16', 4))
a(C.add_wi('w17', 'w17', 1))
a(C.str_w('w17', 'x16', 4))                                 # held frames (written by this cave only)
a.label('wait')
a.many(lambda pc, L: C.far_jump(pc, WAIT))                  # 0x1130034: return, polled again next frame
a.label('go')
a.many(lambda pc, L: C.far_jump(pc, ADVANCE))               # 0x1130020: stock advance (tail call 0x112FED8)
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words, 'an encoder is missing in cave_lib'
cave = g.cave('LINEUPHOLD', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LINEUPHOLD 0x%X (x16 dead: see listing)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
HOOK_WORD = C.b(SITE, PAD)
hook = [g.text_patch(SITE, 'b.lt #0x1130034', HOOK_WORD, 'LINEUPHOLD (WaitMatchPreProcess -> hold check)')]

groups = {'LINEUPHOLD_CAVE': cave + tramp, 'LINEUPHOLD': hook}
order = ['LINEUPHOLD_CAVE', 'LINEUPHOLD']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word 0x%08X at 0x%X (assist: LH_SITE / LH_HOOK, read to see the cave is built in)' % (HOOK_WORD, SITE))
print('LHBOX 0x%X..0x%X (assist: LH_BOX)' % (BOX, BOX + 8))
print('registry rows (lead adds):')
print('outside-the-pools line (lead adds to the registry list, not the table): LHBOX 0x%X..0x%X (scratch page '
      'after text): LINEUPHOLD {u32 hold (assist), u32 held frames (cave)}' % (BOX, BOX + 8))
print('| lineuphold_gen | LINEUPHOLD | 0x%X..0x%X | LINEUPHOLD 0x113001C: WaitMatchPreProcess waits while LHBOX.hold; '
      'trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
C.write_live(OUT_REL, groups, order, __doc__.split('LINEUPHOLD (this file)')[0].strip())
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write("CAVES = {'LINEUPHOLD': 0x%X, 'LHBOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_SITE': 0x%X, 'HOOK_WORD': 0x%X}"
            % (T, BOX, PAD, SITE, HOOK_WORD) + chr(10))
