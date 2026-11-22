"""TEST ONLY - NEVER SHIP. Blood crystal (row 45) hands-free: WHO kills a Bloodsac with a real hit, then the
offer is read, taken with A, and checked on both games. Static work 2026-11-16: py_compile only, never run.

python diag/twin/crystal_test.py A [mode=R|ZR|item] [stock=1]      host kills (A = host in the rig)
python diag/twin/crystal_test.py B [mode=R|ZR|item] [stock=1]      guest kills (needs CRYSTAL_GUEST, see below)
  travel=0   do not jump WHO to the nearest sac it drives when none is usable within 60 m (default: travel)
  aihold=0   do not stop the picked sac's AI during the fight (default: hold; see "AI hold" in the code)
  phasewait=0 / phasesecs=N   start at once / after N s of phase 6 (default: wait until WHO has been in phase 6
             for 30 s in a row, at most 150 s; the 8-minute cap counts from then)
  Fix 2026-11-17 after the first live run: player and sac are found again by HANDLE after every teleport
  (wait_ready: entry 0 alive + sac loaded, up to 30 s), strike.fight gets the handle ('h'), a refused stage is
  repeated once after a reload, and the hold test reads the position by handle (a number, or UNREADABLE).
Added 2026-11-17 (static, never run): travel to the nearest GOOD group, the per-chr AI hold and a 3 s hold test.

Preconditions (refused with the fix printed, nothing written):
  - debug server on A and B; WHO's player position finite;
  - the Bloodsac Gala, env event 1220, is the CURRENT event on both games (history [[main+0x5B57EB8]+0x68]+0x58..
    +0x60, last entry = current; force_event.py). To arm it: in Phase I run
        python diag/twin/force_event.py A 1220 arm B      then end Phase I:  python diag/twin/clock.py 5 AB
  - mode=item only: WHO holds a Fire Flask (goods 4260 in the inventory pgd+0x2E8, itemauth.py's reading). To get
    one:  python diag/twin/item_sources.py A force 20000000   then   python diag/twin/droptest.py WHO
    (and  python diag/twin/item_sources.py A unforce 20000000  afterwards);
  - guest WHO: the crystal gate word main+0x15B0528 must read CRYSTAL_GUEST ON (71C5FF17) on WHO. It is not in
    the build: apply it in the hub first with
        PATCH_FILE=diag/net/crystal_live.py python diag/twin/apply_groups.py AB CRYSTAL_GUEST_CAVE CRYSTAL_GUEST
    stock=1 runs anyway (to see what the stock gate does: expect NOTICE ONLY).

Steps (8-minute cap for the whole run; every step prints what it reads):
  1. BEFORE: treasures.py's block for A and B ("offers pending", "crystal offers by slot"), rewards.py AB snap.
  2. Sacs as WHO sees them (strike.py's readers): alive, loaded (chr-set entry flags 5), finite position, within
     60 m of WHO, and the DRIVER (the game whose assist owner flag >= 0) = WHO ("GOOD"). The 3 nearest candidates
     get strike's ground test (writes WHO's player position / yaw only, puts it back after each): a sac counts as
     on flat ground when a side passes cleanly (not ROUGH) and the landed player y is within 0.5 m of the sac y.
     No GOOD sac: the OTHER game's player is moved 30 m from the nearest candidate (validated: ground test on
     that game, same checks) and the list is read again after 2 s. The other player goes back to its own start
     position at the end.
  3. Fight: strike.fight on the chosen sac, finish=1 pin=driver nodeath=1, in stages until the sac dies:
       a) R x3 per burst, 140 s;  b) ZR hold=40, 100 s;  c) R, dist=0.7 dy=-0.3, freeze on the driver, 120 s
     (mode=item: the thrown flask from 3 m first, 60 s, then a) and b)).
     WHY R + pin first (from the data):
       - the sac is small: hit radius 0.4 m, height 1.0 m, standing on its placement (bloodsac_notes 1);
       - it flees 7-13 m as soon as a player is inside 12 m (catch_notes 1), so the only way to keep it in reach
         is to hold it: pin=driver writes its position on the game that runs its AI, where the write sticks
         (strike_notes 5); the first live run missed 25 of 26 bursts because the pin and the HP write went to the
         game that did NOT drive it;
       - with the sac held, the ground test puts the player 0.9 m from it at its height, facing it: inside a
         light attack's reach [I], with 3 swings per burst;
       - charged ZR is one swing per 40+ frames (fewer chances, more damage): second;
       - the Fire Flask is the weakest choice: throws go at the LOCKED target and the sac's lock distance is -1
         (NpcParam +0x210, catch_notes 1), a player usually holds one flask (10 % drop), 416 HP needs more than
         one throw, and no note gives the size of its fire area. So item is opt-in only.
     strike.fight lowers HP to 1 only on the game that drives the sac NOW, only after a real hit landed (HP fell),
     reads it back after 0.5 s; the kill must then be a real hit (the crystal gate 0x174EF3C needs killer = the
     local player).
  4. AFTER: wait up to 15 s for WHO's offers pending to rise; treasures block A/B; screenshot; press A on WHO
     (twice at most, 3 s apart); offers pending again; rewards.py AB diff, with the pgd fields that also change
     in 3 s without any input (noise, measured first) left out.

Verdict (last line, exit code):
  PASS (0)        sac dead by WHO's hit; WHO's own offers pending rose; after A they are back to the start
                  value; and at least one of WHO's own pgd fields changed that the noise check did not show
  NOTICE ONLY (1) the sac died but one of those is missing (the reason is printed: no offer on WHO, an offer
                  only in another game's slot list, the offer not taken by A, or no pgd change)
  NO KILL (3)     no usable sac / refused / strike stopped (no ground, time-out, 8-minute cap); reason printed
  REFUSED (2)     a precondition failed (fix printed)
  NOT JUDGED (4)  the sac died, but the killer the game recorded at death ([[sac+0x20]+0x114], the handle the
                  kill-reward gate 0x174EF1C..0x174EF54 resolves and compares with the local player) was not WHO's
                  own player, or was never read: no game had to make an offer, so CRYSTAL_GUEST is not tested
                  (2026-11-17: the KillWatch thread polls it every 20 ms on WHO's game; also chr+0x12BC & 0x48000,
                  which makes 0x174EFC4 skip the whole reward)

MEMORY WRITES (all TEST ONLY; each is checked first, see strike.py "Safety"):
  - WHO's player position f32 x y z = [entry 0 +0x28]+0x70 and yaw +0x64 (ground tests and the fight): finite,
    |coord| < 20000, within 60 m of the last known-good player position, within dist of a validated sac position;
  - the OTHER player's position / yaw (only when no sac is GOOD): finite, within 45 m of its own position, landing
    checked (0.3 s later within 0.5 m and still); put back to its start at the end;
  - the sac's physics position [[chr+0x2470]+0xE8]+0x70 on the DRIVER game (pin, every ~10 ms during a burst):
    only while that copy is loaded (entry flags 5), finite, alive, at its own current position;
  - the sac's HP (data module +0x290) = 1 on the DRIVER game, after the first real hit: checked here first that
    the copy is loaded, finite, alive and within 60 m of WHO (wrapper around strike.lower_hp);
  - the no-dead bit on WHO's own player (nodeath.py bit mode), cleared at the end;
  - stage c only: byte main+0x5B84548 "GameData.AllNoMove" = 1 on the driver game, restored at the end;
  - AI hold: byte [[sac chr+0x2470]]+0x14CD bit 7 (= u32 +0x14CC bit 15, "no AI update" of THIS sac only) on
    every loaded copy of the picked sac, re-set every 0.25 s during the fight, cleared at the end where it was
    clear (only if the same copy is still loaded there);
  - travel: WHO's own player jumps up to 150 m to a validated landing 8 m from the nearest GOOD sac (the same
    ground test as the fight); it is not put back (the fight moves it anyway);
  - inputs: R / ZR / D-pad Down bursts and A on WHO (input_sequence).
Nothing else is written. rewards.py and treasures.py only read (rewards' snapshot is a file in %TEMP%).
Run from the workspace root."""
import contextlib
import io
import math
import re
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import strike  # noqa: E402
import tctl  # noqa: E402
from world_lib import W, ENEMY_VT  # noqa: E402

CAP = 480.0                    # 8 minutes for the whole run
GALA = 1220
NETP_G = 0x5B57EB8             # [[*]+0x68] +0x58 / +0x60 = env-event history (force_event.py)
GDM, ITEM_MGR = 0x5B57EB8, 0x5B57E90
GATE = 0x15B0528               # crystal gate word (treasures.py WORDS)
GATE_GUEST = '71C5FF17'
FIRE_FLASK = 4260
MAX_D = 60.0
OTHER_D = 30.0
PY = sys.executable
PAR = 0x5B3CDF8                # [main+PAR]: +0x50 phase (6 = UpdatePhase), +0x120 -> clock, +8 f32 left (clock.py)
T0 = time.time()
CLOCK = {'t0': T0}             # the 8-minute cap starts after the phase wait (see main)


def left():
    return CAP - (time.time() - CLOCK['t0'])


def say(s):
    print('[%5.1f s] %s' % (time.time() - T0, s), flush=True)


def run(args, t=120):
    try:
        r = subprocess.run([PY] + args, capture_output=True, text=True, timeout=t)
        return (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'


# ---------------------------------------------------------------- readers (read only)
def current_event(w):
    n = w.q(w.base + NETP_G)
    h = w.q(n + 0x68) if n else None
    b0, b1 = (w.q(h + 0x58), w.q(h + 0x60)) if h else (None, None)
    if not b0 or b1 is None or b1 < b0 or b1 - b0 > 256 or (b1 - b0) % 4:
        return None
    if b1 == b0:
        return -1
    raw = w.rd(b0, b1 - b0)
    return struct.unpack('<%di' % ((b1 - b0) // 4), raw)[-1] if raw else None


def local_pgd(w):
    g = w.g(GDM)
    return w.q(g + 0x20) if g else None


def goods_count(w, gid):
    """own count of goods gid (itemauth.goods_count on W): inventory pgd+0x2E8"""
    pgd = local_pgd(w)
    if not pgd:
        return None
    inv = pgd + 0x2E8
    n1, total = w.d(inv + 0x2FC), w.d(inv + 0x368)
    a1, a2 = w.q(inv + 0x330), w.q(inv + 0x320)
    if n1 is None or total is None or total + 1 > 4096:
        return None
    cnt = 0
    for k in range(total + 1):
        e = (a1 + k * 16) if k < n1 else (a2 + (k - n1) * 16 if a2 else 0)
        b = w.rd(e, 16) if e else None
        if not b:
            continue
        w0, w1, c = struct.unpack_from('<III', b, 0)
        if w0 and ((w0 & 0x0FFFFFFF) == gid or (w1 & 0x0FFFFFFF) == gid):
            cnt += c
    return cnt


def offers(w):
    """(own pending, own slot, {slot: pending != 0}) from item mgr + 0x21D8 + slot*0x20, u64 +0x18 (treasures.py)"""
    pgd = local_pgd(w)
    im = w.g(ITEM_MGR)
    slot = w.b(pgd + 0x104) if pgd else None
    if not im or slot is None or slot > 0xB:
        return None, slot, {}
    by = {}
    for s in range(12):
        v = w.q(im + 0x21D8 + s * 0x20 + 0x18)
        if v:
            by[s] = v
    return w.q(im + 0x21D8 + slot * 0x20 + 0x18), slot, by


def gate_word(w):
    b = w.rd(w.base + GATE, 4)
    return b.hex().upper() if b else '?'


def treasure_lines(G):
    try:
        import treasures                      # its top-level argument parsing only reads sys.argv; harmless
        for g in 'AB':
            if g in G:
                for line in treasures.block(g, G[g]):
                    if 'role' in line or 'crystal' in line:
                        print('   ' + line, flush=True)
    except Exception as e:  # noqa: BLE001
        say('treasures block failed: %s' % e)


def pgd_diff_offsets(text, who):
    """offsets of '+XXXX' lines under '<who> pgd changes:' in rewards.py diff output"""
    out, cur = {}, None
    for line in text.splitlines():
        if line.endswith('pgd changes:'):
            cur = line.split()[0]
            continue
        if not line.startswith(' '):
            cur = None
            continue
        m = re.match(r'\s+\+([0-9A-F]{4}) ', line)
        if cur == who and m:
            out[int(m.group(1), 16)] = line.strip()
    return out


# ---------------------------------------------------------------- sacs (strike's readers)
def list_sacs(G, who):
    w = G[who]
    me = strike.player(w)
    sm = strike.sync_map(w)
    km = strike.kin_map(w)
    other = {g: strike.sync_map(G[g]) for g in G if g != who}
    rows = []
    for h, (c, _own, _addr) in sm.items():
        if w.q(c) != w.base + ENEMY_VT:
            continue
        t = strike.target(w, c, 'auto', sm=sm, km=km)
        if not t or not t['sac']:
            continue
        vs = {who: t}
        for g, smg in other.items():
            hit = smg.get(t['handle'])
            vs[g] = strike.target(G[g], hit[0], 'auto', sm=smg, km={}) if hit else None
        auth, why = strike.hp_owner(G, vs)
        gap = max((strike.d3(v['pos'], t['pos']) for g, v in vs.items() if g != who and v and v['pos'] and t['pos']),
                  default=None)
        rows.append({'chr': c, 't': t, 'd': strike.d3(t['pos'], me['pos']) if t['pos'] else float('inf'),
                     'auth': auth, 'why': why, 'gap': gap, 'vs': vs})
    rows.sort(key=lambda r: r['d'])
    for k, r in enumerate(rows[:12]):
        t = r['t']
        say('S%-2d chr 0x%x handle %08x hp %s/%s%s d=%.1f %s loaded %s | drv %s%s | gap %s' % (
            k, t['chr'], t['handle'] or 0, t['hp'], t['max'], ' DEAD' if t['gone'] else '', r['d'],
            strike.f3s(t['pos']), 'yes' if t['loaded'] else 'NO (%s)' % t['loaded_why'], r['auth'] or 'NONE',
            ' = %s: GOOD' % who if r['auth'] == who else '', '%.1f m' % r['gap'] if r['gap'] is not None else '-'))
    return me, rows


def usable(r):
    t = r['t']
    return t['loaded'] and not t['gone'] and strike.finite3(t['pos']) and r['d'] <= MAX_D


def ground_ok(G, who, me, r, o):
    """strike's ground test at the sac (writes WHO's player only; back at the start afterwards)"""
    pl = strike.Placer(G[who], me, o)
    t = r['t']
    if pl.safe(t['pos'], 'sac'):
        return False, 'sac position fails the safety check'
    start = math.degrees(math.atan2(t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2]))
    try:
        res, tries = pl.find(t['pos'], o['dist'], start)
    finally:
        pl.ref, pl.ref_yaw = tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0
        pl.back()
    if not res:
        return False, 'no side (%d tried)' % len(tries)
    if res.get('rough'):
        return False, 'only a ROUGH side (drift %.2f): not flat' % res['drift']
    dy = abs(res['p'][1] - t['pos'][1])
    if dy > 0.5:
        return False, 'landed %.2f m above / below the sac: slope' % dy
    return True, 'side %.0f OK drift %.2f dy %.2f' % (res['deg'], res['drift'], dy)


def move_other(G, other, sac_pos, o):
    """put OTHER's player 30 m from the sac on its own side (validated landing); returns its start (pos, yaw)"""
    w = G[other]
    me = strike.player(w)
    if not me or not strike.finite3(me['pos']) or not strike.finite3(sac_pos):
        say('%s: player or sac position not finite: other player not moved' % other)
        return None
    if strike.dh(me['pos'], sac_pos) >= OTHER_D:
        say('%s: already %.1f m from the sac: not moved' % (other, strike.dh(me['pos'], sac_pos)))
        return None
    oo = dict(o, maxjump=45.0, dy=0.2)
    pl = strike.Placer(w, me, oo)
    vx, vz = me['pos'][0] - sac_pos[0], me['pos'][2] - sac_pos[2]
    base = math.degrees(math.atan2(-vx, -vz)) if math.hypot(vx, vz) > 0.1 else 0.0
    start = (tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0)
    for y in (me['pos'][1], sac_pos[1]):
        centre = (sac_pos[0], y, sac_pos[2])
        for k in (0, 1, -1, 2, -2):
            r = pl.try_side(centre, base + 30 * k, OTHER_D)
            if r and r['ok']:
                say('%s: other player moved to %s (%.1f m from the sac, landing drift %.2f)' % (
                    other, strike.f3s(r['p']), strike.dh(r['p'], sac_pos), r['drift']))
                return start
    pl.ref, pl.ref_yaw = start
    pl.back()
    say('%s: no validated spot 30 m away; other player back at its start' % other)
    return None


STATE = {'moved': None}       # review: what main changed on the OTHER game, for the exit path


def put_back(G, other, start, o):
    STATE['moved'] = None         # one attempt only (the exit path does not repeat it)
    if not start:
        return
    w = G[other]
    me = strike.player(w)
    if not me or not strike.finite3(me['pos']):
        say('%s: position not finite now: not put back (start was %s)' % (other, strike.f3s(start[0])))
        return
    pl = strike.Placer(w, me, dict(o, maxjump=45.0))
    if pl.write_player(start[0], start[1]):
        say('%s: other player back at its start %s' % (other, strike.f3s(start[0])))


# ---------------------------------------------------------------- AI hold (2026-11-17, static; never run)
# Why the pin did not hold the sac (live run 2026-11-17: "drv A moved 8.21" with 67 pin writes, AllNoMove on):
#   the chr movement step 0xDA2760.. takes the next position from the physics / animation side every frame, so a
#   position write is simply overwritten; AllNoMove (main+0x5B84548, 0xDA28BC) and the per-chr bit 14 of the
#   same word below (0xDA28A8, set by 0xD777D0 / 0xED2E54) only skip ONE contribution of that step (the w24 / w22
#   apply at 0xDA2990), while the AI keeps driving the flee. [V code, I meaning]
# The handle that stops the cause: the AI-update gate 0xDA6508 (called by the AI tick 0xDAEC48 / 0xDAEF74 /
#   0xDAF024 before the think update 0xB0A340 / 0xB0B480; on "no" 0xDAFA68 calls vt+0x260(-1) [I: clears the command])
#   returns 0 when ANY of these is set [V]:
#     - byte main+0x5B8452C = "GameData.AllNoUpdateAi" (config reader 0x18062E8 -> strb 0x180630C);
#     - [[main+0x5B3CD78]]+0x891 (a debug-manager byte);
#     - [[[chr+0x18]+0x30]+0x18] bit 0;
#     - u32 [[chr+0x2470]]+0x14CC bit 15 = byte +0x14CD bit 7: THIS chr's "no AI update". The game's own setter
#       0xD6AAF8 (orr #0x8000, chr found by handle) is what an event "disable AI" would use [I]; it is cleared at
#       0x174361C (a chr reset path), so the hold re-asserts it.
# This tool sets that per-chr bit on every loaded copy of the picked sac (the driver's matters; the others are
# harmless), every 0.25 s while the fight runs, and clears it at the end where it was clear before.
AI_WORD = 0x14CC               # u32 in [[chr+0x2470]] (module 0)
AI_BYTE, AI_BIT = 0x14CD, 0x80  # bit 15 of the word = no AI update for this chr [V 0xDA6564..0xDA657C]


class AiHold:
    def __init__(self, G, handle):
        self.G, self.handle = G, handle
        self.before = {}                       # (game, module0 address) -> old byte (a reload gives a new copy)
        self.stop = threading.Event()
        self.sets = 0
        self.thread = None

    def module0(self, g):
        w = self.G[g]
        hit = strike.sync_map(w).get(self.handle)
        if not hit:
            return None, 'no copy with handle %08x' % self.handle
        t = strike.target(w, hit[0], 'auto', sm={}, km={})
        if not t or t['gone'] or not t['loaded']:
            return None, 'copy not loaded / dead (%s)' % (t['loaded_why'] if t else 'unreadable')
        bag = w.q(hit[0] + 0x2470)
        m0 = w.q(bag) if bag else None
        if not m0:
            return None, '[[chr+0x2470]] unreadable'
        return m0, None

    def once(self, verbose=False):
        for g in self.G:
            m0, why = self.module0(g)
            if not m0:
                if verbose:
                    say('AI hold %s: %s: not set there' % (g, why))
                continue
            b = self.G[g].b(m0 + AI_BYTE)
            if b is None:
                continue
            if (g, m0) not in self.before:
                self.before[(g, m0)] = b
                say('AI hold %s: [[chr+0x2470]] 0x%x byte +0x%X %02x -> %02x (TEST ONLY: this sac\'s AI stops)' % (
                    g, m0, AI_BYTE, b, b | AI_BIT))
            if not b & AI_BIT:
                if self.stop.is_set() and not verbose:   # audit F2: never write once the clear has started
                    return
                self.G[g].write(m0 + AI_BYTE, bytes([b | AI_BIT]))
                self.sets += 1

    def loop(self):
        while not self.stop.wait(0.25):
            try:
                self.once()
            except Exception:  # noqa: BLE001  (a read error must not kill the fight)
                pass

    def __enter__(self):
        self.once(verbose=True)
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join(2.0)
            if self.thread.is_alive():             # audit F2: a once() still running could set the bit after the clear
                self.thread.join(5.0)
            if self.thread.is_alive():
                say('AI hold: the hold thread is STILL running after 7 s; the bit may be set again after the clear: '
                    'check with  python diag/twin/mem.py <game> r8 <[[chr+0x2470]]+0x%X>' % AI_BYTE)
        for g in self.G:
            mine = {m0: old for (gg, m0), old in self.before.items() if gg == g}
            if not mine:
                continue
            m0, old = None, 0
            try:
                now_m0, _ = self.module0(g)
                if now_m0 not in mine:
                    say('AI hold %s: no copy this test set is loaded now (freed / reloaded): nothing to clear' % g)
                    continue
                m0, old = now_m0, mine[now_m0]
                if old & AI_BIT:
                    say('AI hold %s: the bit was already set before the test: left as it was' % g)
                    continue                       # it was set before the test: leave it
                b = self.G[g].b(m0 + AI_BYTE)
                if b is not None and b & AI_BIT:
                    self.G[g].write(m0 + AI_BYTE, bytes([b & ~AI_BIT & 0xFF]))
                say('AI hold %s: cleared (re-set %d times during the run)' % (g, self.sets))
            except Exception as e:  # noqa: BLE001
                say('AI hold %s: NOT cleared (%s): python diag/twin/mem.py %s w8 0x%x 0x%02x' % (
                    g, e, g, (m0 or 0) + AI_BYTE, old))
        return False


class KillWatch:
    """read only: the sac's recorded killer on EVERY game, every 20 ms, by handle. The kill reward 0x174EE44
    (w1 = 0 from the death handler at 0x17529E4) resolves u32 [[victim+0x20]+0x114] with 0x17E7828 and runs only
    on the game where that is the local player chr (0x174EF3C) or a locally controlled chr (0x17EF704); it also
    skips when u32 victim+0x12BC & 0x48000 (0x174EFC4) or the local player's HP < 1 (0x174EFE8). Only then
    0x15B01A8 (the crystal) runs. Per game: the last sample while alive and the first sample with HP <= 0.
    crystal3 (2026-11-17): all games, so the verdict says WHICH game (if any) owed the offer."""
    def __init__(self, G, who, handle):
        self.G, self.who, self.handle = G, who, handle
        self.alive = {g: None for g in G}      # g -> (t, killer, hp, flags)
        self.death = {g: None for g in G}
        self.mine = {g: self.own_handle(G[g]) for g in G}
        self.stop = threading.Event()
        self.thread = None

    @staticmethod
    def own_handle(w):
        e = w.player_entry(0)
        d = w.q(e[0] + 0x20) if e and e[0] else None
        return w.d(d + 0x78) if d else None

    def sample(self, w):
        c = strike.resolve(w, self.handle, 'h')
        if not c:
            return None
        d = w.q(c + 0x20)
        bag = w.q(c + 0x2470)
        mod = w.q(bag + 0x18) if bag else None
        if not d or not mod:
            return None
        return (time.time(), w.d(d + 0x114), w.i(mod + 0x290), w.d(c + 0x12BC))

    def loop(self):
        while not self.stop.wait(0.02):
            for g, w in self.G.items():
                try:
                    x = self.sample(w)
                except Exception:  # noqa: BLE001
                    x = None
                if not x or x[2] is None:
                    continue
                if x[2] > 0:
                    self.alive[g] = x
                elif self.death[g] is None:
                    self.death[g] = x

    def __enter__(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join(1.0)
        return False

    def name(self, g, h):
        """who handle h is, as game g sees it"""
        if h is None:
            return '?'
        if h == 0xFFFFFFFF:
            return 'NOBODY (-1)'
        for gg, mh in self.mine.items():
            if mh is not None and h == mh:
                return 'player of game %s' % gg
        w = self.G[g]
        for k in range(1, 6):
            e = w.player_entry(k)
            d = w.q(e[0] + 0x20) if e and e[0] else None
            if d and w.d(d + 0x78) == h:
                return 'player entry %d on %s' % (k, g)
        return 'not a player'

    def verdict(self):
        """(credited on WHO's game: True / False / None, text with every game's reading). A game 'owes' the offer
        when its death sample's killer is its OWN local player handle and the 0x48000 flags are clear."""
        parts, owed = [], []
        for g in self.G:
            x = self.death[g] or self.alive[g]
            if x is None:
                parts.append('%s: never read' % g)
                continue
            flags = x[3]
            skip = flags is not None and flags & 0x48000
            here = self.death[g] is not None and x[1] == self.mine[g] and not skip
            if here:
                owed.append(g)
            parts.append('%s: killer %s %08x = %s; own %s; +0x12BC %s%s%s' % (
                g, 'at death' if self.death[g] else 'last alive read (no HP<=0 sample)', x[1] or 0,
                self.name(g, x[1]), '%08x' % self.mine[g] if self.mine[g] is not None else '?',
                '%08x' % flags if flags is not None else '?', ' (& 0x48000: reward skipped)' if skip else '',
                ' -> THIS GAME OWES THE OFFER' if here else ''))
        txt = '%s | offer owed on: %s' % (' || '.join(parts), ', '.join(owed) or 'NO GAME')
        if self.death.get(self.who) is None:
            return None, txt
        return self.who in owed, txt


def pos_by_handle(w, handle):
    """the copy's position on game w, found by HANDLE each time (addresses change after a reload), or None"""
    c = strike.resolve(w, handle, 'h')
    t = strike.target(w, c, 'auto', sm={}, km={}) if c else None
    return t['pos'] if t and t['loaded'] and not t['gone'] and strike.finite3(t['pos']) else None


def hold_test(G, pick, seconds=3.0):
    """the sac's driver-copy position before and after `seconds` with the hold on (no input), by handle; a few
    re-reads so a passing reload does not leave it unreadable. Returns (metres or None, game used)."""
    h = pick['t']['handle']
    for g in [pick['auth']] + [x for x in G if x != pick['auth']]:
        p0 = None
        for _ in range(5):
            p0 = pos_by_handle(G[g], h)
            if p0:
                break
            time.sleep(1.0)
        if not p0:
            continue
        time.sleep(seconds)
        for _ in range(5):
            p1 = pos_by_handle(G[g], h)
            if p1:
                return strike.d3(p0, p1), g
            time.sleep(1.0)
    return None, pick['auth']


def wait_ready(G, who, handle, seconds):
    """after a teleport the area reloads and every address changes: wait until WHO's local player (entry 0) reads
    alive with a finite position AND the sac, found again by handle, reads loaded (entry flags 5) and alive.
    Returns (player, sac target) or (None, reason)."""
    w = G[who]
    t1, why = time.time(), 'not checked'
    while time.time() - t1 < seconds:
        me = strike.player(w)
        if not me or not me['chr'] or not strike.finite3(me['pos']) or (me['hp'] is not None and me['hp'] <= 0):
            why = 'local player (entry 0) not readable yet'
        else:
            c = strike.resolve(w, handle, 'h')
            t = strike.target(w, c, 'auto', sm={}, km={}) if c else None
            if not t:
                why = 'sac handle %08x not found yet' % handle
            elif t['gone']:
                return None, 'the sac is dead / gone'
            elif not t['loaded']:
                why = 'sac not loaded (%s)' % t['loaded_why']
            else:
                time.sleep(1.0)                  # one more read: both must still be the same objects
                me2 = strike.player(w)
                if me2 and me2['chr'] == me['chr'] and strike.is_chr(w, c):
                    say('ready after %.1f s: player chr 0x%x at %s, sac chr 0x%x (handle %08x) loaded' % (
                        time.time() - t1, me['chr'], strike.f3s(me['pos']), c, handle))
                    return me2, t
                why = 'player or sac object changed during the check'
        time.sleep(1.0)
    return None, why


def wait_phase(G, who, need=30.0, limit=150.0):
    """start only after WHO has been in UpdatePhase (phase 6) for `need` seconds in a row (reload / spawn churn
    at a phase start frees and re-creates the sacs). Reads par[0x50] and the clock par[0x120]+8 (clock.py)."""
    w = G[who]
    t1, since = time.time(), None
    while time.time() - t1 < limit:
        par = w.q(w.base + PAR)
        phase = w.d(par + 0x50) if par else None
        clk = w.q(par + 0x120) if par else None
        left_s = w.f(clk + 8) if clk else None
        if phase == 6:
            since = since or time.time()
            if time.time() - since >= need:
                say('phase 6 for %.0f s (clock left %s): starting' % (
                    time.time() - since, '%.0f s' % left_s if left_s is not None else '?'))
                return True
        else:
            since = None
        time.sleep(1.0)
    say('phase 6 not held for %.0f s within %.0f s (last phase %s)' % (need, limit, phase))
    return False


# ---------------------------------------------------------------- travel to the nearest GOOD group
TRAVEL_MAX = 150.0             # farthest validated jump of WHO's own player towards a GOOD sac
TRAVEL_DIST = 8.0              # land this far from the sac (outside its 5 m hearing; it notices at 12 m anyway)


def travel_to_good(G, who, rows, o):
    """WHO's player only: a validated landing (strike's ground test) TRAVEL_DIST from the nearest sac that WHO
    drives, alive and finite, but farther than MAX_D or not loaded; then wait up to 25 s for its entry flags 5."""
    far = [r for r in rows if r['auth'] == who and not r['t']['gone'] and strike.finite3(r['t']['pos'])
           and r['d'] <= TRAVEL_MAX and not usable(r)]
    if not far:
        say('travel: no GOOD sac within %.0f m to travel to' % TRAVEL_MAX)
        return False
    r = far[0]
    t = r['t']
    me = strike.player(G[who])
    if not me or not strike.finite3(me['pos']):
        return False
    pl = strike.Placer(G[who], me, dict(o, maxjump=TRAVEL_MAX + TRAVEL_DIST, dy=0.3))
    start = math.degrees(math.atan2(t['pos'][0] - me['pos'][0], t['pos'][2] - me['pos'][2]))
    say('travel: %s to the GOOD sac 0x%x at %s (%.1f m, loaded %s)' % (
        who, t['chr'], strike.f3s(t['pos']), r['d'], 'yes' if t['loaded'] else 'NO (%s)' % t['loaded_why']))
    res = None
    for _ in range(2):                         # the ground there may still be streaming in: one retry after 3 s
        res, tries = pl.find(t['pos'], TRAVEL_DIST, start)
        if res and not res.get('rough'):
            break
        if res:                                # a ROUGH side is not good enough to stand on: back and retry
            pl.ref, pl.ref_yaw = tuple(me['pos']), me['yaw'] if me['yaw'] is not None else 0.0
            pl.back()
            res = None
        time.sleep(3.0)
    if not res:
        say('travel: no validated landing near the sac (player back at its start)')
        return False
    say('travel: landed at %s (side %.0f, drift %.2f)' % (strike.f3s(res['p']), res['deg'], res['drift']))
    if t['handle'] is None:
        say('travel: the sac has no handle: cannot find it again after the reload')
        return True
    me2, why = wait_ready(G, who, t['handle'], 30.0)
    if not me2:
        say('travel: not ready after 30 s (%s)' % why)
    return True                                # re-list anyway (by handle / sync map): another sac may have loaded


# ---------------------------------------------------------------- HP write guard (wraps strike.lower_hp)
_orig_lower_hp = strike.lower_hp
GUARD = {}


def guarded_lower_hp(G, order, chrs, value, up=False):
    ok = []
    who = GUARD.get('who')
    mp = strike.player(G[who]) if who else None
    for g in order:
        c = chrs.get(g)
        # review 2026-11-16: 'auto' + loaded (entry points back, flags 5, both position sources agree); the old
        # test let a copy whose entry did not point back (= unloaded) through
        t = strike.target(G[g], c, 'auto', sm={}, km={}) if c else None
        if not t or t['gone']:
            print('   HP guard %s: copy unreadable / dead: no write' % g, flush=True)
            continue
        if not t['loaded']:
            print('   HP guard %s: copy not loaded (%s): no write' % (g, t['loaded_why']), flush=True)
            continue
        if not strike.finite3(t['pos']):
            print('   HP guard %s: copy position not finite %s: no write' % (g, strike.f3s(t['pos'])), flush=True)
            continue
        if not mp or not strike.finite3(mp['pos']) or not strike.d3(t['pos'], mp['pos']) <= MAX_D:
            print('   HP guard %s: copy %s is far from %s (> %.0f m): no write' % (g, strike.f3s(t['pos']), who,
                                                                              MAX_D), flush=True)
            continue
        ok.append(g)
    return _orig_lower_hp(G, ok, chrs, value, up) if ok else None


strike.lower_hp = guarded_lower_hp


class Tee(io.TextIOBase):
    def __init__(self):
        self.buf = io.StringIO()

    def writable(self):
        return True

    def write(self, s):
        sys.__stdout__.write(s)
        sys.__stdout__.flush()
        self.buf.write(s)
        return len(s)


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) < 2 or sys.argv[1].upper() not in ('A', 'B'):
        print(__doc__)
        return 2
    who = sys.argv[1].upper()
    other = 'B' if who == 'A' else 'A'
    kv = dict(a.split('=', 1) for a in sys.argv[2:] if '=' in a)
    mode = kv.get('mode', 'R')
    mode = mode.upper() if mode.upper() in ('R', 'ZR') else mode.lower()
    if mode not in ('R', 'ZR', 'item'):
        print('mode must be R, ZR or item')
        return 2
    stock = kv.get('stock') == '1'
    G = {}
    for g in 'AB':
        try:
            G[g] = W(g)
        except Exception as e:  # noqa: BLE001
            print('REFUSED (2): %s has no debug server (%s)' % (g, e))
            return 2
    # ---- preconditions
    say('crystal_test %s (other %s), mode %s; roles A %s B %s' % (
        who, other, mode, G['A'].b(G['A'].base + strike.ROLE), G['B'].b(G['B'].base + strike.ROLE)))
    ev = {g: current_event(G[g]) for g in G}
    say('current env event: %s' % ev)
    if any(v != GALA for v in ev.values()):
        print('REFUSED (2): the Bloodsac Gala (1220) is not the current event on both games.\n'
              '  In Phase I:  python diag/twin/force_event.py A 1220 arm B\n'
              '  then end the phase:  python diag/twin/clock.py 5 AB   (Phase II then runs the Gala)')
        return 2
    me = strike.player(G[who])
    if not me or not strike.finite3(me['pos']):
        print('REFUSED (2): %s player position not finite' % who)
        return 2
    gw = {g: gate_word(G[g]) for g in G}
    role = G[who].b(G[who].base + strike.ROLE)
    say('crystal gate word main+0x%X: %s' % (GATE, gw))
    if role not in (0, 1):
        print('REFUSED (2): %s role byte reads %s (not host 0 / guest 1): not in a session' % (who, role))
        return 2
    if role == 1 and gw[who] != GATE_GUEST and not stock:
        print('REFUSED (2): %s is a guest and its crystal gate is not CRYSTAL_GUEST (%s). In the hub:\n'
              '  PATCH_FILE=diag/net/crystal_live.py python diag/twin/apply_groups.py AB CRYSTAL_GUEST_CAVE '
              'CRYSTAL_GUEST\n  or add stock=1 to see the stock gate (expect NOTICE ONLY).' % (who, gw[who]))
        return 2
    if mode == 'item':
        n = goods_count(G[who], FIRE_FLASK)
        say('%s Fire Flasks: %s' % (who, n))
        if not n:
            print('REFUSED (2): mode=item needs a Fire Flask on %s. Get one:\n'
                  '  python diag/twin/item_sources.py A force 20000000\n'
                  '  python diag/twin/droptest.py %s\n'
                  '  python diag/twin/item_sources.py A unforce 20000000' % (who, who))
            return 2
    # ---- 30 s into the phase first (phasewait=0 skips it); the 8-minute cap counts from here
    if kv.get('phasewait', '1') == '1':
        if not wait_phase(G, who, float(kv.get('phasesecs', '30'))):
            print('VERDICT: NO KILL (3): the phase did not settle (phase 6 for 30 s in a row) within 150 s')
            return 3
    CLOCK['t0'] = time.time()
    # ---- before
    say('BEFORE (treasures):')
    treasure_lines(G)
    p0, slot, by0 = offers(G[who])
    say('%s own offers pending %s (slot %s); by slot %s' % (who, p0, slot, by0))
    tag = 'crys_%s_%d' % (who, int(T0))
    say('rewards snap: %s' % run(['diag/twin/rewards.py', 'AB', 'snap', tag], 90).strip()[-120:])
    # ---- sacs
    o = strike.opts(['strike.py', who, '0x1'])[3]
    o.update(games='AB', maxjump=MAX_D)
    me, rows = list_sacs(G, who)
    if not [r for r in rows if usable(r) and r['auth'] == who] and kv.get('travel', '1') == '1':
        if travel_to_good(G, who, rows, o):
            me, rows = list_sacs(G, who)
    pick, moved = None, None
    for attempt in (1, 2):
        cands = [r for r in rows if usable(r)]
        good = [r for r in cands if r['auth'] == who]
        say('attempt %d: %d sacs, %d usable within %.0f m, %d GOOD (driven by %s)' % (
            attempt, len(rows), len(cands), MAX_D, len(good), who))
        for r in good[:3]:
            if left() < 200:
                break
            ok, why = ground_ok(G, who, me, r, o)
            say('   ground at 0x%x (d %.1f): %s' % (r['chr'], r['d'], why))
            if ok:
                pick = r
                break
        if pick or attempt == 2 or not cands:
            break
        if moved is None:
            STATE.update(G=G, other=other, o=o)
            moved = move_other(G, other, cands[0]['t']['pos'], o)
            STATE['moved'] = moved
            time.sleep(2.0)
            me, rows = list_sacs(G, who)
        if moved is None:
            break
    if not pick:
        put_back(G, other, moved, o)
        reason = ('no Bloodsac in %s\'s sync sets' % who if not rows else
                  'no loaded sac within %.0f m' % MAX_D if not [r for r in rows if usable(r)] else
                  'no sac driven by %s on flat ground (even after moving %s away)' % (who, other))
        print('VERDICT: NO KILL (3): %s' % reason)
        return 3
    t = pick['t']
    say('PICK 0x%x handle %08x d %.1f at %s, driver %s' % (t['chr'], t['handle'] or 0, pick['d'],
                                                           strike.f3s(t['pos']), pick['auth']))
    if t['handle'] is None:
        put_back(G, other, moved, o)
        print('VERDICT: NO KILL (3): the picked sac has no handle (cannot follow it across a reload)')
        return 3
    # the ground tests teleported WHO: make sure the player and the sac (by handle) read loaded before fighting
    me_ok, why = wait_ready(G, who, t['handle'], 30.0)
    if not me_ok:
        put_back(G, other, moved, o)
        print('VERDICT: NO KILL (3): not ready to fight after 30 s: %s' % why)
        return 3
    # ---- fight
    GUARD['who'] = who
    stages = ([dict(mode='item', seconds=60.0)] if mode == 'item' else []) + [
        dict(mode='ZR' if mode == 'ZR' else 'R', seconds=140.0),
        dict(mode='R' if mode == 'ZR' else 'ZR', hold=40, seconds=100.0),
        dict(mode='R', dist=0.7, dy=-0.3, freeze=pick['auth'] or '', seconds=120.0)]
    p0_start, by0_start = p0, by0
    p0, _slot_f, by0 = offers(G[who])                  # audit F1: fresh count just before the fight
    say('%s own offers pending just before the fight %s (at the start %s); by slot %s' % (who, p0, p0_start, by0))
    rc, tee = 1, Tee()
    hold = AiHold(G, t['handle']) if kv.get('aihold', '1') == '1' and t['handle'] is not None else None
    kw = KillWatch(G, who, t['handle'])
    with (hold if hold else contextlib.nullcontext()), kw:
        if hold:
            moved_3s, on = hold_test(G, pick)
            say('AI hold test: the sac moved %s in 3 s with its AI stopped (read on %s by handle %08x; driver %s)' % (
                'UNREADABLE (copy not loaded on any game for 5 s)' if moved_3s is None else '%.2f m' % moved_3s,
                on, t['handle'], pick['auth']))
        for k, st in enumerate(stages):
            budget = min(st['seconds'], left() - 60.0)
            if budget < 20:
                say('8-minute cap: no time for stage %d' % (k + 1))
                break
            oo = dict(o, finish=1, pin='driver', nodeath=1, **{kk: v for kk, v in st.items() if kk != 'seconds'})
            oo['seconds'] = budget
            say('stage %d: %s' % (k + 1, ', '.join('%s=%s' % kv2 for kv2 in sorted(st.items()))))
            for again in (0, 1):
                with contextlib.redirect_stdout(tee):
                    rc = strike.fight(G, who, t['handle'], 'h', oo)
                if rc != 2 or again:
                    break
                # refused: often a reload in the middle (player entry 0 or the sac freed). Wait, then once more.
                me_ok, why = wait_ready(G, who, t['handle'], 30.0)
                if not me_ok:
                    say('stage %d refused and not ready again: %s' % (k + 1, why))
                    break
                say('stage %d refused; player and sac readable again: repeating the stage once' % (k + 1))
            if rc in (0, 2):
                break
    out = tee.buf.getvalue()
    killed = rc == 0 and 'TARGET DEAD' in out
    last_burst = [ln for ln in out.splitlines() if ' | hp ' in ln]
    # the killing burst's line: 'lastatk me' = WHO's player is the last attacker; no lastatk field = the chr was
    # already freed when it was read (unknown, does not block PASS; the offer itself proves the killer)
    my_blow = None if not last_burst or 'lastatk' not in last_burst[-1] else 'lastatk me' in last_burst[-1]
    hit_seen = 'HIT' in out
    if not killed:
        put_back(G, other, moved, o)
        reason = {1: 'time-out / 8-minute cap', 2: 'strike refused the target (see above)',
                  4: 'no ground / sac out of reach'}.get(rc, 'strike rc %s' % rc)
        say('KILLER (no kill seen by strike): %s' % kw.verdict()[1])
        print('VERDICT: NO KILL (3): %s; real hit seen %s' % (reason, hit_seen))
        return 3
    say('sac dead; last burst lastatk me: %s' % my_blow)
    credited, ktxt = kw.verdict()
    say('KILLER: %s' % ktxt)
    # ---- after
    p1, by1 = p0, by0
    t1 = time.time()
    while time.time() - t1 < 15 and left() > 30:
        p1, _, by1 = offers(G[who])
        if p1 is not None and p0 is not None and p1 > p0:
            break
        time.sleep(1.0)
    say('AFTER the kill (treasures):')
    treasure_lines(G)
    other_offer = {g: offers(G[g])[2] for g in G if g != who}
    say('%s own offers pending %s -> %s; by slot %s -> %s; other game by slot %s' % (
        who, p0, p1, by0, by1, other_offer))
    rose = p1 is not None and p0 is not None and p1 > p0
    taken, new_fields = False, {}
    if rose:
        say('shot: %s' % tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}},
                                   'diag/twin/%s_crystal_offer.png' % who)[:100])
        base_tag = tag + '_n'
        run(['diag/twin/rewards.py', 'AB', 'snap', base_tag], 90)
        time.sleep(3.0)
        noise = pgd_diff_offsets(run(['diag/twin/rewards.py', 'AB', 'diff', base_tag], 90), who)
        say('pgd noise (3 s, no input): %d field(s)' % len(noise))
        run(['diag/twin/rewards.py', 'AB', 'snap', base_tag], 90)
        p2 = p1
        for press in (1, 2):
            tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['A'], 'frames': 6},
                                                                             {'frames': 90}]}})
            time.sleep(3.0)
            p2 = offers(G[who])[0]
            say('A press %d: offers pending %s' % (press, p2))
            if p2 is not None and p2 <= p0:
                break
        taken = p2 is not None and p2 <= p0
        diff = run(['diag/twin/rewards.py', 'AB', 'diff', base_tag], 90)
        for line in diff.splitlines()[:60]:
            print('   ' + line)
        new_fields = {k: v for k, v in pgd_diff_offsets(diff, who).items() if k not in noise}
        say('%s pgd fields changed by A (noise left out): %s' % (who, list(new_fields.values())[:8] or 'none'))
    full = run(['diag/twin/rewards.py', 'AB', 'diff', tag], 90)
    say('rewards diff since the start (%s pgd lines): see above for the A step' % (
        len(pgd_diff_offsets(full, who))))
    put_back(G, other, moved, o)
    if rose and taken and new_fields and credited is True and my_blow is True:
        print('VERDICT: PASS (0): %s killed the sac with its own hit (KillWatch: %s); its offer rose %s -> %s, A took '
              'it, and %d own pgd field(s) changed' % (who, ktxt, p0, p1, len(new_fields)))
        return 0
    if rose and taken and new_fields:                  # audit F1: offer seen, but not proven to come from this kill
        print('VERDICT: NOTICE ONLY (1): offer seen (%s -> %s, taken, %d pgd field(s)) but %s; %s' % (
            p0, p1, len(new_fields),
            'the picked sac\'s killer was not %s' % who if credited is False else
            'the picked sac\'s killer was not read' if credited is not True else
            'the last hit was not %s\'s' % who if my_blow is False else 'the last hit was not read (no lastatk)',
            ktxt))
        return 1
    why = ('the killing blow was not seen as %s\'s (last attacker)' % who if my_blow is False else
           'no offer on %s%s' % (who, '; another game lists offers by slot %s' % other_offer
                                if any(other_offer.values()) else '') if not rose else
           'the offer was not taken by A (still pending)' if not taken else
           'A took the offer but no own pgd field changed (beyond the 3 s noise)')
    if credited is not True:
        print('VERDICT: NOT JUDGED (4): sac dead but %s; the WHO game did not owe an offer, so this run says nothing '
              'about CRYSTAL_GUEST (offer on %s %s -> %s, other game by slot %s)' % (
                  ktxt if credited is False else 'the killer at death was not read (%s)' % ktxt, who, p0, p1,
                  other_offer))
        return 4
    print('VERDICT: NOTICE ONLY (1): sac dead; %s; %s' % (why, ktxt))
    return 1


def guarded_main():
    """review 2026-11-16: exactly one verdict line on every path. An exception or Ctrl+C inside strike.fight is
    cleaned up there (AllNoMove, no-dead bit, test side); here the OTHER player goes back and a verdict prints."""
    try:
        return main()
    except BaseException as e:  # noqa: BLE001  (KeyboardInterrupt / SystemExit too)
        sys.stdout = sys.__stdout__
        try:
            if STATE.get('moved'):
                put_back(STATE['G'], STATE['other'], STATE['moved'], STATE['o'])
        except Exception as e2:  # noqa: BLE001
            print('%s: other player NOT put back (%s)' % (STATE.get('other'), e2))
        print('VERDICT: NO KILL (3): stopped by %s: %s' % (type(e).__name__, e))
        return 3


if __name__ == '__main__':
    sys.exit(guarded_main())
