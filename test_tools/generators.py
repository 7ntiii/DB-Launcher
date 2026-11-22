"""Enemy generators (spawners) of the twin games, side by side.
python diag/twin/generators.py AB            list both games (read only); rows matched by (chr set, generator #)
python diag/twin/generators.py A pool S G    the pool chrs of generator G in chr set S with state bytes and positions
python diag/twin/generators.py A goto S G [nudge]   stand next to the nearest pool chr of that generator
Recipe (diag/net/live_enumeration_notes.md section 4):
  WCM = *(main+0x5B3CD88); chr sets = *(WCM+0x18), u32 count WCM+0x10, stride 0x270;
  set +0xD8 u32 generator count, +0xE0 array of generator pointers                    [V 0xE8D354 (as list L), 0x178FAFC]
  (WCM+0x1E0 / +0x1E8 is a second, often empty, list of set pointers: same per-set layout [V 0xE8D314])
  generator: +0xB8 map data X, +0xC0 index, +0xCC enabled, +0xD0 point round robin, +0xD4 spawned count,
             +0xD8 pending count, +0xDC interval, +0xE0 request pending; param P via X+0x6A0.. (see param())  [V]
  P: +0 u8 max alive, +4/+6 u16 min/max per wave, +0x11 point mode, +0x30..+0x4C point ids, +0x60 i32[32] pool parts [V]
  pool chr: part p -> [[X+0x90]+0x10+8p]+0x10 chr index, map id X+0x35B0 -> WCM+8 block list -> chr set slot [V 0x178C0D0]
  chr data [chr+0x20]: +0x128 dead latch, +0x129 gen state (0 ok, 1 dead, 2 respawn asked), +0x12C removed, +0x130  [V]"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, GAMEDATA_G, dist, fmt3


def param(w, gen):
    """copy of the lookup at 0x178C390..0x178C488 [V]"""
    x = w.q(gen + 0xB8)
    idx = w.i(gen + 0xC0)
    if not x or idx is None or idx < 0:
        return None
    v0, v1 = w.q(x + 0x6A8), w.q(x + 0x6B0)
    if v0 == v1:
        if idx >= (w.i(x + 0x698) or 0):
            return None
        k = idx
    else:
        gd = w.g(GAMEDATA_G)
        reg = w.i(gd + 0xB10) if gd else None
        t = w.q(x + 0x6C8)
        if reg is None or reg > 3 or not t or not v0:
            return None
        common = w.d(t + 0x24) or 0
        if idx < common:
            k_index = (w.d(t + 0x20) or 0) + idx
        else:
            e = t + reg * 8
            if idx - common >= (w.d(e + 4) or 0):
                return None
            k_index = (w.d(e) or 0) + idx - common
        k = w.d(v0 + 4 * k_index)
    tab = w.q(x + 0x6A0)
    ent = w.q(tab + 8 * k) if tab is not None and k is not None else None
    return w.q(ent + 0x20) if ent else None


def pool(w, gen, p):
    """pool chrs of a generator, copy of 0x178C0D0..0x178C18C [V]"""
    x, wcm = w.q(gen + 0xB8), w.wcm()
    if not x or not wcm or not p:
        return []
    parts = w.q(x + 0x90)
    nparts = w.d(parts + 4) if parts else 0
    mapid = w.d(x + 0x35B0)
    slot = -1
    blist = w.q(wcm + 8)
    if mapid not in (None, 0xFFFFFFFF) and blist:
        n, arr = w.i(blist + 8) or 0, w.q(blist + 0x10)
        for k in range(min(n, 64)):
            if arr and w.d(arr + k * 0x1B0 + 8) == mapid:
                slot = w.i(arr + k * 0x1B0 + 0x18)
                break
    nsets, sets = w.d(wcm + 0x10) or 0, w.q(wcm + 0x18)
    out = []
    raw = w.rd(p + 0x60, 0x80)
    for pi in (struct.unpack('<32i', raw) if raw else []):
        if pi < 0 or pi >= (nparts or 0) - 1:   # the game skips p >= count-1 (0x178C0E8)
            continue
        part = w.q(parts + 0x10 + 8 * pi)
        ci = w.i(part + 0x10) if part else None
        if ci is None or ci < 0 or slot < 0 or slot >= nsets or not sets:
            continue
        s = sets + slot * 0x270
        if ci >= (w.i(s + 0x78) or 0):
            continue
        c = w.q((w.q(s + 0x80) or 0) + 0x38 * ci)
        if not c:
            continue
        data = w.q(c + 0x20)
        st = w.rd(data + 0x128, 12) if data else None
        out.append({'part': pi, 'chr': c, 'handle': (w.d(data + 0x78) or 0) & 0xFFFF if data else None,
                    'st': (st[0], st[1], struct.unpack_from('<I', st, 4)[0], struct.unpack_from('<I', st, 8)[0]) if st else None,
                    'hp': w.chr_hp(c), 'pos': w.chr_pos(c)})
    return out


def gens(w):
    out = {}
    for s in w.chr_sets():
        n, arr = s['ngen'] or 0, s['gens']
        if not arr or n <= 0 or n > 4096:
            continue
        raw = w.big(arr, 8 * n) or b''
        for gi in range(len(raw) // 8):
            g = struct.unpack_from('<Q', raw, 8 * gi)[0]
            if not g:
                continue
            b = w.rd(g + 0x40, 0xB0)
            if not b:
                continue
            u = lambda o, f='<I': struct.unpack_from(f, b, o - 0x40)[0]
            p = param(w, g)
            out[(s['i'], gi)] = {'gen': g, 'vt': w.q(g), 'block': s['block'], 'step': (u(0x50), u(0x54)),
                                 'idx': u(0xC0, '<i'), 'timer': u(0xC8, '<f'), 'enabled': b[0xCC - 0x40],
                                 'rr': u(0xD0), 'spawned': u(0xD4), 'pending': u(0xD8), 'interval': u(0xDC, '<f'),
                                 'req': b[0xE0 - 0x40], 'param': p,
                                 'pmax': w.b(p) if p else None, 'pmin': w.h(p + 4) if p else None, 'pmx': w.h(p + 6) if p else None,
                                 'mode': w.b(p + 0x11) if p else None}
    return out


def main():
    games = sys.argv[1]
    verb = sys.argv[2] if len(sys.argv) > 2 else 'list'
    if verb == 'list':
        rows, extra = {}, {}
        for g in games:
            w = W(g)
            rows[g] = gens(w)
            wcm = w.wcm()
            extra[g] = (w.d(wcm + 0x1E0) if wcm else None, len(w.chr_sets()), w.d(w.base + 0x492AFD8))
            w.report_missing()
        for g in games:
            print('%s: %d generators, chr sets %d, WCM+0x1E0 list count %s, role flag main+0x492AFD8 = %s' % (
                g, len(rows[g]), extra[g][1], extra[g][0], extra[g][2]))
        print('set.gen  block      ' + ' | '.join('%s: step  en spawned pend req timer  interval max min-max' % g for g in games))
        for key in sorted(set().union(*[set(v) for v in rows.values()])):
            cells, blk = [], None
            for g in games:
                r = rows[g].get(key)
                if not r:
                    cells.append('%s: -' % g)
                    continue
                blk = r['block']
                cells.append('%s: %s/%s %d %4d %3d %d %6.1f %6.1f %s %s-%s' % (
                    g, r['step'][0], r['step'][1], r['enabled'], r['spawned'], r['pending'], r['req'], r['timer'],
                    r['interval'], r['pmax'], r['pmin'], r['pmx']))
            print('%2d.%-3d %-10s %s' % (key[0], key[1], blk, ' | '.join(cells)))
        return
    w = W(games[0])
    key = (int(sys.argv[3]), int(sys.argv[4]))
    r = gens(w).get(key)
    if not r:
        print('no generator', key)
        w.report_missing()
        return
    _, _, here = w.me()
    chrs = pool(w, r['gen'], r['param'])
    if verb == 'pool':
        p = r['param']
        print('%s gen %s at %s param %s: max %s per wave %s-%s mode %s points %s' % (
            w.who, key, w.rel(r['gen']), w.rel(p), r['pmax'], r['pmin'], r['pmx'], r['mode'],
            list(struct.unpack('<8i', w.rd(p + 0x30, 0x20))) if p and w.rd(p + 0x30, 0x20) else None))
        for c in sorted(chrs, key=lambda c: dist(here, c['pos'])):
            print('  part %2d chr %s id %04x hp %s 128/129/12c/130 %s %s d=%.1f' % (
                c['part'], w.rel(c['chr']), c['handle'] or 0, c['hp'], c['st'], fmt3(c['pos']), dist(here, c['pos'])))
    elif verb == 'goto':
        live = [c for c in chrs if c['pos']]
        if not live:
            print('no pool chr with a position')
        else:
            c = min(live, key=lambda c: dist(here, c['pos']))
            w.goto_front(c['pos'], 3.0, 0.3, nudge='nudge' in sys.argv)
    w.report_missing()


if __name__ == '__main__':
    main()
