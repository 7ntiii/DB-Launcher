"""Final HP bonus from Virtue, Virtue, rank and the post-match reward list, as each twin game holds them.
READ-ONLY (only Mem.read). Static basis and [V]/[I] marks: diag/net/endgame_notes.md.
python diag/twin/endgame.py [GAMES=AB] [-v]      (-v: also the counter objects per player)

Per game:
  stage    par = *(main+0x5B3CDF8): step +0x50, round +0xB8; final coordinator par+0x3388 (vtable main+0x56F5F70 =
           point-select, the only kind the stock data builds); current env event = last id of the list
           [*(main+0x5B57EB8)+0x68]+0x58..+0x60 (2000/2002/2030 = type 0x10, the bonus needs it); rule byte
           main+0x5B65C70 (2 = Duo: the bonus uses the team Virtue and graph 761, not computed here)
Per PlayerGameData (same list as virtue.py: GDM +0x08/+0x10/+0x20 = local '*'/+0x28 and the pool):
  hp       pgd+0x08 HP, +0x0C max HP, +0x10 base max HP [I: order {HP, max, base} from 0xDE2004/0xDE2028, base
           offset I]; extra = max - base (all bonuses: SpEffect rates/flat, Virtue, 0xF61B4C)
  stock    pgd+0x42A4 spare lives (phase 19 sets 1 = EnvEventTypeParam row 0 +0xB; the bonus needs stock == 1)
  virtue   s16 pgd+0x42C8 + plain-field counters (wp = pgd+0x46D8, counters wp+0xC18, 25 used by 0xD17780;
           wp+0x11 != 0: counters count as 0); '?N' = N counters with a computed getter (value unknown here)
  bonus    expected Graph(760, virtue) when the conditions hold: steps 0 / +180 (>0) / +250 (>80) / +300 (>100) /
           +320 (>120, max at 150) [V data; I: 0x4927860 = powf, exponent -99 makes each segment a step]
Rank: result rows par+0x3968 (0x190 each, count par+0x45F0): player no, rank +0x20, Virtue s16 +0x80; and the
phase entries par+0x33D0 (0x60, count par+0x3858): rank +0x10, state +0x40..+0x43 (a reward is recorded for an
entry at state 4 with kind +0x41 = 4..7).
Rewards: lobby-reward object L = par+0x4B48 (0x88 bytes): vector L+0x20..L+0x28 of 12-byte records
{u32 player key [I: player no], u32 item id | category << 28, u16 count}. Empty in LAN without REWARD_LOCAL, and
empty with REWARD_LOCAL too while no LobbyRewardParam lot is set (stock regulation). par+0x4708 != 0: the
match result (and its reward list, granted to the local inventory by 0x1048040) was applied."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

GDM, PAR, RULE = 0x5B57EB8, 0x5B3CDF8, 0x5B65C70
VT_POINT, VT_RANDOM = 0x56F5F70, 0x56F5D68
GET_FIELD = 0xF6BEC0
FINAL_ENVS = (2000, 2002, 2030)
GRAPH_760 = ((0.0, 80.0, 100.0, 120.0, 150.0), (0.0, 180.0, 250.0, 300.0, 320.0), -99.0)
NONE = 0xFFFFFFFF

args = [a for a in sys.argv[1:] if not a.startswith('-')]
verbose = '-v' in sys.argv
games = args[0] if args else 'AB'


def s16(b, o): return struct.unpack_from('<h', b, o)[0]
def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def graph(x, g=GRAPH_760):
    """0xF58358 for one CalcCorrectGraph row (all four exponents negative here)."""
    xs, ys, adj = g
    if x <= xs[0]:
        return ys[0]
    if x >= xs[4]:
        return ys[4]
    i = max(k for k in range(4) if xs[k] < x or k == 0)
    t = (xs[i + 1] - x) / (xs[i + 1] - xs[i])
    return ys[i] + (1.0 - t ** -adj) * (ys[i + 1] - ys[i])


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


def virtue(m, p):
    banked = s16(m.read(p + 0x42C8, 2), 0)
    wp = m.u64(p + 0x46D8)
    if not wp:
        return banked, 0, 'no wp', []
    flags = m.read(wp + 0x10, 2)
    known, unknown, rows = 0, 0, []
    for k, obj in enumerate(struct.unpack('<25Q', m.read(wp + 0xC18, 25 * 8))):
        if not obj:
            continue
        vt = m.u64(obj)
        get = m.u64(vt + 0x20) - m.base
        if get == GET_FIELD:
            v = m.u32(obj + 0x68)
            known += v
            rows.append('%2d field %d' % (k, v))
        else:
            unknown += 1
            rows.append('%2d computed (getter %x)' % (k, get))
    total = banked + (0 if flags[1] else known)
    return total, unknown, 'wp flags %d/%d' % (flags[0], flags[1]), rows


def env_now(m):
    g = m.u64(m.base + GDM)
    lst = m.u64(g + 0x68) if g else 0
    if not lst:
        return None
    beg, end = m.u64(lst + 0x58), m.u64(lst + 0x60)
    if not beg or end <= beg:
        return None
    return i32(m.read(end - 4, 4), 0)


for w in games:
    try:
        m = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)
        continue
    par = m.u64(m.base + PAR)
    rule = m.read(m.base + RULE, 1)[0]
    env = env_now(m)
    coord, kind = 0, '-'
    if par:
        coord = m.u64(par + 0x3388)
        if coord:
            vt = m.u64(coord) - m.base
            kind = 'point-select' if vt == VT_POINT else ('all-random' if vt == VT_RANDOM else 'vt %x' % vt)
        print('%s step %d round %d | coordinator %s | env %s%s | rule %d | result applied %s' % (
            w, m.u32(par + 0x50), m.u32(par + 0xB8), kind, env, ' (final type 0x10)' if env in FINAL_ENVS else '',
            rule, 'yes' if m.u64(par + 0x4708) else 'no'))
    else:
        print('%s no stage (par = 0) | env %s | rule %d' % (w, env, rule))
    cond = bool(coord) and env in FINAL_ENVS
    local, ps = pgds(m)
    for tag, p, no in ps:
        hp = m.read(p + 8, 12)
        cur, mx, base = i32(hp, 0), i32(hp, 4), i32(hp, 8)
        stock = m.read(p + 0x42A4, 1)[0]
        tot, unk, fl, rows = virtue(m, p)
        if rule == 2:
            exp = 'Duo: team Virtue, graph 761 (not computed)'
        elif cond and stock == 1:
            exp = '+%d%s' % (round(graph(tot)), ' (or more: %d computed counters)' % unk if unk else '')
        else:
            exp = '0 (%s)' % ('stock %d != 1' % stock if cond else 'not in the point-select final')
        print('  %-8s no %d | HP %d / max %d / base %d (extra %+d) | stock %d | Virtue %d%s %s | bonus %s' % (
            tag, no, cur, mx, base, mx - base, stock, tot, ' ?%d' % unk if unk else '', fl, exp))
        if verbose:
            for r in rows:
                print('           ' + r)
    if not par:
        continue
    rn = m.u32(par + 0x45F0)
    for i in range(min(rn, 8)):
        r = m.read(par + 0x3968 + 0x190 * i, 0x90)
        print('  row %d no %d rank %d Virtue %d' % (i, i32(r, 0), u32(r, 0x20), s16(r, 0x80)))
    n = m.u32(par + 0x3858)
    for i in range(min(n, 12)):
        e = m.read(par + 0x33D0 + 0x60 * i, 0x60)
        st = e[0x40:0x44]
        print('  entry %d no %d rank %d state %s%s' % (i, i32(e, 0), u32(e, 0x10), st.hex(),
                                                     ' (reward case)' if st[0] == 4 and 4 <= st[1] <= 7 else ''))
    lr = m.u64(par + 0x4B48)
    if not lr:
        print('  rewards: no lobby-reward object (par+0x4B48 = 0)')
        continue
    beg, end = m.u64(lr + 0x20), m.u64(lr + 0x28)
    cnt = (end - beg) // 12 if beg and end >= beg else 0
    print('  rewards: object %x, %d record(s)%s' % (lr, cnt, '' if cnt else ' (empty: nothing granted)'))
    if cnt:
        b = m.read(beg, 12 * min(cnt, 64))
        for i in range(min(cnt, 64)):
            key, item, count = u32(b, 12 * i), u32(b, 12 * i + 4), u16(b, 12 * i + 8)
            print('    key %d item %d (category %d) x%d' % (key, item & 0xFFFFFFF, item >> 28, count))
