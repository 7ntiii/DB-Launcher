"""Rewards of each game's LOCAL player (READ-ONLY: only Mem.read / u32 / u64; never writes game memory).
python diag/twin/rewards.py [GAMES=AB] [inv] [snap NAME | diff NAME] [watch SECONDS]

  (default)    one block per game: flags, level / EXP, stakes, forge goods (= weapon affinity [I]), skill-enhancement
               offers, Power of Blood pick state + equip-skill fields, Virtue counters.
  inv          also list every inventory entry (id words + count): find the blood crystal / forge goods ids.
  snap NAME    save the local PlayerGameData (0x47F0 bytes), the inventory list and the counters per game to
               %TEMP%/rewards_snap_NAME.json (a local file outside the workspace; game memory is not touched).
  diff NAME    compare now with that snapshot: changed u32 of the pgd (labelled when known), inventory count
               changes, Virtue counter changes. Use snap before a reward and diff after it.
  watch S      repeat the default block every 0.5 s for S seconds, print a game's block only when it changed.

Addresses (rewards_notes.md has the [V]/[I] source of each):
  offline flag *(main+0x5B65C20)+0xBDA (0 in LAN), HOST byte main+0x492AFD8 (0 = host)
  item mgr     *(main+0x5B57E90) (LEVEL precondition: must be non-zero, else LEVEL is a no-op)
  net mgr      *(main+0x5B3CE08): +0x1268 mode (6 = online/LAN), +0x678 server member id, members (+0x1250-+0x1248)/0x108
  pgd          *(*(main+0x5B57EB8)+0x20): +0xD0 player no, +0x78 level, +0x7C blood (EXP), +0x104 slot index,
               +0x110 base stakes, +0x40D0 type (1 local), +0x4648/+0x4649 stake max/count, +0x46C8 own member id,
               +0x42C8 banked Virtue, +0x46D8 win-point object
  inventory    inv = pgd+0x2E8: entries of 16 bytes {u32 +0, u32 +4, u32 count +8}: index < u32 inv+0x2FC in
               [inv+0x330], else in [inv+0x320] (minus that count); total = u32 inv+0x368 + 1   [V 0xCCD4A0, I field names]
  skill offers item mgr + 0x21D8 + slot*0x20: two u64 options, u64 count at +0x18   [V 0xCFF4A0]
  Power chain  par = *(main+0x5B3CDF8) (stage), sys = par+0x2E8 [V 0x13AD828]: u8 +0x1154 = SLOT COUNT (not an
               index), map +0xE48[team] -> slot, slot = +0xE54 + slot*0x40 (+0x28 offered, +0x29 eligible),
               u8 +0x1158 = pick made by the menu (not "offer pending"), +0x1240 server 0x6B flag. Three
               'Power ...' lines + a verdict (first failing condition); see power_lines() / power_offer_notes.md.
  equip skills pgd+0xED0, +0x1C6C (0x640 bytes), +0x28F0 (Powers of Blood, summon_struggle_notes 4)   [I layout]
  Virtue       26 counters at wp+0xC18; id = vt+0x18 getter (decoded from its code), value = obj+0x68 when the
               value getter vt+0x20 is main+0xF6BEC0. Ids: 110000 small Flame, 110010 large Flame, 130000 joint
               struggle (Trespasser), 140000 kill   [V push sites, I meaning]
  weapon       (rewards2_notes.md 1) sub = [[WCM+0x1A8]+0x20]: u32 sub+0x270 = current affinity code (0/100/110/200/
               300/310/500/600) [V 0xE92AA8 write, 0x11A04B4 read]; u32 sub+0x20C+slot*4 = level digit [V 0xE93A6C];
               equip = [pgd+0x5A8] or pgd+0x430: u32 +0x28+slot*4 = equipped weapon param id = base*10000 + affinity
               + level (id % 10) [V 0xCD401C / 0xCD4120, I field names]. Forge goods 9100..9699 (asset param +0x188).
  patch words  ON/off of FORGE_OWN, FORGE_APPLY (proposed, rewards2_notes.md), SKILL_LOCAL, LEVEL, POWER_PICK,
               POWER_OFFER, read from the game's text (no write).
Expected after each reward: rewards_notes.md 'Live tests' and rewards2_notes.md section 4."""
import json
import os
import struct
import sys
import tempfile
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

GDM, WCM, ITEM_MGR, NET, PAR = 0x5B57EB8, 0x5B3CD88, 0x5B57E90, 0x5B3CE08, 0x5B3CDF8
OFFLINE, HOST, BOX = 0x5B65C20, 0x492AFD8, 0x492AFF8
GET_FIELD = 0xF6BEC0
KNOWN_IDS = {110000: 'FlameS', 110010: 'FlameL', 130000: 'JointStruggle', 140000: 'Kill'}
LABELS = {0x78: 'level', 0x7C: 'blood/EXP', 0x104: 'slot index', 0x110: 'base stakes', 0x42C8: 'banked Virtue',
          0x4648: 'stake max/count', 0xED0: 'equip skill', 0x28F0: 'equip skill'}
for _k in range(8):
    LABELS[0x430 + 0x28 + _k * 4] = 'equip id slot %d (weapon: base*10000+affinity+level)' % _k
# (address, new bytes as in memory, name): ON when the word equals the patched value
PATCH_WORDS = [(0x11A06E4, '41040054', 'FORGE_OWN'), (0xCF8F74, ('C4DFFF17', 'C7172515'), 'FORGE_OWN grant'),
               (0xD0078C, 'F303032A', 'FORGE_APPLY gate'), (0xD00798, '48000034', 'FORGE_APPLY skip-local'),
               (0xCFEA04, '12000014', 'SKILL_LOCAL lot'), (0xCFF1D8, '34000014', 'SKILL_LOCAL pick'),
               (0xCFF878, '1F2003D5', 'SKILL_LOCAL award'), (0x17BBD48, '35000014', 'LEVEL'),
               (0x100B034, '0E000014', 'POWER_PICK'), (0x100BFC0, '06000014', 'POWER_OFFER'),
               (0x15B555C, '4587FF17', 'PICKUP_ADD'), (0xCF8F70, None, 'word 0xCF8F70 (stock 08696F39 = ITEMAUTH D1 off)')]
# Law of the Deep Sea (smallgaps2_notes.md 3, reward_audit_notes.md): module [chr+0x2470]+0x2F0, masks +0x10 / +0x18;
# kill rule 0xE06FA8 needs equip skill 0x104411 on the killer (0xE070AC). HP block pgd +0x08 HP, +0x0C max, +0x10 base.
DEEPSEA_SKILL = 0x104411
# Power of Blood chain (power_offer_notes.md): (address, new bytes, name)
POWER_WORDS = [(0x100BFC0, '06000014', 'OFFER2 members'), (0x100BFE4, '1F2003D5', 'OFFER2 offline-gate'),
               (0x100DC34, 'A2808052', 'OFFER2 mask 0x405'), (0x100D3EC, '09203991', 'OFFER3 a'),
               (0x100D3F0, '29696838', 'OFFER3 b'), (0x100D3F4, '3F310071', 'OFFER3 c'),
               (0x100D3F8, '620B0054', 'OFFER3 d'), (0x100B034, '0E000014', 'PICK a'),
               (0x100B078, '1F2003D5', 'PICK b')]
THIRD_WAIT = 0x114FC40          # PrepareThird "not ready": 6D000014 = wait (stock), 02000014 = go (assist bypass)
SPECTATOR = 0x5B55D30           # CSGameWatchingManImp: u32 +0x50 mode, u8 +0x17A (0x11485D8 skip test)
MISSION = 0x5B44E88             # mission object, u32 +0xB8 row id (0x11485D8 row byte +0x4B bit 1)
STEP_NAMES = {6: 'UpdatePhase', 7: 'EndPhase', 10: 'PhaseResult', 16: 'Advance', 21: 'PrepareSecond',
              22: 'PrepareThird', 23: 'PreIntermission', 26: 'Intermission', 28: 'EndIntermission'}


REPO = 0x5B3CE68                # param repository: SkillParam +0x2310/+0x2318, rank-chance param +0x21F0/+0x21F8
POWER_OFFER4 = [(0x1012618, '28008052'), (0x1019468, '28008052'), (0x10194A0, '2A008052')]


def param_hdr(m, repo, off):
    """In-memory param header of repo slot off (count at off, holder at off+8): [[holder+0x70]+0x78]."""
    if not repo or not m.u32(repo + off):
        return 0
    h = m.u64(repo + off + 8)
    return m.u64(m.u64(h + 0x70) + 0x78) if h else 0


def param_rows(m, hdr):
    """[(id, data address)] like 0x1D2CB34 (24-byte entries when +0x2E bit 1, data -4 when version u16 +8 < 0x10)."""
    ver, n = struct.unpack('<HH', m.read(hdr + 8, 4))
    big = u8(m, hdr + 0x2E) & 2
    adj = -4 if ver < 0x10 else 0
    out = []
    raw = m.read(hdr + 0x40, n * (24 if big else 12))
    for i in range(n):
        if big:
            rid, off = struct.unpack_from('<i4xq', raw, i * 24)
        else:
            rid, off = struct.unpack_from('<iI', raw, i * 12)
        out.append((rid, hdr + off + adj))
    return out


G1800 = ((2, 0), (3, 1), (4, 1), (6, 1), (8, 3))   # CalcCorrectGraph 1800 (romfs gameparam) [V data]


def graph1800(n):
    """Tier split k of 0x1176824 (0xF58358(0x708, n), truncated); linear between knots [I curve shape]."""
    if n <= G1800[0][0]:
        return G1800[0][1]
    for (x0, y0), (x1, y1) in zip(G1800, G1800[1:]):
        if n <= x1:
            return int(y0 + (y1 - y0) * (n - x0) / (x1 - x0))
    return G1800[-1][1]


def cnt_players(m, s):
    """Players with a rank entry (rank map sys+0x1168, 0xFF = none) [I: 0x1176824 counts chrs of mask 0x407]."""
    return sum(1 for b in m.read(s + 0x1168, 12) if b != 0xFF)


def power_source_lines(m, par, s, key, slot, rnd, mid):
    """Where the slot option ids come from (power_offer_notes.md section 6), read-only [V code, I labels]:
    (a) server 0x6B (+1240); (b) local lot 0x100E980: candidates = global table sys+0x198 (every SkillParam row),
    weights = per-team pool sys+0x10+i*32 (0x1019340: SkillParam u16 +0x80 + 2*(clamp(roundrow id % 10, 2, 5) - 2)),
    gated per slot by the roll byte slot+0x3D (0x1012618: chance by rank tier > rand % 100; tiers = first row bytes
    +0x32C top / +0x32D middle / +0x32E bottom of the param at repo+0x21F0); (c) mission round row (0x100F030:
    only when the mission row exists; writes PhaseInfoParam +0xB8..+0xC4 ids into the local slot)."""
    L = []
    repo = ptr(m, REPO)
    # roll bytes of the local slot
    sb = m.read(s + 0xE54 + slot * 0x40, 0x40) if slot < 12 else bytes(0x40)
    req = struct.unpack_from('<i', sb, 0x2C)[0]
    rmap = m.read(s + 0x1168, 12)
    ri = rmap[key] if 0 <= key < 12 else 0xFF
    rank = m.u32(s + 0x1178 + ri * 16 + 8) if ri < 12 else -1
    tiers = '?'
    ch = param_hdr(m, repo, 0x21F0)
    if ch:
        t = u8(m, ch + 0x2D)
        if (t & 0x7F) == 2:
            doff = m.u32(ch + 0x34)
        elif (t & 0x80) and (u8(m, ch + 0x2E) & 2):
            doff = m.u64(ch + 0x48)
        else:
            doff = m.u32(ch + 0x44)
        tiers = '/'.join(str(x) for x in m.read(ch + doff + 0x32C, 3))
    L.append('  Power roll: local slot +2C request %d | roll +3D %d +3E %d (bytes +38..+3E %s) | rank map +1168 %s '
             '-> entry %s rank %d | chance top/mid/bottom %% %s | sys+115E %d +1160 %d | OFFER4 %s'
             % (req, sb[0x3D], sb[0x3E], sb[0x38:0x3F].hex(), rmap.hex(), ri if ri < 12 else 'none', rank, tiers,
                u8(m, s + 0x115E), m.u32(s + 0x1160),
                'ON' if all(m.read(m.base + a, 4).hex().upper() == w for a, w in POWER_OFFER4) else 'off'))
    # pools
    pidx = u8(m, s + key) if 0 <= key < 12 else 0xFF
    pn, pnz = -1, -1
    if pidx < 12:
        b0, e0 = m.u64(s + 0x10 + pidx * 32), m.u64(s + 0x18 + pidx * 32)
        if b0 and 0 <= e0 - b0 < 0x10000:
            raw = m.read(b0, e0 - b0)
            ws = [struct.unpack_from('<H', raw, i + 4)[0] for i in range(0, len(raw), 8)]
            pn, pnz = len(ws), sum(1 for w in ws if w)
    gb, ge = m.u64(s + 0x198), m.u64(s + 0x1A0)
    ib, ie = m.u64(s + 0x1B8), m.u64(s + 0x1C0)
    L.append('  Power pools: team pool index %s (count +190 %d): %d entries, %d with weight > 0 | global table '
             '+198 %d records, +1B8 %d indices [I layout]'
             % (pidx if pidx < 12 else 'none', u8(m, s + 0x190), pn, pnz,
                (ge - gb) // 0x28 if ge >= gb else -1, (ie - ib) // 4 if ie >= ib else -1))
    # live params: round row and SkillParam weights for its round index
    ro = 0
    if 1 <= rnd <= 9:
        ro = m.u64(par + 0xD0 + (rnd - 1) * 8)
    elif rnd == 0:
        ro = m.u64(par + 0x118)
    rid = m.u32(ro + 8) if ro else -1
    rowp = m.u64(ro + 0x10) if ro else 0
    rids = list(struct.unpack('<4i', m.read(rowp + 0xB8, 16))) if rowp else []
    widx = min(max(rid % 10, 2), 5) - 2 if rid not in (-1, 0xFFFFFFFF) else 0
    sk = param_hdr(m, repo, 0x2310)
    nz, tot, sample = -1, -1, []
    if sk:
        rows = param_rows(m, sk)
        tot, nz = len(rows), 0
        for sid, d in rows:
            w = struct.unpack('<H', m.read(d + 0x80 + 2 * widx, 2))[0]
            if w:
                nz += 1
                if len(sample) < 4:
                    sample.append('%d:%d' % (sid, w))
    L.append('  Power data: round row %s (id %d, weight index %d) ids +B8..+C4 %s | SkillParam rows %d, weight > 0 '
             'at index %d: %d %s | mission %d (round-row path 0x100F030 needs a mission row)'
             % ('%x' % ro if ro else 'none', rid, widx, rids, tot, widx, nz, ' '.join(sample), mid))
    # roll inputs (power_offer2_notes.md 2) [V code 0x1176824 / 0x10125A0 / 0x1013904, I player count n]
    n_pl = cnt_players(m, s)
    k = graph1800(n_pl)
    if rank < 0:
        tier = 'no rank entry (byte 0xFF default)'
    elif k >= rank:
        tier = 'TOP (+32C)'
    elif n_pl - k >= rank:
        tier = 'MIDDLE (+32D)'
    else:
        tier = 'BOTTOM (+32E)'
    bidx = u8(m, s + 0x218 + key) if 0 <= key < 12 else 0xFF
    bn, bsrc = -1, 0
    if bidx < 12:
        blk = s + 0x228 + bidx * 0x80
        b0, e0 = m.u64(blk + 0x20), m.u64(blk + 0x28)
        bn = (e0 - b0) // 4 if b0 and 0 <= e0 - b0 < 0x10000 else -1
        c0, c1 = m.u64(blk), m.u64(blk + 8)
        bsrc = (c1 - c0) // 0x28 if c0 and 0 <= c1 - c0 < 0x100000 else -1
    fu = -1
    if sk:
        fu = 0
        for sid, d in param_rows(m, sk):
            if any(x >= 0 for x in struct.unpack('<3i', m.read(d + 0x54, 12))):
                fu += 1
    L.append('  Power roll inputs: players n %d [I: slot/member count] -> tier split k = graph1800(n) %d | local rank '
             '%d -> %s, chance %s %% | roll +3D %d (lot A, new Powers) | lot B (follow-ups, mode 3): list index %s, '
             'records %d, open entries %d (chance graph 1900 at x=n) | option sources: 0x6B flag %d, lot A weights > 0 '
             '%d, SkillParam rows with follow-up ids %d, round row ids %s'
             % (n_pl, k, rank, tier, tiers, sb[0x3D], bidx if bidx < 12 else 'none', bsrc, bn,
                u8(m, s + 0x1240) if s else -1, nz, fu, rids))
    if sb[0x28] and all(struct.unpack_from('<i', sb, i * 8)[0] == -1 for i in range(4)):
        if s and u8(m, s + 0x1240):
            why = 'server 0x6B came but gave no ids'
        elif nz == 0 and pnz <= 0 and fu == 0 and all(x < 0 for x in rids):
            why = ('no local source has data (lot A weights 0, no follow-up ids, round row ids -1): the same as '
                   'offline with the shipped regulation -> no Power options at the intermission is the stock '
                   'result (POWER_OFFER4 withdrawn; Powers come from roses / Trespassers)')
        elif nz == 0 and pnz <= 0:
            why = ('every Power weight is 0 for this round and lot B / round row gave nothing -> stock result, '
                   'no options')
        elif not sb[0x3D]:
            why = 'slot roll +3D = 0 (chance %s for rank %d) -> lot 1 skipped' % (tiers, rank)
        else:
            why = 'weights and roll present but no draw: check the lot filters 0x1012DC0 / multiplier (not read)'
        L.append('  Power source verdict: slot offered with no option ids: ' + why)
    return L


def power_lines(m, pgd, chr_, members, bda):
    """Every condition of the Power of Blood offer, in chain order, read-only [V code, I labels]:
    Advance (16) sets par+0xC0 bit 7 for rounds >= 2 (0x114E068) -> PrepareSecond (21) 0x114F5EC skip test
    0x11485D8 false -> 0x100BD1C: bit 7 (else slots reset), members <= 0 or OFFER2, +0xBDA or OFFER2 -> generator
    0x100C060: slot per chr of mask 0x405/0x407 keyed by team (map sys+0xE48[team] -> slot, count sys+0x1154),
    slot+0x29 eligible (chr type not 0x14..0x18 and pgd+0x46B2 == 0), slot+0x28 offered (0x100EB78) ->
    PrepareThird (22) 0x100B680 waits for server msg 0x6B (online offers; would RESET the slots if one came;
    sets sys+0x1240) -> assist bypass -> intermission menu page 0x12C9880: 0x100D3C0 (stock: team < count;
    OFFER3: map[team] < 12) and slot+0x28 -> two-option page -> menu sets sys+0x1158 pending + choice ->
    0x100AFE8 (PICK) applies via 0x100B140 to the local slot. EndPhase (7) clears every slot+0x28 (0x100CC44)."""
    L = []
    par = ptr(m, PAR)
    if not par:
        return ['  Power of Blood: no stage object (par)']
    s = par + 0x2E8
    step, rnd, rule = m.u32(par + 0x50), m.u32(par + 0xB8), u8(m, par + 0xC0)
    cnt, pend = u8(m, s + 0x1154), u8(m, s + 0x1158)
    choice = m.read(s + 0x1159, 4).hex()
    smap = m.read(s + 0xE48, 12)
    srv_flag = u8(m, s + 0x1240)
    rounds_done = m.u64(s + 0x1248 + 0x18)
    spec = ptr(m, SPECTATOR)
    smode = m.u32(spec + 0x50) if spec else -1
    s17a = u8(m, spec + 0x17A) if spec else -1
    mis = ptr(m, MISSION)
    mid = m.u32(mis + 0xB8) if mis else -1
    p165, coord = u8(m, par + 0x165), m.u64(par + 0x3388)
    if s17a == 0:
        skip_mode = smode in (1, 4, 5)
    else:
        skip_mode = 2 <= smode <= 5
    third = m.read(m.base + THIRD_WAIT, 4).hex().upper()
    words = {}
    for a, new, name in POWER_WORDS:
        try:
            words[name] = m.read(m.base + a, 4).hex().upper() == new
        except Exception:
            words[name] = False
    off2 = all(words[k] for k in ('OFFER2 members', 'OFFER2 offline-gate', 'OFFER2 mask 0x405'))
    off3 = all(words['OFFER3 ' + k] for k in 'abcd')
    pick = words['PICK a'] and words['PICK b']
    L.append('  Power chain: step %d %s round %d | par+0xC0 %02x (bit7 offers this round: %s) | skip test: '
             'spectator mode %d +17A %d par+165 %d final-coord %x mission %d -> %s'
             % (step, STEP_NAMES.get(step, ''), rnd, rule, 'yes' if rule & 0x80 else 'NO', smode, s17a, p165,
                coord, mid, 'SKIP' if (skip_mode or p165) else 'ok (row bit / coord vt+0x50 not read)'))
    L.append('  Power words: OFFER2 %s (%s) | OFFER3 %s | PICK %s | members %d +0xBDA %d | PrepareThird wait '
             'word %s (%s)' % ('ON' if off2 else 'off', ' '.join('%s=%d' % (k[7:], v) for k, v in words.items()
                                                                if k.startswith('OFFER2')),
                               'ON' if off3 else 'off', 'ON' if pick else 'off', members, bda, third,
                               {'6D000014': 'wait', '02000014': 'go/bypass'}.get(third, '?')))
    key, typ, b46 = -1, -1, -1
    if chr_:
        sub = m.u64(chr_ + 0x20)
        if sub:
            typ = m.u32(sub + 0x18)
            gd = m.u64(sub + 0x1D0)
            if gd:
                key = struct.unpack('<b', m.read(gd + 0x104, 1))[0]
    if pgd:
        b46 = u8(m, pgd + 0x46B2)
    slot = smap[key] if 0 <= key < 12 else 0xFF
    L.append('  Power slots: count +1154 = %d | map +E48 %s | local team key %d -> slot %s | server msg 0x6B '
             'flag +1240 %d | rounds offered (set +1248 size) %d | pick pending +1158 %d choice %s'
             % (cnt, smap.hex(), key, slot if slot < 12 else 'none', srv_flag, rounds_done, pend, choice))
    for i in range(min(cnt, 12)):
        b = m.read(s + 0xE54 + i * 0x40, 0x40)
        w = struct.unpack_from('<10I', b, 0)
        L.append('    slot %d%s: words %s | +24 %d +28 offered %d +29 eligible %d +2A %d +2B %d +34 handle %04x'
                 % (i, ' (LOCAL)' if i == slot else '', ' '.join('%x' % v for v in w), w[9], b[0x28], b[0x29],
                    b[0x2A], b[0x2B], struct.unpack_from('<H', b, 0x34)[0]))
    try:
        L.extend(power_source_lines(m, par, s, key, slot, rnd, mid))
    except Exception as e:  # read-only diagnostics must never stop the block
        L.append('  Power source: read failed (%s)' % e)
    # first failing condition, in chain order
    sb = m.read(s + 0xE54 + slot * 0x40, 0x40) if slot < 12 else None
    stock_ok = 0 <= key < 12 and key < cnt
    if not rule & 0x80:
        why = 'par+0xC0 bit 7 clear: no offers this round (normal in round 1; must be set from Advance of round 2)'
    elif skip_mode or p165:
        why = 'skip test 0x11485D8 true (spectator mode / par+0x165): 0x100BD1C never called'
    elif members > 0 and not off2:
        why = 'members > 0 and POWER_OFFER2 off: offers wait for the server (0x100BFC0)'
    elif bda == 0 and not off2:
        why = '+0xBDA = 0 and POWER_OFFER2 off (0x100BFE4)'
    elif cnt == 0:
        why = 'slot count 0: generator did not run yet (before PrepareSecond) or slots were reset (bit 7 / 0x6B)'
    elif slot >= 12:
        why = 'local team key %d has no slot (mask / functor 0x1012400 did not see the local chr)' % key
    elif not sb[0x29]:
        why = 'slot not eligible +0x29 = 0 (chr type %#x in 0x14..0x18 or pgd+0x46B2 = %d)' % (typ, b46)
    elif not sb[0x28]:
        why = 'slot+0x28 offered = 0 (generator 0x100E980 skipped it, EndPhase cleared it, or picked already)'
    elif not stock_ok and not off3:
        why = 'menu test 0x100D3C0 fails: team key %d >= slot count %d (POWER_OFFER3 off) -> no Power page' % (
            key, cnt)
    else:
        why = 'all conditions pass: the intermission menu should show the two-option Power page'
    L.append('  Power verdict: ' + why)
    return L


def patch_words(m):
    out = []
    for a, new, name in PATCH_WORDS:
        try:
            cur = m.read(m.base + a, 4).hex().upper()
        except Exception:
            cur = '?'
        if new is None:                       # show the raw word only
            out.append('%s %s' % (name, cur))
            continue
        ok = (cur in new) if isinstance(new, tuple) else (cur == new)
        out.append('%s %s' % (name, 'ON' if ok else 'off'))
    return ', '.join(out)


def weapon(m, pgd):
    """(affinity code, level words, equipped ids) of the local player, all read-only."""
    wcm = ptr(m, WCM)
    chr_ = m.u64(wcm + 0x1A8) if wcm else 0
    sub = m.u64(chr_ + 0x20) if chr_ else 0
    aff = m.u32(sub + 0x270) if sub else None
    lv = list(struct.unpack('<4I', m.read(sub + 0x20C, 16))) if sub else []
    eq = m.u64(pgd + 0x5A8) or (pgd + 0x430)
    ids = list(struct.unpack('<8I', m.read(eq + 0x28, 32)))
    return aff, lv, ids


def wdecode(i):
    if i in (0, 0xFFFFFFFF):
        return '-'
    return '%d(aff %d lv %d)' % (i, (i % 1000) // 10 * 10, i % 10)

args = sys.argv[1:]
games = args[0] if args and args[0].isalpha() and args[0].isupper() else 'AB'
want_inv = 'inv' in args


def arg_after(k):
    return args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None


snap_name, diff_name, watch = arg_after('snap'), arg_after('diff'), float(arg_after('watch') or 0)


def i32(m, a): return struct.unpack('<i', m.read(a, 4))[0]
def u8(m, a): return m.read(a, 1)[0]


def ptr(m, off):
    return m.u64(m.base + off)


def local_pgd(m):
    g = ptr(m, GDM)
    return m.u64(g + 0x20) if g else 0


def inventory(m, pgd):
    inv = pgd + 0x2E8
    n1, total = m.u32(inv + 0x2FC), m.u32(inv + 0x368) + 1
    a1, a2 = m.u64(inv + 0x330), m.u64(inv + 0x320)
    out = []
    if total > 4096:
        return out
    for i in range(total):
        base = (a1 + i * 16) if i < n1 else (a2 + (i - n1) * 16)
        if not base:
            continue
        e = m.read(base, 16)
        w0, w1, cnt = struct.unpack_from('<III', e, 0)
        if w0:
            out.append((i, w0, w1, cnt))
    return out


def forge_goods(inv):
    """Entries whose id word (either) is goods 9100..9699 (forge asset param +0x188: 99240 9200, 99241 9400,
    99242 9410, 99243 9300, 99244 9500, 99245 9210, 99246 9600, 99247 9100; rewards2_notes.md 1)."""
    out = []
    for i, w0, w1, cnt in inv:
        for w in (w0, w1):
            if 9100 <= (w & 0x0FFFFFFF) <= 9699:
                out.append('%d x%d' % (w & 0x0FFFFFFF, cnt))
                break
    return out


def getter_id(m, fn):
    """Decode a tiny 'return id' getter: mov/movk w0 constant, or ldr w0,[x0,#off]. None if not that shape."""
    code = struct.unpack('<4I', m.read(fn, 16))
    val, obj_off = None, None
    for w in code:
        if w in (0xD503237F, 0xD503233F):          # pacibsp / paciasp
            continue
        if (w & 0xFF80001F) == 0x52800000:          # movz w0
            val = ((w >> 5) & 0xFFFF) << (((w >> 21) & 3) * 16)
        elif (w & 0xFF80001F) == 0x72800000 and val is not None:   # movk w0
            sh = ((w >> 21) & 3) * 16
            val = (val & ~(0xFFFF << sh)) | (((w >> 5) & 0xFFFF) << sh)
        elif (w & 0xFFC003FF) == 0xB9400000:        # ldr w0, [x0, #off]
            obj_off = ((w >> 10) & 0xFFF) * 4
        elif w in (0xD65F03C0, 0xD65F0FFF, 0xD65F0BFF):
            return val, obj_off
        else:
            return None, None
    return val, obj_off


def counters(m, pgd):
    wp = m.u64(pgd + 0x46D8)
    out = {}
    if not wp:
        return out
    for k, obj in enumerate(struct.unpack('<26Q', m.read(wp + 0xC18, 26 * 8))):
        if not obj:
            continue
        vt = m.u64(obj)
        cid, off = getter_id(m, m.u64(vt + 0x18))
        if cid is None and off is not None:
            cid = m.u32(obj + off)
        get = m.u64(vt + 0x20) - m.base
        val = m.u32(obj + 0x68) if get == GET_FIELD else None
        out[str(cid if cid is not None else 'slot%d' % k)] = val
    return out


def block(w, m):
    L = []
    off = ptr(m, OFFLINE)
    bda = u8(m, off + 0xBDA) if off else -1
    im = ptr(m, ITEM_MGR)
    net = ptr(m, NET)
    mode = m.u32(net + 0x1268) if net else -1
    srv = m.u64(net + 0x678) if net else 0
    members = (m.u64(net + 0x1250) - m.u64(net + 0x1248)) // 0x108 if net else -1
    L.append('%s offline %d host-byte %d | item mgr %x (LEVEL needs != 0) | net mode %d members %d server member %x'
             % (w, bda, u8(m, m.base + HOST), im, mode, members, srv))
    pgd = local_pgd(m)
    if not pgd:
        return L + ['  no local PlayerGameData']
    no, lvl, blood = i32(m, pgd + 0xD0), m.u32(pgd + 0x78), m.u32(pgd + 0x7C)
    idx, typ, base = u8(m, pgd + 0x104), u8(m, pgd + 0x40D0), u8(m, pgd + 0x110)
    mx, cnt = m.read(pgd + 0x4648, 2)
    mid = m.u64(pgd + 0x46C8)
    wcm = ptr(m, WCM)
    chr_ = m.u64(wcm + 0x1A8) if wcm else 0
    L.append('  player %d slot %d type %d chr %x | LEVEL %d EXP(blood) %d | stakes %d/%d base %d'
             % (no, idx, typ, chr_, lvl, blood, cnt, mx, base))
    try:
        hp, hmax, hbase = i32(m, pgd + 0x08), i32(m, pgd + 0x0C), i32(m, pgd + 0x10)
        ds = m.u64(m.u64(chr_ + 0x2470) + 0x2F0) if chr_ and m.u64(chr_ + 0x2470) else 0
        dsm = '%03x / %03x' % (m.u64(ds + 0x10) & 0xFFF, m.u64(ds + 0x18) & 0xFFF) if ds else '-'
        sk = struct.unpack('<%dI' % (0x640 // 4), m.read(pgd + 0x1C6C, 0x640)) + (m.u32(pgd + 0xED0),)
        L.append('  HP %d / max %d / base %d (max - base = level + Virtue bonus + Deep Sea) | Deep Sea masks '
                 '+10/+18 %s | skill 0x104411 (Law of the Deep Sea) in equip fields [I]: %s'
                 % (hp, hmax, hbase, dsm, 'yes' if DEEPSEA_SKILL in sk else 'no'))
    except Exception as e:
        L.append('  HP / Deep Sea read failed: %s' % e)
    L.append('  own member id %x %s server member (B3 0x10/0x12 sender check today: %s)'
             % (mid, '==' if mid == srv else '!=', 'passes' if mid == srv else 'fails'))
    inv = []
    try:
        inv = inventory(m, pgd)
    except Exception as e:
        L.append('  inventory read failed: %s' % e)
    L.append('  forge goods (hidden goods granted by the forge): %s | inventory entries %d'
             % (', '.join(forge_goods(inv)) or '-', len(inv)))
    try:
        aff, lv, ids = weapon(m, pgd)
        L.append('  weapon: affinity code %s | level words +20C %s | equip ids %s'
                 % (aff, ' '.join('%d' % v for v in lv) or '-', ' '.join(wdecode(i) for i in ids[:4])))
    except Exception as e:
        L.append('  weapon read failed: %s' % e)
    L.append('  patch words: ' + patch_words(m))
    if want_inv:
        for i, w0, w1, c in inv:
            L.append('    inv %3d  %08X %08X  x%d' % (i, w0, w1, c))
    if im and idx <= 0xB:
        e = im + 0x21D8 + idx * 0x20
        n = m.u64(e + 0x18)
        opts = [m.read(e + 8 * k, 8).hex() for k in range(min(n, 2))] if n <= 2 else ['bad count %d' % n]
        L.append('  skill-enhancement offers pending %d: %s' % (n, ' '.join(opts) or '-'))
    L.extend(power_lines(m, pgd, chr_, members, bda))
    sk = struct.unpack('<16I', m.read(pgd + 0x1C6C, 0x40))
    L.append('  equip skills [I]: +ED0 %08x +28F0 %08x +1C6C %s' % (
        m.u32(pgd + 0xED0), m.u32(pgd + 0x28F0), ' '.join('%x' % v for v in sk if v) or '-'))
    box = m.read(m.base + BOX, 8)
    cs = counters(m, pgd)
    shown = ' '.join('%s=%s' % (KNOWN_IDS.get(int(k), k) if k.isdigit() else k, '?' if v is None else v)
                     for k, v in sorted(cs.items()))
    L.append('  Virtue banked %d | box total %d count %d | counters %s'
             % (struct.unpack('<h', m.read(pgd + 0x42C8, 2))[0], *struct.unpack('<II', box), shown or '-'))
    return L


def snapshot(m):
    pgd = local_pgd(m)
    if not pgd:
        return None
    try:
        aff, lv, ids = weapon(m, pgd)
    except Exception:
        aff, lv, ids = None, [], []
    return {'pgd': m.read(pgd, 0x47F0).hex(), 'inv': inventory(m, pgd), 'cnt': counters(m, pgd),
            'wep': [aff, lv, ids]}


mems = {}
for w in games:
    try:
        mems[w] = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)

if snap_name:
    path = os.path.join(tempfile.gettempdir(), 'rewards_snap_%s.json' % snap_name)
    data = {w: snapshot(m) for w, m in mems.items()}
    open(path, 'w').write(json.dumps(data))
    print('saved', path)
    sys.exit(0)

if diff_name:
    path = os.path.join(tempfile.gettempdir(), 'rewards_snap_%s.json' % diff_name)
    old = json.loads(open(path).read())
    for w, m in mems.items():
        now, was = snapshot(m), old.get(w)
        if not now or not was:
            print(w, 'no pgd now or in the snapshot')
            continue
        a, bb = bytes.fromhex(was['pgd']), bytes.fromhex(now['pgd'])
        print('%s pgd changes:' % w)
        for o in range(0, min(len(a), len(bb)), 4):
            x, y = struct.unpack_from('<I', a, o)[0], struct.unpack_from('<I', bb, o)[0]
            if x != y:
                lab = LABELS.get(o) or ('equip skills' if 0x1C6C <= o < 0x22AC else '')
                print('  +%04X %08x -> %08x %s' % (o, x, y, lab))
        wi = {(e[1], e[2]): e[3] for e in was['inv']}
        ni = {(e[1], e[2]): e[3] for e in now['inv']}
        for k in sorted(set(wi) | set(ni)):
            if wi.get(k) != ni.get(k):
                print('  inv %08X %08X: %s -> %s' % (k[0], k[1], wi.get(k), ni.get(k)))
        if was.get('wep') != now.get('wep'):
            print('  weapon (affinity, level words, equip ids): %s -> %s' % (was.get('wep'), now.get('wep')))
        for k in sorted(set(was['cnt']) | set(now['cnt'])):
            if was['cnt'].get(k) != now['cnt'].get(k):
                print('  Virtue counter %s: %s -> %s' % (k, was['cnt'].get(k), now['cnt'].get(k)))
    sys.exit(0)

last = {}
t0 = time.time()
while True:
    for w, m in mems.items():
        try:
            s = '\n'.join(block(w, m))
        except Exception as e:
            s = '%s read failed: %s' % (w, e)
        if s != last.get(w):
            print('%6.1f\n%s' % (time.time() - t0, s), flush=True)
            last[w] = s
    if time.time() - t0 >= watch:
        break
    time.sleep(0.5)
