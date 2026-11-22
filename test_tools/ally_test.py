"""Alliance round trip on the twin rig: python diag/twin/ally_test.py [FROM=A] [TO=B] [accept|decline]
FROM opens the map (Plus), the Bloodsworn list (X) and petitions (A); TO holds Minus on the notice
("Check") and picks Enter alliance (A) or Decline (Right, A). Prints the alliance count AM+0x38 of both."""
import sys, threading, time
sys.path.insert(0, 'diag/twin')
import tctl
from mem import Mem
src = sys.argv[1] if len(sys.argv) > 1 else 'A'
dst = sys.argv[2] if len(sys.argv) > 2 else 'B'
answer = sys.argv[3] if len(sys.argv) > 3 else 'accept'
def press(w, b, wait=45): tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [b], 'frames': 5}, {'frames': wait}]}})
def shot(w, tag): tctl.call(w, {'method': 'screenshot', 'params': {'height': 720}}, 'diag/twin/%s_%s.png' % (w, tag))
def count(): return {w: Mem(w).u32(Mem(w).u64(Mem(w).base + 0x5B3CDD0) + 0x38) for w in (src, dst)}
print('before', count())
for k in range(3): press(dst, 'B', 15)
press(src, 'Plus'); press(src, 'X', 50)
t = threading.Thread(target=lambda: tctl.call(dst, {'method': 'input_sequence', 'params': {'steps': [{'frames': 45}, {'buttons': ['Minus'], 'frames': 90}, {'frames': 40}]}}))
t.start(); press(src, 'A', 20); t.join()
shot(dst, 'ally_dialog')
if answer == 'decline':
    press(dst, 'Right', 20)
press(dst, 'A', 90)
shot(dst, 'ally_after'); shot(src, 'ally_after')
for k in range(3): press(src, 'B', 15)
print('after', count())
