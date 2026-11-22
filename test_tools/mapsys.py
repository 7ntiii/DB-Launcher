"""Read the MapSystem state of the twin games: python diag/twin/mapsys.py [GAMES=AB] [dump KIND]
MS = [par+0x2D8]; object lists at MS+0x28+kind*0x20 {begin,end,cap} for kinds 0..29 (0x1B/0x1C/0x1D = kin circles
Ring/Blade/Eye); MS+0x20 = apply enabled; MS+0x530 = simulation has run. Prints the byte length of every list."""
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
dump = int(sys.argv[3], 0) if len(sys.argv) > 3 and sys.argv[2] == 'dump' else None
for w in games:
    m = Mem(w)
    par = m.u64(m.base + 0x5B3CDF8)
    if not par:
        print(w, 'no match object')
        continue
    ms = m.u64(par + 0x2D8)
    step, rnd = m.u32(par + 0x50), m.u32(par + 0xB8)
    if not ms:
        print(w, 'step', step, 'round', rnd, 'MS = 0')
        continue
    out = []
    for k in range(30):
        b, e = m.u64(ms + 0x28 + k * 0x20), m.u64(ms + 0x30 + k * 0x20)
        if e > b:
            out.append('%X:%d' % (k, e - b))
        if dump == k and e > b:
            data = m.read(b, min(e - b, 0x400))
            for i in range(0, len(data), 32):
                print('   ', '%04X' % i, data[i:i + 32].hex())
    prev = []
    for i in range(3):
        b, e = m.u64(ms + 0x3E8 + i * 0x20), m.u64(ms + 0x3F0 + i * 0x20)
        prev.append(e - b)
    print(w, 'step', step, 'round', rnd, 'MS %X apply %d ran %d' % (ms, m.read(ms + 0x20, 1)[0], m.read(ms + 0x530, 1)[0]),
          'lists(kind:bytes)', ' '.join(out) or 'all empty', 'prev circles', prev)
