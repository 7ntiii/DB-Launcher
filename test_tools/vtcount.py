"""Count heap objects whose first qword is main+VT: python diag/twin/vtcount.py A 0x572B108 [print]
Uses the debug server's search_memory (heap), continuing with 'next' until complete."""
import time
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

m = Mem(sys.argv[1])
vt = m.base + int(sys.argv[2], 16)
pattern = struct.pack('<Q', vt).hex()
hits, start = [], None
for _ in range(4000):
    params = {'pattern': pattern, 'max_hits': 256, 'budget_ms': 100}
    if start:
        params['start'] = start
    time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
    r = m.call('search_memory', params)
    hits += [int(h, 16) if isinstance(h, str) else int(h.get('address'), 16) for h in r.get('hits', [])]
    if r.get('complete') and not r.get('next'):
        break
    start = r.get('next')
    if not start:
        break
hits = [h for h in hits if h % 8 == 0]
print(sys.argv[1], 'vt main+%s' % sys.argv[2], 'objects', len(hits))
if len(sys.argv) > 3:
    for h in hits:
        print(hex(h), hex(m.u64(h + 8)))
