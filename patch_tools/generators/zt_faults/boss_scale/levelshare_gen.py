"""levelshare_gen.py: LEVELSHARE - every game gets the host's enemy strength levels (boss_scale study, 2026-11-21).
Static generator in the style of diag/net/*_gen.py. Gen(dry=True): cave_registry.md is NOT written (the lead adds
the printed rows). Writes bossscale_live.py NEXT TO THIS FILE (diag/net/zt_faults/boss_scale/).
    python diag/net/zt_faults/boss_scale/levelshare_gen.py      (from the workspace root, or anywhere)

Root cause [V code + data, L live lists]:
  The Trespasser chr's NpcParam row is chosen at creation by 0xEB8CA0 (only caller 0x1773E04 in the chr creator
  0x1773A20): key = chr handle (set << 12 | index); if the key is in the strength-level map of the module
  M = [*(main+0x5B3CDF8) + 0x3378] (unordered map at M+0x38, nodes {next, hash, u16 key +0x10, u16 key +0x12,
  s16 level +0x14}, first node M+0x50, size M+0x60), the NpcParam id, the think id and the JointStruggleParam id
  get + 1000 * level (0xEB8EEC..0xEB8F0C), e.g. NpcParam 21400000 -> 21401000, JointStruggleParam 214000000 ->
  214001000. Row 21401000 holds SpEffect 2210100 in its slot +0x68 and the base 2799300 at +0x498; the chr's
  SpEffect slot provider (vtable 0x56E22F8, slot +0x48 = 0xEB0540) adds the round (stage+0xB8) to the base when
  row +0x128 bit 2 is set: 2799300 + 2 = 2799302 (max HP rate 1.25, attack rates 1.35). Row 21400000 has neither.
  Writers of M+0x38: the trend step 0x1120B80 -> 0xEB7B40 at 0x1121304 (inside the MapSystem body 0x11123A0,
  host only since MAPSIM_HOST 0x11123E0); the lottery 0xEB5060 (returns at 0xEB509C in mode 6); the 0x75 reader
  0xEB7DA0 (PrepareSecond 0x114F324; reads only the server member mgr3+0x658, 0xEB7E38). In LAN no 0x75 comes,
  so a guest's map stays empty and its copy is built from the base row.

LEVELSHARE (this file): the host's assist sends its map {key, level} (side type 28, assist diff
levelshare_assist.diff); a guest's assist puts it in LVBOX; the cave on the chr creator's call 0x1773E04
(bl 0xEB8CA0) inserts the entries ONCE per round with the game's own insert 0xEBD6A0 (the same call 0xEB7B40
makes at 0xEB7C28, value {u16 key, s16 level}) before the lookup runs, then tail-calls 0xEB8CA0.
LVBOX {u32 armed = round + 1 (assist), u32 fed = round + 1 (cave), u32 count, u32 runs (cave),
{u16 key, s16 level}[LV_MAX]}.  The host never arms its box, so the host's game is unchanged."""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, NET)
os.chdir(NET)
import cave_lib as C  # noqa: E402

OUT = 'bossscale_live.py'
OUT_REL = os.path.join('zt_faults', 'boss_scale', OUT)   # write_live joins it to diag/net
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
listing = []

SITE, BACK = 0x1773E04, 0x1773E08
LOOKUP, INSERT, FILL = 0xEB8CA0, 0xEBD6A0, 0xEB7B40
STAGE_G, P_ROUND, P_LEVEL = 0x5B3CDF8, 0xB8, 0x3378
LV_MAX = 18
BOX_SIZE = 16 + 4 * LV_MAX           # 0x58


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


# ================================================================ code facts [V]
for a, t in (
        # chr creator 0x1773A20: the lookup call and its arguments (x0 = [par+0x3378], x1 = &key)
        (0x1773A44, 'adrp x8, #0x5b3c000'), (0x1773A48, 'add x8, x8, #0xdf8'), (0x1773A54, 'ldr x9, [x8, #0x3378]'),
        (0x1773AC8, 'stp x9, x2, [sp, #0x10]'), (0x1773DE0, 'cbz x20, #0x1773e08'),
        (0x1773DEC, 'mov x0, x20'), (0x1773DE8, 'sub x1, x29, #0xc'), (SITE, 'bl #0xeb8ca0'),
        (BACK, 'adrp x19, #0x5b3c000'),
        # the lookup: map +0x38 hit -> level * 1000 into the param ids
        (LOOKUP, 'pacibsp'), (0xEB8D6C, 'ldr x12, [x23, #0x40]'), (0xEB8DCC, 'ldr x15, [x23, #0x38]'),
        (0xEB8EEC, 'ldrsh w9, [x15, #0x14]'), (0xEB8F00, 'mov w10, #0x3e8'), (0xEB8F04, 'mul w9, w9, w10'),
        (0xEB9114, 'bl #0x1d29ca0'), (0xEB9298, 'bl #0x155d5a0'),
        # the host's fill (trend step) and its insert call; the insert's node layout
        (0x11212F8, 'ldr x0, [x8, #0x3378]'), (0x1121304, 'bl #0xeb7b40'), (0x111434C, 'bl #0x1120b80'),
        (0xEB7BA4, 'add x8, x20, #0x38'), (0xEB7C10, 'strh w20, [sp, #0x14]'), (0xEB7C24, 'strh w8, [sp, #0x16]'),
        (0xEB7C28, 'bl #0xebd6a0'),
        (INSERT, 'pacibsp'), (0xEBD6BC, 'ldrh w23, [x1]'), (0xEBD7F0, 'ldrh w8, [x22]'),
        (0xEBD7F8, 'strh w8, [x0, #0x10]'), (0xEBD7FC, 'ldr w8, [x21]'), (0xEBD804, 'stur w8, [x0, #0x12]'),
        # other writers: lottery off in mode 6, 0x75 reader from the server member only
        (0xEB5098, 'cmp w8, #6'), (0xEB509C, 'b.eq #0xeb5fb0'), (0xEB7E38, 'add x1, x0, #0x658'),
        (0x114F324, 'bl #0xeb7da0'),
        # the boss effect: slot provider 0xEB0540 (row +0x358 / +0x498, + round when row +0x128 bit 2)
        (0xEB0570, 'ldr w10, [x8, #0x358]'), (0xEB0584, 'ldr w8, [x8, #0x498]'), (0xEB060C, 'ldrb w8, [x8, #0x128]'),
        (0xEB0610, 'tbz w8, #2, #0xeb0670'), (0xEB0624, 'ldr w20, [x8, #0xb8]'), (0xEB062C, 'add w8, w19, w20'),
        (0xEB064C, 'bl #0x1d2dba0'),
):
    stock(a, t)
assert struct.unpack_from('<Q', C.DATA, 0x56E2340 - C.DATA_BASE)[0] == 0xEB0540, 'vtable 0x56E22F8 slot +0x48'
listing.append('0x1773E04 `bl 0xEB8CA0` is the only call of the lookup (diag/net/callers.py EB8CA0); at a bl site '
               'x9..x18 are free (AAPCS64), x0..x5 are the lookup arguments (saved / restored by the cave), x30 is '
               'set by the hooked bl itself (site + 4)')

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
    """n zero words of inter-function padding near site (same rules as icons1v3_gen.find_pad)."""
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

g = C.Gen('levelshare_gen', out=OUT, dry=True)
# alpha plans not in cave_registry.md (see icons1v3_gen PLANNED): keep clear of them
for owner, tag, lo, hi in (('icons1v3_gen', 'I1RBOX', 0xC50F8E0, 0xC50F8F0),
                           ('icons1v3_gen', 'I1REPICK', 0xC504118, 0xC5041A8)):
    if not any(r['lo'] < hi and lo < r['hi'] for r in C.read_registry()):
        g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))
SIZE = 56
BOX = g.alloc('LVBOX', 'FAR_DATA', BOX_SIZE, 'LEVELSHARE {u32 armed round+1, u32 fed round+1, u32 count, u32 runs, '
              '{u16 key, s16 level}[%d]}' % LV_MAX)
T = g.alloc('LEVELSHARE', 'FAR_CODE', SIZE * 4, 'LEVELSHARE 0x1773E04: host strength levels into the map before 0xEB8CA0')
a = C.Asm(T)
a(C.sub_xi('sp', 'sp', 0x60))
a(C.stp_x(0, 1, 'sp', 0))
a(C.stp_x(2, 3, 'sp', 0x10))
a(C.stp_x(4, 5, 'sp', 0x20))
a(C.stp_x(29, 30, 'sp', 0x30))
a(C.stp_x(19, 20, 'sp', 0x40))
a(C.stp_x(21, 22, 'sp', 0x50))
a(lambda pc, L: C.adrp(pc, 19, BOX))
a(C.add_xi(19, 19, C.lo12(BOX)))                           # x19 = LVBOX
a(C.ldr_w(9, 19, 0))                                       # armed (round + 1)
a(C.to(C.cbz_w, 'w9', 'done'))
a(lambda pc, L: C.adrp(pc, 10, STAGE_G))
a(C.ldr_x(10, 10, C.lo12(STAGE_G)))                        # par = *(main+0x5B3CDF8)
a(C.to(C.cbz_x, 'x10', 'done'))
a(C.ldr_w(11, 10, P_ROUND))
a(C.add_wi(11, 11, 1))                                     # round + 1
a(C.cmp_wr(9, 11))
a(C.to(C.bcond, 'ne', 'done'))                             # armed for another round
a(C.ldr_w(12, 19, 4))
a(C.cmp_wr(12, 11))
a(C.to(C.bcond, 'eq', 'done'))                             # fed already this round
a(C.ldr_w(20, 19, 8))                                      # count
a(C.to(C.cbz_w, 'w20', 'done'))
a(C.cmp_wi(20, LV_MAX))
a(C.to(C.bcond, 'hi', 'done'))
a(C.ldr_x(21, 10, P_LEVEL))                                # M = [par+0x3378]
a(C.to(C.cbz_x, 'x21', 'done'))
a(C.add_xi(21, 21, 0x38))                                  # the key -> level map (as 0xEB7BA4)
a(C.str_w(11, 19, 4))                                      # fed = round + 1 (before the calls)
a(C.ldr_w(12, 19, 12))
a(C.add_wi(12, 12, 1))
a(C.str_w(12, 19, 12))                                     # runs += 1
a(C.add_xi(22, 19, 16))                                    # first entry {u16 key, s16 level}
a.label('loop')
a(C.mov_x(0, 21))
a(C.mov_x(1, 22))                                          # &key
a(C.mov_x(2, 22))                                          # &key
a(C.mov_x(3, 22))                                          # &value {key, level}
a.many(lambda pc, L: C.far_call(pc, INSERT))               # 0xEBD6A0: emplace (a key already there stays)
a(C.add_xi(22, 22, 4))
a(C.sub_wi(20, 20, 1))
a(C.to(C.cbnz_w, 'w20', 'loop'))
a.label('done')
a(C.ldp_x(0, 1, 'sp', 0))
a(C.ldp_x(2, 3, 'sp', 0x10))
a(C.ldp_x(4, 5, 'sp', 0x20))
a(C.ldp_x(29, 30, 'sp', 0x30))
a(C.ldp_x(19, 20, 'sp', 0x40))
a(C.ldp_x(21, 22, 'sp', 0x50))
a(C.add_xi('sp', 'sp', 0x60))
a.many(lambda pc, L: C.far_jump(pc, LOOKUP))               # tail call; x30 = 0x1773E08 (the hooked bl's)
words = a.words()
assert len(words) <= SIZE, len(words)
assert 0 not in words, 'an encoder is missing in cave_lib'
cave = g.cave('LEVELSHARE', T, a)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> LEVELSHARE 0x%X (x16 dead: bl site / function entry)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
HOOK_WORD = C.bl(SITE, PAD)
hook = [g.text_patch(SITE, 'bl #0xeb8ca0', HOOK_WORD, 'LEVELSHARE (chr creator -> strength lookup)')]

groups = {'LEVELSHARE_CAVE': cave + tramp, 'LEVELSHARE': hook}
order = ['LEVELSHARE_CAVE', 'LEVELSHARE']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('hook word 0x%08X at 0x%X (assist: LV_HOOK_SITE / LV_HOOK_WORD)' % (HOOK_WORD, SITE))
print('LVBOX 0x%X..0x%X (assist: LEVEL_BOX), LV_MAX %d' % (BOX, BOX + BOX_SIZE, LV_MAX))
print('registry rows (lead adds):')
print('| levelshare_gen | LVBOX | 0x%X..0x%X | LEVELSHARE {u32 armed round+1, u32 fed round+1, u32 count, u32 runs, '
      '{u16 key, s16 level}[%d]} (FAR_DATA) |' % (BOX, BOX + BOX_SIZE, LV_MAX))
print('| levelshare_gen | LEVELSHARE | 0x%X..0x%X | LEVELSHARE 0x1773E04: the host\'s strength levels into '
      '[par+0x3378]+0x38 (0xEBD6A0) before the lookup 0xEB8CA0; trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 12))
C.write_live(OUT_REL, groups, order, __doc__.split('LEVELSHARE (this file)')[0].strip())
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write("CAVES = {'LEVELSHARE': 0x%X, 'LVBOX': 0x%X, 'TRAMP': 0x%X, 'HOOK_SITE': 0x%X, 'HOOK_WORD': 0x%X}"
            % (T, BOX, PAD, SITE, HOOK_WORD) + chr(10))
