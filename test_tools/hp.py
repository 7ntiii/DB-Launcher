"""Health of a twin game's own character. The master value is chr-set entry 0 -> [+0x18] + 0xF30
(a copy at +0xF00 and the data module's at [[chr+0x20]+0x1d0]+8 follow it every frame; max at +4).
python diag/twin/hp.py A            print the three copies and the max
python diag/twin/hp.py A set 100    write the master
python diag/twin/hp.py A press X 6  set nothing, press a button and print every change for N seconds"""
import struct, sys, threading, time
sys.path.insert(0, 'diag/twin')
from dbg import Dbg
from lanlog import main_base
import tctl
who = sys.argv[1]
import os
g = Dbg(who); base = int(os.environ['DUSK_BASE'], 16) if os.environ.get('DUSK_BASE') else main_base(who)
def rd(a, n): return bytes.fromhex(g.call('read_memory', {'address': hex(a), 'size': n})['hex'])
def u64(a): return struct.unpack('<Q', rd(a, 8))[0]
world = u64(base + 0x5B3CD88); entries = u64(world + 0x30); chr_ = u64(entries)
data = u64(u64(chr_ + 0x20) + 0x1d0); e3 = u64(entries + 0x18)
c = [data + 8, e3 + 0xF00, e3 + 0xF30]
def show(): return tuple(struct.unpack('<i', rd(a, 4))[0] for a in c) + (struct.unpack('<i', rd(data + 12, 4))[0],)
if len(sys.argv) > 3 and sys.argv[2] == 'setdata':
    g.call('write_memory', {'address': hex(c[0]), 'hex': struct.pack('<i', int(sys.argv[3])).hex()})
    time.sleep(0.3)
if len(sys.argv) > 3 and sys.argv[2] == 'set':
    g.call('write_memory', {'address': hex(c[2]), 'hex': struct.pack('<i', int(sys.argv[3])).hex()})
    time.sleep(0.3)
print('data, +F00, master, max:', show(), 'e3', hex(e3))
if len(sys.argv) > 3 and sys.argv[2] == 'press':
    btn = sys.argv[3]; secs = float(sys.argv[4]) if len(sys.argv) > 4 else 6
    threading.Thread(target=lambda: tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': 6}, {'frames': 10}]}})).start()
    t0 = time.time(); last = None
    while time.time() - t0 < secs:
        v = show()
        if v != last:
            print('  %.2f s' % (time.time() - t0), v); last = v
        time.sleep(0.005)
