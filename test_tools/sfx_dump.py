"""READ-ONLY: dump the CSSfx singleton [main+0x5B4D3E0] and one level of pointees (fire hunt)."""
import sys, struct
sys.path.insert(0, 'diag/twin')
from mem import Mem
who = sys.argv[1]
n = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x200
m = Mem(who)
addr = int(sys.argv[3], 16) if len(sys.argv) > 3 else m.u64(m.base + 0x5B4D3E0)
print(who, 'obj', hex(addr))
b = m.read(addr, n)
for o in range(0, n, 8):
    v = struct.unpack_from('<Q', b, o)[0]
    tag = ''
    if m.base <= v < m.base + 0x6B30000:
        tag = 'main+%x' % (v - m.base)
    elif v > 0x1000000000:
        try:
            tag = 'heap -> [0]=%s' % (('main+%x' % (m.u64(v) - m.base)) if m.base <= m.u64(v) < m.base + 0x6B30000 else hex(m.u64(v)))
        except Exception:
            tag = 'heap?'
    print('+%03x %016x %s' % (o, v, tag))
