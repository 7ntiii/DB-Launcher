"""snap(GAME): {(set, index): (position, hp, owned here, entry flags)} of a twin game's enemies."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

ENEMY_VT = 0x572B108


def big(m, a, n):
    return b''.join(m.read(a + o, min(0x2000, n - o)) for o in range(0, n, 0x2000))


def snap(w):
    m = Mem(w)
    wcm = m.u64(m.base + 0x5B3CD88)
    sm = m.u64(wcm + 0x540)
    out = {}
    for si in range(min(m.u32(sm + 8), 16)):
        s = m.u64(sm + 0x10 + 8 * si)
        if not s:
            continue
        n = m.u32(s + 0x10)
        cs = m.u64(s + 8)
        if not n or n > 8192 or not cs:
            continue
        ent = big(m, m.u64(cs + 8), 0x38 * n)
        own = struct.unpack('<%dh' % n, big(m, m.u64(s + 0x18), 2 * n))
        for j in range(n):
            c, _, fl, _, _, ph, _ = struct.unpack_from('<7Q', ent, 0x38 * j)
            if not c or not ph:
                continue
            try:
                if m.u64(c) != m.base + ENEMY_VT:
                    continue
                mod = m.u64(m.u64(c + 0x2470) + 0x18)
                hp = struct.unpack('<i', m.read(mod + 0x290, 4))[0] if mod else -1
                out[(si, j)] = (struct.unpack('<3f', m.read(ph + 0x70, 12)), hp, own[j] >= 0, fl & 0xff)
            except Exception:
                pass
    return out


