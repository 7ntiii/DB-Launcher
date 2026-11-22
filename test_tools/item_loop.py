"""item_loop.py USER OTHER [steps N] [tag T]  -- TEST ONLY: use every quick item of USER once and judge its effect on
BOTH games (row 53-other: Memorial Stake and other items). Written 2026-11-16 (helper 3) for runitem.sh. Not run yet.

Per step (step 0 = the quick item shown now; every later step first presses Right once = "Switch Quick Item"):
  1. USER's HP is lowered to 60 % of its max (TEST ONLY write of the master HP, hp.py) so a heal can show;
  2. before: USER's inventory (pgd+0x2E8, rewards.py layout), USER's HP on its own game and the HP of USER's chr
     copy on OTHER, and the active effect nodes (emote.py walker: [[chr+0x20]+0x90]) of USER's chr on BOTH games;
  3. use_item.py USER <0|1> (Down; the request counter [[main+0x59E1B28]]+0x2180 must move);
  4. after 3 s: the same reads.
  The item = the inventory entry whose count fell by 1 on USER's game. An effect node is told by the first 0x40
  bytes of its param row (the same data on both games, unlike its address).
Verdict per item, ONE line "RESULT item_<goods> <PASS|FAIL|NOT JUDGED> ...":
  PASS        count -1 AND the effect shows on BOTH games: (a) a new effect row on USER's chr on its own game AND the
              same row (same bytes) new on OTHER's copy, or (b) HP up on USER's game AND on OTHER's copy (>= 10 each).
  FAIL        count -1 and the effect shows on USER's game only (a or b on one game): not shared.
  NOT JUDGED  count -1 but no readable effect on either game (an item whose effect has no reader here, e.g. a
              planted Memorial Stake or a thrown item with no target): human card.
  (a step with no request / no count change gives "RESULT slot<k> NOT JUDGED no use" and the loop goes on).
The loop ends when an item already judged comes round again (the quick slots cycled) or after N steps (default 8).
At the end USER's HP is topped up to its max again (also on any error).

runitem 15:43 fix (2026-11-16): all 16 slots gave "requests +0". The rig characters start Phase I with NO quick
item: the inventory held only goods 510 / 520 / 530 / 1000 / 3000, the weapons and the stakes. Down is the right
input: the Fire Flask proof (handoff 1257) used use_item.py's Down, and "the picked-up flask sits in quick slot 1 by
itself". So now:
  collect K (default 6): before the loop, USER takes the K nearest untaken world items through the REAL pick-up
      (item_sources.world_items, goto 1.5 m facing it, Y; positions validated), then prints what it gained.
  HP baseline: HP is lowered and read again 4 s later with no input. In the 15:43 run HP came back to full between
      steps (natural regain). If it rises with no item, the HP criterion is off and only effect rows count.
  The loop stops after 2 steps in a row with no use (the quick slots are empty)."""
import math
import struct
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402

GDM_G = 0x5B57EB8      # regress_small.py GDM_G: [GDM+0x20] = local pgd
WCM_G = 0x5B3CD88
EFFECT_SYNC = 0x59E1B28


def arg(k, d=None):
    a = sys.argv
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


USER, OTHER = sys.argv[1], sys.argv[2]
STEPS = int(arg('steps', 8))
TAG = arg('tag', '')
u, o = W(USER), W(OTHER)


def say(s):
    print('%s %s' % (time.strftime('%H:%M:%S'), s), flush=True)


def result(name, verdict, text):
    print('RESULT %s %s | %s' % (name, verdict, text), flush=True)


def pgd_of_chr(w, c):
    d = w.q(c + 0x20) if c else None
    return w.q(d + 0x1D0) if d else None


def my_no():
    p = pgd_of_chr(u, u.player_entry(0)[0])
    return u.i(p + 0xD0) if p else None


def chr_by_no(w, no):
    for e in w.players(12):
        p = pgd_of_chr(w, e[0])
        if p and w.i(p + 0xD0) == no:
            return e[0]
    return None


def inventory(w):
    g = w.g(GDM_G)
    pgd = w.q(g + 0x20) if g else None
    if not pgd:
        return {}
    inv = pgd + 0x2E8
    n1, total = w.d(inv + 0x2FC), (w.d(inv + 0x368) or 0) + 1
    a1, a2 = w.q(inv + 0x330), w.q(inv + 0x320)
    out = {}
    if n1 is None or total > 4096:
        return out
    for i in range(total):
        base = (a1 + i * 16) if i < n1 else ((a2 or 0) + (i - n1) * 16)
        if not base:
            continue
        b = w.rd(base, 16)
        if not b:
            continue
        w0, w1, cnt = struct.unpack_from('<III', b, 0)
        if w0:
            out[(w0, w1)] = cnt
    return out


def effects(w, c):
    """set of row fingerprints (first 0x40 bytes of the param row) of the chr's effect nodes; None = unreadable"""
    data = w.q(c + 0x20) if c else None
    mgr = w.q(data + 0x90) if data else None
    if not mgr:
        return None
    out, seen = set(), set()
    node, outer = w.q(mgr + 8), mgr + 8
    for _ in range(256):
        n = 0
        while node and node not in seen and n < 512:
            seen.add(node)
            row = w.q(node + 0x80)
            b = w.rd(row, 0x40) if row else None
            if b:
                out.add(b.hex())
            node = w.q(node + 0x88)
            n += 1
        outer = w.q(outer + 0x18) if outer else None
        if not outer:
            break
        node = w.q(outer)
    return out


def own_hp():
    e = u.player_entry(0)
    if not e or not e[3]:
        return None, None, None
    p = pgd_of_chr(u, e[0])
    return u.i(e[3] + 0xF30), (u.i(p + 0xC) if p else None), e[3]


def set_hp(frac):
    hp, mx, e3 = own_hp()
    if hp is None or mx is None or not 0 < mx <= 100000 or hp <= 0:
        return 'HP %s / %s: not changed' % (hp, mx)
    want = max(1, int(mx * frac))
    u.write(e3 + 0xF30, struct.pack('<i', want))
    return 'HP %s -> %s of %s' % (hp, u.i(e3 + 0xF30), mx)


def snap(no):
    cu = u.player_entry(0)[0]
    co = chr_by_no(o, no)
    return {'inv': inventory(u), 'hp_u': own_hp()[0], 'hp_o': o.chr_hp(co) if co else None,
            'fx_u': effects(u, cu), 'fx_o': effects(o, co) if co else None, 'co': co}


def finite(p):
    return bool(p) and len(p) == 3 and all(isinstance(v, float) and math.isfinite(v) and abs(v) < 1e5 for v in p)


def collect(k):
    """REAL pick-up of the k nearest untaken world items (MapItemMan lists; flags 0x4000 = taken). -> text"""
    import item_sources as IS
    import tctl
    before = inventory(u)
    tried, picks = set(), []
    for _ in range(k):
        here = u.me()[2]
        if not finite(here):
            picks.append('own position not valid: stop')
            break
        rows = [r for r in IS.world_items(u) if finite(r['pos']) and not (r['flags'] or 0) & 0x4000
                and r['a'] not in tried]
        if not rows:
            picks.append('no untaken world item left')
            break
        r = min(rows, key=lambda x: math.dist(here, x['pos']))
        tried.add(r['a'])
        inv0 = inventory(u)
        u.goto_front(r['pos'], 1.5, 0.3, nudge=True)
        time.sleep(0.8)
        tctl.call(USER, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['Y'], 'frames': 8},
                                                                          {'buttons': [], 'frames': 50}]}})
        time.sleep(4.0)
        inv1 = inventory(u)
        got = ['%s +%d' % (goods(kk), c - inv0.get(kk, 0)) for kk, c in inv1.items() if c > inv0.get(kk, 0)]
        picks.append('item %s at %.0f m: %s' % (r['id'], math.dist(here, r['pos']), ', '.join(got) or 'nothing'))
    after = inventory(u)
    gained = ['%s +%d' % (goods(kk), c - before.get(kk, 0)) for kk, c in after.items() if c > before.get(kk, 0)]
    return gained, picks


def goods(key):
    return '%d' % (key[0] & 0x0FFFFFFF)


def main():
    no = my_no()
    if not no:
        sys.exit('%s: no player number' % USER)
    if not chr_by_no(o, no):
        sys.exit('%s: no copy of player %s' % (OTHER, no))
    s0 = snap(no)
    say('%s (player %s) inventory: %s' % (USER, no, ', '.join('%s x%d' % (goods(k), c) for k, c in s0['inv'].items())))
    judged = set()
    gained, picks = collect(int(arg('collect', 6)))
    say('pick-ups: %s' % ' | '.join(picks))
    say('gained: %s' % (', '.join(gained) or 'NOTHING (no item to use)'))
    # HP baseline: does HP come back with no item at all?
    say('HP baseline: %s' % set_hp(0.6))
    h0 = own_hp()[0]
    time.sleep(4.0)
    h1 = own_hp()[0]
    hp_valid = h0 is not None and h1 is not None and h1 - h0 < 5
    say('HP baseline: %s -> %s in 4 s with no input: HP criterion %s' % (
        h0, h1, 'ON' if hp_valid else 'OFF (HP comes back by itself; effect rows only)'))
    empty_run = 0
    try:
        for step in range(STEPS):
            say('step %d: %s' % (step, set_hp(0.6)))
            time.sleep(1.0)
            b = snap(no)
            p = subprocess.run([sys.executable, 'diag/twin/use_item.py', USER, '1' if step else '0'],
                               capture_output=True, text=True, timeout=60)
            req = next((ln.strip() for ln in p.stdout.splitlines() if '-> Down: requests' in ln), 'no request line')
            time.sleep(3.0)
            a = snap(no)
            used = [k for k, c in b['inv'].items() if a['inv'].get(k, 0) == c - 1]
            if not used:
                result('%sslot%d' % (TAG, step), 'NOT JUDGED', 'no use: no inventory count fell (%s)' % req)
                empty_run += 1
                if empty_run >= 2:
                    say('two steps in a row with no use: the quick slots are empty, loop ends')
                    break
                continue
            empty_run = 0
            key = used[0]
            if key in judged:
                say('item %s came round again: the quick slots cycled, loop ends' % goods(key))
                break
            judged.add(key)
            new_u = (a['fx_u'] or set()) - (b['fx_u'] or set()) if a['fx_u'] is not None else None
            new_o = (a['fx_o'] or set()) - (b['fx_o'] or set()) if a['fx_o'] is not None else None
            fx_both = bool(new_u) and bool(new_o) and bool(new_u & new_o)
            fx_one = bool(new_u) or bool(new_o)
            dhu = (a['hp_u'] or 0) - (b['hp_u'] or 0)
            dho = (a['hp_o'] or 0) - (b['hp_o'] or 0)
            hp_both = hp_valid and dhu >= 10 and dho >= 10
            hp_one = hp_valid and (dhu >= 10 or dho >= 10)
            text = ('%s x%d -> x%d (%s) | new effect rows: %s %s, %s %s, shared %s | HP %s %s -> %s, %s copy %s -> %s' % (
                goods(key), b['inv'][key], a['inv'].get(key, 0), req,
                USER, '?' if new_u is None else len(new_u), OTHER, '?' if new_o is None else len(new_o),
                len(new_u & new_o) if new_u and new_o else 0,
                USER, b['hp_u'], a['hp_u'], OTHER, b['hp_o'], a['hp_o']))
            if fx_both or hp_both:
                verdict = 'PASS'
                text = 'effect on BOTH games (%s) | %s' % ('effect row' if fx_both else 'HP', text)
            elif fx_one or hp_one:
                verdict = 'FAIL'
                text = 'effect on ONE game only (not shared) | %s' % text
            else:
                verdict = 'NOT JUDGED'
                text = 'used, but no readable effect on either game (human card) | %s' % text
            result('%sitem_%s' % (TAG, goods(key)), verdict, text)
    finally:
        say('end: %s' % set_hp(1.0))


if __name__ == '__main__':
    main()
