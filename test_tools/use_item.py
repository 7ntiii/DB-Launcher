"""use_item.py WHO [ITEM_SLOT] [lock] [btn BUTTON] [probe] [validate] [secs S]  -- TEST ONLY item-use driver.

Run from the workspace root:
  python diag/twin/use_item.py B validate      press Up (Goldblood Stake, verified heal input): the detector must
                                               show "requests +1" and stakes -1 -> proves the reader works
  python diag/twin/use_item.py B               use the quick item shown in the RIGHT HUD slot (button Down [I])
  python diag/twin/use_item.py B probe         try Down, Right, Left, Y, X one by one until "requests" moves
  python diag/twin/use_item.py B lock          first lock on to the nearest enemy (kill.py: move 1.5 m, face, StickR)
  ITEM_SLOT = number of "Switch Quick Item" presses (Right [I]) before the use (default 0).
  python diag/twin/use_item.py B range         READ-ONLY: each airship's 3D distance from B's player, the game's
                                               radius (param row 0 +0x58, read live) and ACCEPT/DENY by the rule
                                               of the host decision 0xF11140 (zeppelin4_notes.md section 8)
  python diag/twin/use_item.py B wait [max S]  poll range every 0.25 s until a ship would be accepted, then press
                                               the use button (Down) once (default max 300 s)
  Run range/wait on the REQUESTER's game; for a guest, busy/held are the guest's copies (the host's decide).

DETECTOR [V]: every item-use request bumps the u32 request counter [[main+0x59E1B28]]+0x2180 (0xCF3D90..0xCF3DC4,
reset only at 0xCF1870 / 0xD07DD8). The records (slot +0x50 deque) live only ~one ConfirmEffects tick (50 ms) and
were missed by the old 0.2 s poll, so "0 records" proved nothing. The request is made by the anim event handler
0x194DFC4 at the use frame of the item animation (0x194E3B8 bl 0xCF3520, preceded by 0x194E384 bl 0xF102C0 for
goods with param +0xA3 bit 3 = Transmitter): no animation -> no request -> no zeppelin request.
Native preconditions printed below [V 0x194E318..0x194E384, 0xF102C0, 0xCF3A00..0xCF3A1C]: user = local chr
(WCM+0x1A8), AS = *(par+0x2C0) non-null, goods +0xA3 bit 3 (static: 4120 has 8), inventory count >= pending + 1.
NOT needed natively: lock-on (target id = lock target or 0xFFFF), a target type, range (range only filters the
airship candidates: radius + ray test in 0xF102C0; an empty list is a DENIED strike, not a missing use).
The HKS state W_ItemSupportRequest (c0000.hks) plays the use animation; its own gates are bytecode [I].
"""
import math
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import tctl  # noqa: E402
import zeppelin as Z  # noqa: E402

args = sys.argv[1:]
if not args:
    print(__doc__)
    sys.exit(1)
who = args[0]
slot = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
opt = lambda k: args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None  # noqa: E731
btn = opt('btn') or ('Up' if 'validate' in args else 'Down')
secs = float(opt('secs') or 4.0)
r = Z.R(who)


def counter():
    h = r.g(Z.EFFECT_SYNC)
    mgr = r.q(h) if h else None
    return r.d(mgr + 0x2180) if mgr else None


def local():
    w = r.g(Z.WCM_G)
    c = r.q(w + 0x1A8) if w else None
    data = r.q(c + 0x20) if c else None
    pgd = r.q(data + 0x1D0) if data else None
    arr = r.q(w + 0x30) if w else None
    e3 = r.q(arr + 0x18) if arr else None          # entry 0 +0x18 -> +0xF30 HP (hp.py)
    return c, pgd, e3


def precond():
    c, pgd, e3 = local()
    par = r.g(Z.PAR_G)
    a = r.q(par + 0x2C0) if par else None
    pos = Z.chr_pos(r, c) if c else None
    ships = []
    if a:
        _, ents = Z.vec(r, a + 0xF0, 0x40)
        want = {r.h(x): x for x in ents}
        for ch in Z.all_chrs(r):
            i16 = Z.chr_id16(r, ch)
            if i16 in want:
                p = Z.chr_pos(r, ch)
                d = math.dist(p, pos) if p and pos else None
                x = want[i16]
                ships.append('%#06x dist %s busy %s n %s' % (i16, '?' if d is None else '%.0f m' % d,
                                                            r.b(x + 0x38), r.q(x + 0x30)))
    rec = Z.use_records(r).get(r.d(pgd + 0xD0) if pgd else None)
    return {
        'requests(+0x2180)': counter(),
        'local chr': hex(c) if c else None,
        'player no': r.d(pgd + 0xD0) if pgd else None,
        'HP': r.i(e3 + 0xF30) if e3 else None,
        'Transmitter x': Z.goods_count(r, pgd, Z.TRANSMITTER),
        'pending Transmitter records': rec[1] if rec else 0,
        'stakes(+0x4649)': r.b(pgd + 0x4649) if pgd else None,
        'AS type': None if not a else '%#04x' % (r.b(a + 8) or 0),
        'airships': ' | '.join(ships) or 'none',
        'phase step': r.d(par + 0x50) if par else None,
    }


def show(tag, s):
    print('%s %s' % (tag, '  '.join('%s=%s' % kv for kv in s.items())), flush=True)


def press(steps):
    return tctl.call(who, {'method': 'input_sequence', 'params': {'steps': steps}})


def lock_nearest():
    """kill.py's lock-on: move 1.5 m in front of the nearest active enemy, face it, StickR (TEST ONLY write)"""
    import npcs
    m = r.m
    wcm = m.u64(m.base + Z.WCM_G)
    me = struct.unpack('<7Q', m.read(m.u64(wcm + 0x30), 56))
    phys = me[5]
    here = struct.unpack('<3f', m.read(phys + 0x70, 12))
    en = [e for e in npcs.find(m) if e['phys'] and e['flags'] & 0xff == 5]
    if not en:
        print('lock: no active enemy found, using no lock')
        return
    t = min(en, key=lambda e: math.dist(e['pos'], here))
    ep = t['pos']
    yaw = math.atan2(ep[0] - here[0], ep[2] - here[2])
    spot = (ep[0] - 1.5 * math.sin(yaw), ep[1] + 0.3, ep[2] - 1.5 * math.cos(yaw))
    m.write(phys + 0x70, struct.pack('<3f', *spot))
    m.write(phys + 0x64, struct.pack('<f', yaw))
    time.sleep(0.5)
    press([{'buttons': ['StickR'], 'frames': 4}, {'frames': 12}])
    print('lock: enemy handle %x at (%.1f %.1f %.1f)' % (t['handle'], *ep))


def try_button(b):
    before = precond()
    show('before %-6s' % b, before)
    th = threading.Thread(target=lambda: press([{'buttons': [b], 'frames': 6}, {'frames': 90}]))
    th.start()
    t0, c0, seen = time.time(), before['requests(+0x2180)'], None
    while time.time() - t0 < secs:
        c = counter()
        if c is not None and c0 is not None and c != c0 and seen is None:
            seen = time.time() - t0
        time.sleep(0.05)
    th.join(timeout=10)
    after = precond()
    show('after  %-6s' % b, after)
    moved = (after['requests(+0x2180)'] or 0) - (c0 or 0)
    print('  -> %s: requests %+d%s' % (b, moved, '' if seen is None else ' (first change at %.2f s)' % seen))
    return moved


def param_row0(obj, n_off, f_off):
    """row 0 of a param file, as 0x155A140 / 0x155AC00 do it [V]: file = [obj+f_off] (needs u32 [obj+n_off]),
    data x8 = [[file+0x70]+0x78], count s32 [x8-0xC], id table at x8 + align16(s32 [x8-0x10]) (8-byte entries
    {u32 id, u32 idx}), search for id 0 (the game's own downward halving), then the row offset by type byte +0x2D."""
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


RADIUS_G = 0x59DFFF8   # GOT -> global -> obj; +0x20D0 n / +0x20D8 file; row 0 +0x58 f32 = radius [V 0x155A140]
ENVP_G = 0x5B3CE68     # obj; +0x36C0 n / +0x36C8 file; row 0 [V 0x155AC00]


def no_fire_ids(c):
    """ship chr's region list checked in 0xF117A8..0xF11C2C: [[chr+0x2470]+0x18]: +0x70 tbl, +0x80 idx ->
    [[tbl+0x90]+idx*8+0x10]+0x70 (u16 type 0xB) +8 -> 9 u32 region ids; requester point inside one = ship skipped"""
    x9 = r.q(r.q(c + 0x2470) + 0x18) if r.q(c + 0x2470) else None
    x10 = r.q(x9 + 0x70) if x9 else None
    if not x10:
        return []
    k, tb = r.i(x9 + 0x80), r.q(x10 + 0x90)
    if k is None or k < 0 or not tb or k >= (r.i(tb + 4) or 0) - 1:
        return []
    x28 = r.q(tb + k * 8 + 0x10)
    st = r.q(x28 + 0x70) if x28 else None
    if not st or r.h(st) != 0xB:
        return []
    lst = r.q(st + 8)
    return [v for v in (r.i(lst + 4 * j) for j in range(9)) if v not in (None, -1, 0)] if lst else []


HEAP = {}


def judge(verbose=True):
    """the host decision 0xF11140 (+ request side 0xF102C0) evaluated NOW for the local player [V rule, see
    zeppelin4_notes.md section 8]; returns the ship id that would be chosen or None"""
    c, pgd, _ = local()
    par = r.g(Z.PAR_G)
    a = r.q(par + 0x2C0) if par else None
    pos = Z.chr_pos(r, c) if c else None
    row = param_row0(r.q(r.g(RADIUS_G) or 0), 0x20D0, 0x20D8)
    rad = r.f(row + 0x58) if row else None
    env = param_row0(r.g(ENVP_G), 0x36C0, 0x36C8)
    e = {k: (r.i(env + k) if env else None) for k in (0x140, 0x18, 0x1C, 0xB4, 0xB8)}
    tx = Z.goods_count(r, pgd, Z.TRANSMITTER)
    held = set()
    _, sts = Z.vec(r, a + 0x130, 0x20) if a else (None, [])
    for s in sts:
        if r.b(s + 0x1C):
            held.add(r.h(s + 0x18))
    out, best = [], None
    if a and pos:
        _, ents = Z.vec(r, a + 0xF0, 0x40)
        want = {r.h(x): x for x in ents}
        chrs = {Z.chr_id16(r, ch): ch for ch in Z.all_chrs(r)}
        for i16, x in want.items():
            ch = Z.chr_by_id(r, i16) or chrs.get(i16)
            if not ch:
                if '_heap' not in HEAP:                    # slow fallback once: the scan that finds them
                    HEAP['_heap'] = {Z.chr_id16(r, c2): c2 for c2, _fl in Z.heap_enemies(r)}
                ch = HEAP['_heap'].get(i16)
            p = Z.chr_pos(r, ch) if ch else None
            d = math.dist(p, pos) if p else None
            why = []
            if r.b(x + 0x38):
                why.append('busy')
            if i16 in held:
                why.append('held by pending strike')
            if d is None:
                why.append('no chr')
            elif rad is None or d >= rad:
                why.append('out of range')
            nf = no_fire_ids(ch) if ch else []
            ok = not why
            if ok and (best is None or d < best[1]):
                best = (i16, d)
            out.append('%04x d=%s h=%s%s -> %s' % (
                i16, '?' if d is None else '%.1f' % d,
                '?' if not p else '%.0f' % (p[1] - pos[1]),
                (' nofire%s' % nf) if nf else '', 'OK' if ok else ','.join(why)))
    if not tx:
        best = None
    if verbose:
        print('range: pos %s radius %s (3D) Transmitter %s env+0x140 %s SpEffect ok/deny %s/%s notice ok/deny '
              '%s/%s' % (Z.p3(pos), '?' if rad is None else '%.1f' % rad, tx, e[0x140], e[0x18], e[0x1C],
                         e[0xB4], e[0xB8]), flush=True)
        print('  ' + (' | '.join(out) or 'no airships in AS+0xF0'), flush=True)
        print('  -> %s' % ('ACCEPT %04x (nearest free in range; ray test + nofire regions not checked)' % best[0]
                           if best else 'DENY now'), flush=True)
    return best


if 'range' in args:
    judge()
    sys.exit(0)
if 'wait' in args:
    if 'lock' in args:
        print('wait + lock: lock moves the player next to an enemy and breaks the range; use one of them')
        sys.exit(1)
    lim = float(opt('max') or 300)
    t0 = time.time()
    while time.time() - t0 < lim:
        if judge(verbose=False):
            break
        time.sleep(0.25)
    else:
        judge()
        print('wait: no ship came in range within %.0f s, not pressing' % lim)
        sys.exit(2)
    judge()

if 'lock' in args:
    lock_nearest()
for _ in range(slot):
    press([{'buttons': ['Right'], 'frames': 5}, {'frames': 20}])
if 'probe' in args:
    for b in ('Down', 'Right', 'Left', 'Y', 'X'):
        if try_button(b):
            print('USE INPUT = %s (request counter moved)' % b)
            break
        time.sleep(1.0)
    else:
        print('no candidate moved the request counter: run "validate" first (Up must move it); if Up moves it '
              'and nothing else does, the HKS refuses the Transmitter use (state/area) [I]')
else:
    n = try_button(btn)
    if 'validate' in args:
        print('reader OK' if n else 'reader NOT validated: Up gave no request (stake count 0? HP full is fine)')
    elif not n:
        print('no item-use request: wrong input or the use animation was refused; try "probe"')
