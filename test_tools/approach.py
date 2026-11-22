"""Walk the local player up to an object so it FACES it (for prompts such as "Enter compact with kin" and
"Swear to the blood pledge pillar", whose range test checks the model-matrix facing, not phys+0x64).

python diag/twin/approach.py WHO X Y Z [dist=1.5] [from=DX,DZ | facing=DX,DZ] [y=ABS | dy=0.2]
                             [hold=BUTTON:FRAMES] [shot=NAME]
  WHO        twin game (A, B, C)
  X Y Z      target (kin circle: the 'button' origin promptcheck prints; pillar: the geom position)
  dist       final horizontal distance to the target (m, default 1.5); a bare number also works
  from=DX,DZ side to stand on: unit vector target -> standing spot (default: the side the player is on now)
  facing=DX,DZ the opposite: direction standing spot -> target (promptcheck's 'STAND AT ... (dir DX, DZ)')
  y= / dy=   teleport height: absolute y, or target Y + dy (default dy=0.2)
  hold=Y:420 hold a button N frames after the approach; shot=NAME screenshots to diag/twin/<WHO>_<NAME>.png
             (and <WHO>_<NAME>_pre.png before the hold)
Steps: (1) teleport (W.goto, the only memory write) to dist+1.0 m from the target, (2) measure how the
camera-relative left stick maps to world xz by short pushes (as place.py), (3) walk in with small pushes,
re-measuring every push, until the horizontal distance is `dist` (max 12 pushes, never on purpose past it),
(4) read the game's facing (-Z row of [chr+0x68]+0x150, x/z) and turn in place with 2-frame pushes while it is
more than 30 deg off (max 4), (5) optional hold + screenshot. Run from the workspace root."""
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402
import tctl  # noqa: E402

WS = HERE.parents[1]
MAX_WALK = 12
MAX_TURN = 4
FACE_OK = 30.0          # deg
MEASURE_FRAMES = 6
SETTLE = 12             # frames with no input after each push before reading the position
MIN_MOVE = 0.02         # m: smaller than this = the push did not move the player


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def deg(a):
    return math.degrees(a)


def ang_w(dx, dz):
    """world xz angle in the world_lib.goto convention: atan2(x, z)"""
    return math.atan2(dx, dz)


def parse(argv):
    if len(argv) < 5:
        print(__doc__)
        sys.exit(1)
    o = {'who': argv[1], 'tgt': tuple(float(v) for v in argv[2:5]), 'dist': 1.5, 'side': None,
         'y': None, 'dy': 0.2, 'hold': None, 'shot': None}
    for a in argv[5:]:
        k, _, v = a.partition('=')
        if not _:
            o['dist'] = float(a)
        elif k == 'dist':
            o['dist'] = float(v)
        elif k in ('from', 'facing'):
            dx, dz = (float(t) for t in v.split(','))
            n = math.hypot(dx, dz)
            if n < 1e-6:
                sys.exit('%s=%s: zero vector' % (k, v))
            o['side'] = (dx / n, dz / n) if k == 'from' else (-dx / n, -dz / n)
        elif k == 'y':
            o['y'] = float(v)
        elif k == 'dy':
            o['dy'] = float(v)
        elif k == 'hold':
            b, _, f = v.partition(':')
            o['hold'] = (b, int(f or 60))
        elif k == 'shot':
            o['shot'] = v
        else:
            sys.exit('unknown option %s' % a)
    return o


class Approach:
    def __init__(self, o):
        self.o = o
        self.who = o['who']
        self.w = W(self.who)
        self.tgt = o['tgt']
        self.cam = None      # world angle of stick-up (atan2(x,z))
        self.hand = 1        # +1: stick right turns clockwise like world angle +; -1: mirrored
        self.mpf = None      # metres per pushed frame (incl. the coast after release), learned

    # ---------- reads (no writes) ----------
    def state(self):
        chr_, phys, pos = self.w.me()
        return chr_, pos

    def hp(self, chr_):
        return self.w.chr_hp(chr_) if chr_ else None

    def facing(self, chr_):
        """-(Z row of the chr model matrix): [chr+0x68]+0x170, x and z (promptcheck.player_facing) [V]"""
        m68 = self.w.q(chr_ + 0x68) if chr_ else None
        z = self.w.f3(m68 + 0x170) if m68 else None
        if not z:
            return None
        fx, fz = -z[0], -z[2]
        n = math.hypot(fx, fz)
        return (fx / n, fz / n) if n > 1e-6 else None

    def to_target(self, pos):
        dx, dz = self.tgt[0] - pos[0], self.tgt[2] - pos[2]
        return dx, dz, math.hypot(dx, dz)

    def face_err(self, chr_, pos):
        """degrees between the game facing and the direction to the target, or None"""
        f = self.facing(chr_)
        dx, dz, d = self.to_target(pos)
        if f is None or d < 1e-4:
            return None, f
        dot = (f[0] * dx + f[1] * dz) / d
        return deg(math.acos(max(-1.0, min(1.0, dot)))), f

    def report(self, tag):
        chr_, pos = self.state()
        if pos is None:
            print('%-10s no player position' % tag)
            return chr_, None, None, None
        _, _, d = self.to_target(pos)
        err, f = self.face_err(chr_, pos)
        print('%-10s pos (%.2f %.2f %.2f)  horiz dist %.2f (want %.2f)  dy %+.2f  facing %s  off target %s' % (
            tag, pos[0], pos[1], pos[2], d, self.o['dist'], pos[1] - self.tgt[1],
            '(%.2f, %.2f)' % f if f else '?', '%.0f deg' % err if err is not None else '?'))
        return chr_, pos, d, err

    def alive(self, chr_, tag):
        hp = self.hp(chr_)
        if hp is None:
            print('%s: HP unreadable ([[chr+0x2470]+0x18]+0x290), continuing' % tag)
            return True
        if hp <= 0:
            print('%s: player HP %d: dead, stopping' % (tag, hp))
            return False
        return True

    # ---------- input ----------
    def push(self, stick, frames, settle=SETTLE):
        _, a = self.state()
        tctl.call(self.who, {'method': 'input_sequence', 'params': {'steps': [
            {'left_stick': [round(stick[0], 3), round(stick[1], 3)], 'frames': int(frames)}, {'frames': settle}]}})
        _, b = self.state()
        if a is None or b is None:
            return None
        return b[0] - a[0], b[2] - a[2]

    def learn(self, stick, frames, d):
        """update the camera angle from one push: world angle = cam + hand * stick angle"""
        if d is None or math.hypot(*d) < MIN_MOVE:
            return False
        a_s = math.atan2(stick[0], stick[1])
        a_w = ang_w(*d)
        self.cam = wrap(a_w - self.hand * a_s)
        mpf = math.hypot(*d) / frames
        self.mpf = mpf if self.mpf is None else 0.5 * (self.mpf + mpf)
        return True

    def stick_for(self, dx, dz):
        """stick vector that should walk along world (dx, dz)"""
        a_s = self.hand * wrap(ang_w(dx, dz) - self.cam)
        return math.sin(a_s), math.cos(a_s)

    def measure(self):
        """two pushes: stick up gives the camera angle, stick right the handedness (as place.py, plus a 2nd axis)"""
        for frames in (MEASURE_FRAMES, MEASURE_FRAMES * 2):
            up = self.push((0, 1), frames)
            if up and math.hypot(*up) >= MIN_MOVE:
                break
            print('measure: stick up %d frames moved %s m: retrying longer' % (
                frames, '%.3f' % math.hypot(*up) if up else '?'))
        else:
            print('measure: the player does not move with the stick (menu open, stunned, loading?): stopping')
            return False
        cam = ang_w(*up)
        right = self.push((1, 0), frames)
        if right and math.hypot(*right) >= MIN_MOVE:
            turn = wrap(ang_w(*right) - cam)
            self.hand = 1 if turn > 0 else -1
            if abs(abs(turn) - math.pi / 2) > math.radians(35):
                print('measure: stick right is %.0f deg from stick up in world (expected +-90): camera moved?' % deg(turn))
        else:
            print('measure: stick right did not move the player; assuming handedness +1')
        self.cam, self.mpf = cam, math.hypot(*up) / frames
        self.learn((1, 0), frames, right)
        print('measure: stick up -> world dir (%.2f, %.2f) = %.0f deg, handedness %+d, now cam %.0f deg, %.3f m/frame' % (
            math.sin(cam), math.cos(cam), deg(cam), self.hand, deg(self.cam), self.mpf))
        return True

    # ---------- steps ----------
    def teleport(self):
        t, o = self.tgt, self.o
        side = o['side']
        if side is None:
            _, pos = self.state()
            if pos is not None and math.hypot(pos[0] - t[0], pos[2] - t[2]) > 0.05:
                n = math.hypot(pos[0] - t[0], pos[2] - t[2])
                side = ((pos[0] - t[0]) / n, (pos[2] - t[2]) / n)
            else:
                side = (0.0, -1.0)
            print('side: the one the player is on now, target -> player (%.2f, %.2f)' % side)
        else:
            print('side: given, target -> stand (%.2f, %.2f)' % side)
        r = o['dist'] + 1.0
        y = o['y'] if o['y'] is not None else t[1] + o['dy']
        spot = (t[0] + side[0] * r, y, t[2] + side[1] * r)
        yaw = ang_w(-side[0], -side[1])
        if not self.w.goto(spot, yaw):
            return False
        tctl.call(self.who, {'method': 'input_sequence', 'params': {'steps': [{'frames': 30}]}})
        return True

    def walk(self):
        want = self.o['dist']
        for k in range(1, MAX_WALK + 1):
            chr_, pos, d, _ = self.report('walk %d' % k)
            if pos is None or not self.alive(chr_, 'walk %d' % k):
                return False
            rem = d - want
            step = self.mpf * 2 if self.mpf else 0.1        # what the shortest (2-frame) push would cover
            if rem <= max(0.12, 0.5 * step):
                print('walk: at %.2f m (%.2f over the wanted %.2f): done' % (d, rem, want))
                return True
            frames = int(max(2, min(12, math.floor(0.8 * rem / self.mpf)))) if self.mpf else 3
            if self.mpf and frames * self.mpf > rem:                   # never plan past the target distance
                frames = max(2, int(rem / self.mpf))
                if frames * self.mpf > rem + 0.1:
                    print('walk: even 2 frames (%.2f m) would overshoot %.2f m: stopping here' % (frames * self.mpf, rem))
                    return True
            dx, dz, _ = self.to_target(pos)
            stick = self.stick_for(dx, dz)
            dlt = self.push(stick, frames)
            moved = math.hypot(*dlt) if dlt else 0.0
            err = deg(wrap(ang_w(*dlt) - ang_w(dx, dz))) if dlt and moved >= MIN_MOVE else None
            print('          push stick (%.2f, %.2f) %d frames: moved %.2f m, %s off the target line' % (
                stick[0], stick[1], frames, moved, '%+.0f deg' % err if err is not None else '?'))
            if not self.learn(stick, frames, dlt):
                print('walk: the push did not move the player (wall, stagger, menu?): re-measuring')
                if not self.measure():
                    return False
        _, pos, d, _ = self.report('walk end')
        print('walk: time-out after %d pushes at %.2f m' % (MAX_WALK, d if d is not None else -1))
        return d is not None

    def turn(self):
        for k in range(MAX_TURN + 1):
            chr_, pos, d, err = self.report('face %d' % k)
            if pos is None:
                return False
            if err is None:
                print('face: facing unreadable ([chr+0x68]+0x170) or player on the target: cannot verify')
                return False
            if err <= FACE_OK:
                print('face: %.0f deg <= %.0f: facing the target' % (err, FACE_OK))
                return True
            if k == MAX_TURN:
                break
            if self.cam is None and not self.measure():
                return False
            dx, dz, _ = self.to_target(pos)
            stick = self.stick_for(dx, dz)
            dlt = self.push(stick, 2)
            self.learn(stick, 2, dlt)
            print('          turn push stick (%.2f, %.2f) 2 frames, moved %.2f m' % (
                stick[0], stick[1], math.hypot(*dlt) if dlt else 0.0))
        print('face: still over %.0f deg after %d turn pushes' % (FACE_OK, MAX_TURN))
        return False

    def finish(self):
        o = self.o
        name = o['shot']
        if name and o['hold']:
            out = WS / 'diag' / 'twin' / ('%s_%s_pre.png' % (self.who, name))
            print('shot (before hold):', tctl.call(self.who, {'method': 'screenshot', 'params': {'height': 480}}, out))
        if o['hold']:
            b, n = o['hold']
            print('hold %s for %d frames' % (b, n))
            print(tctl.call(self.who, {'method': 'input_sequence', 'params': {'steps': [
                {'buttons': [b], 'frames': n}, {'frames': 20}]}}))
            chr_, _, _, _ = self.report('after hold')
            self.alive(chr_, 'after hold')
        if name:
            out = WS / 'diag' / 'twin' / ('%s_%s.png' % (self.who, name))
            print('shot:', tctl.call(self.who, {'method': 'screenshot', 'params': {'height': 480}}, out))

    def run(self):
        print('%s: target (%.2f %.2f %.2f), want %.2f m' % ((self.who,) + self.tgt + (self.o['dist'],)))
        chr_, pos, _, _ = self.report('start')
        if pos is None:
            self.w.report_missing()
            return 2
        if not self.alive(chr_, 'start'):
            return 3
        if not self.teleport():
            return 2
        chr_, pos, _, _ = self.report('teleport')
        if pos is None or not self.alive(chr_, 'teleport'):
            return 3
        if not self.measure():
            return 4
        walked = self.walk()
        faced = self.turn() if walked else False
        chr_, pos, d, err = self.report('final')
        if chr_ is not None and not self.alive(chr_, 'final'):
            return 3
        self.finish()
        self.w.report_missing()
        print('RESULT dist %s facing %s -> %s' % ('%.2f' % d if d is not None else '?',
                                                 '%.0f deg' % err if err is not None else '?',
                                                 'OK' if walked and faced else 'NOT OK'))
        return 0 if walked and faced else 1


if __name__ == '__main__':
    sys.exit(Approach(parse(sys.argv)).run())
