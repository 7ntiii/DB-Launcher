"""near_body: put rig game B's OWN player 1.5 m beside A's own (dead) player, once. For the fire test
(fire_m2night_notes 4): after A's last-life death in a final, B stands at the body so B's frame rate and probes
see what the laptop saw.
    python diag/twin/near_body.py            (reads A, writes B once)
    python diag/twin/near_body.py --dry      (reads A and B, prints the target, writes nothing)
Reads A's player-set entry 0 (A's own chr: it stays at its death spot on A, v418). Writes ONE 12-byte position
(f32 x y z) to B's own physics +0x70, the same write as goto.py / place.py. No pin, no HP, no other chr, nothing on A.
Refuses (writes nothing) when: A's own player is alive (HP > 0), B's own player is dead, a position is not finite,
or the target is more than 60 m from B (a wrong read). Through the debug server (Dbg 6545 / 6546), like watch_match."""
import math
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

SET = 0x5B3CD88      # player set: [main+SET]+0x30 = entry array, 0x38 per entry, entry 0 = own player
OFF = (1.5, 0.3, 0.0)


def own(m):
    e = m.u64(m.u64(m.base + SET) + 0x30)
    ent = struct.unpack('<7Q', m.read(e, 0x38))
    chr_, ins, phys = ent[0], ent[3], ent[5]
    if not chr_ or not phys:
        return None
    pos = struct.unpack('<3f', m.read(phys + 0x70, 12))
    hp = struct.unpack('<i', m.read(ins + 0xF30, 4))[0] if ins else None
    return {'chr': chr_, 'phys': phys, 'pos': pos, 'hp': hp}


def main():
    dry = '--dry' in sys.argv
    a, b = Mem('A'), Mem('B')
    pa, pb = own(a), own(b)
    if not pa or not pb:
        print('refused: no own player entry on %s' % ('A' if not pa else 'B'))
        return 1
    print('A own: hp %s pos (%.1f, %.1f, %.1f)' % ((pa['hp'],) + pa['pos']))
    print('B own: hp %s pos (%.1f, %.1f, %.1f)' % ((pb['hp'],) + pb['pos']))
    if not all(map(math.isfinite, pa['pos'] + pb['pos'])):
        print('refused: a position is not finite')
        return 1
    if pa['hp'] is None or pa['hp'] > 0:
        print('refused: A\'s own player is not dead (hp %s): use this after A\'s last-life death only' % pa['hp'])
        return 1
    if pb['hp'] is None or pb['hp'] <= 0:
        print('refused: B\'s own player is dead (hp %s)' % pb['hp'])
        return 1
    tgt = tuple(p + o for p, o in zip(pa['pos'], OFF))
    if math.dist(tgt, pb['pos']) > 60:
        print('refused: target %.1f m from B (more than 60 m: a wrong read?)' % math.dist(tgt, pb['pos']))
        return 1
    print('target for B: (%.1f, %.1f, %.1f), %.1f m from B now' % (tgt + (math.dist(tgt, pb['pos']),)))
    if dry:
        print('dry: nothing written')
        return 0
    b.write(pb['phys'] + 0x70, struct.pack('<3f', *tgt))
    time.sleep(0.5)
    now = struct.unpack('<3f', b.read(pb['phys'] + 0x70, 12))
    print('B now (%.1f, %.1f, %.1f), %.1f m from A\'s body' % (now + (math.dist(now, pa['pos']),)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
