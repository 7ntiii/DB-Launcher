"""Read / write a round's cut limit (PhaseInfoParam +0x92, "advance count") on each twin game.
python diag/twin/cutlimit.py GAMES ROUND [VALUE] [force]
  GAMES  e.g. ABC     ROUND 1..4 (0 = par+0x118 cfg)     VALUE -1..127 (omit = print only)
  e.g.   python diag/twin/cutlimit.py ABC 2 2      (many_players_fix_notes test list: round 2 cut limit 2)

The cut (0xF879A0, match_structure_notes 'End-of-phase decision'): every entry not at stage 4 whose rank is
> PhaseInfo +0x92 is eliminated; < 0 = no cut. Stock LAN rows 1002000Y: I -1, II 6, III 3, final -1.
Row lookup (match_structure_notes 'Per-phase rules'; virtue.py comm_manager does the same):
  par = *(main+0x5B3CDF8); cfg = [par+0xD0+8*(round-1)] (round 0: [par+0x118]) = {vt main+0x56D8A28,
  +8 row id, +0x10 row ptr}; the cut limit is the s8 at row+0x92.
Checks before writing (refused unless 'force'): par, cfg and row non-null, cfg vtable == main+0x56D8A28,
row id % 10 == ROUND. Prints the row address, row id, the round's other values and old -> new (read back).
Note: the row is the loaded param data, so the change lasts for every later match of that game session."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, PAR_G  # noqa: E402

CFG_VT = 0x56D8A28
# 2026-11-16 runcut2 15:07: B's round-2 cfg had vtable main+0x56D8A38 (B's own base, W(who).base: the base was not
# the cause, every other read on B was right and the row's values matched virtue.py's). Two cfg classes are seen,
# 0x10 apart; both are accepted. The row id check (id % 10 == round, same 1002000x table as the other rounds)
# stays the real guard.
CFG_VTS = (0x56D8A28, 0x56D8A38)


def cfg_of(w, par, rnd):
    return w.q(par + 0x118) if rnd == 0 else w.q(par + 0xD0 + 8 * (rnd - 1))


def row_text(w, row):
    b = w.rd(row, 0x100)
    if not b:
        return 'row unreadable'
    t_i, t_f = struct.unpack_from('<i', b, 4)[0], struct.unpack_from('<f', b, 4)[0]
    return ('time +4 %d (as float %.1f) | cut +0x92 %d | Bloodfang +0x8D/+0x8E %d/%d | Collector +0x93/+0x94 '
            '%d/%d | +0x95 %d +0x96 %d | checkpoints +0xEC %s | final check +0xF6 %d') % (
        t_i, t_f, struct.unpack_from('<b', b, 0x92)[0], b[0x8D], b[0x8E], b[0x93], b[0x94], b[0x95], b[0x96],
        list(struct.unpack_from('<5h', b, 0xEC)), struct.unpack_from('<h', b, 0xF6)[0])


def one(who, rnd, value, force):
    try:
        w = W(who)
    except Exception as e:  # noqa: BLE001
        print('%s: no debug server: %s' % (who, e))
        return False
    par = w.g(PAR_G)
    if not par:
        print('%s: par *(main+0x5B3CDF8) is null (not in a match): refused' % who)
        return False
    print('%s: par %s step %s round %s' % (who, hex(par), w.d(par + 0x50), w.d(par + 0xB8)))
    for r in range(1, 5):                      # overview: every round's row id and cut
        c = cfg_of(w, par, r)
        rw = w.q(c + 0x10) if c else None
        cut = w.rd(rw + 0x92, 1) if rw else None
        print('    round %d cfg %s row id %s row %s cut %s' % (
            r, hex(c) if c else 'null', w.d(c + 8) if c else None, hex(rw) if rw else 'null',
            struct.unpack('<b', cut)[0] if cut else None))
    cfg = cfg_of(w, par, rnd)
    if not cfg:
        print('%s: cfg of round %d is null: refused' % (who, rnd))
        return False
    vt = w.q(cfg)
    rid = w.d(cfg + 8)
    row = w.q(cfg + 0x10)
    if not row:
        print('%s: row pointer cfg+0x10 is null: refused' % who)
        return False
    print('%s: round %d cfg %s vt %s row id %s row %s' % (who, rnd, hex(cfg), w.rel(vt), rid, hex(row)))
    print('    %s' % row_text(w, row))
    bad = []
    if vt is None or vt - w.base not in CFG_VTS:
        bad.append('cfg vtable %s not in %s' % (w.rel(vt), ', '.join('main+0x%X' % v for v in CFG_VTS)))
    if rid is None or rid % 10 != rnd:
        bad.append('row id %s does not end in %d' % (rid, rnd))
    ids = [w.d(c + 8) for c in (cfg_of(w, par, r) for r in range(1, 5)) if c]
    if rid is not None and any(i is not None and i // 10 != rid // 10 for i in ids):
        bad.append('row id %s not in the same table as the other rounds %s' % (rid, ids))
    if bad:
        print('%s: %s%s' % (who, '; '.join(bad), ' (force: writing anyway)' if force else ': refused (add force)'))
        if not force:
            return False
    if value is None:
        return True
    old = struct.unpack('<b', w.rd(row + 0x92, 1))[0]
    w.write(row + 0x92, struct.pack('<b', value))
    new = struct.unpack('<b', w.rd(row + 0x92, 1))[0]
    print('%s: round %d cut limit (row %s +0x92) %d -> %d%s' % (
        who, rnd, hex(row), old, new, '' if new == value else '  READ-BACK MISMATCH'))
    return new == value


def main():
    args = [a for a in sys.argv[1:] if a != 'force']
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    games, rnd = args[0], int(args[1])
    value = int(args[2]) if len(args) > 2 else None
    if not 0 <= rnd <= 9 or (value is not None and not -128 <= value <= 127):
        sys.exit('ROUND 0..9, VALUE -128..127')
    ok = [one(g, rnd, value, 'force' in sys.argv) for g in games]
    sys.exit(0 if all(ok) else 1)


if __name__ == '__main__':
    main()
