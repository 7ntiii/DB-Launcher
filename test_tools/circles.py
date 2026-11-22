"""Find kin summoning circles and other map-system assets in the world: python diag/twin/circles.py A [ID ..]
Walks every geometry instance; asset id = [info+0x18] % 10000000 (info = [ins+0x10]) [V live: 10099295], circle type = [info+0x306],
holder = [info+0x460]. Default ids: 99290 99291 99292 (big circles Ring / Blade / Eye), 99295 (small circle),
920250. Prints address, asset id, type, holder, position, 'off' when disabled, and for a big circle the kin it
can offer (READ ONLY, nothing is written).

Which kin a big circle offers (diag/net/kin2_notes.md section 1) [V param + code]:
  the circle type byte info+0x306 (1 Ring / 2 Blade / 3 Eye, set at creation from MapSystem kind 0x1B..0x1D) selects
  the BuddySpeciesParam rows with +0xC bit 0 set and +0xD == type (0xD7F300); the lottery 0xD7EE60 picks one of them.
  Not fixed per circle: every circle of one type offers the same pool. Removed from the pool (0xD7F300):
  the presser's own current kin species (0xD7F578..0xD7F58C) and species already held by >= EnemyCommonParam+0x18C
  (= 2) players. Pools (BuddyParam id = species row * 100):
    Ring  (99290, type 1): 603000 Baritone, 604000 Undead Marlowe, 607000 Nia
    Blade (99291, type 2): 601000 Thaumaturge Avester, 602000 Gunslinger Beatrice, 610000 Black Wulf of Mors
    Eye   (99292, type 3): 609000 Valentius the Unwise, 613000 Gargoyle
  So to be offered a DIFFERENT kin for sure, use a circle whose type differs from the current kin's type
  (kin_type(buddy) below); a same-type circle offers only the other species of that type."""
import struct
import sys

sys.path.insert(0, 'diag/twin')

TYPE_NAME = {1: 'Ring', 2: 'Blade', 3: 'Eye'}
CIRCLE_TYPE = {99290: 1, 99291: 2, 99292: 3}        # asset id -> info+0x306 [V live: 1/2/3 in this order]
KIN_POOL = {1: (603000, 604000, 607000), 2: (601000, 602000, 610000), 3: (609000, 613000)}   # [V BuddySpeciesParam +0xD]
KIN_NAME = {601000: 'Avester', 602000: 'Beatrice', 603000: 'Baritone', 604000: 'Marlowe', 607000: 'Nia',
            609000: 'Valentius', 610000: 'Black Wulf', 613000: 'Gargoyle'}


def kin_type(buddy):
    """circle type (1/2/3) whose pool holds this BuddyParam id (9601xx variants map to their base 60xx00), else None"""
    if buddy is None:
        return None
    base = 600000 + (buddy - 960000) * 10 if 960000 <= buddy < 970000 else buddy   # 960100 -> 601000
    for t, ids in KIN_POOL.items():
        if base in ids:
            return t
    return None


def offers(typ, own_buddy=None):
    """BuddyParam ids a circle of type typ can offer to a player whose current kin is own_buddy (cap of 2 holders
    per species not applied: needs every player's kin)"""
    return tuple(b for b in KIN_POOL.get(typ, ()) if b != own_buddy)


def local_has_kin(w):
    """(local player no, True if the BuddyManager has a node of that owner): the branch of the big circle's
    button choice 0x119F440 (kin3_notes.md) [V]: BM = [[WCM+0x5B8]+0x10], nodes from BM+0x18 (sentinel BM+0x10),
    node+0x10 chr, owner [chr+0x20]+0xB8; local no = [[[WCM+0x1A8]+0x20]+0x1D0]+0xD0"""
    wcm = w.wcm()
    me = w.q(wcm + 0x1A8) if wcm else None
    d = w.q(me + 0x20) if me else None
    pgd = w.q(d + 0x1D0) if d else None
    no = w.i(pgd + 0xD0) if pgd else None
    x = w.q(wcm + 0x5B8) if wcm else None
    bm = w.q(x + 0x10) if x else None
    if not bm or no is None:
        return no, None
    node, k = w.q(bm + 0x18), 0
    while node and node != bm + 0x10 and k < 16:
        c = w.q(node + 0x10)
        cd = w.q(c + 0x20) if c else None
        if c and cd and w.i(cd + 0xB8) == no:
            return no, True
        node, k = w.q(node + 8), k + 1
    return no, False


def button_kind(w, info, has_kin):
    """the ActionButtonParam row the prompt uses: info+0x320/+0x328 (no kin) or +0x338/+0x340 (own kin node, 0x119F440)
    as two u64 (printed raw), and byte +2 of the row behind the second word when it reads as a row pointer
    (ActionButtonParam byte +2: 0 = a press (9021..9023), 2 = a hold gauge (9031..9033, stones, forge), 3 = the
    pledge pillar) [V param, I that the second word is the row pointer]"""
    off = 0x338 if has_kin else 0x320
    a, b = w.q(info + off), w.q(info + off + 8)
    kind = w.b(b + 2) if b and b > 0x10000 else None
    return off, a, b, kind


def main():
    from world_lib import W
    w = W(sys.argv[1])
    lno, has_kin = local_has_kin(w)
    print('%s local player %s, own kin node %s -> big circles use button %s' % (
        sys.argv[1], lno, has_kin, 'info+0x338 (903x, HOLD the button ~3-7 s)' if has_kin else 'info+0x320 (902x, a press)'))
    ids = set(int(a) for a in sys.argv[2:]) or {99290, 99291, 99292, 99295, 920250}
    count = {}
    n = 0
    for blockid, k, ins in w.all_geoms(limit=200000):
        n += 1
        info = w.q(ins + 0x10)
        if not info:
            continue
        aid = w.i(info + 0x18)
        if aid is None:
            continue
        aid %= 10000000
        if aid in ids:
            count[aid] = count.get(aid, 0) + 1
            if aid != 99295 or count[aid] <= 3:
                z = w.q(info + 0x20)
                off = bool(z) and w.b(z + 0xD) == 1
                pos = struct.unpack('<3f', w.rd(ins + 0x110, 12))
                typ = w.b(info + 0x306)
                pool = ''
                if aid in CIRCLE_TYPE:
                    pool = ' %s pool %s' % (TYPE_NAME.get(typ, '?'), ' '.join(
                        '%d(%s)' % (b, KIN_NAME[b]) for b in KIN_POOL.get(typ, ())))
                if aid in CIRCLE_TYPE or aid == 99295:
                    off, ra, rb, kind = button_kind(w, info, bool(has_kin) and aid in CIRCLE_TYPE)
                    bits = (w.q(info + 0x468) or 0) & 0xFFF
                    pool += ' | bits(+0x468) %03x used(+0x470) %s | button +0x%x = %s %s kind %s' % (
                        bits, w.b(info + 0x470), off, None if ra is None else '%x' % ra,
                        None if rb is None else '%x' % rb, kind)
                print('%s geom 0x%x asset %d type %d holder %d pos (%.1f %.1f %.1f)%s%s' % (
                    sys.argv[1], ins, aid, typ, w.i(info + 0x460), pos[0], pos[1], pos[2], ' off' if off else '', pool))
    print(sys.argv[1], 'geoms', n, 'counts', count)


if __name__ == '__main__':
    main()
