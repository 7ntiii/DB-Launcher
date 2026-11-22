"""TEST ONLY - NEVER SHIP. Stagger one enemy and drink its blood (row 50), hands-free.
python diag/twin/draintry.py WHO ENEMY_CHR [cycles=40] [hold=45] [dist=1.4] [keephp=GAME] [gauge=BAG:OFF]

Each cycle: put the player dist m from the enemy, facing it (phys+0x70 / +0x64, as kill.py); ZR held `hold` frames
(charged strong attack: the biggest stagger-gauge gain a tool can press; TutorialBody 18013010 "Attacking an enemy
inflicts damage while filling stagger gauge"); then R twice at once (R = "Drink blood" near a staggered enemy,
18013000; otherwise a light attack that also fills the gauge).
  keephp=GAME  TEST ONLY: after each cycle write the enemy's HP back to its max on GAME (the authority: the host,
               A), so it does not die before the gauge is full (enemy found on GAME by handle chr+8)
  gauge=BAG:OFF the stagger-gauge float found with modscan.py (module at [[chr+0x2470]+BAG], field +OFF, hex):
               printed every cycle; when it falls by more than half (the gauge resets when the stagger starts),
               R is pressed three more times at once
Detects the drink by (a) the player's HP rising - IGNORED while the no-death bit or switch is on (nodeath.py refills
HP, handoff: false "137 -> 277"); then (b) / (c) decide,
(b) the enemy entering the local player's friendly group ([[chr+0x2470]+0x280] slot pointer +0x1C == 1, credit.py
'fg'; "spellbound foes follow"), (c) an enemy HP drop above 30 % of its max in one cycle.
Writes: player position / yaw; with keephp the enemy HP on GAME. Reads only otherwise. Run from the workspace root.
Pick an enemy whose family has a player drain throw (ThrowParam 1000FFFF00: c2000, 2010, 2011, 2020, 2070, 2071,
2090, 2140 ... ; NOT 2040, 2050, 2080, 2100 Milhusa cavalry, 2110, 2120, 2130 Bloodsac: "some enemies are immune")."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl


def opts(argv):
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    o = {'cycles': 40, 'hold': 45, 'dist': 1.4, 'keephp': '', 'gauge': ''}
    for a in argv[3:]:
        k, _, v = a.partition('=')
        if k not in o or not _:
            sys.exit('unknown option %s' % a)
        o[k] = v if k in ('keephp', 'gauge') else (float(v) if k == 'dist' else int(v))
    return argv[1], int(argv[2], 16), o


def fg_slots(m, c):
    try:
        fg = m.u64(m.u64(c + 0x2470) + 0x280)
        ptrs = struct.unpack('<12Q', m.read(fg + 0x18, 96))
        return {g for g, s in enumerate(ptrs) if s and m.read(s + 0x1C, 1)[0] == 1}
    except Exception:
        return None


def main():
    who, c, o = opts(sys.argv)
    m = Mem(who)
    wcm = m.u64(m.base + 0x5B3CD88)
    me = struct.unpack('<7Q', m.read(m.u64(wcm + 0x30), 56))
    my_chr, my_mod, my_phys = me[0], me[3], me[5]
    slot = m.read(m.u64(m.u64(my_chr + 0x20) + 0x1D0) + 0x104, 1)[0]
    mod = m.u64(m.u64(c + 0x2470) + 0x18)
    hp_m, hp_mod = None, None
    if o['keephp']:
        import npcs
        hp_m = Mem(o['keephp'])
        h = m.u64(c + 8) & 0xFFFFFFFF
        hc = next((r['chr'] for r in npcs.find(hp_m) if r['handle'] & 0xFFFFFFFF == h), None)
        hp_mod = hp_m.u64(hp_m.u64(hc + 0x2470) + 0x18) if hc else None
        print('keephp: %s chr %s' % (o['keephp'], hex(hc) if hc else 'NOT FOUND'), flush=True)
    gb = go = None
    if o['gauge']:
        gb, go = [int(x, 16) for x in o['gauge'].split(':')]

    def gauge():
        if gb is None:
            return None
        return struct.unpack('<f', m.read(m.u64(m.u64(c + 0x2470) + gb) + go, 4))[0]

    def r_burst(n):
        s = []
        for _ in range(n):
            s += [{'buttons': ['R'], 'frames': 4}, {'frames': 8}]
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': s}})

    my_dmod = m.u64(m.u64(my_chr + 0x2470) + 0x18)

    def nodeath_on():
        """nodeath.py state: u16 [[chr+0x2470]+0x18]+0x4A0 bit 2, or the debug byte main+0x5B84290"""
        try:
            return bool(struct.unpack('<H', m.read(my_dmod + 0x4A0, 2))[0] & 4) or m.read(m.base + 0x5B84290, 1)[0] != 0
        except Exception:
            return True

    fg0 = fg_slots(m, c)
    print('%s: enemy 0x%x hp %d/%d fg %s, my slot %d hp %d' % (
        who, c, m.u32(mod + 0x290), m.u32(mod + 0x294), fg0, slot, m.u32(my_mod + 0xF30)), flush=True)
    last_g = gauge()
    for n in range(1, o['cycles'] + 1):
        here = struct.unpack('<3f', m.read(my_phys + 0x70, 12))
        ep = struct.unpack('<3f', m.read(m.u64(m.u64(c + 0x2470) + 0xE8) + 0x70, 12))
        yaw = math.atan2(ep[0] - here[0], ep[2] - here[2])
        m.write(my_phys + 0x70, struct.pack('<3f', ep[0] - o['dist'] * math.sin(yaw), ep[1] + 0.1,
                                            ep[2] - o['dist'] * math.cos(yaw)))
        m.write(my_phys + 0x64, struct.pack('<f', yaw))
        time.sleep(0.3)
        here_t = struct.unpack('<3f', m.read(my_phys + 0x70, 12))
        print('   abs: enemy (%.2f %.2f %.2f) me after teleport (%.2f %.2f %.2f) horiz %.2f' % (
            *ep, *here_t, math.hypot(ep[0] - here_t[0], ep[2] - here_t[2])), flush=True)
        php0, ehp0 = struct.unpack('<i', m.read(my_mod + 0xF30, 4))[0], struct.unpack('<i', m.read(mod + 0x290, 4))[0]
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['ZR'], 'frames': o['hold']},
                                                                          {'frames': 20}]}})
        g = gauge()
        if g is not None and last_g and g < last_g * 0.5:
            r_burst(3)
        else:
            r_burst(2)
        time.sleep(1.5)
        php1, ehp1 = struct.unpack('<i', m.read(my_mod + 0xF30, 4))[0], struct.unpack('<i', m.read(mod + 0x290, 4))[0]
        emax = struct.unpack('<i', m.read(mod + 0x294, 4))[0]
        fg = fg_slots(m, c)
        print('cycle %d: enemy hp %d -> %d / %d | my hp %d -> %d | fg %s%s' % (
            n, ehp0, ehp1, emax, php0, php1, sorted(fg) if fg is not None else '?',
            ' | gauge %.3f' % g if g is not None else ''), flush=True)
        drank = []
        nd = nodeath_on()
        if php1 > php0 and not nd:
            drank.append('my HP rose %d -> %d' % (php0, php1))
        elif php1 != php0 and nd:
            print('   (my HP %d -> %d ignored: the no-death bit / switch is on and refills HP)' % (php0, php1))
        if fg and slot in fg and not (fg0 and slot in fg0):
            drank.append('enemy joined my friendly group (slot %d)' % slot)
        if emax and ehp0 - ehp1 > 0.3 * emax:
            drank.append('enemy lost %d HP in one cycle' % (ehp0 - ehp1))
        if drank:
            print('%s: DRINK? %s' % (who, '; '.join(drank)), flush=True)
            if len(drank) >= 2 or 'friendly' in drank[0]:
                print('%s: DRAIN SEEN after %d cycles' % (who, n))
                return 0
        if ehp1 <= 0:
            print('%s: enemy died before a drain (use keephp=A)' % who)
            return 1
        if hp_mod and emax:
            hp_m.write(hp_mod + 0x290, struct.pack('<i', emax))
        last_g = g
    print('%s: no drain in %d cycles' % (who, o['cycles']))
    return 1


if __name__ == '__main__':
    sys.exit(main())
