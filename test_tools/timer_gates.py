"""READ-ONLY (diag/net/timer_notes.md): every input of the match-timer HUD question, in one line per game.
python diag/twin/timer_gates.py WHO           one line for game WHO (A, B, C, D)
python diag/twin/timer_gates.py AB diff       one line per game, then only the fields that differ
Run it on host and guest in Phases I-III and in the final, and compare the lines. Nothing is written.

Fields (each pointer is checked; "-" = null or not readable):
  phase   stage+0x50 step (6 = UpdatePhase)      round   stage+0xB8 (4 = the final)
  clock   f32 [stage+0x120]+8, the value the HUD copies every frame (0x12A2734..0x12A276C)
  coord   stage+0x3388 != 0 (the final's coordinator; hides panel byte +0x2630+0x128 on every game)
  fade    byte [main+0x5B99BB0]+0x7DB9 (== 3 hides that byte)  hud88   u32 [main+0x5B76C38]+0x88 (== 0 hides)
  auth    u32 main+0x492AFD8 (cave 3: 0 = this game is the authority, 1 = another game is)
  own     own player number (net table +0x28 / +0x20 -> +0xD0)
  in      numbers of the pool copies with take-part byte +0x46A0 == 1 and state stage byte 1
  leader  1 when own is the lowest number of `in` (the game whose clock the assist never corrects)
  hudclk / hudrnd / hudskip   the HUD data block D = [main+0x5B76C30] + 0x49BB0 (0x14A5F64 -> 0x1A8E880 ->
          0x1A8EDCC..0x12A1620 [V]): D+0x1D8 = the clock copy the dial prints, D+0x1D4 = round, D+0x183 != 0 makes
          0x12A1620 skip the whole update (copy frozen)
  dclk / dhud   change of clock and hudclk over 1.0 s (about -1.0 = counting; 0 = pinned or frozen)
  hud     the HUD object H of 0x12E32E0 (no global): found by scanning [main+0x5B76C30] .. +0x80000 for a qword
          == D at H+0x9D0 [I]; then pan = H+0x2630 bytes +0 (last w21) / +0x128 (shown flag) / +0x90 / +0x91,
          on = H+0x7CA, txt = H+0x302C (the last number the dial printed). "-" when not found.
          timer_notes 7: H is a HEAP object, so pass it: TIMER_HUD_A=0x... TIMER_HUD_B=0x... (x0 printed by
          `python diag/twin/bpprobe.py A 3 12E32E0`); "not-H" = the address has no H vtable (main+0x57068B8).
  vis     [H+0x7C0]+0x1DC (the window's layout is visible)   fo / fi   H+0x7C8 / +0x7C9 (fade-out / fade-in running)
  d9d4    D+0x9D4 (1 = the HUD took its "area changed" path this frame instead of the panel state machine)"""
import os
import struct
import sys
import time
sys.path.insert(0, 'diag/twin')
from mem import Mem

STAGE, NET, AUTH = 0x5B3CDF8, 0x5B57EB8, 0x492AFD8
FE, HUD_DATA = 0x5B76C30, 0x49BB0
FADE_OBJ, FADE_OFF, HUD_OBJ, HUD_OFF = 0x5B99BB0, 0x7DB9, 0x5B76C38, 0x88
P_STATE, P_ROUND, P_CLOCK, P_FINAL = 0x50, 0xB8, 0x120, 0x3388
PGD_LOCAL, PGD_LOCAL_ALT, PGD_POOL, PGD_SIZE, PGD_MAX = 0x20, 0x28, 0x30, 0x47F0, 12
ORDER = ('phase', 'round', 'clock', 'coord', 'fade', 'hud88', 'auth', 'own', 'in', 'leader', 'hudclk', 'hudrnd',
         'hudskip', 'dclk', 'dhud', 'hud', 'pan0', 'pan128', 'pan90', 'pan91', 'on', 'txt', 'vis', 'fo', 'fi',
         'd9d4')


def ok(p):
    return p and p < (1 << 48) and p % 8 == 0


class Reader:
    def __init__(self, who):
        self.m = Mem(who)

    def rd(self, a, n):
        try:
            return self.m.read(a, n)
        except Exception:
            return None

    def ptr(self, a):
        b = self.rd(a, 8)
        p = struct.unpack('<Q', b)[0] if b else 0
        return p if ok(p) else 0

    def num(self, a, fmt):
        b = self.rd(a, struct.calcsize(fmt))
        return struct.unpack('<' + fmt, b)[0] if b else None


def clocks(r):
    base = r.m.base
    stage = r.ptr(base + STAGE)
    clock = r.ptr(stage + P_CLOCK) if stage else 0
    c = r.num(clock + 8, 'f') if clock else None
    fe = r.ptr(base + FE)
    h = r.num(fe + HUD_DATA + 0x1D8, 'f') if fe else None
    return c, h


def find_hud(r, fe, d):
    want = struct.pack('<Q', d)
    for start in range(0, 0x80000, 0x10000):
        blob = r.rd(fe + start, 0x10000)
        if not blob:
            continue
        at = blob.find(want)
        while at != -1:
            if at % 8 == 0 and (fe + start + at - 0x9D0) % 8 == 0:
                hud = fe + start + at - 0x9D0
                if r.ptr(hud):          # an object: vtable pointer first
                    return hud
            at = blob.find(want, at + 1)
    return 0


def gates(who):
    r = Reader(who)
    c0, h0 = clocks(r)
    t0 = time.time()
    base = r.m.base
    f = dict.fromkeys(ORDER, '-')
    stage = r.ptr(base + STAGE)
    if stage:
        v = r.num(stage + P_STATE, 'I')
        f['phase'] = str(v) if v is not None else '-'
        v = r.num(stage + P_ROUND, 'I')
        f['round'] = str(v) if v is not None else '-'
        clock = r.ptr(stage + P_CLOCK)
        if clock:
            v = r.num(clock + 8, 'f')
            f['clock'] = f'{v:.1f}' if v is not None else '-'
        coord = r.ptr(stage + P_FINAL)
        f['coord'] = '1' if coord else '0'
    obj = r.ptr(base + FADE_OBJ)
    if obj:
        v = r.num(obj + FADE_OFF, 'B')
        f['fade'] = str(v) if v is not None else '-'
    obj = r.ptr(base + HUD_OBJ)
    if obj:
        v = r.num(obj + HUD_OFF, 'I')
        f['hud88'] = str(v) if v is not None else '-'
    v = r.num(base + AUTH, 'I')
    f['auth'] = str(v) if v is not None else '-'
    net = r.ptr(base + NET)
    own = None
    if net:
        local = [p for p in (r.ptr(net + PGD_LOCAL_ALT), r.ptr(net + PGD_LOCAL)) if p]
        for p in local:
            v = r.num(p + 0xD0, 'i')
            if v is not None and v > 0:
                own = v
                break
        f['own'] = str(own) if own else '-'
        pool = r.ptr(net + PGD_POOL)
        nos = set()
        for k in range(PGD_MAX if pool else 0):
            p = pool + k * PGD_SIZE
            no = r.num(p + 0xD0, 'i')
            part = r.num(p + 0x46A0, 'B')
            stage_b = r.num(p + 0x46B0, 'B')
            if no and 0 < no < 0x100 and part == 1 and stage_b == 1:
                nos.add(no)
        if own:
            nos.add(own)  # the own copy may sit outside the pool
        f['in'] = ','.join(str(n) for n in sorted(nos)) or '-'
        f['leader'] = ('1' if own == min(nos) else '0') if own and nos else '-'
    fe = r.ptr(base + FE)
    if fe:
        d = fe + HUD_DATA
        v = r.num(d + 0x1D8, 'f')
        f['hudclk'] = f'{v:.1f}' if v is not None else '-'
        v = r.num(d + 0x1D4, 'I')
        f['hudrnd'] = str(v) if v is not None else '-'
        v = r.num(d + 0x183, 'B')
        f['hudskip'] = str(v) if v is not None else '-'
        v = r.num(d + 0x9D4, 'B')
        f['d9d4'] = str(v) if v is not None else '-'
        # timer_notes 7: H is a heap object (0x5830 B, vt main+0x57068B8), so the FE scan below usually misses
        # it. Give it per game: TIMER_HUD_A=0x... (x0 of `python diag/twin/bpprobe.py A 3 12E32E0`).
        hud = int(os.environ.get('TIMER_HUD_' + who, '0'), 16) or find_hud(r, fe, d)
        if hud and r.ptr(hud) != base + 0x57068B8:
            f['hud'] = 'not-H'
            hud = 0
        if hud:
            layout = r.ptr(hud + 0x7C0)
            v = r.num(layout + 0x1DC, 'B') if layout else None
            f['vis'] = str(v) if v is not None else '-'
            for key, off in (('fo', 0x7C8), ('fi', 0x7C9)):
                v = r.num(hud + off, 'B')
                f[key] = str(v) if v is not None else '-'
            f['hud'] = f'+{hud - fe:#x}'
            pan = hud + 0x2630
            for key, off in (('pan0', 0), ('pan128', 0x128), ('pan90', 0x90), ('pan91', 0x91)):
                v = r.num(pan + off, 'B')
                f[key] = str(v) if v is not None else '-'
            v = r.num(hud + 0x7CA, 'B')
            f['on'] = str(v) if v is not None else '-'
            v = r.num(hud + 0x302C, 'f')
            f['txt'] = f'{v:.1f}' if v is not None else '-'
    time.sleep(max(0.0, 1.0 - (time.time() - t0)))
    c1, h1 = clocks(r)
    if c0 is not None and c1 is not None:
        f['dclk'] = f'{c1 - c0:+.1f}'
    if h0 is not None and h1 is not None:
        f['dhud'] = f'{h1 - h0:+.1f}'
    return f


def line(who, f):
    return who + ' ' + ' '.join(f'{k}={f[k]}' for k in ORDER)


def main():
    args = sys.argv[1:]
    if not args or any(c not in 'ABCD' for c in args[0]):
        print(__doc__)
        return 2
    games = list(args[0])
    got = {w: gates(w) for w in games}
    for w in games:
        print(line(w, got[w]))
    if 'diff' in args[1:] and len(games) >= 2:
        diff = [k for k in ORDER if len({got[w][k] for w in games}) > 1]
        if not diff:
            print('diff: none')
        for k in diff:
            print('diff ' + k + ': ' + ' '.join(f'{w}={got[w][k]}' for w in games))
    return 0


if __name__ == '__main__':
    sys.exit(main())
