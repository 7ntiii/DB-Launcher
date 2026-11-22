"""Guest hits an enemy that the other game owns: python diag/twin/crosshit.py OWNER ATTACKER [ROUNDS]
Puts OWNER 0.7 m from its nearest active enemy and ATTACKER 2.4 m away on the other side (so OWNER
stays the nearest player and keeps the enemy), then ATTACKER locks on and presses R. Prints the
enemy's HP and owner flag in both games each round (HP = [[chr+0x2470]+0x18]+0x290)."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem
import npcs
import tctl

own_w, att_w = sys.argv[1], sys.argv[2]
rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 8
G = {w: Mem(w) for w in (own_w, att_w)}


def me(m):
    return struct.unpack('<7Q', m.read(m.u64(m.u64(m.base + 0x5B3CD88) + 0x30), 56))


def pos(m, phys):
    return struct.unpack('<3f', m.read(phys + 0x70, 12))


def entry(m, j):
    sm = m.u64(m.u64(m.base + 0x5B3CD88) + 0x540)
    s = m.u64(sm + 0x10)
    e = struct.unpack('<7Q', m.read(m.u64(m.u64(s + 8) + 8) + 0x38 * j, 56))
    return e, m.u64(s + 0x18) + 2 * j


def view(w, j):
    m = G[w]
    e, flag = entry(m, j)
    if not e[0]:
        return '%s: gone' % w
    mod = m.u64(m.u64(e[0] + 0x2470) + 0x18)
    hp = struct.unpack('<2i', m.read(mod + 0x290, 8))
    own = struct.unpack('<h', m.read(flag, 2))[0]
    return '%s: hp %d/%d own %d act %d' % (w, hp[0], hp[1], own, e[2] & 0xff)


mo = G[own_w]
here = pos(mo, me(mo)[5])
def alive(r):
    mod = mo.u64(mo.u64(r['chr'] + 0x2470) + 0x18)
    return mod and struct.unpack('<i', mo.read(mod + 0x290, 4))[0] > 0


cands = [r for r in npcs.find(mo) if r['phys'] and r['flags'] & 0xff == 5 and alive(r)]
t = min(cands, key=lambda r: math.dist(pos(mo, r['phys']), here))
j = t['handle'] & 0xfff
ep = pos(mo, t['phys'])
print('target handle %x at (%.1f %.1f %.1f)' % (t['handle'], *ep))
for w, dist, ang in ((own_w, 0.7, 0.0), (att_w, 2.4, math.pi)):
    m = G[w]
    p = me(m)[5]
    spot = (ep[0] - dist * math.sin(ang), ep[1] + 0.3, ep[2] - dist * math.cos(ang))
    m.write(p + 0x70, struct.pack('<3f', *spot))
    m.write(p + 0x64, struct.pack('<f', ang))
time.sleep(0.5)
# A position written into memory is not sent to the other game until the player really moves.
tctl.call(own_w, {'method': 'input_sequence', 'params': {'steps': [{'left_stick': [0, 1], 'frames': 14}, {'left_stick': [0, -1], 'frames': 14}, {'frames': 20}]}})
time.sleep(2.0)
for w in (own_w, att_w):
    m = G[w]
    arr = m.read(m.u64(m.u64(m.base + 0x5B3CD88) + 0x30), 0x38 * 2)
    print(w, 'sees players at', [tuple(round(x, 1) for x in pos(m, struct.unpack_from('<7Q', arr, 0x38 * i)[5])) for i in range(2)])
print('before  ', view(own_w, j), '|', view(att_w, j))
tctl.call(att_w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4}, {'frames': 10}]}})
for i in range(rounds):
    tctl.call(att_w, {'method': 'input_sequence', 'params': {'steps': [{'left_stick': [0, 1], 'buttons': ['R'], 'frames': 5}, {'frames': 28}]}})
    print('round %d ' % i, view(own_w, j), '|', view(att_w, j), flush=True)
