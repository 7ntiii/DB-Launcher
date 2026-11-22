"""Leave the "Select revival point" map: python diag/twin/revive.py WHO [plus=1] [confirm=1] [unit=4] [legs=14] [settle=1.5]

Run when the local player is dead (master HP [entry0+0x18]+0xF30 == 0) and the revival-point map is open.
How the map works (static, diag/net/test_tools_notes.md section 2): the map content (CSGfBindData_MapContent)
has a FREE cursor (CursorLeftVh/CursorTopVh at +0x50/+0x54) and a hover focus (FocusIcon, IsVisibleCursorAction,
CursorActionIcon/Name): a point is chosen only while the cursor sits on its icon, then A runs the action. The
revive itself is the warp-with-fade 0x1A92A78 on the fade/warp object *(main+0x5B99BB0) (+0x80 / +0x98 = a
sequence is running) that ends in 0x17BEE4C (warp chr to the point). There is no list index to set: the map is
driven by the stick, and the game's own state tells whether an A press was accepted.

Steps
1. (plus=1) press Plus once, in case the map legend overlay is open over the map.
2. Tries, each: move the cursor, press A; then watch the game state for up to 1.5 s:
   ACCEPTED = fade/warp sequence started ([*(main+0x5B99BB0)+0x80] or +0x98 non-null) or chr+0x26E4 bit 8
   (0x17BEE4C ran) newly set or HP > 0. Not accepted and confirm=1 -> a second A (a confirm dialog, if any),
   watch again. Once accepted, NO more input: wait up to 15 s for HP > 0.
   Tries: A in place; the lead's nudges [1.0, 0.0] x2, [1.0, -0.5] x10, [1.0, 0.3] x2 / x3 (frames); then a
   square spiral around the start point: legs of 1, 1, 2, 2, 3, 3, ... x `unit` frames of full stick (right,
   down, left, up), A after every leg and in the middle of legs >= 3 units. The free cursor sweeps an area
   about (legs/2 * unit) frames of cursor travel in each direction instead of the old 2..9-frame wiggles.
3. Still dead: Plus again (in case step 1 opened the legend) and run the list once more; then a screenshot
   diag/twin/<WHO>_revive_fail.png and exit 1.
As a module: revive.revive(who, plus=True, confirm=True) -> True / False. Run from the workspace root.
Memory is only READ (HP, fade object, chr flags). No in-memory revive: the debug server cannot call game code,
and forcing HP > 0 skips the game's revive (warp, flags, stock), see the notes."""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402
import tctl  # noqa: E402

WS = HERE.parents[1]
FADE_G = 0x5B99BB0     # fade / warp sequence object; +0x80, +0x98 busy  [V 0x1A92AA0..AAC, 0x17AC25C, lives.py]

# (stick, frames); None = press A without moving the cursor
LEAD_TRIES = [None, ((1.0, 0.0), 2), ((1.0, -0.5), 10), ((1.0, 0.3), 2), ((1.0, 0.3), 3)]
DIRS = [(1.0, 0.0), (0.0, -1.0), (-1.0, 0.0), (0.0, 1.0)]   # right, down, left, up (left_stick x, y)


def square_spiral(unit=4, legs=14):
    """legs 1,1,2,2,3,3,... units; split long legs so A is pressed mid-way too"""
    out = []
    for k in range(legs):
        n = k // 2 + 1
        d = DIRS[k % 4]
        if n >= 3:
            h = n // 2
            out.append((d, h * unit))
            out.append((d, (n - h) * unit))
        else:
            out.append((d, n * unit))
    return out


def master_hp(w):
    """[entry0+0x18]+0xF30 (hp.py / final_kills.py); None if unreadable"""
    e = w.player_entry(0)
    return w.i(e[3] + 0xF30) if e and e[3] else None


def signals(w):
    e = w.player_entry(0)
    chr_ = e[0] if e else None
    fo = w.g(FADE_G)
    f80 = w.q(fo + 0x80) if fo else None
    f98 = w.q(fo + 0x98) if fo else None
    fl = w.d(chr_ + 0x26E4) if chr_ else None
    return {'hp': w.i(e[3] + 0xF30) if e and e[3] else None,
            'fade': bool(f80) or bool(f98),
            'b8': None if fl is None else (fl >> 8) & 1,
            'b16': None if fl is None else (fl >> 16) & 1}


def fmt(s):
    return 'HP %s fade %s 26E4.b8 %s b16 %s' % (s['hp'], int(s['fade']), s['b8'], s['b16'])


def steps(who, s):
    return tctl.call(who, {'method': 'input_sequence', 'params': {'steps': s}})


def press(who, btn, frames=6, after=20):
    return steps(who, [{'buttons': [btn], 'frames': frames}, {'frames': after}])


def watch(w, base, secs):
    """'alive' / 'accepted' / None within secs"""
    t0 = time.time()
    while time.time() - t0 < secs:
        s = signals(w)
        if s['hp'] is not None and s['hp'] > 0:
            return 'alive', s
        if s['fade'] or (s['b8'] and not base['b8']):
            return 'accepted', s
        time.sleep(0.2)
    return None, signals(w)


def wait_alive(w, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        hp = master_hp(w)
        if hp is not None and hp > 0:
            return hp
        time.sleep(0.25)
    return None


def one_pass(w, tries, confirm, tag):
    who = w.who
    for k, t in enumerate(tries):
        if t is None:
            desc = 'A only (no move)'
        else:
            (sx, sy), fr = t
            desc = 'left_stick [%.2f, %.2f] %d frames, then A' % (sx, sy, fr)
            steps(who, [{'left_stick': [sx, sy], 'frames': fr}, {'frames': 10}])
        base = signals(w)
        press(who, 'A', 6, 30)
        res, s = watch(w, base, 1.5)
        if res is None and confirm:
            press(who, 'A', 6, 30)
            desc += ' (+ second A)'
            res, s = watch(w, base, 2.0)
        print('%s %s try %2d: %s -> %s | %s' % (who, tag, k, desc, res or 'nothing', fmt(s)), flush=True)
        if res == 'accepted':
            print('%s: revive accepted by the game (fade/warp started): waiting, no more input' % who, flush=True)
            hp = wait_alive(w, 15.0)
            print('%s: after the wait: %s' % (who, fmt(signals(w))), flush=True)
            if hp is not None:
                res = 'alive'
            else:
                print('%s: accepted but HP still 0 after 15 s: continuing with the tries' % who, flush=True)
                continue
        if res == 'alive':
            print('%s: REVIVED by %s try %d: %s, HP %s' % (who, tag, k, desc, master_hp(w)), flush=True)
            return True
    return False


def revive(who, plus=True, confirm=True, unit=4, legs=14, settle=1.5):
    w = W(who)
    hp = master_hp(w)
    if hp is None:
        print('%s: master HP unreadable ([entry0+0x18]+0xF30): no local player entry (loading?)' % who)
        w.report_missing()
        return False
    if hp > 0:
        print('%s: master HP %d > 0: alive, nothing to do' % (who, hp))
        return True
    print('%s: master HP 0: revival map assumed open | %s' % (who, fmt(signals(w))), flush=True)
    s = signals(w)
    if s['fade']:
        print('%s: a fade/warp sequence is already running: waiting for it first' % who, flush=True)
        if wait_alive(w, 15.0):
            print('%s: REVIVED while waiting (HP %s)' % (who, master_hp(w)))
            return True
    time.sleep(settle)       # death camera / map open animation
    tries = LEAD_TRIES + square_spiral(unit, legs)
    if plus:
        print('%s: Plus (close a legend overlay, if open)' % who)
        press(who, 'Plus', 6, 30)
    if one_pass(w, tries, confirm, 'pass 1'):
        return True
    print('%s: pass 1 failed: Plus again (toggle the legend back) and retry' % who, flush=True)
    press(who, 'Plus', 6, 30)
    if one_pass(w, tries, confirm, 'pass 2'):
        return True
    out = WS / 'diag' / 'twin' / ('%s_revive_fail.png' % who)
    print('%s: still dead after both passes (%s); screenshot: %s' % (
        who, fmt(signals(w)), tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}}, out)))
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    o = {'plus': True, 'confirm': True, 'unit': 4, 'legs': 14, 'settle': 1.5}
    for a in sys.argv[2:]:
        k, _, v = a.partition('=')
        if k not in o:
            sys.exit('unknown option %s' % a)
        if k in ('plus', 'confirm'):
            o[k] = v not in ('0', 'no', 'off', 'false')
        elif k == 'settle':
            o[k] = float(v)
        else:
            o[k] = int(v)
    sys.exit(0 if revive(sys.argv[1], o['plus'], o['confirm'], o['unit'], o['legs'], o['settle']) else 1)


if __name__ == '__main__':
    main()
