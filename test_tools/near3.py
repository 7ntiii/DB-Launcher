"""Enemies near a player, as game WHO sees them (read only).
python diag/twin/near3.py WHO NO [radius=80]   NO = player number to measure from"""
import math
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402
import npcs  # noqa: E402
from world_lib import W  # noqa: E402
from starfrag import player_positions  # noqa: E402

who, no = sys.argv[1], int(sys.argv[2])
rad = float(sys.argv[3]) if len(sys.argv) > 3 else 80.0
w = W(who)
me = player_positions(w).get(no)
if me is None or not all(math.isfinite(v) for v in me):
    print('no valid position for player', no)
    sys.exit(2)
m = Mem(who)
rows = []
for e in npcs.find(m):
    p = e['pos']
    if not all(math.isfinite(v) for v in p) or (p[0] == 0.0 and p[2] == 0.0):
        continue
    d = math.sqrt((p[0] - me[0]) ** 2 + (p[2] - me[2]) ** 2)
    if d <= rad:
        try:
            hp = m.u32(m.u64(m.u64(e['chr'] + 0x2470) + 0x18) + 0x290)
        except Exception:
            hp = None
        rows.append((d, p[1] - me[1], e, hp))
rows.sort(key=lambda r: r[0])
print('player', no, 'at (%.1f %.1f %.1f); %d enemies within %.0f m' % (me[0], me[1], me[2], len(rows), rad))
import os
if os.environ.get("NEAR_HP"):
    rows = [r for r in rows if r[3] == int(os.environ["NEAR_HP"])]
for d, dy, e, hp in rows[:10]:
    print('  %5.1f m  dy %+5.1f  chr %x  flags %x  hp %s  pos (%.1f %.1f %.1f)' % (
        d, dy, e['chr'], e['flags'] & 0xFF, hp, e['pos'][0], e['pos'][1], e['pos'][2]))
