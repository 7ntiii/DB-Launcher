"""Fight ONE given enemy until it is dead (TEST ONLY: holds the player's HP and shortens the enemy's HP).
python diag/twin/fightfoe.py WHO ENEMY_CHR_ADDR [maxhp=60] [seconds=120] [hold=N] [dist=1.6] [far=3.0] [bursts=3]

  WHO            twin game (A, B, C)
  ENEMY_CHR_ADDR enemy chr address (hex), e.g. from trespassers.py ('enemy chr ...') or kill.py's search
  maxhp=60       after the enemy has taken its first real hit (HP below its start value / its max), its HP is
                 lowered to this value (and capped there afterwards), so the fight ends with real hits
  seconds=120    give up after this long
  hold=N         HP the local player is kept at (default: its max, pgd+0xC); 0 = no HP hold
  dist / far     stand-off distance after an approach (m) / re-approach when the horizontal distance is above far
  bursts         R presses per attack burst (5 frames down, 25 up each)
  nodeath=1      TEST ONLY, never ship: set the engine's per-chr "no dead" bit (nodeath.py: [[chr+0x2470]+0x18]
                 +0x4A0 bit 2) on the local player for the fight, so a hit stops at HP 1 and the HP hold refills it;
                 the hold thread sets it again if the game clears it; cleared at the end (unless it was set before).
                 The player's own attacks are unaffected.

Steps: if the local player is dead -> revive.revive(); start the HP-hold thread (own debug connection, writes the
master HP [entry0+0x18]+0xF30 every 0.1 s when 0 < HP < hold); approach (approach.py's Approach, target re-read
from the enemy every step: teleport to dist+1 m, measure the stick, walk in to dist, turn to face the enemy),
lock on (StickR); then loop: re-approach if the distance > far, turn if the facing is > 30 deg off (StickR again
if it stays > 45 deg off: the lock is lost), R burst, read the enemy HP, print a progress line. Stops when the
enemy HP <= 0 or its dead bit is set, the enemy chr becomes unreadable, or time runs out.
Enemy HP [[chr+0x2470]+0x18]+0x290, max +0x294 (kill.py / trespassers.py); dead bit [[chr+0x18]+0x30]+0x18
bit 0 (trespassers.py); position [[chr+0x2470]+0xE8]+0x70 (world_lib.chr_pos). Run from the workspace root.
Exit: 0 enemy dead, 1 time-out, 2 bad enemy / no player, 3 player dead and revive failed."""
import math
import struct
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402
from approach import Approach  # noqa: E402
import revive  # noqa: E402
import nodeath  # noqa: E402
import tctl  # noqa: E402


# ---------- readers ----------
def master_hp_addr(w):
    e = w.player_entry(0)
    return e[3] + 0xF30 if e and e[3] else None


def player_max(w):
    """pgd+0xC, pgd = [[chr+0x20]+0x1D0] (hp.py prints it as 'max')"""
    chr_, _, _ = w.me()
    data = w.q(chr_ + 0x20) if chr_ else None
    pgd = w.q(data + 0x1D0) if data else None
    return w.i(pgd + 0xC) if pgd else None


def enemy_hp_addr(w, c):
    m = w.q(c + 0x2470)
    mod = w.q(m + 0x18) if m else None
    return mod + 0x290 if mod else None


def enemy_state(w, c):
    """(hp, max, dead bit) or None if the chr is unreadable"""
    a = enemy_hp_addr(w, c)
    if a is None:
        return None
    hp, mx = w.i(a), w.i(a + 4)
    if hp is None:
        return None
    p = w.q(c + 0x18)
    p = w.q(p + 0x30) if p else None
    v = w.b(p + 0x18) if p else None
    return hp, mx, (None if v is None else v & 1)


# ---------- HP hold thread ----------
class HoldHP(threading.Thread):
    def __init__(self, who, value, nodeath_on=False):
        super().__init__(daemon=True)
        self.w = W(who)              # own Mem / socket: Dbg is not shared between threads
        self.value = value
        self.nodeath_on = nodeath_on   # re-assert the no-dead bit (the game clears it in 0xEE1AD4)
        self.stop = threading.Event()
        self.pause = threading.Event()
        self.writes = 0
        self.reasserts = 0
        self.dead_seen = False

    def run(self):
        while not self.stop.is_set():
            if not self.pause.is_set():
                try:
                    if self.nodeath_on:
                        _, mod, why = nodeath.module(self.w)
                        f = self.w.h(mod + nodeath.FLAGS_OFF) if mod and not why else None
                        if f is not None and not f & nodeath.NODEAD_BIT:
                            self.w.write(mod + nodeath.FLAGS_OFF, struct.pack('<B', (f | nodeath.NODEAD_BIT) & 0xFF))
                            self.reasserts += 1
                            print('hold: no-dead bit was cleared by the game: set again (%d)' % self.reasserts,
                                  flush=True)
                    if self.value is None:
                        time.sleep(0.1)
                        continue
                    a = master_hp_addr(self.w)
                    cur = self.w.i(a) if a else None
                    if cur is not None and cur <= 0:
                        self.dead_seen = True          # never write a dead player back to life here
                    elif cur is not None and cur < self.value:
                        self.w.write(a, struct.pack('<i', self.value))
                        self.writes += 1
                except Exception as e:  # noqa: BLE001  (debug server hiccup: keep going)
                    print('hold: %s' % e, flush=True)
                    time.sleep(0.5)
            time.sleep(0.1)


# ---------- approach that follows the enemy ----------
class FoeApproach(Approach):
    def __init__(self, who, enemy, dist):
        super().__init__({'who': who, 'tgt': (0.0, 0.0, 0.0), 'dist': dist, 'side': None, 'y': None,
                          'dy': 0.3, 'hold': None, 'shot': None})
        self.enemy = enemy
        self.refresh()

    def refresh(self):
        p = self.w.chr_pos(self.enemy)
        if p:
            self.tgt = p
        return p

    def to_target(self, pos):
        self.refresh()
        return super().to_target(pos)

    def approach(self):
        """teleport + (measure once) + walk + turn; True when in range (facing may still be off)"""
        if not self.refresh():
            print('approach: enemy position unreadable')
            return False
        if not self.teleport():
            return False
        if self.cam is None:
            for k in range(3):
                if self.measure():
                    break
                time.sleep(2.0)
            else:
                return False
        self.walk()
        self.turn()
        return True


def lock_on(who):
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4}, {'frames': 10}]}})


def burst(who, n):
    s = []
    for _ in range(n):
        s += [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': s}})


def parse(argv):
    if len(argv) < 3:
        print(__doc__)
        sys.exit(1)
    o = {'who': argv[1], 'enemy': int(argv[2], 16), 'maxhp': 60, 'seconds': 120.0, 'hold': None,
         'dist': 1.6, 'far': 3.0, 'bursts': 3, 'nodeath': 0}
    for a in argv[3:]:
        k, _, v = a.partition('=')
        if k not in o or not _:
            sys.exit('unknown option %s' % a)
        o[k] = float(v) if k in ('seconds', 'dist', 'far') else int(v)
    return o


def main():
    o = parse(sys.argv)
    who, c = o['who'], o['enemy']
    ap = FoeApproach(who, c, o['dist'])
    w = ap.w
    st = enemy_state(w, c)
    if st is None or not ap.refresh():
        print('%s: enemy chr %s unreadable (hp %s, pos %s)' % (who, w.rel(c), st, w.chr_pos(c)))
        w.report_missing()
        return 2
    hp0, emax, dead = st
    print('%s: enemy %s hp %d/%s dead %s at (%.2f %.2f %.2f)' % ((who, w.rel(c), hp0, emax, dead) + tuple(ap.tgt)),
          flush=True)
    if hp0 <= 0 or dead:
        print('enemy already dead')
        return 0
    a = master_hp_addr(w)
    if a is None:
        print('%s: no local player entry' % who)
        return 2
    if (w.i(a) or 0) <= 0:
        print('%s: local player dead at start: revive' % who, flush=True)
        if not revive.revive(who):
            return 3
        time.sleep(2.0)
    hold_v = o['hold'] if o['hold'] is not None else (player_max(w) or w.i(master_hp_addr(w)))
    hold = None
    nd_before = None
    if o['nodeath']:
        print('%s: nodeath=1: TEST ONLY no-dead bit on the local player for this fight' % who, flush=True)
        nd_before, nd_after = nodeath.set_nodeath(w, True, 'bit')
        if nd_after is None:
            print('%s: no-dead could not be set: fighting without it' % who, flush=True)
            nd_before = None
    if (hold_v and hold_v > 0) or nd_before is not None:
        hold = HoldHP(who, hold_v if hold_v and hold_v > 0 else None, nodeath_on=nd_before is not None)
        hold.start()
        if hold.value:
            print('%s: holding the master HP at %d (test only)' % (who, hold_v), flush=True)

    ref = hp0 if hp0 < (emax or hp0 + 1) else emax     # a "real hit" = HP below this
    hit_t, lowered, caps, last_lock = None, 0, 0, 0.0
    t0 = time.time()
    rc = 1
    try:
        ap.approach()
        lock_on(who)
        last_lock = time.time()
        n = 0
        while time.time() - t0 < o['seconds']:
            n += 1
            # player alive?
            a = master_hp_addr(w)
            mine = w.i(a) if a else None
            if mine is not None and mine <= 0:
                print('%s: player died (HP 0): revive' % who, flush=True)
                if hold:
                    hold.pause.set()
                ok = revive.revive(who)
                if hold:
                    hold.pause.clear()
                if not ok:
                    rc = 3
                    break
                time.sleep(2.0)
                ap.approach()
                lock_on(who)
                last_lock = time.time()
                continue
            # range / facing
            chr_, pos = ap.state()
            if pos is None:
                print('%s: no player position (loading?)' % who)
                time.sleep(1.0)
                continue
            _, _, d = ap.to_target(pos)
            if d > o['far']:
                print('%s: %.2f m > %.1f: re-approach' % (who, d, o['far']), flush=True)
                ap.approach()
                chr_, pos = ap.state()
            err, _ = ap.face_err(chr_, pos) if pos else (None, None)
            if err is not None and err > 30:
                ap.turn()
                chr_, pos = ap.state()
                err, _ = ap.face_err(chr_, pos) if pos else (None, None)
                if err is not None and err > 45 and time.time() - last_lock > 5:
                    print('%s: still %.0f deg off: lock-on lost? StickR' % (who, err), flush=True)
                    lock_on(who)
                    last_lock = time.time()
            # attack
            burst(who, o['bursts'])
            st = enemy_state(w, c)
            if st is None:
                print('%s: enemy chr unreadable now (despawned / freed): stopping' % who)
                rc = 0
                break
            ehp, emax, dead = st
            if hit_t is None and ehp < ref:
                hit_t = time.time() - t0
                print('%s: first real hit at %.1f s: enemy hp %d (was %d)' % (who, hit_t, ehp, ref), flush=True)
            if hit_t is not None and ehp > o['maxhp'] and ehp > 0 and not dead:
                ha = enemy_hp_addr(w, c)
                if ha:
                    w.write(ha, struct.pack('<i', o['maxhp']))
                    lowered += 1
                    print('%s: enemy hp %d -> %d (write %d)' % (who, ehp, o['maxhp'], lowered), flush=True)
            _, pos = ap.state()
            _, _, d = ap.to_target(pos) if pos else (0, 0, -1)
            print('%5.1f s burst %d: enemy hp %d/%s dead %s | my hp %s | dist %.2f | facing off %s | holds %s%s' % (
                time.time() - t0, n, ehp, emax, dead, mine, d, '%.0f' % err if err is not None else '?',
                hold.writes if hold else '-',
                ' | nodead re-sets %d' % hold.reasserts if hold and hold.nodeath_on else ''), flush=True)
            if ehp <= 0 or dead:
                print('%s: ENEMY DEAD after %.1f s (%d bursts, first hit %s, HP lowered %d x)' % (
                    who, time.time() - t0, n, '%.1f s' % hit_t if hit_t is not None else 'never seen', lowered))
                rc = 0
                break
        else:
            print('%s: time-out after %.0f s, enemy hp %s' % (who, o['seconds'], enemy_state(w, c)))
    finally:
        if hold:
            hold.stop.set()
            hold.join(1.0)
        if nd_before is not None:
            was = bool((nd_before['flags'] or 0) & nodeath.NODEAD_BIT)
            if was:
                print('%s: no-dead bit was already set before the fight: left on' % who)
            else:
                print('%s: fight over: no-dead off again' % who)
                nodeath.set_nodeath(w, False, 'bit')
        w.report_missing()
    return rc


if __name__ == '__main__':
    sys.exit(main())
