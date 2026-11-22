"""Test helper: write the host's rule-set menu mask while it is in the hub: python diag/twin/set_rule.py A MASK
room = *(*(main+0x5B44248)+0xC0); mask byte at room+0xE4 (1 Standard, 2 No Alliances, 4 Bloodbound). Rewrites it
every half second until a match object exists, then prints the last value read."""
import sys, time
sys.path.insert(0, 'diag/twin')
from mem import Mem
who, mask = sys.argv[1], int(sys.argv[2], 0)
t0 = time.time(); n = 0
while time.time() - t0 < 420:
    try:
        m = Mem(who)
        a = m.u64(m.base + 0x5B44248)
        room = m.u64(a + 0xC0) if a else 0
        if room:
            if m.read(room + 0xE4, 1)[0] != mask:
                m.write(room + 0xE4, bytes([mask])); n += 1
        par = m.u64(m.base + 0x5B3CDF8)
        if par and m.u32(par + 0xB8) >= 1:
            break
    except Exception:
        pass
    time.sleep(0.5)
print(who, 'mask written', n, 'times; rule byte now', Mem(who).read(Mem(who).base + 0x5B65C70, 1)[0], flush=True)
