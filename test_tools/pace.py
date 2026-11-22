"""Makes a twin player pace back and forth (position writes 60 times a second, about 2 m/s over 5 m), so
the assists have movement to compare. python diag/twin/pace.py A|B|AB SECONDS"""
import struct, sys, threading, time
sys.path.insert(0, 'diag/twin')
from dbg import Dbg
def pace(who, secs):
    g = Dbg(who); pm = g.phys()[0]; x0, y0, z0 = g.pos(pm); t0 = time.time()
    while time.time() - t0 < secs:
        t = time.time() - t0
        k = (t * 2.0) % 10.0
        g.call('write_memory', {'address': hex(pm + 0x70), 'hex': struct.pack('<f', x0 + (k if k < 5 else 10 - k)).hex(), 'code': False})
        time.sleep(1 / 60)
    g.call('write_memory', {'address': hex(pm + 0x70), 'hex': struct.pack('<f', x0).hex(), 'code': False})
if __name__ == '__main__':
    ts = [threading.Thread(target=pace, args=(w, float(sys.argv[2]))) for w in sys.argv[1]]
    [t.start() for t in ts]; [t.join() for t in ts]
