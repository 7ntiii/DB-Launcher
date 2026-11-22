"""Virtue (win points) of every player as each twin game sees it. READ-ONLY (only Mem.read).
python diag/twin/virtue.py [GAMES=AB] [-v]       (-v: also the 26 counter objects per player)

Per game: score manager par[0x148] kind (vtable main+0x56E9FB0 = the Dusk score manager with the ranking / cut,
main+0x56EA2B8 = the other kind), step par+0x50, round par+0xB8, the Virtue box of virtue_live.py VIRTUE_PUB
(main+0x492AFF8 own total, +0x492AFFC publish count; 0 0 without the patch).
Per PlayerGameData known to this game (GDM = *(main+0x5B57EB8): +0x08, +0x10, +0x20 = local, +0x28, and the
pool [GDM+0x30] + i*0x47F0, i < 12), player number != -1:
  banked  s16 pgd+0x42C8  Virtue of the finished phases (bank 0xF88360 adds the phase points at each phase end;
                          VIRTUE mirror: the assist writes the owner's live total here on the other games)
  part    pgd+0x46A0 participant flag (ranking skips 0), state u32 pgd+0x46B0, s32 pgd+0x6C (sort key +0x14)
  wp      pgd+0x46D8 win-point object; flags wp+0x10 / wp+0x11 (wp+0x11 != 0: counters count as 0)
  cnt     counters whose value is a plain field (getter 0xF6BEC0: u32 obj+0x68) summed; '?N' = N counters whose
          getter computes the value (not readable without running code)
  net     the two net-synced counter values wp+0x488 / wp+0x568 ({u8, u32}, message 0x58 to the owner)
  cat     the 6-int per-category arrays pgd+0x46F0 / +0x46F8 / +0x4700 (summed by 0xD17D14), when present
Then the applied phase entries (par+0x33D0, 0x60 each, count par+0x3858): player no, rank +0x10, points +0x28
(this phase's counter sum computed by THIS game for that player at the last EndPhase), counter mask +0x30,
category sums +0x48..+0x5C, state bytes +0x40..+0x43; and the result rows R (par+0x3968, 0x190 each, count
par+0x45F0): player no, rank +0x20, Virtue s16 +0x80.
Compare A and B: for player P, banked and the entry points must be equal on every game. Today [I] each game
holds 0 for every player but its own.
Commendation (diag/net/commendation_notes.md), per PlayerGameData:
  comm    fang u32 pgd+0x44C8 (Bloodfang points, enemy kills), coll u32 pgd+0x4458 (Collector points, map
          items); both must be equal on every game for the same player (the assist mirrors them)
  c30000  counter wp+0x248 (Bloodfang, pays PhaseInfo +0x8D / +0x8E for rank 1 / 2), c40000 counter wp+0x2B0
          (Collector, +0x93 / +0x94): number of records, last record (fang rank +0x10, coll rank +0x20,
          u16 +0x28 = final-check byte | 0x100 when ignored by the getter); rank 255 = no award
and per game the commendation manager par+0x2E0: participant list (+0x150 count, +8 entries of 0x28: player no,
rank +0x10 Bloodfang, +0x20 Collector), +0x158 checkpoint, +0x15C final check done, +0x15D / +0x15E Bloodfang /
Collector on, +0x15F off (final), and this round's PhaseInfo award bytes and check times."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

GDM, PAR = 0x5B57EB8, 0x5B3CDF8
VT_DUSK, VT_OTHER = 0x56E9FB0, 0x56EA2B8
GET_FIELD = 0xF6BEC0
BOX = 0x492AFF8
NONE = 0xFFFFFFFF

args = [a for a in sys.argv[1:] if not a.startswith('-')]
verbose = '-v' in sys.argv
games = args[0] if args else 'AB'


def s16(b, o): return struct.unpack_from('<h', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def pgds(m):
    g = m.u64(m.base + GDM)
    if not g:
        return 0, []
    head = m.read(g, 0x38)
    local = u64(head, 0x20)
    cand = [('gdm+%x' % o, u64(head, o)) for o in (0x08, 0x10, 0x20, 0x28)]
    pool = u64(head, 0x30)
    if pool:
        cand += [('pool%d' % i, pool + i * 0x47F0) for i in range(12)]
    out, seen = [], set()
    for tag, p in cand:
        if not p or p in seen:
            continue
        seen.add(p)
        try:
            no = m.u32(p + 0xD0)
        except Exception:
            continue
        if no == NONE:
            continue
        out.append((tag + ('*' if p == local else ''), p, no))
    return local, out


def counters(m, wp):
    known, unknown, rows = 0, 0, []
    ptrs = struct.unpack('<26Q', m.read(wp + 0xC18, 26 * 8))
    for k, obj in enumerate(ptrs):
        if not obj:
            rows.append('%2d -' % k)
            continue
        vt = m.u64(obj)
        get = m.u64(vt + 0x20) - m.base
        if get == GET_FIELD:
            v = m.u32(obj + 0x68)
            known += v
            rows.append('%2d vt %x field %d' % (k, vt - m.base, v))
        else:
            unknown += 1
            rows.append('%2d vt %x getter %x (computed)' % (k, vt - m.base, get))
    return known, unknown, rows


COMM_COUNTERS = ((0x248, 'c30000'), (0x2B0, 'c40000'))


def comm_counter(m, wp, off, tag):
    obj = wp + off
    cid = m.u32(obj + 8)
    beg, end = m.u64(obj + 0x38), m.u64(obj + 0x40)
    n = (end - beg) // 0x38 if beg and end >= beg else 0
    txt = '%s id %d n %d' % (tag, cid, n)
    if n:
        r = m.read(end - 0x38, 0x38)
        txt += ' last fang %d coll %d flag %04x' % (r[0x10], r[0x20], struct.unpack_from('<H', r, 0x28)[0])
    return txt


def comm_manager(m, par):
    cm = m.u64(par + 0x2E0)
    if not cm:
        return ['  commendation manager par+0x2E0 = 0']
    b = m.read(cm, 0x160)
    n = u64(b, 0x150)
    out = ['  commendation par+0x2E0 %x: list %d | checkpoint %d final-done %d fang-on %d coll-on %d off %d' % (
        cm, n, u32(b, 0x158), b[0x15C], b[0x15D], b[0x15E], b[0x15F])]
    for i in range(min(n, 8)):
        e = 8 + i * 0x28
        out.append('    list %d no %d fang rank %d coll rank %d' % (i, i32(b, e), b[e + 0x10], b[e + 0x20]))
    rnd = m.u32(par + 0xB8)
    row = m.u64(par + 0xD0 + (rnd - 1) * 8) if 1 <= rnd <= 9 else 0
    prm = m.u64(row + 0x10) if row else 0
    if prm:
        r = m.read(prm + 0x8C, 0x6C)
        out.append('    round %d award: Bloodfang %d/%d Collector %d/%d | checkpoints %s final check %d s' % (
            rnd, r[1], r[2], r[7], r[8], list(struct.unpack_from('<5h', r, 0x60)), struct.unpack_from('<h', r, 0x6A)[0]))
    return out


def cats(m, p):
    out = []
    for o in (0x46F0, 0x46F8, 0x4700):
        a = m.u64(p + o)
        if a:
            out.append('%x:%s' % (o, list(struct.unpack('<6i', m.read(a, 24)))))
    return ' '.join(out) or '-'


for w in games:
    try:
        m = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)
        continue
    par = m.u64(m.base + PAR)
    box = m.read(m.base + BOX, 8)
    hdr = '%s box total %d count %d' % (w, u32(box, 0), u32(box, 4))
    if par:
        sm = m.u64(par + 0x148)
        kind = '-'
        if sm:
            vt = m.u64(sm) - m.base
            kind = 'dusk' if vt == VT_DUSK else ('other' if vt == VT_OTHER else 'vt %x' % vt)
        hdr += ' | step %d round %d score manager %s' % (m.u32(par + 0x50), m.u32(par + 0xB8), kind)
    else:
        hdr += ' | no stage (par = 0)'
    print(hdr)
    local, ps = pgds(m)
    for tag, p, no in ps:
        b = m.read(p + 0x42C8, 0x420)          # 0x42C8 .. 0x46E8
        banked = s16(b, 0)
        part, state, b2 = b[0x46A0 - 0x42C8], u32(b, 0x46B0 - 0x42C8), b[0x46B2 - 0x42C8]
        wp = u64(b, 0x46D8 - 0x42C8)
        line = '  %-8s no %d banked %d part %d state %08x/%d +6c %d' % (tag, no, banked, part, state, b2, m.u32(p + 0x6C))
        if wp:
            f = m.read(wp + 0x10, 2)
            known, unknown, rows = counters(m, wp)
            net = (m.read(wp + 0x488, 8).hex(), m.read(wp + 0x568, 8).hex())
            line += ' | wp flags %d/%d cnt %d ?%d net %s %s | live >= %d' % (f[0], f[1], known, unknown, net[0], net[1],
                                                                            banked + (0 if f[1] else known))
        else:
            line += ' | no wp'
            rows = []
        print(line)
        print('           cat %s' % cats(m, p))
        comm = '           comm fang %d coll %d' % (m.u32(p + 0x44C8), m.u32(p + 0x4458))
        if wp:
            comm += ' | ' + ' | '.join(comm_counter(m, wp, o, t) for o, t in COMM_COUNTERS)
        print(comm)
        if verbose:
            for r in rows:
                print('           ' + r)
    if not par:
        continue
    for t in comm_manager(m, par):
        print(t)
    n = m.u32(par + 0x3858)
    for i in range(min(n, 12)):
        e = m.read(par + 0x33D0 + 0x60 * i, 0x60)
        print('  entry %d no %d rank %d pts %d mask %x cat %s state %s' % (
            i, i32(e, 0), u32(e, 0x10), u32(e, 0x28), u64(e, 0x30),
            list(struct.unpack_from('<6i', e, 0x48)), e[0x40:0x44].hex()))
    rn = m.u32(par + 0x45F0)
    for i in range(min(rn, 8)):
        r = m.read(par + 0x3968 + 0x190 * i, 0x90)
        print('  row %d no %d rank %d virtue %d' % (i, i32(r, 0), u32(r, 0x20), s16(r, 0x80)))
