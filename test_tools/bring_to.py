"""Bring both rig players next to another player (test only).
python diag/twin/bring_to.py NO      NO = the target's player number (as game A sees it); A and B land 1.5 m beside it"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402
from world_lib import W  # noqa: E402
from starfrag import player_positions  # noqa: E402

no = int(sys.argv[1])
pos = None
for who in 'AB':
    seen = player_positions(W(who))
    print(who, 'sees', {k: tuple(round(v, 1) for v in p) for k, p in seen.items()})
    if pos is None and no in seen:
        pos = seen[no]
if pos is None:
    sys.exit(f'player {no} not seen')
for who, dx in (('A', 1.5), ('B', -1.5)):
    m = Mem(who)
    e = m.u64(m.u64(m.base + 0x5B3CD88) + 0x30)
    phys = m.u64(e + 0x28)
    m.write(phys + 0x70, struct.pack('<3f', pos[0] + dx, pos[1] + 0.5, pos[2]))
    print(who, 'moved next to player', no)
