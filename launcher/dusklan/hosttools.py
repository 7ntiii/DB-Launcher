"""The host's match tools: heal, no-death, go to a player, freeze the match time, hold a boss's health.

Talks to the running game through the emulator's local debug server (127.0.0.1:6545 by default; the game
must be started with EDEN_NX2_DEBUG_SERVER=127.0.0.1:<port>). Standard library only.

Every address and pointer chain here is ported from the rig tools in diag/twin and diag/net/zt_faults
(named next to each constant) and the merged emulator's own assist (src/lichii-merge/src/core/dusk_lan.cpp);
nothing is new. The debug server protocol (core/debugger/nx2_debug_server.cpp): one JSON object per line,
{"id", "method", "params"} -> {"id", "result"} or {"id", "error"}. The merged build accepts any number of
clients (one session per connection, all served one after another by one thread); this module still keeps
ONE connection open and shares it between the caller and its own background thread under a lock.

Rules enforced in code (learned on the rig, handoffs/1-LICHII_BOOT_AND_NETWORK.md):
- nothing is written outside a match, and no write follows a failed or implausible read;
- every pointer is checked (range, alignment, and the module's back-pointer to its chr where one exists);
- no teleport in the first 20 s of a phase (drop-in pose; the notes name Phase I) or to a position that is not
  finite, is all zero, or is implausibly far;
- every hold stops by itself (and undoes what it changed) when the match or phase ends, the game closes or the
  connection drops; close() releases everything.
"""
import json
import math
import os
import re
import socket
import struct
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------- addresses (main-relative unless noted)
WCM_G = 0x5B3CD88        # world chr manager: +0x30 player entries (0x38 each, entry 0 = local)  dbg.py, world_lib.py
STRUGGLE_G = 0x5B3CD90   # Trespasser (joint struggle) manager: +8..+0x10 vector of instances    trespassers.py
PAR_G = 0x5B3CDF8        # stage phase: +0x50 step, +0xB8 round, +0x120 clock (+8 f32 s left)   hold_clock.py, dusk_lan.cpp
SESSION_REF = 0x59DFEC8  # [[main+X]] session manager: +0x1268 mode (6 = LAN), +0x126C state (8 = in the match)  dusk_lan.cpp
BUILD_ID_OFF = 0x563E448  # GNU build-id payload of main                                         dusk_lan.cpp FindMain
BUILD_ID = bytes.fromhex('14925E87E1ACD4D5E9D071AFEED230A1D4569F98')

S_MODE, S_STATE, MODE_LAN, STATE_IN_MATCH = 0x1268, 0x126C, 6, 8
P_STEP, P_ROUND, P_CLOCK = 0x50, 0xB8, 0x120
STEP_UPDATE = 6          # UpdatePhase: the playing part of a phase
STEP_NAMES = {6: 'UpdatePhase', 7: 'EndPhase', 9: 'PreResult', 10: 'PhaseResult', 16: 'Advance',
              19: 'FinalPoint', 21: 'PrepareSecond', 22: 'PrepareThird', 23: 'PreIntermission',
              26: 'Intermission', 28: 'EndIntermission', 36: 'MatchEnd'}  # rewards.py STEP_NAMES + notes
ROUND_NAMES = {1: 'Phase I', 2: 'Phase II', 3: 'Phase III', 4: 'Final'}
PHASE1_SECONDS = 360.0   # Phase I clock ("real 360 s clock", handoff 2-PC test)

ENTRY_SIZE = 0x38        # {chr, 0, flags, module, 0, physics, module}                              world_lib.player_entry
E_CHR, E_MODULE, E_PHYS = 0, 3, 5
PHYS_POS = 0x70          # physics +0x70: xyz f32; writing it teleports the local player               goto.py, handoff
CHR_DATA, DATA_PGD = 0x20, 0x1D0  # pgd = [[chr+0x20]+0x1D0]: +8 HP, +0xC max, +0xD0 player number   hp.py, starfrag.py
PGD_HP, PGD_NO = 0x8, 0xD0
MASTER_HP = 0xF30        # [entry module]+0xF30: the master HP the others follow                    hp.py, hold_clock.py
CHR_MODS = 0x2470        # [chr+0x2470]: module table; +0x18 data module, +0xE8 physics             nodeath.py, world_lib.chr_pos
M_DATA, M_PHYS = 0x18, 0xE8
D_BACK, D_HP, D_MAX, D_FLAGS = 0x8, 0x290, 0x294, 0x4A0  # data module: [+8] == chr, HP, max, u16 flags  nodeath.py
NODEAD_BIT = 1 << 2      # "no dead" (HP stops at 1); the game clears it on a chr reset (0xEE1AD4)   nodeath.py
D_HPPROP = 0x1F8 + 0x168  # HP net property P: working P+0x10, master P+0x40                        boss_low3.py
P_WORKING, P_MASTER = 0x10, 0x40
CHR_ENTRY, ENT_STATE, STATE_DEAD = 0x18, 0x30, 0x18  # dead = [[chr+0x18]+0x30]+0x18 bit 0            trespassers.chr_dead
DATA_KEY = 0x78          # [chr+0x20]+0x78 low 16 bits = enemy key (= Trespasser id >> 16)          trespassers.chr_key
JS_ID, JS_STEP = 0xC0, 0x50  # instance: id = round | key << 16, step 0..9 (4 Cancel, 5 End, 9 Finish) trespassers.py
WCM_SETS_N, WCM_SETS, SET_SIZE, SET_NCHR, SET_CHRS = 0x10, 0x18, 0x270, 0x78, 0x80  # world_lib.chr_sets

# ---------------------------------------------------------------- limits
DROPIN_SECONDS = 20.0    # "do not teleport in the first ~20 s of Phase I" (handoff TEST PITFALL)
BESIDE = (1.5, 0.5, 0.0)  # bring_to.py: 1.5 m beside the target, 0.5 m up
MAX_TELEPORT_M = 3000.0  # farther than this from our own position is not plausible
MAX_COORD = 20000.0
BOSS_RANGE_M = 150.0     # hold_boss only takes a boss this near
NOT_IN_MATCH_STOP_S = 2.0
CLOCK_SLACK = 1.0        # hold_clock_smooth.py: put the clock back once it is 1 s below the held value
BOSS_REFRESH_S = 15.0
GUEST_TOP = 1 << 40


class _Lost(Exception):
    """the connection is gone"""


class _Bad(Exception):
    """a read or write failed, or a value is not plausible; nothing was written after it"""


def _finite3(p):
    return p is not None and len(p) == 3 and all(isinstance(v, float) and math.isfinite(v) for v in p)


def _ptr_ok(p):
    return isinstance(p, int) and 0x10000 <= p < GUEST_TOP and p % 8 == 0


def _hdist(a, b):
    return math.dist(a, b)


class HostTools:
    def __init__(self, port=6545, log=lambda text: None, *, data_dir=None, main_base=None):
        """data_dir: the emulator's data folder (its log/dusk_lan.txt names main's base address); main_base: a
        known base (both optional; every candidate is checked against main's build id before use)."""
        self._port = int(port)
        self._logf = log
        self._data_dir = data_dir
        self._base_hint = main_base
        self._lock = threading.RLock()
        self._sock = None
        self._buf = b''
        self._n = 0
        self._base = None
        self._last_base = None
        self._next_try = 0.0
        self._base_warned = False
        self._clock = None      # {'value', 'round'}
        self._nodeath = None    # {'chr', 'mod', 'was_set', 'resets'}
        self._boss = None       # {'chr', 'id', 'want', 'round', 'writes': [times], 'warned'}
        self._pending_restore = None  # no-death bit to clear after a reconnect: (base, chr, mod)
        self._phase_key = None  # (round, step) seen last
        self._phase_start = None  # time.monotonic() when the current UpdatePhase began (or an estimate)
        self._out_since = None
        self._bosses = []       # cached [{'chr', 'id', 'key', 'step'}]
        self._bosses_at = 0.0
        self._nodeath_at = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='HostTools', daemon=True)
        self._thread.start()

    # ================================================================ public API
    def status(self) -> dict:
        out = {'connected': False, 'in_match': False, 'phase': None, 'clock_held': False, 'no_death': False,
               'boss_hold': False, 'me': None, 'players': [], 'bosses': []}
        try:
            with self._lock:
                if not self._ensure():
                    return self._flags(out)
                out['connected'] = True
                if self._base is None:
                    return self._flags(out)
                st = self._phase()
                out['in_match'] = st['in_match']
                out['phase'] = st['name']
                me = self._me()
                if me:
                    out['me'] = {'pos': [round(v, 2) for v in me['pos']], 'hp': me['hp'], 'hp_max': me['hp_max']}
                    for p in self._others(me):
                        out['players'].append({'number': p['number'], 'pos': [round(v, 2) for v in p['pos']],
                                               'distance': round(_hdist(p['pos'], me['pos']), 1)})
                    if st['in_match']:
                        for b in self._boss_rows(me['pos']):
                            out['bosses'].append({'id': b['id'], 'hp': b['hp'], 'hp_max': b['hp_max'],
                                                  'distance': round(b['distance'], 1)})
        except _Lost:
            out['connected'] = False
        except Exception as e:  # never raise
            self._say('status: %s' % e)
        return self._flags(out)

    def heal(self) -> tuple[bool, str]:
        return self._guard('heal', self._heal)

    def set_no_death(self, on: bool) -> tuple[bool, str]:
        return self._guard('no-death', lambda: self._set_no_death(bool(on)))

    def teleport_to_player(self, number: int) -> tuple[bool, str]:
        return self._guard('teleport', lambda: self._teleport(number))

    def hold_clock(self, on: bool) -> tuple[bool, str]:
        return self._guard('clock', lambda: self._hold_clock(bool(on)))

    def hold_boss(self, on: bool, hp: int | None = None) -> tuple[bool, str]:
        return self._guard('boss', lambda: self._hold_boss(bool(on), hp))

    def close(self):
        try:
            self._stop.set()
            with self._lock:
                self._release_all('the host tools were closed')
                self._disconnect()
        except Exception as e:
            self._say('close: %s' % e)
        try:
            if self._thread is not threading.current_thread():
                self._thread.join(timeout=3.0)
        except Exception:
            pass

    # ================================================================ actions
    def _heal(self):
        self._need_match()
        me = self._me(strict=True)
        hp, mx = me['hp'], me['hp_max']
        if hp <= 0:
            return False, 'Your character is down; healing cannot bring it back. Use the revival map.'
        if hp >= mx:
            return True, 'Your health is already full (%d).' % mx
        master = me['module'] + MASTER_HP
        cur = self._i32(master)
        if not 0 <= cur <= mx:
            raise _Bad('master health reads %d (max %d): not plausible' % (cur, mx))
        self._write(master, struct.pack('<i', mx))
        return True, 'Health restored to full (%d).' % mx

    def _set_no_death(self, on):
        if not on:
            if not self._nodeath:
                return True, 'No-death was not on.'
            self._stop_nodeath('switched off')
            return True, 'No-death is off: you can die again.'
        self._need_match()
        me = self._me(strict=True)
        chr_, mod = me['chr'], self._data_module(me['chr'])
        flags = self._u16(mod + D_FLAGS)
        was = bool(flags & NODEAD_BIT)
        if not was:
            self._write(mod + D_FLAGS, struct.pack('<B', (flags | NODEAD_BIT) & 0xFF))  # low byte only (nodeath.py)
            if not self._u16(mod + D_FLAGS) & NODEAD_BIT:
                raise _Bad('the no-death bit did not stick')
        keep_was = was if not self._nodeath else self._nodeath['was_set']
        self._nodeath = {'chr': chr_, 'mod': mod, 'was_set': keep_was, 'resets': 0}
        return True, ('No-death is on: hits still land, but your health stops at 1. Falls into the void and '
                      'scripted instant kills are not covered. It switches off when the match ends.')

    def _teleport(self, number):
        try:
            number = int(number)
        except (TypeError, ValueError):
            return False, 'That is not a player number.'
        st = self._need_match()
        if st['step'] != STEP_UPDATE:
            return False, 'You can only move to a player while the phase is being played.'
        age = self._phase_age(st)
        if age is not None and age < DROPIN_SECONDS:
            return False, 'Wait %d more seconds: at the start of a phase everyone is still dropping in.' % (
                math.ceil(DROPIN_SECONDS - age))
        me = self._me(strict=True)
        if number == me['number']:
            return False, 'That is your own player number.'
        if me['hp'] <= 0:
            return False, 'Your character is down; revive first.'
        target = next((p for p in self._others(me) if p['number'] == number), None)
        if target is None:
            return False, 'Player %d is not seen by this game right now.' % number
        tp = target['pos']
        if not _finite3(tp) or all(abs(v) < 1e-3 for v in tp) or (tp[0] == 0.0 and tp[2] == 0.0):
            return False, 'Player %d has no valid position yet.' % number
        if any(abs(v) > MAX_COORD for v in tp):
            return False, 'Player %d\'s position is not plausible; not moving.' % number
        far = _hdist(tp, me['pos'])
        if far > MAX_TELEPORT_M:
            return False, 'Player %d seems %.0f m away, which is not plausible; not moving.' % (number, far)
        spot = (tp[0] + BESIDE[0], tp[1] + BESIDE[1], tp[2] + BESIDE[2])
        # the local entry must still be the same character and physics object right before the write
        again = self._entry(0)
        if again[E_CHR] != me['chr'] or again[E_PHYS] != me['phys']:
            raise _Bad('the local character changed while reading')
        self._write(me['phys'] + PHYS_POS, struct.pack('<3f', *spot))
        now = self._f3(me['phys'] + PHYS_POS)
        if not _finite3(now) or _hdist(now, spot) > 3.0:
            return True, 'Moved next to player %d, but the game put your character somewhere else.' % number
        return True, 'Moved next to player %d (%.0f m).' % (number, far)

    def _hold_clock(self, on):
        if not on:
            if not self._clock:
                return True, 'The match time was not held.'
            self._clock = None
            return True, 'The match time runs again.'
        st = self._need_match()
        if st['step'] != STEP_UPDATE:
            return False, 'The time can only be held while the phase is being played.'
        left = st['clock']
        if left is None or not 0.0 < left <= 7200.0:
            raise _Bad('the phase clock reads %r' % left)
        self._clock = {'value': left, 'round': st['round']}
        return True, ('Match time held at %d:%02d left. While it is held the timer dial shows no number. It holds '
                      'only while this game leads the match clock, and stops when the phase ends.' % (
                          int(left) // 60, int(left) % 60))

    def _hold_boss(self, on, hp):
        if not on:
            if not self._boss:
                return True, 'No boss was held.'
            self._boss = None
            return True, 'The boss\'s health is no longer held.'
        st = self._need_match()
        me = self._me(strict=True)
        self._refresh_bosses(force=True)
        rows = self._boss_rows(me['pos'])
        if not rows:
            return False, 'No boss (Trespasser) is near you right now.'
        b = rows[0]
        if b['distance'] > BOSS_RANGE_M:
            return False, 'The nearest boss is %.0f m away; get closer first.' % b['distance']
        if hp is None:
            want = b['hp']
        else:
            try:
                want = int(hp)
            except (TypeError, ValueError):
                return False, 'That is not a health value.'
        if want < 1:
            return False, 'The held health must be at least 1.'
        want = min(want, b['hp_max'])
        self._boss = {'chr': b['chr'], 'id': b['id'], 'want': want, 'round': st['round'], 'writes': [],
                      'warned': False}
        self._boss_tick()
        if not self._boss:
            return False, 'The boss could not be held (it is gone or defeated).'
        return True, ('Boss %s: health kept at %d or lower (hits still lower it). It works only while this game '
                      'drives that boss.' % (b['id'], want))

    # ================================================================ background thread
    def _run(self):
        while not self._stop.is_set():
            pause, scan = 1.0, False
            try:
                with self._lock:
                    if self._ensure() and self._base is not None:
                        scan = self._tick()
                        pause = 0.1 if self._boss else 0.25 if (self._clock or self._nodeath) else 1.0
                # the Trespasser scan reads many chrs: outside the lock, so the caller is not held up
                if scan and not self._stop.is_set():
                    self._refresh_bosses()
            except _Lost:
                pass
            except Exception as e:
                self._say('background: %s' % e)
            self._stop.wait(pause)

    def _tick(self):
        """one pass of the holds; returns True when the Trespasser list is due for a refresh"""
        st = self._phase()
        if not st['in_match']:
            if self._out_since is None:
                self._out_since = time.monotonic()
            if time.monotonic() - self._out_since >= NOT_IN_MATCH_STOP_S:
                self._release_all('the match ended')
                self._bosses = []
            return False
        self._out_since = None
        if self._clock:
            try:
                self._clock_tick(st)
            except _Bad:
                pass  # nothing written after a failed read; next pass tries again
        if self._nodeath and time.monotonic() - self._nodeath_at >= 0.5:
            self._nodeath_at = time.monotonic()
            try:
                self._nodeath_tick()
            except _Bad:
                pass
        if self._boss:
            if st['round'] != self._boss['round']:
                self._stop_boss('the phase changed')
            else:
                try:
                    self._boss_tick()
                except _Bad:
                    pass
        return time.monotonic() - self._bosses_at >= BOSS_REFRESH_S

    def _clock_tick(self, st):
        c = self._clock
        if st['step'] != STEP_UPDATE or st['round'] != c['round']:
            self._clock = None
            self._say('Match time hold ended: the phase ended.')
            return
        left = st['clock']
        if left is None or not math.isfinite(left):
            return
        if left < c['value'] - CLOCK_SLACK:
            self._write(st['clock_addr'], struct.pack('<f', c['value']))

    def _nodeath_tick(self):
        nd = self._nodeath
        try:
            e = self._entry(0)
            chr_ = e[E_CHR]
            mod = self._data_module(chr_)
        except _Bad:
            return  # loading or a chr reset in progress: try again next tick, write nothing
        if chr_ != nd['chr'] or mod != nd['mod']:
            nd.update(chr=chr_, mod=mod)  # new character object (new round): follow it
        flags = self._u16(mod + D_FLAGS)
        if not flags & NODEAD_BIT:
            self._write(mod + D_FLAGS, struct.pack('<B', (flags | NODEAD_BIT) & 0xFF))
            nd['resets'] += 1

    def _boss_tick(self):
        b = self._boss
        c = b['chr']
        try:
            mod = self._data_module(c)
            hp = self._i32(mod + D_HP)
            dead = self._chr_dead(c)
        except _Bad:
            self._stop_boss('the boss is gone')
            return
        if hp <= 0 or dead:
            self._stop_boss('the boss was defeated')
            return
        prop = self._u64(mod + D_HPPROP)
        spots = [mod + D_HP] + ([prop + P_WORKING, prop + P_MASTER] if _ptr_ok(prop) else [])
        wrote = False
        for a in spots:
            v = self._i32(a)
            if v > b['want']:
                self._write(a, struct.pack('<i', b['want']))
                wrote = True
        if wrote:
            now = time.monotonic()
            b['writes'] = [t for t in b['writes'] if now - t < 10.0] + [now]
            if len(b['writes']) >= 40 and not b['warned']:
                b['warned'] = True
                self._say('Boss %s: its health keeps coming back; another game drives this boss, so the hold '
                          'cannot stick.' % b['id'])

    # ================================================================ stopping and restoring
    def _release_all(self, why):
        if self._clock:
            self._clock = None
            self._say('Match time hold ended: %s.' % why)
        if self._boss:
            self._stop_boss(why)
        if self._nodeath:
            self._stop_nodeath(why)

    def _stop_boss(self, why):
        if self._boss:
            self._say('Boss %s hold ended: %s.' % (self._boss['id'], why))
        self._boss = None  # nothing to restore: putting the health back up would heal the boss

    def _stop_nodeath(self, why):
        nd, self._nodeath = self._nodeath, None
        if not nd:
            return
        self._say('No-death ended: %s.' % why)
        if nd['was_set']:
            return
        try:
            self._clear_nodead(nd['chr'], nd['mod'])
        except _Lost:
            self._pending_restore = (self._last_base, nd['chr'], nd['mod'])
        except _Bad:
            pass  # the character is gone (match over / game closed): the bit went with it

    def _clear_nodead(self, chr_, mod):
        if self._data_module(chr_) != mod:
            return
        flags = self._u16(mod + D_FLAGS)
        if flags & NODEAD_BIT:
            self._write(mod + D_FLAGS, struct.pack('<B', (flags & ~NODEAD_BIT) & 0xFF))

    def _on_lost(self, why):
        """the connection dropped: every hold stops; a set no-death bit is cleared after a reconnect"""
        if self._clock or self._boss or self._nodeath:
            self._say('Connection to the game lost (%s): every hold stopped.' % why)
        self._clock = self._boss = None
        nd, self._nodeath = self._nodeath, None
        if nd and not nd['was_set']:
            self._pending_restore = (self._last_base, nd['chr'], nd['mod'])
        self._phase_key = self._phase_start = None
        self._bosses, self._bosses_at = [], 0.0

    # ================================================================ game state readers
    def _phase(self):
        st = {'in_match': False, 'name': None, 'step': None, 'round': None, 'clock': None, 'clock_addr': None}
        try:
            mgr = self._u64(self._u64(self._base + SESSION_REF))
            lan = _ptr_ok(mgr) and self._u32(mgr + S_MODE) == MODE_LAN and self._u32(mgr + S_STATE) == STATE_IN_MATCH
            par = self._u64(self._base + PAR_G)
            if not _ptr_ok(par):
                self._track(None)
                return st
            step, rnd = self._u32(par + P_STEP), self._u32(par + P_ROUND)
        except _Bad:
            self._track(None)
            return st
        st['step'], st['round'] = step, rnd
        st['in_match'] = bool(lan and 1 <= rnd <= 4)
        if st['in_match']:
            name = ROUND_NAMES[rnd]
            st['name'] = name if step == STEP_UPDATE else '%s (%s)' % (name, STEP_NAMES.get(step, 'step %d' % step))
        if step == STEP_UPDATE:
            try:
                clock = self._u64(par + P_CLOCK)
                if _ptr_ok(clock):
                    left = self._f32(clock + 8)
                    if math.isfinite(left):
                        st['clock'], st['clock_addr'] = left, clock + 8
            except _Bad:
                pass
        self._track(st)
        return st

    def _track(self, st):
        """remember when the current UpdatePhase began, for the drop-in rule"""
        key = (st['round'], st['step']) if st and st['in_match'] else None
        if key == self._phase_key:
            return
        first_look = self._phase_key is None
        self._phase_key = key
        self._phase_start = None
        if key and key[1] == STEP_UPDATE:
            now = time.monotonic()
            if not first_look:
                self._phase_start = now  # seen it begin
            elif key[0] == 1 and st['clock'] is not None and 0.0 <= st['clock'] <= PHASE1_SECONDS:
                self._phase_start = now - (PHASE1_SECONDS - st['clock'])  # joined mid-phase: from the clock
            else:
                self._phase_start = now - DROPIN_SECONDS  # joined mid-phase, length unknown: assume past the drop-in

    def _phase_age(self, st):
        if self._phase_key != (st['round'], st['step']) or self._phase_start is None:
            return 0.0  # not tracked yet: treat as just begun (refuse), the thread tracks it within a second
        return time.monotonic() - self._phase_start

    def _need_match(self):
        if self._base is None:
            raise _Bad('main base unknown')
        st = self._phase()
        if not st['in_match']:
            raise _NotInMatch()
        return st

    def _entry(self, k):
        wcm = self._ptr(self._base + WCM_G)
        arr = self._ptr(wcm + 0x30)
        return struct.unpack('<7Q', self._read(arr + ENTRY_SIZE * k, ENTRY_SIZE))

    def _entries(self, maxn=16):
        wcm = self._ptr(self._base + WCM_G)
        arr = self._ptr(wcm + 0x30)
        out = []
        for k in range(maxn):
            e = struct.unpack('<7Q', self._read(arr + ENTRY_SIZE * k, ENTRY_SIZE))
            if not e[E_CHR]:
                break
            out.append(e)
        return out

    def _pgd(self, chr_):
        if not _ptr_ok(chr_):
            raise _Bad('bad chr pointer')
        return self._ptr(self._ptr(chr_ + CHR_DATA) + DATA_PGD)

    def _me(self, strict=False):
        try:
            e = self._entry(0)
            chr_, module, phys = e[E_CHR], e[E_MODULE], e[E_PHYS]
            if not (_ptr_ok(chr_) and _ptr_ok(module) and _ptr_ok(phys)):
                raise _Bad('local player entry not ready')
            pos = self._f3(phys + PHYS_POS)
            if not _finite3(pos):
                raise _Bad('own position not finite')
            pgd = self._pgd(chr_)
            hp, mx = struct.unpack('<2i', self._read(pgd + PGD_HP, 8))
            no = self._u32(pgd + PGD_NO)
            if not (0 < mx <= 1000000 and -1 <= hp <= mx):
                raise _Bad('own health reads %d / %d' % (hp, mx))
            return {'chr': chr_, 'module': module, 'phys': phys, 'pos': pos, 'hp': max(hp, 0), 'hp_max': mx,
                    'number': no if no < 0x100 else None}
        except _Bad:
            if strict:
                raise _Bad('your character cannot be read right now (loading?)')
            return None

    def _others(self, me):
        out = []
        try:
            entries = self._entries()
        except _Bad:
            return out
        for e in entries[1:]:
            try:
                no = self._u32(self._pgd(e[E_CHR]) + PGD_NO)
                if no >= 0x100 or no == me['number']:
                    continue
                pos = self._f3(e[E_PHYS] + PHYS_POS) if _ptr_ok(e[E_PHYS]) else None
                if not _finite3(pos):
                    continue
                out.append({'number': no, 'pos': pos})
            except _Bad:
                continue
        return out

    def _data_module(self, chr_):
        """[[chr+0x2470]+0x18], checked by its back-pointer [mod+8] == chr (nodeath.module)"""
        if not _ptr_ok(chr_):
            raise _Bad('bad chr pointer')
        mod = self._ptr(self._ptr(chr_ + CHR_MODS) + M_DATA)
        if self._u64(mod + D_BACK) != chr_:
            raise _Bad('data module does not belong to the chr')
        return mod

    def _chr_dead(self, chr_):
        ent = self._ptr(chr_ + CHR_ENTRY)
        return bool(self._read(self._ptr(ent + ENT_STATE) + STATE_DEAD, 1)[0] & 1)

    def _chr_pos(self, chr_):
        return self._f3(self._ptr(self._ptr(chr_ + CHR_MODS) + M_PHYS) + PHYS_POS)

    # ---------------------------------------------------------------- Trespassers
    def _refresh_bosses(self, force=False):
        if not force and time.monotonic() - self._bosses_at < BOSS_REFRESH_S:
            return
        self._bosses_at = time.monotonic()
        found = []
        try:
            keys = self._struggle_keys()
            if keys:
                for c in self._all_chrs():
                    try:
                        k = self._u32(self._ptr(c + CHR_DATA) + DATA_KEY) & 0xFFFF
                    except _Bad:
                        continue
                    if k in keys:
                        found.append({'chr': c, 'key': k, 'id': '0x%x' % k, 'step': keys[k]})
        except (_Bad, TypeError):  # TypeError: the connection dropped mid-scan (base gone)
            pass
        self._bosses = found

    def _struggle_keys(self):
        """enemy key -> instance step, for instances not yet cancelled / ended / finished (step < 4)"""
        m = self._u64(self._base + STRUGGLE_G)
        if not _ptr_ok(m):
            return {}
        lo, hi = struct.unpack('<2Q', self._read(m + 8, 16))
        if not _ptr_ok(lo) or hi < lo or (hi - lo) // 8 > 64:
            return {}
        keys = {}
        n = (hi - lo) // 8
        if n:
            for ins in struct.unpack('<%dQ' % n, self._read(lo, 8 * n)):
                if not _ptr_ok(ins):
                    continue
                try:
                    step, iid = self._u32(ins + JS_STEP), self._u32(ins + JS_ID)
                except _Bad:
                    continue
                if step < 4:
                    keys[iid >> 16] = step
        return keys

    def _all_chrs(self):
        wcm = self._ptr(self._base + WCM_G)
        n, arr = self._u32(wcm + WCM_SETS_N), self._u64(wcm + WCM_SETS)
        if not _ptr_ok(arr) or not 0 < n <= 256:
            return []
        out = []
        for k in range(n):
            try:
                head = self._read(arr + k * SET_SIZE + SET_NCHR, 0x10)
                nchr, chrs = struct.unpack_from('<I', head, 0)[0], struct.unpack_from('<Q', head, 8)[0]
                if not _ptr_ok(chrs) or not 0 < nchr <= 8192:
                    continue
                raw = b''
                total = ENTRY_SIZE * nchr
                for o in range(0, total, 0xE000):
                    raw += self._read(chrs + o, min(0xE000, total - o))
                for j in range(nchr):
                    c = struct.unpack_from('<Q', raw, ENTRY_SIZE * j)[0]
                    if _ptr_ok(c):
                        out.append(c)
            except _Bad:
                continue
            if len(out) > 20000:
                break
        return out

    def _boss_rows(self, here):
        rows = []
        for b in self._bosses:
            try:
                mod = self._data_module(b['chr'])
                hp, mx = struct.unpack('<2i', self._read(mod + D_HP, 8))
                if hp <= 0 or mx <= 0 or self._chr_dead(b['chr']):
                    continue
                pos = self._chr_pos(b['chr'])
                if not _finite3(pos):
                    continue
                rows.append(dict(b, hp=hp, hp_max=mx, distance=_hdist(pos, here)))
            except _Bad:
                continue
        rows.sort(key=lambda r: r['distance'])
        return rows

    # ================================================================ connection and memory
    def _ensure(self):
        """connected (and the base looked up); False when the game cannot be reached"""
        if self._sock is not None and (self._base is not None or time.monotonic() < self._next_try):
            return True
        if self._stop.is_set() or time.monotonic() < self._next_try:
            return False
        self._next_try = time.monotonic() + 3.0
        if self._sock is None:
            try:
                self._sock = socket.create_connection(('127.0.0.1', self._port), timeout=1.5)
                self._sock.settimeout(5.0)
                self._buf = b''
                self._base_warned = False
            except OSError:
                self._sock = None
                return False
        try:
            self._base = self._find_base()
            if self._base is None:
                if not self._base_warned:
                    self._base_warned = True
                    self._say('Connected to the game, but main\'s base address is not known yet.')
                self._next_try = time.monotonic() + 3.0
            else:
                self._last_base = self._base
                self._after_reconnect()
        except _Lost:
            return False
        return self._sock is not None

    def _after_reconnect(self):
        pend, self._pending_restore = self._pending_restore, None
        if pend and pend[0] == self._base:
            try:
                self._clear_nodead(pend[1], pend[2])
            except _Bad:
                pass

    def _disconnect(self):
        s, self._sock = self._sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
        self._base = None

    def _lost(self, why):
        self._disconnect()
        self._on_lost(why)
        raise _Lost(why)

    def _call(self, method, params):
        with self._lock:
            if self._sock is None:
                raise _Lost('not connected')
            self._n += 1
            want = self._n
            try:
                self._sock.sendall(json.dumps({'id': want, 'method': method, 'params': params}).encode() + b'\n')
                while True:
                    while b'\n' not in self._buf:
                        chunk = self._sock.recv(1 << 20)
                        if not chunk:
                            self._lost('the game closed the connection')
                        self._buf += chunk
                    raw, _, self._buf = self._buf.partition(b'\n')
                    r = json.loads(raw)
                    if r.get('id') == want:
                        break
            except (OSError, ValueError) as e:
                self._lost(str(e) or type(e).__name__)
            if 'error' in r:
                raise _Bad(str(r['error']))
            res = r.get('result')
            if not isinstance(res, dict):
                raise _Bad('empty answer')
            return res

    def _read(self, a, n):
        if not isinstance(a, int) or a < 0x10000 or a + n > GUEST_TOP or not 0 < n <= 0x10000:
            raise _Bad('address %r not readable' % (a,))
        r = self._call('read_memory', {'address': hex(a), 'size': n})
        try:
            b = bytes.fromhex(r.get('hex') or '')
        except ValueError:
            raise _Bad('bad read answer')
        if len(b) != n:
            raise _Bad('short read at %#x' % a)
        return b

    def _write(self, a, data):
        data = bytes(data)
        if not isinstance(a, int) or a < 0x10000 or a + len(data) > GUEST_TOP or not 0 < len(data) <= 64:
            raise _Bad('address %r not writable' % (a,))
        r = self._call('write_memory', {'address': hex(a), 'hex': data.hex()})
        if r.get('size') != len(data):
            raise _Bad('write at %#x not confirmed' % a)

    def _u64(self, a):
        return struct.unpack('<Q', self._read(a, 8))[0]

    def _u32(self, a):
        return struct.unpack('<I', self._read(a, 4))[0]

    def _i32(self, a):
        return struct.unpack('<i', self._read(a, 4))[0]

    def _u16(self, a):
        return struct.unpack('<H', self._read(a, 2))[0]

    def _f32(self, a):
        return struct.unpack('<f', self._read(a, 4))[0]

    def _f3(self, a):
        return struct.unpack('<3f', self._read(a, 12))

    def _ptr(self, a):
        p = self._u64(a)
        if not _ptr_ok(p):
            raise _Bad('null or bad pointer at %#x' % a)
        return p

    # ---------------------------------------------------------------- main's base address
    def _base_ok(self, base):
        try:
            return isinstance(base, int) and base % 0x1000 == 0 and self._read(base + BUILD_ID_OFF, 20) == BUILD_ID
        except _Bad:
            return False

    def _find_base(self):
        """from (1) the caller, (2) DUSK_BASE, (3) the newest 'main base 0x..' line of the emulator's
        log/dusk_lan.txt (written by the built-in LAN assist at boot, as the rig's lanlog.main_base reads it),
        (4) a search for main's build id; each candidate must show the build id at base + 0x563E448"""
        cands = []
        if self._base_hint:
            cands.append(int(self._base_hint))
        if os.environ.get('DUSK_BASE'):
            try:
                cands.append(int(os.environ['DUSK_BASE'], 16))
            except ValueError:
                pass
        if self._last_base:
            cands.append(self._last_base)
        cands += self._bases_from_logs()
        seen = set()
        for b in cands:
            if b not in seen:
                seen.add(b)
                if self._base_ok(b):
                    return b
        return self._base_by_search()

    def _bases_from_logs(self):
        dirs = []
        if self._data_dir:
            dirs.append(Path(self._data_dir))
        if os.environ.get('LICHII_USER_DIR'):
            dirs.append(Path(os.environ['LICHII_USER_DIR']))
        dirs.append(Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'eden')
        files = []
        for d in dirs:
            p = d / 'log' / 'dusk_lan.txt'
            try:
                files.append((p.stat().st_mtime, p))
            except OSError:
                pass
        out = []
        for _, p in sorted(files, reverse=True):
            try:
                text = p.read_text(errors='replace')
            except OSError:
                continue
            out += [int(x, 16) for x in reversed(re.findall(r'main base (0x[0-9a-fA-F]+)', text))]
        return out

    def _base_by_search(self):
        """Not proven on the rig: a read-only search for the build id near the addresses main was seen at
        (0x8008d000..0x80fdc000 in the rig logs), in small slices so the game is not held up."""
        start, end = 0x80000000 + BUILD_ID_OFF, 0x84000000 + BUILD_ID_OFF + 20
        for _ in range(400):
            try:
                r = self._call('search_memory', {'pattern': BUILD_ID.hex(), 'regions': 'all', 'start': hex(start),
                                                 'end': hex(end), 'max_hits': 16, 'budget_ms': 50})
            except _Bad:
                return None
            for h in r.get('hits', []):
                try:
                    b = int(h, 16) - BUILD_ID_OFF
                except (TypeError, ValueError):
                    continue
                if self._base_ok(b):
                    return b
            nxt = r.get('next')
            if not nxt:
                return None
            start = int(nxt, 16)
            time.sleep(0.02)
        return None

    # ---------------------------------------------------------------- helpers
    def _guard(self, what, fn):
        try:
            with self._lock:
                if not self._ensure():
                    return False, ('Cannot reach the game on port %d. Is the game running (started with its '
                                   'debug server on)?' % self._port)
                if self._base is None:
                    return False, 'The game is still starting; try again in a moment.'
                return fn()
        except _NotInMatch:
            return False, 'You are not in a match.'
        except _Lost:
            return False, 'The connection to the game was lost; nothing was changed.'
        except _Bad as e:
            self._say('%s refused: %s' % (what, e))
            return False, 'Could not do that safely right now (%s); nothing was changed.' % e
        except Exception as e:
            self._say('%s failed: %r' % (what, e))
            return False, 'Something went wrong; nothing more was changed.'

    def _flags(self, out):
        out['clock_held'] = self._clock is not None
        out['no_death'] = self._nodeath is not None
        out['boss_hold'] = self._boss is not None
        return out

    def _say(self, text):
        try:
            self._logf(text)
        except Exception:
            pass


class _NotInMatch(_Bad):
    pass


if __name__ == '__main__':
    import sys
    tools = HostTools(int(sys.argv[1]) if len(sys.argv) > 1 else 6545, log=lambda t: print('#', t, file=sys.stderr))
    try:
        print(json.dumps(tools.status(), indent=1))
    finally:
        tools.close()
