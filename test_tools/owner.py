"""Chr sync ownership (handoff 1 section 8.9l, diag/net/enemy_sync_notes.md).
python diag/twin/owner.py A show        per sync set: entries, enemies, owned, flag bits
python diag/twin/owner.py A own         owner = 1 for every enemy entry (this game drives them)
python diag/twin/owner.py A remote      owner = -1 for every enemy entry
python diag/twin/owner.py A hold own|remote SECONDS   repeat every second"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

ENEMY_VT = 0x572B108


def big(m, a, n):
    return b''.join(m.read(a + o, min(0x2000, n - o)) for o in range(0, n, 0x2000))


def sets(m):
    sm = m.u64(m.u64(m.base + 0x5B3CD88) + 0x540)
    out = []
    for i in range(m.u32(sm + 8)):
        s = m.u64(sm + 0x10 + 8 * i)
        if not s:
            continue
        n = m.u32(s + 0x10)
        chrset = m.u64(s + 8)
        if not n or not chrset or n > 4096:
            out.append((i, s, n, [], 0, 0))
            continue
        entries = big(m, m.u64(chrset + 8), 0x38 * n)
        chrs = [struct.unpack_from('<Q', entries, 0x38 * j)[0] for j in range(n)]
        enemy = [j for j, c in enumerate(chrs) if c and m.u64(c) == m.base + ENEMY_VT]
        out.append((i, s, n, enemy, m.u64(s + 0x18), m.u64(s + 0x38)))
    return sm, out


def show(m):
    sm, ss = sets(m)
    w1 = m.u32(m.u64(m.base + 0x5B659A8) + 0x20)
    print('SM %x sets %d  send set w1=%d' % (sm, len(ss), w1))
    for i, s, n, enemy, own, flags in ss:
        if not enemy:
            print(' set %d: n %d, no enemies' % (i, n))
            continue
        ow = struct.unpack('<%dh' % n, big(m, own, 2 * n))
        fl = big(m, flags, 0xc * n)
        owned = sum(1 for j in enemy if ow[j] >= 0)
        bits = {b: sum(1 for j in enemy if struct.unpack_from('<H', fl, 0xc * j)[0] >> b & 1) for b in (1, 2, 5, 6)}
        print(' set %d: n %d, enemies %d, owned %d, flag bits %s' % (i, n, len(enemy), owned, bits))


def write(m, value):
    _, ss = sets(m)
    total = 0
    for i, s, n, enemy, own, flags in ss:
        if not enemy:
            continue
        ow = bytearray(big(m, own, 2 * n))
        for j in enemy:
            struct.pack_into('<h', ow, 2 * j, value)
        for o in range(0, len(ow), 0x1000):
            m.write(own + o, bytes(ow[o:o + 0x1000]))
        total += len(enemy)
    return total


w, op = sys.argv[1], sys.argv[2]
m = Mem(w)
if op == 'show':
    show(m)
elif op in ('own', 'remote'):
    print(w, op, write(m, 1 if op == 'own' else -1), 'enemies')
elif op == 'hold':
    value = 1 if sys.argv[3] == 'own' else -1
    t0 = time.time()
    while time.time() - t0 < float(sys.argv[4]):
        n = write(m, value)
        time.sleep(1)
    print(w, 'held', sys.argv[3], n, 'enemies')
