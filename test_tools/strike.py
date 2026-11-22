"""TEST ONLY - NEVER SHIP. Land real hits on ONE chosen chr (enemy, Bloodsac, kin) and finish it, hands-free.
Notes: diag/net/strike_notes.md (fields, evidence, recipes). Static work: written 2026-11-15/16, never run.

python diag/twin/strike.py WHO TARGET probe [games=AB] [ground=1]       read-only diagnosis (ground=1: see below)
python diag/twin/strike.py WHO TARGET [mode=R|ZR|item|drain] [options]   fight
python diag/twin/strike.py WHO sacs [n=12] [ground=1 k=5]               Bloodsacs WHO knows: driver per game,
          loaded, HP, gap between the games' copies; ground=1 also runs the ground test at the k nearest usable
          ones (writes WHO's player position only, back at the start after each). Pick "drv = WHO: GOOD".
DRIVER: the game whose copy carries the assist's owner flag >= 0 (sync set +0x18, s16 per entry; dusk_lan.cpp
  EnemyOwners: each game sets +1 / -1 on its OWN copy every 250 ms, nearest living player wins with a 3 m margin;
  kin always go to the summoner's game). It is re-read every cycle; pin=driver and finish= / keephp= act on it.

  WHO     the game whose local player attacks (A, B, C)
  TARGET  hex chr address (as item_sources.py sacs / npcs.py / kinstate.py print it on WHO) or a handle (chr+8,
          u32, the same on every game for map enemies); force the reading with c:0x... or h:0x...

Options (defaults in brackets):
  mode=R        R: `presses` light attacks (R 5 frames down, 25 up) [R]; ZR: ZR held `hold` frames then 40 idle
                (charged strong attack when long enough [I]); item: quick item (D-pad Down, as use_item.py) thrown
                from `itemdist` m, no lock-on; the throw is confirmed by the item-use request counter
                [[main+0x59E1B28]]+0x2180 (+1 per use, use_item.py DETECTOR [V])
                drain: ZR held `hold` frames, then R x2 at once (draintry.py cycle: R drinks a staggered enemy
                [V fmg 18013000], else it is one more gauge-filling hit); the drink is detected by the target
                joining WHO's friendly group (credit.py 'fg': [[chr+0x2470]+0x280]+0x18+8*slot -> +0x1C == 1,
                slot = WHO's pgd+0x104) and the run then stops with DRAIN SEEN (exit 0)
  keephp=0      TEST ONLY: 1 = after every burst write the target's HP back to its max on the HP-owner game (read
                back as finish=), so a weak c2000 does not die before it staggers (for mode=drain)
  presses=3 hold=40 dist=0.9 itemdist=3.0 dy=0.1 (player y above the target's y at the spot)
  seconds=120   give up after this long
  tol=0.5       ground test: the player must stay within tol m (3D) of the spot 0.3 s after the teleport and move
                less than 0.25 m in the next 0.15 s; else the next side is tried (45 deg steps, then a closer ring)
  maxjump=60    every written position must lie within this many m of the last known-good player position
  pin=0         hold the target still while a cycle (ground test + burst) runs: 0 off; driver (= auth): on the game
                that drives it NOW, at that copy's own current position (no teleport); or explicit games (A, B, AB)
                at WHO's view. Writes, on each pin game, 12 bytes f32 x y z to the target's OWN physics position
                [[chr+0x2470]+0xE8]+0x70 of that game's copy (found by handle), about every 10 ms, in a thread
                with its own debug connection. Refused when that game's copy is more than 5 m from WHO's view.
  freeze=       TEST ONLY engine debug byte "GameData.AllNoMove" main+0x5B84548 = 1 on these games for the run,
                restored at the end (catch_notes.md 1; stops EVERY enemy of that game)
  finish=0      after the first real hit lower the target's HP (data module +0x290) to this value on the HP-owner
                game; the write is read back after 0.5 s; if the game put it back, the other games are tried and
                the one that keeps it is used from then on. 0 = never write HP (real damage only)
  forcefinish=1 allow finish= on a kin (refused by default: a kin's HP write only kills it on one game, handoff)
  nodeath=1     TEST ONLY no-dead bit on WHO's player for the run (nodeath.py bit mode; cleared at the end)
  side=         first side in degrees (spot = target - dist*(sin a, cos a); default: the side the player is on)
  posfrom=auto  target position: auto = the physics module [[chr+0x2470]+0xE8]+0x70 when the chr-set entry's
                physics ([chr+0x18]+0x28) is the same object or within 1 m; bag / entry force one (printed always)
  games=        games to look at for HP owner / pin / finish [env TWIN_GAMES or AB]

Safety (every write is checked first; the tool refuses and writes nothing for that step otherwise):
  - target loaded: chr-set entry [chr+0x18] points back to chr and its flags byte (+0x10) is 5 (2 = far: positions
    stale / nan); a kin must also be in BuddyManager state 3 (Summon); [[chr+0x2470]+0x18]+8 == chr;
  - every position written (player spot, pin position, restore) is finite, |x|,|y|,|z| < 20000, within maxjump m
    of the last known-good player position (start: where the player stands), and a spot is within dist+0.01 m of
    a validated target position; a target that jumps more than 30 m between two reads is not followed;
  - when no side passes the ground test the player is put back to the last known-good position and the burst is
    skipped; 3 such cycles in a row end the run (exit 4).
ground=1 with probe: runs only the ground test (writes the PLAYER's position / yaw only, then writes the start
position and yaw back). Without ground=1 the probe writes nothing at all.

Output: one line per burst: absolute positions (player, spot, target on WHO and on the pin/HP game), HP on WHO and
on the HP-owner game before -> after, HIT / miss, last attacker = me?, throw requests, pin writes.
Exit: 0 target dead (or freed after a hit), 1 time-out, 2 bad target / refused, 4 no ground / target out of reach.
Run from the workspace root."""
import math
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, ENEMY_VT, WCM_G  # noqa: E402
import tctl  # noqa: E402

ROLE = 0x492AFD8           # 0 = host / offline, 1 = guest (credit.py, treasures.py)
ALL_NO_MOVE = 0x5B84548    # "GameData.AllNoMove" (catch_notes.md 1) [V]
EFFECT_SYNC = 0x59E1B28    # [[main+0x59E1B28]]+0x2180 item-use request counter (use_item.py) [V]
DRAIN_FAMILIES = {2000, 2010, 2011, 2020, 2070, 2071, 2090, 2140, 2150, 2160, 2161, 2170, 2180, 2190}  # catch 3
NO_DRAIN = {2040, 2050, 2080, 2081, 2100, 2101, 2103, 2110, 2120, 2121, 2130}
KIN_STATES = {0: 'Init', 1: 'ResLoad', 2: 'Unsummon', 3: 'Summon', 4: 'RequestUnsummon', 5: 'RequestForceUnsummon',
              6: 'FadeoutForceUnsummon', 7: 'DeadAnim', 8: 'FinishUnsummon', 9: 'WaitRevive'}


# ---------------------------------------------------------------- small helpers
REREAD_WAIT = 10.0     # s: a '(?)' player / target is waited for and re-resolved by handle, not refused


def finite3(p):
    return p is not None and len(p) == 3 and all(math.isfinite(x) and abs(x) < 20000.0 for x in p)


def f3s(p):
    return '(%.2f %.2f %.2f)' % tuple(p) if p is not None and len(p) == 3 else '(?)'


def d3(a, b):
    return math.dist(a, b) if finite3(a) and finite3(b) else float('inf')


def dh(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2]) if finite3(a) and finite3(b) else float('inf')


def opts(argv):
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    o = {'mode': 'R', 'presses': 3, 'hold': 40, 'dist': 0.9, 'itemdist': 3.0, 'dy': 0.1, 'seconds': 120.0,
         'tol': 0.5, 'maxjump': 60.0, 'pin': '0', 'freeze': '', 'finish': 0, 'forcefinish': 0, 'nodeath': 0,
         'side': None, 'posfrom': 'auto', 'games': tctl.GAMES, 'probe': 0, 'ground': 0, 'keephp': 0, 'sacs': 0,
         'n': 12, 'k': 5}
    strs = ('mode', 'pin', 'freeze', 'posfrom', 'games')
    floats = ('dist', 'itemdist', 'dy', 'seconds', 'tol', 'maxjump', 'side')
    for a in argv[3:]:
        if a == 'probe':
            o['probe'] = 1
            continue
        k, eq, v = a.partition('=')
        if k not in o or not eq:
            sys.exit('unknown option %s' % a)
        o[k] = v if k in strs else (float(v) if k in floats else int(v))
    o['mode'] = o['mode'].upper() if o['mode'].upper() in ('R', 'ZR') else o['mode'].lower()
    if o['mode'] not in ('R', 'ZR', 'item', 'drain'):
        sys.exit('mode must be R, ZR, item or drain')
    if o['posfrom'] not in ('auto', 'bag', 'entry'):
        sys.exit('posfrom must be auto, bag or entry')
    who = argv[1].upper()
    if who not in o['games']:
        o['games'] = who + o['games']
    t = argv[2].lower()
    if t == 'sacs':
        o['sacs'] = 1
        return who, 0, None, o
    kind = None
    if t.startswith('c:') or t.startswith('h:'):
        kind, t = t[0], t[2:]
    return who, int(t, 16), kind, o


# ---------------------------------------------------------------- readers (all null-safe, read only)
def sync_map(w):
    """{handle u32: (chr, own flag s16)} from the chr sync sets WCM+0x540 (credit.py / zeppelin.owner_flag):
    own >= 0 = this game drives the chr, -1 = remote [V dusk_lan.cpp EnemyOwners]"""
    out = {}
    wcm = w.g(WCM_G)
    sm = w.q(wcm + 0x540) if wcm else None
    n = w.d(sm + 8) if sm else None
    if not n or n > 16:
        return out
    for i in range(n):
        s = w.q(sm + 0x10 + 8 * i)
        if not s:
            continue
        cnt, cs, own = w.d(s + 0x10), w.q(s + 8), w.q(s + 0x18)
        first = w.q(cs + 8) if cs else None
        if not first or not cnt or cnt > 4096 or not own:
            continue
        raw = w.big(first, 0x38 * cnt)
        ownraw = w.rd(own, 2 * cnt)
        if not raw or not ownraw:
            continue
        for j in range(cnt):
            c = struct.unpack_from('<Q', raw, 0x38 * j)[0]
            if c:
                h = w.d(c + 8)
                if h is not None:
                    out[h] = (c, struct.unpack_from('<h', ownraw, 2 * j)[0], own + 2 * j)
    return out


def own_now(w, addr):
    """the assist's per-entry owner flag (s16 at sync set +0x18 [+2*j]): >= 0 this game drives the chr. It is the
    only record of ownership in game memory: dusk_lan.cpp EnemyOwners writes it on each game for its own copy
    (+1 taken / -1 left) every 250 ms; who the OTHER game is lives only in the assist (enemy_claims), so the driver
    is found by reading this flag on every game."""
    v = w.rd(addr, 2) if addr else None
    return struct.unpack('<h', v)[0] if v else None


def kin_map(w):
    """{chr: (owner player no, summon state)} from BuddyManager [[WCM+0x5B8]+0x10] (kinstate.py)"""
    out = {}
    wcm = w.g(WCM_G)
    x = w.q(wcm + 0x5B8) if wcm else None
    bm = w.q(x + 0x10) if x else None
    if not bm:
        return out
    node, k = w.q(bm + 0x18), 0
    while node and node != bm + 0x10 and k < 16:
        c = w.q(node + 0x10)
        cd = w.q(c + 0x20) if c else None
        st = w.q(node + 0x30)
        if c:
            out[c] = (w.i(cd + 0xB8) if cd else None, w.d(st + 0x50) if st else None)
        node, k = w.q(node + 8), k + 1
    return out


def is_chr(w, c):
    bag = w.q(c + 0x2470)
    dmod = w.q(bag + 0x18) if bag else None
    return bool(dmod) and w.q(dmod + 8) == c


def my_no(w):
    e = w.player_entry(0)
    data = w.q(e[0] + 0x20) if e and e[0] else None
    pgd = w.q(data + 0x1D0) if data else None
    return w.i(pgd + 0xD0) if pgd else None


def resolve(w, value, kind=None, handle_hint=None, owner_hint=None):
    """chr address on w for TARGET (chr or handle), or None"""
    if kind != 'h' and value > 0x10000 and is_chr(w, value):
        return value
    if kind == 'c':
        return None
    h = value & 0xFFFFFFFF if handle_hint is None else handle_hint
    sm = sync_map(w)
    if h in sm:
        return sm[h][0]
    km = kin_map(w)
    for c in km:
        if w.d(c + 8) == h:
            return c
    if owner_hint is not None:                   # a kin may carry a different handle per game [I]
        for c, (owner, _) in km.items():
            if owner == owner_hint:
                return c
    for _, _, c in w.all_chrs():
        if w.d(c + 8) == h:
            return c
    return None


def target(w, c, posfrom='auto', sm=None, km=None):
    """everything about chr c on game w, or None when it is not a chr any more"""
    bag = w.q(c + 0x2470)
    dmod = w.q(bag + 0x18) if bag else None
    if not dmod or w.q(dmod + 8) != c:
        return None
    r = {'chr': c, 'vt': w.q(c), 'handle': w.d(c + 8), 'dmod': dmod}
    hp = w.rd(dmod + 0x290, 8)
    r['hp'], r['max'] = struct.unpack('<2i', hp) if hp else (None, None)
    r['flags'] = w.h(dmod + 0x4A0)
    r['phys_bag'] = w.q(bag + 0xE8)
    r['pos_bag'] = w.f3(r['phys_bag'] + 0x70) if r['phys_bag'] else None
    ent = w.q(c + 0x18)
    e = w.rd(ent, 0x38) if ent else None
    e = struct.unpack('<7Q', e) if e else None
    r['entry_ok'] = bool(e and e[0] == c)
    r['eflags'] = e[2] & 0xFF if r['entry_ok'] else None
    r['phys_e'] = e[5] if r['entry_ok'] else None
    r['pos_e'] = w.f3(e[5] + 0x70) if r['entry_ok'] and e[5] else None
    m2 = e[6] if r['entry_ok'] else None
    dv = w.b(m2 + 0x18) if m2 else None
    r['dead'] = None if dv is None else dv & 1
    data = w.q(c + 0x20)
    holder = w.q(data + 0xE8) if data else None
    row = w.q(holder + 8) if holder else None
    fl = w.b(row + 0x4EE) if row else None
    r['sac'] = None if fl is None else bool(fl & 8)
    r['behav'] = w.i(row + 4) if row else None
    la = w.d(data + 0x114) if data else None
    r['lastatk'] = None if la is None else la & 0xFFFF
    st32 = w.d(c + 0x12C5)
    r['hbit'] = None if st32 is None else (st32 >> 25) & 1
    sm = sync_map(w) if sm is None else sm
    hit = sm.get(r['handle'])
    r['own'], r['own_addr'] = (hit[1], hit[2]) if hit and hit[0] == c else (None, None)
    km = kin_map(w) if km is None else km
    r['kin'] = km.get(c)
    # position source
    pb, pe = r['pos_bag'], r['pos_e']
    same = r['phys_bag'] and r['phys_bag'] == r['phys_e']
    r['same_phys'] = bool(same)
    if posfrom == 'bag':
        r['pos'], r['pos_why'] = (pb, 'forced bag') if finite3(pb) else (None, 'bag position not finite')
    elif posfrom == 'entry':
        r['pos'], r['pos_why'] = (pe, 'forced entry') if finite3(pe) else (None, 'entry position not finite')
    elif not finite3(pb):
        r['pos'], r['pos_why'] = None, 'physics position [[chr+0x2470]+0xE8]+0x70 not finite (%s)' % f3s(pb)
    elif same or pe is None or d3(pb, pe) <= 1.0:
        r['pos'], r['pos_why'] = pb, 'bag+0xE8 (%s)' % ('same object as entry' if same else
                                                       'no entry physics' if pe is None else
                                                       'entry within %.2f m' % d3(pb, pe))
    else:
        r['pos'], r['pos_why'] = None, 'bag %s and entry %s disagree by %.1f m: use posfrom=' % (
            f3s(pb), f3s(pe), d3(pb, pe))
    # loaded verdict
    why = []
    if not r['entry_ok']:
        why.append('chr-set entry [chr+0x18] does not point back')
    elif r['eflags'] != 5:
        why.append('entry flags %s (5 = loaded / simulated, 2 = far)' % r['eflags'])
    if r['kin'] is not None and r['kin'][1] != 3:
        why.append('kin state %s %s (need 3 Summon)' % (r['kin'][1], KIN_STATES.get(r['kin'][1], '?')))
    if r['pos'] is None:
        why.append(r['pos_why'])
    r['loaded_why'] = '; '.join(why)
    r['loaded'] = not why
    r['gone'] = (r['hp'] is not None and r['hp'] <= 0) or bool(r['dead'])
    return r


def player(w):
    """local player: chr, physics (chr-set entry 0 +0x28: kill.py / goto write its +0x70 / +0x64), pos, yaw"""
    e = w.player_entry(0)
    if not e or not e[0] or not e[5]:
        return None
    c, phys = e[0], e[5]
    bag = w.q(c + 0x2470)
    data = w.q(c + 0x20)
    h = w.d(data + 0x78) if data else None
    return {'chr': c, 'phys': phys, 'pos': w.f3(phys + 0x70), 'yaw': w.f(phys + 0x64),
            'phys_bag': w.q(bag + 0xE8) if bag else None, 'handle': None if h is None else h & 0xFFFF,
            'hp': w.i(e[3] + 0xF30) if e[3] else None}


def my_slot(w):
    e = w.player_entry(0)
    data = w.q(e[0] + 0x20) if e and e[0] else None
    pgd = w.q(data + 0x1D0) if data else None
    return w.b(pgd + 0x104) if pgd else None


def fg_slots(w, c):
    """player slots whose friendly group holds chr c (credit.friendly_groups), or None"""
    bag = w.q(c + 0x2470)
    fg = w.q(bag + 0x280) if bag else None
    raw = w.rd(fg + 0x18, 96) if fg else None
    if not raw:
        return None
    return {g for g, s in enumerate(struct.unpack('<12Q', raw)) if s and w.b(s + 0x1C) == 1}


def throw_counter(w):
    h = w.g(EFFECT_SYNC)
    mgr = w.q(h) if h else None
    return w.d(mgr + 0x2180) if mgr else None


def family(behav):
    return behav // 10 if behav and behav > 1000 else None


# ---------------------------------------------------------------- authority (HP owner) guess
def views(G, who, c, o):
    """{game: target dict or None} for WHO's chr c, found on the other games by handle (kin: by owner no)"""
    t0 = target(G[who], c, o['posfrom'])
    out = {who: t0}
    if not t0:
        return out
    owner = t0['kin'][0] if t0['kin'] else None
    for g, w in G.items():
        if g == who:
            continue
        cg = resolve(w, t0['handle'] or 0, 'h', t0['handle'], owner)
        out[g] = target(w, cg, o['posfrom']) if cg else None
    return out


def drivers_now(G, vs):
    """{game: (own flag, entry flags)} read NOW for every copy, and the list of games whose flag is >= 0.
    The flag is the assist's per-copy record (own_now); kin flags are forced to the summoner's game by the assist."""
    st, drv = {}, []
    for g, t in vs.items():
        if not t:
            continue
        own = own_now(G[g], t.get('own_addr'))
        ent = G[g].rd(G[g].q(t['chr'] + 0x18) or 0, 0x18) if t.get('chr') else None
        ef = ent[0x10] if ent else None
        st[g] = (own, ef)
        if own is not None and own >= 0:
            drv.append(g)
    return st, drv


def drv_str(st):
    return ' '.join('%s:%s/e%s' % (g, 'DRIVES' if o is not None and o >= 0 else ('-' if o is None else 'remote'), e)
                    for g, (o, e) in st.items())


def hp_owner(G, vs):
    """(game or None, reason): the game that drives the chr now (assist flag >= 0 on its copy). The game that
    drives an enemy runs its AI and sends its HP / status, so a write elsewhere is overwritten (live 2026-11-16:
    A wrote HP 1, reverted to 340, while B drove the sac). Two drivers (both games think their player is nearer,
    e.g. their copies are 10 m apart): the lower player number (assist tie rule), with a warning. None: nobody
    drives it at this moment (do not pin / finish; wait)."""
    st, drv = drivers_now(G, vs)
    if len(drv) == 1:
        return drv[0], '%s drives it (%s)' % (drv[0], drv_str(st))
    if len(drv) > 1:
        low = min(drv, key=lambda g: my_no(G[g]) or 99)
        return low, 'SEVERAL drive it (%s): copies disagree; using the lower player number %s' % (drv_str(st), low)
    return None, 'nobody drives it now (%s)' % drv_str(st)


def nearest_players(G, vs):
    """per game: distances from that game's copy of the target to every player chr it knows (entry 0 = own).
    This is what EnemyOwners compares (ours < theirs - 3 m takes it)."""
    out = {}
    for g, t in vs.items():
        if not t or not t['pos']:
            continue
        w = G[g]
        ds = []
        for k, e in enumerate(w.players()):
            p = w.f3(e[5] + 0x70) if e[5] else None
            if finite3(p):
                ds.append('%s%.1f' % ('own ' if k == 0 else 'p%d ' % k, d3(p, t['pos'])))
        out[g] = ' '.join(ds)
    return out


# ---------------------------------------------------------------- pin thread
class Pin(threading.Thread):
    """writes 12 bytes (f32 x y z) to [[chr+0x2470]+0xE8]+0x70 of game `g`'s copy every ~10 ms"""

    def __init__(self, g, chr_, pos):
        super().__init__(daemon=True)
        self.g, self.c, self.pos = g, chr_, tuple(pos)
        self.w = W(g)                                # own debug connection (fightfoe.HoldHP pattern)
        self.stop = threading.Event()
        self.writes, self.err = 0, None

    def run(self):
        if not finite3(self.pos):
            self.err = 'pin position not finite'
            return
        data = struct.pack('<3f', *self.pos)
        addr = None
        k = 0
        while not self.stop.is_set():
            try:
                if addr is None or k % 25 == 0:          # re-check every ~0.25 s that it is still the same live chr
                    # review 2026-11-16: 'auto' (both position sources must agree), the entry must point back AND
                    # carry flags 5 (an entry that does not point back = unloaded: was let through before), and the
                    # copy must still be near the pin position (a respawn / re-placement elsewhere ends the pin)
                    t = target(self.w, self.c, 'auto', sm={}, km={})
                    if (not t or t['gone'] or not t['phys_bag'] or not t['entry_ok'] or t['eflags'] != 5
                            or not finite3(t['pos']) or d3(t['pos'], self.pos) > 5.0):
                        self.err = 'target gone / unloaded / moved away on %s' % self.g
                        return
                    addr = t['phys_bag'] + 0x70
                self.w.write(addr, data)
                self.writes += 1
            except Exception as e:  # noqa: BLE001
                self.err = str(e)
                return
            k += 1
            time.sleep(0.01)


# ---------------------------------------------------------------- placement / ground test
class Placer:
    def __init__(self, w, me, o, check=None):
        self.w, self.phys, self.o = w, me['phys'], o
        self.chr = me['chr']
        self.ref = tuple(me['pos'])                  # last known-good player position
        self.ref_yaw = me['yaw'] if me['yaw'] is not None and math.isfinite(me['yaw']) else 0.0
        self.good = None                             # last side (deg) that passed
        self.check = check                           # review: callable -> None (target still fine) or a reason
        self.trial = False                           # a test side is written and not yet confirmed / put back

    def safe(self, p, what):
        if not finite3(p):
            return '%s %s not finite' % (what, f3s(p))
        if d3(p, self.ref) > self.o['maxjump']:
            return '%s %s is %.1f m from the last good player position %s (> maxjump %.0f)' % (
                what, f3s(p), d3(p, self.ref), f3s(self.ref), self.o['maxjump'])
        return None

    def player_ok(self):
        """review 2026-11-16: the physics object is re-read before EVERY write. After a death / respawn / load the
        entry's physics can be another object, and a write to the old address lands in freed memory. Also: the
        player is alive and its two position sources (entry +0x28 and [chr+0x2470]+0xE8) agree within 1 m."""
        me = self.refresh()
        if not me:
            return 'the local player is not readable for %.0f s' % REREAD_WAIT
        if me['hp'] is not None and me['hp'] <= 0:
            return 'the local player is dead (hp %s)' % me['hp']
        if not finite3(me['pos']):
            return 'the player position now reads %s' % f3s(me['pos'])
        if me['phys_bag'] and me['phys_bag'] != me['phys']:
            pb = self.w.f3(me['phys_bag'] + 0x70)
            if not finite3(pb) or d3(pb, me['pos']) > 1.0:
                return 'player position sources disagree: entry %s, bag %s' % (f3s(me['pos']), f3s(pb))
        return None

    def refresh(self, wait=None):
        """host run 2026-11-16: on the host a teleport of the local player can re-create the chr set (every address
        changes, 'me (?)'). Re-read the player entry 0 before EVERY read / write; while it is unreadable wait and
        re-read up to REREAD_WAIT s; adopt the new chr / physics object (never write to the old one)."""
        end = time.time() + (REREAD_WAIT if wait is None else wait)
        while True:
            me = player(self.w)
            if me and finite3(me['pos']):
                if me['chr'] != self.chr or me['phys'] != self.phys:
                    print('   player re-resolved: chr 0x%x -> 0x%x, physics 0x%x -> 0x%x, handle %s, at %s' % (
                        self.chr, me['chr'], self.phys, me['phys'],
                        '%04x' % me['handle'] if me['handle'] is not None else '?', f3s(me['pos'])), flush=True)
                    self.chr, self.phys = me['chr'], me['phys']
                return me
            if time.time() >= end:
                return None
            time.sleep(0.5)

    def pos(self):
        me = self.refresh()
        return me['pos'] if me else None

    def write_player(self, p, yaw):
        why = self.safe(p, 'player position') or self.player_ok()
        if why:
            print('   REFUSED write: %s' % why, flush=True)
            return False
        self.w.write(self.phys + 0x70, struct.pack('<3f', *p))
        if yaw is not None and math.isfinite(yaw):
            self.w.write(self.phys + 0x64, struct.pack('<f', yaw))
        return True

    def back(self):
        if self.write_player(self.ref, self.ref_yaw):
            self.trial = False

    def try_side(self, tpos, deg, dist):
        a = math.radians(deg)
        if not finite3(tpos):
            return None
        spot = (tpos[0] - dist * math.sin(a), tpos[1] + self.o['dy'], tpos[2] - dist * math.cos(a))
        if d3(spot, tpos) > dist + abs(self.o['dy']) + 0.01:
            return None
        if self.check:
            why = self.check()
            if why:
                print('   no side written: %s' % why, flush=True)
                return 'abort'
        if not self.write_player(spot, a):
            return None
        self.trial = True
        time.sleep(0.3)
        p1 = self.pos()                              # re-resolved after the write (host: chr set may be re-created)
        time.sleep(0.15)
        p2 = self.pos()
        drift, slide = d3(p1, spot), d3(p2, p1)
        ok = finite3(p2) and drift <= self.o['tol'] and slide <= 0.25
        return {'deg': deg % 360, 'dist': dist, 'spot': spot, 'p': p2, 'drift': drift, 'slide': slide, 'ok': ok,
                'yaw': a}

    def find(self, tpos, dist, start_deg, verbose=False):
        """ground test: 8 sides at dist, then 8 at 0.65 dist; returns the first passing side, a ROUGH best one,
        or None (player put back). Stops at once (player put back) when self.check reports the target unusable."""
        tries = []
        first = self.good if self.good is not None else start_deg
        for dd in (dist, max(0.5, dist * 0.65)):
            for k in (0, 1, -1, 2, -2, 3, -3, 4):
                r = self.try_side(tpos, first + 45 * k, dd)
                if r == 'abort':
                    self.back()
                    return None, tries
                if r is None:
                    continue
                tries.append(r)
                if verbose:
                    print('   ground side %3.0f deg dist %.2f: spot %s -> me %s drift %.2f slide %.2f %s' % (
                        r['deg'], dd, f3s(r['spot']), f3s(r['p']), r['drift'], r['slide'],
                        'OK' if r['ok'] else 'no'), flush=True)
                if r['ok']:
                    self.good = r['deg']
                    self.ref = tuple(r['p'])
                    self.trial = False
                    return r, tries
        best = min(tries, key=lambda r: r['drift'], default=None)
        if (best and best['drift'] <= 1.5 and dh(best['p'], tpos) <= best['dist'] + 0.8 and finite3(best['p'])
                and not (self.check and self.check())):
            # put the player back on the least-bad side for this burst
            if self.write_player(best['spot'], best['yaw']):
                time.sleep(0.3)
                p = self.pos()
                if finite3(p) and d3(p, best['spot']) <= 1.5:
                    best = dict(best, p=p, rough=True)
                    self.ref = tuple(p)
                    self.trial = False
                    return best, tries
        self.back()
        return None, tries


# ---------------------------------------------------------------- HP lowering with read-back
def lower_hp(G, order, chrs, value, up=False):
    """write value to data module +0x290 on the first game of `order` that keeps it; returns that game or None
    (up=True, keephp: 'kept' = HP above the value read before the write, 0.5 s later)"""
    for g in order:
        c = chrs.get(g)
        # review 2026-11-16: 'auto' + loaded (entry points back, flags 5, both position sources agree), and the value
        # inside (0, max]: no HP write on an unloaded / half-freed copy, never 0 or a negative / oversized value
        t = target(G[g], c, 'auto', sm={}, km={}) if c else None
        if not t or t['gone']:
            print('   %s: %s copy unreadable / dead: no HP write' % ('keephp' if up else 'finish', g))
            continue
        if not t['loaded']:
            print('   %s: %s copy not loaded (%s): no HP write' % ('keephp' if up else 'finish', g, t['loaded_why']))
            continue
        if not t['max'] or not 0 < value <= t['max']:
            print('   %s: %s value %s outside 1..max %s: no HP write' % ('keephp' if up else 'finish', g, value,
                                                                         t['max']))
            continue
        G[g].write(t['dmod'] + 0x290, struct.pack('<i', value))
        time.sleep(0.5)
        now = G[g].i(t['dmod'] + 0x290)
        kept = now is not None and (now > t['hp'] if up else now <= value)
        print('   %s: %s HP %s -> wrote %d -> %s after 0.5 s: %s' % (
            'keephp' if up else 'finish', g, t['hp'], value, now, 'KEPT' if kept else 'REVERTED'), flush=True)
        if kept:
            return g
    return None


# ---------------------------------------------------------------- probe
def probe(G, who, c, kind, o):
    w = G[who]
    if kind != 'h' and c > 0x10000 and is_chr(w, c):
        cw = c
    else:
        cw = resolve(w, c, kind)
    if not cw:
        print('%s: TARGET %x is neither a chr nor a known handle on %s' % (who, c, who))
        return 2
    vs = views(G, who, cw, o)
    for g, t in vs.items():
        wg = G[g]
        me = player(wg)
        print('== %s (role %s, local player no %s): player %s phys %s (bag+0xE8 %s: %s) handle %s hp %s' % (
            g, wg.b(wg.base + ROLE), my_no(wg), f3s(me['pos']) if me else '?', wg.rel(me['phys']) if me else '?',
            wg.rel(me['phys_bag']) if me else '?', 'same object' if me and me['phys'] == me['phys_bag'] else 'DIFFER',
            '%04x' % me['handle'] if me and me['handle'] is not None else '?', me['hp'] if me else '?'))
        if not t:
            print('   target: not found on %s' % g)
            continue
        fam = family(t['behav'])
        print('   target chr 0x%x vt %s handle %08x | hp %s/%s dead %s | Bloodsac %s | behav +0x04 %s (family c%s: '
              'drain %s [I]) | flags 0x%04x (b0 immortal %d b1 no-dmg %d b2 no-dead %d b4 no-dec %d)' % (
                  t['chr'], 'EnemyIns' if t['vt'] == wg.base + ENEMY_VT else wg.rel(t['vt']), t['handle'] or 0,
                  t['hp'], t['max'], t['dead'], t['sac'], t['behav'], fam,
                  'yes' if fam in DRAIN_FAMILIES else 'NO (immune)' if fam in NO_DRAIN else '?',
                  t['flags'] or 0, (t['flags'] or 0) & 1, (t['flags'] or 0) >> 1 & 1, (t['flags'] or 0) >> 2 & 1,
                  (t['flags'] or 0) >> 4 & 1))
        print('   positions: bag [[chr+0x2470]+0xE8]+0x70 %s (phys %s) | entry [chr+0x18]+0x28 %s (phys %s) | %s' % (
            f3s(t['pos_bag']), wg.rel(t['phys_bag']), f3s(t['pos_e']), wg.rel(t['phys_e']),
            'SAME object' if t['same_phys'] else 'different objects'))
        print('   loaded %s%s | entry flags %s | sync own %s (%s) | kin %s | last attacker %s%s | hit bit %s' % (
            'YES' if t['loaded'] else 'NO', '' if t['loaded'] else ' (%s)' % t['loaded_why'], t['eflags'], t['own'],
            'drives it' if t['own'] is not None and t['own'] >= 0 else 'remote' if t['own'] is not None else
            'not in sync sets', '-' if not t['kin'] else 'owner %s state %s %s' % (
                t['kin'][0], t['kin'][1], KIN_STATES.get(t['kin'][1], '?')),
            '%04x' % t['lastatk'] if t['lastatk'] is not None else '?',
            ' (= this player)' if me and t['lastatk'] == me['handle'] else '', t['hbit']))
        if t['pos'] and me and finite3(me['pos']):
            print('   target - player: horiz %.2f m, y %+.2f m (%s); position used: %s' % (
                dh(t['pos'], me['pos']), t['pos'][1] - me['pos'][1],
                'OK for maxjump' if d3(t['pos'], me['pos']) <= o['maxjump'] else
                'FARTHER than maxjump %.0f: goto first' % o['maxjump'], t['pos_why']))
    auth, why = hp_owner(G, vs)
    print('DRIVER (HP owner) now: %s (%s)' % (auth, why))
    for g, txt in nearest_players(G, vs).items():
        print('   %s: target copy to players: %s  (the assist gives it to the clearly nearest, 3 m margin)' % (g, txt))
    if auth != who:
        print('   NOTE %s does not drive it: hits still count, but pin / finish go to %s. Prefer a target %s drives '
              '(strike.py %s sacs), or move the other player(s) away so %s is clearly nearest.' % (
                  who, auth, who, who, who))
    if vs.get(who) and vs[who]['pos']:
        for g, t in vs.items():
            if g != who and t and t['pos']:
                print('views differ %s-%s: %.2f m' % (who, g, d3(t['pos'], vs[who]['pos'])))
    t = vs.get(who)
    me = player(w)
    if not o['ground']:
        print('ground test: not run (probe writes nothing). Run "probe ground=1" to test the sides '
              '(writes the player position only, then puts it back).')
        return 0
    if not t or not t['loaded'] or not me or not finite3(me['pos']):
        print('ground test REFUSED: target not loaded / player position not finite')
        return 2
    pl = Placer(w, me, o)
    why = pl.safe(t['pos'], 'target position')
    if why:
        print('ground test REFUSED: %s' % why)
        return 2
    start = o['side'] if o['side'] is not None else math.degrees(
        math.atan2(t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2]))
    dist = o['itemdist'] if o['mode'] == 'item' else o['dist']
    print('ground test (writes the player position / yaw only) around %s, dist %.2f:' % (f3s(t['pos']), dist))
    pl.good = None
    res, tries = Placer.find(pl, t['pos'], dist, start, verbose=True)
    print('ground result: %s' % ('side %.0f deg dist %.2f %s (drift %.2f)' % (
        res['deg'], res['dist'], 'ROUGH' if res.get('rough') else 'OK', res['drift']) if res else
        'NO side keeps the player within %.2f m (%d tries)' % (o['tol'], len(tries))))
    pl.ref, pl.ref_yaw = tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0
    pl.back()
    print('player put back to %s' % f3s(me['pos']))
    return 0


# ---------------------------------------------------------------- sacs list
def sacs(G, who, o):
    """Bloodsacs WHO knows (EnemyIns in the sync sets whose NpcParam row has +0x4EE bit 3), nearest first, with the
    driver on every game, the loaded flag, HP, and (ground=1) the ground test at the k nearest usable ones."""
    w = G[who]
    me = player(w)
    if not me or not finite3(me['pos']):
        print('%s: local player position not finite' % who)
        return 2
    sm = sync_map(w)
    km = kin_map(w)
    rows = []
    for h, (c, own, addr) in sm.items():
        if w.q(c) != w.base + ENEMY_VT:
            continue
        t = target(w, c, 'auto', sm=sm, km=km)
        if not t or not t['sac']:
            continue
        rows.append((d3(t['pos'], me['pos']) if t['pos'] else 1e9, t))
    rows.sort(key=lambda r: r[0])
    print('%s: player %s, Bloodsacs in the sync sets: %d (row +0x4EE bit 3)' % (who, f3s(me['pos']), len(rows)))
    other = {g: sync_map(G[g]) for g in G if g != who}
    tested = 0
    pl = Placer(w, me, o) if o['ground'] else None
    try:
        for k, (d, t) in enumerate(rows[:o['n']]):
            vs = {who: t}
            for g, smg in other.items():
                hit = smg.get(t['handle'])
                vs[g] = target(G[g], hit[0], 'auto', sm=smg, km={}) if hit else None
            auth, why = hp_owner(G, vs)
            gap = ' '.join('%s-%s %.1f m' % (who, g, d3(v['pos'], t['pos'])) for g, v in vs.items()
                           if g != who and v and v['pos'] and t['pos'])
            line = 'S%-2d chr 0x%x handle %08x hp %s/%s%s d=%.1f %s loaded %s | drv %s%s | %s' % (
                k, t['chr'], t['handle'] or 0, t['hp'], t['max'], ' DEAD' if t['gone'] else '', d, f3s(t['pos']),
                'yes' if t['loaded'] else 'NO(%s)' % t['loaded_why'], auth or 'NONE',
                ' = %s: GOOD' % who if auth == who else '', gap or 'no other copy')
            if pl and tested < o['k'] and t['loaded'] and not t['gone'] and not pl.safe(t['pos'], 'sac'):
                pl.good = None
                start = math.degrees(math.atan2(t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2]))
                res, tries = pl.find(t['pos'], o['dist'], start)
                line += ' | ground %s' % ('side %.0f %s drift %.2f' % (
                    res['deg'], 'ROUGH' if res.get('rough') else 'OK', res['drift']) if res else
                    'NONE (%d sides; best drift %.2f)' % (len(tries), min((r['drift'] for r in tries),
                                                                          default=float('nan'))))
                tested += 1
                pl.ref, pl.ref_yaw = tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0
                pl.back()                               # back to the start before the next sac
            print(line, flush=True)
    finally:
        if pl:
            pl.ref, pl.ref_yaw = tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0
            pl.back()
            print('%s: player put back to %s' % (who, f3s(me['pos'])))
    print('Pick: loaded yes, drv = %s (GOOD), ground OK, gap to the other copies under 2 m.' % who)
    return 0


# ---------------------------------------------------------------- fight
def burst_steps(o):
    if o['mode'] == 'ZR':
        return [{'buttons': ['ZR'], 'frames': o['hold']}, {'frames': 40}]
    if o['mode'] == 'item':
        return [{'buttons': ['Down'], 'frames': 6}, {'frames': 80}]
    if o['mode'] == 'drain':
        return [{'buttons': ['ZR'], 'frames': o['hold']}, {'frames': 20},
                {'buttons': ['R'], 'frames': 4}, {'frames': 8}, {'buttons': ['R'], 'frames': 4}, {'frames': 60}]
    s = []
    for _ in range(o['presses']):
        s += [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]
    return s


def fight(G, who, c, kind, o):
    w = G[who]
    end = time.time() + REREAD_WAIT                  # '(?)' at the start: wait and re-resolve, then refuse
    while True:
        cw = c if (kind != 'h' and c > 0x10000 and is_chr(w, c)) else resolve(w, c, kind)
        me = player(w)
        vs = views(G, who, cw, o) if cw else {}
        t = vs.get(who)
        if (cw and me and finite3(me['pos']) and t) or time.time() >= end:
            break
        time.sleep(0.5)
    if not cw:
        print('%s: TARGET %x is neither a chr nor a known handle (waited %.0f s)' % (who, c, REREAD_WAIT))
        return 2
    if not me or not finite3(me['pos']):
        print('%s: local player position not readable / not finite for %.0f s: refused' % (who, REREAD_WAIT))
        return 2
    print('%s: TARGET %x -> chr 0x%x handle %s; player chr 0x%x handle %s' % (
        who, c, cw, '%08x' % t['handle'] if t and t['handle'] is not None else '?', me['chr'],
        '%04x' % me['handle'] if me['handle'] is not None else '?'), flush=True)
    if not t or not t['loaded'] or t['gone']:
        print('%s: target not usable: %s' % (who, 'unreadable' if not t else t['loaded_why'] or 'already dead'))
        return 2
    pl = Placer(w, me, o)
    why = pl.player_ok()                             # review: own position sources agree before any write
    if why:
        print('%s: REFUSED: %s' % (who, why))
        return 2
    why = pl.safe(t['pos'], 'target position')
    if why:
        print('%s: REFUSED: %s (goto near it first, e.g. item_sources.py %s sacs positions)' % (who, why, who))
        return 2
    auth, awhy = hp_owner(G, vs)
    chrs = {g: v['chr'] for g, v in vs.items() if v}
    handle = t['handle']
    owner = t['kin'][0] if t['kin'] else None

    def find_target(label, wait=REREAD_WAIT):
        """host run 2026-11-16: never keep a chr address across a burst. Re-resolve WHO's copy and every other game's
        copy by handle; while WHO's copy is unreadable ('(?)') wait and retry up to `wait` s. None = still gone."""
        nonlocal cw
        if not handle:                               # no handle read: the old address is all there is
            return target(w, cw, o['posfrom'])
        end = time.time() + wait
        while True:
            c2 = resolve(w, handle, 'h', handle, owner)
            tt = target(w, c2, o['posfrom']) if c2 else None
            if tt:
                if c2 != cw:
                    print('   %s: target re-resolved by handle %08x: 0x%x -> 0x%x' % (label, handle, cw, c2), flush=True)
                cw = c2
                chrs[who] = c2
                for g, wg in G.items():
                    if g != who:
                        cg = resolve(wg, handle, 'h', handle, owner)
                        if cg:
                            chrs[g] = cg
                        else:
                            chrs.pop(g, None)
                return tt
            if time.time() >= end:
                return None
            time.sleep(0.5)

    print('%s: target 0x%x handle %08x hp %s/%s sac %s kin %s at %s (%s); HP owner %s (%s)' % (
        who, cw, t['handle'] or 0, t['hp'], t['max'], t['sac'], t['kin'], f3s(t['pos']), t['pos_why'], auth, awhy),
        flush=True)
    if o['finish'] and o['keephp']:
        print('%s: finish= and keephp=1 exclude each other: refused' % who)
        return 2
    if o['finish'] and t['kin'] and not o['forcefinish']:
        print('%s: finish= refused on a kin (forcefinish=1 to override): real damage only' % who)
        o['finish'] = 0
    pin_mode = o['pin'].lower()
    pin_fixed = '' if pin_mode in ('0', '', 'auth', 'driver') else o['pin'].upper()
    for g in pin_fixed:
        if g not in G:
            print('pin game %s has no debug connection: refused' % g)
            return 2
    slot = my_slot(w)
    fg0 = fg_slots(w, cw)
    if o['mode'] == 'drain':
        print('%s: drain mode: my slot %s, target friendly groups now %s' % (who, slot, sorted(fg0) if fg0 is not None
                                                                              else '?'), flush=True)
    finish_game = None
    nd_was = None
    frozen = {}
    rc = 1
    try:
        if o['nodeath']:
            import nodeath
            before, after = nodeath.set_nodeath(w, True, 'bit', quiet=True)
            if after is not None:
                nd_was = bool((before['flags'] or 0) & nodeath.NODEAD_BIT)
                print('%s: TEST ONLY no-dead bit on (was %s)' % (who, nd_was), flush=True)
        for g in o['freeze'].upper():
            if g in G:
                old = G[g].b(G[g].base + ALL_NO_MOVE)
                frozen[g] = old or 0                 # review: recorded BEFORE the write, so finally always restores
                G[g].write(G[g].base + ALL_NO_MOVE, b'\x01')
                print('%s: TEST ONLY AllNoMove main+0x%X %s -> 1' % (g, ALL_NO_MOVE, old), flush=True)
        ref_hp = {g: v['hp'] for g, v in vs.items() if v}
        first_hit = None
        last_pos, far_skips, ground_misses = t['pos'], 0, 0
        start_deg = o['side'] if o['side'] is not None else math.degrees(
            math.atan2(t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2]))
        dist = o['itemdist'] if o['mode'] == 'item' else o['dist']
        t0 = time.time()
        n = 0
        while time.time() - t0 < o['seconds']:
            n += 1
            t = find_target('cycle %d' % n)
            if not t:
                print('%s: target handle %08x not found on %s for %.0f s (freed)%s' % (
                    who, handle, who, REREAD_WAIT,
                    ': it died after a hit, check item_sources.py sacs / credit.py' if first_hit else ''))
                rc = 0 if first_hit else 2
                break
            if t['gone']:
                rc = 0
                break
            if not t['loaded']:
                print('%5.1f s #%d: target not loaded (%s): waiting' % (time.time() - t0, n, t['loaded_why']),
                      flush=True)
                time.sleep(1.0)
                continue
            jump = d3(t['pos'], last_pos)
            why = pl.safe(t['pos'], 'target position')
            if why or jump > 30.0:
                far_skips += 1
                print('%5.1f s #%d: not following: %s' % (time.time() - t0, n, why or 'target jumped %.1f m' % jump),
                      flush=True)
                if far_skips >= 5:
                    rc = 4
                    break
                time.sleep(1.0)
                continue
            far_skips = 0
            # who drives it NOW (the assist may hand it over every 250 ms)
            vs = views(G, who, cw, o)
            chrs.update({g: v['chr'] for g, v in vs.items() if v})
            auth, awhy = hp_owner(G, vs)
            # pin for the whole cycle: pin=driver (or auth) -> on the driving game, at that copy's OWN position
            # (what it already has: no teleport, it only stops it moving); pin=A/B/AB -> those games, at WHO's view
            # (only when that copy is within 5 m of it)
            pins = []
            pin_now = (auth or '') if pin_mode in ('auth', 'driver') else pin_fixed
            for g in pin_now:
                cg = chrs.get(g)
                tg = target(G[g], cg, 'auto', sm={}, km={}) if cg else None
                if not tg or tg['gone'] or not tg['loaded'] or not finite3(tg['pos']):
                    print('   pin %s: copy not loaded / not finite: no pin' % g)
                    continue
                at = tg['pos'] if pin_mode in ('auth', 'driver') else t['pos']
                if d3(tg['pos'], at) > 5.0:
                    print('   pin %s: its copy %s is %.1f m from %s view %s: no pin this cycle' % (
                        g, f3s(tg['pos']), d3(tg['pos'], t['pos']), who, f3s(t['pos'])))
                    continue
                p = Pin(g, cg, at)
                p.start()
                pins.append(p)
            if pin_mode in ('auth', 'driver') and not auth:
                print('   pin: nobody drives it now (%s): no pin this cycle' % awhy)
            try:
                hp0 = {g: (target(G[g], chrs[g], 'bag', sm={}, km={}) or {}).get('hp') for g in chrs}
                tpos0 = tuple(t['pos'])

                def still_ok(tpos0=tpos0):
                    # review: before EVERY test side: the target is still loaded, alive and where we aim
                    tt = find_target('side check')
                    if not tt or tt['gone']:
                        return 'target died / freed'
                    if not tt['loaded']:
                        return 'target unloaded (%s)' % tt['loaded_why']
                    if not finite3(tt['pos']) or d3(tt['pos'], tpos0) > 2.0:
                        return 'target moved to %s' % f3s(tt['pos'])
                    return None
                pl.check = still_ok
                res, tries = pl.find(t['pos'], dist, start_deg)
                if not res:
                    ground_misses += 1
                    print('%5.1f s #%d: NO GROUND around %s (%d sides, best drift %.2f): player back at %s' % (
                        time.time() - t0, n, f3s(t['pos']), len(tries),
                        min((r['drift'] for r in tries), default=float('nan')), f3s(pl.ref)), flush=True)
                    if ground_misses >= 3:
                        rc = 4
                        break
                    continue
                ground_misses = 0
                tc0 = throw_counter(w) if o['mode'] == 'item' else None
                tctl.call(who, {'method': 'input_sequence', 'params': {'steps': burst_steps(o)}})
            finally:
                for p in pins:
                    p.stop.set()
                for p in pins:
                    p.join(1.0)
            tc1 = throw_counter(w) if o['mode'] == 'item' else None
            me = pl.refresh()                        # after the burst: player and target re-resolved by handle
            t1 = find_target('after burst %d' % n)
            hp1 = {g: (target(G[g], chrs[g], 'bag', sm={}, km={}) or {}).get('hp') for g in chrs}
            landed = [g for g in chrs if hp0.get(g) is not None and hp1.get(g) is not None and hp1[g] < hp0[g]]
            if landed and first_hit is None:
                first_hit = time.time() - t0
            if me and finite3(me['pos']) and d3(me['pos'], pl.ref) <= 3.0:
                pl.ref = tuple(me['pos'])            # still a known-good place (stood there through the burst)
            tp = t1['pos'] if t1 else None
            line = '%5.1f s #%d h %08x chr 0x%x %s | me %s spot %s side %.0f d%.2f %s drift %.2f | tgt %s %s' % (
                time.time() - t0, n, handle or 0, cw, o['mode'], f3s(me['pos'] if me else None), f3s(res['spot']), res['deg'],
                res['dist'], 'ROUGH' if res.get('rough') else 'ok', res['drift'], who, f3s(tp))
            for g in chrs:
                if g != who:
                    tg = target(G[g], chrs[g], 'bag', sm={}, km={})
                    line += ' %s %s' % (g, f3s(tg['pos'] if tg else None))
            line += ' | drv %s' % (auth or 'NONE')
            if auth and auth != who:
                line += ' (not %s)' % who
            line += ' moved %.2f | hp %s | %s' % (
                d3(tp, last_pos) if tp else float('nan'),
                ' '.join('%s %s->%s' % (g, hp0.get(g), hp1.get(g)) for g in chrs),
                'HIT' if landed else 'miss')
            if t1 and me:
                line += ' | lastatk %s' % ('me' if t1['lastatk'] == me['handle'] else
                                           '%04x' % t1['lastatk'] if t1['lastatk'] is not None else '?')
            if o['mode'] == 'item':
                line += ' | throw req %s' % ('+%d' % (tc1 - tc0) if tc0 is not None and tc1 is not None else '?')
            fg = fg_slots(w, cw) if o['mode'] == 'drain' else None
            if o['mode'] == 'drain':
                line += ' | fg %s' % (sorted(fg) if fg is not None else '?')
            if pins:
                line += ' | pin ' + ' '.join('%s %d%s' % (p.g, p.writes, ' (%s)' % p.err if p.err else '')
                                             for p in pins)
            print(line, flush=True)
            if tp:
                last_pos = tp
            dead = [g for g in chrs if (target(G[g], chrs[g], 'bag', sm={}, km={}) or {'gone': False})['gone']]
            if dead:
                print('   dead / HP 0 on %s' % ','.join(dead), flush=True)
                rc = 0
                break
            if o['mode'] == 'drain' and fg and slot in fg and not (fg0 and slot in fg0):
                print('%s: DRAIN SEEN: target joined friendly group slot %s after %d bursts' % (who, slot, n),
                      flush=True)
                rc = 0
                break
            # HP writes go to the game that drives it now (it sends HP to the others); no driver -> wait
            if (o['keephp'] or (o['finish'] and first_hit is not None)) and not auth:
                print('   HP write skipped: nobody drives it now (%s)' % awhy, flush=True)
            elif o['keephp'] and t1 and t1['max'] and not t1['gone']:
                cur = hp1.get(auth)
                if cur is not None and 0 < cur < t1['max']:
                    finish_game = lower_hp(G, [auth], chrs, t1['max'], up=True)
            elif o['finish'] and first_hit is not None:
                cur = hp1.get(auth)
                if cur is not None and cur > o['finish']:
                    finish_game = lower_hp(G, [auth], chrs, o['finish'])
                    if not finish_game:
                        print('   finish on the driver %s did not stick: %s' % (auth, awhy), flush=True)
        else:
            rc = 1
        st = {g: target(G[g], chrs[g], 'bag', sm={}, km={}) for g in chrs}
        if rc == 0:
            print('%s: TARGET DEAD after %.1f s (%d bursts, first hit %s) | %s' % (
                who, time.time() - t0, n, '%.1f s' % first_hit if first_hit is not None else 'never seen',
                ' '.join('%s hp %s dead %s' % (g, v['hp'], v['dead']) if v else '%s freed' % g
                         for g, v in st.items())))
        elif rc == 1:
            print('%s: time-out after %.0f s, first hit %s | %s' % (
                who, o['seconds'], '%.1f s' % first_hit if first_hit is not None else 'never',
                ' '.join('%s hp %s/%s' % (g, v['hp'], v['max']) if v else '%s freed' % g for g, v in st.items())))
        elif rc == 4:
            print('%s: stopped: no ground / target out of reach (see the lines above)' % who)
        print('start HP %s' % ref_hp)
    finally:
        if pl.trial:                                 # review: a test side was written and never confirmed
            try:
                pl.back()
                print('%s: player put back at %s' % (who, f3s(pl.ref)), flush=True)
            except Exception as e:  # noqa: BLE001
                print('%s: player NOT put back (%s)' % (who, e), flush=True)
        for g, old in frozen.items():
            try:
                G[g].write(G[g].base + ALL_NO_MOVE, bytes([old]))
                print('%s: AllNoMove restored to %d' % (g, old), flush=True)
            except Exception as e:  # noqa: BLE001
                print('%s: AllNoMove NOT restored (%s): run  python diag/twin/mem.py %s w8 main+0x%x %d' % (
                    g, e, g, ALL_NO_MOVE, old), flush=True)
        if nd_was is False:
            import nodeath
            nodeath.set_nodeath(w, False, 'bit', quiet=True)
            print('%s: no-dead bit off again' % who, flush=True)
    return rc


def main():
    who, c, kind, o = opts(sys.argv)
    G = {}
    for g in o['games']:
        try:
            G[g] = W(g)
        except Exception as e:  # noqa: BLE001
            if g == who:
                print('%s: no debug server: %s' % (g, e))
                return 2
            print('%s: not used (no debug server: %s)' % (g, e))
    if o['sacs']:
        return sacs(G, who, o)
    if o['probe']:
        return probe(G, who, c, kind, o)
    if o['ground']:
        sys.exit('ground=1 belongs to probe')
    return fight(G, who, c, kind, o)


if __name__ == '__main__':
    sys.exit(main())
