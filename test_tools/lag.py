"""Measures how late one twin player's movement shows up in the other game, and the gap between the
two phase clocks. python diag/twin/lag.py [MOVER=A] [SECONDS=10]
Both games must be in UpdatePhase (phase 6). Uses one kept-open debug-server connection per game
(no child processes), samples about 60 times a second, teleports the mover 3 m after 1 s
and reports when the mover's own position and the viewer's copy of it start and stop moving."""
import json
import math
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from lanlog import main_base

from dbg import Dbg


def onset(samples, i, ref, limit, after=0.0):
    for t, row in samples:
        if t >= after and math.dist(row[i][::2], ref[::2]) > limit:
            return t
    return None


mover = sys.argv[1] if len(sys.argv) > 1 else 'A'
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 10
viewer = 'B' if mover == 'A' else 'A'
gm, gv = Dbg(mover), Dbg(viewer)
t0 = time.time(); cm = gm.clock(); t1 = time.time(); cv = gv.clock(); t2 = time.time()
print(f'phase clock left: {mover} {cm:.2f} s, {viewer} {cv:.2f} s -> {viewer} - {mover} = {cv - cm + (t2 - t0) / 2:+.2f} s '
      f'(read took {1000 * (t2 - t0):.0f} ms)')
pm = gm.phys()[0]
start = gm.pos(pm)
copies = [(math.dist(gv.pos(p), start), p) for p in gv.phys()[1:] if p]
dist, pc = min(copies)
print(f'{mover} at ({start[0]:.1f},{start[1]:.1f},{start[2]:.1f}); {viewer}\'s copy of it is {dist:.2f} m off')
c0 = gv.pos(pc)


WALK = '--walk' in sys.argv


def push():
    """a 3 m sideways teleport of the mover (one memory write, exact time); with --walk a smooth
    3 m slide over 1.5 s written 60 times a second instead"""
    time.sleep(1.0)
    g = Dbg(mover)
    steps = 90 if WALK else 1
    for i in range(1, steps + 1):
        x = start[0] + 3.0 * i / steps
        g.call('write_memory', {'address': hex(pm + 0x70), 'hex': struct.pack('<f', x).hex(), 'code': False})
        if WALK:
            time.sleep(1.5 / steps)
    print('move written, done at %.3f s' % (time.time() - begin))


begin = time.time()
threading.Thread(target=push, daemon=True).start()
samples = []
while time.time() - begin < dur:
    t = time.time() - begin
    samples.append((t, (gm.pos(pm), gv.pos(pc))))
print(f'{len(samples)} samples, {len(samples) / dur:.0f} per second')
a = onset(samples, 0, start, 0.15)
b = onset(samples, 1, c0, 0.15)
for mark in (0.5, 1.5, 2.5):
    ta, tb = onset(samples, 0, start, mark), onset(samples, 1, c0, mark)
    if ta is not None and tb is not None:
        print(f'  passes {mark} m: own {ta:.2f} s, copy {tb:.2f} s, lag {tb - ta:.2f} s')
print(f'{mover} starts moving at {a if a is None else round(a, 2)} s, {viewer}\'s copy at {b if b is None else round(b, 2)} s'
      + (f' -> delay {b - a:.2f} s' if a is not None and b is not None else ''))
end_m, end_c = samples[-1][1]
print(f'{mover} moved {math.dist(end_m[::2], start[::2]):.2f} m, the copy moved {math.dist(end_c[::2], c0[::2]):.2f} m, '
      f'end gap {math.dist(end_m, end_c):.2f} m')
step = max(1, len(samples) // 30)
for t, (m, c) in samples[::step]:
    print(f'  {t:5.2f}s  own {math.dist(m[::2], start[::2]):6.2f} m   copy {math.dist(c[::2], c0[::2]):6.2f} m')
