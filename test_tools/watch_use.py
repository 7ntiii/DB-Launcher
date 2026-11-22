"""Presses a button in a twin game and lists which 4-byte words of a memory block change, with
their values over time. python diag/twin/watch_use.py A X e3 0xE00 0x300 [seconds=4]
BLOCK: e3 (chr entry 0 [+0x18]), data (the data module), chr (the ChrIns), or a hex address."""
import struct, sys, threading, time
sys.path.insert(0, 'diag/twin')
from dbg import Dbg
from lanlog import main_base
import tctl
who, btn, block, off, size = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4], 16), int(sys.argv[5], 16)
secs = float(sys.argv[6]) if len(sys.argv) > 6 else 4
g = Dbg(who); base = main_base(who)
def rd(a, n): return bytes.fromhex(g.call('read_memory', {'address': hex(a), 'size': n})['hex'])
def u64(a): return struct.unpack('<Q', rd(a, 8))[0]
world = u64(base + 0x5B3CD88); entries = u64(world + 0x30); chr_ = u64(entries)
where = {'e3': lambda: u64(entries + 0x18), 'data': lambda: u64(u64(chr_ + 0x20) + 0x1d0), 'chr': lambda: chr_}
start = (where[block]() if block in where else int(block, 16)) + off
first = rd(start, size); history = {}
if btn != '-':
    threading.Thread(target=lambda: tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': 8}, {'frames': 10}]}})).start()
t0 = time.time(); prev = first
while time.time() - t0 < secs:
    cur = rd(start, size); t = time.time() - t0
    for k in range(0, size, 4):
        if cur[k:k + 4] != prev[k:k + 4]:
            history.setdefault(k, [(0.0, struct.unpack_from('<i', first, k)[0])]).append((round(t, 2), struct.unpack_from('<i', cur, k)[0]))
    prev = cur
for k in sorted(history):
    h = history[k]
    f0 = struct.unpack('<f', struct.pack('<i', h[0][1]))[0]; f1 = struct.unpack('<f', struct.pack('<i', h[-1][1]))[0]
    print('%s+%#x: %d changes, int %d -> %d, float %.3f -> %.3f, first %s' % (block, off + k, len(h) - 1, h[0][1], h[-1][1], f0, f1, h[1:4]))
print('watched', hex(start), hex(size))
