"""Push the left stick on rig game WHO: python diag/twin/stick.py WHO X Y FRAMES [BTN]   (BTN pressed afterwards)"""
import sys
sys.path.insert(0, 'diag/twin')
import tctl
who, x, y, frames = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
steps = [{'left_stick': [x, y], 'frames': frames}, {'frames': 10}]
if len(sys.argv) > 5:
    steps += [{'buttons': [sys.argv[5]], 'frames': 6}, {'frames': 12}]
print(tctl.call(who, {'method': 'input_sequence', 'params': {'steps': steps}})[:80])
