"""TEST ONLY: choose a Bloodsworn (CharaInitParam row) in the hub the way a player does it, through
House of Night menu -> Bloodsworn Selection, and check that the row apply really ran.
python diag/twin/pick_bloodsworn.py WHO ROW [show] [--force]      (run from the workspace root, game in the hub)
python diag/twin/pick_bloodsworn.py WHO show                        (read only)

Why menu input and not a memory write (diag/net/sigil9_notes.md 1): the decide functor 0x1440558 runs the row apply
0xCE7280(GDM, [GDM+0x20], row) (skills -> pgd+0x1C6C, pgd+0xEC8 = row) and only then stores the row at
pgd+0x10C (0x14408AC). Writing pgd+0x10C alone does nothing for the sigil producer. This tool presses
Minus (menu, Dusk Battle tab), R (Bloodsworn Selection tab), moves the focus and presses A (Select). It detects
each decide with a sentinel: it writes 0 into pgd+0x10C before A and reads which row the decide wrote back. If no
decide happened, it puts the old value back. The list order (push order of 0x143D5A0, preset table ro 0x4C4AEF0):
OFF then ON for Albert, Jan, Trang, Layla, Samir, Zork. It learns how far Down / Right move from the rows it gets.
Every intermediate decide is a normal menu choice. Screenshots: diag/twin/WHO_pick_*.png.
Rows with a sigil: 600000 Albert / 600020 Trang (Sworn Enemy), 600010 Jan (Eye of Muralis), 600030 Layla /
600050 Zork (Old Friend), 600040 Samir (Love Ephemeral); rows ending in 1 = the same Bloodsworn without sigil."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, PGD_G
import sigils
from screen import grab, state, press
from tctl import call

ORDER = [600001, 600000, 600011, 600010, 600021, 600020, 600031, 600030, 600041, 600040, 600051, 600050]
SENT = 0                      # never a CharaInitParam row; the match-start re-apply 0x11C0A0C skips rows < 0 only


def pgd_of(w):
    gdm = w.g(PGD_G)
    return w.q(gdm + 0x20) if gdm else None


def snapshot(w):
    p = pgd_of(w)
    if not p:
        return None
    pairs = [x for _, x in sigils.sigil_pairs(w, p) if x]
    return {'pgd': p, 'row': w.i(p + 0x10C), 'applied': w.i(p + 0xEC8), 'pairs': pairs}


def show(w, s, label):
    if not s:
        print('%s %s: no local pgd ([GDM+0x20] null): not in the hub / still loading' % (w.who, label))
        return
    print('%s %s: pgd %s' % (w.who, label, w.rel(s['pgd'])))
    print('   pgd+0x10C chosen row  = %s -> %s' % (s['row'], sigils.preset_txt(s['row'])))
    print('   pgd+0xEC8 applied row = %s -> %s' % (s['applied'], sigils.preset_txt(s['applied'])))
    if s['pairs']:
        for off, i, c, first30 in s['pairs']:
            print('   pgd+0x%X = {%d, %d} %s%s' % (off, i, c, sigils.SKILL[i // 10 * 10],
                                               '' if first30 else ' (outside the 30 pairs the producer reads)'))
    else:
        print('   no sigil skill pair in the pgd skill blocks (the producer finds no sigil)')


def verdict(w, s, row):
    want = sigils.PRESET.get(row, (None, None))[1]
    ok1 = s['row'] == row
    ok2 = s['applied'] == row
    hit = [x for x in s['pairs'] if x[3] and x[2] >= 1 and x[1] // 10 * 10 == want] if want else []
    print('   %s +0x10C = %s (want %d: the decide 0x14408AC stored it)' % ('PASS' if ok1 else 'FAIL', s['row'], row))
    print('   %s +0xEC8 = %s (want %d: the row apply 0xCE7280 ran)' % ('PASS' if ok2 else 'FAIL', s['applied'], row))
    if want:
        print('   %s pair {%d, 1} in pgd+0x1C6C (first 30 pairs: what the producer 0x1195E40 reads)%s' % (
            'PASS' if hit else 'FAIL', want, ' at +0x%X' % hit[0][0] if hit else ''))
    else:
        others = [x for x in s['pairs'] if x[2] >= 1]
        print('   %s no-sigil row: %s' % ('PASS' if not others else 'NOTE', 'no sigil pair' if not others else
                                         'a sigil pair is still there (give_sigil.py earlier?)'))
    return ok1 and ok2 and (bool(hit) if want else True)


def shot(who, name):
    try:
        call(who, {'method': 'screenshot', 'params': {'height': 480}}, 'diag/twin/%s_pick_%s.png' % (who, name))
    except Exception:
        pass


def scr(who):
    try:
        return state(grab(who))[0]
    except Exception:
        return 'other'


def open_tab(who):
    """hub -> Minus (menu on the Dusk Battle tab) -> R (Bloodsworn Selection). True when not on the hub / Dusk
    Battle menu afterwards (the Bloodsworn tab has no reference shot: 'other' is the expected state)."""
    s = scr(who)
    if s == 'hub':
        press(who, 'Minus')
        time.sleep(1.5)
        s = scr(who)
    if s == 'mmenu':
        press(who, 'R')
        time.sleep(1.5)
        s = scr(who)
    if s == 'mmenu':                 # R dropped: once more
        press(who, 'R')
        time.sleep(1.5)
        s = scr(who)
    return s not in ('hub', 'mmenu', 'mmgo', 'settings')


def decide(w, who, p):
    """press A on the focused item; returns the row the decide wrote into pgd+0x10C, or None"""
    old = w.i(p + 0x10C)
    for k in range(2):               # second A: a confirm dialog after Select [I]
        w.write(p + 0x10C, struct.pack('<i', SENT))
        press(who, 'A')
        time.sleep(1.2)
        v = w.i(p + 0x10C)
        if v not in (None, SENT):
            return v
    w.write(p + 0x10C, struct.pack('<i', old))
    return None


def plan(c, t, dd, dr):
    """fewest presses (Down/Up by dd, Right/Left by dr) from list index c to t"""
    best = None
    for a in range(-12, 13):
        for b in range(-12, 13):
            if a * dd + b * dr == t - c and (dd or not a) and (dr or not b):
                if best is None or abs(a) + abs(b) < abs(best[0]) + abs(best[1]):
                    best = (a, b)
    if best is None:
        return None
    a, b = best
    return ['Down' if a > 0 else 'Up'] * abs(a) + ['Right' if b > 0 else 'Left'] * abs(b)


def close_menu(who):
    for _ in range(5):
        if scr(who) == 'hub':
            return True
        press(who, 'B')
        time.sleep(1.2)
    return scr(who) == 'hub'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    if not args:
        raise SystemExit(__doc__)
    who = args[0]
    w = W(who)
    if len(args) < 2 or args[1] == 'show':
        show(w, snapshot(w), 'now')
        return
    row = int(args[1])
    if row not in ORDER:
        raise SystemExit('ROW must be one of %s' % ORDER)
    only_show = len(args) > 2 and args[2] == 'show'
    before = snapshot(w)
    show(w, before, 'before')
    if only_show or not before:
        if before:
            verdict(w, before, row)
        return
    if not force and scr(who) != 'hub':
        raise SystemExit('%s is not on the hub screen (screen.py); bring it to the hub or use --force' % who)
    t = ORDER.index(row)
    p = before['pgd']
    if not open_tab(who):
        shot(who, 'tab')
        raise SystemExit('could not open Bloodsworn Selection (still on hub / Dusk Battle menu): see %s_pick_tab.png'
                         % who)
    shot(who, 'tab')
    v = decide(w, who, p)
    if v is None:
        shot(who, 'nodecide')
        close_menu(who)
        raise SystemExit('A did not decide anything (pgd+0x10C unchanged, restored). Screens: %s_pick_tab.png, '
                         '%s_pick_nodecide.png. By hand: Minus, R, move to the entry "Sigil of ..." of the '
                         'Bloodsworn, A; then run this tool with "show".' % (who, who))
    print('   decided on the focused item: %s (%s)' % (v, sigils.preset_txt(v)))
    deltas = {}
    log = [v]
    for btn in ('Down', 'Right'):
        if v == row or v not in ORDER:
            break
        if not open_tab(who):
            pass
        press(who, btn)
        time.sleep(0.6)
        v2 = decide(w, who, p)
        if v2 is None:
            break
        deltas[btn] = ORDER.index(v2) - ORDER.index(v) if v2 in ORDER else 0
        print('   %s moved %+d (row %s -> %s)' % (btn, deltas[btn], v, v2))
        v = v2
        log.append(v)
        if deltas.get('Down') in (1, -1):     # one list: Down alone reaches every item
            break
    for attempt in range(3):
        if v == row or v not in ORDER:
            break
        seq = plan(ORDER.index(v), t, deltas.get('Down', 0), deltas.get('Right', 0))
        if not seq:
            break
        open_tab(who)
        for b in seq:
            press(who, b)
            time.sleep(0.5)
        v2 = decide(w, who, p)
        print('   pressed %s A -> %s' % (' '.join(seq), v2))
        if v2 is None:
            break
        v = v2
        log.append(v)
    shot(who, 'done')
    closed = close_menu(who)
    after = snapshot(w)
    show(w, after, 'after')
    ok = verdict(w, after, row) if after else False
    print('   decided rows in order: %s; moves learned %s; menu closed: %s' % (log, deltas or '-', closed))
    if ok:
        print('   DONE: nothing more to press on %s. Next: sigils.py %s (section 2 C6 PASS), then matchmaking.'
              % (who, who))
    else:
        print('   NOT DONE: on %s press by hand: Minus, R, move to "%s" (%s), A; check with: python '
              'diag/twin/pick_bloodsworn.py %s %d show. Screens: diag/twin/%s_pick_tab.png / _done.png' % (
                  who, sigils.preset_txt(row), 'list item %d of 12, OFF/ON pairs in the order Albert, Jan, Trang, '
                  'Layla, Samir, Zork' % t, who, row, who))


if __name__ == '__main__':
    main()
