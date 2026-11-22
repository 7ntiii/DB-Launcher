"""TEST ONLY - NEVER SHIP. Hit ONE Bloodsac (or any enemy chr) WITHOUT lock-on, standing at its own height.
python diag/twin/sachit.py WHO SAC_CHR_ADDR [mode=R|ZR] [hold=40] [dist=0.9] [dy=0.0] [seconds=90] [maxhp=1]
                           [clearflags=0] [probe=0]
  WHO           twin game (A, B, C)
  SAC_CHR_ADDR  absolute chr address from `item_sources.py WHO sacs`
  mode          R = light attack burst (3 x R); ZR = strong attack, held `hold` frames (charged when long enough [I])
  dist / dy     horizontal stand-off (m) / height of the player above the sac's own y (0 = same height)
  maxhp         after the first REAL hit (HP below its start), the sac's HP is lowered to this (as fightfoe), so the
                killing blow is still the player's own hit (killer handle = the local player: the crystal gate
                0x174EF3C needs that, treasure_notes 1)
  clearflags=1  TEST ONLY: clear bits 1 (no damage) and 4 (no HP decrease) of the SAC's flag word mod+0x4A0 before
                each burst, if they are set (test_tools_notes 'The data module and its flag word')
  probe=1       READ ONLY: print the diagnosis lines below and exit; writes nothing
  freeze=GAMES  TEST ONLY (catch_notes.md 1): set the engine's debug byte "GameData.AllNoMove" main+0x5B84548 = 1
                on these games (e.g. freeze=A = the host, the enemies' authority; freeze=AB both) for the fight, and
                put the old value back at the end. Read at 0xDA28C4 in the chr movement step: when set, every chr
                that is NOT that game's own player gets no movement applied (the sac still turns / animates, but
                does not run away). It stops ALL enemies on that game, not only the sac.
  side=DEG      first side to stand on (0 = the sac's -z side); if the player ends up more than dist+0.6 m away
                right after the teleport (pushed back by geometry: a ledge / wall), the next burst tries +45 deg
  posfrom=mod|entry  which sac position to use: mod = [[chr+0x2470]+0xE8]+0x70 (default, world_lib.chr_pos),
                entry = the chr-set entry's physics [chr+0x18]+0x28 -> +0x70 (npcs.py). Both are printed each burst
                with the player's absolute position right after the teleport and after the burst.
  hpon=GAME     write the maxhp lowering on GAME's copy of the same enemy (found by handle chr+8), e.g. hpon=A when
                WHO is the guest: the host owns enemy HP and reverts a guest-side write (handoff 1272)

Why: fightfoe.py locks on with StickR. A Bloodsac stands next to bigger enemies (a Milhusa Cavalryman), its NpcParam
row has +0x210 = -1.0 where ordinary enemies have 30.0 [V param; I = lock-on distance], so the lock may pick the
neighbour and every swing goes there. This tool never presses StickR: it puts the player at the sac's height, facing
it, before EVERY burst.

Writes (only this game's memory, no code, no message):
  player phys+0x70 (position) and phys+0x64 (yaw) before each burst, as kill.py;
  the sac's HP mod+0x290 = maxhp, only after a real hit (as fightfoe);
  with clearflags=1 only: the sac's u16 mod+0x4A0 &= ~0x12;
  with freeze=GAMES only: byte main+0x5B84548 on those games (restored at the end, also on Ctrl+C / errors);
  with hpon=GAME only: the HP write goes to GAME's copy instead of WHO's.
Reads per burst: sac HP / max, dead bit, entry flags (chr+0x18 entry +0x10: 5 = near/simulated, 2 = far), flag word
mod+0x4A0, sac and player positions (dy = sac y - player y), whether the sac moved since the last burst.
Exit: 0 dead, 1 time-out, 2 bad chr / no player. Run from the workspace root. Use nodeath.py WHO on first if needed."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl

PAR_WCM = 0x5B3CD88


def opts(argv):
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    o = {'mode': 'R', 'hold': 40, 'dist': 0.9, 'dy': 0.0, 'seconds': 90.0, 'maxhp': 1, 'clearflags': 0, 'probe': 0,
         'freeze': '', 'hpon': '', 'side': 0.0, 'posfrom': 'mod'}
    for a in argv[3:]:
        k, _, v = a.partition('=')
        if k not in o or not _:
            sys.exit('unknown option %s' % a)
        o[k] = v if k in ('mode', 'freeze', 'hpon', 'posfrom') else (
            float(v) if k in ('dist', 'dy', 'seconds', 'side') else int(v))
    return argv[1], int(argv[2], 16), o


def f3(p):
    return '(%.2f %.2f %.2f)' % tuple(p) if p else '?'


ALL_NO_MOVE = 0x5B84548    # "GameData.AllNoMove" (config read 0x1806860 -> strb 0x180687C; used at 0xDA28C4) [V]


def same_enemy(m, handle):
    """chr address of the enemy with this handle (chr+8) on game m (heap search as npcs.find)."""
    import npcs
    for r in npcs.find(m):
        if r['handle'] & 0xFFFFFFFF == handle & 0xFFFFFFFF:
            return r['chr']
    return None


def main():
    who, c, o = opts(sys.argv)
    frozen = {}
    try:
        if o['freeze'] and not o['probe']:
            for g in o['freeze']:
                mg = Mem(g)
                old = mg.read(mg.base + ALL_NO_MOVE, 1)[0]
                mg.write(mg.base + ALL_NO_MOVE, b'\x01')
                frozen[g] = (mg, old)
                print('%s: TEST ONLY AllNoMove main+0x%X %d -> 1 (every enemy on %s stops moving)' % (
                    g, ALL_NO_MOVE, old, g), flush=True)
        return fight(who, c, o)
    finally:
        for g, (mg, old) in frozen.items():
            try:
                mg.write(mg.base + ALL_NO_MOVE, bytes([old]))
                print('%s: AllNoMove restored to %d' % (g, old), flush=True)
            except Exception as e:
                print('%s: AllNoMove NOT restored (%s): run  python diag/twin/mem.py %s w8 main+0x%x %d' % (
                    g, e, g, ALL_NO_MOVE, old), flush=True)


def fight(who, c, o):
    m = Mem(who)
    wcm = m.u64(m.base + PAR_WCM)
    me = struct.unpack('<7Q', m.read(m.u64(wcm + 0x30), 56))
    my_phys = me[5]

    def sac():
        try:
            mod = m.u64(m.u64(c + 0x2470) + 0x18)
            if m.u64(mod + 8) != c:
                return None
            hp, mx = struct.unpack('<ii', m.read(mod + 0x290, 8))
            fl = struct.unpack('<H', m.read(mod + 0x4A0, 2))[0]
            ent = m.u64(c + 0x18)
            e = struct.unpack('<7Q', m.read(ent, 56))
            dead = m.read(m.u64(ent + 0x30) + 0x18, 1)[0] & 1          # [[chr+0x18]+0x30]+0x18 bit 0
            pos_m = struct.unpack('<3f', m.read(m.u64(m.u64(c + 0x2470) + 0xE8) + 0x70, 12))
            pos_e = struct.unpack('<3f', m.read(e[5] + 0x70, 12)) if e[5] else None
            pos = pos_e if (o['posfrom'] == 'entry' and pos_e) else pos_m
            return dict(mod=mod, hp=hp, max=mx, flags=fl, ent=e[2] & 0xFF, dead=dead, pos=pos, pos_m=pos_m,
                        pos_e=pos_e)
        except Exception:
            return None

    s = sac()
    if not s:
        print('%s: chr 0x%x unreadable or not a chr (mod+8 != chr)' % (who, c))
        return 2
    here = struct.unpack('<3f', m.read(my_phys + 0x70, 12))
    print('%s: sac 0x%x hp %d/%d dead %d entry %d flags 0x%04x (bit0 immortal %d, bit1 no-dmg %d, bit4 no-dec %d) '
          'at (%.1f %.1f %.1f); player (%.1f %.1f %.1f), sac y - player y = %.2f' % (
              who, c, s['hp'], s['max'], s['dead'], s['ent'], s['flags'], s['flags'] & 1, (s['flags'] >> 1) & 1,
              (s['flags'] >> 4) & 1, *s['pos'], *here, s['pos'][1] - here[1]), flush=True)
    if o['probe']:
        return 0
    hp_m, hp_mod = None, None
    if o['hpon'] and o['hpon'] != who:
        hp_m = Mem(o['hpon'])
        handle = m.u64(c + 8)
        hc = same_enemy(hp_m, handle)
        if not hc:
            print('%s: no enemy with handle %08x on %s: HP writes stay on %s' % (who, handle & 0xFFFFFFFF, o['hpon'], who))
            hp_m = None
        else:
            hp_mod = hp_m.u64(hp_m.u64(hc + 0x2470) + 0x18)
            print('%s: HP writes go to %s chr 0x%x (same handle %08x)' % (who, o['hpon'], hc, handle & 0xFFFFFFFF),
                  flush=True)
    ref, hit, last = s['hp'], None, s['pos']
    side_k = 0
    t0 = time.time()
    n = 0
    while time.time() - t0 < o['seconds']:
        n += 1
        s = sac()
        if not s:
            print('%s: sac unreadable now (freed?)' % who)
            return 0
        if s['hp'] <= 0 or s['dead']:
            break
        if o['clearflags'] and s['flags'] & 0x12:
            m.write(s['mod'] + 0x4A0, struct.pack('<H', s['flags'] & ~0x12))
            print('%s: TEST ONLY cleared sac flags 0x%04x -> 0x%04x' % (who, s['flags'], s['flags'] & ~0x12), flush=True)
        ep = s['pos']
        a = math.radians(o['side'] + 45.0 * side_k)          # stand on side a, facing the sac
        spot = (ep[0] - o['dist'] * math.sin(a), ep[1] + o['dy'], ep[2] - o['dist'] * math.cos(a))
        m.write(my_phys + 0x70, struct.pack('<3f', *spot))
        m.write(my_phys + 0x64, struct.pack('<f', a))
        time.sleep(0.3)
        here_t = struct.unpack('<3f', m.read(my_phys + 0x70, 12))
        d_t = math.hypot(ep[0] - here_t[0], ep[2] - here_t[2])
        print('   abs: sac(mod +0xE8) %s sac(entry phys) %s | spot %s | me after teleport %s (horiz %.2f)' % (
            f3(s['pos_m']), f3(s['pos_e']), f3(spot), f3(here_t), d_t), flush=True)
        if d_t > o['dist'] + 0.6:
            side_k += 1
            print('   PUSHED BACK %.2f m from the spot: next burst tries side %.0f deg' % (
                math.dist(spot, here_t), (o['side'] + 45.0 * side_k) % 360), flush=True)
        if o['mode'].upper() == 'ZR':
            steps = [{'buttons': ['ZR'], 'frames': o['hold']}, {'frames': 40}]
        else:
            steps = []
            for _ in range(3):
                steps += [{'buttons': ['R'], 'frames': 5}, {'frames': 25}]
        tctl.call(who, {'method': 'input_sequence', 'params': {'steps': steps}})
        s = sac()
        if not s:
            print('%s: sac unreadable now (freed?)' % who)
            return 0
        if hit is None and s['hp'] < ref:
            hit = time.time() - t0
            print('%s: first real hit at %.1f s: hp %d (was %d)' % (who, hit, s['hp'], ref), flush=True)
        if hit is not None and s['hp'] > o['maxhp'] and not s['dead']:
            if hp_mod:
                hp_m.write(hp_mod + 0x290, struct.pack('<i', o['maxhp']))
            else:
                m.write(s['mod'] + 0x290, struct.pack('<i', o['maxhp']))
        here = struct.unpack('<3f', m.read(my_phys + 0x70, 12))
        print('   abs after burst: me %s sac %s' % (f3(here), f3(s['pos'])), flush=True)
        moved = math.dist(last, s['pos'])
        last = s['pos']
        print('%5.1f s burst %d (%s): sac hp %d/%d dead %d entry %d flags 0x%04x moved %.2f m | sac y - me y %.2f | '
              'horiz %.2f m' % (time.time() - t0, n, o['mode'], s['hp'], s['max'], s['dead'], s['ent'], s['flags'],
                                moved, s['pos'][1] - here[1], math.hypot(s['pos'][0] - here[0], s['pos'][2] - here[2])),
              flush=True)
        if s['hp'] <= 0 or s['dead']:
            break
    s = sac()
    if s and (s['hp'] <= 0 or s['dead']):
        print('%s: SAC DEAD after %.1f s (%d bursts, first hit %s)' % (
            who, time.time() - t0, n, '%.1f s' % hit if hit is not None else 'never seen'))
        return 0
    print('%s: time-out, sac %s' % (who, s and (s['hp'], s['flags'], s['ent'])))
    return 1


if __name__ == '__main__':
    sys.exit(main())
