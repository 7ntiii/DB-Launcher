"""TEST ONLY: give the local player of a game a sigil skill pair (as a character row "with sigil" would).
python diag/twin/give_sigil.py WHO [SKILL=1010000]
Writes {skill, 1} into the first free pair of the local pgd's skill block pgd+0x1C6C (30 pairs of {i32 id, u32 count}).
pgd = [GDM+0x20], GDM = *(main+0x5B3CDB8) as sigils.py reads it."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
import sigils
from mem import Mem

who = sys.argv[1]
skill = int(sys.argv[2]) if len(sys.argv) > 2 else 1010000
m = Mem(who)
gdm_g = getattr(sigils, 'PGD_G', None)
if gdm_g is None:
    raise SystemExit('sigils.py has no GDM_G: look up the global there')
gdm = m.u64(m.base + gdm_g)
pgd = m.u64(gdm + 0x20)
raw = m.read(pgd + 0x1C6C, 0xF0)
for k in range(30):
    pid, cnt = struct.unpack_from('<iI', raw, 8 * k)
    if pid == skill:
        print(who, 'pair', k, 'already', pid, cnt)
        break
    if pid < 0:
        m.write(pgd + 0x1C6C + 8 * k, struct.pack('<iI', skill, 1))
        print(who, 'pgd %x pair %d <- {%d, 1}' % (pgd, k, skill))
        break
