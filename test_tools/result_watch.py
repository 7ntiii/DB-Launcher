"""Watch the phase-result block of both twin games through a match: prints at every phase change
par+0x47e0 (kind, player no, text id), +0x50 last-phase flag, +0x58/+0x59 match over, round, and each result entry's
state bytes (applied copy par+0x33d0, 0x60 bytes each, count par+0x3858). python diag/twin/result_watch.py [SECONDS]"""
import struct, sys, time
sys.path.insert(0, 'diag/twin')
from mem import Mem
end = time.time() + (float(sys.argv[1]) if len(sys.argv) > 1 else 900)
last = {}
while time.time() < end:
    for w in 'AB':
        try:
            m = Mem(w); par = m.u64(m.base + 0x5B3CDF8)
            if not par: continue
            ph = m.u32(par + 0x50)
            if last.get(w) == ph: continue
            last[w] = ph
            st = m.read(par + 0x47e0, 0x60)
            kind, no, text = struct.unpack_from('<iiI', st, 0)
            n = m.u32(par + 0x3858)
            ents = []
            for i in range(min(n, 8)):
                e = m.read(par + 0x33d0 + 0x60 * i, 0x60)
                ents.append('no %d rank %d pts %d state %s' % (struct.unpack_from('<i', e, 0)[0], struct.unpack_from('<I', e, 0x10)[0], struct.unpack_from('<I', e, 0x28)[0], e[0x40:0x44].hex()))
            print(time.strftime('%H:%M:%S'), w, 'phase', ph, 'round', m.u32(par + 0xB8), '| kind', kind, 'player', no, 'text', text, 'lastphase', st[0x50], 'over', st[0x58], st[0x59], '| 4838', m.read(par + 0x4838, 2).hex(), '| entries', ents, flush=True)
        except Exception as e:
            pass
    time.sleep(0.5)
