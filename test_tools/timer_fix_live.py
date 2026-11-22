"""TIMER_MODE live check (diag/net/timer4_notes.md, record from diag/net/timer_mode_gen.py). Game A only by default.
    python diag/twin/timer_fix_live.py [A]          code word + refresh (uses the cached H only, no heap search)
    python diag/twin/timer_fix_live.py [A] undo     stock word back + refresh
    python diag/twin/timer_fix_live.py [A] find     only fill the H cache (sliced heap search, 0.1 s slices with
                                                    0.4 s pauses; run it BEFORE the final, e.g. in Phase III)
1. main+0x12C91A8: E8 07 9F 1A (cset w8, ne) <-> E8 03 1F 2A (mov w8, wzr), checked first, written with code=True.
2. Refresh: [H+0x54F0]+0x74 = 0xFFFFFFFF (the phase clock rebuilds when par+0xC8 differs from it, next frame).
   H comes from diag/twin/.h_cache_<game> and is checked (vt main+0x57068B8, H+0x9D0 == D). No cache -> no refresh,
   the word is still written (it then takes effect at the next phase change only).
Expected after the fix on the host in the final: timer_probe4 shows shown+A=0, vec+20=6, +14 > 0; the countdown shows."""
import sys

sys.path.insert(0, 'diag/twin')
from timer_probe2 import R, FE, HUD_DATA, H_VT, _h_cache, find_h  # noqa: E402

OFF, STOCK, NEW = 0x12C91A8, 'e8079f1a', 'e8031f2a'
PHASE_CLOCK, STAMP = 0x54F0, 0x74

args = sys.argv[1:]
games = next((a for a in args if a.isalpha() and a.isupper()), 'A')
undo, find = 'undo' in args, 'find' in args

for g in games:
    r = R(g)
    fe = r.ptr(r.base + FE)
    d = fe + HUD_DATA if fe else 0
    if find:
        _, match = find_h(r, d)
        print(g, 'H', '%#x cached' % match[0] if match else 'NOT found (no cache written)')
        continue
    have = (r.rd(r.base + OFF, 4) or b'').hex()
    want = STOCK if undo else NEW
    if have == want:
        print(g, 'main+%#x already %s' % (OFF, want))
    elif have in (STOCK, NEW):
        r.m.write(r.base + OFF, bytes.fromhex(want), code=True)
        print(g, 'main+%#x %s -> %s%s' % (OFF, have, want, ' (undo)' if undo else ''),
              '; reads back', (r.rd(r.base + OFF, 4) or b'').hex())
    else:
        print(g, 'main+%#x is %s, neither stock nor fix: NOT written, stop' % (OFF, have or 'unreadable'))
        continue
    h = None
    try:
        h = int(open(_h_cache(r)).read().strip(), 16)
    except Exception:
        print(g, 'no H cache (%s): no refresh. Run "timer_fix_live.py %s find" first, outside the final.' % (_h_cache(r), g))
        continue
    if not (r.ptr(h) == r.base + H_VT and r.ptr(h + 0x9D0) == d):
        print(g, 'cached H %#x is stale (vt / D differ): no refresh. Run "find" again.' % h)
        continue
    o = r.ptr(h + PHASE_CLOCK)
    if not o:
        print(g, 'H %#x: no phase clock object at +0x54F0: no refresh' % h)
        continue
    before = r.num(o + STAMP, 'I')
    r.m.write(o + STAMP, b'\xff\xff\xff\xff')
    print(g, 'phase clock %#x +0x74 %s -> 0xffffffff (refresh next frame); mode byte +0xA now %s' % (
        o, before, r.num(o + 0xA, 'B')))
