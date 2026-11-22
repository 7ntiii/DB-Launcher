"""bbfinal_gen.py: Bloodbound Alliances final with two pairs, game half of the F3 fix (static generator,
bbfinal_notes.md; players8_notes.md F3).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes bbfinal_live.py.
python bbfinal_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

What it fixes (bbfinal_notes 2c): the final's kill decision 0x116F240 (coordinator vt+0x88) gives every listed
finalist an event: survivor (in C+0x148) -> 5, partner of a survivor (alliance entry) -> 8, else -> 7. Event 8
turns a word at stage 2 (02 01 01 00, the host's death list) into 04 04 01 01 = the winner class (team rank 1 under
rule 2), but leaves a word at stage 1 unchanged [V 0x11383E8 tables 0x4C49AA4 / 0x4C49AB3]. In LAN only the host
runs the death list, so on a guest whose own player is out while its partner lives, the own word is still
01 01 00 00: no stage 4 -> no team rank from it, no MatchResultCreate item (0x11459C0 needs stage 4) -> no Outcome
for that player. BB_ALLY_OUT does what the online server's death list did: for rule 2 only, a stage-1 word that
is about to get event 8 is first set to 02 01 01 00, so event 8 gives 04 04 01 01 on every game.

Groups
  BB_FINAL_CAVE  far cave BBALLY (19 of 20 words) + a 3-word trampoline in text padding next to the site.
  BB_ALLY_OUT    0x116F670 `mov w1, #8` (reached only from 0x116F4E4: "allied with a survivor") -> b trampoline:
                   LAN, rule byte main+0x5B65C70 == 2, entry +0x40 stage byte == 1 -> entry +0x40 = 0x00010102;
                   then (always) mov w1, #8 and back to 0x116F5A0 (the stock event call).
Inert: offline (+0xBDA) and rule != 2 run exactly the stock words; with fewer than 4 players there is no final
with two pairs (2 players = one pair, decided after Phase I; an odd count is played as Standard by the host).
Apply BB_FINAL_CAVE first, then BB_ALLY_OUT."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'bbfinal_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F
OFFL = 0x5B65C20            # world flag object; byte +0xBDA != 0 = offline
RULE = 0x5B65C70            # u8 rule byte: 2 = Bloodbound Alliances
SITE, BACK = 0x116F670, 0x116F5A0
STAGE2 = 0x00010102         # bytes 02 01 01 00 (the death list's word)
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


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


# ---------------------------------------------------------------- stock words [V]
for a, t in ((0x116F4CC, 'cmp w1, w17'), (0x116F4E0, 'ccmp w14, w9, #0, ne'), (0x116F4E4, 'b.eq #0x116f670'),
             (0x116F58C, 'mov w1, #7'), (0x116F594, 'mov w1, #5'),
             (BACK, 'add x0, x21, #0x38'), (0x116F5A4, 'sub x8, x29, #0x30'), (0x116F5A8, 'mov w2, wzr'),
             (0x116F5AC, 'bl #0x11383e8'), (0x116F5B0, 'ldur w8, [x29, #-0x28]'), (0x116F5B8, 'str w8, [x21, #0x40]'),
             (0x116F5F0, 'ldrb w8, [x8]'), (0x116F5F4, 'cmp w8, #2'), (0x116F5FC, 'str w22, [x21, #0x10]'),
             (0x116F60C, 'ldrb w9, [x9]'), (0x116F63C, 'ldr w22, [x9, x8, lsl #2]'), (0x116F400, 'str w22, [x21, #0x20]'),
             (SITE, 'mov w1, #8'), (SITE + 4, 'b #0x116f5a0'),
             (0x11383F0, 'ldr w10, [x0, #8]'), (0x11383FC, 'and w14, w10, #0xff'),
             (0x113847C, 'mov w11, #1'), (0x1138480, 'sub w13, w1, #6'), (0x11384E4, 'mov w10, #4')):
    stock(a, t)
assert targets_in(SITE, SITE + 8) == [0x116F4E4], [hex(x) for x in targets_in(SITE, SITE + 8)]
listing.append('[V] 0x116F670 is reached only from 0x116F4E4 (partner of a survivor); 0x116F5A0 = event call '
               '0x11383E8(entry+0x38): reads the word at entry+0x40, result stored back at 0x116F5B8')
# event 8 per stage: stage 2 -> 0x11384E4 (reason 4 = winner class), stage 1 -> 0x113851C (no change) [V]
jt1 = C.RO[0x4C49AB3 - C.RO_BASE + 8 - 1]
jt2 = C.RO[0x4C49AA4 - C.RO_BASE + 8 - 6]
assert 0x113845C + 4 * jt1 == 0x113851C and 0x11384B0 + 4 * jt2 == 0x11384E4, (hex(jt1), hex(jt2))
team_tab = struct.unpack_from('<5i', C.RO, 0x4C49B8C - C.RO_BASE)
assert team_tab == (2, 255, 2, 255, 2), team_tab
listing.append('[V] event 8: stage 1 -> unchanged, stage 2 -> 04 04 (winner class); rule-2 team rank table '
               '0x4C49B8C (reasons 3..7) = %r, reasons 2/4/6 -> team rank 1' % (team_tab,))
# x16 / x17: dead from the site to the end of 0x116F240 and in the event function 0x11383E8 (a leaf)
hits = [x for x in range(BACK, 0x116F6FC, 4) if re.search(r'\b[xw]1[67]\b', C.dis1(x, W[x // 4]))]
assert not hits, [hex(x) for x in hits]
# the event function uses x16 / x17 only as its jump-table scratch, written first in each block
for a_, t_ in ((0x1138440, 'adr x16, #0x113845c'), (0x1138444, 'ldrb w17, [x15, x11]'),
               (0x1138494, 'adr x16, #0x11384b0'), (0x1138498, 'ldrb w17, [x15, x13]')):
    stock(a_, t_)
hits = [x for x in range(0x11383E8, 0x1138530, 4) if re.search(r'\b[xw]1[67]\b', C.dis1(x, W[x // 4]))]
assert hits == [0x1138440, 0x1138444, 0x1138448, 0x1138458, 0x1138494, 0x1138498, 0x113849C, 0x11384AC], hits
listing.append('[V] x16 / x17 not named in 0x116F5A0..0x116F6FC; 0x11383E8 writes them before any read '
               '(dead at the hook)')
assert not any(SITE + i in C.SHIPPED for i in range(4)), 'site shipped'
others = C.live_records(exclude=(OUT,))
assert not any(SITE + i in others for i in range(4)), 'site taken: %s' % others.get(SITE)


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


PAD = find_pad(SITE, 3, (SITE,))
assert PAD, 'no padding'
listing.append('trampoline padding 0x%X..0x%X (zero, before a pacibsp, unreferenced, free)' % (PAD, PAD + 12))

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
        for i, r in enumerate(rows):
            for s in rows[i + 1:]:
                assert r['hi'] <= s['lo'] or s['hi'] <= r['lo'], 'registry overlap: %r / %r' % (r, s)
        print('NOTE: cave_registry.md has an exact duplicate row (left as it is)')
        return rows


C.read_registry = _registry_tolerant
g = C.Gen('bbfinal_gen', out=OUT, dry=True)
g.others = others
# rows handed to the lead but maybe not in cave_registry.md yet: kept free here (kindeath3 KAUTH3..KPRED3)
PENDING = ((0xC502600, 0xC502920, 'kindeath3 rows (pending)'),)
for lo_, hi_, why_ in PENDING:
    for x_ in range(lo_, hi_):
        others.setdefault(x_, why_)
SIZE = 20
T = g.alloc('BBALLY', 'FAR_CODE', SIZE * 4, 'BB_ALLY_OUT: rule 2, stage-1 partner of a survivor -> 02 01 01 00 '
            'before event 8 (LAN)')

a = C.Asm(T)
a(lambda pc, L: C.adrp(pc, 16, OFFL))
a(C.ldr_x(16, 16, C.lo12(OFFL)))
a(C.to(C.cbz_x, 'x16', 'stock'))
a(C.ldrb(17, 16, 0xBDA))
a(C.to(C.cbnz_w, 'w17', 'stock'))               # offline: stock
a(lambda pc, L: C.adrp(pc, 16, RULE))
a(C.ldrb(17, 16, C.lo12(RULE)))
a(C.cmp_wi(17, 2))
a(C.to(C.bne, 'stock'))                         # not Bloodbound: stock
a(C.ldrb(17, 21, 0x40))
a(C.cmp_wi(17, 1))
a(C.to(C.bne, 'stock'))                         # already stage 2 (host) or anything else: stock
a(C.movz_w(17, STAGE2 & 0xFFFF))
a(C.movk_w(17, STAGE2 >> 16, 1))
a(C.str_w(17, 21, 0x40))                        # 02 01 01 00, as the death list writes it
a.label('stock')
a(C.movz_w(1, 8))                               # the replaced word
a.many(lambda pc, L: C.far_return(pc, BACK))
cave = a
assert len(cave.words()) <= SIZE, len(cave.words())
listing.append('BBALLY: %d of %d words' % (len(cave.words()), SIZE))
for i, w in enumerate(cave.words()):
    t = C.dis1(T + 4 * i, w)
    assert not re.search(r'\bsp\b', t), t
    dst = re.match(r'(?:ldr|mov|movk|add|adrp|ldrb) ([xw]\d+)', t)
    if dst:
        assert dst.group(1)[1:] in ('1', '16', '17'), t
    if t.startswith('str'):
        assert t == 'str w17, [x21, #0x40]', t

recs = g.cave('BBALLY', T, cave)
tramp = [g.text_patch(PAD + 4 * k, 'udf #0', w, 'trampoline -> 0x%X (x16 dead at the site)' % T)
         for k, w in enumerate(C.far_jump(PAD, T))]
hook = [g.text_patch(SITE, 'mov w1, #8', C.b(SITE, PAD), 'BB_ALLY_OUT (rule 2: partner of a survivor, LAN)')]
groups = {'BB_FINAL_CAVE': recs + tramp, 'BB_ALLY_OUT': hook}
order = ['BB_FINAL_CAVE', 'BB_ALLY_OUT']
print('\n'.join(listing))
print('\n'.join(g.listing))
print('registry row for the lead:')
print('| bbfinal_gen | BBALLY | 0x%X..0x%X | BB_ALLY_OUT: rule 2, stage-1 partner of a survivor -> 02 01 01 00 '
      'before event 8 (LAN); trampoline 0x%X..0x%X |' % (T, T + SIZE * 4, PAD, PAD + 11))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Groups')[0].strip())
    with open(os.path.join(HERE, OUT), 'a') as f:
        f.write("CAVES = {'BBALLY': 0x%X, 'TR': 0x%X}\nSITE = 0x%X\n" % (T, PAD, SITE))
