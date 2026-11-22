"""World items of the twin games (MapItemMan = *(main+0x5B3CDC0); lists at +0x18 / +0x48 / +0x78, next = node+0x10,
id at node+0x30): python diag/twin/items.py [GAMES=AB]"""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
for w in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
    m = Mem(w); im = m.u64(m.base + 0x5B3CDC0); out = []
    for off in (0x18, 0x48, 0x78):
        node, ids = m.u64(im + off), []
        while node and len(ids) < 200:
            try:
                ids.append('%x' % m.u32(node + 0x30)); node = m.u64(node + 0x10)
            except Exception:
                break
        out.append(ids)
    print(w, [len(x) for x in out], out)
