"""READ-ONLY. Love Ephemeral: why the loved one's 250 part (a) (0x118E3DC..0x118E604) does not mirror the bearer's
reunite (diag/net/love6_notes.md section 2). No writes, no input.
python diag/twin/pkgtest.py run diag/twin/love6_probe.py A        (A = the LOVED game)

Prints, on that game: the own 250 module / holder / writer / logic (reunited +0x48, mask), root = logic+0x40 with
BOTH class-B lists root+0x90 and root+0x98 (entries: handle -> player no, flag, slot), and for each listed bearer the
STOCK part-(a) lookup (first SQM entry with that id, the list's slot byte, ACTIVE holder +0x20 only, logic vt+0x150 =
+0x48) next to a tolerant lookup (every entry, slots 0..2, holder +0x20 else +0x28, vtable 240).
Last line: VERDICT ... (whether the "+0x90 only" cause holds, or where the stock lookup stops)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from world_lib import W, PGD_G    # noqa: E402  (W wraps mem.Mem; only readers are used here)

SQM_G = 0x5B3CE18
VT_ACTIVE, VT_PASSIVE = 0x56F7B38, 0x56F7CA8


def handles(w):
    """{chr handle u16: player no} for the WCM player list (sigils._chr_by_handle)"""
    out = {}
    for e in w.players(12):
        data = w.q(e[0] + 0x20)
        if not data:
            continue
        pg = w.q(data + 0x1D0)
        out[w.h(data + 0x78)] = w.i(pg + 0xD0) if pg else None
    return out


def sqm_entries(w):
    sqm = w.g(SQM_G)
    v0, v1 = (w.q(sqm + 8), w.q(sqm + 0x10)) if sqm else (None, None)
    n = (v1 - v0) // 0x20 if v0 and v1 and v1 >= v0 else 0
    return [v0 + 0x20 * k for k in range(min(n, 32))]


def logic_of(w, m, tolerant):
    hd = w.q(m + 0x20)
    which = '+0x20'
    if not hd and tolerant:
        hd, which = w.q(m + 0x28), '+0x28'
    lg = w.q(hd + 0x10) if hd else None
    vt = (w.q(lg) - w.base) if lg and w.q(lg) else None
    return hd, which, lg, vt


def cond_list(w, c, hmap):
    if not c:
        return 'null', []
    n = w.q(c + 0x58) or 0
    ents = []
    for k in range(min(n, 17)):
        v = w.d(c + 0x10 + 4 * k)
        if v is None:
            continue
        hnd, flag, slot = v & 0xFFFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF
        ents.append((hnd, flag, slot, hmap.get(hnd)))
    txt = ' '.join('0x%04X(flag %d slot %d -> p%s)' % e for e in ents) or 'EMPTY'
    return '%s count %d: %s' % (w.rel(c), n, txt), ents


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else 'A'
    w = W(who)
    pgd = w.g(PGD_G)
    pgd = w.q(pgd + 0x20) if pgd else None
    own = w.i(pgd + 0xD0) if pgd else None
    print('%s: own player %s, slots %s' % (who, own, [w.i(pgd + 0x46E0 + 4 * k) for k in range(3)] if pgd else None))
    ents = sqm_entries(w)
    hmap = handles(w)
    print('SQM entries: %s | player handles: %s' % (
        [w.i(e) for e in ents], ' '.join('0x%04X->p%s' % kv for kv in hmap.items())))
    m250 = lg250 = hd250 = None
    for e in ents:
        if w.i(e) != own:
            continue
        for s in range(3):
            m = w.q(e + 8 + 8 * s)
            if not m:
                continue
            hd, which, lg, vt = logic_of(w, m, True)
            if vt == VT_PASSIVE:
                m250, hd250, lg250 = m, hd, lg
                print('own 250: entry %s slot %d module %s holder %s %s logic %s' % (
                    w.rel(e), s, w.rel(m), which, w.rel(hd), w.rel(lg)))
                break
        if m250:
            break
    if not lg250:
        print('VERDICT NOT LOVED: no 250 logic for the own player on %s' % who)
        return 1
    wr = w.q(hd250 + 0x28)
    reun = w.b(lg250 + 0x48)
    print('own 250: reunited +0x48 %s | module +0x48 %s +0x78 %s mask 0x%X | writer %s +0xA8 %s +0xA9 %s +0xA0 0x%X' % (
        reun, w.b(m250 + 0x48), w.b(m250 + 0x78), (w.q(m250 + 0x38) or 0) & 0xFFF, w.rel(wr),
        w.b(wr + 0xA8) if wr else None, w.b(wr + 0xA9) if wr else None, (w.q(wr + 0xA0) or 0) if wr else 0))
    root = w.q(lg250 + 0x40)
    c90, c98 = (w.q(root + 0x90), w.q(root + 0x98)) if root else (None, None)
    t90, e90 = cond_list(w, c90, hmap)
    t98, e98 = cond_list(w, c98, hmap)
    print('root %s | +0x90 list: %s' % (w.rel(root), t90))
    print('root %s | +0x98 list: %s' % (w.rel(root), t98))

    bearers = []
    for hnd, flag, slot, no in (e90 or e98):
        if flag and no is not None:
            bearers.append((no, slot))
    stock_stop = None
    any_reunited = False
    for no, slot in bearers:
        same = [e for e in ents if w.i(e) == no]
        first = same[0] if same else None
        m = w.q(first + 8 + 8 * slot) if first and slot <= 2 else None
        hd, _, lg, vt = logic_of(w, m, False) if m else (None, None, None, None)
        r = w.b(lg + 0x48) if lg else None
        if not same:
            stop = 'no SQM entry with id %d' % no
        elif slot > 2:
            stop = 'slot byte %d > 2' % slot
        elif not m:
            stop = 'entry id %d slot %d: no module' % (no, slot)
        elif not hd:
            stop = 'module %s: ACTIVE holder +0x20 null (built %s)' % (w.rel(m), w.rel(w.q(m + 0x28)))
        elif not lg:
            stop = 'holder: logic +0x10 null'
        elif vt != VT_ACTIVE:
            stop = 'slot %d logic vtable main+0x%X is not the 240 logic' % (slot, vt or 0)
        elif not r:
            stop = 'bearer 240 reunited +0x48 = %s' % r
        else:
            stop = None
        print('bearer p%d: stock lookup: %d entr%s with that id, first %s, slot %d -> module %s holder +0x20 %s logic %s '
              'vt %s reunited %s -> %s' % (no, len(same), 'y' if len(same) == 1 else 'ies', w.rel(first), slot,
                                          w.rel(m), w.rel(hd), w.rel(lg), 'main+0x%X' % vt if vt else None, r,
                                          'PASS' if not stop else 'STOP: ' + stop))
        tol = []
        for e in same:
            for s in range(3):
                mm = w.q(e + 8 + 8 * s)
                if mm:
                    h2, which, l2, v2 = logic_of(w, mm, True)
                    if v2 == VT_ACTIVE:
                        tol.append('entry %s slot %d holder %s reunited %s' % (w.rel(e), s, which, w.b(l2 + 0x48)))
                        any_reunited = any_reunited or bool(w.b(l2 + 0x48))
        print('bearer p%d: tolerant lookup (LOVE6): %s' % (no, '; '.join(tol) or 'no 240 logic found'))
        stock_stop = stock_stop if stock_stop is not None else stop

    if reun:
        print('VERDICT ALREADY REUNITED: the own 250 is reunited; nothing to judge')
    elif not c90 and e98:
        print('VERDICT +0x90 CAUSE HOLDS: root+0x90 null, the bearer list is at +0x98 -> stock part (a) returns at '
              '0x118E458 (and (b) too); LOVE6 reads +0x98 and %s' % (
                  'finds the bearer reunited (would pay 2501)' if any_reunited else 'finds no reunited 240 yet'))
    elif not bearers:
        print('VERDICT NO LISTED BEARER: both lists empty / unflagged -> pairing (LOVE5) is the gap, not part (a)')
    elif stock_stop:
        print('VERDICT +0x90 cause does NOT hold (list at +0x90); stock part (a) stops at: %s; LOVE6 %s' % (
            stock_stop, 'covers it' if any_reunited else 'finds no reunited 240 either'))
    else:
        print('VERDICT stock lookup complete and bearer reunited -> part (a) should fire: check own 250 module '
              '+0x78 (1), module +0x48 (0), writer +0xA8 1 / +0xA9 0 / +0xA0 bit 6 above (update gate 0x1177930)')
    w.report_missing()
    return 0


if __name__ == '__main__':
    sys.exit(main())
