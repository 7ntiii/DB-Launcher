"""Watch the effect-request manager while a button is pressed (heal item = Up).
python diag/twin/effwatch.py A [BUTTON=Up] [SECONDS=5] [HP]
Prints every change of each used slot's requests (0x30 bytes) and records (0x28 bytes), and the
player's HP. Manager [[main+0x59E1B28]]: slots of 0x290 from +8; requests deque +0x90 (start +0xb0,
count +0xb8, 0x55 per block), records deque +0x50 (first +0x70, count +0x78, 102 per block)."""
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl

who = sys.argv[1]
btn = sys.argv[2] if len(sys.argv) > 2 else 'Up'
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 5
m = Mem(who)
mgr = m.u64(m.u64(m.base + 0x59E1B28))
wcm = m.u64(m.base + 0x5B3CD88)
e3 = m.u64(m.u64(wcm + 0x30) + 0x18)
if len(sys.argv) > 4:
    m.write(e3 + 0xF30, struct.pack('<i', int(sys.argv[4])))
    time.sleep(0.3)


def deque(slot, off, start_off, size, per):
    mp, mend = m.u64(slot + off), m.u64(slot + off + 8)
    start, count = m.u64(slot + start_off), m.u64(slot + start_off + 8)
    out = []
    if not mp or count > 64:
        return out
    for i in range(count):
        idx = start + i
        blk = m.u64(mp + idx // per * 8)
        if not blk:
            break
        out.append(m.read(blk + idx % per * size, size).hex())
    return out


def state():
    out = {'hp': struct.unpack('<i', m.read(e3 + 0xF30, 4))[0]}
    for k in range(13):
        slot = mgr + 8 + 0x290 * k
        no = struct.unpack('<i', m.read(slot, 4))[0]
        if no == -1:
            continue
        out['p%d req' % no] = deque(slot, 0x90, 0xb0, 0x30, 0x55)
        out['p%d rec' % no] = deque(slot, 0x50, 0x70, 0x28, 102)
    return out


last = state()
print('start', last)
threading.Thread(target=lambda: tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [({'buttons': [btn], 'frames': 6} if btn != 'none' else {'frames': 6}), {'frames': 10}]}})).start()
t0 = time.time()
while time.time() - t0 < secs:
    s = state()
    for k in s:
        if s[k] != last.get(k):
            print('%.2f %s %s' % (time.time() - t0, k, s[k]), flush=True)
    last = s
