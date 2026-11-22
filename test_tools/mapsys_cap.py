"""Capture the MapSystem lists of the twin games when the simulation has filled them (apply flag MS+0x20 = 1):
python diag/twin/mapsys_cap.py [GAMES=AB] [MAX_SECONDS=300] [sync]
Polls fast; for each game saves diag/twin/mapsys_<game>_r<round>.txt (one line per kind: hex of the list) the first
time the lists are non-empty in a new round, then prints which kinds are equal between the games.
'sync': while waiting, keeps copying game A's random engine state (gamedata+0xB8..+0x110) to the other games until
the first capture (test of the same-seed idea)."""
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 300
sync = 'sync' in sys.argv
ms = {w: Mem(w) for w in games}
got = {}
start = {}
for w, m in ms.items():
    par = m.u64(m.base + 0x5B3CDF8)
    start[w] = m.u32(par + 0xB8)
t0 = time.time()
while time.time() - t0 < limit and len(got) < len(games):
    if sync and not got:
        a = ms[games[0]]
        st = a.read(a.u64(a.base + 0x5B65C20) + 0xB8, 0x58)
        for w in games[1:]:
            m = ms[w]
            m.write(m.u64(m.base + 0x5B65C20) + 0xB8, st)
    for w, m in ms.items():
        if w in got:
            continue
        try:
            par = m.u64(m.base + 0x5B3CDF8)
            msys = m.u64(par + 0x2D8)
            rnd = m.u32(par + 0xB8)
            if rnd == start[w] and m.u32(par + 0x50) == 6:
                continue
            lists = {}
            for k in range(30):
                b, e = m.u64(msys + 0x28 + k * 0x20), m.u64(msys + 0x30 + k * 0x20)
                if e > b:
                    lists[k] = m.read(b, e - b).hex()
            if lists:
                got[w] = lists
                rng = m.read(m.u64(m.base + 0x5B65C20) + 0xB8, 0x58).hex()
                with open('diag/twin/mapsys_%s_r%d.txt' % (w, rnd), 'w') as f:
                    f.write('rng %s\n' % rng)
                    for k in sorted(lists):
                        f.write('%02X %s\n' % (k, lists[k]))
                print(time.strftime('%H:%M:%S'), w, 'round', rnd, 'step', m.u32(par + 0x50), 'kinds', len(lists), flush=True)
        except Exception as ex:
            print(w, 'err', str(ex)[:60], flush=True)
    time.sleep(0.2)
if len(got) == len(games):
    a = got[games[0]]
    for w in games[1:]:
        b = got[w]
        same = [k for k in sorted(set(a) | set(b)) if a.get(k) == b.get(k)]
        diff = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        print(games[0], 'vs', w, 'same kinds', ['%X' % k for k in same], 'different', ['%X:%d/%d' % (k, len(a.get(k, '')) // 2, len(b.get(k, '')) // 2) for k in diff])
else:
    print('not captured', [w for w in games if w not in got])
