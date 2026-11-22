"""Make every enemy of the common type drop for sure, without the slow memory search of item_sources.py force:
python diag/twin/force_lot.py AB
Rewrites the lot ids in the enemies' NpcParam rows (row+0x30 20000000 -> 20000010, row+0x38 29000000 -> 29100090;
both replacements are stock rows with a 100 % weight). Rows are shared by all enemies of a type."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, ENEMY_VT

SWAP = {20000000: 20000010, 20100000: 20000010, 29000000: 29100090, 29100000: 29100090}
for who in sys.argv[1]:
    w = W(who)
    rows = set()
    for si, j, c in w.all_chrs():
        if w.q(c) != w.base + ENEMY_VT:
            continue
        data = w.q(c + 0x20)
        holder = w.q(data + 0xE8) if data else None
        row = w.q(holder + 8) if holder else None
        if row:
            rows.add(row)
    done = 0
    for row in rows:
        for o in (0x30, 0x34, 0x38):
            lot = w.i(row + o)
            if lot in SWAP:
                w.write(row + o, struct.pack('<i', SWAP[lot]))
                done += 1
    print('%s: %d NpcParam rows, %d lot ids rewritten' % (who, len(rows), done))
