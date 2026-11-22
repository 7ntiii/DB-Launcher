"""Ritual Site (Shelter) state of the twin games (read-only): python diag/twin/ritual.py [GAMES=AB]
gl = *(main+0x5B3CDB0): layout record count gl+0x748 (records gl+0x548, 0xA8 each, first byte = site id), manager
entry count gl+0x4F8 (entries gl+0x10 + i*0x1A0: +0 id, +0x188 closed, 0 = open), sync flag gl+0x77C.
STONES (not pledges): gl+0x520+team = stone the team holds (0 red, 1 gold, 0xFF none); plinth list gl+0x500..0x508
(16 B: +0 id, +4 type 0 red / 1 gold, +0xD dropped).
PLEDGES: nl = *(gl+0x780), count nl+0xA60, pillars nl+8 + i*0xB0: +0 id u16, +8 owner pno, +0xC gold flag,
+0x10 signer pending pno, +0x78 candidate (-1 = none).
VIRTUE COUNTERS: wp = *(pgd+0x46D8), counter table wp+0xC18 (count byte wp+0xC10), counter id at c+8, record
vector c+0x38..c+0x40 (bytes printed; counter vt+0x50 = c+0x10, vector +0x28 there). 10020 inside kill (Sword), 10030 redstone tick, 10040 inside kill ally share,
100000 pledge, 100010 pledge (gold), 100020 pledge ally share. Notes: diag/net/site_virtue_notes.md."""
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

GDM = 0x5B57EB8
IDS = (10020, 10030, 10040, 100000, 100010, 100020)


def i32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def counters(m, pgd):
    wp = m.u64(pgd + 0x46D8)
    if not wp:
        return 'no wp'
    got = {}
    for k in range(min(m.read(wp + 0xC10, 1)[0], 48)):
        c = m.u64(wp + 0xC18 + 8 * k)
        if not c:
            continue
        cid = m.u32(c + 8)
        if cid in IDS:
            got[cid] = m.u64(c + 0x40) - m.u64(c + 0x38)   # record vector: vt+0x50 -> c+0x10, +0x28/+0x30 (0xE96A7C)
    return ' '.join('%d:%dB' % (i, got[i]) for i in IDS if i in got)


for w in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
    m = Mem(w)
    gl = m.u64(m.base + 0x5B3CDB0)
    par = m.u64(m.base + 0x5B3CDF8)
    if not gl:
        print(w, 'no site manager')
        continue
    recs, ents = m.u64(gl + 0x748), m.u64(gl + 0x4F8)
    out = []
    for i in range(min(ents, 8)):
        e = gl + 0x10 + i * 0x1A0
        out.append('id %d closed %d' % (m.read(e, 1)[0], m.read(e + 0x188, 1)[0]))
    ids = [m.read(gl + 0x548 + i * 0xA8, 1)[0] for i in range(min(recs, 8))]
    print(w, 'step', m.u32(par + 0x50) if par else -1, 'round', m.u32(par + 0xB8) if par else -1, 'layout records', recs, ids,
          'entries', ents, out, 'sync', m.read(gl + 0x77C, 1)[0])

    gdm = m.u64(m.base + GDM)
    loc = m.u64(gdm + 0x20) if gdm else 0
    team = m.u32(loc + 0x104) if loc else -1
    stones = m.read(gl + 0x520, 8)
    held = stones[team] if 0 <= team < 8 else None
    print('  stones per team', stones.hex(), 'local pno', i32(m.u32(loc + 0xD0)) if loc else -1, 'team', team,
          'holds', {0: 'red', 1: 'gold', 0xFF: 'none', None: '?'}.get(held, hex(held or 0)))
    pb, pe = m.u64(gl + 0x500), m.u64(gl + 0x508)
    pl = []
    for a in range(pb, min(pe, pb + 16 * 16), 16) if pb and pe > pb else []:
        pl.append('%d:%s%s' % (m.u32(a), 'gold' if m.u32(a + 4) else 'red', ' dropped' if m.read(a + 0xD, 1)[0] else ''))
    print('  plinths', pl)

    nl = m.u64(gl + 0x780)
    if nl:
        n = m.u64(nl + 0xA60)
        pil = []
        for i in range(min(n, 15)):
            e = nl + 8 + i * 0xB0
            pil.append('id %d owner %d gold %d signer %d cand %d' % (
                int.from_bytes(m.read(e, 2), 'little'), i32(m.u32(e + 8)), m.read(e + 0xC, 1)[0],
                i32(m.u32(e + 0x10)), i32(m.u32(e + 0x78))))
        print('  pillars', n, pil)
    else:
        print('  no pledge manager')

    if gdm:
        pgds = [('local', loc)] if loc else []
        pool = m.u64(gdm + 0x30)
        for i in range(12) if pool else []:
            p = pool + i * 0x47F0
            if p != loc and i32(m.u32(p + 0xD0)) >= 0:
                pgds.append(('pool%d' % i, p))
        for tag, p in pgds:
            print('  %s pno %d team %d  %s' % (tag, i32(m.u32(p + 0xD0)), m.u32(p + 0x104), counters(m, p)))
