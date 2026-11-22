"""Kill credit on every twin game. READ-ONLY (only Mem.read). Notes: diag/net/credit_notes.md.
python diag/twin/credit.py [GAMES=AB] [N=3] [watch SECONDS]

Per game: mode (mgr3+0x1268, 6 in LAN), role word main+0x492AFD8 (0 = host), whether credit_live.py KILL_OWNER
is in (word 0x175242C), then every player chr this game knows (WCM+0x30 entries): handle chrdata+0x78, player
no pgd+0xD0 (pgd = chrdata+0x1D0), copy flag wp+0x11 (wp = pgd+0x46D8), and the counters
  fang  u32 pgd+0x44C8  Bloodfang (enemy kills)        coll  u32 pgd+0x4458  Collector (map items)
  exp   u32 pgd+0x90    EXP [L handoff 1]              lvl   u32 pgd+0x64  (moved 0 -> 1 with a kill [L])
  rep   counter id 140000 (Repulsion Virtue, kill) among wp+0xC18 (26 ptrs, id u32 obj+8): value obj+0x68 when the
        getter is the plain field 0xF6BEC0, else '?'; records n = (obj+0x40 - obj+0x38) / 0x38 [I stride]
Then the N enemies (vtable main+0x572B108, from the sync sets WCM+0x540) nearest to the FIRST game's player,
matched on every game by handle chr+8 (same on all games for map enemies [L]):
  hp / max  [[chr+0x2470]+0x18]+0x290 / +0x294       own   owner[] of the sync set (>= 0: this game drives it)
  last      chrdata+0x114 (last attacker handle, low 16 bits) -> the player it names on THIS game
  lastno    chrdata+0x11C (player no of the last attacker, set with +0x114 by 0xE8E4DC)
  st        u64 chr+0x12BC bits: L = 52 (credited hit by a local / locally controlled attacker),
            D = 53 (dying), H = 54 (death handled: credit given on this game), and u32 chr+0x12C5 bits:
            A = 16 (killer decided: decider / 0x3C answer), h = 25 (a hit went through the damage path)
Two players hitting one enemy: after the death every game must show the same 'last' player, H on every game that
loaded it, and only that player's fang / exp / rep must grow, on its own game only (copies stay).
  fg        friendly-group slots of the enemy (row 50, drain -> ally; summon_struggle_notes.md section 3):
            FG = [[chr+0x2470]+0x280]; slot g = u64 FG+0x18+8*g (g = player SLOT 0..11, pgd+0x104); joined when
            u8 slot+0x1C == 1 [V reader 0xE4EA60 kind 2; slot layout from the notes' "live check" line, I].
            '-' = in no group. Player lines show 'slot' (pgd+0x104) to map a group to a player.
Drain check: before the drain every game prints fg - for the enemy; after it every game that loaded the enemy
prints fg = the drainer's slot."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

WCM_VAR, MGR3_VAR, ROLE = 0x5B3CD88, 0x5B3CE08, 0x492AFD8
ENEMY_VT = 0x572B108
GET_FIELD = 0xF6BEC0
KILL_OWNER_WORD = 0x175242C          # orig tbnz x9,#0x34 (0xB7A00129 family); patched: b 0x6B32200
REP_ID = 140000

args = [a for a in sys.argv[1:]]
watch = 0.0
if 'watch' in args:
    i = args.index('watch')
    watch = float(args[i + 1]) if i + 1 < len(args) else 30.0
    del args[i:i + 2]
games = args[0] if args else 'AB'
nearest_n = int(args[1]) if len(args) > 1 else 3


def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def f3(m, a):
    return struct.unpack('<3f', m.read(a, 12))


def players(m):
    """[(chr, handle, pgd, no)] of WCM+0x30 entries (entry 0 = this game's player)."""
    wcm = m.u64(m.base + WCM_VAR)
    arr = m.u64(wcm + 0x30) if wcm else 0
    out = []
    if not arr:
        return out
    raw = m.read(arr, 0x38 * 8)
    for i in range(8):
        chr_ = u64(raw, 0x38 * i)
        if not chr_:
            continue
        try:
            data = m.u64(chr_ + 0x20)
            handle = m.u32(data + 0x78) & 0xFFFF if data else 0xFFFF
            pgd = m.u64(data + 0x1D0) if data else 0
            no = m.u32(pgd + 0xD0) if pgd else 0xFFFFFFFF
            phys = u64(raw, 0x38 * i + 0x28)
            out.append({'i': i, 'chr': chr_, 'handle': handle, 'pgd': pgd, 'no': no, 'phys': phys})
        except Exception:
            continue
    return out


def rep_counter(m, wp):
    ptrs = struct.unpack('<26Q', m.read(wp + 0xC18, 26 * 8))
    for obj in ptrs:
        if not obj:
            continue
        try:
            if m.u32(obj + 8) != REP_ID:
                continue
            get = m.u64(m.u64(obj) + 0x20) - m.base
            val = str(m.u32(obj + 0x68)) if get == GET_FIELD else '?(getter %x)' % get
            beg, end = m.u64(obj + 0x38), m.u64(obj + 0x40)
            n = (end - beg) // 0x38 if beg and end >= beg else 0
            return 'rep %s n %d' % (val, n)
        except Exception:
            continue
    return 'rep -(no counter id 140000 at +8)'


def player_line(m, p):
    pgd = p['pgd']
    if not pgd:
        return '    P%d handle %04x (no pgd)' % (p['i'], p['handle'])
    wp = m.u64(pgd + 0x46D8)
    copy = m.read(wp + 0x10, 2)[1] if wp else -1
    try:
        slot = m.read(pgd + 0x104, 1)[0]
    except Exception:
        slot = -1
    txt = '    P%d no %d slot %d handle %04x copy %d | fang %d coll %d exp %d lvl %d' % (
        p['i'], p['no'], slot, p['handle'], copy, m.u32(pgd + 0x44C8), m.u32(pgd + 0x4458), m.u32(pgd + 0x90),
        m.u32(pgd + 0x64))
    if wp:
        txt += ' | ' + rep_counter(m, wp)
    return txt


def enemies(m):
    """{handle: (chr, owner_flag_addr)} from the chr sync sets."""
    wcm = m.u64(m.base + WCM_VAR)
    sm = m.u64(wcm + 0x540) if wcm else 0
    out = {}
    if not sm:
        return out
    for i in range(min(m.u32(sm + 8), 16)):
        s = m.u64(sm + 0x10 + 8 * i)
        if not s:
            continue
        n = m.u32(s + 0x10)
        chrset = m.u64(s + 8)
        own = m.u64(s + 0x18)
        if not n or n > 4096 or not chrset or not own:
            continue
        first = m.u64(chrset + 8)
        raw = b''.join(m.read(first + o, min(0x2000, 0x38 * n - o)) for o in range(0, 0x38 * n, 0x2000))
        for j in range(n):
            c = u64(raw, 0x38 * j)
            if c and m.u64(c) == m.base + ENEMY_VT:
                out[m.u32(c + 8)] = (c, own + 2 * j, u64(raw, 0x38 * j + 0x28))
    return out


def enemy_line(m, w, c, ownaddr, names):
    try:
        mod = m.u64(m.u64(c + 0x2470) + 0x18)
        hp, mx = struct.unpack('<2i', m.read(mod + 0x290, 8)) if mod else (0, 0)
        own = struct.unpack('<h', m.read(ownaddr, 2))[0]
        data = m.u64(c + 0x20)
        last = m.u32(data + 0x114)
        lastno = m.u32(data + 0x11C)
        st64 = struct.unpack('<Q', m.read(c + 0x12BC, 8))[0]
        st32 = m.u32(c + 0x12C5)
    except Exception as e:
        return '    %s: unreadable (%s)' % (w, e)
    st = ''.join(ch for ch, on in (('L', st64 >> 52 & 1), ('D', st64 >> 53 & 1), ('H', st64 >> 54 & 1),
                                   ('A', st32 >> 16 & 1), ('h', st32 >> 25 & 1)) if on) or '-'
    who = names.get(last & 0xFFFF, 'not a player')
    return '    %s: hp %d/%d own %d last %08x (%s) lastno %d st %s fg %s' % (
        w, hp, mx, own, last, who, lastno if lastno != 0xFFFFFFFF else -1, st, friendly_groups(m, c))


def friendly_groups(m, c):
    """Player slots whose friendly group holds this chr (READ ONLY; see the docstring 'fg')."""
    try:
        fg = m.u64(m.u64(c + 0x2470) + 0x280)
        if not fg:
            return '?(no module)'
        ptrs = struct.unpack('<12Q', m.read(fg + 0x18, 12 * 8))
        on = []
        for g, s in enumerate(ptrs):
            if s and m.read(s + 0x1C, 1)[0] == 1:
                on.append(str(g))
        return ','.join(on) or '-'
    except Exception as e:
        return '?(%s)' % type(e).__name__


def once(G):
    snap = {}
    for w, m in G.items():
        mgr3 = m.u64(m.base + MGR3_VAR)
        mode = m.u32(mgr3 + 0x1268) if mgr3 else -1
        role = m.u32(m.base + ROLE)
        hook = m.u32(m.base + KILL_OWNER_WORD)
        patched = (hook & 0xFC000000) == 0x14000000
        ps = players(m)
        print('%s mode %d role %d KILL_OWNER %s (word %08x)' % (w, mode, role, 'in' if patched else 'not in', hook))
        for p in ps:
            print(player_line(m, p))
        names = {p['handle']: 'P%d no %d' % (p['i'], p['no']) for p in ps}
        snap[w] = (ps, names, enemies(m))
    first = next(iter(G))
    ps0, _, en0 = snap[first]
    if not ps0 or not ps0[0]['phys']:
        print('no player on %s' % first)
        return
    me = f3(G[first], ps0[0]['phys'] + 0x70)
    near = []
    for h, (c, ownaddr, phys) in en0.items():
        try:
            near.append((math.dist(me, f3(G[first], phys + 0x70)), h))
        except Exception:
            pass
    near.sort()
    for d, h in near[:nearest_n]:
        print('  enemy %08x  %.1f m from %s player' % (h, d, first))
        for w, m in G.items():
            _, names, en = snap[w]
            if h not in en:
                print('    %s: not loaded' % w)
                continue
            c, ownaddr, _ = en[h]
            print(enemy_line(m, w, c, ownaddr, names))


G = {}
for w in games:
    try:
        G[w] = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)
if watch:
    t0 = time.time()
    while time.time() - t0 < watch:
        print('--- t+%.0f s' % (time.time() - t0))
        once(G)
        time.sleep(1.0)
else:
    once(G)
