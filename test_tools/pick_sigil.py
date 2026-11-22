"""TEST ONLY: pick a Bloodsworn (with or without its sigil) in the hub's Bloodsworn Selection, blind but verified.
python diag/twin/pick_sigil.py WHO ID [plus=1] [tries=3]   (from the workspace root, game on the hub screen)
python diag/twin/pick_sigil.py WHO ID dry                    (read only: state, plan, show; presses nothing)
python diag/twin/pick_sigil.py WHO learn                     (save the CURRENT screen as the Bloodsworn-tab reference)
python diag/twin/pick_sigil.py WHO show                      (= pick_bloodsworn.py WHO show)

ID: 600000 Albert / 600020 Trang (Sworn Enemy), 600010 Jan (Eye of Muralis), 600030 Layla / 600050 Zork
(Old Friend), 600040 Samir (Love Ephemeral); 6000X1 = the same Bloodsworn without sigil.

What is verified how (diag/net/pick_sigil_notes.md):
  memory      local pgd [GDM+0x20] exists; every A that should DECIDE is checked by the sentinel method of
              pick_bloodsworn.py (0 written into pgd+0x10C before A; the decide 0x14408AC writes the focused item's
              row there; restored if nothing was decided). So the cursor position is read back from memory after
              every confirm, and the result (+0x10C, +0xEC8, pair in +0x1C6C) at the end.
  screenshot  hub (before Minus), Dusk Battle tab = screen.py 'mmenu' (after Minus / L), "left the Dusk Battle tab"
              after the single R; with diag/twin/pick_sigil_ref_tab.png present (made with `learn`) the
              Bloodsworn tab itself. Every press saves diag/twin/WHO_sigil_NN_<step>.png.
  not found   the hub tab index and the list row / column in memory (Gameface UI): no memory check before the
              first A; that A is pressed only after the tab checks above passed.
Rules: R is pressed once and never repeated; A only on a verified Bloodsworn screen; Y never (no matchmaking);
any mismatch stops with a message and the screenshots. Ends on the Dusk Battle tab (Plus closes the first-time
sigil popup, L goes back) and prints `show`."""
import os
import shutil
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W                     # noqa: E402

import pick_bloodsworn as PB                 # noqa: E402  (snapshot / show / verdict, no side effects on import)
from screen import grab, state, press, d     # noqa: E402
from PIL import Image                        # noqa: E402

D = 'diag/twin/'
REF_TAB = D + 'pick_sigil_ref_tab.png'
REF_LIMIT = 12.0          # mean grey difference on 64x36 [U: not calibrated; see the notes]
SENT = PB.SENT
COLS = {0: 'Albert', 1: 'Jan', 2: 'Trang', 3: 'Layla', 4: 'Samir', 5: 'Zork'}
START = (0, 0)            # (sigil row 0/1, column): the list opens on Albert "No Sigil" (known by hand)
MENU_STATES = ('hub', 'mmgo', 'settings', 'err', 'menu', 'black')
step_no = [0]


class Stop(Exception):
    pass


def cell(row):
    """CharaInitParam row -> (sigil 1 / no sigil 0, column)"""
    k = row - 600000
    if k < 0 or k > 51 or k % 10 not in (0, 1) or k // 10 not in COLS:
        return None
    return (1 if k % 10 == 0 else 0, k // 10)


def row_of(c):
    return 600000 + 10 * c[1] + (0 if c[0] else 1)


def name(row):
    c = cell(row)
    return '%d (%s, %s)' % (row, COLS[c[1]], 'sigil' if c[0] else 'no sigil') if c else str(row)


def look(who, label):
    """screenshot -> screen.py state; the frame is kept as diag/twin/WHO_sigil_NN_label.png"""
    im = grab(who)
    s, dist = state(im, who)
    step_no[0] += 1
    src = '%s_live_%s.png' % (D, who)
    if os.path.exists(src):
        try:
            shutil.copyfile(src, '%s%s_sigil_%02d_%s.png' % (D, who, step_no[0], label))
        except OSError:
            pass
    return s, dist, im


def tab_distance(im):
    if not os.path.exists(REF_TAB):
        return None
    ref = Image.open(REF_TAB).convert('L').resize((64, 36), Image.BOX)
    return d(im.resize((64, 36), Image.BOX), ref)


def wait_state(who, label, good, seconds=3.0):
    """poll the screen until good(state) or the time is up; returns (state, dist, image)"""
    end = time.time() + seconds
    while True:
        s, dist, im = look(who, label)
        if good(s) or time.time() >= end:
            return s, dist, im
        time.sleep(0.6)


def decide(w, who, p, label):
    """A with the sentinel: the row the decide wrote, or None (nothing decided; +0x10C restored)"""
    old = w.i(p + 0x10C)
    w.write(p + 0x10C, struct.pack('<i', SENT))
    press(who, 'A')
    end = time.time() + 1.6
    v = SENT
    while time.time() < end:
        time.sleep(0.3)
        v = w.i(p + 0x10C)
        if v not in (None, SENT):
            break
    look(who, label)
    if v in (None, SENT):
        w.write(p + 0x10C, struct.pack('<i', old))
        return None
    return v


def moves(a, b):
    """presses from cell a to cell b (rows Down / Up, columns Right / Left)"""
    out = ['Down' if b[0] > a[0] else 'Up'] * abs(b[0] - a[0])
    out += ['Right' if b[1] > a[1] else 'Left'] * abs(b[1] - a[1])
    return out


def open_bloodsworn(who, dry):
    """hub -> Minus -> (L until Dusk Battle) -> R once. Raises Stop unless every step was verified."""
    s, dist, _ = look(who, 'start')
    print('   screen %s (%.1f)' % (s, dist))
    if s != 'hub':
        raise Stop('%s is not on the hub screen (screen.py says %s): bring it to the hub first' % (who, s))
    if dry:
        print('   dry: would press Minus, then L until the Dusk Battle tab (screen.py mmenu, at most 6), then R once')
        return
    press(who, 'Minus')
    s, dist, _ = wait_state(who, 'minus', lambda x: x != 'hub')
    print('   Minus -> %s (%.1f)' % (s, dist))
    if s == 'hub':
        raise Stop('Minus did not open the hub menu')
    tries = 0
    while s != 'mmenu':
        if s in MENU_STATES:
            raise Stop('after Minus the screen is %s, not a hub-menu tab' % s)
        if tries >= 6:
            raise Stop('6 x L did not reach the Dusk Battle tab (screen.py mmenu)')
        press(who, 'L')
        tries += 1
        s, dist, _ = wait_state(who, 'L%d' % tries, lambda x: x == 'mmenu', 2.5)
        print('   L -> %s (%.1f)' % (s, dist))
    print('   Dusk Battle tab: VERIFIED (screen.py mmenu)')
    press(who, 'R')                       # once; never repeated (a repeat went one tab too far before)
    s, dist, im = wait_state(who, 'R', lambda x: x != 'mmenu', 3.0)
    print('   R -> %s (%.1f)' % (s, dist))
    if s == 'mmenu':
        raise Stop('R did not leave the Dusk Battle tab within 3 s; not pressed again. Press R by hand or rerun')
    if s in MENU_STATES:
        raise Stop('after R the screen is %s, not the Bloodsworn Selection tab' % s)
    t = tab_distance(im)
    if t is None:
        print('   Bloodsworn tab: VERIFIED as "one R from the verified Dusk Battle tab, screen left it" '
              '(no reference %s yet: make one with `learn`)' % REF_TAB)
    elif t > REF_LIMIT:
        raise Stop('the screen after R differs from the Bloodsworn-tab reference (%.1f > %.1f)' % (t, REF_LIMIT))
    else:
        print('   Bloodsworn tab: VERIFIED by the reference (%.1f <= %.1f)' % (t, REF_LIMIT))


def confirm_from(w, who, p, pos, target, label):
    """moves from cell pos to the target, then A with the sentinel: the decided row (memory) or Stop"""
    seq = moves(pos, cell(target))
    for b in seq:
        press(who, b)
        time.sleep(0.45)
        look(who, b.lower())
    v = decide(w, who, p, label)
    print('   from %s: %s A -> %s' % (name(row_of(pos)), ' '.join(seq) or '(no move)',
                                    'nothing decided' if v is None else name(v)))
    if v is None:
        raise Stop('the confirm A decided nothing (pgd+0x10C unchanged, restored): the list was not open')
    if cell(v) is None:
        raise Stop('the confirm decided row %s, not a Bloodsworn list row' % v)
    return v


def pick(w, who, p, target, tries):
    """Fast path: A opens the list at START (known by hand), moves, A. Every later round finds the cursor from
    memory first (a decide without moving tells where it is), so no move is ever planned from a guess twice."""
    decided = []
    # round 0: first A on the freshly verified tab. The list is closed, so no sentinel (the menu may read
    # pgd+0x10C when it opens, sigil9_notes 1.1); a change of +0x10C would mean that A decided something.
    current = w.i(p + 0x10C)
    press(who, 'A')
    time.sleep(1.2)
    look(who, 'open')
    now_row = w.i(p + 0x10C)
    if now_row != current and cell(now_row) is not None:
        print('   A decided %s at once (the list was open)' % name(now_row))
        decided.append(now_row)
        pos = cell(now_row)
    elif now_row != current:
        raise Stop('A changed pgd+0x10C to %s, not a Bloodsworn row' % now_row)
    else:
        pos = START
        print('   A opened the list (nothing decided); cursor assumed at %s (by hand)' % name(row_of(START)))
    if decided and decided[-1] == target:
        return decided
    v = confirm_from(w, who, p, pos, target, 'confirm0')
    decided.append(v)
    for k in range(1, tries):
        if v == target:
            return decided
        print('   MISMATCH: the cursor was on %s, not %s; finding it from memory' % (name(v), name(target)))
        # where is the cursor now? A without moving: a decide = the list stayed open (on that item);
        # nothing decided = A reopened the list, then one more A without moving decides the start item
        r = decide(w, who, p, 'find%d' % k)
        if r is None:
            r = decide(w, who, p, 'probe%d' % k)
            if r is None:
                raise Stop('two A presses decided nothing: not in the Bloodsworn list any more')
            print('   reopened list starts on %s (decided, memory)' % name(r))
            decided.append(r)
            if r == target:
                return decided
            # after this decide the last choice IS the start item, so a reopened list starts there under either
            # rule ("fixed start" or "last choice"); one more A tells open (decide) or reopened (nothing)
            r2 = decide(w, who, p, 'find%db' % k)
            if r2 is not None:
                decided.append(r2)
                r = r2
        else:
            decided.append(r)
            print('   list still open, cursor on %s (decided, memory)' % name(r))
        if cell(r) is None:
            raise Stop('decided row %s, not a Bloodsworn list row' % r)
        if r == target:
            return decided
        v = confirm_from(w, who, p, cell(r), target, 'confirm%d' % k)
        decided.append(v)
    if v == target:
        return decided
    raise Stop('target not reached after %d rounds; decided %s (the Down / Right model of the grid does not '
               'fit: see the screenshots)' % (tries, [name(x) for x in decided]))


def back_to_dusk_battle(who, plus):
    if plus:
        time.sleep(1.0)
        press(who, 'Plus')        # first-time sigil popup (by hand: Plus closes it)
        time.sleep(1.0)
        look(who, 'plus')
    press(who, 'L')
    s, dist, _ = wait_state(who, 'back', lambda x: x == 'mmenu', 3.0)
    print('   L -> %s (%.1f)' % (s, dist))
    return s == 'mmenu'


def main():
    args = [a for a in sys.argv[1:]]
    opts = dict(a.split('=', 1) for a in args if '=' in a)
    pos = [a for a in args if '=' not in a]
    if not pos:
        raise SystemExit(__doc__)
    who = pos[0]
    w = W(who)
    if len(pos) < 2 or pos[1] == 'show':
        PB.show(w, PB.snapshot(w), 'now')
        return
    if pos[1] == 'learn':
        s, dist, im = look(who, 'learn')
        im.save(REF_TAB)
        print('%s: saved the current screen (screen.py %s) as %s: use only when the Bloodsworn Selection tab is '
              'open and its list closed' % (who, s, REF_TAB))
        return
    target = int(pos[1], 0)
    if cell(target) is None:
        raise SystemExit('ID must be 6000X0 (sigil) or 6000X1 (no sigil), X = 0..5: %s' % COLS)
    dry = 'dry' in pos[2:]
    plus = opts.get('plus', '1') != '0'
    tries = max(1, min(4, int(opts.get('tries', '3'))))
    before = PB.snapshot(w)
    PB.show(w, before, 'before')
    if not before:
        raise SystemExit('no local pgd: not in the hub')
    print('   target %s; plan from the list start: %s A' % (name(target), ' '.join(moves(START, cell(target)))
                                                         or '(no move)'))
    if before['row'] == target and before['applied'] == target and not dry:
        PB.verdict(w, before, target)
        print('   already chosen: nothing pressed')
        return
    try:
        open_bloodsworn(who, dry)
        if dry:
            print('   dry: then A (open list), the moves above, A (confirm; checked in pgd+0x10C), Plus, L. '
                  'Nothing pressed.')
            PB.verdict(w, before, target)
            return
        decided = pick(w, who, before['pgd'], target, tries)
        print('   decided in order: %s' % [name(x) for x in decided])
        if not back_to_dusk_battle(who, plus and cell(target)[0] == 1):
            print('   NOTE: not back on the Dusk Battle tab (see the last %s_sigil_*.png); the choice is stored '
                  'already. Close the popup / go back by hand.' % who)
    except Stop as e:
        print('   STOP: %s. Screens: diag/twin/%s_sigil_*.png' % (e, who))
    after = PB.snapshot(w)
    PB.show(w, after, 'after')
    ok = PB.verdict(w, after, target) if after else False
    print('   %s. Matchmaking is NOT started by this tool (Y by hand).' % ('DONE' if ok else 'NOT DONE'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
