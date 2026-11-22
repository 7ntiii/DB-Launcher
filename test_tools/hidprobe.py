import sys, struct
sys.path.insert(0, 'diag/twin')
from mem import Mem
for w in ('A', 'B'):
    m = Mem(w); b = m.base
    wcm = m.u64(b + 0x5B3CD88)
    own = m.u64(wcm + 0x1A8)
    arr, cnt = m.u64(wcm + 0x30), m.u32(wcm + 0x28)
    print(w, 'own %x count %d own+50 %x' % (own, cnt, m.u64(own + 0x50)))
    for i in range(min(cnt, 6)):
        e = arr + 0x38 * i
        c = m.u64(e)
        if c == 0: continue
        cd = m.u64(c + 0x20); pgd = m.u64(cd + 0x1D0) if cd else 0
        net = m.u64(e + 0x30)
        print('  slot %d chr %x no %s ent+10 %d ent+20 %02x net18 %s +50 %x +1a28 %x 1c51 %s 12bc %x' % (
            i, c, m.u32(pgd + 0xD0) if pgd else '?', m.u32(e + 0x10), m.read(e + 0x20, 1)[0],
            m.read(net + 0x18, 1).hex() if net else '-', m.u64(c + 0x50), m.u64(c + 0x1A28),
            m.read(c + 0x1C51, 4).hex(), m.u64(c + 0x12BC)))
