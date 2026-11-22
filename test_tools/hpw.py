"""Watch 4-byte ints at given addresses while pressing a button: python diag/twin/hpw.py PORT BTN SECS ADDR..."""
import struct, sys, threading, time, json, socket
sys.path.insert(0, 'diag/twin')
from dbg import Dbg
import tctl
port, btn, secs = sys.argv[1], sys.argv[2], float(sys.argv[3])
who = {'6545': 'A', '6546': 'B'}[port]
g = Dbg(who)
addrs = [int(a, 16) for a in sys.argv[4:]]
def show(): return tuple(struct.unpack('<i', bytes.fromhex(g.call('read_memory', {'address': hex(a), 'size': 4})['hex']))[0] for a in addrs)
print('start', show())
if btn != '-':
    threading.Thread(target=lambda: tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': 8}, {'frames': 10}]}})).start()
t0 = time.time(); last = None
while time.time() - t0 < secs:
    v = show()
    if v != last:
        print('  %.2f s' % (time.time() - t0), v); last = v
    time.sleep(0.005)
