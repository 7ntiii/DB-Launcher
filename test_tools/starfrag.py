"""Star Fragment environment event (EnvEventParam 1210, env type 0x1A) on the twin games.
Notes: diag/net/starfrag_notes.md.  [V] = read in the code / params, [I] = inferred.

READ-ONLY (only Mem.read; snap writes a local json file, never game memory):
  python diag/twin/starfrag.py [GAMES=AB]          per game: event state, crash sites, ground items, players
  python diag/twin/starfrag.py WHO nearest         nearest fragment source for WHO + ready approach/goto lines
  python diag/twin/starfrag.py GAMES snap TAG      save counts / world-item ids to diag/twin/starfrag_<TAG>.json
  python diag/twin/starfrag.py GAMES diff TAG      compare now with that snapshot: per-player delta, new / gone
                                                   ground items, and the conservation line (created / lost)
  python diag/twin/starfrag.py GAMES watch [SECS]  poll every 2 s (default 120 s), print only changes
  python diag/twin/starfrag.py GAMES chain         the whole crash -> item -> pick-up -> Virtue chain per game, the
                                                   8 site assets (AEG099_211), and the first link that is missing
                                                   ("CHAIN STOPS AT ..."); slow (walks every geom once)
TEST-ONLY (writes the local player's position, like goto.py; never run it against a game outside the rig):
  python diag/twin/starfrag.py WHO tp N            teleport WHO 1.2 m in front of source N of `nearest`

What it reads (main-relative):
  par = *(0x5B3CDF8): +0x50 step, +0xB8 round, +0x2C0 -> AS env object (+8 env type, 0x1A = star [V 0xF0DDD0];
        +0x50 first crash done, +0x51 second crash done [V 0xF0DF2C / 0xF0E0E4]), +0x2D8 -> MS MapSystem
  MS:   +0x468 u32[2] asset handles of the two crash sites, +0x478 count (filled by the apply 0x1114A60 for
        object kind 0xF, max 2 [V 0x1115250..0x1115278]); kind-0xF list MS+0x208 (0x10-byte records, +4 handle [I])
  env:  current event = last u32 of [*(0x5B57EB8)+0x68]+0x58..+0x60; flags 5210 (start) / 5211 (end)
  item: Star Fragment = accessory 40000 (inventory id word 0x20009C40, EquipParamAccessory +0x42 = 1 [V]) and
        goods 8010 (same name text; not seen granted [I]); inventory pgd+0x2E8 (layout as itemauth.py)
  Virtue: counter id 60000 at wp+0x390 (wp = pgd+0x46D8; vtable main+0x56E7B58 [V 0xF70F4C]); records at
        +0x38/+0x40 (0x10 each; one per fragment taken while the event runs [V 0xCD0AF4, I one per fragment]);
        getter 0xF6DB80: 1 record -> WinPointObtain 601001000, 2 -> 601001001, else 0 [V];
        value byte by round (0xF68C6C): 601001000 = 0/10/15/0, 601001001 = 0/10/20/0 [V params]
  ground: MapItemMan *(0x5B3CDC0) lists +0x18/+0x48/+0x78 (node +0x30 id, +0x40 xyz, +0x58 flags 0x4000 taken);
        'STAR?' = node bytes +0x30..+0x1FF hold 0x20009C40 [I heuristic; diff is the reliable check]
  DROP: hooks of itemauth_live.py ITEMAUTH_DROP (D1 0xCF8F70, D2 0x15B4430, D3 0x15AAD2C, D4 0x15B4A50)
  2026-11-15 (starfrag2_notes.md):
  FRAG: node +0x58 bit 0x100000 = Star Fragment world item ("Pick up Star Fragment", button 4210 at 0x15A5D6C;
        set by the maker 0x15ABC94) [V]; node +0x3C = the crash-site asset handle, node +0x58 bit 3 = linked;
        pick-able only while that asset ins +0x126 has bits 0 and 1 set (0x15A1D20) [V]
  sites: the 8 assets AEG099_211_0000..0007 (asset id 99211, m10_00 parts 2399..2406), each with one MSB treasure
        (lot 52310); hidden by the MapSystem apply, shown by the crash step 0xF0DEC0 (S0/S1 only) [V]
  V2: starfrag_live.py STARFRAG_V2: bl hooks 0xC2D058 (online treasure gate) and 0xF0DF88 / 0xF0E144 (crash 1/2);
      the LAN host runs the treasure spawner 0x115DC10 for the drawn site at its crash, SPAWN flag set meanwhile.
      'chain' prints every decision input: role, offline byte, hook words, SPAWN, per site the treasure link
      (lot 52310), param +0xD, and MapItemMan counts (other asset-linked treasures for comparison).
"""
import json
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, MAPITEM_G, PAR_G, GAMEDATA_G, dist, fmt3  # noqa: E402

GDM_G = 0x5B57EB8
FLAGMAN_G = 0x5B44EB8
ROLE = 0x492AFD8
STAR_VT = 0x56E7B58
STAR_ID = 60000
STAR_ACC = 0x20009C40         # accessory 40000 as an inventory / lot id word (category 2 in bits 28..31) [V 0x15B1F70]
GOODS_8010 = 8010
VIRTUE = {1: (0, 10, 15, 0), 2: (0, 10, 20, 0)}   # WinPointObtain 601001000 / 601001001 bytes +4..+7 [V]
DROP_HOOKS = {0xCF8F70: ('D1 gate', 0x396F6908), 0x15B4430: ('D2 drop', 0xB40033D8),
              0x15AAD2C: ('D3 own-death', None), 0x15B4A50: ('D4 guest-create', None)}
try:
    sys.path.insert(0, 'diag/net')
    import itemauth_live as _IA        # data file only (lists of tuples); stock words follow a re-generation
    for _a, _o, _n, _c in _IA.ITEMAUTH_DROP:
        if _a in DROP_HOOKS:
            DROP_HOOKS[_a] = (DROP_HOOKS[_a][0], int.from_bytes(bytes.fromhex(_o), 'little'))
except Exception:
    pass
FRAG_FLAG = 0x100000          # node +0x58: Star Fragment world item [V 0x15ABC94 / 0x15A5D5C]
SITE_ASSET = 99211            # AEG099_211: the 8 crash-site assets [V MSB m10_00 parts 2399..2406]
SITE_LOT = 52310             # the MSB treasure lot of every site (accessory 40000 x1) [V MSB + ItemLotParam]
# STARFRAG_V2 (starfrag_live.py): bl hooks at the online gate 0xC2D058 and the two crash words; SPAWN flag in FAR_DATA
V2_HOOKS = {0xC2D058: ('gate', 0x340006C8), 0xF0DF88: ('crash1', 0x91080000), 0xF0E144: ('crash2', 0x91080000)}
V2_SPAWN = 0xC50F20C
V2_NEW = {}
try:
    import starfrag_live as _SF       # data file only
    V2_SPAWN = _SF.SPAWN
    for _a, _o, _n, _c in _SF.STARFRAG_V2:
        if _a in V2_HOOKS:
            V2_HOOKS[_a] = (V2_HOOKS[_a][0], int.from_bytes(bytes.fromhex(_o), 'little'))
            V2_NEW[_a] = int.from_bytes(bytes.fromhex(_n), 'little')
except Exception:
    pass
SNAP = 'diag/twin/starfrag_%s.json'


def event_flag(w, fid):
    """same walk as zeppelin.event_flag / promptcheck (0xC1BF60)"""
    mgr = w.g(FLAGMAN_G)
    if not mgr or not w.b(mgr + 0x228):
        return None
    area = (fid // 10000) % 100
    tbl = w.q(mgr + 0x218)
    ent = w.q(tbl) if tbl else None
    if not ent or area >= 10:
        return None
    bits = w.q(ent + area * 0xA8 + ((fid // 1000) % 10) * 0x10)
    rem = fid % 1000
    wd = w.d(bits + (rem >> 5) * 4) if bits else None
    return None if wd is None else bool((wd >> (31 - (rem & 31))) & 1)


def current_event(w):
    n = w.g(GDM_G)
    h = w.q(n + 0x68) if n else None
    b0, b1 = (w.q(h + 0x58), w.q(h + 0x60)) if h else (None, None)
    if not b0 or b1 is None or b1 < b0 or b1 - b0 > 256:
        return None
    return w.i(b1 - 4) if b1 > b0 else -1


def inventory(w, pgd):
    """(accessory 40000 count, goods 8010 count) in pgd+0x2E8"""
    inv = pgd + 0x2E8
    n1, total = w.d(inv + 0x2FC), w.d(inv + 0x368)
    a1, a2 = w.q(inv + 0x330), w.q(inv + 0x320)
    if n1 is None or total is None or total + 1 > 4096:
        return None, None
    acc = goods = 0
    for k in range(total + 1):
        e = (a1 + k * 16) if k < n1 else (a2 + (k - n1) * 16 if a2 else None)
        raw = w.rd(e, 16) if e else None
        if not raw:
            continue
        w0, w1, c = struct.unpack_from('<III', raw, 0)
        if not w0:
            continue
        if STAR_ACC in (w0, w1):
            acc += c
        elif GOODS_8010 in (w0 & 0x0FFFFFFF, w1 & 0x0FFFFFFF) and 4 in (w0 >> 28, w1 >> 28):
            goods += c
    return acc, goods


def star_counter(w, pgd):
    wp = w.q(pgd + 0x46D8)
    if not wp:
        return None
    c = wp + 0x390
    vt, cid = w.q(c), w.d(c + 8)
    beg, end = w.q(c + 0x38), w.q(c + 0x40)
    n = (end - beg) // 0x10 if beg and end and end >= beg and end - beg < 0x1000 else None
    recs = []
    if n:
        raw = w.rd(beg, 0x10 * min(n, 4))
        recs = [raw[i:i + 0x10].hex() for i in range(0, len(raw), 0x10)] if raw else []
    return {'ok': vt == w.base + STAR_VT and cid == STAR_ID, 'vt': w.rel(vt), 'id': cid, 'n': n,
            'off': w.b(c + 0x58), 'wp11': w.b(wp + 0x11), 'recs': recs}


def pgds(w):
    g = w.g(GDM_G)
    if not g:
        return None, []
    local = w.q(g + 0x20)
    cand = [w.q(g + o) for o in (0x08, 0x10, 0x20, 0x28)]
    pool = w.q(g + 0x30)
    if pool:
        cand += [pool + i * 0x47F0 for i in range(12)]
    out, seen = [], set()
    for p in cand:
        if not p or p in seen:
            continue
        seen.add(p)
        no = w.d(p + 0xD0)
        if no is None or no == 0xFFFFFFFF:
            continue
        out.append((p, no))
    return local, out


def player_positions(w):
    """player number -> position, from the player chr set (chr+0x20 -> +0x1D0 pgd -> +0xD0) [V itemauth_notes 2.4]"""
    out = {}
    for e in w.players():
        data = w.q(e[0] + 0x20)
        pgd = w.q(data + 0x1D0) if data else None
        no = w.d(pgd + 0xD0) if pgd else None
        pos = w.f3(e[5] + 0x70) if e[5] else w.chr_pos(e[0])
        if no is not None:
            out[no] = pos
    return out


def world_items(w):
    im = w.g(MAPITEM_G)
    out = []
    if not im:
        return out
    for li, off in enumerate((0x18, 0x48, 0x78)):
        node, k = w.q(im + off), 0
        while node and k < 300:
            body = w.rd(node + 0x30, 0x1D0) or b''
            star = any(struct.unpack_from('<I', body, i)[0] == STAR_ACC for i in range(0, len(body) - 3, 4))
            iid = w.d(node + 0x30)
            flags = w.d(node + 0x58) or 0
            frag = bool(flags & FRAG_FLAG)
            out.append({'list': li, 'id': iid, 'pos': w.f3(node + 0x40), 'flags': flags,
                        'star': star or frag, 'frag': frag, 'ahandle': w.d(node + 0x3C) if flags & 8 else None,
                        'tag': ((iid or 0) >> 27) & 0xF})
            node, k = w.q(node + 0x10), k + 1
    return out


def crash_sites(w, ms):
    out = []
    if not ms:
        return out, []
    n = w.q(ms + 0x478)
    for k in range(min(n or 0, 2)):
        h = w.d(ms + 0x468 + 4 * k)
        ins = w.geom_from_handle(h)
        out.append({'k': k, 'handle': h, 'pos': w.geom_pos(ins), 'ins': ins})
    cand = []
    b, e = w.q(ms + 0x28 + 0xF * 0x20), w.q(ms + 0x30 + 0xF * 0x20)
    if b and e and e > b and e - b <= 0x1000:
        raw = w.rd(b, e - b) or b''
        for i in range(0, len(raw) - 15, 0x10):
            h = struct.unpack_from('<I', raw, i + 4)[0]
            ins = w.geom_from_handle(h)
            cand.append({'raw': raw[i:i + 0x10].hex(), 'handle': h, 'pos': w.geom_pos(ins)})
    return out, cand


def site_shown(w, handle):
    """0x15A1D20 for an asset-linked item: the asset ins (+0x126 bits 0 and 1) and its parents (info+0x430)"""
    ins = w.geom_from_handle(handle)
    k = 0
    while ins and k < 8:
        v = w.b(ins + 0x126)
        if v is None or (v & 3) != 3:
            return False
        info = w.q(ins + 0x10)
        ins = w.q(info + 0x430) if info else None
        k += 1
    return k > 0


def star_sites(w):
    """the 8 crash-site assets (asset id 99211): handle ins+8, position, +0x126 shown bits [V]"""
    out = []
    for blockid, k, ins in w.all_geoms():
        info = w.q(ins + 0x10)
        aid = w.i(info + 0x18) if info else None
        if aid is None or aid % 10000000 != SITE_ASSET:
            continue
        out.append({'handle': w.d(ins + 8), 'pos': w.geom_pos(ins), 'b126': w.b(ins + 0x126), 'ins': ins,
                    'block': blockid})
    return sorted(out, key=lambda r: r['handle'] or 0)


def create_hook(w):
    """STARFRAG_V2 hook words: 'V2' when all three are the group's words, else each one's state"""
    st = []
    for a, (name, stock) in V2_HOOKS.items():
        v = w.d(w.base + a)
        st.append((name, '?' if v is None else 'stock' if v == stock else
                   'V2' if v == V2_NEW.get(a, -1) else 'other %08X' % v))
    if all(t == 'V2' for _, t in st):
        return 'STARFRAG_V2 (gate+crash1+crash2)'
    return ' '.join('%s %s' % kv for kv in st)


def spawn_flag(w):
    """FAR_DATA u32 of STARFRAG_V2: 1 only while the crash cave runs the spawner (expect 0 in every read)"""
    return w.d(w.base + V2_SPAWN)


def treasure_link(w, ins):
    """decision input of 0xC2CEE0 / 0xF2C2A0 for one asset ins [I layout, from the code]:
    info = ins+0x10; t = [[info+0x50]+0x80]; list [t+8 .. t+0x10) of entry pointers; entry +0xC == 4 = treasure,
    data [entry+0x20]: lot +0x10, type byte +0x40. Also the site param byte +0xD = [[info+0x20]+0xD] (1 = not shown)."""
    out = {'lots': [], 'types': [], 'p0d': None, 'raw': None}
    info = w.q(ins + 0x10) if ins else None
    if not info:
        return out
    par = w.q(info + 0x20)
    out['p0d'] = w.b(par + 0xD) if par else None
    a = w.q(info + 0x50)
    t = w.q(a + 0x80) if a else None
    b, e = (w.q(t + 8), w.q(t + 0x10)) if t else (None, None)
    out['raw'] = '%s/%s' % (w.rel(a) if a else None, w.rel(t) if t else None)
    if not b or not e or e < b or e - b > 0x200:
        return out
    for p in range(b, e, 8):
        ent = w.q(p)
        if not ent or w.d(ent + 0xC) != 4:
            continue
        d = w.q(ent + 0x20)
        if d:
            out['lots'].append(w.i(d + 0x10))
            out['types'].append(w.b(d + 0x40))
    return out


def state(who):
    w = W(who)
    s = {'who': who, 'w': w}
    s['role'] = w.b(w.base + ROLE)
    gd = w.g(GAMEDATA_G)
    s['offline'] = w.b(gd + 0xBDA) if gd else None
    par = w.g(PAR_G)
    s['step'], s['round'] = (w.d(par + 0x50), w.d(par + 0xB8)) if par else (None, None)
    s['event'] = current_event(w)
    asx = w.q(par + 0x2C0) if par else None
    s['as'] = (w.b(asx + 8), w.b(asx + 0x50), w.b(asx + 0x51)) if asx else None
    s['f5210'], s['f5211'] = event_flag(w, 5210), event_flag(w, 5211)
    ms = w.q(par + 0x2D8) if par else None
    s['ms'] = ms
    s['sites'], s['cand'] = crash_sites(w, ms)
    s['items'] = world_items(w)
    local, ps = pgds(w)
    pos = player_positions(w)
    s['players'] = []
    for p, no in ps:
        acc, goods = inventory(w, p)
        s['players'].append({'no': no, 'local': p == local, 'acc': acc, 'goods': goods, 'ctr': star_counter(w, p),
                             'banked': w.h(p + 0x42C8), 'pos': pos.get(no)})
    s['me'] = w.me()[2]
    s['hooks'] = {}
    for a, (name, stock) in DROP_HOOKS.items():
        v = w.d(w.base + a)
        s['hooks'][name] = '?' if v is None else ('stock' if v == stock else ('%08X' % v if stock is None else 'PATCHED'))
    s['create'] = create_hook(w)
    return s


def virtue_of(n, rnd):
    if not n or n not in VIRTUE or not rnd:
        return 0
    return VIRTUE[n][min(rnd, 4) - 1]


def show(s):
    w = s['w']
    ev = s['event']
    ast = s['as']
    active = ast is not None and ast[0] == 0x1A
    print('==== %s  role %s (%s)  offline %s  step %s round %s  event %s%s  AS type %s crash1 %s crash2 %s  '
          'flag5210 %s 5211 %s' % (
              s['who'], s['role'], {0: 'host', 1: 'guest'}.get(s['role'], '?'), s['offline'], s['step'], s['round'],
              ev, ' (Star Fragment)' if ev == 1210 else '', None if not ast else '%#x' % ast[0],
              None if not ast else ast[1], None if not ast else ast[2], s['f5210'], s['f5211']))
    print('   star event %s; DROP hooks %s' % ('ACTIVE' if active else 'not active',
                                              ', '.join('%s %s' % kv for kv in s['hooks'].items())))
    print('   STARFRAG_V2 hooks: %s  SPAWN flag %s' % (s['create'], spawn_flag(w)))
    print('   crash sites (MS %s +0x478 count %d):' % (w.rel(s['ms']), len(s['sites'])))
    for c in s['sites']:
        print('     S%d handle %08x pos %s d=%.1f' % (c['k'], c['handle'] or 0, fmt3(c['pos']), dist(s['me'], c['pos'])))
    if s['cand']:
        print('   kind-0xF candidates (%d): %s' % (len(s['cand']), ' '.join(
            '%08x%s' % (c['handle'], fmt3(c['pos']) if c['pos'] else '') for c in s['cand'][:12])))
    items = sorted(s['items'], key=lambda r: dist(s['me'], r['pos']))
    stars = [r for r in items if r['star']]
    print('   ground items %d (STAR? %d):' % (len(items), len(stars)))
    for r in items[:20]:
        print('     id %08x%s list %d %s d=%.1f flags %08x%s%s%s' % (
            r['id'] or 0, '(p%d)' % r['tag'] if r['tag'] else '', r['list'], fmt3(r['pos']), dist(s['me'], r['pos']),
            r['flags'], ' TAKEN' if r['flags'] & 0x4000 else '',
            ' FRAG(site %08x)' % (r['ahandle'] or 0) if r['frag'] else (' STAR?' if r['star'] else ''),
            '' if not r['frag'] else (' pick-able' if site_shown(w, r['ahandle']) else ' hidden')))
    for p in s['players']:
        c = p['ctr']
        ctr = 'no wp' if not c else '60000 records %s%s%s%s' % (
            c['n'], '' if c['ok'] else ' (vt %s id %s: NOT the star counter?)' % (c['vt'], c['id']),
            ' off' if c['off'] else '', ' wp+0x11=%d (counts 0)' % c['wp11'] if c['wp11'] else '')
        live = virtue_of(c['n'] if c else 0, s['round']) if active else 0
        print('   player %d%s: fragments acc40000 %s goods8010 %s | %s -> star Virtue now %d | banked %s | pos %s' % (
            p['no'], ' (own)' if p['local'] else ' (copy)', p['acc'], p['goods'], ctr, live, p['banked'],
            fmt3(p['pos'])))
        if c and c['recs']:
            print('       records %s' % ' '.join(c['recs']))
    w.report_missing()


def sources(s):
    out = []
    for c in s['sites']:
        if c['pos']:
            out.append(('crash site S%d' % c['k'], c['pos']))
    for r in s['items']:
        if r['pos'] and not r['flags'] & 0x4000:
            out.append(('ground item %08x%s' % (r['id'] or 0, ' STAR?' if r['star'] else ''), r['pos'], r['star']))
    own = [p['no'] for p in s['players'] if p['local']]
    for p in s['players']:
        if not p['local'] and p['pos'] and (p['acc'] or (p['ctr'] and p['ctr']['n'])):
            out.append(('player %d carries (copy count %s)' % (p['no'], p['acc']), p['pos']))
    out = [(o[0], o[1], o[2] if len(o) > 2 else True) for o in out]
    return sorted(out, key=lambda o: (not o[2], dist(s['me'], o[1]))), own


def nearest(who):
    s = state(who)
    srcs, _ = sources(s)
    if not srcs:
        print('%s: no fragment source (event %s, crash sites %d, ground items %d)' % (
            who, s['event'], len(s['sites']), len(s['items'])))
        return
    for k, (name, pos, starish) in enumerate(srcs[:8]):
        print('N%d %s at %s d=%.1f' % (k, name, fmt3(pos), dist(s['me'], pos)))
    name, pos, _ = srcs[0]
    print('nearest: %s' % name)
    print('  python diag/twin/approach.py %s %.2f %.2f %.2f 1.2' % (who, pos[0], pos[1], pos[2]))
    print('  python diag/twin/goto.py %s %.2f %.2f %.2f' % (who, pos[0], pos[1] + 0.3, pos[2] - 1.2))
    print('  python diag/twin/starfrag.py %s tp 0      (TEST-ONLY teleport)' % who)


def tp(who, k):
    """TEST-ONLY: writes the local player's position (phys+0x70) and yaw, as goto.py / item_sources.py goto."""
    s = state(who)
    srcs, _ = sources(s)
    if k >= len(srcs):
        sys.exit('no source N%d' % k)
    name, pos, _ = srcs[k]
    print('TEST-ONLY teleport %s to %s' % (who, name))
    s['w'].goto_front(pos, 1.2, 0.3)


def summary(s):
    me = [p for p in s['players'] if p['local']]
    return {'role': s['role'], 'round': s['round'], 'event': s['event'],
            'players': {str(p['no']): {'acc': p['acc'], 'goods': p['goods'], 'n': p['ctr']['n'] if p['ctr'] else None,
                                       'local': p['local'], 'banked': p['banked']} for p in s['players']},
            'own': me[0]['no'] if me else None,
            'items': sorted('%08x' % r['id'] for r in s['items'] if r['id'] is not None and not r['flags'] & 0x4000),
            'stars': sorted('%08x' % r['id'] for r in s['items'] if r['star'] and not r['flags'] & 0x4000)}


def totals(sums):
    """real fragments = each game's OWN player's inventory + ground items (union over games; one id = one item)"""
    own = sum((v['players'].get(str(v['own']), {}).get('acc') or 0) for v in sums.values() if v['own'] is not None)
    ground = set()
    stars = set()
    for v in sums.values():
        ground |= set(v['items'])
        stars |= set(v['stars'])
    return own, ground, stars


def snap(games, tag):
    sums = {g: summary(state(g)) for g in games}
    json.dump(sums, open(SNAP % tag, 'w'), indent=1)
    own, ground, stars = totals(sums)
    print('saved %s: own-inventory fragments %d, ground items %d (STAR? %d)' % (SNAP % tag, own, len(ground), len(stars)))
    for g, v in sums.items():
        print('  %s own player %s: %s' % (g, v['own'], v['players'].get(str(v['own']))))


def diff(games, tag):
    old = json.load(open(SNAP % tag))
    new = {g: summary(state(g)) for g in games}
    for g in games:
        o, n = old.get(g), new[g]
        if not o:
            print(g, 'not in snapshot')
            continue
        for no, pn in n['players'].items():
            po = o['players'].get(no, {})
            d = (pn.get('acc') or 0) - (po.get('acc') or 0)
            dn = (pn.get('n') or 0) - (po.get('n') or 0)
            if d or dn or no == str(n['own']):
                print('  %s player %s%s: acc40000 %s -> %s (%+d), 60000 records %s -> %s (%+d)' % (
                    g, no, ' (own)' if pn['local'] else ' (copy)', po.get('acc'), pn.get('acc'), d, po.get('n'),
                    pn.get('n'), dn))
        add, gone = sorted(set(n['items']) - set(o['items'])), sorted(set(o['items']) - set(n['items']))
        print('  %s ground: new %s gone %s' % (g, add, gone))
    o_own, o_ground, _ = totals(old)
    n_own, n_ground, _ = totals(new)
    d_own, d_ground = n_own - o_own, len(n_ground) - len(o_ground)
    print('conservation: own inventories %d -> %d (%+d), ground items %d -> %d (%+d) => %s' % (
        o_own, n_own, d_own, len(o_ground), len(n_ground), d_ground,
        'balanced' if d_own + d_ground == 0 else ('CREATED %d' % (d_own + d_ground) if d_own + d_ground > 0
                                                  else 'LOST %d' % -(d_own + d_ground))))
    print('  (assumes each new ground item holds the fragments of one drop; a drop of 2 fragments is ONE item: '
          'check the dier\'s delta)')


def watch(games, secs):
    last, end = {}, time.time() + secs
    while time.time() < end:
        for g in games:
            try:
                s = state(g)
                v = summary(s)
                key = json.dumps([v['event'], s['as'], v['players'], v['items']], sort_keys=True)
                txt = 'event %s AS %s players %s items %s' % (v['event'], s['as'], {k: (p['acc'], p['n']) for k, p in
                                                                                    v['players'].items()}, v['items'])
            except Exception as ex:
                key = txt = 'error %s' % ex
            if last.get(g) != key:
                print('%5.0f s %s: %s' % (secs - (end - time.time()), g, txt))
                last[g] = key
        time.sleep(2)


def chain(games):
    """one live read of the whole chain; prints the first missing link per game"""
    per = {}
    for g in games:
        try:
            s = state(g)
        except Exception as ex:
            print(g, 'not readable:', ex)
            continue
        w = s['w']
        sites = star_sites(w)
        frags = [r for r in s['items'] if r['frag']]
        site_h = [c['handle'] for c in s['sites']]
        me = [p for p in s['players'] if p['local']]
        me = me[0] if me else None
        ast = s['as']
        per[g] = {'sites': site_h, 'frags': sorted('%08x>%08x' % (r['id'] or 0, r['ahandle'] or 0) for r in frags)}
        spawn = spawn_flag(w)
        linked = [r for r in s['items'] if r['ahandle'] is not None and not r['frag']]
        print('==== %s  role %s (%s)  offline byte %s  round %s  event %s' % (
            g, s['role'], {0: 'host/offline', 1: 'guest'}.get(s['role'], '?'), s['offline'], s['round'], s['event']))
        print('   decision inputs: hooks %s | SPAWN %s (must read 0) | crash cave acts: %s' % (
            s['create'], spawn, 'YES (LAN host)' if s['role'] == 0 and not s['offline'] else
            'no (offline: stock item since load)' if s['offline'] else 'no (guest: gets the host item)'))
        print('   MapItemMan items %d, fragments %d, other asset-linked items %d %s' % (
            len(s['items']), len(frags), len(linked),
            ' '.join('%08x>%08x' % (r['id'] or 0, r['ahandle']) for r in linked[:6])))
        print('   site assets 99211 loaded: %d' % len(sites))
        no_link = []
        for c in sites:
            tag = ' S%d' % site_h.index(c['handle']) if c['handle'] in site_h else ''
            it = [r for r in frags if r['ahandle'] == c['handle']]
            tl = treasure_link(w, c['ins'])
            if SITE_LOT not in tl['lots']:
                no_link.append(c['handle'])
            print('     %08x%s pos %s shown(+0x126&3)=%s param+0xD %s treasure lots %s types %s (%s) item %s' % (
                c['handle'] or 0, tag, fmt3(c['pos']), (c['b126'] or 0) & 3, tl['p0d'], tl['lots'] or '-',
                tl['types'] or '-', 'lot 52310 OK' if SITE_LOT in tl['lots'] else 'NO LOT 52310 (raw %s)' % tl['raw'],
                ', '.join('%08x%s' % (r['id'] or 0, ' TAKEN' if r['flags'] & 0x4000 else '') for r in it) or '-'))
        steps = [
            ('event 1210 current', s['event'] == 1210),
            ('AS env type 0x1A', bool(ast and ast[0] == 0x1A)),
            ('MapSystem crash sites (MS+0x478 >= 1)', len(s['sites']) >= 1),
            ('drawn sites have a treasure link with lot 52310', bool(site_h) and not any(h in no_link for h in site_h)),
            ('STARFRAG_V2 applied (or offline)', bool(s['offline']) or s['create'].startswith('STARFRAG_V2')),
            ('crash 1 done (AS+0x50, 30 s; LAN items are made here)', bool(ast and ast[1])),
            ('fragment world items exist (node +0x58 bit 0x100000)', len(frags) >= 1),
            ('an item is linked to S0/S1', any(r['ahandle'] in site_h for r in frags)),
            ('S0 shown -> its item pick-able', any(r['ahandle'] == site_h[0] and site_shown(w, r['ahandle'])
                                                   for r in frags) if site_h else False),
            ('own player holds a fragment (acc 40000)', bool(me and me['acc'])),
            ('own 60000 records (Virtue live)', bool(me and me['ctr'] and me['ctr']['n'])),
        ]
        stop = None
        for k, (name, ok) in enumerate(steps):
            print('   [%s] %d %s' % ('x' if ok else ' ', k + 1, name))
            if not ok and stop is None:
                stop = name
        if me:
            n = me['ctr']['n'] if me['ctr'] else 0
            print('   own player %d: acc %s records %s -> star Virtue now %d (round %s), banked %s' % (
                me['no'], me['acc'], n, virtue_of(n, s['round']) if ast and ast[0] == 0x1A else 0, s['round'],
                me['banked']))
        print('   CHAIN STOPS AT: %s' % (stop or 'nothing (complete up to the own Virtue)'))
    if len(per) > 1:
        vals = list(per.values())
        print('same crash sites on all games: %s; same fragment items (id>site) on all games: %s' % (
            all(v['sites'] == vals[0]['sites'] for v in vals), all(v['frags'] == vals[0]['frags'] for v in vals)))
        for g, v in per.items():
            print('  %s sites %s items %s' % (g, ['%08x' % h for h in v['sites']], v['frags']))


def main():
    a = sys.argv[1:]
    games = a[0] if a and a[0].isalpha() and a[0].isupper() else 'AB'
    verb = a[1] if len(a) > 1 else 'show'
    if verb == 'show':
        for g in games:
            try:
                show(state(g))
            except Exception as ex:
                print(g, 'not readable:', ex)
        if len(games) > 1:
            try:
                own, ground, stars = totals({g: summary(state(g)) for g in games})
                print('TOTAL own-inventory fragments %d + ground items %d (STAR? %d)' % (own, len(ground), len(stars)))
            except Exception as ex:
                print('total: %s' % ex)
    elif verb == 'nearest':
        nearest(games[0])
    elif verb == 'tp':
        tp(games[0], int(a[2]) if len(a) > 2 else 0)
    elif verb == 'snap':
        snap(games, a[2])
    elif verb == 'diff':
        diff(games, a[2])
    elif verb == 'watch':
        watch(games, float(a[2]) if len(a) > 2 else 120.0)
    elif verb == 'chain':
        chain(games)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
