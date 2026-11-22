"""Memory of a twin game through its debug server.

As a module: Mem('A') -> .base, .read(a, n), .write(a, data, code=False), .u64(a), .u32(a)
(code=True drops the JIT translations of the range: use it for every write to code).
Rebuilt 2026-11-13 14:55 (the original file was overwritten by mistake); same API as before.

As a script (addresses: 'main+0x5b65c20', '*main+0x5b65c20+0xbda' = one deref of main+X then +Y,
or absolute hex):
python diag/twin/mem.py A r ADDR [N]        hex dump N bytes (default 16)
python diag/twin/mem.py A q ADDR [N]        N u64 values
python diag/twin/mem.py A w ADDR HEX        write bytes
python diag/twin/mem.py A w8|w32 ADDR VALUE"""
import os
import struct
import sys

sys.path.insert(0, 'diag/twin')
from dbg import Dbg
from lanlog import main_base


class Mem:
    def __init__(self, who):
        self.g = Dbg(who)
        self.base = int(os.environ['DUSK_BASE'], 16) if os.environ.get('DUSK_BASE') else main_base(who)

    def call(self, method, params):
        return self.g.call(method, params)

    def read(self, a, n):
        r = self.g.call('read_memory', {'address': hex(a), 'size': n})
        return bytes.fromhex(r.get('hex') or r.get('data'))

    def write(self, a, data, code=False):
        params = {'address': hex(a), 'hex': bytes(data).hex()}
        if code:
            params['code'] = True
        return self.g.call('write_memory', params)

    def u64(self, a):
        return struct.unpack('<Q', self.read(a, 8))[0]

    def u32(self, a):
        return struct.unpack('<I', self.read(a, 4))[0]


# Module-level helpers for scripts that do `import mem` after setting sys.argv[1] to the game.
_m = None


def _get():
    global _m
    if _m is None:
        _m = Mem(sys.argv[1])
    return _m


def __getattr__(name):
    if name == 'base':
        return _get().base
    if name == 'g':
        return _get().g
    raise AttributeError(name)


def rd(a, n):
    return _get().read(a, n)


def u64(a):
    return _get().u64(a)


def addr(expr):
    """main+X, *main+X+Y (deref chain with *), or hex."""
    m = _get()
    derefs = expr.count('*')
    parts = expr.replace('*', '').split('+')
    a = m.base if parts[0] == 'main' else int(parts[0], 16)
    rest = parts[1:]
    if not rest:
        return a
    a += int(rest[0], 16)
    for off in rest[1:]:
        if derefs:
            a = m.u64(a)
            derefs -= 1
        a += int(off, 16)
    while derefs:
        a = m.u64(a)
        derefs -= 1
    return a


if __name__ == '__main__':
    op, a = sys.argv[2], addr(sys.argv[3])
    m = _get()
    if op == 'r':
        n = int(sys.argv[4], 0) if len(sys.argv) > 4 else 16
        b = m.read(a, n)
        for i in range(0, n, 16):
            print('%x: %s' % (a + i, b[i:i + 16].hex(' ')))
    elif op == 'q':
        n = int(sys.argv[4], 0) if len(sys.argv) > 4 else 1
        for i, v in enumerate(struct.unpack('<%dQ' % n, m.read(a, 8 * n))):
            print('%x +%x: %x' % (a + 8 * i, 8 * i, v))
    elif op in ('w', 'w8', 'w32'):
        data = bytes.fromhex(sys.argv[4]) if op == 'w' else struct.pack('<B' if op == 'w8' else '<I', int(sys.argv[4], 0))
        old = m.read(a, len(data))
        m.write(a, data)
        print('%x: %s -> %s' % (a, old.hex(), data.hex()))
