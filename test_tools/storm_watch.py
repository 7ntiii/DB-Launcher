"""storm_watch: READ ONLY. Watches the storm (environment event 1140) on the rig games and logs what it does.
    python diag/twin/pkgtest.py run diag/twin/storm_watch.py AB [seconds=3600]
Every second, per game, a few small reads (no writes, no breakpoints; safe in a long match):
  S = *(par + 0x2D0), par = *(main+0x5B3CDF8): the storm step object (event_effects_notes.md 1.1 [V]);
  S+0x50 step (3 WaitIndication .. 6 Execute, 7 WaitWarpEnd, 8 FinishProcess, 9 Finish), S+0x2F0 entry count,
  entries at S+0xE0 aligned to 16, stride 0x40: +0 player number, +0x10 target (x, y, z);
  our own player's position (WCM player entry 0, physics +0x70).
Lines (only on a change):
  "HH:MM:SS A: storm step 3 -> 4 (entries 3)"
  "HH:MM:SS A: storm entries p1 -> (x, y, z), p2 -> (...)"
  "HH:MM:SS A: our player p1 moved 84.1 m: (x, y, z) -> (x, y, z) at step 6"   (a jump > 20 m within 2 s)
At the end (or Ctrl+C): "HH:MM:SS A: storm summary: highest step N, entries M, moved yes/no, our entry (x, y, z)".
PASS for the card: each game reaches step >= 6 with the same entries, and each game's own player moved to its
own entry. FAIL: a game stays at step 3 while another reached 4+ (no 0xC8 record arrived), or entries differ."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, PAR_G  # noqa: E402

STEP_NAMES = {0: 'Init', 1: 'PhasePrepare', 2: 'WaitPhaseStart', 3: 'WaitIndication', 4: 'Indication',
              5: 'WaitExecute', 6: 'Execute', 7: 'WaitWarpEnd', 8: 'FinishProcess', 9: 'Finish'}


def fmt3(p):
    return '(%.1f, %.1f, %.1f)' % p if p else '?'


def snap(w):
    par = w.g(PAR_G)
    s = w.q(par + 0x2D0) if par else None
    out = {'step': None, 'n': None, 'entries': [], 'pos': None, 'no': None}
    if s:
        out['step'] = w.d(s + 0x50)
        n = w.d(s + 0x2F0)
        out['n'] = n
        if n is not None and 0 < n <= 8:
            base = s + 0xE0 + ((-(s + 0xE0)) & 8)
            raw = w.rd(base, 0x40 * n)
            if raw:
                for k in range(n):
                    no = struct.unpack_from('<I', raw, 0x40 * k)[0]
                    out['entries'].append((no, struct.unpack_from('<3f', raw, 0x40 * k + 0x10)))
    chr_, phys, pos = w.me()
    out['pos'] = pos
    if chr_:
        d = w.q(chr_ + 0x20)
        pgd = w.q(d + 0x1D0) if d else None
        out['no'] = w.d(pgd + 0xD0) if pgd else None
    return out


def main(argv):
    games = argv[1] if len(argv) > 1 else 'AB'
    run_s = float(argv[2]) if len(argv) > 2 else 3600
    ws = {g: W(g) for g in games}
    last = {g: None for g in games}
    best = {g: {'step': 0, 'n': 0, 'moved': False, 'entry': None} for g in games}
    print(time.strftime('%H:%M:%S'), 'storm_watch', games, 'for', int(run_s), 's', flush=True)
    t_end = time.time() + run_s
    try:
        while time.time() < t_end:
            for g, w in ws.items():
                try:
                    s = snap(w)
                except Exception as e:  # a game gone: report once, keep going
                    if last[g] != 'gone':
                        print(time.strftime('%H:%M:%S'), '%s: no read (%s)' % (g, str(e)[:60]), flush=True)
                    last[g] = 'gone'
                    continue
                p = last[g] if isinstance(last[g], dict) else None
                t = time.strftime('%H:%M:%S')
                if p is None or s['step'] != p['step']:
                    if s['step'] is not None and p is not None and p['step'] is not None:
                        print(t, '%s: storm step %s -> %s %s (entries %s)' % (
                            g, p['step'], s['step'], STEP_NAMES.get(s['step'], '?'), s['n']), flush=True)
                if s['entries'] and (p is None or s['entries'] != p['entries']):
                    print(t, '%s: storm entries %s' % (g, ', '.join('p%d -> %s' % (no, fmt3(xyz))
                                                                    for no, xyz in s['entries'])), flush=True)
                if p and p['pos'] and s['pos'] and math.dist(p['pos'], s['pos']) > 20:
                    print(t, '%s: our player p%s moved %.1f m: %s -> %s at step %s' % (
                        g, s['no'], math.dist(p['pos'], s['pos']), fmt3(p['pos']), fmt3(s['pos']), s['step']),
                        flush=True)
                    if (s['step'] or 0) >= 5:
                        best[g]['moved'] = True
                b = best[g]
                b['step'] = max(b['step'], s['step'] or 0) if (s['step'] or 0) <= 9 else b['step']
                b['n'] = max(b['n'], s['n'] or 0) if (s['n'] or 0) <= 8 else b['n']
                own = [xyz for no, xyz in s['entries'] if no == s['no']]
                if own:
                    b['entry'] = own[0]
                last[g] = s
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    for g in games:
        b = best[g]
        print(time.strftime('%H:%M:%S'), '%s: storm summary: highest step %d, entries %d, moved %s, our entry %s'
              % (g, b['step'], b['n'], 'yes' if b['moved'] else 'no', fmt3(b['entry'])), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
