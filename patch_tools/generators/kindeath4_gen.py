"""kindeath4_gen.py (v4 of kindeath_gen.py): hits on a kin from another game reach the kin's owner (static generator,
kin5_notes.md, kin8_notes.md). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib.
Writes kindeath4_live.py (v1..v3 data kept). python kindeath4_gen.py [--dry]  (from diag/net; --dry = write nothing)

v4 (2026-11-17, kin8_notes.md): [kin data+0xB8] is the owner's PLAYER NUMBER (kinstate.py "owner no"; live probe
read 2 on both games), not a chr handle. v3 compared it with handles 0x5000 / 0x5001, so nothing matched and every
kin fell to the gone-owner (authority game) rule. v4 compares it with the pgd player number
i32 [[[chr+0x20]+0x1D0]+0xD0] of our player ([WCM+0x1A8]) and of each player entry 1..11 ([[WCM+0x30]+0x38*i]),
cbz on every pointer. A zero player number (pgd not set up yet) on our side = stock. Groups and hook words as v3,
names KIN4_*; caves KAUTH4 / KSEND4 / KPRED4 are NEW ranges (v3's unregistered ranges are kept out), registered in
cave_registry.md. Trampolines are v3's, re-pointed (v3 and v4 never apply together).
Offline (byte [*(main+0x5B65C20)]+0xBDA != 0) every hook runs the stock words. A chr is a "kin" when it is a
node chr of the buddy manager list [[[WCM]+0x5B8]+0x10]+0x10 (the same list the assist's EnemyOwners walks);
"ours" when its data +0xB8 (player number) equals our player's pgd number [[[WCM+0x1A8]+0x20]+0x1D0]+0xD0.

Groups
  KIN4_HIT_CAVE far caves KAUTH4 / KSEND4 / KPRED4, a 6-word trampoline pair + one 3-word trampoline in text padding.
  KIN4_AUTH     0x173D99C `pacibsp` (entry of the HP-property authority test, 48 callers: the damage receivers
                0x11 at 0x17E7E64 and 0x12 at 0x17E818C among them) -> KAUTH:
                  LAN and x0 is a kin: ours -> w0 = 1 (authoritative path 0xDE0D60 on the master copy, pushed to
                  the other games), theirs -> w0 = 0 (predicted path 0xDDF720, the owner's value wins);
                  anything else -> stock (pacibsp, then 0x173D9A0).
  KIN4_SEND     0x195AD90 `ldr w21, [x8, w24, uxtw #2]` (damage module 0x195AC20: outcome = table[victim
                category][attacker category]) -> KSEND: the stock load, then, in LAN only, when the victim [x20+8]
                is a kin of ANOTHER game, the attacker is ours (category 1 our player, 3 / 5 a chr this game
                drives) and the outcome is not 1 (no damage) and not already 3: outcome = 3, the stock "remote
                victim" case (w24 = 2 -> the 0x12 hit broadcast 0x14E239C at 0x195C274). A no-op when the table
                already gives 3 (the case for an enemy-class victim this game does not drive).
  KIN4_PRED     0xDDF720 `pacibsp` (predicted HP-property path, 19 callers) -> KPRED: LAN and [x0] (prop -> chr)
                is a kin of ANOTHER game -> return at once (like the stock early return 0xDDF86C: no change);
                else stock. The copy then shows only the owner's value and dies when that value reaches 0.
  v3 changes (kin5_notes 9):
    - KAUTH "ours" answers 1 again (v1). v2 replayed the stock checks (enter 0x173DA0C): live, they answered 0 for
      a living kin on its owner, so no rival hit was applied anywhere. A dead kin is refused by the authoritative
      path itself (HP < 1 gates 0xDDFE00 / 0xDE0098 [V]), so a late hit / heal cannot change it.
    - gone owner: a kin whose summoner is not in our player entries 1..11 belongs to the authority game
      (u32 main+0x492AFD8 == 0, the assist's GENERATOR_IDLE): there "ours", elsewhere "theirs".
Apply KIN4_HIT_CAVE first, then KIN4_AUTH, KIN4_SEND, KIN4_PRED. v4 replaces v1..v3 (same hook words, new caves)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'kindeath4_live.py'
OLD = ('kindeath_live.py', 'kindeath2_live.py', 'kindeath3_live.py')   # kept; v4 replaces all (same hook words)
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G = 0x5B65C20, 0x5B3CD88
AUTH, AUTH_NEXT = 0x173D99C, 0x173D9A0
SEND, SEND_NEXT = 0x195AD90, 0x195AD94
PRED, PRED_NEXT = 0xDDF720, 0xDDF724
AUTH_BODY = 0x173DA0C            # `mov w0, #1` = non-NetAI branch: the stock chr+0x60 / entry +0x20 & 9 / +0x10 == 5 checks
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def fn_end(a):
    e = a + 4
    while W[e // 4] != PACIBSP:
        e += 4
    return e


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


# ================================================================ code facts [V]
for a, t in ((AUTH, 'pacibsp'), (AUTH_NEXT, 'stp x29, x30, [sp, #-0x20]!'), (0x173D9AC, 'ldr x8, [x0, #0x68]'),
             (0x17E7E64, 'bl #0x173d99c'), (0x17E818C, 'bl #0x173d99c'),
             (0x17E7EA4, 'bl #0xde0d60'), (0x17E7EAC, 'bl #0xddf720'),
             (0x17E81CC, 'bl #0xde0d60'), (0x17E81D4, 'bl #0xddf720'),
             (0x195AD60, 'ldr x0, [x20, #8]'), (0x195AD64, 'bl #0x195ca90'), (0x195AD8C, 'umaddl x8, w0, w9, x8'),
             (SEND, 'ldr w21, [x8, w24, uxtw #2]'), (SEND_NEXT, 'cmp w21, #4'), (0x195AD98, 'b.hi #0x195b06c'),
             (0x195AD9C, 'adrp x8, #0x4c50000'), (0x195ADA4, 'adr x9, #0x195adb8'), (0x195ADA8, 'ldrh w10, [x8, x21, lsl #1]'),
             (0x195B040, 'mov w26, wzr'), (0x195B044, 'mov w24, #2'),
             (0x195C124, 'cmp w24, #2'), (0x195C274, 'bl #0x14e239c')):
    stock(a, t)
listing.append('[V] stock words checked (authority entry, both receivers, outcome load, 0x12 send)')
# outcome jump table 0x4C50FA8 (u16 x5): case 3 = 0x195B040 (w24 = 2: the 0x12 broadcast)
jt = struct.unpack_from('<5H', C.RO, 0x4C50FA8 - C.RO_BASE)
assert 0x195ADB8 + 4 * jt[3] == 0x195B040, [hex(0x195ADB8 + 4 * x) for x in jt]
# victim rows 4 / 6 (not driven here) give 3 for attacker 1 / 3 / 5 in both tables [V]
for tb in (0x4C50FC0, 0x4C51084):
    for v in (4, 6):
        row = struct.unpack_from('<7I', C.RO, tb + 0x1C * v - C.RO_BASE)
        assert row[1] == 3, (hex(tb), v, row)
listing.append('[V] outcome table: case 3 -> 0x195B040; rows 4/6 col 1 = 3 in 0x4C50FC0 and 0x4C51084')
for f in (0x195AC20, AUTH):
    e = fn_end(f)
    hits = [x for x in range(f, e, 4) if W[x // 4] and re.search(r'\b[xw]1[67]\b', C.dis1(x, W[x // 4]))]
    assert not hits, (hex(f), [hex(x) for x in hits])
    listing.append('0x%X..0x%X: x16/x17 never named' % (f, e))
# x0, x8, x9, x10 dead after 0x195AD90 on every path: 0x195AD94 cmp w21, then adrp x8 / adr x9 / ldrh w10
# before any read; the five cases write x0 before reading it (0x195ADBC, 0x195B014, 0x195B054, 0x195BD9C/BDD8).
for a, t in ((0x195ADB8, 'ldr x24, [x20, #8]'), (0x195ADBC, 'mov x0, x24'), (0x195B014, 'ldr x0, [x8]'),
             (0x195B054, 'mov x0, x20'), (0x195BD9C, 'mov x0, x20'), (0x195BDD8, 'mov x0, x20'),
             (0x195B06C, 'mov w24, w26')):
    stock(a, t)
listing.append('[V] x0/x8/x9/x10 written before read after 0x195AD90 (all 5 cases + b.hi)')
for a in (AUTH, SEND):
    assert not any(a + i in C.SHIPPED for i in range(4)), '%x shipped' % a

others = C.live_records(exclude=(OUT,) + OLD)
for a in (AUTH, SEND):
    assert not any(a + i in others for i in range(4)), '%x in %s' % (a, others.get(a))


def find_pad(near, n, sites):
    for a in range(near - 0x80000, near + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if all(C.reach(s, a + 12 * i) for i, s in enumerate(sites)):
                return a
    return None


PAD = find_pad(0x1850000, 6, (AUTH, SEND))
assert PAD == 0x17D34A4, hex(PAD)   # the v1 / v3 pair, re-pointed
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 24))
for k in range(24):
    others[PAD + k] = 'v2 pair'      # keep PAD2 off the pair
PAD2 = find_pad(PRED, 3, (PRED,))
assert PAD2
for k in range(24):
    del others[PAD + k]
listing.append('trampoline padding 0x%X..0x%X for KPRED' % (PAD2, PAD2 + 12))
for a, t in ((PRED, 'pacibsp'), (PRED_NEXT, 'sub sp, sp, #0x70'), (0xDDF74C, 'mov x20, x0'),
             (0xDDF770, 'ldr x8, [x20]'), (0xDDF778, 'ldr x8, [x8, #0x2470]'),
             (0xDDF86C, 'ldp x20, x19, [sp, #0x60]'), (0xDDF880, 'retab'),
             (AUTH_BODY, 'mov w0, #1'), (0x173DA10, 'ldr x8, [x19, #0x60]'), (0x173DA30, 'ldr x19, [sp, #0x10]'),
             (0x173DA34, 'ldp x29, x30, [sp], #0x20'), (0x173DA38, 'retab'), (0x173D9A4, 'str x19, [sp, #0x10]'),
             (0x173D9A8, 'mov x29, sp'), (0x173D9B0, 'mov x19, x0')):
    stock(a, t)
assert not any(PRED + i in C.SHIPPED or PRED + i in others for i in range(4)), 'KPRED site taken'
pre = [x for x in range(PRED, 0xDDF754, 4) if re.search(r'\b[xw](8|9|10|11|16|17)\b', C.dis1(x, W[x // 4]))]
assert not pre, [hex(x) for x in pre]
listing.append('[V] 0xDDF720 (void; x0 = prop, [prop] = chr): x8..x11 / x16 / x17 not named before 0xDDF754; '
               'stock early return 0xDDF86C exists')

_read_registry = C.read_registry


def _registry_tolerant():
    """cave_registry.md may hold one row twice while another helper edits it (same owner, tag and range,
    other purpose text): keep the first; any real overlap still fails in the stock check."""
    try:
        return _read_registry()
    except AssertionError:
        rows, seen = [], set()
        for line in open(C.REGISTRY, encoding='utf-8'):
            m = C._ROW.match(line.strip())
            if m:
                key = (m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16))
                if key not in seen:
                    seen.add(key)
                    rows.append(dict(owner=key[0], tag=key[1], lo=key[2], hi=key[3], purpose=m.group(5)))
        for i, r in enumerate(rows):
            for s in rows[i + 1:]:
                assert r['hi'] <= s['lo'] or s['hi'] <= r['lo'], 'registry overlap: %r / %r' % (r, s)
        print('NOTE: cave_registry.md has an exact duplicate row (left as it is)')
        return rows


C.read_registry = _registry_tolerant
g = C.Gen('kindeath_gen', out=OUT, dry=DRY)
g.others = dict(others)
_v3 = {}
exec(open(os.path.join(HERE, 'kindeath3_live.py'), encoding='utf-8').read().split('CAVES = ')[1].split('\n')[0].join(
    ('_v3.update(', ')')))
for _lo, _n in ((_v3['KAUTH3'], 64 * 4), (_v3['KSEND3'], 72 * 4), (_v3['KPRED3'], 64 * 4)):
    for _x in range(_lo, _lo + _n):
        g.others[_x] = 'kindeath3_live.py cave (unregistered, kept out)'
SIZES = {'KAUTH4': 72, 'KSEND4': 80, 'KPRED4': 72}
T1 = g.alloc('KAUTH4', 'FAR_CODE', SIZES['KAUTH4'] * 4,
             'KIN_AUTH v4: kin -> owner game by player number (gone owner: the authority game) (LAN)')
T2 = g.alloc('KSEND4', 'FAR_CODE', SIZES['KSEND4'] * 4, 'KIN_SEND v4: 0x195AD90 outcome 3 for another game\'s kin (LAN)')
T3 = g.alloc('KPRED4', 'FAR_CODE', SIZES['KPRED4'] * 4, 'KIN_PRED v4: 0xDDF720 drops local HP events on another game\'s kin (LAN)')

SUBS_W8 = 0x71000508          # subs w8, w8, #1
LDR_W21 = C.text_word(SEND)   # ldr w21, [x8, w24, uxtw #2] (position independent)
assert C.dis1(0, SUBS_W8) == 'subs w8, w8, #1'
GEN_IDLE = 0x492AFD8          # u32, assist-written: 0 = this game is the authority (dusk_lan.cpp GENERATOR_IDLE)
PLAYER_SLOTS = 12             # WCM+0x30 entries (dusk_lan.cpp MAX_ENTRIES), entry 0 = our player

# the authoritative path refuses a dead chr by itself [V] (kin4_notes 1b): a late hit / heal on a dead kin
for a_, t_ in ((0xDDFE00, 'ldr w10, [x10, #0x290]'), (0xDDFE04, 'cmp w10, #1'), (0xDDFE08, 'b.lt #0xddfe9c'),
               (0xDE0098, 'ldr w9, [x9, #0x290]'), (0xDE009C, 'cmp w9, #0')):
    stock(a_, t_)
listing.append('[V] 0xDE0D60 path: HP < 1 gate at 0xDDFE00..08 and 0xDE0098 (dead kin refused there)')


def offline_to(a, lab):
    """offline (no world flag object, or +0xBDA set) -> lab. Clobbers x16, w17."""
    a(lambda pc, L: C.adrp(pc, 16, OFFL))
    a(C.ldr_x(16, 16, C.lo12(OFFL)))
    a(C.to(C.cbz_x, 'x16', lab))
    a(C.ldrb(17, 16, 0xBDA))
    a(C.to(C.cbnz_w, 'w17', lab))


def kin_test(a, c, ours, theirs, no):
    """chr in register c: a kin of ours -> ours, of another game -> theirs, else (or unreadable) -> no.
    v3: a kin whose summoner is not among our player entries 1..11 (gone / cut) belongs to the authority
    game (GEN_IDLE == 0 -> ours, else theirs). Clobbers x8 (counter), x9, x10, x16, x17. Never writes c."""
    a(lambda pc, L: C.adrp(pc, 16, WCM_G))
    a(C.ldr_x(16, 16, C.lo12(WCM_G)))           # WCM
    a(C.to(C.cbz_x, 'x16', no))
    a(C.ldr_x(17, 16, 0x5B8))
    a(C.to(C.cbz_x, 'x17', no))
    a(C.ldr_x(17, 17, 0x10))                    # buddy manager
    a(C.to(C.cbz_x, 'x17', no))
    a(C.add_xi(9, 17, 0x10))                    # list head
    a(C.ldr_x(10, 9, 0))                        # first node
    a(C.movz_w(8, 64))
    a.label('loop' + no)
    a(C.cmp_xr(10, 9))
    a(C.to(C.beq, no))
    a(C.to(C.cbz_x, 'x10', no))
    a(C.ldr_x(17, 10, 0x10))                    # node chr
    a(C.cmp_xr(17, c))
    a(C.to(C.beq, 'found' + no))
    a(C.ldr_x(10, 10, 0))
    a(SUBS_W8)
    a(C.to(C.bne, 'loop' + no))
    a(C.to(C.b, no))
    a.label('found' + no)
    a(C.ldr_x(10, c, 0x20))
    a(C.to(C.cbz_x, 'x10', no))
    a(C.ldr_w(17, 10, 0xB8))                    # summoner's PLAYER NUMBER (v4, kin8_notes)
    a(C.ldr_x(10, 16, 0x1A8))
    a(C.to(C.cbz_x, 'x10', no))                 # our chr missing: leave it to the stock code
    a(C.ldr_x(10, 10, 0x20))
    a(C.to(C.cbz_x, 'x10', no))
    a(C.ldr_x(10, 10, 0x1D0))                   # our PlayerGameData
    a(C.to(C.cbz_x, 'x10', no))
    a(C.ldr_w(10, 10, 0xD0))                    # our player number
    a(C.to(C.cbz_w, 'w10', no))                 # not set up yet: stock
    a(C.cmp_wr(17, 10))
    a(C.to(C.beq, ours))
    # another player's kin: is that player still here (entries 1..11)?
    a(C.ldr_x(9, 16, 0x30))
    a(C.to(C.cbz_x, 'x9', 'gone' + no))
    a(C.movz_w(8, PLAYER_SLOTS - 1))
    a.label('ploop' + no)
    a(C.add_xi(9, 9, 0x38))
    a(C.ldr_x(10, 9, 0))
    a(C.to(C.cbz_x, 'x10', 'pnext' + no))
    a(C.ldr_x(10, 10, 0x20))
    a(C.to(C.cbz_x, 'x10', 'pnext' + no))
    a(C.ldr_x(10, 10, 0x1D0))                   # entry's PlayerGameData
    a(C.to(C.cbz_x, 'x10', 'pnext' + no))
    a(C.ldr_w(10, 10, 0xD0))                    # entry's player number
    a(C.cmp_wr(10, 17))
    a(C.to(C.beq, theirs))                      # summoner present: its game decides
    a.label('pnext' + no)
    a(SUBS_W8)
    a(C.to(C.bne, 'ploop' + no))
    a.label('gone' + no)                        # summoner gone: the authority game takes the kin
    a(lambda pc, L: C.adrp(pc, 10, GEN_IDLE))
    a(C.ldr_w(10, 10, C.lo12(GEN_IDLE)))
    a(C.to(C.cbz_w, 'w10', ours))
    a(C.to(C.b, theirs))


# KAUTH3: entry of 0x173D99C. v3 = v1's answer for "ours" (1). v2's replay of the stock checks (0x173DA0C) answered
# 0 for a living kin on its owner (live: owner HP 515 never moved) - a dead kin is refused by 0xDE0D60 itself.
a = C.Asm(T1)
offline_to(a, 'stock')
kin_test(a, 0, 'ours', 'theirs', 'stock')
a.label('ours')
a(C.movz_w(0, 1))
a(C.RET)
a.label('theirs')
a(C.mov_w(0, 'wzr'))
a(C.RET)
a.label('stock')
a(PACIBSP)
a.many(lambda pc, L: C.far_jump(pc, AUTH_NEXT))
kauth = a

# KSEND3: 0x195AD90 (b; x0/x8/x9/x10/x16/x17 dead after the stock load, flags re-set by 0x195AD94)
a = C.Asm(T2)
a(LDR_W21)
offline_to(a, 'back')
a(C.cmp_wi(21, 3))
a(C.to(C.beq, 'back'))
a(C.cmp_wi(21, 1))
a(C.to(C.beq, 'back'))                          # never turn "no damage" into damage
a(C.cmp_wi(24, 1))
a(C.to(C.beq, 'att'))
a(C.cmp_wi(24, 3))
a(C.to(C.beq, 'att'))
a(C.cmp_wi(24, 5))
a(C.to(C.bne, 'back'))                          # attacker not ours (remote copies settle nothing here)
a.label('att')
a(C.ldr_x(0, 20, 8))                            # victim chr
a(C.to(C.cbz_x, 'x0', 'back'))
kin_test(a, 0, 'back', 'theirs', 'back')
a.label('theirs')
a(C.movz_w(21, 3))
a.label('back')
a.many(lambda pc, L: C.far_return(pc, SEND_NEXT))
ksend = a

# KPRED3: entry of 0xDDF720 (b; x30 = the caller's return; args x0..x5 kept; x8..x11 / x16 / x17 free)
a = C.Asm(T3)
offline_to(a, 'stock')
a(C.ldr_x(11, 0, 0))                            # chr = [prop]
a(C.to(C.cbz_x, 'x11', 'stock'))
kin_test(a, 11, 'stock', 'drop', 'stock')
a.label('drop')
a(C.RET)                                        # another game's kin: no local HP change; the owner's value comes in
a.label('stock')
a(PACIBSP)
a.many(lambda pc, L: C.far_jump(pc, PRED_NEXT))
kpred = a

for n, x in (('KAUTH4', kauth), ('KSEND4', ksend), ('KPRED4', kpred)):
    assert len(x.words()) <= SIZES[n], (n, len(x.words()))
    listing.append('%s: %d of %d words' % (n, len(x.words()), SIZES[n]))
for base, x, ok in ((T1, kauth, ('0', '8', '9', '10', '16', '17')), (T2, ksend, ('0', '8', '9', '10', '16', '17', '21')),
                    (T3, kpred, ('8', '9', '10', '11', '16', '17'))):
    for i, w in enumerate(x.words()):
        t = C.dis1(base + 4 * i, w)
        assert not re.search(r'\bsp\b', t), t
        dst = re.match(r'(?:ldr|mov|add|adrp|ldrb|subs) ([xw]\d+)', t)
        if dst:
            assert dst.group(1)[1:] in ok, t

caves = g.cave('KAUTH4', T1, kauth) + g.cave('KSEND4', T2, ksend) + g.cave('KPRED4', T3, kpred)
tramps = []
for t, tgt in ((PAD, T1), (PAD + 12, T2), (PAD2, T3)):
    for k, w in enumerate(C.far_jump(t, tgt)):
        tramps.append(g.text_patch(t + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 dead at both sites)' % tgt))
auth = [g.text_patch(AUTH, 'pacibsp', C.b(AUTH, PAD), 'KIN_AUTH (kin HP authority = its owner game, LAN)')]
send = [g.text_patch(SEND, 'ldr w21, [x8, w24, uxtw #2]', C.b(SEND, PAD + 12),
                     'KIN_SEND (another game\'s kin hit by us -> 0x12 broadcast, LAN)')]
pred = [g.text_patch(PRED, 'pacibsp', C.b(PRED, PAD2), 'KIN_PRED (no local HP event on another game\'s kin, LAN)')]
groups = {'KIN4_HIT_CAVE': caves + tramps, 'KIN4_AUTH': auth, 'KIN4_SEND': send, 'KIN4_PRED': pred}
order = ['KIN4_HIT_CAVE', 'KIN4_AUTH', 'KIN4_SEND', 'KIN4_PRED']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows (%s; v1 rows KAUTH / KSEND can be deleted by the lead once v4 is used):' % (
    'dry: NOT written' if DRY else 'written by alloc'))
print('| kindeath_gen | KAUTH4 | 0x%X..0x%X | KIN_AUTH v4: kin -> owner game by player number (LAN); trampoline 0x%X..0x%X |'
      % (T1, T1 + SIZES['KAUTH4'] * 4, PAD, PAD + 11))
print('| kindeath_gen | KSEND4 | 0x%X..0x%X | KIN_SEND v4: 0x195AD90 outcome 3 for another game\'s kin (LAN); trampoline 0x%X..0x%X |'
      % (T2, T2 + SIZES['KSEND4'] * 4, PAD + 12, PAD + 23))
print('| kindeath_gen | KPRED4 | 0x%X..0x%X | KIN_PRED v4: 0xDDF720 drops local HP events on another game\'s kin (LAN); trampoline 0x%X..0x%X |'
      % (T3, T3 + SIZES['KPRED4'] * 4, PAD2, PAD2 + 11))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'KAUTH4': 0x%X, 'KSEND4': 0x%X, 'KPRED4': 0x%X, 'TR': 0x%X, 'TR2': 0x%X}\n"
                "REPLACES = ['kindeath_live.py', 'kindeath2_live.py', 'kindeath3_live.py']\n" % (T1, T2, T3, PAD, PAD2))
