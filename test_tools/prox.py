"""Nearest-player enemy ownership, live on the twin rig (what the game server did with 0x13/0x14):
each game owns the enemies that are nearer to its own player than to any other player.
python diag/twin/prox.py AB SECONDS"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

ENEMY_VT = 0x572B108


def big(m, a, n):
    return b''.join(m.read(a + o, min(0x2000, n - o)) for o in range(0, n, 0x2000))


class Game:
    def __init__(self, w):
        self.w = w
        self.m = Mem(w)
        m = self.m
        self.wcm = m.u64(m.base + 0x5B3CD88)
        sm = m.u64(self.wcm + 0x540)
        self.s = m.u64(sm + 0x10)
        self.n = m.u32(self.s + 0x10)
        self.own = m.u64(self.s + 0x18)
        cs = m.u64(self.s + 8)
        self.ent = m.u64(cs + 8)
        entries = big(m, self.ent, 0x38 * self.n)
        self.enemy = []
        for j in range(self.n):
            c, _, _, _, _, phys, _ = struct.unpack_from('<7Q', entries, 0x38 * j)
            if c and phys and m.u64(c) == m.base + ENEMY_VT:
                self.enemy.append((j, phys))

    def players(self):
        m = self.m
        arr = m.read(m.u64(self.wcm + 0x30), 0x38 * 8)
        out = []
        for i in range(8):
            c, _, _, _, _, phys, _ = struct.unpack_from('<7Q', arr, 0x38 * i)
            if c and phys:
                out.append(struct.unpack('<3f', m.read(phys + 0x70, 12)))
        return out

    def step(self):
        m = self.m
        ps = self.players()
        if not ps:
            return 0
        me, others = ps[0], ps[1:]
        ow = bytearray(big(m, self.own, 2 * self.n))
        mine = 0
        for j, phys in self.enemy:
            p = struct.unpack('<3f', m.read(phys + 0x70, 12))
            d = lambda q: sum((a - b) ** 2 for a, b in zip(p, q))
            own = all(d(me) <= d(o) for o in others)
            mine += own
            struct.pack_into('<h', ow, 2 * j, 1 if own else -1)
        for o in range(0, len(ow), 0x1000):
            m.write(self.own + o, bytes(ow[o:o + 0x1000]))
        return mine


games = [Game(w) for w in sys.argv[1]]
t0 = time.time()
while time.time() - t0 < float(sys.argv[2]):
    print(time.strftime('%H:%M:%S'), {g.w: '%d/%d' % (g.step(), len(g.enemy)) for g in games}, flush=True)
