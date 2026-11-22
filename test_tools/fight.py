"""Twin combat test: python diag/twin/fight.py ATTACKER [buttons..] -> puts the attacker 1.4 m from the other
player (other one ahead of the attacker's camera), locks on (StickR), presses the attack buttons, and prints
HP of both players as seen by each game (local *(npm+0x20)+8, remote chr module 3 +0xf00)."""
import sys, struct, time, os, math
sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl
PORT = {'A': 6543, 'B': 6544}
def ent(m, i):
    arr = m.read(m.u64(m.u64(m.base + 0x5b3cd88) + 0x30), 0x38 * 3)
    return struct.unpack_from('<7Q', arr, i * 0x38)
def hp_local(m):
    p = m.u64(m.u64(m.base + 0x5b57eb8) + 0x20)
    return struct.unpack('<2i', m.read(p + 8, 8))
def hp_chr(m, i):
    c = ent(m, i)[0]
    md = struct.unpack('<4Q', m.read(m.u64(c + 0x18), 0x20))[3]
    return struct.unpack('<2i', m.read(md + 0xf00, 8))
def hps(ma, mb):
    return f'A: own {hp_local(ma)} copyB {hp_chr(ma, 1)} | B: own {hp_local(mb)} copyA {hp_chr(mb, 1)}'
att = sys.argv[1]; vic = 'B' if att == 'A' else 'A'
btns = sys.argv[2:] or ['R', 'R']
M = {'A': Mem('A'), 'B': Mem('B')}
ma, mb = M['A'], M['B']
print('before', hps(ma, mb))
pa, pv = ent(M[att], 0)[5], ent(M[vic], 0)[5]
a0 = struct.unpack('<3f', M[att].read(pa + 0x70, 12))
tctl.call(att, {'method': 'input_sequence', 'params': {'steps': [{'left_stick': [0, 1], 'frames': 6}, {'frames': 10}]}})
a1 = struct.unpack('<3f', M[att].read(pa + 0x70, 12))
dx, dz = a1[0] - a0[0], a1[2] - a0[2]; n = math.hypot(dx, dz) or 1; fx, fz = dx / n, dz / n
v = struct.unpack('<3f', M[vic].read(pv + 0x70, 12))
tgt = (v[0] - 1.4 * fx, v[1] + 0.2, v[2] - 1.4 * fz)
M[att].write(pa + 0x70, struct.pack('<3f', *tgt))
time.sleep(1.0)
print('placed', att, 'at', tgt, 'victim', v, 'fwd', (round(fx, 2), round(fz, 2)))
steps = [{'buttons': ['StickR'], 'frames': 4}, {'frames': 12}]
for b in btns:
    steps += [{'buttons': [b], 'frames': 4}, {'frames': 40}]
tctl.call(att, {'method': 'input_sequence', 'params': {'steps': steps}})
time.sleep(0.5)
print('after ', hps(ma, mb))
