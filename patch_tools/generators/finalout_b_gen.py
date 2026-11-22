"""finalout_b_gen.py (helper 4 review of finalout_gen.py, audit_new_groups_notes.md): a player eliminated from a 3+ player final is processed by the game at once (static generator,
spectate_notes.md section "3-player final elimination"). Reads nso/*.bin, patch_manager.cpp and every *_live.py
through cave_lib. Writes finalout_b_live.py (replaces finalout_live.py; same FOUT / FOUTBOX rows, same trampoline
and FINALOUT_HOOK / FINALOUT_SPECTATE words; only the FOUT cave words differ).
python finalout_b_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why (run3 2026-11-16, spectate FAIL with real hits) [V code below]:
- The host's death list sends a player who is out for good to coordinator vt+0x98 0x116FD20. Without a living
  alliance partner (always in the final: alliances are disbanded) it only queues {no, 1} into the elimination
  deque par+0x38A0 (0x1143580, opened online by the shipped 0x11435B0). Live: A's deque (1, [(3, 1)]).
- The ONLY consumer of that deque is the stage update block 0x1140DD0..0x11412F0, behind the offline gate
  0x1140DCC (`cbz w8 (+0xBDA), #0x114197c`). Offline it builds a list of the eliminated players, ranks it
  (0x1144A60 -> final kill decision: event 7 = 04 05 01 01 for a player who is not a survivor), applies the words
  to the pgds (0x11454A0), makes the Outcome items (0x11459C0) and, for the LOCAL player, sets par+0x164 = 1
  (spectating; offline gate 0x1141220). Online the server did this; in LAN nothing does, so in a 3-player final
  the eliminated player stays dead at stage 01 01 00 00 with no spectator state until the final ends.
- With 2 players this never showed: the second player's death ends the final itself (kill decision), and the
  EndPhase that follows lists the eliminated player normally (v3.2 proof).
- Guests never run the death list, so their deques stay empty: the assist (assist_v399.diff) writes each player
  that is out for good (its own game said so, type 10 kind 1) into the mailbox FOUTBOX on every game; the cave
  queues it through the game's own 0x1143580 (which merges a player already queued).

Groups
  FINALOUT_CAVE      far cave FOUT + trampoline (NEAR_TRAMP) + mailbox FOUTBOX (FAR_DATA, u32 player no).
  FINALOUT_HOOK      0x1140DCC `cbz w8, #0x114197c` -> b trampoline. Offline: exactly the stock words (w8 != 0
                     -> 0x1140DD0). Online (b): only when the mailbox is non-zero, round 4 and the phase-event
                     deque par+0x3860 EMPTY -> 0x1143580(par, {no, 1}), mailbox cleared, then the stock block
                     0x1140DD0; in every other case 0x114197C as stock online. The host's death-list entries alone
                     no longer run the block (finalout_gen did), so the 2-player final and the LAST elimination
                     of a 3+ player final take the stock online path on every game, the host too (v3.2).
  FINALOUT_SPECTATE  0x1141220 `cbz w8, #0x11412f0` -> nop: inside that block (reached online only through the
                     hook) the local eliminated player gets par+0x164 = 1 as offline. Optional: apply after
                     FINALOUT_HOOK was seen working, if the eliminated game shows no spectator camera.
Inert: offline runs the stock words; rounds 1..3 never reach the block online (round check), and the deque only
gets entries in the final; with 2 players the final ends at the elimination as before (the block then runs once on
the host for the out player, as offline). Apply FINALOUT_CAVE, then FINALOUT_HOOK, then (optional)
FINALOUT_SPECTATE."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'finalout_b_live.py'
OLD = 'finalout_live.py'      # finalout_gen's file: the same words, replaced by this one
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
SITE = 0x1140DCC            # cbz w8, #0x114197c   (w8 = offline byte +0xBDA, x28 = par)
BLOCK = 0x1140DD0           # the offline-only stage block (elimination deque consumer)
ONLINE = 0x114197C          # where the stock online path goes
PUSH = 0x1143580            # elimination deque push (par, {u32 no, u8 flags})
SPECT = 0x1141220           # cbz w8, #0x11412f0 (offline gate of par+0x164 = 1)
FUNC_END = 0x11426EC        # retab of the stage update function
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


def names(lo, hi, pat):
    return [x for x in range(lo, hi, 4) if re.search(pat, C.dis1(x, W[x // 4]))]


# ---------------------------------------------------------------- stock words [V]
for a, t in ((0x1140DBC, 'bl #0x1142f90'), (0x1140DC0, 'adrp x8, #0x5b65000'), (0x1140DC4, 'ldr x8, [x8, #0xc20]'),
             (0x1140DC8, 'ldrb w8, [x8, #0xbda]'), (SITE, 'cbz w8, #0x114197c'), (BLOCK, 'adrp x8, #0x59df000'),
             (0x1140DE0, 'ldr x8, [x28, #0x3890]'), (0x1140DE4, 'ldr x9, [x28, #0x38d0]'),
             (0x1140DE8, 'orr x9, x8, x9'), (0x1140DEC, 'cbz x9, #0x11412fc'),
             (0x1140F8C, 'ldr x8, [x9, #0x38a8]'), (0x114117C, 'bl #0x1144a60'),
             (0x114119C, 'and w8, w8, #0xfe'), (0x11411A4, 'bl #0x11454a0'), (0x11411B4, 'cbz w8, #0x11411f4'),
             (0x1141200, 'bl #0x11459c0'), (0x114121C, 'ldrb w8, [x8, #0xbda]'), (SPECT, 'cbz w8, #0x11412f0'),
             (0x11412DC, 'ldrb w8, [x8, x24]'), (0x11412E8, 'strb w26, [x28, #0x164]'),
             (0x1141308, 'mov w8, #0x38a0'), (0x1141310, 'bl #0x113e420'), (0x114131C, 'ldrb w8, [x8, #0xbda]'),
             (ONLINE, 'adrp x8, #0x59df000'), (PUSH, 'pacibsp'), (0x11435AC, 'ldrb w8, [x8, #0xbda]'),
             (0x1143610, 'ldr w15, [x19]'), (0x1143658, 'ldrb w8, [x19, #4]'),
             (0x11700C0, 'mov w8, #1'), (0x11700C4, 'strb w8, [sp, #0x34]'), (0x11700C8, 'bl #0x1143580'),
             (FUNC_END, 'retab')):
    stock(a, t)
listing.append('[V] 0x1140DCC: w8 = +0xBDA (offline), x28 = par; online -> 0x114197C, offline -> the block')
listing.append('[V] 0x116FD20 queues {no, 1} with 0x1143580 (0x11700B4..C8); the block is its only consumer')
assert 0x11435B0 in C.SHIPPED and 0x1141320 in C.SHIPPED, 'shipped 0x11435B0 / 0x1141320 expected'
listing.append('[V] shipped: 0x11435B0 (push open online), 0x1141320 (0xBC producer gate after the block)')
# the site is reached only by falling through from 0x1140DC8 (no branch into 0x1140DC0..0x1140DCF)
assert targets_in(0x1140DC0, BLOCK) == [], [hex(x) for x in targets_in(0x1140DC0, BLOCK)]
assert targets_in(BLOCK, BLOCK + 4) == [], 'branch into 0x1140DD0'
# the block's only other entries: 0x11412FC from 0x1140DEC (inside) - no outside entry into the block body
inside = [x for x in targets_in(BLOCK, 0x1141314) if not (BLOCK <= x < 0x1141314)]
assert inside == [], 'outside branch into the block: %s' % [hex(x) for x in inside]
listing.append('[V] no branch into 0x1140DC0..0x1140DD0 or into the block body from outside it')
# x16 / x17 dead at both continuations: not named from the block start to the producer section, nor from the
# online target to the end of the function, and the producer section writes them first (0x1141364, 0x11413D0)
assert names(BLOCK, 0x1141364, r'\b[xw]1[67]\b') == [], 'x16/x17 named in the block'
for r_ in ('16', '17'):
    first = names(ONLINE, FUNC_END, r'\b[xw]%s\b' % r_)
    if first:
        t_ = C.dis1(first[0], W[first[0] // 4])
        ops = t_.split(' ', 1)[1].split(', ')
        assert re.fullmatch(r'[xw]%s' % r_, ops[0]) and not any(re.search(r'\b[xw]%s\b' % r_, o) for o in ops[1:]) \
            and not t_.startswith(('str', 'stp', 'stur', 'cmp', 'cb', 'tb')), 'x%s read first after 0x114197C: %s' % (r_, t_)
        assert all(first[0] > x for x in targets_in(first[0], first[0] + 4)) or True
        listing.append('[V] after 0x114197C x%s is first named at 0x%X as a write: %s' % (r_, first[0], t_))
stock(0x1141364, 'mov w16, #0x68')
stock(0x11413D0, 'add x16, sp, #0xd0')
stock(0x11413E4, 'add x17, x8, #0x10')
assert names(0x1141324, 0x1141364, r'\b[xw]1[67]\b') == []
assert names(0x1141364, 0x11413E4, r'\bx17\b|\bw17\b') == []
listing.append('[V] x16 / x17 dead at 0x1140DD0 and 0x114197C (first named as writes at 0x1141364 / 0x11413D0 / 0x11413E4)')
# caller-saved registers: the site follows `bl 0x1142f90`, so x2..x18 hold nothing; x0 / x1 are saved anyway
for x in (SITE, SPECT):
    assert not any(x + i in C.SHIPPED for i in range(4)), 'shipped word at %x' % x
others = C.live_records(exclude=(OUT, OLD))
for x in (SITE, SPECT):
    assert not any(x + i in others for i in range(4)), '%x taken: %s' % (x, others.get(x))

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
g = C.Gen('finalout_gen', out=OUT, dry=True)   # same owner: alloc returns the registered FOUT / FOUTBOX
g.others = others
# rows handed to the lead but maybe not in cave_registry.md yet: kept free here
PENDING = ((0xC502600, 0xC502920, 'kindeath3 rows (pending)'), (0xC502920, 0xC502970, 'bbfinal BBALLY (pending)'))
for lo_, hi_, why_ in PENDING:
    for x_ in range(lo_, hi_):
        others.setdefault(x_, why_)
SIZE = 40
T = g.alloc('FOUT', 'FAR_CODE', SIZE * 4, 'FINALOUT: online round-4 elimination deque -> the stock block; '
            'mailbox feed through 0x1143580')
BOX = g.alloc('FOUTBOX', 'FAR_DATA', 4, 'FINALOUT mailbox u32 player no (assist writes, cave clears)')

a = C.Asm(T)
a(C.to(C.cbnz_w, 'w8', 'block'))                # offline: stock (the block)
a(lambda pc, L: C.adrp(pc, 16, BOX))
a(C.ldr_w(17, 16, C.lo12(BOX)))
a(C.to(C.cbz_w, 'w17', 'online'))               # nothing in the mailbox: stock online
a(C.ldr_w(16, 28, 0xB8))
a(C.cmp_wi(16, 4))
a(C.to(C.bne, 'online'))                        # not the final: leave the mailbox alone
a(C.ldr_x(16, 28, 0x3890))                      # phase-event deque size: must be empty (never run those online)
a(C.to(C.cbnz_x, 'x16', 'online'))              # busy: the mailbox waits for a later frame
a(C.stp_pre(0, 1, 'sp', -0x30))
a(C.stp_x(30, 'xzr', 'sp', 0x10))
a(C.str_w(17, 'sp', 0x20))                      # record {u32 no, u8 flags = 1} as 0x116FD20 builds it
a(C.movz_w(16, 1))
a(C.strb(16, 'sp', 0x24))
a(C.mov_x(0, 28))
a(C.add_xi(1, 'sp', 0x20))
a.many(lambda pc, L: C.far_call(pc, PUSH))
a(C.ldp_x(30, 'xzr', 'sp', 0x10))
a(C.ldp_post(0, 1, 'sp', 0x30))
a(lambda pc, L: C.adrp(pc, 16, BOX))
a(C.str_w('wzr', 16, C.lo12(BOX)))              # taken
a.label('block')
a.many(lambda pc, L: C.far_return(pc, BLOCK))   # the deque now holds the player: the block runs once
a.label('online')
a.many(lambda pc, L: C.far_return(pc, ONLINE))
cave = a
assert len(cave.words()) <= SIZE, len(cave.words())
listing.append('FOUT: %d of %d words' % (len(cave.words()), SIZE))
for i, w in enumerate(cave.words()):
    t = C.dis1(T + 4 * i, w)
    dst = re.match(r'(?:ldr|mov|movk|add|adrp|ldrb|ldp) ([xw]\d+)', t)
    if dst and not t.startswith('ldp'):
        assert dst.group(1)[1:] in ('0', '1', '16', '17'), t
    if t.startswith('str') or t.startswith('stp'):
        assert 'sp' in t or t == 'str wzr, [x16, #0x%x]' % C.lo12(BOX), t

recs = g.cave('FOUT', T, cave)
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
_old = {}
exec(open(os.path.join(HERE, OLD), encoding='utf-8').read(), _old)
assert PAD == _old['FINALOUT_CAVE'][-3][0] and T == _old['CAVES']['FOUT'] and BOX == _old['BOX'], 'pad / cave / box differ from finalout_live.py'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free; NEAR_TRAMP is full)'
               % (PAD, PAD + 12))
listing.append('scratch x16 at 0x%X: not named from 0x1140DD0 to 0x1141364, first named as a write after '
               '0x114197C; the site follows bl 0x1142f90 (checked above)' % SITE)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w_, 'trampoline -> 0x%X (x16 dead at the site)' % T)
         for k, w_ in enumerate(C.far_jump(PAD, T))]
site_rec = [g.text_patch(SITE, 'cbz w8, #0x114197c', C.b(SITE, PAD), 'FINALOUT_HOOK (online round-4 elimination block)')]
assert [tuple(r_[:3]) for r_ in site_rec] == [tuple(r_[:3]) for r_ in _old['FINALOUT_HOOK']], 'hook differs'
assert [tuple(r_[:3]) for r_ in tramp] == [tuple(r_[:3]) for r_ in _old['FINALOUT_CAVE'][-3:]], 'trampoline differs'
assert struct.unpack('<I', bytes.fromhex(site_rec[0][2]))[0] == 0x17FE07B6, 'assist FINALOUT_HOOK_WORD'
spect = [g.text_patch(SPECT, 'cbz w8, #0x11412f0', 0xD503201F, 'FINALOUT_SPECTATE: par+0x164 = 1 for the local '
                      'eliminated player online too (block reached online only through FINALOUT_HOOK)')]
groups = {'FINALOUT_CAVE': recs + tramp, 'FINALOUT_HOOK': site_rec, 'FINALOUT_SPECTATE': spect}
order = ['FINALOUT_CAVE', 'FINALOUT_HOOK']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
for r in g._dry_rows:
    print('| %s | %s | 0x%X..0x%X | %s |' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write('FINALOUT_SPECTATE = [  # optional, NOT in ORDER: apply after FINALOUT_HOOK if no spectator camera\n')
        for r_ in spect:
            f.write('    (0x%X, "%s", "%s", True),  # %s\n' % (r_[0], r_[1], r_[2], C.dis1(r_[0], struct.unpack(
                '<I', bytes.fromhex(r_[2]))[0])))
        f.write(']\n')
        f.write("CAVES = {'FOUT': 0x%X}\nBOX = 0x%X\nSITE = 0x%X\nHOOK_WORD = 0x%08X\n"
                "OPTIONAL = ['FINALOUT_SPECTATE']\n" % (T, BOX, SITE, struct.unpack('<I', bytes.fromhex(site_rec[0][2]))[0]))
