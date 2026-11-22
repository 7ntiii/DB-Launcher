"""Kept-open debug-server connection to a twin game (no child process per call): Dbg('A').read(addr, n),
.u64, .phys() (chr-set physics pointers, entry 0 = local player), .pos(phys), .clock() (phase seconds left)."""
import json
import socket
import struct
import sys

sys.path.insert(0, 'diag/twin')
from lanlog import main_base

PORT = {'A': 6545, 'B': 6546, 'C': 6547, 'D': 6548}


class Dbg:
    def __init__(self, who):
        self.sock = socket.create_connection(('127.0.0.1', PORT[who]), timeout=10)
        self.buf = b''
        self.n = 0
        self.base = main_base(who)

    def call(self, method, params):
        self.n += 1
        self.sock.sendall(json.dumps({'id': self.n, 'method': method, 'params': params}).encode() + b'\n')
        while b'\n' not in self.buf:
            self.buf += self.sock.recv(1 << 20)
        raw, _, self.buf = self.buf.partition(b'\n')
        r = json.loads(raw)
        return r.get('result', r)

    def read(self, a, n):
        r = self.call('read_memory', {'address': hex(a), 'size': n})
        return bytes.fromhex(r.get('hex') or r.get('data'))

    def u64(self, a):
        return struct.unpack('<Q', self.read(a, 8))[0]

    def phys(self):
        """physics object pointers of the chr-set entries (entry 0 = the local player)"""
        wcm = self.u64(self.base + 0x5b3cd88)
        arr = self.read(self.u64(wcm + 0x30), 0x38 * 3)
        return [struct.unpack_from('<7Q', arr, i * 0x38)[5] for i in range(3)]

    def pos(self, phys):
        return struct.unpack('<3f', self.read(phys + 0x70, 12))

    def clock(self):
        par = self.u64(self.base + 0x5b3cdf8)
        return struct.unpack('<f', self.read(self.u64(par + 0x120) + 8, 4))[0]
