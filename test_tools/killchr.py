"""Fight ONE given chr with kill.py's sequence (TEST ONLY; writes the player's position and facing, NEVER any HP).
python diag/twin/killchr.py WHO chr=ADDR [rounds=12] [seconds=0] [every=4] [dist=1.5]

kill.py's method, which works on the rig for ground enemies: teleport 1.5 m from the target AT THE TARGET'S
HEIGHT, face it, lock on (StickR), then R presses (5 frames down, 25 up). kill.py itself always takes the NEAREST
chr of npcs.find(), i.e. a chr with the enemy vtable main+0x572B108 whose entry chr+0x18 points back and whose
entry flags low byte is 5 (near / active). A kin can miss that list: it may have another class (vtable), an
entry that is not near-active, or simply not be the nearest. Here the target is given:
  chr=ADDR      target chr (hex): an enemy, a kin copy (regress_small kin_view / kinstate.py), anything with
                [[chr+0x2470]+0x18]+0x290 HP
  rounds=12     R presses (each re-reads the target; ignored when seconds > 0)
  seconds=0     > 0: keep fighting this long (until the target's HP here is <= 0 or it is unreadable)
  every=4       re-teleport + face + StickR every N presses (a kin moves)
  dist=1.5      stand-off distance (m)
Position of the target: its entry's physics (chr+0x18 -> entry, +0x28 physics, +0x70) when that entry points back,
else [[chr+0x2470]+0xE8]+0x70 (world_lib.chr_pos). Prints one line per press: target HP here, my HP, distance.
Exit 0 target HP <= 0 here, 1 rounds / time used up, 2 bad target / no player."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402
import tctl  # noqa: E402

VT_ENEMY = 0x572B108


def opts(argv):
    o = {'who': argv[1], 'chr': None, 'rounds': 12, 'seconds': 0.0, 'every': 4, 'dist': 1.5}
    for a in argv[2:]:
        k, _, v = a.partition('=')
        if k == 'chr':
            o['chr'] = int(v, 16)
        elif k in ('rounds', 'every'):
            o[k] = int(v)
        elif k in ('seconds', 'dist'):
            o[k] = float(v)
    return o


def main():
    o = opts(sys.argv)
    who, c = o['who'], o['chr']
    if not c:
        print('usage: killchr.py WHO chr=ADDR [rounds=12] [seconds=0] [every=4] [dist=1.5]')
        return 2
    m = Mem(who)
    wcm = m.u64(m.base + 0x5B3CD88)
    me = struct.unpack('<7Q', m.read(m.u64(wcm + 0x30), 56))
    my_phys, my_mod = me[5], me[3]

    def f3(a):
        return struct.unpack('<3f', m.read(a, 12))

    def target_phys():
        try:
            ent = m.u64(c + 0x18)
            if ent and m.u64(ent) == c:
                ph = m.u64(ent + 0x28)
                if ph:
                    return ph
        except Exception:
            pass
        mm = m.u64(c + 0x2470)
        return m.u64(mm + 0xE8) if mm else None

    def target_hp():
        try:
            mm = m.u64(c + 0x2470)
            mod = m.u64(mm + 0x18) if mm else None
            return struct.unpack('<i', m.read(mod + 0x290, 4))[0] if mod else None
        except Exception:
            return None

    def my_hp():
        try:
            return struct.unpack('<i', m.read(my_mod + 0xF30, 4))[0]
        except Exception:
            return None

    vt = m.u64(c)
    print('%s: target chr %x vtable main+%x%s, hp %s' % (
        who, c, vt - m.base if vt else 0, ' (enemy class)' if vt == m.base + VT_ENEMY else ' (NOT the enemy class '
        'npcs.py / kill.py search)', target_hp()), flush=True)

    def go():
        ph = target_phys()
        if not ph:
            return None
        here, ep = f3(my_phys + 0x70), f3(ph + 0x70)
        yaw = math.atan2(ep[0] - here[0], ep[2] - here[2])
        spot = (ep[0] - o['dist'] * math.sin(yaw), ep[1], ep[2] - o['dist'] * math.cos(yaw))   # the target's height
        m.write(my_phys + 0x70, struct.pack('<3f', *spot))
        m.write(my_phys + 0x64, struct.pack('<f', yaw))
        time.sleep(0.3)
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['StickR'], 'frames': 4},
                                                                          {'frames': 10}]}})
        return ep

    if go() is None or target_hp() is None:
        print('%s: target unreadable' % who)
        return 2
    t0, n = time.time(), 0
    while True:
        if o['seconds'] > 0:
            if time.time() - t0 > o['seconds']:
                break
        elif n >= o['rounds']:
            break
        if n and n % max(1, o['every']) == 0:
            go()
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['R'], 'frames': 5},
                                                                          {'frames': 25}]}})
        n += 1
        hp = target_hp()
        ph = target_phys()
        d = math.dist(f3(my_phys + 0x70), f3(ph + 0x70)) if ph else float('nan')
        print('%5.1f s press %d: target hp %s, my hp %s, dist %.2f' % (time.time() - t0, n, hp, my_hp(), d), flush=True)
        if hp is None:
            print('%s: target unreadable' % who)
            return 2
        if hp <= 0:
            return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
