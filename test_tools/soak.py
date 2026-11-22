"""Back-to-back twin matches with both phases cut to 5 s: python diag/twin/soak.py MATCHES
(start with both games in their first match, e.g. right after go.sh). Prints one line per step and
stops on a hang (no progress in 5 minutes) or a PANIC in either eden log."""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl
from mem import Mem

EDEN = {'A': r'C:\Users\<user>\AppData\Roaming\eden\log\eden_log.txt', 'B': 'diag/twin/userB/log/eden_log.txt'}


def phase(w):
    try:
        m = Mem(w)
        par = m.u64(m.base + 0x5B3CDF8)
        return m.u32(par + 0x50) if par else -1
    except Exception:
        return -2


def panic():
    for w, p in EDEN.items():
        try:
            if 'PANIC' in open(p, errors='replace').read():
                return w
        except OSError:
            pass
    return None


def wait_for(pred, what, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        if panic():
            print(time.strftime('%H:%M:%S'), 'PANIC in', panic(), 'while waiting for', what, flush=True)
            sys.exit(1)
        ph = {w: phase(w) for w in 'AB'}
        if pred(ph):
            return ph
        time.sleep(2)
    print(time.strftime('%H:%M:%S'), 'HANG waiting for', what, {w: phase(w) for w in 'AB'}, flush=True)
    sys.exit(1)


for n in range(int(sys.argv[1])):
    if n or '--from-outcome' in sys.argv:
        for w in 'AB':
            if phase(w) != 36:
                continue                  # already back in the hub
            tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['A'], 'frames': 6}, {'frames': 20}]}})
        time.sleep(30)
        subprocess.run([sys.executable, 'diag/twin/to_match2.py'], timeout=400, capture_output=True)
    for rnd in (1, 2):
        wait_for(lambda ph: ph['A'] == 6 and ph['B'] == 6, f'match {n + 1} phase {rnd}')
        time.sleep(10)
        subprocess.run([sys.executable, 'diag/twin/clock.py', '5', 'AB'], capture_output=True)
        print(time.strftime('%H:%M:%S'), f'match {n + 1}: phase {rnd} running, clocks cut', flush=True)
        wait_for(lambda ph: ph['A'] != 6 and ph['B'] != 6, f'match {n + 1} phase {rnd} end')
    wait_for(lambda ph: ph['A'] in (36, 0) and ph['B'] in (36, 0), f'match {n + 1} outcome')
    print(time.strftime('%H:%M:%S'), f'match {n + 1}: Outcome on both', flush=True)
    time.sleep(3)
print('soak passed')
