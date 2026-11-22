"""TEST ONLY: clear the take-request mark (bit 14 of node +0x58) on WHO's own per-player items so the auto-take
runs again; prints taken (+0x288) / allowed (+0x290) masks.   usage: python diag/twin/retake.py A [read]"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

who = sys.argv[1]
m = Mem(who)
mi = m.u64(m.base + 0x5B3CDC0)
node, n = m.u64(mi + 0x1B8), 0
while node and n < 64:
    iid = m.u32(node + 0x30)
    f = m.u32(node + 0x58)
    print('%s node %x id %08x +58 %08x taken(+288) %x allowed(+290) %x' % (
        who, node, iid, f, m.u64(node + 0x288), m.u64(node + 0x290)))
    if 'read' not in sys.argv and f & 0x4000:
        m.write(node + 0x58, struct.pack('<I', f & ~0x4000))
        print('   cleared 0x4000 -> %08x' % m.u32(node + 0x58))
    node, n = m.u64(node + 8), n + 1
