"""Drive the twin games to the start of the final without cutting the final's clock:
python diag/twin/to_final.py [MAX_SECONDS=900]
Cuts the phase clock to 5 s in rounds 1-3 (10 s after each starts) and stops when all games are in
UpdatePhase (6) of round 4. Games: TWIN_GAMES (default AB)."""
import os
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

GAMES = os.environ.get('TWIN_GAMES', 'AB')


def st(w):
    try:
        m = Mem(w)
        par = m.u64(m.base + 0x5B3CDF8)
        return (m.u32(par + 0x50), m.u32(par + 0xB8)) if par else (-1, 0)
    except Exception:
        return (-2, 0)


t0, cut, last = time.time(), set(), None
limit = float(sys.argv[1]) if len(sys.argv) > 1 else 900
while time.time() - t0 < limit:
    now = tuple(st(w) for w in GAMES)
    if now != last:
        print(time.strftime('%H:%M:%S'), now, flush=True)
        last = now
    if all(s[0] == 6 for s in now):
        rnd = now[0][1]
        if rnd >= 4:
            print('final reached', flush=True)
            break
        if rnd not in cut:
            time.sleep(10)
            subprocess.run([sys.executable, 'diag/twin/clock.py', '5', GAMES], capture_output=True)
            cut.add(rnd)
            print('  clocks cut in round', rnd, flush=True)
    time.sleep(2)
