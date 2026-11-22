"""kindeath_gen.py: hits on a kin from another game reach the kin's owner (static generator, kin5_notes.md).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes kindeath_live.py.
python kindeath_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.
Offline (byte [*(main+0x5B65C20)]+0xBDA != 0) every hook runs the stock words. A chr is a "kin" when it is a
node chr of the buddy manager list [[[WCM]+0x5B8]+0x10]+0x10 (the same list the assist's EnemyOwners walks);
"ours" when its data +0xB8 equals our player's u32 [[WCM+0x1A8]+0x20]+0x78 (the assist's rule).

Groups
  KIN_HIT_CAVE  far caves KAUTH / KSEND and one 6-word trampoline pair in text padding.
  KIN_AUTH      0x173D99C `pacibsp` (entry of the HP-property authority test, 48 callers: the damage receivers
                0x11 at 0x17E7E64 and 0x12 at 0x17E818C among them) -> KAUTH:
                  LAN and x0 is a kin: ours -> w0 = 1 (authoritative path 0xDE0D60 on the master copy, pushed to
                  the other games), theirs -> w0 = 0 (predicted path 0xDDF720, the owner's value wins);
                  anything else -> stock (pacibsp, then 0x173D9A0).
  KIN_SEND      0x195AD90 `ldr w21, [x8, w24, uxtw #2]` (damage module 0x195AC20: outcome = table[victim
                category][attacker category]) -> KSEND: the stock load, then, in LAN only, when the victim [x20+8]
                is a kin of ANOTHER game, the attacker is ours (category 1 our player, 3 / 5 a chr this game
                drives) and the outcome is not 1 (no damage) and not already 3: outcome = 3, the stock "remote
                victim" case (w24 = 2 -> the 0x12 hit broadcast 0x14E239C at 0x195C274). A no-op when the table
                already gives 3 (the case for an enemy-class victim this game does not drive).
Apply KIN_HIT_CAVE first, then KIN_AUTH, then KIN_SEND (KIN_SEND alone is safe; KIN_AUTH alone is the main fix)."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'kindeath_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL, WCM_G = 0x5B65C20, 0x5B3CD88
AUTH, AUTH_NEXT = 0x173D99C, 0x173D9A0
SEND, SEND_NEXT = 0x195AD90, 0x195AD94
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

others = C.live_records(exclude=(OUT,))
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
assert PAD
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 24))

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
g = C.Gen('kindeath_gen', out=OUT, dry=True)
SIZES = {'KAUTH': 44, 'KSEND': 56}
T1 = g.alloc('KAUTH', 'FAR_CODE', SIZES['KAUTH'] * 4, 'KIN_AUTH: HP authority 0x173D99C, kin -> owner game only (LAN)')
T2 = g.alloc('KSEND', 'FAR_CODE', SIZES['KSEND'] * 4, 'KIN_SEND: 0x195AD90 outcome 3 for another game\'s kin (LAN)')

SUBS_W8 = 0x71000508          # subs w8, w8, #1
LDR_W21 = C.text_word(SEND)   # ldr w21, [x8, w24, uxtw #2] (position independent)
assert C.dis1(0, SUBS_W8) == 'subs w8, w8, #1'


def offline_to(a, lab):
    """offline (no world flag object, or +0xBDA set) -> lab. Clobbers x16, w17."""
    a(lambda pc, L: C.adrp(pc, 16, OFFL))
    a(C.ldr_x(16, 16, C.lo12(OFFL)))
    a(C.to(C.cbz_x, 'x16', lab))
    a(C.ldrb(17, 16, 0xBDA))
    a(C.to(C.cbnz_w, 'w17', lab))


def kin_test(a, c, ours, theirs, no):
    """chr in register c: a kin of ours -> ours, of another game -> theirs, else (or unreadable) -> no.
    Clobbers x8 (counter), x9, x10, x16, x17. Never writes c."""
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
    a(C.ldr_w(17, 10, 0xB8))                    # owner's player handle
    a(C.ldr_x(10, 16, 0x1A8))
    a(C.to(C.cbz_x, 'x10', no))                 # our chr missing: leave it to the stock code
    a(C.ldr_x(10, 10, 0x20))
    a(C.to(C.cbz_x, 'x10', no))
    a(C.ldr_w(10, 10, 0x78))                    # our handle
    a(C.cmp_wr(17, 10))
    a(C.to(C.beq, ours))
    a(C.to(C.b, theirs))


# KAUTH: entry of 0x173D99C (b, x30 = the caller's return; x16/x17 and x8..x10 free at a function entry)
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

# KSEND: 0x195AD90 (b; x0/x8/x9/x10/x16/x17 dead after the stock load, flags re-set by 0x195AD94)
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

for n, x in (('KAUTH', kauth), ('KSEND', ksend)):
    assert len(x.words()) <= SIZES[n], (n, len(x.words()))
    listing.append('%s: %d of %d words' % (n, len(x.words()), SIZES[n]))
# KAUTH must not touch the stack or x19..x30 (the stock body signs x30 after its own pacibsp)
for i, w in enumerate(kauth.words()):
    t = C.dis1(T1 + 4 * i, w)
    assert not re.search(r'\b(sp|x(19|2\d|30)|w(19|2\d))\b', t), t
for i, w in enumerate(ksend.words()):
    t = C.dis1(T2 + 4 * i, w)
    assert not re.search(r'\bsp\b', t), t
    dst = re.match(r'(?:ldr|mov|add|adrp|ldrb|subs) ([xw]\d+)', t)
    if dst:   # only w21 (the outcome) and scratch x0/x8/x9/x10/x16/x17 are written
        assert dst.group(1)[1:] in ('0', '8', '9', '10', '16', '17', '21'), t

caves = g.cave('KAUTH', T1, kauth) + g.cave('KSEND', T2, ksend)
tramps = []
for t, tgt in ((PAD, T1), (PAD + 12, T2)):
    for k, w in enumerate(C.far_jump(t, tgt)):
        tramps.append(g.text_patch(t + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 dead at both sites)' % tgt))
auth = [g.text_patch(AUTH, 'pacibsp', C.b(AUTH, PAD), 'KIN_AUTH (kin HP authority = its owner game, LAN)')]
send = [g.text_patch(SEND, 'ldr w21, [x8, w24, uxtw #2]', C.b(SEND, PAD + 12),
                     'KIN_SEND (another game\'s kin hit by us -> 0x12 broadcast, LAN)')]
groups = {'KIN_HIT_CAVE': caves + tramps, 'KIN_AUTH': auth, 'KIN_SEND': send}
order = ['KIN_HIT_CAVE', 'KIN_AUTH', 'KIN_SEND']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry rows for the lead:')
print('| kindeath_gen | KAUTH | 0x%X..0x%X | KIN_AUTH: HP authority 0x173D99C, kin -> owner game only (LAN); trampoline 0x%X..0x%X |'
      % (T1, T1 + SIZES['KAUTH'] * 4, PAD, PAD + 11))
print('| kindeath_gen | KSEND | 0x%X..0x%X | KIN_SEND: 0x195AD90 outcome 3 for another game\'s kin (LAN); trampoline 0x%X..0x%X |'
      % (T2, T2 + SIZES['KSEND'] * 4, PAD + 12, PAD + 23))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'KAUTH': 0x%X, 'KSEND': 0x%X, 'TR': 0x%X}\n" % (T1, T2, PAD))
