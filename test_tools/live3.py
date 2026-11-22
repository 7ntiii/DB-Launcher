"""Live 3-player test helper (rig games only).
python diag/twin/live3.py WHO where            every player's position as game WHO sees it
python diag/twin/live3.py WHO bring NO [dist]  teleport WHO's OWN player to `dist` m (default 2.5) beside player NO
Every position is validated (finite, sane range) before the one write (W.goto)."""
import math
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, dist, fmt3  # noqa: E402
from starfrag import player_positions  # noqa: E402


def ok(p):
    return p is not None and len(p) == 3 and all(isinstance(v, float) and math.isfinite(v) and abs(v) < 20000 for v in p)


def own_no(w):
    for e in w.players():
        pass
    try:
        return w.own_no()
    except Exception:
        return None


who, cmd = sys.argv[1], sys.argv[2]
w = W(who)
pos = player_positions(w)
if cmd == 'where':
    for no in sorted(pos):
        print(who, 'player', no, fmt3(pos[no]) if ok(pos[no]) else 'INVALID %r' % (pos[no],))
    sys.exit(0)
if cmd == 'bring':
    no = int(sys.argv[3])
    d = float(sys.argv[4]) if len(sys.argv) > 4 else 2.5
    if no not in pos or not ok(pos[no]):
        print('REFUSED: no valid position for player', no, pos.get(no))
        sys.exit(2)
    t = pos[no]
    dest = (t[0] + d, t[1] + 0.3, t[2])
    if not ok(dest):
        print('REFUSED: bad destination', dest)
        sys.exit(2)
    w.goto(dest)
    print(who, 'moved beside player', no, 'to', fmt3(dest))
    sys.exit(0)
if cmd == 'to':
    dest = tuple(float(v) for v in sys.argv[3:6])
    if not ok(dest):
        print('REFUSED: bad destination', dest)
        sys.exit(2)
    w.goto(dest)
    print(who, 'moved to', fmt3(dest))
    sys.exit(0)
print(__doc__)
