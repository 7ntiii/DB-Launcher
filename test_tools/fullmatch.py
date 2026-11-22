"""Run a whole 4-phase twin match with each phase clock cut to 5 s and print every phase/round change.
python diag/twin/fullmatch.py [MAX_SECONDS=900]. Start with both games in the first match (after go.sh)."""
import struct, subprocess, sys, time
sys.path.insert(0, 'diag/twin')
from mem import Mem
def st(w):
    try:
        m = Mem(w); par = m.u64(m.base + 0x5B3CDF8)
        return (m.u32(par + 0x50), m.u32(par + 0xB8)) if par else (-1, 0)
    except Exception:
        return (-2, 0)
t0 = time.time(); cut = set(); last = None; limit = float(sys.argv[1]) if len(sys.argv) > 1 else 900
while time.time() - t0 < limit:
    a, b = st('A'), st('B')
    if (a, b) != last:
        print(time.strftime('%H:%M:%S'), a, b, flush=True); last = (a, b)
    if a[0] == 6 and b[0] == 6 and a[1] not in cut:
        time.sleep(10)
        if a[1] >= 4:
            for w in __import__('os').environ.get('TWIN_GAMES', 'AB'):
                m = Mem(w); e = struct.unpack('<7Q', m.read(m.u64(m.u64(m.base + 0x5B3CD88) + 0x30), 56))
                print('  final:', w, 'player at', tuple(round(x, 1) for x in struct.unpack('<3f', m.read(e[5] + 0x70, 12))), flush=True)
            subprocess.run([sys.executable, 'diag/twin/tctl.py', 'A', 'shot', 'final'], capture_output=True)
        subprocess.run([sys.executable, 'diag/twin/clock.py', '5', __import__('os').environ.get('TWIN_GAMES', 'AB')], capture_output=True)
        cut.add(a[1]); print('  clocks cut in round', a[1], flush=True)
    if a[0] in (36, 0) and b[0] in (36, 0) and cut:
        print('match over after rounds', sorted(cut)); break
    time.sleep(2)
