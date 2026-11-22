"""Shared, null-safe readers for the enumeration tools (levers.py, item_sources.py, kin.py, generators.py,
final_kills.py, nearest_objects.py). Every reader returns None instead of raising; W.null() records what was
missing so the tools can print it. Addresses: see diag/net/live_enumeration_notes.md ([V] = read in the
disassembly, [I] = inferred)."""
import math
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

# main-relative globals
WCM_G = 0x5B3CD88        # world chr manager                                   [V]
MAPITEM_G = 0x5B3CDC0    # MapItemMan                                          [V]
PAR_G = 0x5B3CDF8        # stage/phase object ("par")                          [V]
MGR3_G = 0x5B3CE08       # session manager, mode at +0x1268                    [V]
GEOM_G = 0x5B3CE28       # CSWorldGeomMan (handle -> geom ins, 0xFEC6E0)       [V]
WORLDGEOM_DROP_G = 0x5B57E90  # "online world" singleton checked by the drop code [V]
PGD_G = 0x5B57EB8        # [x+0x20] = local PlayerGameData (0xD8BA9C)           [V]
AAE_G = 0x5B59B60        # CSAssetAccessEventMan                                [V]
BLOCKS_G = 0x5B659A8     # block table used by the handle decoder (0xFEC704)    [V]
GAMEDATA_G = 0x5B65C20   # gamedata (+0xBDA offline flag, +0xB10 region index)  [V]
KILLGATE_G = 0x5B44240   # +0xC byte gates the local elimination (0x1166688)    [V]
HANDLE_TAB = 0x573F330   # {u32 mask, u32 shift, u32 index mask, ...} x 0x18 per handle type (h>>28) [V]
ENEMY_VT = 0x572B108     # EnemyIns vtable                                      [V live]

KNOWN_VT = {ENEMY_VT: 'EnemyIns', 0x56D8270: 'CSAssetAccessEventSequenceStep?', 0x56E0F60: 'NetEnemyIns'}


class W:
    def __init__(self, who):
        self.who = who
        self.m = Mem(who)
        self.base = self.m.base
        self.missing = []

    # ---------- raw readers ----------
    def rd(self, a, n):
        if a is None or a < 0x10000 or a > 0xFFFFFFFFFFFF:
            return None
        try:
            b = self.m.read(a, n)
            return b if b is not None and len(b) == n else None
        except Exception:
            return None

    def big(self, a, n):
        out = b''
        for o in range(0, n, 0x2000):
            b = self.rd(a + o, min(0x2000, n - o))
            if b is None:
                return None
            out += b
        return out

    def _u(self, a, fmt, n):
        b = self.rd(a, n)
        return struct.unpack(fmt, b)[0] if b else None

    def q(self, a):
        return self._u(a, '<Q', 8)

    def d(self, a):
        return self._u(a, '<I', 4)

    def i(self, a):
        return self._u(a, '<i', 4)

    def h(self, a):
        return self._u(a, '<H', 2)

    def b(self, a):
        return self._u(a, '<B', 1)

    def f(self, a):
        return self._u(a, '<f', 4)

    def f3(self, a):
        b = self.rd(a, 12)
        return struct.unpack('<3f', b) if b else None

    def g(self, off):
        """u64 at main+off (a global singleton pointer)"""
        return self.q(self.base + off)

    def null(self, what):
        self.missing.append(what)
        return None

    def report_missing(self):
        if self.missing:
            print('%s: null / unreadable: %s' % (self.who, ', '.join(dict.fromkeys(self.missing))))

    def write(self, a, data):
        self.m.write(a, data)

    def rel(self, a):
        return 'main+0x%X' % (a - self.base) if a and self.base <= a < self.base + 0x7000000 else ('0x%x' % a if a else 'null')

    # ---------- player ----------
    def wcm(self):
        return self.g(WCM_G) or self.null('WCM *(main+0x5B3CD88)')

    def player_entry(self, k=0):
        """k-th entry of the player chr set (WCM+0x30, 0x38 bytes: chr, 0, flags, module, 0, physics, module)"""
        w = self.wcm()
        arr = self.q(w + 0x30) if w else None
        if not arr:
            return self.null('player entries WCM+0x30')
        b = self.rd(arr + 0x38 * k, 0x38)
        return struct.unpack('<7Q', b) if b else None

    def me(self):
        e = self.player_entry(0)
        if not e or not e[5]:
            return None, None, self.null('local player physics (entry 0 +0x28)')
        return e[0], e[5], self.f3(e[5] + 0x70)

    def players(self, maxn=8):
        out = []
        for k in range(maxn):
            e = self.player_entry(k)
            if not e or not e[0]:
                break
            out.append(e)
        return out

    def goto(self, pos, yaw=None, nudge=False):
        _, phys, _ = self.me()
        if not phys:
            print(self.who, 'goto: no local player physics')
            return False
        self.write(phys + 0x70, struct.pack('<3f', *pos))
        if yaw is not None:
            self.write(phys + 0x64, struct.pack('<f', yaw))
        print('%s: player at (%.2f %.2f %.2f)%s' % (self.who, pos[0], pos[1], pos[2], '' if yaw is None else ' yaw %.2f' % yaw))
        if nudge:
            import tctl
            tctl.call(self.who, {'method': 'input_sequence', 'params': {'steps': [
                {'left_stick': [0, 1], 'frames': 4}, {'left_stick': [0, -1], 'frames': 4}, {'frames': 10}]}})
        return True

    def goto_front(self, target, dist=1.2, dy=0.2, nudge=False):
        """put the local player `dist` m from target on the side it is now, facing the target"""
        _, _, here = self.me()
        if here is None:
            here = (target[0], target[1], target[2] - 1.0)
        yaw = math.atan2(target[0] - here[0], target[2] - here[2])
        if math.dist(here, target) < 0.01:
            yaw = 0.0
        spot = (target[0] - dist * math.sin(yaw), target[1] + dy, target[2] - dist * math.cos(yaw))
        return self.goto(spot, yaw, nudge)

    def press(self, btn, frames=6, after=20):
        import tctl
        return tctl.call(self.who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': frames}, {'frames': after}]}})

    # ---------- chr helpers ----------
    def chr_pos(self, c):
        """[[chr+0x2470]+0xE8]+0x70 (the drop code 0x174EC3C and the 0xB6 apply 0xE8D410 use it) [V]"""
        m = self.q(c + 0x2470)
        ph = self.q(m + 0xE8) if m else None
        return self.f3(ph + 0x70) if ph else None

    def chr_hp(self, c):
        m = self.q(c + 0x2470)
        mod = self.q(m + 0x18) if m else None
        return self.i(mod + 0x290) if mod else None

    def chr_sets(self):
        """WCM+0x10 count, *(WCM+0x18) array of 0x270-byte chr sets: +8 -> block info (+0x1C block id),
        +0x78 chr count, +0x80 entries (0x38 bytes, +0 chr), +0xD8 generator count, +0xE0 generator array [V 0x178C164, 0x178FA5C]"""
        w = self.wcm()
        if not w:
            return []
        n, arr = self.d(w + 0x10), self.q(w + 0x18)
        if not arr or not n or n > 256:
            self.null('chr set array WCM+0x18 (count %s)' % n)
            return []
        out = []
        for k in range(n):
            s = arr + k * 0x270
            info = self.q(s + 8)
            out.append({'i': k, 'set': s, 'block': self.d(info + 0x1C) if info else None,
                        'nchr': self.d(s + 0x78), 'chrs': self.q(s + 0x80),
                        'ngen': self.d(s + 0xD8), 'gens': self.q(s + 0xE0)})
        return out

    def set_chrs(self, s):
        n, arr = s['nchr'], s['chrs']
        if not arr or not n or n > 8192:
            return []
        raw = self.big(arr, 0x38 * n)
        if raw is None:
            return []
        return [(j, struct.unpack_from('<Q', raw, 0x38 * j)[0]) for j in range(n) if struct.unpack_from('<Q', raw, 0x38 * j)[0]]

    def all_chrs(self):
        out = []
        for s in self.chr_sets():
            for j, c in self.set_chrs(s):
                out.append((s['i'], j, c))
        return out

    # ---------- libc++ std::map (node: +0 left, +8 right, +0x20 u32 key, +0x28 value) ----------
    def map_find(self, anchor, key):
        res, node, guard = anchor, self.q(anchor), 0
        while node and guard < 64:
            k = self.d(node + 0x20)
            if k is None:
                return None
            if k < key:
                node = self.q(node + 8)
            else:
                res, node = node, self.q(node)
            guard += 1
        if res == anchor or key < (self.d(res + 0x20) or 0):
            return None
        return self.q(res + 0x28)

    def map_items(self, anchor, limit=4096):
        out, stack, node = [], [], self.q(anchor)
        while (stack or node) and len(out) < limit:
            while node and len(stack) < 64:
                stack.append(node)
                node = self.q(node)
            if not stack:
                break
            node = stack.pop()
            out.append((self.d(node + 0x20), self.q(node + 0x28)))
            node = self.q(node + 8)
        return out

    # ---------- geometry ----------
    def geom_from_handle(self, hnd, strict=False):
        """Python copy of 0xFEC6E0 / 0xFEC520 (handle -> CSWorldGeomIns) [V]. strict=True also applies the
        final '[[ins+0x10]+0x20]+0xD != 1' test of the game."""
        if hnd is None or hnd == 0xFFFFFFFF or (hnd & 0xE0000000) != 0x60000000:
            return None
        ent = self.rd(self.base + HANDLE_TAB + (hnd >> 28) * 0x18, 12)
        if not ent:
            return self.null('handle table main+0x573F330')
        mask, shift, imask = struct.unpack('<3I', ent)
        blk = (hnd >> shift) & mask
        blockid = 0xFFFFFFFF
        x = self.g(BLOCKS_G)
        y = self.q(x + 0x10) if x else None
        if y:
            cnt, arr = self.i(y + 8), self.q(y + 0x10)
            if arr and cnt and cnt > blk:
                blockid = self.d(arr + blk * 0x1B0 + 0x1C)
        gm = self.g(GEOM_G)
        if not gm:
            return self.null('CSWorldGeomMan *(main+0x5B3CE28)')
        bg = self.map_find(gm + 0x18, blockid)
        if not bg or not self.b(bg + 0xB8):
            return None
        idx = hnd & imask
        if (idx >> 4) <= 0x752:
            tot = (self.d(bg + 0x20) or 0) + (self.d(bg + 0x2C) or 0) + (self.d(bg + 0x30) or 0)
            if tot <= idx or (self.d(bg + 0x80) or 0) <= idx:
                return None
            ins = self.q((self.q(bg + 0x70) or 0) + idx * 8)
        else:
            ins = self.map_find(bg + 0x1A8, idx)
        if not ins:
            return None
        if strict:
            info = self.q(ins + 0x10)
            z = self.q(info + 0x20) if info else None
            if not z or self.b(z + 0xD) == 1:
                return None
        return ins

    def geom_pos(self, ins):
        """world translation row of the matrix at ins+0xE0..0x11F (0xF2AB74..0xF2AC5C) [V]"""
        return self.f3(ins + 0x110) if ins else None

    def all_geoms(self, limit=20000):
        """every geom ins of every loaded block: tree CSWorldGeomMan+0x18 (key block id, value block geom);
        block geom +0xB8 loaded, +0x70 array (count +0x80), +0x1A8 tree for big indices [V 0xFEC6E0]"""
        gm = self.g(GEOM_G)
        if not gm:
            self.null('CSWorldGeomMan *(main+0x5B3CE28)')
            return []
        out = []
        for blockid, bg in self.map_items(gm + 0x18, 512):
            if not bg or not self.b(bg + 0xB8):
                continue
            n, arr = self.d(bg + 0x80) or 0, self.q(bg + 0x70)
            if arr and 0 < n < 200000:
                raw = self.big(arr, 8 * n)
                if raw:
                    for k in range(n):
                        ins = struct.unpack_from('<Q', raw, 8 * k)[0]
                        if ins:
                            out.append((blockid, k, ins))
            for k, ins in self.map_items(bg + 0x1A8, 4096):
                if ins:
                    out.append((blockid, k, ins))
            if len(out) >= limit:
                break
        return out[:limit]


def dist(a, b):
    return math.dist(a, b) if a and b else float('inf')


def fmt3(p):
    return '(%.1f %.1f %.1f)' % p if p else '(?)'
