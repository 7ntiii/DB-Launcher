"""Track both twin players once in the match: python diag/twin/track.py [seconds] -> prints par state and
chr-set entries (local + remote) with physics position every 2 s (fall / death check)."""
import sys, time, struct
sys.path.insert(0, 'diag/twin')
from mem import Mem
from tctl import GAMES
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 600
t0 = time.time(); ms = {}
while time.time() - t0 < dur:
    line = [time.strftime('%H:%M:%S')]
    for who in GAMES:
        try:
            m = ms.get(who) or Mem(who); ms[who] = m
            par = m.u64(m.base + 0x5b3cdf8); pst = m.u32(par + 0x50) if par else -1
            s = f'{who} par={pst}'
            wcm = m.u64(m.base + 0x5b3cd88)
            if pst == 6 and wcm:
                arr = m.read(m.u64(wcm + 0x30), 0x38 * 3)
                for i in range(3):
                    chr_, _, act, _, _, phys, _ = struct.unpack_from('<7Q', arr, i * 0x38)
                    if chr_ and phys:
                        x, y, z = struct.unpack('<3f', m.read(phys + 0x70, 12))
                        s += f' e{i}=({x:.1f},{y:.1f},{z:.1f})'
            line.append(s)
        except Exception as e:
            ms.pop(who, None); line.append(f'{who} err {str(e)[:60]}')
    print(' | '.join(line), flush=True)
    time.sleep(2)
