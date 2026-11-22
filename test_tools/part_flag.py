"""Participant flag (PlayerGameData+0x46A0) of every player on each twin game: python diag/twin/part_flag.py [GAMES] [set]
pgd = [[chr+0x20]+0x1D0] for each player chr in the WCM chr set (entry 0 = local). "set" writes 1."""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
for w in games:
    m = Mem(w); wcm = m.u64(m.base + 0x5B3CD88); arr = m.read(m.u64(wcm + 0x30), 0x38 * 8); out = []
    for i in range(8):
        c = struct.unpack_from('<Q', arr, 0x38 * i)[0]
        if not c: continue
        try:
            if m.u64(c) == m.base + 0x572B108: continue
            pgd = m.u64(m.u64(c + 0x20) + 0x1D0)
            if not pgd: continue
            if 'set' in sys.argv: m.write(pgd + 0x46A0, b'\x01')
            out.append('no %d flag %d state %s' % (m.u32(pgd + 0xD0), m.read(pgd + 0x46A0, 1)[0], m.read(pgd + 0x46B0, 4).hex()))
        except Exception as e:
            out.append('err')
    print(w, out)
