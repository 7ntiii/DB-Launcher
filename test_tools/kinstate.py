"""Kin state of the twin games, READ ONLY (memory reads through mem.py / world_lib; nothing is written).
python diag/twin/kinstate.py GAMES [nocircles]      e.g.  kinstate.py AB   or   kinstate.py ABC nocircles

Per game:
  - flags: offline +0xBDA (*(main+0x5B65C20)+0xBDA), HOST byte main+0x492AFD8 (0 = host)
  - every player chr (WCM+0x30 entries): player no, and its PlayerGameData kin ring (kin_rules_notes.md section 3):
      pgd = [[chr+0x20]+0x1D0]; cur = u32 pgd+0x475C; slot k = 0..2:
      EXP total u32 pgd+0x4740+4k, EXP toward next u32 pgd+0x474C+4k, level s8 pgd+0x4758+k   [V 0xE94E40, 0xAAF3DC]
      the current kin uses slot cur (cur > 2 -> level 1, EXP 0); pgd+0x4698 = summon param of the last create [V 0xD8AFE8]
  - every kin in the BuddyManager BM = [[WCM+0x5B8]+0x10] (node +8 next, +0x10 chr, +0x30 summon state step):
      owner no [chr+0x20]+0xB8, BuddyParam id [chr+0x20]+0xB4, chr id u16 [chr+0x20]+0x78, HP, position,
      step state +0x50 (names below [I]), flags +0xC0 / +0xC8 / u16 +0xCC (bit 4 = revive allowed, set by 0x54
      kind 2 [V 0xE85320]) / u8 +0xD0, unsummoned time f32 +0xE0
      delete-pending count BM+0x40, pending 0x36 queue BM+0x50..+0x58 (0x70 bytes each)
  - circles (unless 'nocircles'): AEG099_290/291/292 (big, type info+0x306), 99295 (small), 920250:
      holder s32 info+0x460, per-player used bits info+0x468 (low 12), used byte info+0x470, off flag
Compare games: the same owner's level / EXP / cur must match on every game (else kin HP / attack differ)."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, fmt3, GAMEDATA_G

HOST_BYTE = 0x492AFD8
STATES = {0: 'Init', 1: 'ResLoad', 2: 'Unsummon', 3: 'Summon', 4: 'RequestUnsummon', 5: 'RequestForceUnsummon',
          6: 'FadeoutForceUnsummon', 7: 'DeadAnim', 8: 'FinishUnsummon', 9: 'WaitRevive'}   # table 0x5B5AD20 [V names]
CIRCLES = {99290: 'big-290', 99291: 'big-291', 99292: 'big-292', 99295: 'small', 920250: 'kinEXP-920250'}
TYPE = {1: 'Ring', 2: 'Blade', 3: 'Eye'}


def s8(v):
    return None if v is None else (v - 256 if v > 127 else v)


def ring(w, pgd):
    if not pgd:
        return None
    raw = w.rd(pgd + 0x4740, 0x20)
    if not raw:
        return None
    exp = struct.unpack_from('<3I', raw, 0)
    nxt = struct.unpack_from('<3I', raw, 0xC)
    lvl = [s8(x) for x in raw[0x18:0x1B]]
    cur = struct.unpack_from('<I', raw, 0x1C)[0]
    return {'cur': cur, 'exp': exp, 'next': nxt, 'lvl': lvl,
            'now_lvl': lvl[cur] if cur <= 2 else 1, 'now_exp': exp[cur] if cur <= 2 else 0,
            'param': w.q(pgd + 0x4698), 'no': w.i(pgd + 0xD0)}


def players(w):
    out = []
    for k, e in enumerate(w.players()):
        c = e[0]
        data = w.q(c + 0x20)
        pgd = w.q(data + 0x1D0) if data else None
        out.append({'k': k, 'chr': c, 'pgd': pgd, 'ring': ring(w, pgd), 'hp': w.chr_hp(c)})
    return out


def kins(w):
    wcm = w.wcm()
    x = w.q(wcm + 0x5B8) if wcm else None
    bm = w.q(x + 0x10) if x else None
    if not bm:
        w.null('BuddyManager [[WCM+0x5B8]+0x10]')
        return None, []
    head = {'bm': bm, 'count': w.d(bm + 0x20), 'delcount': w.d(bm + 0x40),
            'queue': ((w.q(bm + 0x58) or 0) - (w.q(bm + 0x50) or 0)) // 0x70}
    out, node, k = [], w.q(bm + 0x18), 0
    while node and node != bm + 0x10 and k < 16:
        c = w.q(node + 0x10)
        cd = w.q(c + 0x20) if c else None
        st = w.q(node + 0x30)
        out.append({
            'node': node, 'chr': c,
            'owner': w.i(cd + 0xB8) if cd else None,
            'buddy': w.i(cd + 0xB4) if cd else None,
            'id': w.h(cd + 0x78) if cd else None,
            'hp': w.chr_hp(c) if c else None,
            'pos': w.chr_pos(c) if c else None,
            'state': w.d(st + 0x50) if st else None,
            'c0': w.b(st + 0xC0) if st else None, 'c8': w.b(st + 0xC8) if st else None,
            'cc': w.h(st + 0xCC) if st else None, 'd0': w.b(st + 0xD0) if st else None,
            'unsummoned_s': w.f(st + 0xE0) if st else None,
        })
        node, k = w.q(node + 8), k + 1
    return head, out


def circles(w):
    out, counts = [], {}
    for blockid, k, ins in w.all_geoms(limit=200000):
        info = w.q(ins + 0x10)
        aid = w.i(info + 0x18) if info else None
        if aid is None:
            continue
        aid %= 10000000
        if aid not in CIRCLES:
            continue
        counts[aid] = counts.get(aid, 0) + 1
        holder, mask, used = w.i(info + 0x460), w.q(info + 0x468), w.b(info + 0x470)
        z = w.q(info + 0x20)
        off = bool(z) and w.b(z + 0xD) == 1
        interesting = aid != 99295 or (holder not in (None, -1)) or (mask or 0) & 0xFFF or used
        if interesting or counts[aid] <= 2:
            out.append((aid, ins, w.b(info + 0x306), holder, (mask or 0) & 0xFFF, used, off, w.geom_pos(ins)))
    return out, counts


def show(g, with_circles):
    w = W(g)
    gd = w.g(GAMEDATA_G)
    bda = w.b(gd + 0xBDA) if gd else None
    host = w.b(w.base + HOST_BYTE)
    print('==== game %s: offline +0xBDA = %s, HOST byte = %s (%s)' % (g, bda, host, 'host' if host == 0 else 'guest'))
    for p in players(w):
        r = p['ring']
        if r:
            print('  player %d chr %s no %s HP %s | kin ring cur %s: level %s EXP %s (to next %s) | slots lvl %s exp %s next %s | param %s' % (
                p['k'], w.rel(p['chr']), r['no'], p['hp'], r['cur'], r['now_lvl'], r['now_exp'],
                r['next'][r['cur']] if r['cur'] <= 2 else 0, r['lvl'], list(r['exp']), list(r['next']),
                None if r['param'] is None else '%x' % r['param']))
        else:
            print('  player %d chr %s: no PlayerGameData at [[chr+0x20]+0x1D0] (%s)' % (p['k'], w.rel(p['chr']), w.rel(p['pgd'])))
    head, ks = kins(w)
    if head:
        print('  BM %s: count %s, delete-pending %s, 0x36 queue %s' % (w.rel(head['bm']), head['count'], head['delcount'], head['queue']))
    for k in ks:
        cc = k['cc']
        print('  kin owner %s buddy %s id %s chr %s HP %s %s | state %s %s | c0 %s c8 %s cc %s (revive-ok %s) d0 %s | unsummoned %.1f s | pos %s' % (
            k['owner'], k['buddy'], None if k['id'] is None else '%04x' % k['id'], w.rel(k['chr']), k['hp'],
            'alive' if (k['hp'] or 0) > 0 else 'DEAD/0', k['state'], STATES.get(k['state'], '?'),
            k['c0'], k['c8'], None if cc is None else '%04x' % cc, None if cc is None else bool(cc & 0x10), k['d0'],
            k['unsummoned_s'] or 0.0, fmt3(k['pos'])))
    if with_circles:
        cs, counts = circles(w)
        for aid, ins, typ, holder, mask, used, off, pos in cs:
            print('  circle %s geom %s type %s holder %s used-bits %03x used %s%s pos %s' % (
                CIRCLES[aid], w.rel(ins), TYPE.get(typ, typ), holder, mask, used, ' off' if off else '', fmt3(pos)))
        print('  circle counts %s' % {CIRCLES[a]: n for a, n in counts.items()})
    w.report_missing()


def main():
    games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
    with_circles = 'nocircles' not in sys.argv
    for g in games:
        show(g, with_circles)


if __name__ == '__main__':
    main()
