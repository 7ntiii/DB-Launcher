"""TEST ONLY - NEVER SHIP. Row 50 (blood drain on an enemy), one reliable run with one verdict line.
python diag/twin/drain_test.py WHO [games=AB] [enemy=0x<chr on WHO>] [seconds=360] [lowhp=1]
Notes: diag/net/drain_notes.md (the game code behind every field). Static work 2026-11-16, py_compile only.

What it does:
 1. Checks that nothing refills WHO's HP: the no-dead bit u16 [[chr+0x2470]+0x18]+0x4A0 bit 2 and the debug byte
    main+0x5B84290 (nodeath.py) must both be clear, now and at every check (else SKIP: run nodeath.py WHO off).
 2. Picks the enemy (unless enemy= is given): an EnemyIns in WHO's chr sync sets, loaded (entry flags 5), alive,
    model family with a drain throw (ThrowParam 1000<family>00, strike.DRAIN_FAMILIES), stagger gauge max > 0
    (NpcParam u16 +0x378 -> [[chr+0x2470]+0xC0]+0x10), DRIVEN BY WHO (assist owner flag >= 0, strike.hp_owner), nearest
    first, within 40 m.
 3. lowhp=1 (default): ONE write of WHO's own HP to 60 % of its current value (master [entry0+0x18]+0xF30, as
    hp.py), so the drink's heal can show. Nothing else ever writes WHO's HP.
 4. Each cycle (strike.py's validated pieces, imported: Placer ground test, Pin, lower_hp):
    - pin: strike.Pin on the driver (WHO) holds the enemy at its own position during the cycle (writes f32 x y z to
      [[chr+0x2470]+0xE8]+0x70 every 10 ms on WHO only);
    - place WHO 1.0 m from the enemy, facing it (Placer: player position / yaw writes, maxjump 60 m, ground test);
    - burst: the hit type that fills the gauge fastest. The first 4 cycles try R x3 and ZR held 40 (2 each) and
      measure the gauge drop per second; the faster one is used from then on. The gauge refills to max 2 s
      after the last hit (0x17409A8), so a burst is kept under 1.6 s and cycles follow at once;
    - HP floor: when the enemy's HP on the driver is below 50 % of max, write max back (strike.lower_hp, read back
      after 0.5 s). Only on the driver, never on another game.
 5. A watcher thread (own debug connection, reads only) polls the gauge every 20 ms. STAGGER = the gauge was below
    max and is back at max while its hit timer is still running (> 1.5 s of 2.0), which only the break path does
    (0xDE3CC4: current <= 0 -> broke byte, current = max, timer = 2.0); the timer-out refill leaves the timer at 0.
    The toughness module ([[chr+0x2470]+0xC8], broken byte +0x30) is watched too (families with NpcParam +0x1A0 > 0).
    On STAGGER the main loop presses R twice at once (R near a staggered enemy = Drink blood, fmg 18013000; the
    throw ThrowParam 1000<fam>00: within 1.8 m, WHO facing the enemy within 90 deg, height within 1.8 m).
 6. Verdict: PASS = WHO's HP rose while the no-dead bit / switch stayed clear, AND the enemy's friendly-group module
    ([[chr+0x2470]+0x280]+0x18+8*slot -> +0x1C == 1, slot = WHO's pgd+0x104) shows WHO's slot on EVERY game.
    PARTIAL = one of the two. FAIL = stagger seen but no drink, or no stagger in the time. SKIP = no usable enemy /
    nodeath on / WHO's HP below 25 %.
Writes (all TEST ONLY): WHO's player position / yaw (Placer, re-validated before every write, put back on exit),
the enemy's physics position on the game that DRIVES it now (Pin, at that copy's own position, only while loaded),
the enemy's HP on the driver (floor: only when 0 < HP < 50 % of max), WHO's own HP (lowhp=1: once down, restored
to the start value at every exit). Review 2026-11-16: a heal counts only in a cycle with a drink press and above
the measured passive regeneration; Trespassers, kins, Bloodsacs, immune families (cavalry 2100-2103 ...) and max
HP >= 3000 are refused, also for enemy=; the 6-minute cap includes setup.
v2 (2026-11-16, after the live "no hit landed in 71 cycles" on a c2140 21 m away): candidates sorted c2000 family
first, nearest first; kill.py's exact attack (1.5 m off, 0.3 m up, facing, one StickR lock-on per target, R 5/25
frames per call, 3 per cycle) through the validated Placer; every cycle prints CONNECT (enemy HP fell on any game or
the gauge moved) or miss; 3 misses in a row or 60 s -> the next target; the first stagger -> R R at once and the
verdict; no pin, no ZR; total cap 5 minutes.
v3 (2026-11-17): attack probe (R, ZR charged, ZR, ZL, L; 2 one-press cycles each) until one lowers the stagger
gauge, then that input only; HP floor on the driver BEFORE every cycle (< 70 % -> max, validated); presses per
cycle sized so one burst cannot kill from the floor; no stagger = NOT JUDGED (exit 3), FAIL only for a stagger
without a drink.
Exactly one line starts with "DRAIN_TEST ". Exit 0 PASS, 1 FAIL/PARTIAL, 2 SKIP, 3 NOT JUDGED."""
import math
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import strike as S  # noqa: E402
from world_lib import W, ENEMY_VT  # noqa: E402
import tctl  # noqa: E402

NODEATH_BYTE = 0x5B84290       # debug "no dead" byte (nodeath.py)
SA_SLOT, TOUGH_SLOT, FG_SLOT = 0xC0, 0xC8, 0x280
TRES_MGR = 0x5B3CD90           # Trespasser manager: +8 vector of instances, ins +0xC0 id; chr key = id >> 16
MAX_HP_OK = 3000               # review: larger = great foe / Trespasser candidate (trespassers.py 'foes'): refused
T_START = time.time()          # review: the 6-minute cap counts from the start, setup included


class Usage(Exception):
    pass


def opts(argv):
    if len(argv) < 2:
        print(__doc__)
        raise Usage('no WHO given')
    o = {'games': tctl.GAMES, 'enemy': '', 'seconds': 300.0, 'lowhp': 1}
    for a in argv[2:]:
        k, eq, v = a.partition('=')
        if k not in o or not eq:
            raise Usage('unknown option %s' % a)
        try:
            o[k] = float(v) if k == 'seconds' else int(v) if k == 'lowhp' else v
        except ValueError:
            raise Usage('bad value %s' % a)
    who = argv[1].upper()
    if who not in o['games']:
        o['games'] = who + o['games']
    o['seconds'] = min(o['seconds'], 300.0)                  # v2: the 5-minute cap
    return who, o


def tres_keys(w):
    """chr keys ([chr+0x20]+0x78 low 16) of every Trespasser instance (trespassers.py's reading), read only"""
    keys = set()
    m = w.g(TRES_MGR)
    lo, hi = (w.q(m + 8), w.q(m + 0x10)) if m else (None, None)
    if lo and hi and lo <= hi and (hi - lo) // 8 <= 64:
        for a in range(lo, hi, 8):
            ins = w.q(a)
            iid = w.d(ins + 0xC0) if ins else None
            if iid:
                keys.add(iid >> 16)
    return keys


def chr_key(w, c):
    p = w.q(c + 0x20)
    v = w.d(p + 0x78) if p else None
    return None if v is None else v & 0xFFFF


def gauge(w, c):
    """stagger gauge [[chr+0x2470]+0xC0]: (max +0x10, current +0x14, hit timer +0x18, lock +0x20) and the toughness
    module [[chr+0x2470]+0xC8]: (value +0x20, broken byte +0x30, latched +0x31)"""
    bag = w.q(c + 0x2470)
    sa = w.q(bag + SA_SLOT) if bag else None
    to = w.q(bag + TOUGH_SLOT) if bag else None
    r = w.rd(sa + 0x10, 0x14) if sa else None
    t = w.rd(to + 0x20, 0x14) if to else None
    g = {'max': None, 'cur': None, 'timer': None, 'lock': None, 'tough': None, 'tbroken': None}
    if r:
        g['max'], g['cur'], g['timer'] = struct.unpack_from('<3f', r, 0)
        g['lock'] = struct.unpack_from('<i', r, 0x10)[0]
    if t:
        g['tough'] = struct.unpack_from('<f', t, 0)[0]
        g['tbroken'] = t[0x10] | t[0x11]
    return g


def nodeath_on(w):
    """the two things nodeath.py sets: no-dead bit 2 of u16 [[chr+0x2470]+0x18]+0x4A0, debug byte main+0x5B84290"""
    me = S.player(w)
    bag = w.q(me['chr'] + 0x2470) if me else None
    dmod = w.q(bag + 0x18) if bag else None
    fl = w.h(dmod + 0x4A0) if dmod else None
    db = w.b(w.base + NODEATH_BYTE)
    if fl is None or db is None:
        return True, 'unreadable (flags %s, byte %s)' % (fl, db)
    return bool(fl & 4) or db != 0, 'no-dead bit %d, debug byte %d' % ((fl >> 2) & 1, db)


class Watch(threading.Thread):
    """reads only: polls the gauge every 20 ms on its own debug connection and records STAGGER events"""

    def __init__(self, who, c):
        super().__init__(daemon=True)
        self.w, self.c = W(who), c
        self.stop = threading.Event()
        self.events, self.low, self.err = [], None, None
        self.hit = threading.Event()

    def run(self):
        prev = None
        while not self.stop.is_set():
            try:
                g = gauge(self.w, self.c)
            except Exception as e:  # noqa: BLE001
                self.err = str(e)
                return
            if g['cur'] is not None and g['max']:
                self.low = g['cur'] if self.low is None else min(self.low, g['cur'])
                if prev and prev['cur'] is not None and prev['cur'] < g['max'] - 0.01 and \
                        g['cur'] >= g['max'] - 0.01 and (g['timer'] or 0) > 1.5:
                    self.events.append((time.time(), 'gauge broke (%.1f -> %.1f, timer %.2f)' % (
                        prev['cur'], g['cur'], g['timer'])))
                    self.hit.set()
            if g['tbroken'] and not (prev and prev['tbroken']):
                self.events.append((time.time(), 'toughness broken (+0x30/+0x31 %s)' % g['tbroken']))
                self.hit.set()
            prev = g
            time.sleep(0.02)


def pick(G, who, o, far=None):
    """(list of (chr, text), how) or (None, why). far (a list): filled with (dist, chr, family, pos) of enemies that
    pass every filter except 'over 40 m' / 'not loaded' and lie within FAR_M (driven by WHO, finite position)"""
    w = G[who]
    me = S.player(w)
    if not me or not S.finite3(me['pos']):
        return None, 'WHO player position unreadable'
    sm = S.sync_map(w)
    km = S.kin_map(w)
    tk = tres_keys(w)

    def why_bad(c, own):
        """review 2026-11-16: the same filters for a given enemy= as for the search (it skipped all of them):
        EnemyIns, not a kin, not a Trespasser, not a Bloodsac (flag or family 2130), a family WITH the drain throw
        (cavalry 2100/2101/2103 and the other immune families are not in DRAIN_FAMILIES), max HP below 3000,
        loaded, alive, finite, within 40 m, gauge max > 0, driven by WHO"""
        if w.q(c) != w.base + ENEMY_VT:
            return 'not an EnemyIns'
        if c in km:
            return 'kin'
        if chr_key(w, c) in tk:
            return 'Trespasser'
        t = S.target(w, c, 'auto', sm=sm, km=km)
        if not t or t['gone'] or not t['loaded'] or not S.finite3(t['pos']):
            return 'not loaded / dead / position bad'
        fam = S.family(t['behav'])
        if t['sac'] or t['sac'] is None or fam == 2130:
            return 'Bloodsac (or its flag unreadable)'
        if fam not in S.DRAIN_FAMILIES:
            return 'no drain throw (family %s)' % fam
        if not t['max'] or t['max'] >= MAX_HP_OK:
            return 'max HP %s (great foe / Trespasser size)' % t['max']
        if S.d3(t['pos'], me['pos']) > 40.0:
            return 'over 40 m'
        if not (gauge(w, c)['max'] or 0) > 0:
            return 'gauge max 0'
        if own is None or own < 0:
            return 'driven elsewhere'
        return None

    def far_ok(c, own):
        """the same filters as why_bad without the 40 m / loaded / gauge ones (a far copy has no live gauge)"""
        if own is None or own < 0 or w.q(c) != w.base + ENEMY_VT or c in km or chr_key(w, c) in tk:
            return None
        t = S.target(w, c, 'auto', sm=sm, km=km)
        if not t or t['gone'] or not S.finite3(t['pos']):
            return None
        fam = S.family(t['behav'])
        if t['sac'] or t['sac'] is None or fam == 2130 or fam not in S.DRAIN_FAMILIES:
            return None
        if not t['max'] or t['max'] >= MAX_HP_OK:
            return None
        d = S.d3(t['pos'], me['pos'])
        return (d, c, fam, tuple(t['pos'])) if d <= FAR_M else None

    if o['enemy']:
        try:
            c = int(o['enemy'], 16)
        except ValueError:
            return None, 'enemy= %s is not hex' % o['enemy']
        if not S.is_chr(w, c):
            return None, 'enemy= %x is not a chr on %s' % (c, who)
        h = w.d(c + 8)
        hit = sm.get(h)
        why = why_bad(c, hit[1] if hit and hit[0] == c else None)
        return ([(c, 'given')], 'given') if not why else (None, 'enemy= %x refused: %s' % (c, why))
    cands, why_not = [], {}
    for h, (c, own, addr) in sm.items():
        why = why_bad(c, own)
        if why in ('over 40 m', 'not loaded / dead / position bad') and far is not None:
            fd = far_ok(c, own)
            if fd:
                far.append(fd)
        if why:
            k = why.split(' (')[0]
            why_not[k] = why_not.get(k, 0) + 1
            continue
        t = S.target(w, c, 'auto', sm=sm, km=km)
        cands.append((S.d3(t['pos'], me['pos']), c, S.family(t['behav']), t['hp'], t['max']))
    if not cands:
        return None, 'no drainable enemy within 40 m driven by %s (%s)' % (who, why_not or 'none near')
    # v2: the c2000 family first (the ordinary foes kill.py reliably hits), then any other drain family; nearest first
    cands.sort(key=lambda r: (r[2] not in C2000, r[0]))
    return [(c, 'c%s at %.1f m, HP %s/%s' % (fam, d, hp, mx)) for d, c, fam, hp, mx in cands],         '%d candidates (refused: %s)' % (len(cands), why_not)


FAR_M, LOAD_WAIT = 150.0, 25.0     # travel: farthest enemy, seconds to wait for it to load after the trip


def travel(w, c, deadline):
    """validated trip to a far enemy chr c driven by WHO: strike.Placer ground test (16 sides, drift / slide
    checks, player put back on failure) at 3 m from it with maxjump FAR_M + 5, two tries 2 s apart (collision
    streaming in); then wait LOAD_WAIT s for entry flags 5 and gauge max > 0. On any failure the player goes back
    to the start spot. (ok, text)"""
    me = S.player(w)
    if not me or not S.finite3(me['pos']) or not me['hp'] or me['hp'] <= 0:
        return False, 'WHO unreadable / dead'
    pl = S.Placer(w, me, {'posfrom': 'auto', 'dist': 3.0, 'dy': 0.5, 'tol': 0.8, 'maxjump': FAR_M + 5.0})
    why = pl.player_ok()
    if why:
        return False, why
    start, start_yaw = pl.ref, pl.ref_yaw

    def home(txt):
        if S.d3(pl.ref, start) > 0.5:
            pl.ref = start
            ok = pl.write_player(start, start_yaw)
            txt += '; put back at %s%s' % (S.f3s(start), '' if ok else ' REFUSED')
        return False, txt

    r = None
    for k in range(2):
        if time.time() > deadline - 70:
            return False, 'no time left for the trip'
        t = S.target(w, c, 'auto')
        if not t or t['gone'] or not S.finite3(t['pos']):
            return False, 'target gone before the trip'
        if S.d3(t['pos'], start) > FAR_M:
            return False, 'target now %.0f m away' % S.d3(t['pos'], start)
        r, _ = pl.find(t['pos'], 3.0, 0.0)
        if r:
            break
        time.sleep(2.0)
    if not r:
        return False, 'no ground spot near it (player put back)'
    print('travel: at %s, %.1f m from 0x%x%s' % (S.f3s(r['p']), S.d3(r['p'], t['pos']), c,
                                                ' (rough side)' if r.get('rough') else ''), flush=True)
    t_end = min(time.time() + LOAD_WAIT, deadline - 60)
    while time.time() < t_end:
        t = S.target(w, c, 'auto')
        if not t or t['gone']:
            return home('target died / gone after the trip')
        why = pl.player_ok()
        if why:
            return False, 'player after the trip: ' + why
        p = w.f3(pl.phys + 0x70)
        if not S.finite3(p) or p[1] < pl.ref[1] - 5.0:
            return home('player falling after the trip (%s)' % S.f3s(p))
        if t['loaded'] and (gauge(w, c)['max'] or 0) > 0:
            return True, 'travelled %.0f m to 0x%x, loaded in %.0f s' % (
                S.d3(start, p), c, LOAD_WAIT - (t_end - time.time()))
        time.sleep(0.5)
    return home('0x%x not loaded %.0f s after the trip (%s)' % (c, LOAD_WAIT, t['loaded_why'] if t else '?'))


C2000 = {2000, 2010, 2011, 2020}   # c2000-type families (ThrowParam 1000<fam>00 present); c2140 is drainable too
KILL_R = [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]                    # kill.py's press, one call each
LOCK = [{'buttons': ['StickR'], 'frames': 4}, {'frames': 10}]                  # kill.py's lock-on
PER_TARGET, MISS_LIMIT, PRESSES = 60.0, 3, 3
# v3 (2026-11-17, after the live "gauge low 100.0" in every connecting cycle: R hits took HP but never counted on
# the stagger gauge). 0xDE3AFC counts a hit only when its per-hit slot byte [dmg+idx*0xB4+0x50] == 8 (set by the
# attack, not by the target), so the attack TYPE decides. The tool now probes each input below (2 cycles of ONE
# press each) and keeps the first that lowers the gauge; R is kept for the drink only.
ATTACKS = [
    ('R', [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]),
    ('ZR charged', [{'buttons': ['ZR'], 'frames': 45}, {'frames': 35}]),
    ('ZR', [{'buttons': ['ZR'], 'frames': 6}, {'frames': 35}]),
    ('ZL', [{'buttons': ['ZL'], 'frames': 6}, {'frames': 35}]),
    ('L', [{'buttons': ['L'], 'frames': 6}, {'frames': 35}]),
]
PROBE_CYCLES = 2               # cycles per attack type while probing
FLOOR_FRAC = 0.7               # HP floor on the driver BEFORE every cycle: below 70 % of max -> max
DRINK = [{'buttons': ['R'], 'frames': 4}, {'frames': 8}, {'buttons': ['R'], 'frames': 4}, {'frames': 40}]


def own_hp_write(w, chr0, value):
    """review: WHO's own master HP (+0xF30), only on the same live player chr and only a value inside 1..start"""
    e = w.player_entry(0)
    if not e or e[0] != chr0 or not e[3]:
        return 'player chr changed (death / load): no own-HP write'
    cur = w.i(e[3] + 0xF30)
    if cur is None or cur <= 0:
        return 'player HP %s: no own-HP write' % cur
    if not 0 < value < 100000:
        return 'value %s out of range' % value
    w.write(e[3] + 0xF30, struct.pack('<i', int(value)))
    return None


def main(verdict, st):
    who, o = opts(sys.argv)
    st['who'] = who
    G = {}
    for g in o['games']:
        try:
            G[g] = W(g)
        except Exception as e:  # noqa: BLE001
            # review: every listed game is required: PASS says "friendly group on EVERY game"
            verdict[:] = ['SKIP', '%s has no debug server (%s)' % (g, e), '']
            return
    w = G[who]
    deadline = T_START + o['seconds'] - 8.0          # review: whole run inside the cap, room for the last checks
    nd, ndtxt = nodeath_on(w)
    if nd:
        verdict[1] = 'nodeath is on (%s): the HP test would be void; run  python diag/twin/nodeath.py %s off' % (
            ndtxt, who)
        return
    far = []
    cands, how = pick(G, who, o, far)
    if not cands and far and not o['enemy']:
        # 2026-11-16: nothing usable within 40 m -> travel (validated) to the nearest far one WHO drives, max 2 tries
        far.sort()
        tlog = []
        for d, c, fam, pos in far[:2]:
            print('no target within 40 m (%s): travel to 0x%x c%s at %.0f m' % (how, c, fam, d), flush=True)
            ok, txt = travel(w, c, deadline)
            tlog.append('0x%x c%s %.0f m: %s' % (c, fam, d, txt))
            print('travel: ' + tlog[-1], flush=True)
            if ok:
                cands, how2 = pick(G, who, o)
                if cands:
                    how = '%s; %s' % (txt, how2)
                    break
                tlog.append('after the trip: %s' % how2)
        if not cands:
            verdict[1] = '%s; travel: %s' % (how, ' | '.join(tlog))
            return
    if not cands:
        verdict[1] = how if far or o['enemy'] else how.replace('within 40 m', 'within 40 m (none within 150 m either)')
        return
    print('candidates: %s' % '; '.join('0x%x %s' % ch for ch in cands[:8]), flush=True)
    # v2: kill.py's geometry: 1.5 m off, 0.3 m above the target's height, facing it (Placer: validated sides)
    o2 = {'posfrom': 'auto', 'dist': 1.5, 'dy': 0.3, 'tol': 0.5, 'maxjump': 60.0}
    me = S.player(w)
    if not me or not S.finite3(me['pos']) or not me['hp'] or me['hp'] <= 0:
        verdict[1] = 'WHO player unreadable / dead'
        return
    pl = S.Placer(w, me, o2)
    why = pl.player_ok()                             # review: own position sources agree before any write
    if why:
        verdict[1] = why
        return
    st['pl'] = pl
    slot = S.my_slot(w)
    log = ['%s; my slot %s' % (how, slot)]
    hp_start = me['hp']
    if o['lowhp'] and hp_start > 100:
        why = own_hp_write(w, me['chr'], int(hp_start * 0.6))
        if why:
            verdict[1] = why
            return
        st['restore_hp'] = (me['chr'], hp_start)     # review: put back at every exit
        time.sleep(0.5)
        log.append('TEST ONLY own HP %s -> %s (master +0xF30)' % (hp_start, (S.player(w) or {}).get('hp')))
        print(log[-1], flush=True)
    # review: passive regeneration baseline (3 s, no input): a rise has to beat it to count as the drink
    h_a = (S.player(w) or {}).get('hp')
    time.sleep(3.0)
    h_b = (S.player(w) or {}).get('hp')
    regen = max(0.0, (h_b - h_a) / 3.0) if h_a is not None and h_b is not None else None
    if regen is None:
        verdict[1] = 'WHO HP unreadable during the regeneration check'
        return
    log.append('passive regeneration %.1f HP/s (3 s, no input)' % regen)
    print(log[-1], flush=True)
    t0 = time.time()
    n, drink_tries, floor_writes, tried, connects = 0, 0, 0, [], 0
    probe = {'k': 0, 'chosen': None, 'presses': 1, 'none': False, 'stats': {}}
    events_all = []
    for c, chow in cands:
        if time.time() > deadline - 10:
            break
        vs = S.views(G, who, c, o2)
        t = vs.get(who)
        if not t or t['gone'] or not t['loaded'] or not S.finite3(t['pos']):
            tried.append('0x%x gone / unloaded before the start' % c)
            continue
        fg0 = {g: S.fg_slots(G[g], v['chr']) if v else None for g, v in vs.items()}
        g0 = gauge(w, c)
        print('target 0x%x %s: gauge max %s, toughness %s, fg before %s' % (c, chow, g0['max'], g0['tough'], fg0),
              flush=True)
        watch = Watch(who, c)
        watch.start()
        st['watch'] = watch
        t_tgt, misses, locked, hits_here, rose = time.time(), 0, False, 0, None
        why_left = 'time per target (%.0f s) used' % PER_TARGET
        try:
            while time.time() - t_tgt < PER_TARGET and time.time() < deadline:
                n += 1
                nd, ndtxt = nodeath_on(w)
                if nd:
                    verdict[:] = ['SKIP', 'nodeath turned on during the run (%s)' % ndtxt, '']
                    return
                vs = S.views(G, who, c, o2)
                t = vs.get(who)
                if not t or t['gone']:
                    why_left = 'died / freed'
                    break
                if not t['loaded'] or not S.finite3(t['pos']):
                    why_left = 'unloaded'
                    break
                chrs = {g: v['chr'] for g, v in vs.items() if v}
                me = S.player(w)
                if not me or me['hp'] is None or me['hp'] <= 0:
                    verdict[:] = ['FAIL', 'WHO player unreadable / dead after %d cycles' % n, '']
                    return
                if me['hp'] < 0.25 * hp_start:
                    verdict[:] = ['SKIP', 'WHO HP %s below 25 %% of the start: stopped before a death' % me['hp'], '']
                    return
                hp_c0, tc0, drank = me['hp'], time.time(), False
                tpos0 = tuple(t['pos'])

                def still_ok(tpos0=tpos0):
                    tt = S.target(w, c, 'auto', sm={}, km={})
                    if not tt or tt['gone']:
                        return 'enemy died / freed'
                    if not tt['loaded']:
                        return 'enemy unloaded (%s)' % tt['loaded_why']
                    if not S.finite3(tt['pos']) or S.d3(tt['pos'], tpos0) > 2.0:
                        return 'enemy moved to %s' % S.f3s(tt['pos'])
                    return None
                pl.check = still_ok
                res, _tries = pl.find(t['pos'], o2['dist'], math.degrees(math.atan2(
                    t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2])))
                if not res:
                    misses += 1
                    print('%5.1f s #%d 0x%x: no ground beside it (miss %d)' % (time.time() - t0, n, c, misses),
                          flush=True)
                    if misses >= MISS_LIMIT:
                        why_left = '%d cycles without a connecting swing' % misses
                        break
                    continue
                if not locked:                                 # kill.py: one StickR lock-on per target
                    time.sleep(0.5)
                    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': LOCK}})
                    locked = True
                # v3: HP floor BEFORE the burst (enemies died inside one 3-press cycle), driver only, validated
                auth0, _ = S.hp_owner(G, vs)
                dv0 = vs.get(auth0) if auth0 else None
                if (dv0 and dv0['loaded'] and not dv0['gone'] and S.finite3(dv0['pos']) and dv0['max']
                        and dv0['hp'] is not None and 0 < dv0['hp'] < FLOOR_FRAC * dv0['max']):
                    if S.lower_hp(G, [auth0], chrs, dv0['max'], up=True):
                        floor_writes += 1
                    vs = S.views(G, who, c, o2)
                if probe['chosen']:
                    typ, steps, npress = probe['chosen'], dict(ATTACKS)[probe['chosen']], probe['presses']
                else:
                    typ, steps = ATTACKS[min(probe['k'] // PROBE_CYCLES, len(ATTACKS) - 1)]
                    npress = 1
                    probe['k'] += 1
                ev0 = len(watch.events)
                hp0 = {g: v['hp'] for g, v in vs.items() if v}
                low0 = watch.low
                for _ in range(npress):
                    if watch.hit.is_set():
                        break
                    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': steps}})
                if watch.hit.is_set():                         # the first stagger: drink at once
                    watch.hit.clear()
                    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': DRINK}})
                    drink_tries += 1
                    drank = True
                    time.sleep(1.5)
                vs = S.views(G, who, c, o2)
                chrs.update({g: v['chr'] for g, v in vs.items() if v})
                hp1 = {g: v['hp'] for g, v in vs.items() if v}
                g2 = gauge(w, c)
                hp_drop = any(hp0.get(g) is not None and hp1.get(g) is not None and hp1[g] < hp0[g] for g in hp1)
                g_moved = watch.low is not None and (low0 is None or watch.low < low0 - 0.01) or \
                    len(watch.events) > ev0
                conn = hp_drop or g_moved
                sx = probe['stats'].setdefault(typ, {'cycles': 0, 'hp': 0, 'gauge': 0, 'dmg': []})
                sx['cycles'] += 1
                sx['hp'] += 1 if hp_drop else 0
                sx['gauge'] += 1 if g_moved else 0
                if hp_drop:
                    sx['dmg'] += [hp0[g] - hp1[g] for g in hp1 if hp0.get(g) is not None and hp1.get(g) is not None
                                  and hp1[g] < hp0[g]][:1]
                if g_moved and not probe['chosen']:
                    # the first input that lowers the gauge: keep it; presses per cycle so one burst cannot kill
                    # from the floor (FLOOR_FRAC * max) with the damage measured so far
                    d = max(sx['dmg']) if sx['dmg'] else 0
                    mx = (vs.get(who) or {}).get('max') or 0
                    probe['chosen'] = typ
                    probe['presses'] = max(1, min(PRESSES, int((FLOOR_FRAC * mx - 1) // d) if d else PRESSES))
                    print('   ATTACK CHOSEN: %s lowers the stagger gauge (damage per hit %s, %d press(es) per cycle)' % (
                        typ, d or '?', probe['presses']), flush=True)
                elif not probe['chosen'] and probe['k'] >= PROBE_CYCLES * len(ATTACKS):
                    probe['chosen'], probe['presses'], probe['none'] = 'R', 1, True
                    print('   no input lowered the stagger gauge in %d probe cycles: %s' % (
                        probe['k'], probe['stats']), flush=True)
                misses = 0 if conn or not probe['chosen'] else misses + 1
                hits_here += 1 if conn else 0
                connects += 1 if conn else 0
                me = S.player(w)
                hp_c1 = me['hp'] if me else None
                print('%5.1f s #%d 0x%x | %s | enemy hp %s -> %s | gauge now %s / %s (low %s) timer %.2f | tough %s | '
                      'my hp %s -> %s | events %d drinks %d' % (
                          time.time() - t0, n, c, '%s %s' % (typ, 'CONNECT' if conn else 'miss %d' % misses), hp0,
                          hp1, g2['cur'],
                          g2['max'], watch.low, g2['timer'] or 0, g2['tough'], hp_c0, hp_c1, len(watch.events),
                          drink_tries), flush=True)
                # review: HP floor on the driver only, only when 0 < HP < 50 % of ITS max
                auth, awhy = S.hp_owner(G, vs)
                dv = vs.get(auth) if auth else None
                if (dv and dv['loaded'] and not dv['gone'] and dv['max'] and dv['hp'] is not None
                        and 0 < dv['hp'] < 0.5 * dv['max']):
                    if S.lower_hp(G, [auth], chrs, dv['max'], up=True):
                        floor_writes += 1
                # review: a rise counts only in a cycle with a drink press and above the passive regeneration
                if hp_c1 is not None:
                    dt = max(0.5, time.time() - tc0)
                    gain = hp_c1 - hp_c0
                    need = max(5.0, 0.02 * hp_start, 3.0 * regen * dt)
                    if not drank and gain > 0:
                        regen = max(regen, gain / dt)
                    elif drank and gain > need and rose is None:
                        rose = (hp_c0, hp_c1, n)
                if drank:                                      # the first stagger decides: judge now
                    time.sleep(2.0)                            # let the 0x91 group record reach the others
                    vs = S.views(G, who, c, o2)
                    fg = {g: S.fg_slots(G[g], v['chr']) if v else None for g, v in vs.items()}
                    joined = {g: bool(f and slot in f) for g, f in fg.items()}
                    nd, ndtxt = nodeath_on(w)
                    hp_ok = rose is not None and not nd
                    fg_ok = all(joined.get(g) for g in G)
                    vals = 'target 0x%x %s | rose %s, regen %.1f/s, nodeath %s | fg before %s now %s | events %s | ' \
                           'tried %s | %s' % (c, chow, rose, regen, ndtxt, fg0, fg, [e[1] for e in watch.events],
                                             tried, '; '.join(log))
                    if hp_ok and fg_ok:
                        verdict[:] = ['PASS', 'stagger, then the drink: HP %s -> %s (above regen) with nodeath off, '
                                      'the enemy in slot %s friendly group on %s' % (rose[0], rose[1], slot,
                                                                                    ''.join(G)), vals]
                    elif hp_ok or any(joined.values()):
                        verdict[:] = ['PARTIAL', 'stagger + drink press: HP rose above regen %s, friendly group %s' % (
                            hp_ok, joined), vals]
                    else:
                        verdict[:] = ['FAIL', 'stagger seen (%s), R R pressed at once, but no heal and no friendly '
                                      'group' % watch.events[-1][1] if watch.events else 'stagger', vals]
                    return
                if misses >= MISS_LIMIT:
                    why_left = '%d cycles in a row without a connecting swing' % misses
                    break
        finally:
            watch.stop.set()
            watch.join(1.0)
            events_all += [e[1] for e in watch.events]
            pl.check = None
        tried.append('0x%x %s: %s (%d connecting cycles, gauge low %s)' % (c, chow, why_left, hits_here, watch.low))
        print('next target: %s' % tried[-1], flush=True)
    why = ('no input lowered the stagger gauge (probe %s)' % probe['stats'] if probe['none'] else
           'no stagger within the 5-minute cap (%d cycles, %d connecting, %d target(s), attack %s)' % (
               n, connects, len(tried), probe['chosen']) if connects else
           'no swing connected on any target (%d cycles, %d target(s))' % (n, len(tried)))
    verdict[:] = ['NOT JUDGED', why + ': the drain-ready (staggered) state was never reached, so the drink was '
                  'not tested', 'tried %s | events %s | floor writes %d | regen %.1f/s | probe %s | %s' % (
                      tried, events_all, floor_writes, regen, probe['stats'], '; '.join(log))]


def run():
    """review 2026-11-16: exactly one "DRAIN_TEST" line on every path (usage error, exception, Ctrl+C), and every
    exit restores: watcher stopped, a test side put back, WHO's own HP back to its start value (same chr, alive)"""
    verdict = ['SKIP', 'not started', '']
    st = {}
    try:
        main(verdict, st)
    except Usage as e:
        verdict[:] = ['SKIP', 'usage: %s' % e, '']
    except BaseException as e:  # noqa: BLE001  (KeyboardInterrupt too)
        verdict[:] = ['FAIL', 'stopped by %s: %s' % (type(e).__name__, e), verdict[2]]
    finally:
        notes = []
        try:
            if st.get('watch'):
                st['watch'].stop.set()
                st['watch'].join(1.0)
            pl = st.get('pl')
            if pl and pl.trial:
                pl.back()
                notes.append('player put back' if not pl.trial else 'player NOT put back')
            if st.get('restore_hp'):
                chr0, hp0 = st['restore_hp']
                why = own_hp_write(W(st['who']), chr0, hp0)
                notes.append('own HP restored to %s' % hp0 if not why else 'own HP NOT restored: %s' % why)
        except Exception as e:  # noqa: BLE001
            notes.append('cleanup error %s' % e)
        if notes:
            print('cleanup: %s' % '; '.join(notes), flush=True)
    print('DRAIN_TEST %s %s: %s | %s' % (verdict[0], st.get('who', '?'), verdict[1], verdict[2]), flush=True)
    return {'PASS': 0, 'SKIP': 2, 'NOT JUDGED': 3}.get(verdict[0], 1)


if __name__ == '__main__':
    sys.exit(run())
