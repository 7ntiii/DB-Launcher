"""zeppelin.py GAMES [watch SECONDS]  -- READ-ONLY state of the zeppelin support event (1120, env type 0x0A).

Usage (from the workspace root):  python diag/twin/zeppelin.py AB
                                  python diag/twin/zeppelin.py AB watch 10   (every 0.2 s, print only changes)
                                  python diag/twin/zeppelin.py AB scan       (also heap-search enemy chrs, slow)
Only Mem.read (and the read-only search_memory) is used; nothing is written. Offsets: zeppelin2_notes.md,
corrections in zeppelin4_notes.md.
Per game: HOST byte / offline flag / mode, the patch sites of zeppelin2_notes (orig / new / other), event flags
9580 / 9581, the support object AS = *(par+0x2C0) (heap object 0x160 bytes, ctor 0xF0B8E0; NOT par+0x2C0 itself,
fixed 2026-11-15 [V 0x114F614, 0x114E598, 0x114FD10, 0x1149C34]), its airships / request queue / strikes, the
airship chrs (u16 id, airship type bit, or near the two MSB positions) and the Transmitter (goods 4120) count of
every player chr's pgd plus the item-use records of each effect slot.
+0xB / +0xC: set by PrepareSecond (0xF0DB68 / 0xF0DC2C), CLEARED again by PrepareThird (0x114FC8C sturh wzr)
before the airship scan, so during a running phase both read 0 [V]. Type +8 = 0x0A from step 17 (0x114E5B4).
"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

PAR_G, NET_G, GAMEDATA_G, WCM_G = 0x5B3CDF8, 0x5B3CE08, 0x5B65C20, 0x5B3CD88
PGD_G, ITEMMGR_G, FLAGMAN_G = 0x5B57EB8, 0x5B57E90, 0x5B44EB8
HOST_BYTE = 0x492AFD8
TRANSMITTER = 4120
FLAGS = (9580, 9581)

# (main offset, original word, proposed word, name) from zeppelin2_notes.md section 3/4 (words as u32)
SITES = [
    (0xF0DB88, 0x34000548, 0xD503201F, 'S1 grant gate'),
    (0xF107F8, 0x540007C1, 0x340007C8, 'S3 sender host/guest'),
    (0xF11EEC, 0x34001F08, 0x35001F08, 'S4 store host only'),
    (0xF1117C, 0x340005E8, 0x350005E8, 'S5 decide host only'),
    (0xF11EA0, 0x54002161, 0x34002168, 'S6 kind 1 guests only'),
    (0xF11258, 0xB4000DF9, 0x14000048, 'S7 skip goods check (opt)'),
    (0xF0C52C, 0x940015FD, None, 'C1 hook (bl 0xF11D20)'),
    (0xCF8F74, 0x34000388, None, 'C2 hook (bda gate of 0xCF8E2C)'),
    (0xF108DC, 0xF9402508, 0xF9402108, 'ZEP4_SEND 0x9E broadcast'),
    (0xF0C884, 0x54000060, 0x540003E0, 'ZEP4_NOPH'),
    (0xF10BEC, 0xF9402508, 0xF9402108, 'ZEP4_END_A0 broadcast'),
    (0xF10F34, 0xF9402508, 0xF9402108, 'ZEP4_END_A1 broadcast'),
    # zep5_live.py (zeppelin5_notes.md): ZEP5_END = the two ZEP4_END words above
    (0xF114D0, 0x390053E9, 0x390053FF, 'ZEP5_READY_D decision: new strike ready'),
    (0xF120A8, 0x381943AC, 0x381943BF, 'ZEP5_READY_K guest kind 1: new strike ready'),
    (0xF0CD84, 0xB4000555, 0x151CC897, 'ZEP5_FIREANY hook (b 0x563EFE0)'),
    (0xC50183C, 0x00000000, 0xFFFFFFFF, 'ZEP5_FIREANY_LIT cave literal -1'),
    (0xF11410, 0x140000A2, 0x151CB6F7, 'ZEP5_ONCE hook (b 0x563EFEC): one use = one ship'),
]
ATTR_GOT = 0x59E41D0   # GOT -> attribute table (8 bytes per type, byte +4 routing) [V 0x1CD7CA4..0x1CD7CC4]
ROUTE_9E = 0x4C4B8A0  # ro byte: 0x40 orig, 0x20 proposed (S2)
EFFECT_SYNC = 0x59E1B28            # [[main+0x59E1B28]] = item/effect manager (dusk_lan.cpp ConfirmEffects) [V]
TRANSMITTER_WORD = 0x30000000 | TRANSMITTER
ENEMY_VT = 0x572B108               # EnemyIns vtable (npcs.py)
# MSB m10_00_00_00 enemy parts c1510_0000 / c1510_0001 (entity 1000260 / 1000261) [V msb.parts.txt]
AIRSHIP_MSB = ((1000260, (251.3, 160.1, 648.6)), (1000261, (114.9, 149.1, -131.8)))


class R:
    """null-safe reads"""
    def __init__(self, who):
        self.m = Mem(who)
        self.base = self.m.base

    def rd(self, a, n):
        if not a or a < 0x10000 or a > 0xFFFFFFFFFFFF:
            return None
        try:
            b = self.m.read(a, n)
            return b if b and len(b) == n else None
        except Exception:
            return None

    def _u(self, a, f, n):
        b = self.rd(a, n)
        return struct.unpack(f, b)[0] if b else None

    def q(self, a): return self._u(a, '<Q', 8)
    def d(self, a): return self._u(a, '<I', 4)
    def i(self, a): return self._u(a, '<i', 4)
    def h(self, a): return self._u(a, '<H', 2)
    def b(self, a): return self._u(a, '<B', 1)
    def f(self, a): return self._u(a, '<f', 4)

    def f3(self, a):
        b = self.rd(a, 12)
        return struct.unpack('<3f', b) if b else None

    def g(self, off): return self.q(self.base + off)


def p3(v):
    return '?' if v is None else '(%.2f, %.2f, %.2f)' % v


def vec(r, a, size, limit=16):
    b0, b1 = r.q(a), r.q(a + 8)
    if b0 is None or b1 is None:
        return None, []
    if not b0 or b1 < b0 or (b1 - b0) % size or (b1 - b0) // size > 256:
        return (0 if b0 == b1 else None), []
    n = (b1 - b0) // size
    return n, [b0 + k * size for k in range(min(n, limit))]


def event_flag(r, fid):
    """same walk as promptcheck.event_flag (0xC1BF60 + 0x1B5ADA0), ids < 100,000,000, area < 10"""
    mgr = r.g(FLAGMAN_G)
    if not mgr or not r.b(mgr + 0x228):
        return None
    area = (fid // 10000) % 100
    tbl = r.q(mgr + 0x218)
    ent = r.q(tbl) if tbl else None
    if not ent or area >= 10:
        return None
    blk = ent + area * 0xA8 + ((fid // 1000) % 10) * 0x10
    bits = r.q(blk)
    rem = fid % 1000
    wd = r.d(bits + (rem >> 5) * 4) if bits else None
    return None if wd is None else bool((wd >> (31 - (rem & 31))) & 1)


def goods_count(r, pgd, gid):
    """inventory pgd+0x2E8 (layout as rewards.py, 0xCCD4A0): sum of counts whose id word matches goods gid"""
    if not pgd:
        return None
    inv = pgd + 0x2E8
    n1, total = r.d(inv + 0x2FC), r.d(inv + 0x368)
    a1, a2 = r.q(inv + 0x330), r.q(inv + 0x320)
    if n1 is None or total is None or total + 1 > 4096:
        return None
    cnt = 0
    for k in range(total + 1):
        e = (a1 + k * 16) if k < n1 else (a2 + (k - n1) * 16 if a2 else None)
        raw = r.rd(e, 16) if e else None
        if not raw:
            continue
        w0, w1, c = struct.unpack_from('<III', raw, 0)
        if w0 and ((w0 & 0x0FFFFFFF) == gid or (w1 & 0x0FFFFFFF) == gid):  # which word is the id: [I]
            cnt += c
    return cnt


def chr_id16(r, c):
    data = r.q(c + 0x20)
    v = r.d(data + 0x78) if data else None
    return None if v is None else v & 0xFFFF


def chr_pos(r, c):
    m = r.q(c + 0x2470)
    ph = r.q(m + 0xE8) if m else None
    return r.f3(ph + 0x70) if ph else None


def all_chrs(r):
    """WCM+0x10 count, *(WCM+0x18) sets of 0x270 bytes: +0x78 count, +0x80 entries of 0x38 (+0 chr) [V 0x178C164]"""
    w = r.g(WCM_G)
    n, arr = (r.d(w + 0x10), r.q(w + 0x18)) if w else (None, None)
    out = []
    if not arr or not n or n > 256:
        return out
    for k in range(n):
        s = arr + k * 0x270
        cn, ca = r.d(s + 0x78), r.q(s + 0x80)
        if not ca or not cn or cn > 8192:
            continue
        raw = r.rd(ca, 0x38 * cn)
        if not raw:
            continue
        for j in range(cn):
            c = struct.unpack_from('<Q', raw, 0x38 * j)[0]
            if c:
                out.append(c)
    return out


def chr_by_id(r, i16):
    """the game's own id lookup 0x17E7828 (normal path): blk = [WCM + (id >> 12) * 8 + 0x4A0], u32 [blk] > (id & 0xFFF)
    -> chr = [[blk+8] + (id & 0xFFF) * 0x38] [V 0x17E78A4..0x17E78D0]. The special block ([[WCM+8]+8]+2) is not
    handled -> None."""
    w = r.g(WCM_G)
    if not w or i16 is None or i16 == 0xFFFF:
        return None
    hi, lo = i16 >> 12, i16 & 0xFFF
    blk = r.q(w + hi * 8 + 0x4A0)
    if not blk or (r.d(blk) or 0) <= lo:
        return None
    arr = r.q(blk + 8)
    return r.q(arr + lo * 0x38) if arr else None


def is_airship_type(r, c):
    """[[chr+0x20]+0xE8]+8 -> byte +0x39D bit 3 (the PrepareThird filter 0xF16240) [V]"""
    data = r.q(c + 0x20)
    x = r.q(data + 0xE8) if data else None
    y = r.q(x + 8) if x else None
    v = r.b(y + 0x39D) if y else None
    return None if v is None else bool(v & 8)


def players(r):
    """(chr, player no, pgd) of WCM+0x30 entries; pgd = [[chr+0x20]+0x1D0] (also the copies of remote players)"""
    w = r.g(WCM_G)
    arr = r.q(w + 0x30) if w else None
    out = []
    for k in range(8):
        c = r.q(arr + 0x38 * k) if arr else None
        if not c:
            break
        data = r.q(c + 0x20)
        pgd = r.q(data + 0x1D0) if data else None
        out.append((c, r.d(pgd + 0xD0) if pgd else None, pgd))
    return out


def use_records(r):
    """item-use records per effect slot (slot = mgr+8+k*0x290, player no at +0; record deque +0x50 map, +0x58 end,
    +0x70 first, +0x78 count; records 0x28 bytes, 102 per block; +0x10 item word, +0x18 state) [V dusk_lan.cpp].
    Returns {player no: (records, transmitter records, [states of the transmitter records])}"""
    h = r.g(EFFECT_SYNC)
    mgr = r.q(h) if h else None
    out = {}
    if not mgr:
        return out
    for k in range(13):
        s = mgr + 8 + k * 0x290
        no = r.i(s)
        if no is None or no == -1:
            continue
        mp, me, first, cnt = r.q(s + 0x50), r.q(s + 0x58), r.q(s + 0x70), r.q(s + 0x78)
        tx, st = 0, []
        if mp and me and me > mp and cnt is not None and cnt <= 4096:
            for i in range(cnt):
                idx = first + i
                bs = mp + idx // 102 * 8
                blk = r.q(bs) if bs < me else None
                if not blk:
                    break
                rec = blk + idx % 102 * 0x28
                if r.d(rec + 0x10) == TRANSMITTER_WORD:
                    tx += 1
                    st.append(r.i(rec + 0x18))
        out[no] = (cnt, tx, st)
    return out


def owner_flag(r, c):
    """assist ownership flag of an enemy chr: WCM+0x540 sync mgr, sets at +0x10 (count +8), set +8 chr set
    (+8 entries of 0x38), +0x10 count, +0x18 s16 per entry: >= 0 this game drives it, -1 remote [V dusk_lan.cpp
    EnemyOwners 1279..1312, 1462]. Returns (flag, set, index) or None."""
    w = r.g(WCM_G)
    sync = r.q(w + 0x540) if w else None
    n = r.d(sync + 8) if sync else None
    if not n or n > 16:
        return None
    for i in range(n):
        s = r.q(sync + 0x10 + 8 * i)
        cs = r.q(s + 8) if s else None
        cnt = r.d(s + 0x10) if s else None
        own = r.q(s + 0x18) if s else None
        first = r.q(cs + 8) if cs else None
        if not first or not cnt or cnt > 8192 or not own:
            continue
        raw = r.rd(first, 0x38 * cnt)
        if not raw:
            continue
        for j in range(cnt):
            if struct.unpack_from('<Q', raw, 0x38 * j)[0] == c:
                v = r.rd(own + 2 * j, 2)
                return (struct.unpack('<h', v)[0] if v else None), i, j
    return None


def ai_state(r, c):
    """airship AI = [[chr+0x2480]+0x160] (chr vt+0x228 = 0x1784C04 `ldr x0,[x0,#0x2480]`) [V]; the fire order
    0xF0CDF0..0xF0CE28 writes +0x74C5 = 1, +0x8950 target point, +0x8A28 requester handle, then 0xB0FBA0.
    +0x74C5 is cleared by the 0xA0 attack report (grantgate 4) [V]."""
    comp = r.q(c + 0x2480)
    ai = r.q(comp + 0x160) if comp else None
    if not ai:
        return None
    return r.b(ai + 0x74C5), r.f3(ai + 0x8950), r.d(ai + 0x8A28)


RADIUS_G = 0x59DFFF8   # GOT -> global -> obj; +0x20D0 n / +0x20D8 file; row 0 +0x58 f32 = radius [V 0x155A140]
ENVP_G = 0x5B3CE68     # obj; +0x36C0 n / +0x36C8 file; row 0 +0x140 == -1 -> every ship [V 0x155AC00]


def param_row0(r, obj, n_off, f_off):
    """row 0 of a param file as 0x155A140 / 0x155AC00 do it (same code as use_item.param_row0) [V]"""
    if not obj or not r.d(obj + n_off):
        return None
    f = r.q(obj + f_off)
    x8 = r.q(r.q(f + 0x70) + 0x78) if f and r.q(f + 0x70) else None
    if not x8:
        return None
    n, so = r.i(x8 - 0xC), r.i(x8 - 0x10)
    if n is None or so is None or n < 1:
        return None
    x10 = x8 + ((so + 0xF) & ~0xF)
    w9, idx = n, None
    while True:
        w11 = w9 - 1
        w9 = w11 >> 1
        if r.d(x10 + w9 * 8) == 0:
            idx = r.d(x10 + w9 * 8 + 4)
            break
        if w11 < 2:
            return None
    if idx is None or idx & 0x80000000:
        return None
    t = r.b(x8 + 0x2D) or 0
    wide = bool((r.b(x8 + 0x2E) or 0) & 2)
    k = t & 0x7F
    if k == 2:
        off = r.d(x8 + 12 * idx + 0x34)
    elif k == 3 or (k == 4 and not wide) or (k == 5 and not (t & 0x80 and wide)):
        off = r.d(x8 + 12 * idx + 0x44)
    elif k in (4, 5):
        off = r.q(x8 + 24 * idx + 0x48)
    else:
        return None
    return None if off is None else x8 + off


def candidates_now(r, a, pl, detail):
    """zeppelin6_notes 2: the request side 0xF102C0 builds the candidate list ON THE REQUESTER'S GAME: env row 0
    +0x140 == -1 -> every ship; else for each AS ship: chr by the game's own id lookup 0x17E7828 (0xF10684; not
    found -> skipped), 3D |ship - requester|^2 < R^2 (0xF106F0), then a ray test (0x15F1594, NOT checked here).
    The host decision 0xF11140 repeats the lookup (0xF11768) and the range with ITS ship positions and the sent
    point. Returns lines: per ship (lookup / copy state / pos / distance per player) when detail, and one summary
    line 'candidates now (range only)' per player chr of this game (compact, so watch prints it on change)."""
    row = param_row0(r, r.q(r.g(RADIUS_G) or 0), 0x20D0, 0x20D8)
    rad = r.f(row + 0x58) if row else None
    env = param_row0(r, r.g(ENVP_G), 0x36C0, 0x36C8)
    allships = (r.i(env + 0x140) if env else None) == -1
    _, ents = vec(r, a + 0xF0, 0x40)
    ppos = [(no, chr_pos(r, c)) for c, no, _pgd in pl]
    cand = {no: [] for no, _ in ppos}
    out = []
    for x in ents:
        sid = r.h(x)
        ch = chr_by_id(r, sid)
        p = chr_pos(r, ch) if ch else None
        ent = r.q(ch + 0x18) if ch else None
        cs = r.d(ent + 0x10) if ent else None
        ds = []
        for no, q in ppos:
            d = sum((u - v) ** 2 for u, v in zip(p, q)) ** 0.5 if p and q else None
            ok = allships or (ch is not None and d is not None and rad is not None and d < rad)
            if ok:
                cand[no].append(sid)
            ds.append('p%s %s%s' % (no, '?' if d is None else '%.0f m' % d, ' IN' if ok else ''))
        if detail:
            out.append('    ship %#06x lookup 0x17E7828 %s copy state %s pos %s | %s' % (
                sid or 0, 'found' if ch else 'NOT FOUND (skipped by 0xF10684 / 0xF11768)', cs, p3(p),
                ', '.join(ds)))
    out.append('  candidates now (range + id lookup, ray not checked; R %s, env+0x140 %s): %s' % (
        '?' if rad is None else '%.0f' % rad, 'all' if allships else 'radius',
        ' '.join('p%s=[%s]' % (no, ','.join('%04x' % s for s in v)) for no, v in cand.items()) or '-'))
    return out


def near_msb(p, lim=60.0):
    if not p:
        return None
    for ent, q in AIRSHIP_MSB:
        if sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5 < lim:
            return ent
    return None


def heap_enemies(r):
    """EnemyIns chrs by a heap search for the vtable (as npcs.find; read-only search_memory)"""
    pat = struct.pack('<Q', r.base + ENEMY_VT).hex()
    hits, start = [], None
    for _ in range(4000):
        p = {'pattern': pat, 'max_hits': 256, 'budget_ms': 100}
        if start:
            p['start'] = start
        time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
        res = r.m.call('search_memory', p)
        hits += [int(h, 16) if isinstance(h, str) else int(h['address'], 16) for h in res.get('hits', [])]
        start = res.get('next')
        if not start:
            break
    out = []
    for v in hits:
        ent = r.q(v + 0x18)
        if ent and r.q(ent) == v:
            out.append((v, r.q(ent + 0x10)))   # entry +0x10 flags: 5 near / 2 far
    return out


def game(who, deep=True, scan=False):
    r = R(who)
    L = []
    gd, net, par = r.g(GAMEDATA_G), r.g(NET_G), r.g(PAR_G)
    host = r.b(r.base + HOST_BYTE)
    L.append('==== game %s ====  HOST byte %s (%s)  offline(bda) %s  mode %s  phase %s' % (
        who, host, 'host' if host == 0 else 'guest' if host == 1 else '?', r.b(gd + 0xBDA) if gd else None,
        r.d(net + 0x1268) if net else None, r.d(par + 0x50) if par else None))
    if deep:
        st = []
        for off, orig, new, name in SITES:
            w = r.d(r.base + off)
            tag = 'orig' if w == orig else ('new' if new is not None and w == new else
                                             ('?' if w is None else 'other %08X' % w))
            st.append('%s=%s' % (name.split()[0], tag))
        rb = r.b(r.base + ROUTE_9E)
        st.append('S2=%s' % ({0x40: 'orig', 0x20: 'new'}.get(rb, '?' if rb is None else 'other %02X' % rb)))
        L.append('patch sites: ' + ' '.join(st))
        tb = r.g(ATTR_GOT)
        L.append('routing bytes (0x00 all, 0x20 non-server members, 0x40 server only): ' + ' '.join(
            '%02X=%s' % (t, '?' if not tb else '%02X' % (r.b(tb + 8 * t + 4) or 0)) for t in (0x9E, 0x9F, 0xA0, 0xA1)))
        if net:
            b0, b1 = r.q(net + 0x1248), r.q(net + 0x1250)
            mem = []
            if b0 and b1 and b1 >= b0 and (b1 - b0) % 0xF8 == 0 and (b1 - b0) // 0xF8 <= 16:
                for k in range((b1 - b0) // 0xF8):
                    e = b0 + k * 0xF8
                    mem.append('%#x(+E0 %s)' % (e, r.b(e + 0xE0)))
            # 0x20 sends only to members with +0xE0 == 0; routing applies only while +0x668 != 0 [V 0x1CD7E70..F50]
            L.append('members (+0x1248, 0xF8 each): %s  server link +0x658 %s  +0x668 %s' % (
                ' '.join(mem) or '-', hex(r.q(net + 0x658) or 0), hex(r.q(net + 0x668) or 0)))
    L.append('flags: ' + ' '.join('%d=%s' % (f, {True: 'ON', False: 'off', None: '?'}[event_flag(r, f)]) for f in FLAGS))

    me = r.q(r.g(PGD_G) + 0x20) if r.g(PGD_G) else None
    pl = players(r)
    L.append('local player no %s; player chrs: %s' % (r.d(me + 0xD0) if me else None,
                                                       ', '.join('%#x no %s' % p[:2] for p in pl) or '-'))
    L.append('Transmitter (goods %d): local inventory %s' % (TRANSMITTER, goods_count(r, me, TRANSMITTER)))
    # The item-mgr slot (mgr+8+k*0x290) holds NO pgd at +0x10: 0xCF3F08 returns a new 0x18 object {player no,
    # +8 slot, +0x10 pgd from 0xCEA240 kind 0x3F} [V 0xCF40D8..0xCF4108]. Read the pgd of every player chr instead.
    L.append('  per player chr pgd: ' + ('; '.join('no %s pgd %s x%s' % (no, hex(pgd) if pgd else None,
                                                                          goods_count(r, pgd, TRANSMITTER))
                                                    for _c, no, pgd in pl) or '-'))
    ur = use_records(r)
    L.append('  item-use records (slot: all / Transmitter [states]): ' + (
        '; '.join('no %d: %s / %d %s' % (no, v[0], v[1], v[2]) for no, v in sorted(ur.items())) or 'none'))
    if not r.g(ITEMMGR_G):
        L.append('  item mgr *(main+0x5B57E90) null (PrepareSecond grants nothing)')

    if not par:
        L.append('par null')
        return '\n'.join(L)
    a = r.q(par + 0x2C0)                               # pointer [V 0x114F614 ldr x0,[x19,#0x2c0]]
    if not a:
        L.append('AS *(par+0x2C0) null')
        return '\n'.join(L)
    t = r.b(a + 8)
    L.append('AS %#x type %s (0x0a = zeppelin) ready(+B) %s prepared(+C) %s (both 0 after PrepareThird)' % (
        a, '?' if t is None else '%#04x' % t, r.b(a + 0xB), r.b(a + 0xC)))
    n, ships = vec(r, a + 0xF0, 0x40)
    ids = {}
    L.append('  airships (+F0): %s' % n)
    for x in ships:
        sid = r.h(x)
        ids[sid] = x
        L.append('    id %#06x tgt %s count %s busy(+38) %s volley player(+8) %s' % (
            sid or 0, r.h(x + 0x18), r.q(x + 0x30), r.b(x + 0x38), r.d(x + 8)))
    L.extend(candidates_now(r, a, pl, deep))
    n, reqs = vec(r, a + 0x110, 0x38)
    L.append('  request queue (+110): %s' % n)
    for x in reqs:
        cn, cs = vec(r, x + 0x18, 2)
        cand = [r.h(c) for c in cs]
        L.append('    player %s pos %s target %s candidates %s %s' % (
            r.d(x), p3(r.f3(x + 8)), r.h(x + 0x14), cn, ' '.join('%#06x' % c for c in cand if c is not None)))
    n, sts = vec(r, a + 0x130, 0x20)
    L.append('  strikes (+130): %s' % n)
    for x in sts:
        # +4 = wait for the requester (1 until the requester's game sees its chr flag bit 23 clear and sends
        # 0x9F; every game clears +4 on 0x9F); fires only with +4 == 0 and pending +0x1C == 1 [V 0xF0C954,
        # 0xF0C6D4, 0xF0C888]. +4 1 forever = no 0x9F arrived. +0x1C 0 with +4 0 = 0x9F came before the answer.
        L.append('    player %s wait(+4) %s result(+8) %s point %s ship %s target %s pending(+1C) %s' % (
            r.d(x), r.b(x + 4), r.b(x + 8), p3(r.f3(x + 0xC)), r.h(x + 0x18), r.h(x + 0x1A), r.b(x + 0x1C)))

    if deep:
        found, seen = [], set()

        def add(c, src, flags=None):
            if c in seen:
                return
            i16, typ, pos = chr_id16(r, c), is_airship_type(r, c), chr_pos(r, c)
            ent = near_msb(pos)
            if i16 in ids or typ or ent:
                seen.add(c)
                found.append('    [%s] chr %#x id %s in list %s airship-type %s near MSB %s pos %s%s' % (
                    src, c, None if i16 is None else '%#06x' % i16, i16 in ids, typ, ent, p3(pos),
                    '' if flags is None else ' entry flags %#x' % flags))
                ow, ai = owner_flag(r, c), ai_state(r, c)
                found.append('      owner flag %s (>=0 driven HERE, -1 by another game)  AI fire(+74C5) %s '
                             'target(+8950) %s requester(+8A28) %s' % (
                                 None if ow is None else ow[0], None if ai is None else ai[0],
                                 p3(ai[1]) if ai else '?', None if ai is None else '%#x' % (ai[2] or 0)))
        for c in all_chrs(r):
            add(c, 'wcm')
        if scan:
            he = heap_enemies(r)
            for c, fl in he:
                add(c, 'heap', fl)
            L.append('  heap scan: %d enemy chrs' % len(he))
        L.append('  airship chrs (1000260/1000261 expected): %d' % len(found))
        L.extend(found)
    return '\n'.join(L)


def fast(games, secs):
    """'fast SECONDS': only the AS vectors (queue / strikes / ships), raw, every ~20 ms; prints every change with
    its time. Catches entries that live a few frames (the host's queue lives < 1 frame: C1 drains + decides in the
    same call, so a host queue entry is NOT expected to be seen; host strikes of a remote requester wait for its
    0x9F and are visible)."""
    rs = {g: R(g) for g in games}
    last, t0 = {}, time.time()
    while time.time() - t0 < secs:
        for g, r in rs.items():
            par = r.g(PAR_G)
            a = r.q(par + 0x2C0) if par else None
            if not a:
                continue
            raw = r.rd(a + 0xF0, 0x50)
            if not raw:
                continue
            out = []
            for off, size, name in ((0, 0x40, 'ships'), (0x20, 0x38, 'queue'), (0x40, 0x20, 'strikes')):
                b0, b1 = struct.unpack_from('<QQ', raw, off)
                n = (b1 - b0) // size if b0 and b1 >= b0 and (b1 - b0) % size == 0 and b1 - b0 < 0x4000 else 0
                body = r.rd(b0, n * size) if n else b''
                if name == 'ships':
                    out.append('ships ' + ' '.join('%04x:busy%d' % (struct.unpack_from('<H', body, k * size)[0],
                                                                  body[k * size + 0x38]) for k in range(n)))
                elif name == 'queue':
                    out.append('queue ' + ' '.join('p%d' % struct.unpack_from('<I', body, k * size)[0]
                                                   for k in range(n)))
                else:
                    out.append('strikes ' + ' '.join(
                        'p%d w%d r%d s%04x pend%d' % (struct.unpack_from('<I', body, k * size)[0], body[k * size + 4],
                                                       body[k * size + 8],
                                                       struct.unpack_from('<H', body, k * size + 0x18)[0],
                                                       body[k * size + 0x1C]) for k in range(n)))
            s = ' | '.join(out)
            if last.get(g) != s:
                print('%7.3f %s %s' % (time.time() - t0, g, s), flush=True)
                last[g] = s


if __name__ == '__main__':
    args = sys.argv[1:]
    games = args[0] if args and args[0].isalpha() and args[0].isupper() else 'AB'
    if 'fast' in args:
        fast(games, float(args[args.index('fast') + 1]) if args.index('fast') + 1 < len(args) else 30.0)
        sys.exit(0)
    secs = float(args[args.index('watch') + 1]) if 'watch' in args and args.index('watch') + 1 < len(args) else 0
    for g in games:
        try:
            print(game(g, scan='scan' in args))
        except Exception as ex:  # a closed game must not stop the others
            print('game %s: %s' % (g, ex))
    last, end = {}, time.time() + secs
    while time.time() < end:
        time.sleep(0.2)
        for g in games:
            try:
                s = game(g, deep=False)
            except Exception as ex:
                s = 'game %s: %s' % (g, ex)
            if last.get(g) != s:
                print('--- %.1f s' % (secs - (end - time.time())))
                print(s)
                last[g] = s
