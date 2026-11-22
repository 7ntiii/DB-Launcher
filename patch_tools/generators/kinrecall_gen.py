"""kinrecall_gen.py: a kin recalled from the Function Menu (hold Y + Down) always leaves; re-summon works after it
(static generator, kin6_notes.md). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib.
Writes kinrecall_live.py.
python kinrecall_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why (2-game run 2026-11-16, kin_recall FAIL: B (guest owner) 3 -> 4 RequestUnsummon and stuck there; A stays 3)
[V code below, kin6_notes.md 1]:
- The whole recall is decided on the OWNER's game; no message is sent for state 4, no host and no server answer:
  SummonState 0xD83360 -> 4 on the owner; RequestUnsummon 0xD83874 sets the per-frame request bit
  [[kin+0x2470]+0]+0x14C8 bit 1 (cleared every frame by 0x1904220) = HKS env IsBuddyUnsummonRequestReceived
  (0xAB00DC) and waits for the KIN'S OWN ANSWER: 0xD8375C (kin action 0x1B8 and an owner-target condition), or
  the kin chr's dead / disappear bit [[kin+0x18]+0x30]+0x18 bit 0, or step cc bits 2 / 3 (0x54 kind 1 or 0xE839DC).
  Only after that -> 8 FinishUnsummon: the owner sets step+0xD0 bits 1 | 0, the BM update 0xE80E20 hides the chr
  (BM vt+0x48 0xE84C60) and sends 0x54 kind 1 (BM vt+0x38 0xE851E0 on the others: cc bit 3 -> their 3 -> 8), then
  9 WaitRevive -> 0x54 kind 2 -> 2 on every game. Re-summon: UnsummonState 0xD82FC0 on the owner (action 0x165)
  -> kin vt+0x8F0 -> 3, 0x54 kind 0 (0xE84FC0) -> 3 on the others. 0x54 is sent with send vt+0x40 (every member)
  and read from anyone: nothing of it is server-only.
- So the stuck request is the kin's behaviour never giving its answer on the owner's game (live: 12 s, an enemy
  near) [I: either the stock in-combat wait or the behaviour not completing on that copy; the host-owner run of
  kin_recall tells which].

Groups
  KINRECALL_CAVE   far cave KREC + trampoline in text padding (NEAR_TRAMP is full).
  KINRECALL_HOOK   0xD838A8 `mov x0, x19` (RequestUnsummon, after the request bit) -> b trampoline. Offline
                   (+0xBDA != 0): the stock word. LAN, only on the OWNER's game (kin data+0xB8 == our player's
                   handle [[WCM+0x1A8]+0x20]+0x78, as dusk_lan EnemyOwners): step+0xE0 counts the seconds in state 4
                   (FD4Time dt at [x1+8], as UnsummonState 0xD832C8 reads it; +0xE0 is 0 on entry: the summon
                   0xD831D0 zeroes it and states 3 / 4 never add to it [V]); the stock wait runs as before, and only
                   if the kin has not answered after KREC_SECS (6.0 s) it goes on as if it had: +0xE0 = 0, then the
                   stock "-> 8" words 0xD838D8 (FinishUnsummon -> 0x54 kind 1 / kind 2 -> 2 everywhere).
Inert: offline stock; other games' copies are never forced (they follow the owner's 0x54 as stock); host and guest
owners alike; the re-summon needs no change (owner-local + 0x54 kind 0). Apply KINRECALL_CAVE, then
KINRECALL_HOOK."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'kinrecall_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
SITE = 0xD838A8             # mov x0, x19   (RequestUnsummon, after the 0x14C8 bit-1 request)
BACK = 0xD838AC             # bl 0xd8375c   (the stock wait)
FORCE = 0xD838D8            # ldr x8, [x19] ... vt+0x28(8): -> FinishUnsummon
FUNC = 0xD83874             # RequestUnsummon
FUNC_END = 0xD83914         # next function (RequestForceUnsummon)
SECS = 6.0
listing = []


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


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


# ---------------------------------------------------------------- stock words [V]
for a, t in ((FUNC, 'pacibsp'), (0xD83884, 'ldr x8, [x0, #0xb8]'), (0xD83888, 'mov x19, x0'),
             (0xD8388C, 'ldr x8, [x8, #0x2470]'), (0xD83894, 'cbz x8, #0xd838a8'), (0xD83898, 'mov w9, #0x14c8'),
             (0xD838A0, 'orr w10, w10, #2'), (0xD838A4, 'strb w10, [x8, x9]'),
             (SITE, 'mov x0, x19'), (BACK, 'bl #0xd8375c'), (0xD838B0, 'tbnz w0, #0, #0xd838d8'),
             (0xD838C8, 'tbnz w8, #0, #0xd838d8'), (0xD838D0, 'tst w8, #0xc'), (0xD838D4, 'b.eq #0xd83908'),
             (FORCE, 'ldr x8, [x19]'), (0xD838DC, 'mov x0, x19'), (0xD838E0, 'mov w1, #8'),
             (0xD838E4, 'ldr x8, [x8, #0x28]'), (0xD838E8, 'blr x8'), (0xD83904, 'br x1'),
             (0xD83908, 'ldr x19, [sp, #0x10]'), (0xD83910, 'retab'), (FUNC_END, 'pacibsp'),
             # SummonState 3 -> 4 (0xD8362C..0xD83654) and the +0xE0 users
             (0xD83640, 'mov w1, #4'), (0xD83654, 'mov w1, #4'),
             (0xD831D0, 'str wzr, [x19, #0xe0]'), (0xD832C8, 'ldr s0, [x20, #8]'), (0xD832CC, 'ldr s1, [x19, #0xe0]'),
             (0xD832D4, 'str s0, [x19, #0xe0]'), (0xD82FE8, 'mov x20, x1'),
             # owner test of FinishUnsummon (local player chr == the kin's owner) and the WCM pointer
             (0xD83CF0, 'adrp x8, #0x5b3c000'), (0xD83CF4, 'add x8, x8, #0xd88'), (0xD83D00, 'ldr x9, [x8, #0x1a8]'),
             (0xD83E18, 'ldrb w8, [x19, #0xd0]'), (0xD83E1C, 'orr w8, w8, #2'),
             # HKS env IsBuddyUnsummonRequestReceived = bit 1 of the request byte
             (0xAB00E0, 'mov w9, #0x14c8'), (0xAB00FC, 'ubfx w0, w8, #1, #1'),
             # offline byte as the stage code reads it
             (0x1140DC0, 'adrp x8, #0x5b65000'), (0x1140DC4, 'ldr x8, [x8, #0xc20]'),
             (0x1140DC8, 'ldrb w8, [x8, #0xbda]')):
    stock(a, t)
listing.append('[V] RequestUnsummon 0xD83874: request bit, then the wait (0xD8375C / dead bit / cc & 0xC) -> 8')
# +0xE0 is touched in the buddy step code only by UnsummonState (add dt, zero at the summon) [V scan]
e0 = [x for x in range(0xD82E44, 0xD84070, 4) if re.search(r'#0xe0\]', C.dis1(x, W[x // 4]))]
assert e0 == [0xD831D0, 0xD832CC, 0xD832D4], [hex(x) for x in e0]
listing.append('[V] step+0xE0 in 0xD82E44..0xD84070 only at 0xD831D0 (zero), 0xD832CC / 0xD832D4 (add dt in state 2)')
# the site is a branch target only from inside the function (0xD83894); the hook keeps that path
into = targets_in(SITE, SITE + 4)
assert into == [0xD83894], [hex(x) for x in into]
assert targets_in(FORCE, FORCE + 4) == [0xD838B0, 0xD838C8], [hex(x) for x in targets_in(FORCE, FORCE + 4)]
listing.append('[V] 0xD838A8 is entered by fall-through and from 0xD83894 only; 0xD838D8 from 0xD838B0 / 0xD838C8')
# x16 / x17 / s0 / s1: caller-saved and dead at the site (a bl follows at 0xD838AC on the stock path; the force path
# 0xD838D8 names x8 / x0 / x1 / x19 only before its blr / br)
for x in range(FORCE, FUNC_END, 4):
    assert not re.search(r'\b[xw]1[67]\b|\bs[01]\b', C.dis1(x, W[x // 4])), hex(x)
assert not re.search(r'\bx1\b|\bw1\b', ' '.join(C.dis1(x, W[x // 4]) for x in range(FUNC, SITE, 4))), 'x1 written before the site'
listing.append('[V] x1 (FD4Time) untouched from the entry to the site; x16 / x17 / s0 / s1 dead at both continuations')
for x in (SITE,):
    assert not any(x + i in C.SHIPPED for i in range(4)), 'shipped word at %x' % x
others = C.live_records(exclude=(OUT,))
assert not any(SITE + i in others for i in range(4)), '%x taken: %s' % (SITE, others.get(SITE))

_read_registry = C.read_registry


def _registry_tolerant():
    """an exact duplicate registry row (another helper's edit) is tolerated; any real overlap still fails"""
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
        print('NOTE: cave_registry.md has an exact duplicate row (left as it is)')
        return rows


C.read_registry = _registry_tolerant
g = C.Gen('kinrecall_gen', out=OUT, dry=True)
g.others = others
# rows handed to the lead but maybe not in cave_registry.md yet: kept free here
PENDING = ((0xC502600, 0xC502920, 'kindeath3 rows (pending)'), (0xC502920, 0xC502970, 'bbfinal BBALLY (pending)'),
           (0xC502B20, 0xC502BC0, 'finalout FOUT (pending)'), (0xC50F314, 0xC50F318, 'finalout FOUTBOX (pending)'),
           (0x10C2CA4, 0x10C2CB0, 'finalout trampoline (pending)'))
for lo_, hi_, why_ in PENDING:
    for x_ in range(lo_, hi_):
        others.setdefault(x_, why_)
SIZE = 40
T = g.alloc('KREC', 'FAR_CODE', SIZE * 4, 'KINRECALL: owner game, RequestUnsummon unanswered for 6 s -> the stock '
            '-> 8 words (FinishUnsummon)')


def raw(w):
    return lambda pc, L: w


def fp_ls(store, rt, rn, off):           # ldr / str s<rt>, [x<rn>, #off]
    return (0xBD000000 if store else 0xBD400000) | ((off // 4) << 10) | (C.R(rn) << 5) | rt


SECS_BITS = struct.unpack('<I', struct.pack('<f', SECS))[0]
assert SECS_BITS & 0xFFFF == 0
a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 16, 0x5B65C20))
a(C.ldr_x(16, 16, 0xC20))
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldrb(16, 16, 0xBDA))
a(C.to(C.cbnz_w, 'w16', 'stock'))               # offline: stock
a(C.ldr_x(16, 19, 0xB8))                        # kin chr
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_x(16, 16, 0x20))                        # kin data
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_w(17, 16, 0xB8))                        # the owner's player handle
a(C.to(C.cbz_w, 'w17', 'stock'))
a(lambda pc, L: C.adrp(pc, 16, 0x5B3CD88))
a(C.ldr_x(16, 16, 0xD88))                       # WCM
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_x(16, 16, 0x1A8))                       # our player chr
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_x(16, 16, 0x20))
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldr_w(16, 16, 0x78))                        # our player handle
a(C.cmp_wr(16, 17))
a(C.to(C.bne, 'stock'))                         # not our kin: the others follow the owner (0x54), never forced
a(raw(fp_ls(False, 0, 1, 8)))                   # s0 = dt (FD4Time)
a(raw(fp_ls(False, 1, 19, 0xE0)))
a(raw(0x1E202800 | (0 << 16) | (1 << 5) | 1))   # fadd s1, s1, s0
a(raw(fp_ls(True, 1, 19, 0xE0)))                # seconds in state 4
a(C.movz_w(16, SECS_BITS >> 16, 1))
a(raw(0x1E270000 | (16 << 5) | 0))              # fmov s0, w16
a(raw(0x1E202000 | (0 << 16) | (1 << 5)))       # fcmp s1, s0
a(lambda pc, L: C.bcond(pc, 'ge', L['force']))
a.label('stock')
a(C.mov_x(0, 19))                               # the replaced word
a.many(lambda pc, L: C.far_return(pc, BACK))
a.label('force')
a(C.str_w('wzr', 19, 0xE0))
a.many(lambda pc, L: C.far_return(pc, FORCE))
cave = a
assert len(cave.words()) <= SIZE, len(cave.words())
listing.append('KREC: %d of %d words, KREC_SECS %.1f (word 0x%08X)' % (len(cave.words()), SIZE, SECS, SECS_BITS))
expect_fp = {'ldr s0, [x1, #8]', 'ldr s1, [x19, #0xe0]', 'fadd s1, s1, s0', 'str s1, [x19, #0xe0]', 'fmov s0, w16',
             'fcmp s1, s0'}
seen_fp = set()
for i, w in enumerate(cave.words()):
    t = C.dis1(T + 4 * i, w)
    if re.match(r'(fadd|fmov|fcmp)|(ldr|str) s', t):
        seen_fp.add(t)
    dst = re.match(r'(?:ldr|mov|movk|movz|add|adrp|ldrb) ([xws]\d+)', t)
    if dst:
        assert dst.group(1)[1:] in ('0', '1', '16', '17'), t
    if t.startswith('str'):
        assert t in ('str s1, [x19, #0xe0]', 'str wzr, [x19, #0xe0]'), t
assert seen_fp == expect_fp, seen_fp ^ expect_fp
listing.append('[V gen] the cave writes only x0 / x16 / x17 / s0 / s1 and step+0xE0')
recs = g.cave('KREC', T, cave)
PACIBSP = 0xD503237F


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


def find_pad(near, n):
    """n zero words in text padding (before a pacibsp, unreferenced, free) in b reach of `near`
    (NEAR_TRAMP is full)"""
    for a_ in range(near - 0x80000, near + 0x80000, 4):
        if all(W[a_ // 4 + k] == 0 for k in range(n)) and W[a_ // 4 - 1] != 0:
            z = a_
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if any(x in C.SHIPPED or x in others for x in range(a_, a_ + 4 * n)):
                continue
            if targets_in(a_, z) or qwords_in(a_, z):
                continue
            if C.reach(near, a_):
                return a_
    return None


PAD = find_pad(SITE, 3)
assert PAD, 'no text padding near the site'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free; NEAR_TRAMP is full)'
               % (PAD, PAD + 12))
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w_, 'trampoline -> 0x%X (x16 dead at the site)' % T)
         for k, w_ in enumerate(C.far_jump(PAD, T))]
site_rec = [g.text_patch(SITE, 'mov x0, x19', C.b(SITE, PAD), 'KINRECALL_HOOK (owner: unanswered recall -> 8 after '
                         '%.0f s)' % SECS)]
groups = {'KINRECALL_CAVE': recs + tramp, 'KINRECALL_HOOK': site_rec}
order = ['KINRECALL_CAVE', 'KINRECALL_HOOK']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
print('(+ trampoline 0x%X..0x%X in text padding, no pool row)' % (PAD, PAD + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    secs_at = T + 4 * next(i for i, w in enumerate(cave.words()) if C.dis1(T + 4 * i, w).startswith('mov w16, #0x40'))
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'KREC': 0x%X}\nSITE = 0x%X\nHOOK_WORD = 0x%08X\nSECS = %.1f\nSECS_WORD_AT = 0x%X  "
                "# movz w16, #hi16(float secs), lsl #16: live tuning\n"
                % (T, SITE, struct.unpack('<I', bytes.fromhex(site_rec[0][2]))[0], SECS, secs_at))
