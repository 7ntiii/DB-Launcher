"""fps_watch: READ ONLY. Polls each rig game's debug-server status (fps, presents) every 2 s and logs a line
when a game stops drawing (fps < 1 or presents frozen for 4 s), and again when it draws again. Light: one status
call per game per poll, no memory reads, safe at a final's start.
    python diag/twin/fps_watch.py AB [seconds] [--low N]   (run through pkgtest.py run, like the other rig tools)
    python diag/twin/fps_watch.py --selftest
Lines:
  "HH:MM:SS B: BLACK? fps 0.0, presents 51944 unchanged for 4 s" / "HH:MM:SS B: drawing again (fps 58.9)"
  "HH:MM:SS B: LOW fps 14.2 (< 20) for 3 s"  then every 10 s while low: "HH:MM:SS B: still LOW fps 13.8 (min 12.1)"
  "HH:MM:SS B: fps back 52.0 after 41 s low (min 12.1)"
'fps' is the status call's presents per second (a 0.5-s window). In the final of joint match 2 the laptop showed
about 2 presents per game frame, so LOW < 20 is about < 9-10 game frames per second.
Made 2026-11-18 after match 5 (BLACK?); LOW added 2026-11-19 for the laptop's final frame drop (fire_m2night_notes)."""
import json
import sys
import time

LOW_FPS = 20.0
LOW_HOLD_S = 3.0
LOW_REPEAT_S = 10.0


class Watch:
    def __init__(self, low=LOW_FPS):
        self.low = low
        self.last = {}
        self.bad_since = {}
        self.black = {}
        self.low_since = {}
        self.low_min = {}
        self.low_said = {}

    def gone(self, g, err):
        if self.black.get(g) != 'gone':
            self.black[g] = 'gone'
            return ['%s: no status (%s)' % (g, str(err)[:60])]
        return []

    def step(self, g, fps, pres, now):
        out = []
        frozen = pres is not None and self.last.get(g) == pres
        self.last[g] = pres
        bad = fps < 1 or frozen
        if bad:
            self.bad_since.setdefault(g, now)
            if now - self.bad_since[g] >= 4 and self.black.get(g) is not True:
                out.append('%s: BLACK? fps %.1f, presents %s %s for %d s'
                           % (g, fps, pres, 'unchanged' if frozen else 'moving', now - self.bad_since[g]))
                self.black[g] = True
        else:
            self.bad_since.pop(g, None)
            if self.black.get(g):
                out.append('%s: drawing again (fps %.1f)' % (g, fps))
            self.black[g] = False
        # LOW: drawing, but slower than the line (a black game is BLACK?, not LOW)
        if not bad and fps < self.low:
            self.low_since.setdefault(g, now)
            self.low_min[g] = min(self.low_min.get(g, fps), fps)
            held = now - self.low_since[g]
            if g not in self.low_said and held >= LOW_HOLD_S:
                out.append('%s: LOW fps %.1f (< %g) for %d s' % (g, fps, self.low, held))
                self.low_said[g] = now
            elif g in self.low_said and now - self.low_said[g] >= LOW_REPEAT_S:
                out.append('%s: still LOW fps %.1f (min %.1f)' % (g, fps, self.low_min[g]))
                self.low_said[g] = now
        elif g in self.low_since:
            if g in self.low_said:
                out.append('%s: fps back %.1f after %d s low (min %.1f)'
                           % (g, fps, now - self.low_since[g], self.low_min[g]))
            self.low_since.pop(g, None)
            self.low_min.pop(g, None)
            self.low_said.pop(g, None)
        return out


def selftest():
    w = Watch(20)
    got = []
    t = 0.0
    pres = 1000
    # 10 s normal, 30 s at 14 fps, 4 s back to 50, 6 s frozen (black), back
    for fps in [50] * 5 + [14, 13, 12, 14, 14, 15, 14, 13, 14, 14, 14, 14, 14, 14, 14] + [50, 50]:
        pres += int(fps * 2)
        got += ['%4.0f %s' % (t, s) for s in w.step('B', fps, pres, t)]
        t += 2
    for _ in range(4):
        got += ['%4.0f %s' % (t, s) for s in w.step('B', 0.0, pres, t)]
        t += 2
    pres += 100
    got += ['%4.0f %s' % (t, s) for s in w.step('B', 50, pres, t)]
    # a single 2-s dip must not print LOW
    t += 2
    pres += 20
    got += ['%4.0f %s' % (t, s) for s in w.step('B', 10, pres, t)]
    t += 2
    pres += 100
    got += ['%4.0f %s' % (t, s) for s in w.step('B', 50, pres, t)]
    for s in got:
        print(s)
    kinds = [s.split(': ', 1)[1].split(' ')[0] + (' ' + s.split(': ', 1)[1].split(' ')[1]
                                                  if s.split(': ', 1)[1].startswith(('still', 'fps', 'drawing')) else '')
             for s in got]
    want = ['LOW', 'still LOW', 'still LOW', 'fps back', 'BLACK?', 'drawing again']
    ok = kinds == want
    print('selftest %s (%d lines: %s)' % ('PASS' if ok else 'FAIL', len(got), ', '.join(kinds)))
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if '--selftest' in args:
        return selftest()
    low = LOW_FPS
    if '--low' in args:
        i = args.index('--low')
        low = float(args[i + 1])
        del args[i:i + 2]
    games = args[0] if args else 'AB'
    run_s = float(args[1]) if len(args) > 1 else 7200
    sys.path.insert(0, __import__('os').path.dirname(__file__))
    import tctl  # noqa: E402
    w = Watch(low)
    t_end = time.time() + run_s
    print(time.strftime('%H:%M:%S'), 'fps_watch', games, 'for', int(run_s), 's (LOW < %g fps for %g s)'
          % (low, LOW_HOLD_S), flush=True)
    while time.time() < t_end:
        for g in games:
            try:
                st = json.loads(tctl.call(g, {'method': 'status'}))
            except Exception as e:  # game gone or debug server busy: report once per change
                for s in w.gone(g, e):
                    print(time.strftime('%H:%M:%S'), s, flush=True)
                continue
            for s in w.step(g, float(st.get('fps', 0) or 0), st.get('presents'), time.time()):
                print(time.strftime('%H:%M:%S'), s, flush=True)
        time.sleep(2)
    print(time.strftime('%H:%M:%S'), 'fps_watch done', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
