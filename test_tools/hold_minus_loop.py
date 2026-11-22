"""TEST ONLY. Hold Minus on rig game WHO every few seconds for SECS, to open an incoming alliance petition.
python diag/twin/pkgtest.py run diag/twin/hold_minus_loop.py WHO [SECS=60]"""
import sys, time
sys.path.insert(0, 'diag/twin')
import tctl
who = sys.argv[1]
end = time.time() + (float(sys.argv[2]) if len(sys.argv) > 2 else 60)
while time.time() < end:
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['Minus'], 'frames': 90}, {'frames': 30}]}})
    print(time.strftime('%H:%M:%S'), 'held Minus', flush=True)
    time.sleep(1.0)
