"""Hold the role word (main+0x492AFD8) of a game at 1 (= not the authority) for N seconds, written every
20 ms over one connection: stands in for the assist's early role write when testing live patches."""
import struct, sys, time
sys.path.insert(0, 'diag/twin')
from dbg import Dbg
g = Dbg(sys.argv[1]); end = time.time() + float(sys.argv[2])
while time.time() < end:
    g.call('write_memory', {'address': hex(g.base + 0x492AFD8), 'hex': struct.pack('<I', 1).hex()})
    time.sleep(0.02)
