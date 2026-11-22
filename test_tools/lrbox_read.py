import sys
sys.path.insert(0,'diag/twin')
from mem import Mem
for g in 'AB':
    m=Mem(g)
    print(g,'LRBOX uses',m.u32(m.base+0xC50F8F0),'hook word %08x'%m.u32(m.base+0x3FFB864))
