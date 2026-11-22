"""TEST ONLY - NEVER SHIP. Bring ordinary enemies next to a player (live 3-player tests: the laptop player fights them).
python diag/twin/bring_enemy.py WHO list NO [maxhp=400] [n=12]            read only: candidates near game WHO's player
python diag/twin/bring_enemy.py WHO NO [count=1] [dist=4] [maxhp=400] [maxmove=250] [dry=1]

  WHO      A, B or auto (auto: the rig game that DRIVES the most candidates; both A and B are read)
  NO       player number to bring the enemies to (e.g. 2 = the laptop), as game WHO sees it (starfrag.player_positions)
  count    enemies to move (one write each, nearest to WHO's own player first, i.e. the ones WHO drives)
  dist     metres from player NO; the enemies are spread around it (0, 120, 240 deg ...) at the PLAYER's height
  maxhp    only enemies with 1 <= HP and max HP <= maxhp (never bosses, Trespassers, kin, players, Bloodsacs)
  maxmove  refuse a move longer than this (m)
  dry=1    print what would be written, write nothing

Safety (an earlier quick tool wrote a wrong field and froze the host):
- written ONLY on the game that DRIVES the enemy: the assist's owner flag (sync set +0x18 s16 >= 0 on that game,
  strike.sync_map / own_now, the same reading as strike.py and cmp_enemies.py), re-read just before the write;
- the chr must have the enemy vtable main+0x572B108, its entry [chr+0x18] must point back, entry flags low byte 5
  (loaded / simulated), it must not be a kin (BuddyManager) or a Bloodsac (NpcParam +0x4EE bit 3), not dead;
- the entry's physics object (entry +0x28, the field npcs.find / killchr.py read, +0x70 position) must be the same
  object as [[chr+0x2470]+0xE8] (the chr's own physics), so the one write cannot leave two positions apart;
- source, player and destination positions finite and |v| < 20000; destination y = the player's y (+0.3);
- the write is 12 bytes of 3 finite floats at physics+0x70 (as W.goto does for a player), read back at once,
  after 0.5 s and after 2 s; a move that snaps back is reported, never repeated in a loop;
- any doubt (unreadable field, owner changed, different physics objects) -> REFUSED for that enemy, nothing written.
Exit 0 = every requested enemy moved and stayed, 1 = fewer, 2 = refused / bad arguments."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, ENEMY_VT  # noqa: E402
import npcs  # noqa: E402
from strike import target, sync_map, kin_map, own_now  # noqa: E402
from starfrag import player_positions  # noqa: E402

LIMIT = 20000.0


def ok3(p):
    return (p is not None and len(p) == 3 and all(isinstance(v, float) and math.isfinite(v) and abs(v) < LIMIT
                                                  for v in p))


def f3s(p):
    return '(%.2f %.2f %.2f)' % tuple(p) if ok3(p) else repr(p)


def opts(argv):
    o = {'count': 1, 'dist': 4.0, 'maxhp': 400, 'maxmove': 250.0, 'dry': 0, 'n': 12}
    pos = []
    for a in argv:
        k, eq, v = a.partition('=')
        if not eq:
            pos.append(a)
        elif k in ('count', 'maxhp', 'dry', 'n'):
            o[k] = int(v)
        elif k in ('dist', 'maxmove'):
            o[k] = float(v)
        else:
            raise SystemExit('unknown option %s' % a)
    return pos, o


def candidates(w, o):
    """[(view, reason or None)] for every enemy-vtable chr on game w; view = strike.target() dict + own"""
    sm, km = sync_map(w), kin_map(w)
    out = []
    for r in npcs.find(w.m):
        c = r['chr']
        t = target(w, c, 'auto', sm=sm, km=km)
        if t is None:
            continue
        why = []
        if t['vt'] != w.base + ENEMY_VT:
            why.append('not the enemy class')
        if not t['entry_ok']:
            why.append('entry does not point back')
        elif t['eflags'] != 5:
            why.append('entry flags %s (not 5 = loaded)' % t['eflags'])
        if t['kin'] is not None:
            why.append('kin')
        if t['sac']:
            why.append('Bloodsac')
        if t['gone'] or t['hp'] is None or t['hp'] < 1:
            why.append('dead / no HP (%s)' % t['hp'])
        if t['max'] is None or t['max'] > o['maxhp'] or (t['hp'] or 0) > o['maxhp']:
            why.append('HP %s / %s above maxhp %d' % (t['hp'], t['max'], o['maxhp']))
        if not t['same_phys']:
            why.append('entry physics 0x%x != chr physics 0x%x' % (t['phys_e'] or 0, t['phys_bag'] or 0))
        if not ok3(t['pos_e']):
            why.append('position %s' % f3s(t['pos_e']))
        if t['own'] is None:
            why.append('no owner flag (not in a sync set)')
        elif t['own'] < 0:
            why.append('driven by another game (owner flag %d)' % t['own'])
        out.append((t, '; '.join(why) or None))
    return out


def player_pos(w, no):
    pos = player_positions(w)
    p = pos.get(no)
    return p if ok3(p) else None


def show(w, no, o):
    me = w.me()[2]
    tp = player_pos(w, no)
    print('%s: own player at %s, player %s at %s' % (w.who, f3s(me), no, f3s(tp)))
    rows = candidates(w, o)
    ref = me if ok3(me) else tp
    rows.sort(key=lambda r: math.dist(ref, r[0]['pos_e']) if ok3(r[0]['pos_e']) and ref else 1e9)
    usable = [r for r in rows if r[1] is None]
    print('%s: %d enemy chrs, %d usable here (driven by %s, HP <= %d, loaded, one physics object)' % (
        w.who, len(rows), len(usable), w.who, o['maxhp']))
    for t, why in rows[:o['n']]:
        d = math.dist(ref, t['pos_e']) if ok3(t['pos_e']) and ref else float('nan')
        print('  chr %x handle %04x hp %s/%s own %s pos %s %.0f m from %s%s' % (
            t['chr'], t['handle'] or 0, t['hp'], t['max'], t['own'], f3s(t['pos_e']), d,
            'own player' if ref is me else 'player %s' % no, '' if why is None else '  -- ' + why))
    return usable


def move_one(w, t, dest, o):
    """one validated write on game w; (ok, text)"""
    c = t['chr']
    # re-read everything just before the write
    t2 = target(w, c, 'auto', sm=sync_map(w), km=kin_map(w))
    if t2 is None or t2['chr'] != c:
        return False, 'REFUSED: chr %x not readable any more' % c
    if not t2['entry_ok'] or t2['eflags'] != 5 or not t2['same_phys'] or t2['kin'] is not None or t2['gone']:
        return False, 'REFUSED: chr %x changed (entry %s flags %s same physics %s kin %s gone %s)' % (
            c, t2['entry_ok'], t2['eflags'], t2['same_phys'], t2['kin'], t2['gone'])
    own = own_now(w, t2['own_addr'])
    if own is None or own < 0:
        return False, 'REFUSED: chr %x is not driven by %s now (owner flag %s)' % (c, w.who, own)
    src = t2['pos_e']
    if not ok3(src) or not ok3(dest):
        return False, 'REFUSED: source %s / destination %s not valid' % (f3s(src), f3s(dest))
    if math.dist(src, dest) > o['maxmove']:
        return False, 'REFUSED: move of %.0f m > maxmove %.0f' % (math.dist(src, dest), o['maxmove'])
    phys = t2['phys_e']
    if not phys or w.q(w.q(c + 0x18) + 0x28) != phys:
        return False, 'REFUSED: physics object of %x changed' % c
    if o['dry']:
        return True, 'dry: would write %s at physics 0x%x+0x70 (now %s)' % (f3s(dest), phys, f3s(src))
    w.write(phys + 0x70, struct.pack('<3f', *dest))
    back0 = w.f3(phys + 0x70)
    time.sleep(0.5)
    back1 = w.f3(phys + 0x70)
    time.sleep(1.5)
    t3 = target(w, c, 'auto', sm={}, km={})
    back2 = t3['pos_e'] if t3 else None
    held = ok3(back2) and math.dist(back2, dest) <= 3.0
    return held, 'chr %x hp %s: %s -> %s; read back %s, 0.5 s %s, 2 s %s%s' % (
        c, t2['hp'], f3s(src), f3s(dest), f3s(back0), f3s(back1), f3s(back2),
        '' if held else '  !! did not stay (snapped back or moved away): not repeated')


def main():
    pos, o = opts(sys.argv[1:])
    if len(pos) < 2:
        print(__doc__)
        return 2
    who = pos[0]
    if pos[1] == 'list':
        if len(pos) < 3:
            print(__doc__)
            return 2
        for g in (('A', 'B') if who == 'auto' else (who,)):
            show(W(g), int(pos[2]), o)
        return 0
    no = int(pos[1])
    games = ('A', 'B') if who == 'auto' else (who,)
    best = None
    for g in games:
        w = W(g)
        usable = show(w, no, o)
        if best is None or len(usable) > len(best[1]):
            best = (w, usable)
    w, usable = best
    tp = player_pos(w, no)
    if tp is None:
        print('REFUSED: no valid position for player %s on %s' % (no, w.who))
        return 2
    if not usable:
        print('REFUSED: no usable enemy driven by %s (see the list; run with the game whose player is near some '
              'ordinary enemies, or raise maxhp)' % ('/'.join(games)))
        return 2
    print('%s drives %d usable enemies; moving %d to %.1f m from player %s %s' % (
        w.who, len(usable), min(o['count'], len(usable)), o['dist'], no, f3s(tp)))
    moved = 0
    for k, (t, _) in enumerate(usable[:o['count']]):
        a = math.radians(120.0 * k + 30.0)
        dest = (tp[0] + o['dist'] * math.sin(a), tp[1] + 0.3, tp[2] + o['dist'] * math.cos(a))
        okk, text = move_one(w, t, dest, o)
        print('  %s %s' % ('OK ' if okk else '-- ', text), flush=True)
        moved += 1 if okk else 0
    print('RESULT bring_enemy %s: %d of %d moved on %s to player %s' % (
        'PASS' if moved == min(o['count'], len(usable)) else 'PARTIAL' if moved else 'FAIL',
        moved, min(o['count'], len(usable)), w.who, no))
    return 0 if moved == min(o['count'], len(usable)) else 1


if __name__ == '__main__':
    sys.exit(main())
