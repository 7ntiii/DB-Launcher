"""Fight the nearest enemy: python diag/twin/kill.py A [ROUNDS]
Moves the player 1.5 m from the nearest active enemy chr (vtable main+0x572B108), faces it, locks on
(StickR) and presses R; prints the enemy's HP ([[chr+0x2470]+0x18]+0x290; max at +0x294) and the player's HP each round."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl

who = sys.argv[1]
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 12
m = Mem(who)
wcm = m.u64(m.base + 0x5B3CD88)
me = struct.unpack('<7Q', m.read(m.u64(wcm + 0x30), 56))
my_phys, my_mod = me[5], me[3]


def pos(phys):
    return struct.unpack('<3f', m.read(phys + 0x70, 12))


def enemies():
    import npcs
    return [(r['chr'], r['handle'], r['phys'], r['mod']) for r in npcs.find(m) if r['phys'] and r['flags'] & 0xff == 5]


here = pos(my_phys)
target = min(enemies(), key=lambda t: math.dist(pos(t[2]), here))
_, handle, ph, mod = target
ep = pos(ph)
yaw = math.atan2(ep[0] - here[0], ep[2] - here[2])
spot = (ep[0] - 1.5 * math.sin(yaw), ep[1] + 0.3, ep[2] - 1.5 * math.cos(yaw))
m.write(my_phys + 0x70, struct.pack('<3f', *spot))
m.write(my_phys + 0x64, struct.pack('<f', yaw))
print('target handle %x at (%.1f %.1f %.1f)' % (handle, *ep))
time.sleep(0.5)
tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4}, {'frames': 10}]}})
for i in range(rounds):
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]}})
    ehp = struct.unpack('<i', m.read(m.u64(m.u64(target[0] + 0x2470) + 0x18) + 0x290, 4))[0]
    php = struct.unpack('<i', m.read(my_mod + 0xF30, 4))[0]
    print('round %d: enemy hp %d, my hp %d' % (i, ehp, php), flush=True)
    if ehp <= 0:
        break
