"""TEST ONLY: set an enemy chr's HP on one game (use on the authority).  python diag/twin/sethp.py A CHR HP"""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1]); chr_ = int(sys.argv[2], 16); hp = int(sys.argv[3])
mod = m.u64(m.u64(chr_ + 0x2470) + 0x18)
print('hp before', m.u32(mod + 0x290), '/', m.u32(mod + 0x294))
m.write(mod + 0x290, struct.pack('<I', hp))
print('hp after', m.u32(mod + 0x290))
