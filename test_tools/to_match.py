"""Both twin games from the hub: Minus (menu) then Y (matchmaking) together; shots after 12 s."""
import sys, threading, time
sys.path.insert(0, 'diag/twin')
from tctl import call
def press(w, b): call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [b], 'frames': 6}, {'frames': 30}]}})
def both(f, *a):
    ts = [threading.Thread(target=f, args=(w,) + a) for w in 'AB']
    [t.start() for t in ts]; [t.join() for t in ts]
for b in sys.argv[1:] or ['Minus', 'Y']:
    both(press, b); time.sleep(4)
print('pressed', time.strftime('%H:%M:%S'), flush=True)
time.sleep(12)
both(lambda w: call(w, {'method': 'screenshot', 'params': {'height': 480}}, f'diag/twin/{w}_mm.png'))
