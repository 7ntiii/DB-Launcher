"""Teleport a twin game's own player: python diag/twin/goto.py A X Y Z"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

m = Mem(sys.argv[1])
e = m.u64(m.u64(m.base + 0x5B3CD88) + 0x30)
phys = m.u64(e + 0x28)
m.write(phys + 0x70, struct.pack('<3f', *(float(v) for v in sys.argv[2:5])))
print(sys.argv[1], 'at', sys.argv[2:5])
