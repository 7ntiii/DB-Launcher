"""Tap a button on rig game WHO: python diag/twin/pressy.py WHO BTN [times]"""
import sys, time
sys.path.insert(0, 'diag/twin')
import tctl
who, btn = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
for _ in range(n):
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': 6}, {'frames': 12}]}})
    time.sleep(0.4)
print('pressed', btn, n)
